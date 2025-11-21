from django.urls import path, register_converter

from skorie_news.views import NewsletterCreateView, NewsletterUpdateView, NewsletterDeleteView, \
    MailingListView, \
    NewsletterSubscriptionsView, UpdateMySubscription, \
    MessageArticlesView, SubscribeWithEmail, EventSendView, \
    NewsletterDashboardView, SubscriptionThanks, SubscribeWithEmailRedirect, SubscribeWithEmailUnconfirmed, \
    IssueEditView, IssueCreateView, IssuePreviewView, IssueListView, ArticleListView, ArticleEditView, \
    ManageSubscriptionsView, UnsubscribeView, ConfirmSubscribeView, ClaimEmailManageLinkView, \
    SendFromArticleTemplateView, AdminNewsletterDownloadView, fix_subscribers, issue_queue_mailing, NewsListView, \
    NewsCreateView, NewsUpdateView, NewsDeleteView, DirectEmailDetailView, ArticlePreviewHTMLView, ArticlePreviewTextView

app_name = "skorie_news"


urlpatterns = [
    # Newsletters
    path("", NewsletterDashboardView.as_view(), name="news-home"),
    # path("newsletter/list/", NewsletterListView.as_view(), name="newsletter-list"),
    path("newsletter/add/", NewsletterCreateView.as_view(), name="newsletter-add"),
    path("newsletter/<int:pk>/edit/", NewsletterUpdateView.as_view(), name="newsletter-edit"),
    path("newsletter/<int:pk>/delete/", NewsletterDeleteView.as_view(), name="newsletter-delete"),

    path("event/<event_ref:event_ref>/news/", NewsListView.as_view(), name="news_list"),
    path("event/<event_ref:event_ref>/news/create/", NewsCreateView.as_view(), name="news_create"),
    path("event/<event_ref:event_ref>/news/<int:pk>/edit/", NewsUpdateView.as_view(), name="news_edit"),
    path("event/<event_ref:event_ref>/news/<int:pk>/delete/", NewsDeleteView.as_view(), name="news_delete"),

    # Issues

    path("issue/<int:newsletter_pk>/", IssueListView.as_view(), name="issue-list"),
    path("issue/add/", IssueCreateView.as_view(), name="issue-add"),
    path("issue/add/<int:newsletter_pk>/", IssueCreateView.as_view(), name="issue-add"),
    path("issue/<int:pk>/edit/", IssueEditView.as_view(), name="issue-edit"),
    path("issue/<int:pk>/preview/", IssuePreviewView.as_view(), name="issue-preview"),
    path("issues/<int:pk>/queue/", issue_queue_mailing, name="issue-queue" ),

    # Mailings
    path("mailings/", MailingListView.as_view(), name="mailing-list"),



    #Articles


    path("articles/", ArticleListView.as_view(), name="article-list"),
    path("articles/<int:pk>/edit/", ArticleEditView.as_view(), name="article-edit"),
    path("articles/new/", ArticleEditView.as_view(), name="article-new"),
    path("articles/<int:pk>/preview/", ArticlePreviewHTMLView.as_view(), name="article-preview"),
    path("articles/<int:pk>/preview.txt", ArticlePreviewTextView.as_view(), name="article-preview-text"),
    # path("event/<event_ref:event_ref>/send/", EventSendView.as_view(), name="event-send"),

    # Subscriptions
    path("newsletter/<str:newsletter_slug>/subscribe/", SubscribeWithEmail.as_view(), name="subscribe-with-email-only"),
    # only used while transferring from icontact - does not require confirmation
    # Subscriptions
    path("newsletter/<str:newsletter_slug>/subscribe/", SubscribeWithEmailUnconfirmed.as_view(),
         name="subscribe-with-email"),


    # only used while transferring from icontact - does not require confirmation
    path("resubscribe/", SubscribeWithEmailRedirect.as_view(), name="resubscribe-with-email"),

    path("newsletter/<int:newsletter_pk>/subscription/", UpdateMySubscription.as_view(), name="subscription-update"),
    path(
        "newsletter/<int:newsletter_pk>/subscriptions/",
        NewsletterSubscriptionsView.as_view(),
        name="subscriptions-manage",
    ),
    path(
        "newsletter/<int:newsletter_pk>/subscriptions/<str:action>",
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
        SendFromArticleTemplateView.as_view(),
        name="admin-send-from-template",
    ),

    # with template_id
    path(
        "send-from-template/<int:pk>/<int:template_id>/",
        SendFromArticleTemplateView.as_view(),
        name="admin-send-from-template",
    ),

    path("subscribers/<int:pk>/download/", AdminNewsletterDownloadView.as_view(),
         name="subscribers-download"),

    path('fix_subscribers/', fix_subscribers, name="fix_subscribers"),

    path("mail/direct/<int:pk>/", DirectEmailDetailView.as_view(), name="directemail-detail"),

]
