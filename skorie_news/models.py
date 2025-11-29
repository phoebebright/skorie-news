import json
import os
import logging
import secrets
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from anymail.message import AnymailMessage
from django.conf import settings
from django.contrib.auth import get_user_model, apps
from django.contrib.postgres.fields import ArrayField
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Max

from django.template import Context
from django.template.loader import select_template, render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import strip_tags
from django.utils.module_loading import import_string
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

# can't import from skorie.common as get circular import
from .model_mixins import EventMixin, CreatedUpdatedMixin
from .skorie_storage.storage_backends import HetznerPublicStorage

public_storage = HetznerPublicStorage()

logger = logging.getLogger("django")
# User = get_user_model() .  # don't do this - ends up with circular import


# ---------------------------------------------------------------------
# Helpers / Settings
# ---------------------------------------------------------------------

NEWSLETTER_BASENAME = getattr(settings, "NEWSLETTER_BASENAME", "")


def _abs_url(url: str, base_url: str) -> str:
    if not url:
        return ""
    # if already absolute, leave it
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))


def get_mail_class():
    """
    Load the configured mail class from settings.APP_MAIL_CLASS.
    Defaults to django.core.mail if not set.
    """
    dotted = getattr(settings, "EMAIL_WRAPPER", "django.core.mail")
    return import_string(dotted)


#
# def send_single_email(*, to_email, subject, text=None, html=None, recipient_vars=None):
#     """
#     Send a single email via Mailgun API.
#     """
#     url = f"{MAILGUN_BASE_URL}/messages"
#     data = {
#         "from": settings.DEFAULT_FROM_EMAIL,
#         "to": [to_email],
#         "subject": subject,
#     }
#     if text:
#         data["text"] = text
#     if html:
#         data["html"] = html
#     if recipient_vars:
#         data["recipient-variables"] = json.dumps(recipient_vars)
#
#
#     url = f"{MAILGUN_API_URL}/{MAILGUN_SENDER_DOMAIN}/messages"
#     auth = ("api", MAILGUN_API_KEY)
#
#
#     response = requests.post(url, auth=auth, data=data)
#     response.raise_for_status()
#     mailgun_id = (response.json() or {}).get("id")
#
#     Delivery.objects.create(dsubmission=self, email=addr, mailgun_id=mailgun_id, status="sent")
#
#     return response.json()

def get_address(name: str | None, email: str) -> str:
    return f"{name} <{email}>" if name else email


def attachment_upload_to(instance, filename):
    # HETZNER_AWS_S3_FILE_OVERWRITE is True so ensure the same filename in different attachments is unique
    return os.path.join(
        "newsletter", "attachments",
        datetime.utcnow().strftime("%Y-%m-%d"),
        f"article-{instance.article_id or 'new'}",
        filename,
    )


def article_upload_to(instance, filename):
    # HETZNER_AWS_S3_FILE_OVERWRITE is True so ensure the same filename in different articles is unique
    return os.path.join(
        "newsletter", "attachments",
        datetime.utcnow().strftime("%Y-%m-%d"),
        f"article-{instance.article_id or 'new'}",
        filename,
    )


# ---------------------------------------------------------------------
# Newsletter
# ---------------------------------------------------------------------
class NewsletterQuerySet(models.QuerySet):

    def visible(self):
        return self.filter(visible=True)

    def active(self):
        return self.filter(visible=True)

    def public(self):
        return self.filter(public=True, visible=True)


class Newsletter(EventMixin, CreatedUpdatedMixin, models.Model):
    site = models.ManyToManyField(Site, blank=True)

    title = models.CharField(max_length=200, verbose_name=_("newsletter title"))
    slug = models.SlugField(db_index=True, unique=True)
    about = models.TextField(blank=True, null=True, help_text=_("Short description shown on subscribe page"))
    email = models.EmailField(verbose_name=_("e-mail"), help_text=_("Sender e-mail"))
    sender = models.CharField(max_length=200, verbose_name=_("sender"), help_text=_("Sender name"))
    reply_to = models.EmailField(blank=True, null=True, verbose_name=_("reply to e-mail"))

    visible = models.BooleanField(default=True, db_index=True, help_text=_(
        "Should be named active.  Can be active and not public for team use only."))
    public = models.BooleanField(default=True, help_text=_("Appears in list that users can subscribe to."),
                                 db_index=True)
    send_html = models.BooleanField(
        default=True, verbose_name=_("send html"),
        help_text=_("Whether or not to send HTML versions of e-mails."),
    )
    objects = NewsletterQuerySet.as_manager()

    class Meta:
        verbose_name = _("newsletter")
        verbose_name_plural = _("newsletters")
        ordering = ["title"]

    def __str__(self):
        return self.title

    # ----- URLs in your site (optional) -----
    @property
    def base_url(self):
        # in future might want to customise
        return settings.SITE_URL

    def get_absolute_url(self):
        return reverse(f"skorie_news:newsletter-edit", kwargs={"pk": self.id})
        # return reverse(f"news:newsletter_detail", kwargs={"newsletter_slug": self.slug})

    def subscribe_url(self):
        return reverse(f"newsapi:subscribe_from_request", kwargs={"newsletter_slug": self.slug})

    def unsubscribe_url(self):
        return reverse(f"newsapi:unsubscribe_from_request", kwargs={"newsletter_slug": self.slug})

    def archive_url(self):
        return reverse(f"skorie_news:newsletter_archive", kwargs={"newsletter_slug": self.slug})

    @classmethod
    def is_subscribed_to_newsletter(cls, user, newsletter=None):
        '''check if a user is currently subscribed to a newsletter'''
        if not newsletter:
            newsletter = cls.objects.get(slug=settings.NEWSLETTER_GENERAL_SLUG)
        # TODO: this should be a search on user not email - potential for confusion
        sub = Subscription.get_subscription(email=user.email, newsletter=newsletter)
        return sub.subscribed if sub else False

    def subscribe_me(self, request):
        # use this to subscribed the authenticated user
        return Subscription.subscribe_me(self, request)

    def unsubscribe_me(self, request):
        # use this to subscribed the authenticated user
        return Subscription.unsubscribe_me(self, request)

    def subscribe_from_request(self, request):
        '''subscribe the user in the request to the current newsletter'''
        return Subscription.subscribe_from_request(self, request)

    def unsubscribe_from_request(self, request):
        '''subscribe the user in the request to the current newsletter'''
        return Subscription.unsubscribe_from_request(self, request)

    def subscribe_from_email(self, email, request):
        '''subscribe the user in the request to the current newsletter'''
        return Subscription.subscribe_from_request(self, request)

    # ----- From header helper -----
    @property
    def get_sender(self) -> str:
        return get_address(self.sender, self.email)

    # ----- Template selection (subject/text/html) -----
    def get_templates(self, action: str):
        """
        Return a tuple: (subject_template, text_template, html_template or None)
        Looks under:
            skorie_news/message/<slug>/<action>_subject.txt
            skorie_news/message/<action>_subject.txt
        and similarly for .txt and .html
        """
        assert action in ("mailing", "subscribe", "update", "unsubscribe"), f"Unknown action: {action}"

        tpl_root = "skorie_news/mailings/"
        subs = {"newsletter": self.slug, "action": action}

        subject_template = select_template([
            f"{tpl_root}{subs['newsletter']}/{subs['action']}_subject.txt",
            f"{tpl_root}{subs['action']}_subject.txt",
        ])
        text_template = select_template([
            f"{tpl_root}{subs['newsletter']}/{subs['action']}.txt",
            f"{tpl_root}{subs['action']}.txt",
        ])
        html_template = None
        if self.send_html:
            html_template = select_template([
                f"{tpl_root}{subs['newsletter']}/{subs['action']}.html",
                f"{tpl_root}{subs['action']}.html",
            ])
        return subject_template, text_template, html_template

    # ----- Stats -----
    def sent_since(self, dt):
        # "created" proxy; you can track sent count via Delivery if you prefer
        return Issue.objects.filter(newsletter=self, created__gte=dt).count()

    # ----- Subscription helpers -----
    def get_subscriptions(self):
        return Subscription.objects.active().filter(newsletter=self)

    @classmethod
    def get_default(cls):
        obj = cls.objects.order_by("pk").first()
        return obj.pk if obj else None


# ---------------------------------------------------------------------
# Subscription (user-or-email)
# ---------------------------------------------------------------------

class SubscriptionEvent(models.Model):
    class Event(models.TextChoices):
        SUBSCRIBE = "subscribe", "Subscribe"
        UNSUBSCRIBE = "unsubscribe", "Unsubscribe"
        CONSENT = "consent", "Consent"
        SUB_AND_CONSENT = "subscribe_consent", "Subscribe and Consent"  # used where a user is logged in and requests subscribe/unsubscribe
        # UNSUB_AND_CONSENT = "unsubscribe_consent", "Subscribe and Consent"    # used where a user is logged in and requests subscribe/unsubscribe
        UPDATE_PREFS = "update_prefs", "Update Preferences"
        BOUNCE = "bounce", "Bounce"
        COMPLAINT = "complaint", "Complaint"
        ERASE = "erase", "Erase (GDPR)"
        EMAIL_SENT = "email_sent", "Email Sent"

    subscription = models.ForeignKey("Subscription", on_delete=models.CASCADE, related_name="events")
    event = models.CharField(max_length=32, choices=Event.choices)
    at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"{self.subscription_id} {self.event} @ {self.at:%Y-%m-%d %H:%M}"

    @classmethod
    def log(cls, sub: "Subscription", event: "SubscriptionEvent.Event", **kwargs):
        cls.objects.create(subscription=sub, event=event, **kwargs)


def generate_activation_code():
    return secrets.token_urlsafe(24)[:40]  # 24 bytes → ~32 chars, slice to 40 max


class SubscriptionQuerySet(models.QuerySet):
    def active(self):
        # Now trust the computed flag.
        return self.filter(active=True)

    def pending(self):
        # Created/intent but not confirmed by consent; not unsubscribed.
        return self.filter(active=False, unsubscribed=False)

    def unsubscribed(self):
        return self.filter(unsubscribed=True)

    def inactive(self):
        # includes bounced, complained, gdpr_erased
        return self.filter(active=False)

    def suppressed(self):
        return self.filter(
            Q(bounced=True) | Q(complained=True) | Q(active=False) | Q(gdpr_erased_at__isnull=False)
        )

    def subscribed(self):
        return self.filter(active=True, unsubscribed=False)

    def active(self):
        # includes not bounced, complained, gdpr_erased
        return self.filter(active=True)


class Subscription(CreatedUpdatedMixin):
    class LawfulBasis(models.TextChoices):
        CONSENT = "consent", "Consent"
        CONTRACT = "contract", "Contract"
        LEGITIMATE_INTEREST = "legit_interest", "Legitimate Interest"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.CASCADE)
    name = models.CharField(db_column="name", max_length=200, blank=True, null=True, verbose_name=_("name"))
    email = models.EmailField(db_column="email", db_index=True, blank=True, null=True, verbose_name=_("e-mail"))

    ip = models.GenericIPAddressField(_("IP address"), blank=True, null=True)
    newsletter = models.ForeignKey(Newsletter, on_delete=models.CASCADE, related_name="subscriptions")

    # Consent & GDPR
    lawful_basis = models.CharField(max_length=32, choices=LawfulBasis.choices, default=LawfulBasis.CONSENT)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_source = models.CharField(max_length=255, blank=True, help_text="e.g. form path or campaign")
    consent_user_agent = models.TextField(blank=True)
    consent_text = models.TextField(blank=True, help_text="Snapshot of the consent wording shown to user")
    gdpr_erased_at = models.DateTimeField(null=True, blank=True)

    # Channel preferences (expand later if you add SMS/WhatsApp)
    email_opt_in = models.BooleanField(default=True)  # delete

    # Subscription state
    active = models.BooleanField(
        default=False, db_index=True,
        help_text="True when consent is present and the subscription is deliverable."
    )

    subscribed = models.BooleanField(default=False, db_index=True)
    subscribe_date = models.DateTimeField(null=True, blank=True)
    unsubscribed = models.BooleanField(default=False, db_index=True)
    unsubscribe_date = models.DateTimeField(null=True, blank=True)

    # Suppression flags
    bounced = models.BooleanField(default=False)
    bounced_at = models.DateTimeField(null=True, blank=True)
    bounce_reason = models.TextField(blank=True)
    complained = models.BooleanField(default=False)
    complained_at = models.DateTimeField(null=True, blank=True)
    complaint_reason = models.TextField(blank=True)

    # TODO: convert to UUID
    activation_code = models.CharField(max_length=40, default=generate_activation_code, unique=True)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")
        ordering = ["-created", ]
        constraints = [

            # models.UniqueConstraint(
            #     fields=["newsletter", "email"],
            #     name="uniq_newsletter_email",
            #     condition=models.Q(email__isnull=False),
            # ),
            models.UniqueConstraint(
                fields=["newsletter", "email"],
                name="uniq_newsletter_email",
                condition=models.Q(email__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.name or self.email} → {self.newsletter}"

    def save(self, *args, **kwargs):

        if not self.email and self.user:
            self.email = self.user.email.strip().lower()
        elif self.email:
            self.email = self.email.strip().lower()

        self._recompute_active()

        super().save(*args, **kwargs)

    def _recompute_active(self) -> bool:
        """Compute deliverability according to your current rules."""

        self.active = bool(
            self.subscribed and
            not self.unsubscribed and
            self.consent_at is not None and
            not self.bounced and
            not self.complained and
            self.gdpr_erased_at is None
        )
        return self.active

    @classmethod
    def get_subscription(cls, newsletter, email) -> Optional["Subscription"]:
        '''currently have some duplciates so using filter but need to be able to do get'''
        qs = cls.objects.filter(newsletter=newsletter, email=email)
        sub = qs.first()
        if qs.count() > 1:
            logger.warning(
                f"Multiple subscriptions found for {email} and newsletter {newsletter.pk} - using pk {sub.pk}")
        return sub

    @classmethod
    def consent_from_request(cls, request):
        '''extract consent details from the request'''

        return {
            "source": request.META.get('HTTP_REFERER', ''),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:1024],
            "ip_address": request.META.get("REMOTE_ADDR", ""),
            "consent_text": request.data.get("consent_text", "")
        }

    @classmethod
    def subscribe_me(cls, newsletter: "Newsletter", request) -> "Subscription":
        # use this to subscribed the authenticated user

        if not request.user.is_authenticated:
            raise PermissionDenied("You must be logged in to subscribe.")

        me = request.user

        # check for existing subscription
        sub = cls.get_subscription(newsletter=newsletter, email=me.email)

        if not sub:
            sub = cls(user=me, newsletter=newsletter)
            consent = cls.consent_from_request(request)
            sub.subscribe(consent, send_email=False)
        else:
            if sub.active:
                # already subscribed - nothing to do
                return sub

            elif sub.unsubscribed:
                # resubscribe

                sub._subscribe()  # subscribed=True, unsubscribed=False, dates updated
                # Clear any previous consent so it stays pending until new consent is obtained
                sub.consent_at = None
                sub.consent_source = ""
                sub.consent_user_agent = ""
                sub.consent_text = ""
                sub.save(user=me)

            consent = cls.consent_from_request(request)
            sub.record_consent(**consent, send_email=False)

        return sub

    @classmethod
    def unsubscribe_me(cls, newsletter: "Newsletter", request) -> "Subscription":
        # use this to subscribed the authenticated user

        if not request.user.is_authenticated:
            raise PermissionDenied("You must be logged in to subscribe.")

        me = request.user

        sub = cls.get_subscription(email=me.email, newsletter=newsletter)

        if not sub:
            raise ValidationError("No subscription found for this user and newsletter.")

        consent = cls.consent_from_request(request)
        sub.unsubscribe(consent, me, send_email=False)
        return sub

    @classmethod
    def subscribe_from_request(cls, newsletter: "Newsletter", request) -> "Subscription":
        """
        # use this for subscribing where info about subscriber is in the payload of the request
        Subscribe (or re-subscribe) an email to a newsletter based on the incoming request.
           #TODO: block logged in user from subscribing with different email
        Rules:
        - Guest (not logged in): create/leave as PENDING until consent is recorded (confirmation click).
        - Logged in: record consent immediately (active).
        - Previously unsubscribed: treat as re-subscribe.
          * Guest → pending (no consent yet).
          * Logged in → pending then consent → active.
        - Already subscribed:
          * If pending and user is logged in → record consent now.
          * Else no-op (idempotent).
        """
        User = get_user_model()
        data = getattr(request, "data", None) or getattr(request, "POST", {})
        email = (data.get("email") or "").strip().lower()
        name = (data.get("name") or "").strip()
        try:
            user = User.objects.get(email=email)  # we are not currently checking for status of user - does it matter?
        except User.DoesNotExist:
            user = None
        logged_in = request.user.is_authenticated

        # validation
        if not email:
            raise ValidationError("Email is required")

        if logged_in and request.user.email != email:
            raise ValidationError("Can't add subscription for someone else")

        # check for existing subscription
        sub = cls.get_subscription(newsletter=newsletter, email=email)

        if not sub:
            if not user:
                # create and require consent
                sub = cls(email=email, name=name, newsletter=newsletter)
                sub.subscribe()
            elif user and not logged_in:
                # create and require consent because user is not logged in
                sub = cls(user=user, newsletter=newsletter)
                sub.subscribe()
            elif user and logged_in:
                sub = cls(user=user, newsletter=newsletter)
                consent = cls.consent_from_request(request)
                sub.subscribe(consent)
        else:
            if sub.active:
                # already subscribed - nothing to do
                return sub

            elif sub.unsubscribed:
                # resubscribe

                sub._subscribe()  # subscribed=True, unsubscribed=False, dates updated
                # Clear any previous consent so it stays pending until new consent is obtained
                sub.consent_at = None
                sub.consent_source = ""
                sub.consent_user_agent = ""
                sub.consent_text = ""
                sub.save(user=request.user if logged_in else None)

                if logged_in:
                    # Logged-in re-subscribe → record consent now (activate)
                    consent = cls.consent_from_request(request)
                    sub.record_consent(**consent)
                else:
                    SubscriptionEvent.log(sub, SubscriptionEvent.Event.SUBSCRIBE)

                # Guest: leave pending; confirmation email should be (re)sent elsewhere
                return sub

            # Already subscribed but waiting consent
            if sub.is_pending:
                consent = cls.consent_from_request(request)
                # If pending and user is logged in, confirm now
                if logged_in and consent:
                    sub.record_consent(**consent)
                elif not logged_in:
                    # resend email
                    sub.subscribe()

        return sub

    @classmethod
    def admin_subscribe(cls, newsletter, email, name, subscriber_user, consent={}, user=None):
        '''used by system users to subscribe/unsubscribe when setting up system'''

        # check for existing subscription
        sub = cls.get_subscription(newsletter=newsletter, email=email)

        if not sub:
            if not subscriber_user:
                # create and require consent
                sub = cls(email=email, name=name, newsletter=newsletter)
                sub._subscribe()
            elif subscriber_user and not consent:
                # create and require consent because user is not logged in
                sub = cls(user=subscriber_user, newsletter=newsletter)
                sub._subscribe()
            elif subscriber_user and consent:
                sub = cls(user=subscriber_user, newsletter=newsletter)
                sub._subscribe()
            sub.record_consent(SubscriptionEvent.Event.SUB_AND_CONSENT, send_email=False, **consent)
        else:
            if sub.active and sub.subscribed:
                # already subscribed - nothing to do
                return sub
            else:
                sub._subscribe()
                sub.record_consent(SubscriptionEvent.Event.SUB_AND_CONSENT, send_email=False, **consent)
        sub.save()

        return sub

    @classmethod
    def admin_unsubscribe(cls, newsletter, email, name, subscriber_user, consent=None, user=None):
        '''used by system users to subscribe/unsubscribe when setting up system'''

        # check for existing subscription
        sub = cls.get_subscription(newsletter=newsletter, email=email)

        if not sub:
            if not subscriber_user:
                # create and require consent
                sub = cls(email=email, name=name, newsletter=newsletter)
            elif subscriber_user:
                # create and require consent because user is not logged in
                sub = cls(user=subscriber_user, newsletter=newsletter)

            if sub:
                sub._unsubscribe()
        else:
            if not sub.active:
                # already subscribed - nothing to do
                return sub

            elif sub.subscribed:

                sub._unsubscribe()

        sub.save()

        return sub

    @classmethod
    def unsubscribe_from_request(cls, newsletter, request):
        """
        Unsubscribe by email (guest or logged-in). No consent required.
        If no row exists, create a suppression row (unsubscribed=True).
        """
        user = request.user if request.user.is_authenticated else None
        if user:
            email = user.email
        else:
            data = getattr(request, "data", None) or getattr(request, "POST", {})
            email = (data.get("email") or "").strip().lower()
            if not email:
                raise ValidationError("Email is required.")

        sub = cls.get_subscription(email=email, newsletter=newsletter)

        if not sub:
            raise ValidationError("No subscription found for this user and newsletter.")

        consent = cls.consent_from_request(request)
        sub.unsubscribe(consent, user)
        return sub

    @property
    def is_pending(self):
        '''subscription is unconfirmed'''
        return self.subscribed and not self.active

    @property
    def is_erased(self):
        return self.gdpr_erased_at is not None

    @property
    def subscribe_confirm_url(self):
        """
        Secure unsubscribe link using activation_code
        """

        path = reverse("news:confirm-subscribe", args=[self.pk, self.activation_code])
        return f"{settings.SITE_URL}{path}"

    @property
    def unsubscribe_url(self):
        """
        Secure unsubscribe link using activation_code
        """

        path = reverse("news:unsubscribe-now", args=[self.pk, self.activation_code])
        return f"{settings.SITE_URL}{path}"

    @property
    def subscribe_url(self):
        """
        Secure subscribe link using activation_code
        """
        # link will subscribe and confirm
        path = reverse("news:confirm-subscribe", args=[self.pk, self.activation_code])
        return f"{settings.SITE_URL}{path}"

    @classmethod
    def link_subscriptions_to_user(cls, user) -> int:
        """
        Attach any subscriptions for the user's email to this user.
        Creates a SubscriptionEvent(kind='linked_user') for each link.
        Returns the number of subscriptions linked.
        """

        # Lock matching subs that are not yet linked to *any* user
        subs = (Subscription.objects
                .select_for_update()
                .filter(user__isnull=True, email__iexact=user.email))

        count = 0
        for sub in subs:
            sub.user = user
            sub.save()
            SubscriptionEvent.log(sub, SubscriptionEvent.Event.UPDATE_PREFS)

            count += 1

        return count

    # ---- state helpers ----
    def _subscribe(self):
        '''use for initial subscription or re-subscribe '''
        self.subscribed = True
        self.unsubscribed = False
        self.subscribe_date = timezone.now()
        self.unsubscribe_date = None
        self.consent_at = None
        self.consent_source = ""
        self.consent_user_agent = ""
        self.consent_text = ""

    def _unsubscribe(self):
        self.subscribed = False
        self.unsubscribed = True
        self.unsubscribe_date = timezone.now()

        # clear consent in case user resubscribes
        self.consent_at = None
        self.consent_source = ""
        self.consent_user_agent = ""
        self.consent_text = ""

    def subscribe(self, consent: dict = {}, user=None, send_email=True):

        already_active = self.active
        sub_event = SubscriptionEvent.Event.SUBSCRIBE
        self._subscribe()
        if consent:
            self.record_consent(SubscriptionEvent.Event.SUB_AND_CONSENT, send_email=False,
                                **consent)  # will add to SubscriptionEvent in here

        self.save(user=user)

        if not consent:
            # can't add this until sub is sved
            SubscriptionEvent.log(self, sub_event)

        # do we need an email?
        if not already_active and not consent:
            self._send_tx_email("request_consent")
        elif not already_active and self.active and send_email:
            self._send_tx_email("subscribed")

        if self.active and self.user and hasattr(self.user, 'subscribe_news'):
            self.user.subscribe_news = self.subscribe_date
            self.user.unsubscribe_news = self.unsubscribe_date
            self.user.save()

    def unsubscribe(self, consent: dict = {}, user=None, send_email=True):
        '''not really consent as we do not require it for unsubscribe, but we can log some metadata'''

        was_unsubscribed = self.unsubscribed  # detect transition

        self._unsubscribe()
        sub_event = SubscriptionEvent.Event.UNSUBSCRIBE

        # If you want to capture metadata about the request, log it in the event meta,
        # but DO NOT call record_consent() here (consent is for subscribe).
        meta = {}
        if consent:
            meta = {
                "source": consent.get("source", ""),
                "ip": consent.get("ip_address", ""),
                "user_agent": consent.get("user_agent", ""),
                "consent_text": consent.get("consent_text", ""),
            }

        self.save(user=user)
        SubscriptionEvent.log(self, sub_event, meta=meta)

        # Send a confirmation email only when we actually transitioned to unsubscribed
        if not was_unsubscribed and self.unsubscribed and send_email:
            self._send_tx_email("unsubscribed")

    def record_consent(self, event=SubscriptionEvent.Event.CONSENT,
                       source: str = "",
                       user_agent: str = "",
                       consent_text: str = "",
                       ip_address: str = "",
                       send_email=True):

        was_active = getattr(self, "active", False)  # capture pre-state

        self.consent_at = timezone.now()
        self.consent_source = source[:255]
        self.consent_user_agent = user_agent
        self.consent_text = consent_text
        self.lawful_basis = self.LawfulBasis.CONSENT
        self.ip = ip_address
        self.save()  # refresh active

        SubscriptionEvent.log(self, event, meta={'source': source, 'ip': ip_address, 'user_agent': user_agent})

        # # If this consent made us become active now (fresh after any unsubscribe), send confirmation
        if send_email and not was_active and self.active:
            self._send_tx_email("subscribed")

    def mark_bounce(self, reason: str = ""):
        self.bounced = True
        self.bounced_at = timezone.now()
        self.bounce_reason = reason

        self.save()
        SubscriptionEvent.log(self, SubscriptionEvent.Event.BOUNCE, meta={"reason": reason})

    def mark_complaint(self, reason: str = ""):
        self.complained = True
        self.complained_at = timezone.now()
        self.complaint_reason = reason

        self.save()
        SubscriptionEvent.log(self, SubscriptionEvent.Event.COMPLAINT, meta={"reason": reason})

    def request_erasure(self, user=None):
        """GDPR erase/anonymize as much as possible while keeping minimal audit."""
        # keep a hashed marker if you want dedupe; here we just null-out
        self.name = None
        if self.email:
            # create anon email to keep uniqueness intact
            self.email = f"erased-{self.pk}-{int(timezone.now().timestamp())}@example.com"

        self.unsubscribe(user=user)
        self.gdpr_erased_at = timezone.now()
        self.save()
        SubscriptionEvent.log(self, SubscriptionEvent.Event.ERASE)

    # --- helper: render and send a single transactional email (subscribe/unsubscribe) ---
    def _send_tx_email(self, action: str) -> None:
        """
        action: 'subscribe' or 'unsubscribe'
        Uses Newsletter.get_templates(action) to render.
        """

        # hard code for now
        if action == "request_consent":
            subject = f"Please confirm your subscription to {self.newsletter.title}"
            text = f"Please confirm your subscription to {self.newsletter.title} by clicking the link below:\n\n{self.subscribe_confirm_url}\n\nIf you did not request this, please ignore this email."

        elif action == "subscribed":
            subject = f"You are now subscribed to {self.newsletter.title}"
            text = f"You are now subscribed to {self.newsletter.title}.\n\nIf you did not request this, please ignore this email or click the link below to unsubscribe:\n\n{self.unsubscribe_url}\n"

        elif action == "unsubscribed":
            subject = f"You are now unsubscribed from {self.newsletter.title}"
            text = f"You are now unsubscribed from {self.newsletter.title}.\n\nIf you did not request this, If you want to resubscribe, follow this link:\n\n{self.subscribe_url}\n"

        else:
            raise NotImplementedError(f"action {action} is not implemented _send_tx_email")

        result = DirectEmail.send_simple_email(subject, text, user=self.user, to_email=self.email)
        result_pk = result.pk if result else None
        SubscriptionEvent.log(self, SubscriptionEvent.Event.EMAIL_SENT,
                              meta={'email_action': action, 'result': result_pk})


# ---------------------------------------------------------------------
# Article (+ Attachment on Article)
# ---------------------------------------------------------------------

class Article(CreatedUpdatedMixin):

    def image_location(instance, filename):
        return f"newsletter/article/images/{filename}"

    TEMPLATE_TYPE_NEWSLETTER = "N"
    TEMPLATE_TYPE_EMAIL = "E"
    TEMPLATE_TYPE_CHOICES = (
        (TEMPLATE_TYPE_NEWSLETTER, "Newsletter"),
        (TEMPLATE_TYPE_EMAIL, "Email"),
    )

    ABOVE = "above";
    BELOW = "below";
    LEFT = "left";
    RIGHT = "right"
    IMAGE_POSITION_CHOICES = [(ABOVE, "Above text"), (BELOW, "Below text"), (LEFT, "Left of text"),
                              (RIGHT, "Right of text")]

    template_type = models.CharField(
        max_length=1, choices=TEMPLATE_TYPE_CHOICES, default=TEMPLATE_TYPE_NEWSLETTER
    )

    title = models.CharField(max_length=200)
    body_html = models.TextField(blank=True)
    body_text = models.TextField(blank=True)
    url = models.URLField(blank=True, null=True)

    image = models.ImageField(upload_to=image_location, storage=public_storage, blank=True, null=True)
    image_position = models.CharField(max_length=10, choices=IMAGE_POSITION_CHOICES, default=ABOVE)

    is_template = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("article")
        verbose_name_plural = _("articles")
        ordering = ["-created"]

    def __str__(self):
        return self.title

    def render_html(
            self,
            *,
            base_url: str | None = None,
            include_attachments: bool = True,
            include_title: bool = True,
    ) -> str:
        """
        Return an HTML string for this article (image positioned + body_html + attachments list).
        Uses inline styles suitable for email clients.
        """
        base_url = (base_url or getattr(settings, "SITE_URL", "")).rstrip("/")
        pieces: list[str] = []

        # Optional title
        if include_title and self.title:
            pieces.append(f'<h2 style="margin:0 0 12px 0;font-family:inherit;">{self.title}</h2>')

        # Prepare image HTML (absolute URL + inline style)
        img_html = ""
        if self.image:
            img_url = _abs_url(getattr(self.image, "url", ""), base_url)
            if self.image_position == "above":
                img_html = f'<p style="margin:0 0 12px 0;"><img src="{img_url}" alt="" style="max-width:100%;height:auto;border:0;"></p>'
            elif self.image_position == "below":
                # inject later, after body
                pass
            elif self.image_position == "left":
                img_html = (
                    f'<img src="{img_url}" alt="" '
                    f'style="max-width:40%;height:auto;border:0;float:left;'
                    f'margin:0 12px 12px 0;">'
                )
            elif self.image_position == "right":
                img_html = (
                    f'<img src="{img_url}" alt="" '
                    f'style="max-width:40%;height:auto;border:0;float:right;'
                    f'margin:0 0 12px 12px;">'
                )

        # Image before body for above/left/right
        if img_html and self.image_position in {"above", "left", "right"}:
            pieces.append(img_html)

        # Body HTML (as-is; assume it’s clean)
        if self.body_html:
            pieces.append(f'<div style="font-family:inherit;line-height:1.5;">{self.body_html}</div>')

        # Image after body for below
        if self.image and self.image_position == "below":
            img_url = _abs_url(getattr(self.image, "url", ""), base_url)
            pieces.append(
                f'<p style="margin:12px 0 0 0;"><img src="{img_url}" alt="" style="max-width:100%;height:auto;border:0;"></p>')

        # Clear floats for left/right layouts
        if self.image_position in {"left", "right"}:
            pieces.append('<div style="clear:both;"></div>')

        # Optional attachments
        if include_attachments:
            atts = list(self.attachments.all())
            if atts:
                pieces.append('<hr style="border:none;border-top:1px solid #ddd;margin:16px 0;">')
                pieces.append('<div style="font-size:90%;">Attachments:</div>')
                pieces.append('<ul style="margin:8px 0 0 18px;padding:0;">')
                for a in atts:
                    url = _abs_url(getattr(a.file, "url", ""), base_url)
                    name = a.name or a.file.name
                    pieces.append(
                        f'<li style="margin:0 0 6px 0;"><a href="{url}" '
                        f'style="color:#0d6efd;text-decoration:underline;">{name}</a></li>'
                    )
                pieces.append('</ul>')

        return "".join(pieces)

    def render_text(
            self,
            *,
            base_url: str | None = None,
            include_attachments: bool = True,
            include_title: bool = True,
    ) -> str:
        """
        Return a plain-text version of this article (good for text part of emails).
        """
        base_url = (base_url or getattr(settings, "SITE_URL", "")).rstrip("/")
        lines: list[str] = []

        if include_title and self.title:
            lines.append(self.title)
            lines.append("")

        # Image note
        if self.image:
            img_url = _abs_url(getattr(self.image, "url", ""), base_url)
            lines.append(f"[Image: {img_url}]")
            lines.append("")

        # Body text: strip tags
        if self.body_html:
            body_text = strip_tags(self.body_html)
            # Normalize whitespace a bit
            body_text = "\n".join([ln.rstrip() for ln in body_text.splitlines()]).strip()
            lines.append(body_text)
            lines.append("")

        # Optional link
        if self.url:
            lines.append(f"More: {_abs_url(self.url, base_url)}")
            lines.append("")

        # Attachments
        if include_attachments:
            atts = list(self.attachments.all())
            if atts:
                lines.append("Attachments:")
                for a in atts:
                    url = _abs_url(getattr(a.file, "url", ""), base_url)
                    name = a.name or a.file.name
                    lines.append(f" - {name}: {url}")
                lines.append("")

        return "\n".join(lines).rstrip()


class Attachment(CreatedUpdatedMixin):
    name = models.CharField(max_length=60, null=True, blank=True, help_text=_("Optional name/description"))
    file = models.FileField(upload_to=attachment_upload_to, storage=public_storage, verbose_name=_("attachment"))
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="attachments")

    class Meta:
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")

    def __str__(self):
        return self.name or self.file_name

    @property
    def file_name(self):
        return os.path.split(self.file.name)[1]


# ---------------------------------------------------------------------
# Message (Issue) + IssueArticle (ordering + appear_in_blog)
# ---------------------------------------------------------------------

class Issue(CreatedUpdatedMixin):
    # == Issue
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    newsletter = models.ForeignKey(Newsletter, on_delete=models.CASCADE, related_name="issues")

    published_at = models.DateTimeField(null=True, blank=True)  # when published to blog

    # Articles through join for order + appear_in_blog
    articles = models.ManyToManyField(Article, through="IssueArticle", related_name="issues")

    class Meta:
        verbose_name = _("message")
        verbose_name_plural = _("messages")
        unique_together = ("slug", "newsletter")
        ordering = ["-created"]

    def __str__(self):
        return f"{self.title} in {self.newsletter}"

    def save(self, *args, **kwargs):
        if not self.slug and self.title:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def ordered_articles(self):
        return self.issue_articles.select_related("article").order_by("position", "id")

    @property
    def is_blog_published(self):  # simple helper
        return self.published_at is not None

    @property
    def active_mailing(self):
        """Return queued/sending mailing if present (or None)."""
        # If you haven't renamed Submission -> Mailing yet, use Submission.Status.*
        qs = self.mailings.filter(
            status__in=[Mailing.Status.QUEUED, Mailing.Status.SENDING]
        ).order_by("-created")
        if qs.count() > 1:
            logger.warning("Message %s has more than one active mailing", self.pk)
        return qs.first()

    @property
    def can_queue_mailing(self) -> bool:
        """
        Business rule: allow queue if there is no active mailing.
        You can tighten this later (e.g. only if not SENT, etc.).
        """
        active = self.mailings.filter(
            status__in=[Mailing.Status.QUEUED, Mailing.Status.SENDING]
        ).exists()
        return not active

    @classmethod
    def send_due(cls, max_per_run: int | None = None) -> int:
        """
        Find all QUEUED mailings whose publish_date is due and send them.

        Returns the number of mailings that were *attempted* (i.e. we called
        send_via_anymail on them), not the number of individual recipient emails.
        """
        now = timezone.now()

        qs = cls.objects.filter(
            status=cls.Status.QUEUED,
            publish_date__lte=now,
        ).order_by("publish_date", "pk")

        if max_per_run is not None:
            qs = qs[:max_per_run]

        processed = 0

        for mailing in qs:
            # Optional safety: skip obviously unprepared mailings
            if not mailing.prepared:
                logger.warning(f"Mailing {mailing.pk} is not prepared; marking as ERROR.")
                mailing.status = cls.Status.ERROR
                mailing.save(update_fields=["status", "updated"])
                continue

            try:
                mailing.send_via_anymail()
                processed += 1
            except Exception:
                # send_via_anymail itself sets status to SENT or ERROR
                logger.exception(f"Error sending mailing {mailing.pk}")
                # don’t re-raise here, so we continue to other mailings

        return processed

    def schedule_mailing(self, publish_date=None, subscriptions=None, publish=True) -> "Mailing":
        """
        Create (but don't necessarily queue) a Mailing for this Issue.
        Does all data-changing work here, not in the view.
        """
        if publish_date is None:
            publish_date = timezone.now()

        mailing = Mailing(
            issue=self,
            newsletter=self.newsletter,
            publish_date=publish_date,
            publish=publish,
            status=Mailing.Status.INACTIVE,
        )
        mailing.save()

        # default recipients = all active subscribers, unless explicit subset provided
        if subscriptions is None:
            subscriptions = self.newsletter.get_subscriptions()
        mailing.subscriptions.set(subscriptions)

        return mailing

    def queue_mailing(self, publish_date=None, subscriptions=None, publish=True) -> "Mailing":
        """
        High-level operation: create + queue a mailing.
        This is what the view should call.
        """
        if not self.can_queue_mailing:
            # you can raise or just return existing latest; I’d raise and handle in the view
            raise ValueError("Issue already has an active mailing queued or sending.")

        mailing = self.schedule_mailing(
            publish_date=publish_date,
            subscriptions=subscriptions,
            publish=publish,
        )
        mailing.queue()  # uses Mailing.queue()
        return mailing

    def publish_to_blog(self):
        if not self.published_at:
            self.published_at = timezone.now()
            self.save(update_fields=["published_at"])

    def send_one(self, email_addr):
        '''this has a lot of duplicated code form Mailing.send_via_anymail - should dry'''

        # Ordered list of issue articles for this issue
        articles = (
            self.issue_articles
            .select_related("article")
            .order_by("position")
        )

        ctx = {
            "subscription": None,
            "site": Site.objects.get_current(),
            "mailing": None,
            "date": timezone.now(),
            "STATIC_URL": settings.STATIC_URL,
            "MEDIA_URL": settings.MEDIA_URL,
            'unsubscribe_url': self.newsletter.unsubscribe_url,
        }

        email = self.render_email(extra_context=ctx)
        '''email = {
            "subject": subject,
            "text": text,
            "html": html,
            "files": files,
        }'''

        merge_data = {email_addr: {
            "name": "Test Name",
            "unsubscribe_url": "",
            "subscription_id": 0,
        }
        }
        try:
            # get domain from reply to email
            domain = self.newsletter.reply_to.split('@')[-1]
            msg = AnymailMessage(
                subject=email['subject'],
                body=email['text'],
                from_email=self.newsletter.get_sender,
                to=[email_addr, ],
                reply_to=[self.newsletter.reply_to,],
                tags=["newsletter", "general"],
                headers={
                    "X-List-ID": f"{domain}-{self.newsletter.slug}",
                    "X-Feedback-ID": f"{domain}-{self.newsletter.slug}:issue-{self.pk}",
                })
            if 'html' in email and email['html']:
                msg.attach_alternative(email['html'], "text/html")

            # Attachments on the Issue
            for _kind, (filename, fileobj) in email['files']:
                try:
                    fileobj.open("rb")
                except Exception:
                    pass
                msg.attach(filename, fileobj.read())

            # Provider-agnostic knobs
            msg.tags = [NEWSLETTER_BASENAME or "newsletter", self.newsletter.slug]
            msg.metadata = {"mailing_id": str(self.pk), "newsletter_id": str(self.newsletter_id)}
            msg.merge_data = merge_data
            # If your ESP supports header merge vars (Mailgun does), this works there;
            # across providers safest is also to include the link in body.
            msg.extra_headers = {"List-Unsubscribe": "<{{ unsubscribe_url }}>"}

            msg.send()  # uses Anymail backend

            # Create Delivery rows
            # anymail_status.recipients maps each email -> {'status': 'queued/sent', 'message_id': '...'}
            anymail_status = msg.anymail_status
            print(anymail_status)
            # esp_name = anymail_status.esp_name
            esp_name = 'mailgun'
            Delivery.objects.create(
                mailing=None,
                email=email_addr,
                esp_name=esp_name,  # normally 'mailgun'

                state="sending",  # accepted by ESP
                sent_at=timezone.now(),
                tags=[self.newsletter.slug],
            )

        except Exception as e:
            logger.exception(f"Test Email {self.pk} failed to send via Anymail/Mailgun error: {e}")

            return False
        return True

    # ---- Templates for send ----
    @cached_property
    def _templates(self):
        # Rendered for the 'message' action (see Newsletter.get_templates)
        return self.newsletter.get_templates("mailing")

    @property
    def subject_template(self):
        return self._templates[0]

    @property
    def text_template(self):
        return self._templates[1]

    @property
    def html_template(self):
        return self._templates[2]

    def render_html(self):
        html = ""
        for ia in self.issue_articles.select_related("article"):
            if self.html_template:
                html += ia.article.render_html(base_url=self.newsletter.base_url) + "<br><br>"
        return html

    def render_text(self):
        text = ""
        for ia in self.issue_articles.select_related("article"):
            text += ia.article.render_text(base_url=self.newsletter.base_url) + "\n\n"

        return text

    def render_email(self, extra_context=None):
        """
        Prepare subject, text, html, and attachments for this message.
        Returns a dict suitable for Mailgun.
        """
        context = {
            "issue": self,
            "newsletter": self.newsletter,
            "issue": self,
            "articles": self.ordered_articles,
        }
        if extra_context:
            context.update(extra_context)

        subject = self.subject_template.render(context).strip()

        text = self.text_template.render(context).strip()
        html = self.html_template.render(context).strip()

        files = []
        for ia in self.issue_articles.select_related("article"):
            for attach in ia.article.attachments.all():
                files.append(("attachment", (attach.file_name, attach.file.open("rb"))))

        return {
            "subject": subject,
            "text": text,
            "html": html,
            "files": files,
        }


class IssueArticle(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="issue_articles")
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="issue_links")
    position = models.PositiveIntegerField(default=0)
    appear_in_blog = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "id"]
        unique_together = [("issue", "article")]

    def __str__(self):
        return f"{self.issue.title} → {self.article.title} (#{self.position})"

    def save(self, *args, **kwargs):
        # automatically assign position to the end of the list if not provided.
        if not self.position:
            # Find current max position for this issue
            max_pos = (
                    IssueArticle.objects.filter(issue=self.issue)
                    .aggregate(_max=Max("position"))
                    .get("_max") or 0
            )
            self.position = max_pos + 1

        super().save(*args, **kwargs)


# ---------------------------------------------------------------------
# Mailing + Delivery
# ---------------------------------------------------------------------

class Mailing(CreatedUpdatedMixin):
    """
    Represents sending a Issue to newsletter subscribers.
    """

    class Status(models.TextChoices):
        INACTIVE = "0", "Inactive"
        QUEUED = "1", "Queued"
        SENDING = "2", "Sending"
        SENT = "3", "Sent"
        ERROR = "9", "Error"

    newsletter = models.ForeignKey(Newsletter, on_delete=models.CASCADE, related_name="mailings", editable=False)
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="mailings")

    # Optional: restrict to a subset; if empty, we resolve all active
    subscriptions = models.ManyToManyField(Subscription, blank=True, related_name="mailings")

    publish_date = models.DateTimeField(default=timezone.now, db_index=True)
    publish = models.BooleanField(default=True, help_text=_("Publish in archive."), db_index=True)

    status = models.CharField(max_length=1, choices=Status.choices, default=Status.INACTIVE)

    class Meta:
        verbose_name = _("mailing")
        verbose_name_plural = _("mailings")
        ordering = ["-created"]

    def __str__(self):
        return f"{self.issue} @ {self.publish_date:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if not self.pk:
            # keep newsletter in sync
            self.newsletter = self.issue.newsletter
        super().save(*args, **kwargs)

    @property
    def prepared(self):
        # "prepared" = has an Issue + Newsletter + at least one potential recipient
        if not self.issue_id or not self.newsletter_id:
            return False
        return bool(self.subscriptions.exists() or self.newsletter.get_subscriptions())

    @property
    def sending(self):
        return self.status == self.Status.SENDING

    @property
    def sent(self):
        return self.status == self.Status.SENT

    @property
    def is_active(self):
        return self.status in {self.Status.QUEUED, self.Status.SENDING}

    @property
    def is_inactive(self):
        return self.status == self.Status.INACTIVE

    @property
    def is_queued(self):
        return self.status == self.Status.QUEUED

    @property
    def is_sending(self):
        return self.status == self.Status.SENDING

    @property
    def is_sent(self):
        return self.status == self.Status.SENT

    # ----- Lifecycle -----
    @classmethod
    def send_issue(cls, issue: Issue) -> "Mailing":
        '''start processing of sending an issue to subscribers'''
        sub = cls(issue=issue, newsletter=issue.newsletter)
        sub.save()
        # default recipients = all active subscribers
        sub.subscriptions.set(issue.newsletter.get_subscriptions())
        return sub

    def queue(self):
        if self.is_sent:
            logger.warning(f" {self} already sent.")
            return
        self.status = self.Status.QUEUED
        self.save()

    def get_subscription_emails(self) -> list[str]:
        subs = self.subscriptions.active()
        if not subs.exists():
            subs = self.newsletter.get_subscriptions()
        return [s.email for s in subs if s.email]

    # @property
    # def extra_headers(self):
    #     unsubscribe_url = reverse("skorie_news-subscription-api-unsubscribe", args=[self.pk])
    #     return {
    #         "List-Unsubscribe": f"<https://{settings.SITE_URL}{unsubscribe_url}>"
    #     }

    # def send_via_mailgun(self):
    #     """
    #     Send to subscribers using Mailgun Batch API; write Delivery rows.
    #     Each recipient gets their own unsubscribe link.
    #     """
    #     if not (settings.MAILGUN_SENDER_DOMAIN and settings.MAILGUN_API_KEY):
    #         raise ValidationError("Mailgun not configured: set MAILGUN_SENDER_DOMAIN and MAILGUN_API_KEY.")
    #
    #     # collect recipients
    #     subs = list(self.subscriptions.active()) or list(self.skorie_news.get_subscriptions())
    #     recipients = [(s.email, (s.name or ""), s.pk, s.unsubscribe_url) for s in subs if s.email]
    #
    #     if not recipients:
    #         self.status = self.Status.INACTIVE
    #         self.save(update_fields=["status", "updated"])
    #         return
    #
    #     # render templates
    #     context = Context({
    #         "subscription": None,
    #         "site": Site.objects.get_current(),
    #         "mailing": self,
    #         "issue": self.issue,
    #         "skorie_news": self.skorie_news,
    #         "date": self.publish_date,
    #         "STATIC_URL": settings.STATIC_URL,
    #         "MEDIA_URL": settings.MEDIA_URL,
    #     })
    #     print(type(self.issue.subject_template))
    #     subject = self.issue.subject_template.render(context).strip()
    #     text = self.issue.text_template.render(context)
    #     html = self.issue.html_template.render(context) if self.issue.html_template else None
    #
    #     # send batches
    #     url = f"{settings.MAILGUN_API_URL}/{settings.MAILGUN_SENDER_DOMAIN}/messages"
    #     auth = ("api", settings.MAILGUN_API_KEY)
    #
    #     self.status = self.Status.SENDING
    #     self.save()
    #
    #     try:
    #         BATCH = 1000
    #         for i in range(0, len(recipients), BATCH):
    #             chunk = recipients[i:i+BATCH]
    #
    #         # per-recipient variables (includes secure unsubscribe URL)
    #             recipient_vars = {
    #             addr: {"name": name, "unsubscribe_url": u}
    #             for addr, name, _, u in chunk
    #             }
    #
    #             data = {
    #                 "from": self.skorie_news.get_sender,
    #                 "subject": subject,
    #                 "text": text,
    #                 "to": list(recipient_vars.keys()),
    #                 "recipient-variables": recipient_vars,
    #                 "h:List-Unsubscribe": "<%recipient.unsubscribe_url%>",
    #             }
    #             if html:
    #                 data["html"] = html
    #
    #             r = requests.post(url, auth=auth, data=data, timeout=30)
    #             r.raise_for_status()
    #             mailgun_id = (r.json() or {}).get("id")
    #
    #             Delivery.objects.bulk_create([
    #                 Delivery(mailing=self, email=addr, mailgun_id=mailgun_id, status="sent")
    #             for addr, *_ in chunk
    #             ])
    #
    #         # only mark as sent if ALL batches succeed
    #         self.status = self.Status.SENT
    #         self.save(update_fields=["status", "updated"])
    #
    #     except Exception as e:
    #         logger.exception("Mailing %s failed to send via Mailgun", self.pk)
    #         self.status = self.Status.ERROR
    #         self.save(update_fields=["status", "updated"])
    #         raise

    def send_via_anymail(self, batch_size: int = 800):
        subs = list(self.subscriptions.active()) or list(self.newsletter.get_subscriptions())


        recipients = [s for s in subs if s.email]
        if not recipients:
            self.status = self.Status.INACTIVE
            self.save(update_fields=["status", "updated"])
            return

        # Ordered list of issue articles for this issue
        articles = (
            self.issue.issue_articles
            .select_related("article")
            .order_by("position")
        )

        ctx = {
            "subscription": None,
            "site": Site.objects.get_current(),
            "mailing": self,
            "date": self.publish_date,
            "STATIC_URL": settings.STATIC_URL,
            "MEDIA_URL": settings.MEDIA_URL,
            'unsubscribe_url': self.newsletter.unsubscribe_url,
        }

        email = self.issue.render_email(extra_context=ctx)
        '''email = {
            "subject": subject,
            "text": text,
            "html": html,
            "files": files,
        }'''

        # 3) Update status
        #     self.issue.status = self.Status.SENDING
        #     self.issue.save()

        all_deliveries = []
        batch_size = 800
        try:
            # 4) Chunk recipients to respect Mailgun limits
            #for start in range(0, len(recipients), batch_size):
            for start in range(421, 820, batch_size):
                chunk = recipients[821:]


                # Per-recipient merge data (step 2: apply user details)
                to_list = [s.email for s in chunk]
                merge_data = {
                    s.email: {
                        "name": s.name or "",
                        "unsubscribe_url": s.unsubscribe_url,
                        "subscription_id": s.pk,
                    }
                    for s in chunk
                }

                msg = AnymailMessage(
                    subject=email['subject'],
                    body=email['text'],
                    from_email=self.newsletter.get_sender,
                    to=to_list,
                reply_to=[self.newsletter.reply_to,],
                )
                if 'html' in email and email['html']:
                    msg.attach_alternative(email['html'], "text/html")

                # Attachments on the Issue
                for _kind, (filename, fileobj) in email['files']:
                    try:
                        fileobj.open("rb")
                    except Exception:
                        pass
                    msg.attach(filename, fileobj.read())

                # Provider-agnostic knobs
                msg.tags = [NEWSLETTER_BASENAME or "newsletter", self.newsletter.slug]
                msg.metadata = {"mailing_id": str(self.pk), "newsletter_id": str(self.newsletter_id)}
                msg.merge_data = merge_data
                # If your ESP supports header merge vars (Mailgun does), this works there;
                # across providers safest is also to include the link in body.
                msg.extra_headers = {"List-Unsubscribe": "<{{ unsubscribe_url }}>"}

                self.status = self.Status.SENDING
                self.save(update_fields=["status", "updated"])

                msg.send()  # uses Anymail backend

                # Create Delivery rows
                # anymail_status.recipients maps each email -> {'status': 'queued/sent', 'message_id': '...'}
                anymail_status = msg.anymail_status
                print(anymail_status)
                # esp_name = anymail_status.esp_name
                esp_name = 'mailgun'

                # 6) Create Delivery rows for this batch
                for email_addr, r in anymail_status.recipients.items():
                    all_deliveries.append(Delivery(
                        mailing=self,
                        email=email_addr,
                        esp_name=esp_name,  # normally 'mailgun'
                        message_id=r.message_id,  # provider id
                        state="sending",  # accepted by ESP
                        sent_at=timezone.now(),
                        metadata={"mailing_id": self.pk},
                        tags=[self.newsletter.slug],
                    ))
            if all_deliveries:
                Delivery.objects.bulk_create(all_deliveries)

            self.status = self.Status.SENT
            self.save(update_fields=["status", "updated"])

        except Exception as e:
            logger.exception(f"Mailing {self.pk} failed to send via Anymail/Mailgun error: {e}")
            self.status = self.Status.ERROR
            self.save(update_fields=["status", "updated"])
            raise


class DirectEmail(CreatedUpdatedMixin):
    # Template/article to render from (optional)

    DIRECT_MAIL_DRAFT = "draft"
    DIRECT_MAIL_QUEUED = "queued"
    DIRECT_MAIL_SENDING = "sending"
    DIRECT_MAIL_SENT = "sent"
    DIRECT_MAIL_ERROR = "error"
    DIRECT_MAIL_CHOICES = (
        (DIRECT_MAIL_DRAFT, "Draft"),
        (DIRECT_MAIL_QUEUED, "Queued"),
        (DIRECT_MAIL_SENDING, "Sending"),
        (DIRECT_MAIL_SENT, "Sent"),
        (DIRECT_MAIL_ERROR, "Error"),
    )
    DIRECT_MAIL_DEFAULT = DIRECT_MAIL_DRAFT

    # Always store the raw target email
    to_email = models.EmailField(db_index=True)

    # SMTP from (do not conflate with sender FK)
    from_email = models.CharField(max_length=255, blank=True)

    # looksup
    user = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True,
                             on_delete=models.CASCADE)  # is this the sender or receive - have both already
    event = models.ForeignKey('web.Event', blank=True, null=True, on_delete=models.CASCADE)
    event_ref = models.CharField(max_length=5, db_index=True, blank=True, null=True)

    eventrole = models.ForeignKey("web.EventRole", blank=True, null=True, on_delete=models.CASCADE)
    competitor = models.ForeignKey("web.Competitor", blank=True, null=True, on_delete=models.CASCADE)
    entries = models.ManyToManyField("web.Entry")

    # context for rendering (optional, extend later if you want variables)
    context = models.JSONField(default=dict, blank=True)

    subject = models.CharField(max_length=255, blank=True)
    body_html = models.TextField(blank=True)
    body_text = models.TextField(blank=True)

    # lifecycle
    status = models.CharField(max_length=7, default=DIRECT_MAIL_DEFAULT, choices=DIRECT_MAIL_CHOICES)

    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        limit_choices_to={"template_type": Article.TEMPLATE_TYPE_EMAIL},
        blank=True, null=True,
        related_name="direct_emails",
    )
    template = models.CharField(max_length=50, blank=True, null=True,
                                help_text="Optional template name that appears in templates/email directory to render from")
    # sender = the staff/admin user who triggered the email
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="emails_sent",
        on_delete=models.PROTECT,
        help_text="The staff user who initiated this email",
    )

    # receiver = the user who is the intended recipient (optional)
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="emails_received",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text="Recipient user, if linked to an account",
    )

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.subject or '(no subject)'} → {self.to_email}"

    # --- helpers ---

    def save(self, *args, **kwargs):

        if not self.status or self.status == self.DIRECT_MAIL_DRAFT:

            if self.to_email:
                self.to_email = self.to_email.strip().lower()

        super().save(*args, **kwargs)

    def context_processor(self, context={}):
        '''add to context for email rendering'''

        context['SITE_URL'] = settings.SITE_URL
        context['SITE_NAME'] = settings.SITE_NAME
        context['SIGNATURE'] = settings.SIGNATURE
        context['SUPPORT_EMAIL'] = settings.SUPPORT_EMAIL
        context['LOGIN_URL'] = settings.LOGIN_URL
        return context

    def render(self, context, save=False):
        """
        Set subject/body from attached Article if not already provided.
        Keeps whatever you've explicitly set on the instance.
        """

        if self.article:
            if not self.subject:
                self.subject = self.article.title or ""
            if not self.body_html:
                self.body_html = self.article.body_html or ""
            if not self.body_text:
                self.body_text = self.article.body_text or ""

        elif self.template:
            # template is the name in the template/email directory
            context = self.context_processor(context)
            # TODO: remove context field - too big - don't know what's going to be in it - might be private.
            # self.context = context -

            if not self.subject:
                try:
                    self.subject = render_to_string(f"email/{self.template}/subject.txt", context).strip()
                except Exception as e:
                    logger.warning(f"Error {e} rendering subject for {self} using /email/{self.template}/subject.txt ")
                    raise

            if not self.body_text:
                try:
                    self.body_text = render_to_string(f"email/{self.template}/body.txt", context)
                except Exception as e:
                    logger.warning(f"Error {e} rendering body for {self} using /email/{self.template}/body.txt ")
                    raise

            if not self.body_html:
                try:
                    self.body_html = render_to_string(f"email/{self.template}/body.html", context)
                except Exception as e:
                    logger.warning(f"Error {e} rendering html body for {self} using /email/{self.template}/body.html ")
                    raise

        if save:
            self.save()

    @classmethod
    def send_simple_email(cls, subject, message, html=None, user=None, to_email=None, from_email=None):
        """
        Convenience factory: create, send, and return the Delivery (or None in DEBUG) - no template/context
        TODO: should get rid of this and just use mail.send
        """
        if user:
            to_email = user.email

        if not to_email:
            raise ValidationError("No recipient email provided")

        obj = cls.objects.create(
            to_email=to_email,
            receiver=user if user else None,
            subject=subject or "",
            body_text=message or "",
            body_html=html or "",
            from_email=from_email or "",
        )
        try:
            delivery = obj.send()
        except Exception as e:
            logger.error(f"Error sending simple email {obj}")
            return None
        else:
            return delivery

    def _build_message(self) -> AnymailMessage:
        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        msg = AnymailMessage(
            subject=self.subject or "",
            body=self.body_text or "",
            from_email=(self.from_email or default_from),
            to=[self.to_email],
            reply_to=[default_from, ],
        )
        if self.body_html:
            msg.attach_alternative(self.body_html, "text/html")

        # Optional provider-agnostic knobs
        msg.tags = ["direct-email"]
        msg.metadata = {
            "direct_email_id": str(self.pk),
            "event_id": getattr(self.event, "id", None),
            "receiver_id": getattr(self.receiver, "id", None),
        }

        # You can also add reply-to, headers, attachments here based on `context`
        # e.g. msg.reply_to = [ ... ]
        return msg

    def send(self):
        """
        Send via Anymail backend and create a Delivery row linked back to this message.
        Returns the Delivery instance (or None in DEBUG short-circuit).
        """

        if not self.to_email:
            raise ValidationError("to_email is required")

            if settings.DEBUG:
                # Dry-run: mark as sent without hitting an ESP
                self.status = "sent"
            self.updated = timezone.now()
            self.save(update_fields=["status", "updated"])
            return None

        msg = self._build_message()

        # transition → sending
        if self.status == self.DIRECT_MAIL_SENDING:
            self.save(update_fields=["status", "updated"])

        # send
        msg.send()
        st = getattr(msg, "anymail_status", None)

        # recip is AnymailRecipientStatus, not a dict
        recip = st.recipients.get(self.to_email) if hasattr(st, "recipients") else None
        message_id = getattr(recip, "message_id", None) or getattr(st, "message_id", None)
        esp_name = "mailgun"

        # Record Delivery (provider-agnostic)
        delivery = Delivery.objects.create(direct_mail=self,
                                           email=self.to_email,
                                           esp_name=esp_name,
                                           message_id=message_id,
                                           state="sending",  # accepted/queued by ESP; later webhooks will roll this up
                                           sent_at=timezone.now(),
                                           metadata={"direct_email_id": self.pk},
                                           tags=["direct-email"],
                                           )

        # local status → sent (means "handed to ESP")
        self.status = self.DIRECT_MAIL_SENT
        self.save(update_fields=["status", "updated"])

        return delivery

    @property
    def get_signature(self):

        if self.event:
            return "Event Team"
        else:
            return getattr('settings', 'SIGNATURE', '')


class Delivery(models.Model):
    mailing = models.ForeignKey(Mailing, on_delete=models.CASCADE, related_name="deliveries", blank=True,
                                null=True)  # only for newsletters not emails
    direct_mail = models.ForeignKey(DirectEmail, on_delete=models.CASCADE, related_name="direct_deliveries", blank=True,
                                    null=True)  # only for direct emails not newsletters
    email = models.EmailField()

    # ESP identity (Anymail-normalized)
    esp_name = models.CharField(
        max_length=20, default="mailgun", db_index=True,
        help_text="Which ESP handled the send (e.g., 'mailgun')."
    )
    message_id = models.CharField(
        max_length=255, blank=True, null=True, unique=True,
        help_text="Provider message id returned by Anymail."
    )
    mailgun_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, default="queued")  # queued, sent, delivered, failed, opened...
    created = models.DateTimeField(auto_now_add=True)

    provider_storage_url = models.URLField(blank=True, null=True)  # from 'storage.url'
    provider_message_size = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)], help_text="Bytes", blank=True
    )

    # Categorization/metadata coming from Mailgun
    tags = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    campaigns = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    user_variables = models.JSONField(default=dict, blank=True)  # from 'user-variables'

    # High-level state (rolled up from events)
    STATE_CHOICES = [
        ("queued", "Queued"),  # created/queued locally
        ("sending", "Sending"),  # accepted/queued by ESP
        ("delivered", "Delivered"),
        ("opened", "Opened"),
        ("clicked", "Clicked"),
        ("failed", "Failed"),
        ("complained", "Complained"),
        ("unsubscribed", "Unsubscribed"),
        ("rejected", "Rejected"),
        ("stored", "Stored"),
    ]
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="queued")

    # Timestamps (first occurrence)
    queued_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)  # accepted/sending
    delivered_at = models.DateTimeField(blank=True, null=True)
    opened_at = models.DateTimeField(blank=True, null=True)
    clicked_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    complained_at = models.DateTimeField(blank=True, null=True)
    unsubscribed_at = models.DateTimeField(blank=True, null=True)
    rejected_at = models.DateTimeField(blank=True, null=True)
    stored_at = models.DateTimeField(blank=True, null=True)

    # Counters & recency
    open_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    last_opened_at = models.DateTimeField(blank=True, null=True)
    last_clicked_at = models.DateTimeField(blank=True, null=True)
    last_event = models.CharField(max_length=20, choices=STATE_CHOICES, blank=True)
    last_event_at = models.DateTimeField(blank=True, null=True)

    # Provider details
    provider_storage_url = models.URLField(blank=True, null=True)  # e.g. Mailgun 'storage.url'
    provider_message_size = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)], help_text="Bytes", blank=True
    )
    tags = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    campaigns = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    user_variables = models.JSONField(default=dict, blank=True)  # metadata/merge vars you sent
    metadata = models.JSONField(default=dict, blank=True)  # extra internal metadata

    # Failure details (snapshot of latest)
    failure_severity = models.CharField(max_length=20, blank=True)  # 'temporary' | 'permanent'
    failure_reason = models.CharField(max_length=50, blank=True)  # e.g. 'bounce'
    smtp_code = models.IntegerField(blank=True, null=True)
    smtp_message = models.TextField(blank=True)
    raw_delivery_status = models.JSONField(default=dict, blank=True)

    # Lifecycle
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created"]
        constraints = [
            # If you keep legacy mailgun_id around, you can’t also enforce unique=True on it safely.
            models.UniqueConstraint(
                fields=["esp_name", "message_id"],
                name="uniq_delivery_esp_message",
                condition=models.Q(message_id__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["state", "last_event_at"]),
            models.Index(fields=["email", "state"]),
            models.Index(fields=["esp_name"]),
        ]

    def __str__(self):
        mid = self.message_id or self.mailgun_id or "∅"
        return f"{self.email} [{self.state}] ({mid})"

    # --- convenience updaters (optional, used by your tracking receiver) ---

    def mark_sent(self, ts=None):
        ts = ts or timezone.now()
        self.state = "sending"
        self.sent_at = self.sent_at or ts
        self.last_event = "queued"
        self.last_event_at = ts
        self.save(update_fields=["state", "sent_at", "last_event", "last_event_at", "updated"])

    def mark_delivered(self, ts):
        if not self.delivered_at:
            self.delivered_at = ts
        self.state = "delivered"
        self.last_event = "delivered"
        self.last_event_at = ts
        self.save(update_fields=["delivered_at", "state", "last_event", "last_event_at", "updated"])

    def mark_open(self, ts):
        self.open_count += 1
        self.last_opened_at = ts
        if not self.opened_at:
            self.opened_at = ts
        self.state = "opened"
        self.last_event = "opened"
        self.last_event_at = ts
        self.save(update_fields=[
            "open_count", "last_opened_at", "opened_at",
            "state", "last_event", "last_event_at", "updated"
        ])

    def mark_click(self, ts):
        self.click_count += 1
        self.last_clicked_at = ts
        if not self.clicked_at:
            self.clicked_at = ts
        self.state = "clicked"
        self.last_event = "clicked"
        self.last_event_at = ts
        self.save(update_fields=[
            "click_count", "last_clicked_at", "clicked_at",
            "state", "last_event", "last_event_at", "updated"
        ])

    def mark_failure(self, ts, *, severity="", reason="", smtp=None, status_json=None):
        if not self.failed_at:
            self.failed_at = ts
        self.state = "failed"
        self.last_event = "failed"
        self.last_event_at = ts
        self.failure_severity = severity or self.failure_severity
        self.failure_reason = reason or self.failure_reason
        if smtp:
            self.smtp_code = smtp.get("code")
            self.smtp_message = smtp.get("message", "")
        if status_json:
            self.raw_delivery_status = status_json
        self.save(update_fields=[
            "failed_at", "state", "last_event", "last_event_at",
            "failure_severity", "failure_reason", "smtp_code",
            "smtp_message", "raw_delivery_status", "updated"
        ])


class DeliveryEvent(CreatedUpdatedMixin):
    """
    Every webhook from Mailgun for a given message.
    Use this for idempotency and full audit.
    """

    # Event type and time
    DELIVERY_EVENT_CHOICES = [
        ("accepted", "accepted"),
        ("rejected", "rejected"),
        ("delivered", "delivered"),
        ("failed", "failed"),
        ("opened", "opened"),
        ("clicked", "clicked"),
        ("unsubscribed", "unsubscribed"),
        ("complained", "complained"),
        ("stored", "stored"),
    ]

    delivery = models.ForeignKey(
        Delivery, on_delete=models.CASCADE, related_name="events"
    )

    # Mailgun event id (unique)
    provider_event_id = models.CharField(max_length=255, unique=True)

    event = models.CharField(max_length=20, choices=DELIVERY_EVENT_CHOICES)
    occurred_at = models.DateTimeField()  # from webhook timestamp

    # Useful context
    recipient = models.EmailField()
    ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    geo = models.JSONField(default=dict, blank=True)  # if you use Mailgun geolocation

    # Click-specific (present only for clicked)
    url = models.URLField(blank=True)

    # Delivery failure detail snapshot for this event
    delivery_status = models.JSONField(default=dict, blank=True)

    # Raw payload for forensics/debugging
    raw_payload = models.JSONField()

    class Meta:
        ordering = ["occurred_at"]
        indexes = [
            models.Index(fields=["event"]),
            models.Index(fields=["recipient"]),
            models.Index(fields=["occurred_at"]),
        ]

    def __str__(self):
        return f"{self.event} @ {self.occurred_at:%Y-%m-%d %H:%M:%S} ({self.recipient})"

    class Meta:
        ordering = ["-created"]


class EventDispatch(EventMixin, CreatedUpdatedMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    article = models.ForeignKey(Article, on_delete=models.PROTECT, related_name="event_dispatches")

    # channel flags
    to_email_competitors = models.BooleanField(default=False)
    to_email_team = models.BooleanField(default=False)
    to_event_news = models.BooleanField(default=False)
    to_bluesky = models.BooleanField(default=False)
    to_facebook = models.BooleanField(default=False)
    to_whatsapp = models.BooleanField(default=False)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    queued_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{getattr(self, 'event', None)} – {self.article} ({self.status})"

    # ---- Orchestration ----
    def can_send(self, user_is_admin=False) -> bool:
        if user_is_admin:
            return True
        return bool(getattr(self.event, "is_open", False))

    def queue(self, user_is_admin=False):
        if not self.can_send(user_is_admin=user_is_admin):
            raise ValueError("Event is closed; cannot queue.")
        self.status = self.Status.QUEUED
        self.queued_at = timezone.now()
        self.save(update_fields=["status", "queued_at", "updated"])

    def send_now(self, user_is_admin=False):
        if not self.can_send(user_is_admin=user_is_admin):
            raise ValueError("Event is closed; cannot send.")

        try:
            if self.to_event_news:
                self._post_to_event_news()

            if self.to_email_competitors or self.to_email_team:
                self._send_email_batches()

            if self.to_bluesky:
                self._post_bluesky_stub()
            if self.to_facebook:
                self._post_facebook_stub()
            if self.to_whatsapp:
                self._post_whatsapp_stub()

            self.status = self.Status.SENT
            self.sent_at = timezone.now()
            self.last_error = ""
            self.save(update_fields=["status", "sent_at", "last_error", "updated"])
        except Exception as e:
            self.status = self.Status.FAILED
            self.last_error = str(e)
            self.save(update_fields=["status", "last_error", "updated"])
            raise

    # ---- Channels ----
    def _post_to_event_news(self):
        """
        Map Article -> your existing public News model.
        Adjust import/path and flags per your project.
        """
        News = apps.get_model("web", "News")  # adjust app/model name as needed
        News.objects.create(
            event=self.event,
            summary=self.article.title[:200],
            body=self.article.body_html,
            public=True,
            for_organisers=False,
            for_staff=False,
            for_competitors=False,
            url=None,
            publish_start=timezone.now(),
            publish_end=None,
        )

    def _send_email_batches(self):
        if not (settings.MAILGUN_SENDER_DOMAIN and settings.MAILGUN_API_KEY):
            raise ValidationError("Mailgun not configured: set MAILGUN_SENDER_DOMAIN and MAILGUN_API_KEY.")

        subject = self.article.title
        html = self.article.body_html or ""
        text = ""

        from_addr = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
        url = f"{settings.MAILGUN_API_URL}/{settings.MAILGUN_SENDER_DOMAIN}/messages"
        auth = ("api", settings.MAILGUN_API_KEY)

        def _emails(kind: str) -> list[str]:
            # Replace with your event helpers
            if kind == "competitors" and hasattr(self.event, "get_competitor_emails"):
                return list(self.event.get_competitor_emails())
            if kind == "team" and hasattr(self.event, "get_team_emails"):
                return list(self.event.get_team_emails())
            return []

        def _batch_send(addresses: list[str]):
            BATCH = 1000
            for i in range(0, len(addresses), BATCH):
                chunk = addresses[i:i + BATCH]
                recipient_vars = {addr: {"name": ""} for addr in chunk}
                data = {
                    "from": from_addr,
                    "subject": subject,
                    "html": html,
                    "text": text,
                    "to": chunk,
                    "recipient-variables": recipient_vars,
                }
                r = requests.post(url, auth=auth, data=data)
                r.raise_for_status()

        if self.to_email_competitors:
            _batch_send(_emails("competitors"))
        if self.to_email_team:
            _batch_send(_emails("team"))

    def _post_bluesky_stub(self):  # hook up API later
        pass

    def _post_facebook_stub(self):  # hook up API later
        pass

    def _post_whatsapp_stub(self):  # hook up BSP later
        pass
