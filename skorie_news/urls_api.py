# skorie_news/urls_api.py

from rest_framework.routers import DefaultRouter
from django.urls import path, include

from skorie_news.api import (
    IssueViewSet,
    ArticleViewSet,
    MailingViewSet,
    AdminSubscriptionROViewSet,
    SubscriptionPublicViewSet,
    SubscriptionAdminViewSet,
    SubscribeMe,
    UnSubscribeMe,
    SubscriberEventListAPIView, mailgun_webhook, SubscribeFromRequest, UnSubscribeFromRequest,
)

# Use DRF's DefaultRouter, not django.db.router
router = DefaultRouter()
router.register(r'news/subscription', SubscriptionAdminViewSet, basename='news-subscription-api')
router.register(r'news/subscription-manage', SubscriptionPublicViewSet, basename='news-sub-manage')
router.register(r'news/admin/subscribers', AdminSubscriptionROViewSet, basename='news-admin-subscribers')
router.register(r'news/mailing', MailingViewSet, basename='news-mailing-api')
router.register(r'news/articles', ArticleViewSet, basename='news-article')
router.register(r'news/issues', IssueViewSet, basename='news-issue')

urlpatterns = [
    path('subscribe_me/', SubscribeMe.as_view(), name='subscribe_me'),
    path('unsubscribe_me/', UnSubscribeMe.as_view(), name='unsubscribe_me'),
    path('subscribe_from_request/', SubscribeFromRequest.as_view(), name='subscribe_from_request'),
    path('unsubscribe_from_request/', UnSubscribeFromRequest.as_view(), name='unsubscribe_from_request'),

    path('news/subscribers/<int:pk>/events/', SubscriberEventListAPIView.as_view(), name='news-subscriber-events'),
    path('mailgun_webhook/', mailgun_webhook, name="mailgun_webhook"),
    # include the router-generated endpoints
    path('', include(router.urls)),
]
