from django import forms
from django.http import HttpResponseBadRequest, JsonResponse
from django.utils.text import slugify
from tinymce.widgets import TinyMCE
import secrets, imghdr
from pathlib import Path
from skorie_news.models import Issue, Newsletter, Article, Attachment, Subscription, EventDispatch, IssueArticle
from django.forms import inlineformset_factory
from django.conf import settings


class NewsletterForm(forms.ModelForm):
    class Meta:
        model = Newsletter
        fields = ['title','visible','send_html']

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Apply defaults for hidden fields
        if not instance.slug and instance.title:
            instance.slug = slugify(instance.title)

        if not instance.email:
            instance.email = settings.NEWSLETTER_FROM_EMAIL

        if not instance.sender:
            instance.sender = settings.NEWSLETTER_SENDER

        if commit:
            instance.save()
            self.save_m2m()

        return instance




class IssueForm(forms.ModelForm):
    class Meta:
        model = Issue
        fields = ["title", "newsletter"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Issue title"}),
            "newsletter": forms.Select(attrs={"class": "form-select"}),
        }

class ArticleQuickForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "body_html", "image", "image_position", "url", "is_template"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "body_html": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "url": forms.URLInput(attrs={"class": "form-control"}),
            "image_position": forms.Select(attrs={"class": "form-select"}),
        }
class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "body_html", "image", "image_position", "is_template"]
        widgets = {
            "body_html": TinyMCE(attrs={"cols": 80, "rows": 20}),
        }



class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["name", "file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # file inputs don’t use form-control in BS5; add form-control if you prefer
        self.fields["file"].widget.attrs.setdefault("class", "form-control")

AttachmentFormSet = forms.inlineformset_factory(
    Article, Attachment, form=AttachmentForm, extra=1, can_delete=True
)

class DispatchForm(forms.ModelForm):
    """Choose channels for this dispatch."""
    class Meta:
        model = EventDispatch
        fields = [
            "to_email_competitors",
            "to_email_team",
            "to_event_news",
            "to_bluesky",
            "to_facebook",
            "to_whatsapp",
        ]



IssueArticleFormSet = inlineformset_factory(
    parent_model=Issue,
    model=IssueArticle,
    fields=["article", "position", "appear_in_blog"],
    extra=1,
    can_delete=True,
)


class SubscriptionForm(forms.ModelForm):
    """Add a single subscriber to a specific newsletter."""
    class Meta:
        model = Subscription
        fields = ["email", "name"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@example.com"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional name"}),
        }


class CSVImportForm(forms.Form):
    """Import many subscribers (email,name) CSV."""
    csv_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        help_text="CSV with headers email,name OR two columns in that order."
    )
    overwrite_names = forms.BooleanField(
        required=False,
        initial=False,
        help_text="If checked, update existing subscribers' names when provided."
    )

class NewsletterDownloadForm(forms.Form):
    SCOPE_CHOICES = [
        ("all", "All"),
        ("subscribed", "Subscribed"),
        ("unsubscribed", "Unsubscribed"),
    ]
    FORMAT_CHOICES = [
        ("csv_all", "CSV (all fields)"),
        ("csv_dates", "CSV (email, name, subscribe/unsubscribe dates)"),
        ("list_email_name", "List: email, name"),
        ("list_emails", "List: emails only"),
    ]

    scope = forms.ChoiceField(choices=SCOPE_CHOICES, initial="all", widget=forms.RadioSelect)
    fmt = forms.ChoiceField(choices=FORMAT_CHOICES, initial="csv_dates", widget=forms.RadioSelect)


# this is the log type news related to an event
class NewsEventFormBase(forms.ModelForm):
    datetime_attributes = {'type': 'datetime-local', 'class': 'date_picker'}
    publish_start = forms.DateTimeField(widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs=datetime_attributes),
                                     required=False,
                                     help_text=_("News is publicly available from this date"))
    publish_end = forms.DateTimeField(widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs=datetime_attributes), required=False, help_text=_("News is publicly available until this date"))
    class Meta:
        model = Newsletter
        fields = [ "competition","entry",  "summary", "body", "public", "for_organisers", "for_staff", "url",
        "publish_start", "publish_end"]

class NewsForm(forms.ModelForm):


    class Meta:
        model = Newsletter
        fields = [  "summary", "body", "public", "for_organisers", "for_staff", "url",
        "publish_start", "publish_end"]
