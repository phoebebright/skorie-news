import csv
import io
import json

from django.contrib import  messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sites import requests
from django.core import signing
from django.core.exceptions import ValidationError

from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction, IntegrityError
from django.db.models import Count, Q, Subquery, OuterRef, Exists, Value, CharField
from django.db.models.functions import Coalesce
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse, HttpResponseRedirect, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template import engines
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, RedirectView, DetailView
from django_users.tools.permission_mixins import UserCanAdministerMixin
from django.conf import settings
from news.models import Newsletter, Issue, Mailing, Subscription, Article, EventDispatch
from skorie.common.api import verify_signature

from skorie.common.mixins import GoNextMixin, GoNextTemplateMixin
from tools.permission_mixins import UserCanOrganiseEventMixin
from users.models import VerificationCode
from web.models import Event, CommsTemplate
from web.views import is_superuser
from .forms import NewsletterForm,  CSVImportForm, SubscriptionForm, \
    ArticleForm, ArticleQuickForm, DispatchForm, AttachmentForm, IssueForm, AttachmentFormSet, NewsletterDownloadForm

User = get_user_model()

from news.api import MANAGE_EMAIL_SALT, MANAGE_EMAIL_MAX_AGE

class MixinNewsletterNMessage(object):
    '''add news and message to context if available'''
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not 'news' in context or not 'message' in context:
            if hasattr(self, 'object') and hasattr(self.object, 'news'):
                context['news'] = self.object.newsletter
            if hasattr(self, 'object') and self.object and hasattr(self.object, 'message'):
                context['message'] = self.object.message
                context['news'] = self.object.message.newsletter

            elif 'message_pk' in kwargs:
                context['message'] = get_object_or_404(Issue, pk=kwargs['message_pk'])
                context['news'] = context['message'].newsletter
            elif 'message_pk' in self.kwargs:
                context['message'] = get_object_or_404(Issue, pk=self.kwargs['message_pk'])
                context['news'] = context['message'].newsletter
        return context

@method_decorator(never_cache, name='dispatch')
class NewsletterDashboardView(UserCanAdministerMixin, TemplateView):
    template_name = "news/admin/newsletter_dash.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Helper subqueries/filters
        active_qs = Subscription.objects.filter(
            newsletter=OuterRef("pk"), active=True)


        unsub_count = Subscription.objects.filter(
            newsletter=OuterRef("pk"),
            unsubscribed=True,
        ).values("news").annotate(c=Count("id")).values("c")

        suppressed_count = Subscription.objects.filter(
            newsletter=OuterRef("pk")
        ).filter(active=False).values("news").annotate(c=Count("id")).values("c")

        issues_count = Issue.objects.filter(
            newsletter=OuterRef("pk")
        ).values("news").annotate(c=Count("id")).values("c")

        last_issue = Issue.objects.filter(
            newsletter=OuterRef("pk")
        ).order_by("-created").values("created")[:1]

        pending_submissions_exists = Mailing.objects.filter(
            newsletter=OuterRef("pk"),
            status__in=[Mailing.Status.QUEUED, Mailing.Status.SENDING]
        )

        newsletters = (
            Newsletter.objects
            .annotate(
                subscribers_active=Subquery(
                    active_qs.values("news").annotate(c=Count("id")).values("c"),
                ),
                subscribers_unsub=Subquery(unsub_count),
                subscribers_suppressed=Subquery(suppressed_count),
                issues_total=Subquery(issues_count),
                last_issue_at=Subquery(last_issue),
                has_pending=Exists(pending_submissions_exists),
            )
            .order_by("-created")
        )

        # Backfill None to 0 in template; or here:
        for nl in newsletters:
            nl.subscribers_active = nl.subscribers_active or 0
            nl.subscribers_unsub = nl.subscribers_unsub or 0
            nl.subscribers_suppressed = nl.subscribers_suppressed or 0
            nl.issues_total = nl.issues_total or 0

        context.update({
            "now": now(),
            "newsletters": newsletters,
        })
        return context

#
# class NewsletterListView(UserCanAdministerMixin, GoNextMixin, ListView):
#     model = Newsletter
#     template_name = "news/admin/newsletter_list.html"
#
#     def get_queryset(self):
#         qs = (
#             Newsletter.objects.all()
#             .annotate(subscriber_count=Count("subscription"))
#             .order_by("title")
#         )
#         q = self.request.GET.get("q")
#         if q:
#             qs = qs.filter(title__icontains=q)
#         return qs


class NewsletterCreateView(UserCanAdministerMixin, GoNextMixin,CreateView):
    model = Newsletter
    form_class = NewsletterForm
    template_name = "news/admin/newsletter_form_create.html"
    success_url = reverse_lazy("news:news-home")

@method_decorator(never_cache, name='dispatch')
class NewsletterUpdateView(UserCanAdministerMixin, UpdateView):
    model = Newsletter
    form_class = NewsletterForm
    template_name = "news/admin/newsletter_form.html"
    success_url = reverse_lazy("news:news-home")


class NewsletterDeleteView(UserCanAdministerMixin, DeleteView):
    model = Newsletter
    template_name = "news/admin/newsletter_confirm_delete.html"
    success_url = reverse_lazy("news:news-home")
#
# @method_decorator(never_cache, name='dispatch')
# class MessageListView(UserCanAdministerMixin, ListView):
#     model = Issue
#     paginate_by = 20
#     template_name = "news/admin/message/../templates/news/admin/issues/message_list.html"
#
#     def get_queryset(self):
#         qs = Issue.objects.select_related("news").order_by("-created")
#         q = self.request.GET.get("q")
#         if q:
#             qs = qs.filter(subject__icontains=q)
#         return qs
#
#
# class MessageCreateView(UserCanAdministerMixin, CreateView):
#     model = Issue
#     form_class = MessageForm
#     template_name = "news/admin/issues/issue_form.html"
#     success_url = reverse_lazy("news:issue-list")
#
#     def get_form_kwargs(self):
#         """Return the keyword arguments for instantiating the form."""
#         kwargs = super().get_form_kwargs()
#         if 'newsletter_pk' in self.kwargs:
#             # If a newsletter_pk is provided, set it in the kwargs
#             kwargs['initial'] = kwargs.get('initial', {})
#             kwargs['initial']['news'] = self.kwargs['newsletter_pk']
#
#         return kwargs
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['news'] = Newsletter.objects.get(pk=self.kwargs['newsletter_pk'])
#         return context
#
# @method_decorator(never_cache, name='dispatch')
# class MessageUpdateView(UserCanAdministerMixin, UpdateView):
#     model = Issue
#     form_class = MessageForm
#     template_name = "news/admin/issues/issue_form.html"
#     article_formset_class = ArticleForm
#     attachment_formset_class = AttachmentForm
#     success_url = reverse_lazy("news:issue-list")
#
#
#     def get(self, request, *args, **kwargs):
#         obj = self.get_object()
#         form = self.form_class(instance=obj)
#         articles = self.article_formset_class(instance=obj, prefix="articles")
#         attachments = self.attachment_formset_class(instance=obj, prefix="files")
#         submission = obj.active_mailing
#         submission_status = submission.get_status_display() if submission else None
#         submissions = obj.submission_set.all().order_by('-publish_date')
#         return render(
#             request,
#             self.template_name,
#             {
#                 "form": form,
#                 "articles": articles,
#                 "attachments": attachments,
#                 "object": obj,
#                 "submission": submission,
#                 "submission_status": submission_status,
#                 "submissions": submissions,
#                 "message": obj,
#                 "news": obj.newsletter,
#             },
#         )
#
#     def post(self, request, *args, **kwargs):
#         obj = self.get_object()
#         form = self.form_class(request.POST, instance=obj)
#         articles = self.article_formset_class(request.POST, instance=obj, prefix="articles")
#         attachments = self.attachment_formset_class(
#             request.POST, request.FILES, instance=obj, prefix="files"
#         )
#
#         if form.is_valid() and articles.is_valid() and attachments.is_valid():
#             with transaction.atomic():
#                 msg = form.save()  # save parent first to get a PK
#                 articles.instance = msg
#                 attachments.instance = msg
#                 articles.save()
#                 attachments.save()
#
#             messages.success(
#                 request,
#                 "Message saved with {} article(s) and {} attachment(s).".format(
#                     articles.total_form_count() - len(articles.deleted_forms),
#                     attachments.total_form_count() - len(attachments.deleted_forms),
#                 ),
#             )
#             return redirect(self.success_url)
#
#         # fall-through: re-render with errors
#         return render(
#             request,
#             self.template_name,
#
#             {
#                 "form": form,
#                 "articles": articles,
#                 "attachments": attachments,
#                 "object": obj,
#
#                 "message": obj,
#                 "news": obj.newsletter,
#             },
#         )
#
#
# class MessageDeleteView(UserCanAdministerMixin, DeleteView):
#     model = Issue
#     template_name = "news/admin/message_confirm_delete.html"
#     success_url = reverse_lazy("news:issue-list")
#
# @method_decorator(never_cache, name='dispatch')
# class MessagePreviewView(UserCanAdministerMixin, View):
#     """Show HTML + text preview of a Message, with Queue button."""
#
#     template_name = "news/admin/message/message_preview.html"
#
#     def get(self, request, pk):
#         message = get_object_or_404(Issue, pk=pk)
#         return render(
#             request,
#             self.template_name,
#             {
#                 "message": message,
#             },
#         )



@method_decorator(never_cache, name='dispatch')
class SubmissionListView(UserCanAdministerMixin, ListView):
    model = Mailing
    paginate_by = 20
    template_name = "news/admin/submission_list.html"

    def get_queryset(self):
        return Mailing.objects.select_related("message", "news").order_by("-prepared")



@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
def issue_queue_submission(request: HttpRequest, pk: int) -> HttpResponse:
    """Create or reuse a Submission for a Message and set it queued.

    NOTE: django-news actually sends via the management command
    `submit_newsletter`. This view only creates the Submission and marks
    it QUEUED, so your scheduled job will send it.
    """
    msg = get_object_or_404(Issue, pk=pk)
    if not msg.newsletter_id:
        raise Http404("Message must be linked to a Newsletter before queueing.")

    submission, created = Mailing.objects.get_or_create(
        message=msg, newsletter=msg.newsletter
    )
    # Status constants vary across versions; using strings for portability
    submission.status = Mailing.STATUS.QUEUE if hasattr(Mailing, "STATUS") else "queued"
    submission.save()

    messages.success(
        request,
        "Submission queued. The management command will deliver it to all current subscribers.",
    )
    return redirect("news:submission-list")

class SubscriptionThanks(TemplateView):
    template_name = "news/user/subscription_thanks.html"

class SubscriberManageView(UserCanAdministerMixin, TemplateView):
    template_name = "news/admin/subscriptions_manage.html"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = kwargs["slug"]
        nl = get_object_or_404(Newsletter, slug=slug)

        q = (self.request.GET.get("q") or "").strip()
        status = (self.request.GET.get("status") or "active").lower()
        page = int(self.request.GET.get("page") or 1)

        subs = Subscription.objects.filter(newsletter=nl)

        if q:
            subs = subs.filter(
                Q(email__icontains=q) |
                Q(name__icontains=q) |
                Q(user__email__icontains=q) |
                Q(user__username__icontains=q)
            )

        if status == "active":
            subs = subs.active()
        elif status == "unsub":
            subs = subs.filter(unsubscribed=True)
        elif status == "suppressed":
            subs = subs.filter(active=False)

        # "all": no extra filter

        subs = subs.order_by("-created")
        paginator = Paginator(subs, self.paginate_by)
        page_obj = paginator.get_page(page)

        totals = {
            "active": Subscription.objects.filter(newsletter=nl).active().count(),
            "unsub": Subscription.objects.filter(newsletter=nl, unsubscribed=True).count(),
            "suppressed": Subscription.objects.filter(newsletter=nl).active().count(),
            "all": Subscription.objects.filter(newsletter=nl).count(),
        }

        context.update({
            "news": nl,
            "q": q,
            "status": status,
            "page_obj": page_obj,
            "totals": totals,
            "now": now(),
        })
        return context

    # keep POST here if you’re doing AJAX bulk actions to the same URL
    def post(self, request, slug):
        """
        Optional: handle bulk actions (unsubscribe/resubscribe/erase) or add-single.
        (Leave as-is from your existing implementation.)
        """
        # ... your existing POST logic ...
        return render(request, self.template_name, self.get_context_data(slug=slug))


@method_decorator(never_cache, name='dispatch')
class NewsletterSubscriptionsView(MixinNewsletterNMessage, UserCanAdministerMixin, View):
    """
    Admin page to manage subscriptions for a single news:
    - List (with search + paginate)
    - Add single subscriber
    - Bulk import CSV
    - Delete selected
    - Export CSV
    """
    template_name = "news/admin/subscriptions_manage.html"
    paginate_by = 100


    def get(self, request, newsletter_pk, *args, **kwargs):
        object = get_object_or_404(Newsletter, pk=newsletter_pk)

        context = {
            "news": object,
            "form_add": SubscriptionForm(),

        }
        return render(request, self.template_name, context)

    def post(self, request, newsletter_pk, *args, **kwargs):
        """
        Handle four actions via 'action' field:
        - add_one
        - import_csv
        - delete_selected
        - export_csv
        """
        nl = get_object_or_404(Newsletter, pk=newsletter_pk)
        action = kwargs.get('action', request.POST.get("action", None))

        if action == "add_one":
            return self._add_one(request, nl)
        elif action == "import_csv":
            return self._import_csv(request, nl)
        elif action == "delete_selected":
            return self._delete_selected(request, nl)
        elif action == "export_csv":
            return self._export_csv(nl, request)
        else:
            messages.error(request, "Unknown action.")
            return redirect(self._list_url(nl))

    def _list_url(self, nl):
        return reverse("news:subscriptions-manage", kwargs={"newsletter_pk": nl.pk})

    # -- Actions --

    def _add_one(self, request, nl):
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.newsletter = nl
            try:
                sub.save()
                messages.success(request, f"Added {sub.email}.")
            except IntegrityError:
                messages.info(request, f"{sub.email} is already subscribed.")
            else:
                sub.subscribe(user=request.user)
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f"{field}: {e}")
        return redirect(self._list_url(nl))

    def _import_csv(self, request, nl):
        form = CSVImportForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Please choose a valid CSV file.")
            return redirect(self._list_url(nl))

        f = form.cleaned_data["csv_file"]
        overwrite = form.cleaned_data["overwrite_names"]
        # Read as text
        data = f.read()
        try:
            text = data.decode("utf-8")
        except AttributeError:
            text = data  # already str (tests)

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        created = updated = skipped = 0

        # Detect header
        has_header = False
        if rows:
            header = [h.strip().lower() for h in rows[0]]
            if "email" in header:
                has_header = True

        iterable = rows[1:] if has_header else rows

        with transaction.atomic():
            for row in iterable:
                if not row:
                    continue
                # Support 1 or 2 columns: email[, name]
                email = (row[0] or "").strip()
                name = (row[1] or "").strip() if len(row) > 1 else ""
                if not email:
                    skipped += 1
                    continue
                sub, was_created = Subscription.objects.get_or_create(
                    newsletter=nl, email=email,
                    defaults={"name": name or ""},
                )
                if was_created:
                    created += 1
                else:
                    if overwrite and name:
                        sub.name = name
                        sub.save(update_fields=["name"])
                        updated += 1
                    else:
                        skipped += 1

        messages.success(
            request,
            f"Import complete: {created} added, {updated} updated, {skipped} skipped."
        )
        return redirect(self._list_url(nl))

    def _delete_selected(self, request, nl):
        ids = request.POST.getlist("selected")
        if not ids:
            messages.info(request, "No subscribers selected.")
            return redirect(self._list_url(nl))
        qs = Subscription.objects.filter(newsletter=nl, id__in=ids)
        count = qs.count()
        qs.delete()
        messages.success(request, f"Deleted {count} subscriber(s).")
        return redirect(self._list_url(nl))

    def _export_csv(self, nl, request):
        qs = Subscription.objects.filter(newsletter=nl).order_by("email")
        # Optional filter by search term
        q = (request.POST.get("q") or request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(email__icontains=q) | qs.filter(name__icontains=q)

        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{nl.slug}_subscribers.csv"'
        writer = csv.writer(resp)
        writer.writerow(["email", "name", "is_user"])
        for s in qs:
            email = s.user.email if s.user else s.email
            writer.writerow([email, getattr(s, "name", ""), "Y" if s.user else ""])
        return resp

class MySubscriptions(LoginRequiredMixin, ListView):
    model = Subscription
    template_name = "news/user/my_subscriptions.html"

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user).order_by("-created")

class UpdateMySubscription(LoginRequiredMixin, GoNextTemplateMixin, TemplateView):

    template_name = "news/user/my_subscription_form.html"


    def get_context_data(self, newsletter_pk):
        context = super().get_context_data()

        context['news'] = get_object_or_404(Newsletter, pk=newsletter_pk)
        try:
            context['subscription'] = Subscription.objects.get(user=self.request.user, newsletter=context['news'])
        except Subscription.DoesNotExist:
            raise Http404("No subscription found")
        return context

class SubscribeWithEmailRedirect(RedirectView):
    """
    Redirect to /news/<newsletter_pk>/subscribe?email=...&name=...&next=...

    This is a convenience view to allow email links like
    /news/subscribe/<newsletter_pk>/?email=...&name=...&next=...
    to redirect to the actual subscription handler.

    This allows cleaner URLs in emails, and avoids exposing the
    subscribe-with-email URL directly in templates.
    """

    permanent = False
    query_string = True
    pattern_name = "news:subscribe-with-email-only"

    def get_redirect_url(self, *args, **kwargs):
        nl = get_object_or_404(Newsletter, slug=settings.NEWSLETTER_GENERAL_SLUG)
        return super().get_redirect_url(newsletter_slug=nl.slug)

@method_decorator(never_cache, name='dispatch')
class SubscribeWithEmailUnconfirmed(View):
    '''this is the normal route that includes seding an email for confirmation'''
    confirm_immediately = False
    confirm_message = "Confirmed I want to continue to receive emailed news."
    confirm_source = "email-link"

    def get(self, request, newsletter_slug ):

        #TODO: if the email matches the logged in user, then redirect to manage subscriptions
        raw_email = (request.GET.get("email") or "").strip().replace(' ','+')
        name = (request.GET.get("name") or "").strip()
        next_url = reverse("news:manage-subs")

        if not newsletter_slug or not raw_email:
            messages.error(request, "Newsletter and email are required.")
            return redirect(next_url)

        try:
            validate_email(raw_email)
        except ValidationError:
            messages.error(request, f"Please enter a valid email address. got {raw_email}")
            return redirect(next_url)

        email = raw_email.lower()
        newsletter = get_object_or_404(Newsletter, slug=newsletter_slug)

        request.session['managed_email'] = email

        # Is there a user account with this email?
        user = User.objects.filter(email__iexact=email).first()

        if user:
            # Prefer an existing user-linked subscription
            request.session['account_username'] = user.username  # used in manage subscriptions when not logged in
        else:
            request.session['account_username'] = None

        sub = newsletter.subscribe_from_request(request)

        if sub.subscribed:
            msg = f"You’re already subscribed to {newsletter}"
        elif sub.unsubscribed:
            msg = f"You had previously unsubscribed from {newsletter}. Please manage your subscriptions to resubscribe."



        messages.success(request, msg)
        return redirect(next_url)

class SubscribeWithEmail(SubscribeWithEmailUnconfirmed):
    """
    GET /news/<newsletter_pk>/subscribe?email=<addr>&name=<optional>&next=<url>

    Behavior:
      - If a User with this email exists: ensure a user-linked Subscription.
      - Else: ensure an email-only Subscription.
      - If an email-only record exists and a user is found now, attach the user and clear email.
    - Idempotent: never creates duplicates.
      - If confirm_immediately=True, records consent and subscribes.
    """

    confirm_immediately = True  # set False if you want to keep pending
    confirm_message = "Confirmed from link from legacy icontact email."
    confirm_source = "icontact-email-link"

class MessageArticlesView(MixinNewsletterNMessage, ListView):
    template_name = "news/message/message_articles.html"
    context_object_name = "articles"


    def get_queryset(self):
        self.message = get_object_or_404(Issue, pk=self.kwargs["message_pk"])
        return self.message.articles.order_by("sortorder")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["message"] = self.message
        return context
#
# class ArticleCreateView(MixinNewsletterNMessage, CreateView):
#     model = Article
#     form_class = ArticleForm
#     template_name = "news/message/article_form.html"
#
#     def form_valid(self, form):
#         message = get_object_or_404(Message, pk=self.kwargs["message_pk"])
#         form.instance.post = message
#         return super().form_valid(form)
#
#     def get_success_url(self):
#         return reverse_lazy("news:message-articles", args=[self.kwargs["message_pk"]])
#
# class ArticleUpdateView(MixinNewsletterNMessage, UpdateView):
#     model = Article
#     form_class = ArticleForm
#     template_name = "news/message/article_form.html"
#
#     def get_success_url(self):
#         return reverse_lazy("news:message-articles", args=[self.object.post.pk])
#
# class ArticleDeleteView(MixinNewsletterNMessage,DeleteView):
#     model = Article
#     template_name = "news/message/article_confirm_delete.html"
#
#     def get_success_url(self):
#         return reverse_lazy("news:message-articles", args=[self.object.post.pk])
#
#
#
#

class ArticleListView(ListView):
    model = Article
    template_name = "news/admin/article/article_list.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        return Article.objects.order_by("-created")

class ArticleEditView(UpdateView):
    model = Article
    form_class = ArticleForm
    template_name = "news/admin/article/article_edit.html"

    def get_object(self, queryset=None):
        if "pk" in self.kwargs:
            return super().get_object(queryset)
        return None  # new article

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.form_class(instance=self.object)
        formset = AttachmentFormSet(instance=self.object)
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.form_class(request.POST, request.FILES, instance=self.object)
        formset = AttachmentFormSet(request.POST, request.FILES, instance=self.object)
        if form.is_valid() and formset.is_valid():
            article = form.save()
            formset.instance = article
            formset.save()
            messages.success(request, "Article saved.")
            return redirect(reverse("news:article-list"))
        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class EventSendView(UserCanOrganiseEventMixin, View):
    template_name = "news/message/event_send.html"

    def get(self, request, event_ref):
        dispatch = EventDispatch(event=self.event, creator=request.user)
        # forms
        article_form = ArticleQuickForm()
        dispatch_form = DispatchForm(instance=dispatch)
        # library: templates first, then recent
        library = Article.objects.all().order_by("-is_template", "-updated")
        return render(request, self.template_name, {
            "event": self.event,
            "article_form": article_form,
            "dispatch_form": dispatch_form,
            "library": library,
        })

    def post(self, request, event_ref):

        action = request.POST.get("action")  # "send_test" or "send_now"
        use_library_id = request.POST.get("article_id")  # if picking from library
        article = None

        if use_library_id:
            article = get_object_or_404(Article, pk=use_library_id)
            article_form = ArticleQuickForm(instance=article)  # read-only in UI, but we won’t save here
        else:
            article_form = ArticleQuickForm(request.POST, request.FILES)
            if article_form.is_valid():
                article = article_form.save()
            else:
                dispatch_form = DispatchForm()
                library = Article.objects.all().order_by("-is_template", "-updated")
                return render(request, self.template_name, {
                    "event": self.event,
                    "article_form": article_form,
                    "dispatch_form": dispatch_form,
                    "library": library,
                })

        dispatch = EventDispatch(event=self.event, article=article, creator=request.user)
        dispatch_form = DispatchForm(request.POST, instance=dispatch)
        if not dispatch_form.is_valid():
            library = Article.objects.all().order_by("-is_template", "-updated")
            return render(request, self.template_name, {
                "event": self.event,
                "article_form": article_form,
                "dispatch_form": dispatch_form,
                "library": library,
            })

        dispatch = dispatch_form.save(commit=False)

        # Send Test
        if action == "send_test":
            test_email = (request.POST.get("test_email") or "").strip().lower()
            try:
                validate_email(test_email)
            except ValidationError:
                messages.error(request, "Please enter a valid test email.")
                return redirect(request.path)

            # Mailgun single send
            url = f"https://api.mailgun.net/v3/{settings.MAILGUN_DOMAIN}/messages"
            auth = ("api", settings.MAILGUN_API_KEY)
            data = {
                "from": getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
                "to": [test_email],
                "subject": f"[TEST] {article.title}",
                "html": article.text or "",
                "text": "",
            }
            r = requests.post(url, auth=auth, data=data)
            try:
                r.raise_for_status()
                messages.success(request, f"Sent test to {test_email}.")
            except Exception:
                messages.error(request, f"Mailgun error: {r.text[:400]}")
            return redirect(request.path)

        # Send Now
        try:
            dispatch.send_now(user_is_admin=request.user.is_staff)
            messages.success(request, "Update sent.")
        except Exception as e:
            messages.error(request, str(e))

        return redirect(reverse("news:event-send", args=[self.event.ref]))



class IssueListView(UserCanAdministerMixin, TemplateView):
    template_name = "news/admin/issues/issue_list.html"
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nl = get_object_or_404(Newsletter, id=kwargs['newsletter_pk'])


        # Subquery: latest submission status per issue
        latest_sub = Mailing.objects.filter(issue=OuterRef("pk")).order_by("-created", "-pk")
        latest_status = Subquery(latest_sub.values("status")[:1])

        issues = (
            Issue.objects
            .filter(newsletter=nl)
            .annotate(latest_status=Coalesce(latest_status, Value("", output_field=CharField())))
            .select_related("news")
            .order_by("-created")
        )




        # quick counts
        counts = {
            "all": Issue.objects.filter(newsletter=nl).count(),
            "queued": Issue.objects.filter(newsletter=nl, submissions__status=Mailing.Status.QUEUED).distinct().count(),
            "sending": Issue.objects.filter(newsletter=nl, submissions__status=Mailing.Status.SENDING).distinct().count(),
            "sent": Issue.objects.filter(newsletter=nl, submissions__status=Mailing.Status.SENT).distinct().count(),
            "draft": Issue.objects.filter(newsletter=nl).exclude(submissions__isnull=False).count(),
        }

        context.update({
            "news": nl,
            "issues": issues,
            "counts": counts,
        })
        return context

class IssueCreateView(UserCanAdministerMixin, TemplateView):
    """
    Step 1: choose news + title
    Step 2 (on same page): pick/add articles, order, mark appear_in_blog
    """
    template_name = "news/admin/issues/issue_form.html"

    def get(self, request, newsletter_pk):
        nl = get_object_or_404(Newsletter, id=newsletter_pk)
        form = IssueForm(initial={"news": nl})
        # “library”: templates first, then recent
        library = Article.objects.all().order_by("-is_template", "-updated")[:50]
        return render(request, self.template_name, {
            "news": nl,
            "form": form,
            "issue": None,
            "library": library,
            "articles": [],  # none yet
        })

    def post(self, request, newsletter_pk):
        nl = get_object_or_404(Newsletter, id=newsletter_pk)
        form = IssueForm(request.POST)
        if not form.is_valid():
            library = Article.objects.all().order_by("-is_template", "-updated")[:50]
            return render(request, self.template_name, {
                "news": nl, "form": form, "issue": None, "library": library, "articles": [],
            })
        issue = form.save()
        messages.success(request, "Issue created. Add articles below, then Queue or Publish.")
        return redirect(reverse("news:issue-edit", args=[issue.pk]))



@method_decorator(never_cache, name='dispatch')
class IssueEditView(UserCanAdministerMixin, UpdateView):
        """
        Edit issue details + manage article list.
        """
        model = Issue
        form_class = IssueForm
        template_name = "news/admin/issues/issue_form.html"
        pk_url_kwarg = "pk"

        def get_queryset(self):
            # keep news handy
            return Issue.objects.select_related("news")

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            issue = self.object

            # article library for quick add
            context["library"] = (
                Article.objects.all().order_by("-is_template", "-updated")[:50]
            )

            # current ordered articles
            context["articles"] = (
                issue.issue_articles.select_related("article").order_by("position", "id")
            )

            context["news"] = issue.newsletter
            context["submission"] = issue.active_mailing if issue else None
            return context

        def form_valid(self, form):
            self.object = form.save()
            messages.success(self.request, "Issue updated.")
            return super().form_valid(form)

        def get_success_url(self):
            # stay on the same page after save
            return reverse("news:issue-edit", args=[self.object.pk])
    #
    # def get(self, request, pk):
    #     issue = get_object_or_404(Issue, pk=pk)
    #     form = IssueForm(instance=issue)
    #     library = Article.objects.all().order_by("-is_template", "-updated")[:50]
    #     # current ordered articles
    #     links = issue.issue_articles.select_related("article").order_by("position", "id")
    #     return render(request, self.template_name, {
    #         "news": issue.news,
    #         "form": form,
    #         "issue": issue,
    #         "library": library,
    #         "articles": links,
    #         "submission": issue.active_mailing if issue else None,
    #     })
    #
    # def post(self, request, pk):
    #     # update basics (title/news)
    #     issue = get_object_or_404(Issue, pk=pk)
    #     form = IssueForm(request.POST, instance=issue)
    #     if form.is_valid():
    #         form.save()
    #         messages.success(request, "Issue updated.")
    #         return redirect(reverse("news:issue-edit", args=[issue.pk]))
    #     library = Article.objects.all().order_by("-is_template", "-updated")[:50]
    #     links = issue.issue_articles.select_related("article").order_by("position", "id")
    #     return render(request, self.template_name, {
    #         "news": issue.news, "form": form, "issue": issue, "library": library, "articles": links,
    #         "submission": issue.active_mailing,
    #     })

class IssuePreviewView(DetailView):
    model = Issue
    template_name = "news/admin/issues/issue_preview.html"
    context_object_name = "issue"

    def get_queryset(self):
        return super().get_queryset().select_related("news").prefetch_related("issue_articles__article")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["articles"] = self.object.ordered_articles()
        return context

class ClaimEmailManageLinkView(TemplateView):
    template_name = "news/public/manage_claimed.html"  # optional informational page

    def dispatch(self, request, *args, **kwargs):
        token = kwargs["token"]
        try:
            email = signing.TimestampSigner(salt=MANAGE_EMAIL_SALT).unsign(token, max_age=MANAGE_EMAIL_MAX_AGE)
        except signing.BadSignature:
            messages.error(request, "Invalid or expired link.")
            return redirect("news:manage-subs")

        request.session["managed_email"] = email
        messages.success(request, f"You can now manage subscriptions for {email}.")
        return redirect("news:manage-subs")


# class ManageSubscriptionsView(TemplateView):
#     """
#     Single page:
#      - If authenticated: show/manage user-linked subs.
#      - Else: show login link AND 'email me a link' form.
#      - If session has managed_email from magic link: show/manage that email's subs.
#     """
#     template_name = "news/public/manage_subscriptions.html"


class ManageSubscriptionsView(TemplateView):
    """
    Shows:
      - For authenticated users: list of their user-linked subscriptions with toggle buttons
      - For guests: a form to request an unsubscribe email for email-only subscriptions
    Also the landing page after subscribe/unsubscribe (use messages framework).
    """
    template_name = "news/user/manage_subscriptions.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['managed_email'] = self.request.session.get('managed_email', None)
        context['account_username'] = self.request.session.get('account_username', None)

        return context


class UnsubscribeView(TemplateView):
    """
    GET /news/unsubscribe/confirm/<pk>/<code>/
    Confirms the email-only unsubscribe immediately and shows a friendly page.
    """
    template_name = "news/user/unsubscribe_confirmed.html"

    def dispatch(self, request, *args, **kwargs):
        sub = get_object_or_404(Subscription, pk=kwargs["pk"], activation_code=kwargs["code"])
        # Only for email-only subs (guests). For user-linked subs, require login/manage page.
        if sub.user_id is not None:
            messages.info(request, "Please log in to manage your subscriptions.")
            return redirect("news:manage-subs")
        sub.unsubscribe()
        self.subscription = sub
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["subscription"] = self.subscription
        return context

class ConfirmSubscribeView(TemplateView):
    template_name = "news/user/subscribe_confirmed.html"

    def dispatch(self, request, *args, **kwargs):
        sub = get_object_or_404(
            Subscription, pk=kwargs["pk"], activation_code=kwargs["code"]
        )

        consent = {
            "source": "confirmation email",
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
            "ip_address": request.META.get("REMOTE_ADDR", ""),
        }

        # Only email-only (guest) flow enforced; user-linked can use manage page
        sub.record_consent(**consent)
        self.subscription = sub  # to pick up from context
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["subscription"] = self.subscription
        return context


@method_decorator(never_cache, name='dispatch')
class SendFromTemplateView(UserCanAdministerMixin, TemplateView):
    template_name = "news/admin/email/send_email_with_template.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = User.objects.get(id=kwargs['pk'])
        context["target_user"] = user
        #context['templates'] = Article.objects.filter(is_template=True, template_type=Article.TEMPLATE_TYPE_EMAIL).order_by("title")
        context['templates'] = CommsTemplate.objects.filter(is_template=True, template_type=Article.TEMPLATE_TYPE_EMAIL).order_by("title")


        # if a template is selected, prefill with recipient details
        selected_template = None
        if "template_id" in kwargs:
            selected_template = get_object_or_404(Article, id=kwargs["template_id"])
        context["selected_template"] = selected_template

        if selected_template:
            # Build a rich context you can expand freely
            full_context = {
                # common objects
                "request": self.request,
                "user": user,  # recipient
                "recipient": user,  # alias if you prefer
                "sender": self.request.user,
                "site_url": settings.SITE_URL,
                # add any other objects you want available to templates
            }

            # we don't want this here but needs must
            verification_code = VerificationCode.objects.filter(user=user, expires_at__lte=timezone.now()).order_by('-created_at').first()
            if verification_code:
                full_context['verification_code'] = verification_code

            # Use Django template engine to render DB strings
            dj = engines["django"]
            subject_tpl = dj.from_string(selected_template.title or "")
            body_text_tpl = dj.from_string(selected_template.body_text or "")

            context["prefilled_subject"] = subject_tpl.render(full_context, request=self.request)
            context["prefilled_body_text"] = body_text_tpl.render(full_context, request=self.request)

        return context



class AdminNewsletterDownloadView(UserCanAdministerMixin, TemplateView):
    template_name = "news/admin/subscriber_downloads.html"

    def dispatch(self, request, *args, **kwargs):
        # Example guard; replace with your UserCanAdministerMixin if you have it
        if not request.user.is_authenticated or not request.user.is_staff:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Admins only.")
        return super().dispatch(request, *args, **kwargs)

    def get_newsletter(self):
        return get_object_or_404(Newsletter, id=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        newsletter = self.get_newsletter()
        form = NewsletterDownloadForm(request.GET or None)

        # If the form is valid AND download=1 is present → return file
        if form.is_valid() and request.GET.get("download") == "1":
            scope = form.cleaned_data["scope"]
            fmt = form.cleaned_data["fmt"]
            return self._build_download_response(newsletter, scope, fmt)

        # Otherwise render the page
        return render(request, self.template_name, {"news": newsletter, "form": form})

    # ---------- helpers ----------

    def _qs_for_scope(self, newsletter, scope):
        base = Subscription.objects.filter(newsletter=newsletter).select_related("user")
        if scope == "subscribed":
            return base.active()
        if scope == "unsubscribed":
            return base.inactive()
        return base

    def _build_download_response(self, newsletter, scope, fmt):
        qs = self._qs_for_scope(newsletter, scope)

        # Filenames like: general_subscribed_2025-09-28.csv
        today = timezone.now().date().isoformat()
        scope_part = scope
        if fmt.startswith("csv"):
            filename = f"{newsletter.slug}_{scope_part}_{fmt}_{today}.csv"
            content = self._render_csv(qs, fmt)
            resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
        else:
            filename = f"{newsletter.slug}_{scope_part}_{today}.txt"
            content = self._render_list(qs, fmt)
            resp = HttpResponse(content, content_type="text/plain; charset=utf-8")

        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    def _render_csv(self, qs, fmt):
        # Build CSV manually; lightweight and fast


        out = io.StringIO()
        writer = csv.writer(out)

        if fmt == "csv_all":
            headers = [
                "email", "name",
                "subscribed", "subscribe_date",
                "unsubscribed", "unsubscribe_date",
                "email_opt_in",
                "bounced", "bounced_at", "bounce_reason",
                "complained", "complained_at", "complaint_reason",
                "consent_at", "lawful_basis",
                "gdpr_erased_at",

            ]
            writer.writerow(headers)
            for s in qs:
                writer.writerow([
                    s.email or "",
                    s.user.formal_name if s.user else s.name or "",
                    s.subscribed, _d(s.subscribe_date),
                    s.unsubscribed, _d(s.unsubscribe_date),
                    s.email_opt_in,
                    s.bounced, _d(s.bounced_at), (s.bounce_reason or "").replace("\n", " ").strip(),
                    s.complained, _d(s.complained_at), (s.complaint_reason or "").replace("\n", " ").strip(),
                    _d(s.consent_at), s.lawful_basis,
                    _d(s.gdpr_erased_at),

                ])
        else:
            # csv_dates
            writer.writerow(["email", "name", "subscribe_date", "unsubscribe_date"])
            for s in qs:

                writer.writerow([
                    s.email,
                    s.user.formal_name if s.user else s.name or "",
                    _d(s.subscribe_date),
                    _d(s.unsubscribe_date),
                ])

        return out.getvalue()

    def _render_list(self, qs, fmt):
        # Two simple text formats
        if fmt == "list_email_name":
            lines = []
            for s in qs:
                name = s.user.formal_name if s.user else s.name or ""

                lines.append(f"{s.email or ''}, {name}")
            return "\n".join(lines) + "\n"
        else:
            # list_emails
            return "\n".join([(s.email or "") for s in qs]) + ","


def _d(dt):
    """Helper: ISO date from datetime or blank."""
    if not dt:
        return ""
    return dt.date().isoformat()

@user_passes_test(is_superuser)
def fix_subscribers(request):
    newsletter = Newsletter.objects.get(slug='general')
    for item in User.objects.filter(is_active=True):
        if item.unsubscribed:
           Subscription.admin_unsubscribe(newsletter, item.email, item.formal_name, item, consent={'consent_text': "unsubscribe copied from user table 28/9/25"}, user=request.user)
        elif item.subscribed:
            Subscription.admin_subscribe(newsletter, item.email, item.formal_name, item, consent={'consent_text': "subscribe copied from user table 28/9/25"}, user=request.user)

    return HttpResponse("Done")
