import base64
import datetime
import hashlib
import json
import random
import secrets
import string
from datetime import timedelta


from cryptography.fernet import Fernet
from django.apps import apps
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.contrib.flatpages.models import FlatPage

from django.conf import settings
from django.utils import timezone
from django.utils.functional import cached_property

from django_users.models import OrganisationBase, PersonOrganisationBase, PersonBase, RoleBase, ModelRoles, \
    DataQualityLogBase, CommsChannelBase, VerificationCodeBase, UserContactBase, CustomUserBase, CustomUserManager, \
    CustomUserQuerySet,  EntryTicketLinkBase
from django_users.tools.model_mixins import DataQualityMixin

from skorie_news.model_mixins import NewsletterUserMixin


from django.core.exceptions import ValidationError
from django.db import models




from django.utils.translation import gettext_lazy as _


import logging



logger = logging.getLogger('django')

def lazy_import(full_path):
    """Lazily import an object from a given path."""
    module_path, _, object_name = full_path.rpartition('.')
    imported_module = __import__(module_path, fromlist=[object_name])
    return getattr(imported_module, object_name)



class CommsChannel(CommsChannelBase):
   pass

class VerificationCode(VerificationCodeBase):
    class Meta(VerificationCodeBase.Meta):
        # We start with the base constraints and will remove the problematic one via migrations
        # Setting this to [] caused "OperationalError: near '[]': syntax error" in SQLite
        pass

    def clean(self):
        super().clean()
        if not self.pk and self.consumed_at is None:
            # Check if there is already an active (unconsumed and UNEXPIRED) code
            # We ONLY block if there's one that hasn't expired yet.
            active_exists = VerificationCode.objects.filter(
                user=self.user,
                channel=self.channel,
                purpose=self.purpose,
                consumed_at__isnull=True,
                expires_at__gt=timezone.now()
            ).exists()
            
            if active_exists:
                raise ValidationError(
                    _("An active verification code already exists for this user and purpose.")
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def _create_code_row(cls, user, channel, purpose, ttl_minutes):
        expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
        raw_code = "".join(random.choices(string.digits, k=6))
        salt = secrets.token_hex(16)
        code_hash = hashlib.sha256((salt + raw_code).encode()).hexdigest()

        # Update or create: look for an existing active record
        obj = cls.objects.filter(
            user=user, channel=channel, purpose=purpose, consumed_at__isnull=True
        ).first()

        if obj:
            obj.code_hash = code_hash
            obj.code_salt = salt
            obj.token_hash = ""
            obj.expires_at = expires_at
            obj.attempts = 0  # Reset attempts on resend
            obj.save()
        else:
            obj = cls.objects.create(
                user=user,
                channel=channel,
                purpose=purpose,
                code_hash=code_hash,
                code_salt=salt,
                token_hash="",
                expires_at=expires_at,
            )
        return obj, {"code": raw_code, "expiry_minutes": ttl_minutes, "user": user}

    @classmethod
    def _create_token_row(cls, user, channel, purpose, ttl_minutes):
        expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
        raw_token = secrets.token_urlsafe(32)
        token_hash = cls._sha256_hex(raw_token)

        # Update or create: look for an existing active record
        obj = cls.objects.filter(
            user=user, channel=channel, purpose=purpose, consumed_at__isnull=True
        ).first()

        if obj:
            obj.token_hash = token_hash
            obj.code_hash = ""
            obj.code_salt = ""
            obj.expires_at = expires_at
            obj.attempts = 0  # Reset attempts on resend
            obj.save()
        else:
            obj = cls.objects.create(
                user=user,
                channel=channel,
                purpose=purpose,
                token_hash=token_hash,
                code_hash="",
                code_salt="",
                expires_at=expires_at,
            )
        return obj, {"token": raw_token, "expiry_minutes": ttl_minutes, "user": user}



class DataQualityLog(DataQualityLogBase):
    pass

class PersonOrganisation(PersonOrganisationBase):
    pass



class Person(DataQualityMixin, PersonBase):

    def save(self, *args, **kwargs):

        super().save(*args, **kwargs)
        self.change_name_globally()

    def change_name_globally(self):
        '''name is added to various models - replace them all'''
        users = self.customuser_set.all()


        # note that person is not getting set in competitor and should be
        Competitor = apps.get_model('web', 'Competitor')
        for item in Competitor.objects.filter(user__in=users):
            item.name = self.formal_name

            if not item.person:
                item.person = self

            item.save()

        Role = apps.get_model('users', 'Role')
        for item in Role.objects.filter(person=self):
            item.name = self.formal_name
            item.save()


        EventRole = apps.get_model('web', 'EventRole')
        # this should probably inherit from the user object as it is not related to person
        for item in EventRole.objects.filter(user__in=users):
            item.name = self.formal_name
            item.save()


class Role(RoleBase):
    pass

class Organisation(OrganisationBase):
    code = models.CharField(max_length=8, help_text=_("Max 10 chars upper case.  Used to tag data as belonging to the organisation"))
    settings = models.JSONField(default=dict, blank=True, help_text=_("Settings for this organisation"))
    '''
    {"STRIPE_API_KEY":"sk_test_51PH596KLzhkFeFrKYqw05ssNcnAvJRtTtx0vjRdP30R8oZW1kJX8Zz28EX7WCqp4Gl7oINEGks9158vd0H6xl6Rn0040SWxkF0","STRIPE_SECRET_KEY":"whsec_pHidHiMenLyJzp0bs8ziAd0ToWz6NWu7", "CURRENCY": "EUR"}
    '''
    # seller = models.ForeignKey("web.Seller", on_delete=models.CASCADE, blank=True, null=True)

    def decrypt_settings_data(self):
        cipher_suite = Fernet(settings.SETTINGS_KEY)
        decrypted_value = cipher_suite.decrypt(base64.b64decode(self.settings)).decode('utf-8')
        return json.loads(decrypted_value)

    @property
    def has_payment_gateway(self):
        '''this can get more sophisticated'''
        if 'PAYMENT_VARIANTS' in settings:
            return True

        return 'STRIPE_API_KEY' in self.settings or hasattr(settings, 'STRIPE_API_KEY')



class CustomUser(DataQualityMixin, NewsletterUserMixin, CustomUserBase):
    EXTRA_ROLES = {
        'testmanager': "Testsheet Manager",
        'testchecker': "Testsheet Checker",
        'devteam': "Skorie Development Team",
    }

    USER_STATUS_ANON = 0
    USER_STATUS_NA = 1  # used for system users
    USER_STATUS_TEMPORARY = 2  # used where user has signed in with an acocunt like scorer1@skor.ie
    USER_STATUS_UNCONFIRMED = 3
    USER_STATUS_CONFIRMED = 4
    USER_STATUS_TRIAL = 5
    USER_STATUS_SUBSCRIBED = 7
    USER_STATUS_TRIAL_LAPSED = 8
    USER_STATUS_SUBSCRIBED_LAPSED = 9
    DEFAULT_USER_STATUS = USER_STATUS_TEMPORARY

    USER_STATUS = (
        (USER_STATUS_ANON, "Unknown"),
        (USER_STATUS_NA, "Not Applicable"),
        (USER_STATUS_TEMPORARY, "Temporary"),
        (USER_STATUS_UNCONFIRMED, "Unconfirmed"),
        (USER_STATUS_CONFIRMED, "Confirmed"),
        (USER_STATUS_TRIAL, "Trial"),
        (USER_STATUS_SUBSCRIBED, "Subscribed"),  #TODO: rename to avoid confusion with subscribed to newsletter
        (USER_STATUS_TRIAL_LAPSED, "Trial Lapsed"),
        (USER_STATUS_SUBSCRIBED_LAPSED, "Subscription Lapsed"),
    )
    objects = CustomUserManager.from_queryset(CustomUserQuerySet)()

    # subscribed left as used in relation to users subscription to skorie - should be renamed to avoid
    # confusion with newsletter subscription
    subscribed = models.DateTimeField(blank=True, null=True)
    unsubscribed = models.DateTimeField(blank=True, null=True)
    # event_notifications_subscribed = models.DateTimeField(blank=True, null=True)
    # event_notifications_unsubscribed = models.DateTimeField(blank=True, null=True)


    def save(self, *args, **kwargs):

        # confirm once profile complete (ie. country is set)
        if self.country and self.profile and self.status == self.USER_STATUS_UNCONFIRMED:
            self.confirm()

        super().save(*args, **kwargs)

        # during migration - copy across missing comms channel
        if self.comms_channels.all().count() == 0:
            CommsChannel.objects.create(user=self, channel_type='email', value=self.email)
            if self.mobile:
                CommsChannel.objects.create(user=self, channel_type='sms', value=self.mobile)

    @property
    def is_rider(self):
        return self.is_competitor

    @cached_property
    def is_issuer(self):
        return Role.objects.active().filter(user=self, role_type=self.ModelRoles.ROLE_ISSUER).exists()


    @property
    def is_temporary(self):
        return self.status == self.USER_STATUS_TEMPORARY

    @property
    def is_unconfirmed(self):
        return self.status == self.USER_STATUS_UNCONFIRMED or self.status == self.USER_STATUS_TEMPORARY

    @property
    def is_confirmed(self):
        return self.status in (self.USER_STATUS_CONFIRMED, self.USER_STATUS_SUBSCRIBED)


    def update_subscribed(self, subscribe:bool):

        logger.warning(f"updating subscribed for {self} to {subscribe} in model - replace with subscribe to newsletter")

        # if settings.USE_NEWSLETTER:
        #     # sync with django-newsletter models
        #     Subscription = apps.get_model('newsletter', 'Subscription')
        #     Newsletter = apps.get_model('newsletter', 'Newsletter')
        #     general_newsletter = Newsletter.objects.get(slug=settings.NEWSLETTER_GENERAL_PK)
        #     sub, _ = Subscription.objects.get_or_create(newsletter=general_newsletter,  user=self)
        #     if subscribe and not sub.subscribed:
        #         sub.update('subscribe')
        #     elif not subscribe and sub.subscribed:
        #         sub.update('unsubscribe')



    def confirm(self, user=None, save=True):

        self.status = self.USER_STATUS_CONFIRMED
        if save:
            self.save()



class UserContact(UserContactBase):

    attributes = models.JSONField(default=dict, blank=True, help_text=_("Data for this contact"))

    def save(self, *args, **kwargs):
        if self.data and not self.attributes:
            self.attributes = self.data

        if not self.site:
            self.site = settings.SITE_URL.replace('https://', '')

        super().save(*args, **kwargs)

    def positive_attributes(self):
        """Return a list of attributes and their values that were not False."""
        if self.attributes:
            try:
                return {k: v for k, v in self.attributes.items() if v not in (False, None, '')}
            except Exception as e:
                logger.error(f"Error processing attributes for {self}: {e}")
                return {}
