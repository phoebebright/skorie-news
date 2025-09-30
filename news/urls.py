from django.urls import path, register_converter

from news.views import NewsletterCreateView, NewsletterUpdateView, NewsletterDeleteView, \
    MessageListView, MessageCreateView, MessageUpdateView, MessageDeleteView, SubmissionListView, \
    NewsletterSubscriptionsView, UpdateMySubscription, MessagePreviewView, \
    MessageArticlesView, SubscribeWithEmail, EventSendView, \
    NewsletterDashboardView, SubscriptionThanks, SubscribeWithEmailRedirect, SubscribeWithEmailUnconfirmed, \
    IssueEditView, IssueCreateView, IssuePreviewView, IssueListView, ArticleListView, ArticleEditView, \
    ManageSubscriptionsView, UnsubscribeView, ConfirmSubscribeView, ClaimEmailManageLinkView, \
    SendFromTemplateView, AdminNewsletterDownloadView, fix_subscribers, issue_queue_submission
from tools.ref import EventRefConverter

app_name = "news"

register_converter(EventRefConverter, 'event_ref')

urlpatterns = [
    # Newsletters
    path("", NewsletterDashboardView.as_view(), name="news-home"),
    # path("news/list/", NewsletterListView.as_view(), name="news-list"),
    path("news/add/", NewsletterCreateView.as_view(), name="news-add"),
    path("news/<int:pk>/edit/", NewsletterUpdateView.as_view(), name="news-edit"),
    path("news/<int:pk>/delete/", NewsletterDeleteView.as_view(), name="news-delete"),

    # Issues
    path("issues/", MessageListView.as_view(), name="issue-list"),
    path("issue/<int:newsletter_pk>/", IssueListView.as_view(), name="issue-list"),
    path("issue/add/", IssueCreateView.as_view(), name="issue-add"),
    path("issue/add/<int:newsletter_pk>/", IssueCreateView.as_view(), name="issue-add"),
    path("issue/<int:pk>/edit/", IssueEditView.as_view(), name="issue-edit"),
    path("messages/<int:pk>/delete/", MessageDeleteView.as_view(), name="message-delete"),
    path("issue/<int:pk>/preview/", IssuePreviewView.as_view(), name="issue-preview"),
    path("issues/<int:pk>/queue/", issue_queue_submission, name="issue-queue" ),

    # Submissions
    path("submissions/", SubmissionListView.as_view(), name="submission-list"),



    #Articles
    path("message/<int:message_pk>/articles/", MessageArticlesView.as_view(), name="message-articles"),
    # path("message/<int:message_pk>/articles/add/", ArticleCreateView.as_view(), name="article-create"),
    # path("article/<int:pk>/edit/", ArticleUpdateView.as_view(), name="article-update"),
    # path("article/<int:pk>/delete/", ArticleDeleteView.as_view(), name="article-delete"),
    # path("message/<int:pk>/articles/reorder/", reorder_articles, name="article-reorder"),

    path("articles/", ArticleListView.as_view(), name="article-list"),
    path("articles/<int:pk>/edit/", ArticleEditView.as_view(), name="article-edit"),
    path("articles/new/", ArticleEditView.as_view(), name="article-new"),

    path("event/<event_ref:event_ref>/send/", EventSendView.as_view(), name="event-send"),

    # Subscriptions
    path("news/<str:newsletter_slug>/subscribe/", SubscribeWithEmail.as_view(), name="subscribe-with-email-only"),
    # only used while transferring from icontact - does not require confirmation
    # Subscriptions
    path("news/<str:newsletter_slug>/subscribe/", SubscribeWithEmailUnconfirmed.as_view(),
         name="subscribe-with-email"),


    # only used while transferring from icontact - does not require confirmation
    path("resubscribe/", SubscribeWithEmailRedirect.as_view(), name="resubscribe-with-email"),

    path("news/<int:newsletter_pk>/subscription/", UpdateMySubscription.as_view(), name="subscription-update"),
    path(
        "news/<int:newsletter_pk>/subscriptions/",
        NewsletterSubscriptionsView.as_view(),
        name="subscriptions-manage",
    ),
    path(
        "news/<int:newsletter_pk>/subscriptions/<str:action>",
        NewsletterSubscriptionsView.as_view(),
        name="subscriptions-manage",
    ),
    path("subscription-thanks/", SubscriptionThanks.as_view(), name="subscription-thanks"),

    path("manage/", ManageSubscriptionsView.as_view(), name="manage-subs"),
    path("manage/claim/<str:token>/", ClaimEmailManageLinkView.as_view(), name="manage-claim"),

    path("unsubscribe/<int:pk>/<str:code>/", UnsubscribeView.as_view(), name="unsubscribe-now"),
    path("subscribe/confirm/<int:pk>/<str:code>/",  ConfirmSubscribeView.as_view(), name="confirm-subscribe"),

    path(
        "send-from-template/<int:pk>/",
        SendFromTemplateView.as_view(),
        name="news-admin-send-from-template",
    ),

    # with template_id
    path(
        "send-from-template/<int:pk>/<int:template_id>/",
        SendFromTemplateView.as_view(),
        name="news-admin-send-from-template",
    ),

    path("subscribers/<int:pk>/download/", AdminNewsletterDownloadView.as_view(),
         name="subscribers-download"),

    path('fix_subscribers/', fix_subscribers, name="fix_subscribers"),
]
