import json
import logging
from datetime import datetime

import requests
from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q, Prefetch
from django.shortcuts import redirect
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from django.utils.module_loading import import_string
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, TemplateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect, Http404
from django.utils import timezone
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from django_users.forms import ProfileForm, SkorieUserCreationForm
from django_users.tools.permission_mixins import UserCanAdministerMixin

from django_users.views import AddUser as AddUserBase

from django_users.helpdesk import CreateTicketView, TicketDetailView

from skorie_news.tools.permission_mixins import RequiresEventMixin
from users.forms import  SubscribeForm
from users.models import  Role, UserContact
from web.models import Competitor, Entry


logger = logging.getLogger('django')

ModelRoles = import_string(settings.MODEL_ROLES_PATH)
Disciplines = import_string(settings.DISCIPLINES_PATH)

User = get_user_model()

class InviteUser2Event(RequiresEventMixin, AddUserBase):

    template_name = 'admin/users/invite_user_2_event.html'

    def get_form_class(self):
        return SkorieUserCreationForm

    def get_success_url(self):
        return HttpResponseRedirect("/")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['role'] = self.request.GET.get('role', None)
        return kwargs

    # def get_context_data(self, **kwargs):
    #     context = super().get_context_data(**kwargs)
    #     context['event'] = self.event
    #     return context

    # def post(self, request, *args, **kwargs):
    #     form = self.get_form()
    #     if form.is_valid():
    #         return self.form_valid(form)
    #     else:
    #         return self.form_invalid(form)

class HelpView(TemplateView):
    template_name = "help.html"

# class HelpView(CreateTicketView):
#     model = HelpDeskTicket
#     form_class = SupportTicketForm
#
#     def get_template_names(self):
#         if self.request.user.is_administrator:
#             return ["django_users/helpdesk/create_ticket_admin.html",]
#         else:
#             return ["usdjango_usersers/helpdesk/create_ticket_user.html", ]


# class SendNewsletters(View):
#     """View to send newsletters to all users."""
#     def get(self, request, *args, **kwargs):
#         NewsletterSubmission.submit_queue()
#         messages.success(request, "Newsletters sent successfully.")
#         return redirect(reverse('users:manage_users'))  # Redirect to a suitable page after sending newsletters


# previously SubscirbeView
class TellUsAbout(LoginRequiredMixin, FormView):
    template_name = "django_users/subscribe.html"
    form_class = SubscribeForm
    success_url = '/'

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_context_data(self):
        context = super().get_context_data()
        if settings.USE_NEWSLETTER:
            Newsletter = apps.get_model('skorie_news', 'Newsletter')
            context['subcribed2newsletter'] = Newsletter.is_subscribed_to_newsletter(self.request.user)

        return context

    def form_valid(self, form):
        UserContact = apps.get_model('users.UserContact')

        # only available for signed in user
        user = self.request.user

        # extra fields
        user.country = form.cleaned_data['country']
        # user.mobile = form.cleaned_data['mobile']
        # user.whatsapp = form.cleaned_data['whatsapp']
        # user.city = form.cleaned_data['city']
        user.save()

        # this will set status to at least Confirmed
        user.update_subscribed(form.cleaned_data['subscribe'])

        # add contact note
        notify = getattr(settings, "NOTIFY_NEW_USER_EMAILS", False)
        UserContact.add(user=user, method="Subscribe & Interest Form", notes=json.dumps(form.cleaned_data),
                            data=form.cleaned_data, send_mail=notify)

        return super().form_valid(form)

class SubscriptionDataFrameView(TemplateView):
    template_name = 'django_users/admin/subscribe_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get filtered queryset
        queryset = self.get_filtered_queryset()

        # Create DataFrame from the data
        all_attributes = set()

        # First pass: collect all unique attributes from the JSONField
        for contact in queryset:
            if contact.attributes and isinstance(contact.attributes, dict):
                all_attributes.update(contact.attributes.keys())

        # remove email and city from attributes
        all_attributes.discard('email')
        all_attributes.discard('city')
        all_attributes.discard('mobile')

        context.update({
            'records': queryset,
            'attribute_columns': list(all_attributes),

        })

        return context

    def get_filtered_queryset(self):
        """Get filtered queryset based on request parameters"""
        # Base filter for subscription/interest/form related contacts
        queryset = UserContact.objects.filter(method__icontains='subscribe').select_related('user')

        # Apply filters from request
        method_filter = self.request.GET.get('method')
        site_filter = self.request.GET.get('site')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')

        if method_filter:
            queryset = queryset.filter(method=method_filter)

        if site_filter:
            queryset = queryset.filter(site=site_filter)

        if date_from:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d').date()

            except ValueError:
                # default to last 6 months
                from_date = timezone.now().date() - timezone.timedelta(days=180)

            queryset = queryset.filter(contact_date__date__gte=from_date)

        if date_to:
            try:
                to_date = datetime.strptime(date_to, '%Y-%m-%d').date()

            except ValueError:
                # default to last 6 months
                to_date = timezone.now().date() - timezone.timedelta(days=180)
            queryset = queryset.filter(contact_date__date__lte=to_date)
        return queryset.order_by('-contact_date')



    def normalize_value(self, value):
        """Normalize values for consistent display"""
        if value is None or value == '':
            return ''

        # Handle boolean values directly from JSONField
        if isinstance(value, bool):
            return value

        # Handle string representations of booleans
        if isinstance(value, str):
            lower_val = value.lower().strip()
            if lower_val in ['true', '1', 'yes', 'on', 'checked']:
                return True
            elif lower_val in ['false', '0', 'no', 'off', 'unchecked']:
                return False

        # Handle numeric values
        if isinstance(value, (int, float)):
            if value in [0, 1]:
                return bool(value)
            return value

        return str(value)

    def get_filter_options(self):
        """Get available filter options"""
        base_queryset = UserContact.objects.filter(
            Q(method__icontains='subscribe') |
            Q(method__icontains='interest') |
            Q(method__icontains='form') |
            Q(method__icontains='newsletter')
        )

        return {
            'methods': list(base_queryset.values_list('method', flat=True).distinct().order_by('method')),
            'sites': list(base_queryset.values_list('site', flat=True).distinct().order_by('site')),
        }



class RoleBrowse(UserCanAdministerMixin, ListView):
    '''browse roles - excludes competitors'''
    template_name = "admin/role_browser.html"
    model = Role

    def get_queryset(self):
        return Role.objects.exclude(role_type__in = [ModelRoles.ROLE_COMPETITOR, ModelRoles.ROLE_DEFAULT])
