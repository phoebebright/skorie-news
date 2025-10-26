# skorie_news/api/viewsets.py
import hashlib
import hmac
import json
import logging
from typing import Tuple, Dict, Any

import requests
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_users.tools.permission_mixins import UserCanAdministerMixin
from rest_framework import viewsets, status, mixins
from rest_framework.decorators import action, authentication_classes
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.mixins import CreateModelMixin, RetrieveModelMixin, ListModelMixin
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet, GenericViewSet
from rest_framework_datatables.django_filters.backends import DatatablesFilterBackend
from rest_framework_datatables.pagination import DatatablesPageNumberPagination
from rest_framework_datatables.renderers import DatatablesRenderer

from config import settings
from skorie.common.api import verify_signature
from tools.permissions import IsAdministratorPermission

from .models import Newsletter, Subscription, Mailing, Issue, SubscriptionEvent, IssueArticle, Article, Delivery, \
    DirectEmail, DeliveryEvent
from .serializers import SubscriptionSerializer, MessageSerializer, SubmissionSerializer, SubscriptionEventSerializer, \
    ArticleSerializer, IssueArticleSerializer, IssueArticlesUpdateSerializer, \
    SubscriptionManageDTSerializer, DirectEmailCreateSerializer, DirectEmailReadSerializer

User = get_user_model()
logger = logging.getLogger('django')

MANAGE_EMAIL_SALT = "skorie_news.manage_email"
MANAGE_EMAIL_MAX_AGE = 60 * 60 * 24  # 24h

class SubscriberEventListAPIView(ListAPIView):
    """
    GET /api/v2/skorie_news/subscribers/<pk>/events/
    Returns up to 50 most recent events for the subscriber.
    """
    serializer_class = SubscriptionEventSerializer

    def get_queryset(self):
        pk = self.kwargs.get("pk")
        try:
            sub = Subscription.objects.get(pk=pk)
        except Subscription.DoesNotExist:
            raise NotFound("Subscriber not found.")
        return SubscriptionEvent.objects.filter(subscription=sub).order_by("-at")[:50]


class SubscriptionManagePagination(DatatablesPageNumberPagination):
    page_size_query_param = "length"  # DataTables uses "length"
    page_size = 100

class AdminSubscriptionROViewSet(ReadOnlyModelViewSet):
    queryset = Subscription.objects.select_related("newsletter","user")
    serializer_class = SubscriptionManageDTSerializer
    pagination_class = SubscriptionManagePagination
    filter_backends = [DatatablesFilterBackend,]
    renderer_classes = [DatatablesRenderer,]
    search_fields = ["email", ]  # global search box
    ordering_fields = ["email",  "subscribe_date", "unsubscribe_date", ]
    ordering = ["-subscribe_date"]

    def get_queryset(self):
        qs = Subscription.objects.all()
        newsletter_slug = self.request.query_params.get("newsletter")
        if newsletter_slug:
            qs = qs.filter(newsletter__slug=newsletter_slug)
        return qs

class SubscriptionAdminViewSet(UserCanAdministerMixin, ModelViewSet):
    """
    Admin: list/retrieve/update/destroy (IsAdminUser)
    Public: POST /api/subscriptions/subscribe/  (AllowAny)
      body: { "newsletter": "<slug>", "email": "...", "name": "..." }
    """
    queryset = Subscription.objects.all().order_by("-created")
    serializer_class = SubscriptionSerializer
    http_method_names = ['post', 'get', 'patch', ]
    #
    # def get_permissions(self):
    #     if self.action in {"subscribe", "create"}:
    #         # You may prefer to disallow generic create and only allow 'subscribe'
    #         return [AllowAny()]
    #     return [IsAdminUser()]

    def create(self, request, *args, **kwargs):
        '''can pass in user pk or just email and name'''

        nl = Newsletter.objects.get(slug=request.data.get('newsletter'))
        if 'user_keycloak_id' in request.data:
            user = User.objects.get(keycloak_id=request.data.get('user_keycloak_id'))
            email = user.email
            name = user.formal_name

        else:
            email = (request.data.get("email") or "").strip().lower()
            name = (request.data.get("name") or "").strip()

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                user = None

        # Idempotent check
        existing = Subscription.objects.filter(newsletter=nl, email__iexact=email).first()
        if existing:
            if existing.subscribed:
                return Response("Already subscribed", status=status.HTTP_200_OK)
            else:
                existing.subscribe()
                return Response("Re-subscribed", status=status.HTTP_200_OK)

        # create new subscription
        with transaction.atomic():
            sub = Subscription.objects.create(
                newsletter=nl, email=email, name=name, user=user
            )
            consent = {'consent_text': f'Subscribed by {request.user}'}
            sub.subscribe(consent=consent, user=request.user)

        return Response("Subscribed", status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"])
    def subscribe_me(self, request, *args, **kwargs):
        """
        Public-friendly endpoint:
        - Accepts newsletter slug
        - Idempotent (returns 200 if already exists)
        - Returns message + serialized subscription
        """
        if 'pk' in kwargs:
            obj = Subscription.objects.get(pk=kwargs["pk"])
        else:
            obj = Subscription.objects.get(slug=settings.NEWSLETTER_GENERAL_SLUG)

        obj.subscribe(user=request.user)

        # add to django messages framework
        messages.success(request, f"Subscribed to {obj.newsletter} successfully")

        return Response(status=status.HTTP_200_OK)


    @action(detail=True, methods=["patch"])
    def unsubscribe_me(self, request, *args, **kwargs):
        """
        Public-friendly endpoint:
        - Accepts newsletter slug
        - Idempotent (returns 200 if already exists)
        - Returns message + serialized subscription
        """
        if 'pk' in kwargs:
            obj = Subscription.objects.get(pk=kwargs["pk"])
        else:
            obj = Subscription.objects.get(slug=settings.NEWSLETTER_GENERAL_SLUG)

        obj.unsubscribe(request.user)

        # add to django messages framework
        messages.success(request, f"Unsubscribed from {obj.newsletter} successfully")

        return Response(status=status.HTTP_200_OK)



    @action(detail=True, methods=["patch"])
    def unsubscribe(self, request, pk=None):
        sub = get_object_or_404(Subscription, pk=pk)
        sub.unsubscribe()
        return Response({"status": "ok", "message": "You have been unsubscribed."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"])
    def resubscribe(self, request, pk=None):
        sub = get_object_or_404(Subscription, pk=pk)
        sub.subscribe()
        return Response({"status": "ok", "message": "You have been resubscribed."}, status=status.HTTP_200_OK)

class UserOrManagedMixin(GenericViewSet):
    '''if logged in user then use that, else use session managed email
    also remove sesison managed email if there is a logged in user'''
    user = None
    email = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.user = request.user
            self.email = request.user.email
            # remove any managed email in session
            if 'managed_email' in request.session:
                del request.session['managed_email']
        else:
            self.user = None
            self.email = request.session.get('managed_email', None)


        return super().dispatch(request, *args, **kwargs)

class SubscriptionPublicViewSet(UserOrManagedMixin, GenericViewSet):
    """
    Manage subscriptions for:
      - an authenticated user, OR
      - a verified guest email (stored as request.session["managed_email"] via magic link).

    Endpoints:
      POST /request_manage_link/     (public)  -> emails a magic link
      GET  /list_current/            (public*) -> requires auth OR session-managed email
      POST /toggle/                  (public*) -> requires auth OR session-managed email
      GET /clear_session/           (public)  -> clears managed_email from session
    """
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
    permission_classes = [AllowAny]  # All actions do their own subject checks

    # ---------------- helpers ----------------


    # def _subject(self, request):
    #     """
    #     Returns a dict describing the current subject or None:
    #       {"kind": "user",  "user": <User>}  if authenticated
    #       {"kind": "email", "email": "<verified@email>"} if guest w/ session
    #     """
    #     if request.user.is_authenticated:
    #         return {"kind": "user", "user": request.user}
    #     email = request.session.get("managed_email")
    #     if email:
    #         return {"kind": "email", "email": email}
    #     return None

    @action(detail=False, methods=["post"], url_path="request-subscribe")
    def request_subscribe(self, request):
        """
        Body: { "email": "...", "newsletter_slug": "...", "name": "Optional" }
        Guest (no login) double-opt-in: send a confirmation email with secure link.
        """
        email = request.data.get("email").strip().lower()
        slug = (request.data.get("newsletter_slug") or settings.NEWSLETTER_GENERAL_SLUG).strip()
        name = (request.data.get("name") or "").strip()
        if not email or not slug:
            return Response({"detail": "email and newsletter_slug required."}, status=400)

        nl = get_object_or_404(Newsletter, slug=slug)

        # Reuse existing email-only subscription or create pending
        sub = Subscription.objects.filter(newsletter=nl, email=email).first()
        if not sub:
            # create a pending record (subscribed False)
            sub = Subscription.objects.create(
                newsletter=nl, email=email, name=name)
        else:
            # update display name if newly provided
            if name and not sub.name:
                sub.name = name
                sub.save(update_fields=["name"])

        if sub.subscribed:
            return Response({"msg": f"You are already subscribed with {email} ."}, status=200)

        # Build confirm URL
        confirm_path = reverse("news:confirm-subscribe", args=[sub.pk, sub.activation_code])
        confirm_url = f"{settings.SITE_URL}{confirm_path}"

        # Send confirmation email (privacy-safe regardless of state)
        ctx = {"newsletter": nl, "confirm_url": confirm_url}
        subject = f"Confirm your subscription – {nl.title}"
        text = render_to_string("skorie_news/email/sub_request.txt", ctx)
        html = render_to_string("skorie_news/email/sub_request.html", ctx)

        from django.core.mail import EmailMultiAlternatives
        msg = EmailMultiAlternatives(
            subject, text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send()

        return Response({"msg": f"We have emailed a link to {email} to confirm your subscription."}, status=200)



    # ---------------- public: request magic link ----------------

    @action(detail=False, methods=["post"], url_path="request_manage_link")
    def request_manage_link(self, request):
        """
        Body: { "email": "you@example.com" }
        Always emails a privacy-safe magic link that, when visited, stores
        managed_email in the session and lets the guest manage their subscriptions.
        """
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "email required."}, status=400)

        signer = signing.TimestampSigner(salt=MANAGE_EMAIL_SALT)
        token = signer.sign(email)
        manage_claim_url = f"{settings.SITE_URL}/skorie_news/manage/claim/{token}/"

        ctx = {"manage_url": manage_claim_url}
        subject = "Manage your subscriptions"
        text = render_to_string("skorie_news/email/manage_link.txt", ctx)
        html = render_to_string("skorie_news/email/manage_link.html", ctx)

        msg = EmailMultiAlternatives(
            subject, text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send()

        return Response({"ok": True})

    # ---------------- list current subject’s subscriptions ----------------

    @method_decorator(never_cache)
    @action(detail=False, methods=["get"], url_path="list_current")
    def list_current(self, request):
        """
        Returns all newsletters with subscription status for the current subject.
        Requires either an authenticated user OR a verified session email.
        """

        items = []

        for nl in Newsletter.objects.public().active():
            sub = Subscription.objects.filter(newsletter=nl, email=self.email).first()

            items.append({
                "newsletter": {"slug": nl.slug, "title": nl.title, "about": nl.about or ""},
                "subscribed": bool(sub and sub.subscribed and not sub.unsubscribed),
                "subscription_id": sub.pk if sub else None,
            })

        return JsonResponse(items, safe=False)

    # ---------------- toggle subscribe/unsubscribe ----------------

    @action(detail=False, methods=["patch"], url_path="toggle")
    @transaction.atomic
    def toggle(self, request):
        """
        Body: { "newsletter_slug": "...", "action": "subscribe"|"unsubscribe" }
        Creates or updates the subject's subscription.
        Works for logged-in users and verified session-managed emails.
        """

        slug  = (request.data.get("newsletter_slug") or "").strip()
        action = (request.data.get("action") or "").strip().lower()
        if action not in {"subscribe", "unsubscribe"}:
            return Response({"detail": "Invalid action."}, status=400)

        nl = get_object_or_404(Newsletter, slug=slug)


        if self.user:
            if action == "subscribe":
                sub = nl.subscribe_from_request(request)
                status_txt = "subscribed"
            else:
                sub = nl.unsubscribe_from_request(request)
                status_txt = "unsubscribed"

        else:
            sub, _ = Subscription.objects.get_or_create(
                newsletter=nl, user__isnull=True, email=self.email)


            consent = Subscription.consent_from_request(request)

            if action == "subscribe":
                sub.subscribe(consent=consent, user=request.user)
                status_txt = "subscribed"
            else:
                sub.unsubscribe(consent=consent, user=request.user)
                status_txt = "unsubscribed"

        return Response({"ok": True, "status": status_txt, "subscription_id": sub.pk})

    # ---------------- utility: clear managed email in session ----------------

    @action(detail=False, methods=["get"], url_path="clear-session")
    def clear_session(self, request):
        request.session.pop("managed_email", None)
        return Response({"ok": True})


class IssueViewSet(ModelViewSet):
    queryset = Issue.objects.all()
    serializer_class = MessageSerializer
    permission_classes = (IsAuthenticated, IsAdministratorPermission)
    http_method_names = ["post", "get"]

    @action(detail=True, methods=["post"], url_path="queue")
    def queue(self, request, pk=None):
        message = self.get_object()
        if not message.newsletter_id:
            return Response({"status": "error", "detail": "No newsletter linked."}, status=400)

        submission = message.submit()
        logger.info(f"Message {message.pk} manually queued as submission {submission.pk} by user {request.user}")


        return Response(
            {
                "status": "ok",
                "submission_id": submission.pk,
                "message": f"Submission queued for '{message.title}' (#{submission.pk}).",
            },
            status=201,
        )

    @action(detail=True, methods=["post"], url_path="send_test")
    def send_test(self, request, pk=None):
            """Send this issue (Message) to a test email via Mailgun."""
            message = self.get_object()
            test_email = (request.data.get("email") or "").strip().lower()
            if not test_email:
                return Response({"error": "Missing email"}, status=status.HTTP_400_BAD_REQUEST)

            # use the model helper
            rendered = message.render_email()

            url = f"https://api.mailgun.net/v3/{settings.MAILGUN_DOMAIN}/messages"
            auth = ("api", settings.MAILGUN_API_KEY)

            data = {
                "from": message.newsletter.get_sender(),
                "to": [test_email],
                "subject": f"[TEST] {rendered['subject']}",
                "text": rendered["text"],
            }
            if rendered["html"]:
                data["html"] = rendered["html"]

            r = requests.post(url, auth=auth, data=data, files=rendered["files"])

            # cleanup: close file handles
            for _, (_, f) in rendered["files"]:
                f.close()

            if r.ok:
                return Response({"status": "ok", "msg": f"Sent test to {test_email}"})
            else:
                return Response({"error": r.text}, status=r.status_code)

class MailingViewSet(ModelViewSet):
    queryset = Mailing.objects.all()
    serializer_class = SubmissionSerializer
    permission_classes = (IsAuthenticated, IsAdministratorPermission)
    http_method_names = ["post", "get"]

    @action(detail=True, methods=["post"], url_path="send")
    def send(self, request, pk=None):
        sub = get_object_or_404(Mailing, pk=pk)

        #TODO: don't resend

        sub.submit(send_now=True)

        sub.refresh_from_db()
        if sub.is_sent:
            return Response(
                {
                    "status": "ok",
                    "message": f"Submission {sub.pk} has already been sent.",
                },
                status=200,
            )
        elif sub.is_sending:
            return Response(
                {
                    "status": "ok",
                    "message": f"Submission {sub.pk} is sending.",
                },
                status=200,
            )
        elif sub.is_error:
            return Response({
                "status": "error",
                "message": f"Submission {sub.pk} failed ",
            }, status=400)
        else:
            return Response({
                "status": "error",
                "message": f"Unknown error in Submission send {sub.pk} ",
            }, status=400)

    @action(detail=True, methods=["post"], url_path="send")
    def submit(self, request, pk=None):
        sub = get_object_or_404(Mailing, pk=pk)

        # TODO: don't resend

        sub.submit(send_now=False)

        sub.refresh_from_db()
        if sub.is_sent:
            return Response(
                {
                    "status": "ok",
                    "message": f"Submission {sub.pk} has already been sent.",
                },
                status=200,
            )
        elif sub.is_sending:
            return Response(
                {
                    "status": "ok",
                    "message": f"Submission {sub.pk} is sending.",
                },
                status=200,
            )
        elif sub.is_error:
            return Response({
                "status": "error",
                "message": f"Submission {sub.pk} failed ",
            }, status=400)
        else:
            return Response({
                "status": "error",
                "message": f"Unknown error in Submission submit {sub.pk} ",
            }, status=400)

class MailgunWebhookView(APIView):
    authentication_classes = []  # public
    permission_classes = []

    def post(self, request):
        event = request.data
        mailgun_id = event.get("message-id") or event.get("id")
        event_type = event.get("event")

        # try:
        #     delivery = Delivery.objects.get(mailgun_id=mailgun_id, email=event.get("recipient"))
        # except Delivery.DoesNotExist:
        #     return Response({"status": "ignored"}, status=200)
        #
        # delivery.status = event_type
        # delivery.event = event
        # delivery.save()

        return Response({"status": "ok"})

# Articles (for quick create / listing library)
class ArticleViewSet(CreateModelMixin,
                     RetrieveModelMixin,
                     ListModelMixin,
                     GenericViewSet):
    queryset = Article.objects.all().order_by("-is_template", "-updated")
    serializer_class = ArticleSerializer

# Issues (Messages)
class IssueViewSet(ModelViewSet):
    """
    Admin-only CRUD for issues + custom actions:
      - GET /issues/{id}/articles/           -> current list (ordered)
      - PUT /issues/{id}/articles/           -> replace ordering/flags
      - POST /issues/{id}/articles/add/      -> add one article (appended)
      - DELETE /issues/{id}/articles/{aid}/  -> remove article
      - POST /issues/{id}/queue/             -> create/reuse Submission + queue
      - POST /issues/{id}/publish/           -> set published_at
    """
    queryset = Issue.objects.select_related("newsletter").all().order_by("-created")
    serializer_class = MessageSerializer


    # ----- articles list / save -----
    @action(detail=True, methods=["get"], url_path="articles")
    def articles_list(self, request, pk=None):
        issue = self.get_object()
        links = issue.issue_articles.select_related("article").order_by("position", "id")
        data = IssueArticleSerializer(links, many=True).data
        return Response(data)

    @articles_list.mapping.put
    def articles_save(self, request, pk=None):
        issue = self.get_object()
        ser = IssueArticlesUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        items = ser.validated_data["articles"]

        with transaction.atomic():
            IssueArticle.objects.filter(issue=issue).delete()
            pos = 1
            for it in items:
                art_id = int(it["article"])
                appear = bool(it.get("appear_in_blog", False))
                position = int(it.get("position") or pos)
                IssueArticle.objects.create(
                    issue=issue, article_id=art_id,
                    position=position, appear_in_blog=appear
                )
                pos += 1

        return Response({"ok": True})

    # ----- add / remove single article -----
    @action(detail=True, methods=["post"], url_path="articles/add")
    def article_add(self, request, pk=None):
        issue = self.get_object()
        article_id = request.data.get("article")
        if not article_id:
            return Response({"detail": "Missing 'article'."}, status=400)
        last_pos = issue.issue_articles.order_by("-position").values_list("position", flat=True).first() or 0
        IssueArticle.objects.create(issue=issue, article_id=int(article_id), position=last_pos + 1)
        return Response({"ok": True}, status=201)

    @action(detail=True, methods=["delete"], url_path=r"articles/(?P<article_id>\d+)")
    def article_remove(self, request, pk=None, article_id=None):
        issue = self.get_object()
        IssueArticle.objects.filter(issue=issue, article_id=article_id).delete()
        return Response(status=204)

    # ----- queue / publish actions -----
    @action(detail=True, methods=["post"])
    def queue(self, request, pk=None):
        issue = self.get_object()
        sub = issue.submit()  # your model method
        return Response({"ok": True, "submission": SubmissionSerializer(sub).data})

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        issue = self.get_object()
        issue.publish_to_blog()
        return Response({"ok": True, "published_at": issue.published_at})

    @action(detail=True, methods=["post"])
    def send_test(self, request, pk=None):
        issue = self.get_object()
        test_email = (request.data.get("email") or "").strip().lower()
        if not test_email:
            return Response({"error": "Missing email"}, status=status.HTTP_400_BAD_REQUEST)

# ---------- ViewSet ----------

class AdminSubscriberViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    GenericViewSet
):
    """
    Admin-only subscriber management for a single Newsletter.
    Routes (via router.register('admin/subscribers', ...)):

    - GET    /api/v2/skorie_news/admin/subscribers/?newsletter=<slug>&q=&status=&page=&page_size=
    - POST   /api/v2/skorie_news/admin/subscribers/               (newsletter_slug, email, name)
    - POST   /api/v2/skorie_news/admin/subscribers/bulk/          (action, ids[])
    - POST   /api/v2/skorie_news/admin/subscribers/{id}/unsubscribe/
    - POST   /api/v2/skorie_news/admin/subscribers/{id}/resubscribe/
    - DELETE /api/v2/skorie_news/admin/subscribers/{id}/erase/
    - GET    /api/v2/skorie_news/admin/subscribers/{id}/events/
    """
    permission_classes = [IsAdminUser]
    queryset = Subscription.objects.select_related("newsletter").all()

    def get_serializer_class(self):
        if self.action == "create":
            return AdminSubscriberCreateSerializer
        return AdminSubscriberSerializer

    # ---- List with server-side filtering/pagination ----
    def get_queryset(self):
        qs = super().get_queryset()

        # Required newsletter slug
        nl_slug = self.request.query_params.get("newsletter")
        if not nl_slug:
            return qs.none()
        try:
            nl = Newsletter.objects.get(slug=nl_slug)
        except Newsletter.DoesNotExist:
            return qs.none()
        qs = qs.filter(newsletter=nl)

        # Status filter
        status_filter = (self.request.query_params.get("status") or "active").lower()
        if status_filter == "active":
            qs = qs.filter(subscribed=True, unsubscribed=False)
        elif status_filter == "unsub":
            qs = qs.filter(unsubscribed=True)
        elif status_filter == "suppressed":
            # If you track suppression flags, filter here; else return none
            qs = qs.filter(Q(bounced=True) | Q(complained=True) | Q(active=False)) if hasattr(Subscription, "bounced") else qs.none()
        elif status_filter == "all":
            pass  # no extra filter

        # Search (email|name|user.username)
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(email__icontains=q) |
                Q(name__icontains=q) |
                Q(user__username__icontains=q)
            )

        return qs.order_by("email", "id")

    # ---- Pagination: DRF’s standard PageNumberPagination will be used ----

    # ---- Bulk actions ----
    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request):
        action_name = (request.data.get("action") or "").lower()
        ids = request.data.get("ids") or []
        if action_name not in {"unsubscribe", "resubscribe", "erase"}:
            return Response({"error": "Invalid action."}, status=400)
        if not ids:
            return Response({"error": "No IDs provided."}, status=400)

        subs = self.get_queryset().filter(id__in=ids)
        count = 0

        if action_name == "unsubscribe":
            for s in subs:
                s.unsubscribe()
                count += 1
        elif action_name == "resubscribe":
            for s in subs:
                s.subscribe()
                count += 1
        else:  # erase (GDPR)
            # If you keep audit, mark erased. Otherwise delete.
            # Here we delete (adjust to your policy).
            count, _ = subs.delete()

        return Response({"ok": True, "count": count})

    # ---- Row actions ----
    @action(detail=True, methods=["post"])
    def unsubscribe(self, request, pk=None):
        sub = self.get_object()
        sub.unsubscribe()
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def resubscribe(self, request, pk=None):
        sub = self.get_object()
        sub.subscribe()
        return Response({"ok": True})

    @action(detail=True, methods=["delete"])
    def erase(self, request, pk=None):
        # Or soft-delete/mark erased if you keep history
        sub = self.get_object()
        sub.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ---- Events (example uses Delivery by email) ----
    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        sub = self.get_object()
        email = sub.email or getattr(sub.user, "email", None)
        if not email:
            return Response([], status=200)

        # Minimal feed from Delivery; customize if you log more event types
        qs = Delivery.objects.filter(email__iexact=email, submission__newsletter=sub.newsletter).order_by("-timestamp")[:200]
        data = [
            {"event": d.status, "at": d.timestamp.isoformat(), "mailgun_id": d.mailgun_id}
            for d in qs
        ]
        return Response(data, status=200)


class DirectEmailViewSet(viewsets.GenericViewSet):

    queryset = DirectEmail.objects.select_related("article", "sender", "receiver")

    # create (no send)
    def create(self, request, *args, **kwargs):
        ser = DirectEmailCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        obj = ser.save()  # queued + rendered snapshot
        return Response(DirectEmailReadSerializer(obj).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["POST"])
    def send(self, request, pk=None):
        direct = self.get_object()
        # call the MODEL's send method
        direct.send()

        return Response(DirectEmailReadSerializer(direct).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["GET"], url_path="templates")
    def templates(self, request):
        # helper endpoint to populate the template dropdown
        qs = Article.objects.filter(is_template=True, template_type=Article.TEMPLATE_TYPE_EMAIL).only("id","title")
        return Response([{"id": a.id, "title": a.title} for a in qs])


def _parse_payload(request) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns (signature_dict, event_data_dict)

    Supports:
    - application/json with {"signature": {...}, "event-data": {...}}
    - form-encoded with fields: signature,timestamp,token and event-data (JSON)
    """
    content_type = (request.META.get("CONTENT_TYPE") or "").split(";")[0].strip()

    if content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8"))
            signature = payload.get("signature") or {}
            event_data = payload.get("event-data") or {}
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON payload")
    else:
        # Mailgun can send application/x-www-form-urlencoded
        signature = {
            "timestamp": request.POST.get("timestamp"),
            "token": request.POST.get("token"),
            "signature": request.POST.get("signature"),
        }
        ed = request.POST.get("event-data")
        if not ed:
            raise ValueError("Missing event-data")
        try:
            event_data = json.loads(ed)
        except json.JSONDecodeError:
            raise ValueError("Invalid event-data JSON")

    # Defensive defaults
    signature.setdefault("timestamp", "")
    signature.setdefault("token", "")
    signature.setdefault("signature", "")

    return signature, event_data


def _verify_mailgun_signature(signature: Dict[str, Any]) -> bool:
    """
    Mailgun signature: HMAC-SHA256 of timestamp + token using the webhook signing key.
    """
    key = getattr(settings, "MAILGUN_WEBHOOK_SIGNING_KEY", None)
    if not key:
        # Fail closed if no key configured
        return False

    ts = str(signature.get("timestamp", ""))
    token = str(signature.get("token", ""))
    sig = str(signature.get("signature", ""))

    if not (ts and token and sig):
        return False

    digest = hmac.new(
        key=key.encode("utf-8"),
        msg=f"{ts}{token}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    # constant-time compare
    return hmac.compare_digest(digest, sig)


def _epoch_to_dt(epoch) -> timezone.datetime:
    try:
        return timezone.datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    except Exception:
        return timezone.now()


def _safe_int(val):
    try:
        return int(val)
    except Exception:
        return None


@csrf_exempt
@require_POST
def mailgun_webhook(request):
    print(f"Received Mailgun webhook: {request.body}")
    try:
        signature, ed = _parse_payload(request)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    if not _verify_mailgun_signature(signature):
        return HttpResponseForbidden("Invalid signature")

    event = (ed.get("event") or "").lower()
    occurred_at = _epoch_to_dt(ed.get("timestamp"))
    provider_event_id = ed.get("id") or ""  # Mailgun's unique event id
    recipient = ed.get("recipient") or ed.get("envelope", {}).get("targets") or ""
    storage = ed.get("storage") or {}
    message = ed.get("message") or {}
    headers = message.get("headers") or {}
    provider_message_id = headers.get("message-id") or ed.get("message", {}).get("headers", {}).get("message-id")
    subject = headers.get("subject", "")

    # Delivery/Failure details
    ds = ed.get("delivery-status") or {}
    smtp_code = _safe_int(ds.get("code"))
    smtp_message = ds.get("message") or ""
    failure_severity = ds.get("severity") or ""
    failure_reason = ds.get("reason") or ds.get("description") or ""

    # Engagement details
    client_info = ed.get("client-info") or {}
    ip = ed.get("ip")
    user_agent = client_info.get("user-agent") or ed.get("user-agent")
    url = ed.get("url") or ""

    tags = ed.get("tags") or []
    campaigns = ed.get("campaigns") or []
    user_vars = ed.get("user-variables") or {}

    # Ensure we have a message id (primary key for tying events to Delivery)
    if not provider_message_id:
        # You can choose to 400 here; creating a placeholder is safer for ops.
        provider_message_id = f"unknown-{provider_event_id or timezone.now().timestamp()}"

    # Create delivery event + update rollups atomically
    try:
        with transaction.atomic():
            # Find or create the Delivery row created at send-time; or create a placeholder
            delivery, created = Delivery.objects.select_for_update().get_or_create(
                mailgun_id=provider_message_id,
                defaults={
                    "email": recipient or "",
                    "provider_storage_url": storage.get("url"),
                    "provider_message_size": _safe_int(storage.get("size")) or 0,
                    "tags": list(tags) if hasattr(Delivery, "tags") else [],
                    "campaigns": list(campaigns) if hasattr(Delivery, "campaigns") else [],
                    "user_variables": dict(user_vars) if hasattr(Delivery, "user_variables") else {},
                },
            )

            # Update recipient/metadata if we learned more
            changed = False
            if recipient and not delivery.email:
                delivery.email = recipient
                changed = True
            if storage.get("url") and getattr(delivery, "provider_storage_url", None) != storage.get("url"):
                delivery.provider_storage_url = storage.get("url")
                changed = True
            if storage.get("size") and (delivery.provider_message_size or 0) == 0:
                delivery.provider_message_size = _safe_int(storage.get("size")) or 0
                changed = True
            if hasattr(delivery, "tags") and tags:
                delivery.tags = sorted(set((delivery.tags or []) + tags))
                changed = True
            if hasattr(delivery, "campaigns") and campaigns:
                delivery.campaigns = sorted(set((delivery.campaigns or []) + campaigns))
                changed = True
            if hasattr(delivery, "user_variables") and user_vars:
                delivery.user_variables = {**(delivery.user_variables or {}), **user_vars}
                changed = True

            # Idempotent insert for the event
            try:
                DeliveryEvent.objects.create(
                    delivery=delivery,
                    provider_event_id=provider_event_id or f"{provider_message_id}:{event}:{occurred_at.timestamp()}",
                    event=event,
                    occurred_at=occurred_at,
                    recipient=recipient or delivery.email or "",
                    ip=ip,
                    user_agent=user_agent or "",
                    geo=ed.get("geolocation") or {},
                    url=url or "",
                    delivery_status=ds or {},
                    raw_payload=ed,
                )
            except IntegrityError:
                # Duplicate event (Mailgun retries or we already processed) -> OK
                pass

            # Roll up state on Delivery
            delivery.last_event = event[:20]
            delivery.last_event_at = occurred_at

            if event in ("accepted", "sending", "queued"):
                delivery.state = "sending"
                delivery.sent_at = delivery.sent_at or occurred_at
                delivery.queued_at = delivery.queued_at or occurred_at

            elif event == "delivered":
                delivery.state = "delivered"
                delivery.delivered_at = delivery.delivered_at or occurred_at

            elif event == "opened":
                delivery.open_count = (delivery.open_count or 0) + 1
                delivery.last_opened_at = occurred_at
                # escalate state if not already beyond
                if delivery.state not in ("clicked",):
                    delivery.state = "opened"

            elif event == "clicked":
                delivery.click_count = (delivery.click_count or 0) + 1
                delivery.last_clicked_at = occurred_at
                delivery.state = "clicked"

            elif event == "failed":
                delivery.state = "failed"
                delivery.failed_at = delivery.failed_at or occurred_at
                delivery.smtp_code = smtp_code
                delivery.smtp_message = smtp_message
                delivery.failure_severity = failure_severity
                delivery.failure_reason = failure_reason
                delivery.raw_delivery_status = ds or {}

            elif event == "complained":
                delivery.state = "complained"
                delivery.complained_at = delivery.complained_at or occurred_at

            elif event == "unsubscribed":
                delivery.state = "unsubscribed"
                delivery.unsubscribed_at = delivery.unsubscribed_at or occurred_at

            elif event == "rejected":
                delivery.state = "rejected"
                delivery.rejected_at = delivery.rejected_at or occurred_at

            elif event == "stored":
                delivery.state = "stored"
                delivery.stored_at = delivery.stored_at or occurred_at

            # Persist signature audit
            delivery.webhook_verified = True
            delivery.webhook_signature_ts = _epoch_to_dt(signature.get("timestamp"))
            delivery.webhook_signature_token = signature.get("token") or ""
            delivery.webhook_signature_sig = signature.get("signature") or ""

            delivery.save()

    except Exception as e:
        # Log e if you use logging; return 200 so Mailgun doesn't keep retrying forever
        # but you can 500 here if you'd like retries.
        print(f"Error processing Mailgun webhook: {e}")
        return JsonResponse({"status": "error", "detail": str(e)}, status=500)

    return JsonResponse({"status": "ok"})

#
# @csrf_exempt
# def mailgun_webhook(request):
#     print(f"Mailgun webhook received: {request.method} {request.body}")
#     if request.method == "POST":
#         data = json.loads(request.body)
#
#         if not verify_signature(data['signature']['timestamp'], data['signature']['token'], data['signature']['signature']):
#             return JsonResponse({"error": "Invalid signature"}, status=403)
#
#
#         mg_event_data = data.get("event-data", {})
#
#         message_id = mg_event_data["id"]
#
#         logger.info(f"Mailgun webhook received for message {message_id} with data {json.dumps(mg_event_data)}")
#
#         delivery = Delivery.objects.get(id=message_id)
#         # try:
#         #     logid = event_data['user-variables']['commslog_id']
#         #     log = CommsLog.objects.get(id=logid)
#         #
#         # except CommsLog.DoesNotExist:
#         #     try:
#         #         log = CommsLog.objects.get(message_id=message_id)
#         #     except CommsLog.DoesNotExist:
#         #         return JsonResponse({"message": f"Webhook received but commslog id {logid} not found"}, status=406)
#         # except:
#         #     return JsonResponse({"error": "Invalid request"}, status=406)
#
#         mg_event = mg_event_data.get("event")  # e.g., delivered, bounced
#         timestamp = mg_event_data.get("timestamp")
#
#         # log.message_id = message_id
#         # log.last_event = event
#         # log.status = event
#         # log.delivery_status = event_data.get("delivery-status", {})
#         # log.metadata = {**(log.metadata or {}), **event_data.get("flags", {})}
#         #
#         # if event == 'delivered':
#         #     log.delivered_at = make_aware(datetime.fromtimestamp(timestamp))
#         #
#         # log.save()
#
#     return JsonResponse({"message": f"Webhook received but message {message_id} not found"}, status=200)

class SubscribeMe(APIView):

    def get(self, request):
        '''get for general newsletter only - only works if email passed as query param'''
        newsletter = Newsletter.objects.get(slug=settings.NEWSLETTER_GENERAL_SLUG)

        newsletter.subscribe_from_request(request)

        # add to django messages framework
        messages.success(request, f"Subscribed to {newsletter} successfully")

        return Response(status=status.HTTP_200_OK)

    def post(self, request):
        '''get for general newsletter only'''
        newsletter = Newsletter.objects.get(slug=settings.NEWSLETTER_GENERAL_SLUG)

        newsletter.subscribe_from_request(request)

        # add to django messages framework
        messages.success(request, f"Subscribed to {newsletter} successfully")

        return Response(status=status.HTTP_200_OK)

class UnSubscribeMe(APIView):

    def get(self, request):

        newsletter = Newsletter.objects.get(slug=settings.NEWSLETTER_GENERAL_SLUG)

        newsletter.unsubscribe_from_request(request)

        # add to django messages framework
        messages.success(request, f"Unsubscribed from {newsletter} successfully")

        return Response(status=status.HTTP_200_OK)
