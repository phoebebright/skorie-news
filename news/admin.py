# news/admin.py
from django.contrib import admin, messages
from django.db.models import Count
from django import forms
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from tinymce.widgets import TinyMCE

from .models import Attachment, Article, Newsletter, Issue, Mailing


# ---------- Helpers ----------

def _admin_link(label, url_name, *args, **kwargs):
    try:
        url = reverse(url_name, args=args, kwargs=kwargs)
        return format_html('<a class="button" href="{}">{}</a>', url, label)
    except Exception:
        return ""


# ---------- Inlines ----------
#
# class AttachmentInline(admin.TabularInline):
#     """Only if you still have Attachment(message=FK)."""
#     model = Attachment
#     extra = 0
#     fields = ("file", "mimetype")
#     verbose_name = "Attachment"
#     verbose_name_plural = "Attachments"
#
#     def has_module_permission(self, request):
#         return self.model is not None
#
#
# # class MessageArticleInline(admin.TabularInline):
# #     """
# #     Inline for placing Articles in a Message (if you created the join model).
# #     Shows 'position' so you can order them manually.
# #     """
# #     model = MessageArticle
# #     extra = 0
# #     fields = ("article", "position")
# #     ordering = ("position",)
# #     autocomplete_fields = ("article",)
# #
# #     def has_module_permission(self, request):
# #         return self.model is not None
#
#
# ---------- Article ----------

class ArticleAdminForm(forms.ModelForm):
    body_html = forms.CharField(widget=TinyMCE())

    class Meta:
        model = Article
        fields = "__all__"  # or list fields explicitly


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    form = ArticleAdminForm
    list_display = (
        "title",
        "template_type",
        "is_template",
        "image_position",
        "has_image",
        "created",
        "updated",
    )
    list_filter = ("is_template", "image_position",        "template_type",)
    search_fields = ("title",)
    readonly_fields = ("image_preview",)
    fieldsets = (
        (None, {
            "fields": ("title", "body_text", "body_html")
        }),
        (_("Image"), {
            "fields": ("image", "image_position", "image_preview"),
            "classes": ("collapse",),
        }),
        (_("Template"), {
            "fields": ("is_template",        "template_type", ),
        }),
        (_("Timestamps"), {
            "fields": ("created", "updated"),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = ("created", "updated", "image_preview")

    def has_image(self, obj):
        return bool(obj.image)
    has_image.boolean = True
    has_image.short_description = "Image?"

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-width:240px;height:auto;border:1px solid #ddd;">', obj.image.url)
        return "-"

    # If you use TinyMCE site-wide, you can also tweak formfield_overrides here.


# # ---------- Newsletter ----------
#
# # @admin.register(Newsletter)
# class NewsletterAdmin(admin.ModelAdmin):
#     list_display = ("title", "slug", "visible", "default_from", "subscriber_count")
#     list_filter = ("visible",)
#     search_fields = ("title", "slug")
#
#     def get_queryset(self, request):
#         qs = super().get_queryset(request)
#         # If you have related Subscription model name different, adjust related_name
#         sub_rel = "subscription"  # default guess; many setups use 'subscriptions'
#         try:
#             qs = qs.annotate(_subs=Count("subscriptions"))
#         except Exception:
#             try:
#                 qs = qs.annotate(_subs=Count("subscription"))
#             except Exception:
#                 qs = qs
#         return qs
#
#     def subscriber_count(self, obj):
#         return getattr(obj, "_subs", obj.subscription_set.count() if hasattr(obj, "subscription_set") else "-")
#     subscriber_count.short_description = "Subscribers"
#
#     def default_from(self, obj):
#         # Adjust to match your fields: sender/email on Newsletter
#         parts = []
#         if hasattr(obj, "sender") and obj.sender:
#             parts.append(obj.sender)
#         if hasattr(obj, "email") and obj.email:
#             parts.append(f"<{obj.email}>")
#         return format_html(" ".join(parts)) if parts else "-"
#     default_from.short_description = "From"
#
#
#
# # @admin.register(Message)
# class MessageAdmin(admin.ModelAdmin):
#     list_display = ("title", "news", "created", "modified", "preview_link", "queue_link")
#     list_filter = ("news",)
#     search_fields = ("title",)
#     inlines = []
#
#
#     def preview_link(self, obj):
#         # If you have a front-end preview view, point to it:
#         # e.g., name="news:message-preview"
#         link = _admin_link("Preview", "news:message-preview", obj.pk)
#         return format_html(link) if link else "-"
#     preview_link.short_description = "Preview"
#
#     def queue_link(self, obj):
#         # If you have an API/URL for queue in the front-end, add it; otherwise admin action above handles bulk.
#         link = _admin_link("Queue", "news:message-queue", obj.pk)
#         return format_html(link) if link else "-"
#     queue_link.short_description = "Queue"
#
#
# # @admin.register(Submission)
# class SubmissionAdmin(admin.ModelAdmin):
#     list_display = ("id", "message", "news", "status", "prepared", "sent")
#     list_filter = ("status", "news")
#     search_fields = ("message__title",)
