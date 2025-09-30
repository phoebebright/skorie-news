import pytest
from django.utils import timezone
from news.models import Subscription, SubscriptionEvent

@pytest.mark.django_db
def test_subscribe_creates_active(newsletter):
    sub = Subscription.objects.create(newsletter=newsletter, email="A@EXAMPLE.COM")
    assert sub.email == "a@example.com"
    assert not sub.subscribed  # default in model
    # activate via helper
    sub.subscribe()
    sub.refresh_from_db()
    assert sub.subscribed is True
    assert sub.unsubscribed is False
    assert sub.subscribe_date is not None
    assert SubscriptionEvent.objects.filter(subscription=sub, event=SubscriptionEvent.Event.SUBSCRIBE).exists()

@pytest.mark.django_db
def test_unsubscribe_sets_flags_and_event(newsletter):
    sub = Subscription.objects.create(newsletter=newsletter, email="a@example.com", subscribed=True)
    sub.unsubscribe()
    sub.refresh_from_db()
    assert sub.subscribed is False
    assert sub.unsubscribed is True
    assert sub.unsubscribe_date is not None
    assert SubscriptionEvent.objects.filter(subscription=sub, event=SubscriptionEvent.Event.UNSUBSCRIBE).exists()

@pytest.mark.django_db
def test_link_subscriptions_to_user_links_all(newsletter, user):
    Subscription.objects.create(newsletter=newsletter, email=user.email)
    Subscription.objects.create(newsletter=newsletter, email=user.email)
    count = Subscription.link_subscriptions_to_user(user)
    assert count == 2
    assert Subscription.objects.filter(user=user).count() == 2

@pytest.mark.django_db
def test_idempotent_reactivate_existing(newsletter):
    # existing unsubscribed row -> resubscribe
    sub = Subscription.objects.create(newsletter=newsletter, email="a@example.com", subscribed=False, unsubscribed=True)
    before = sub.updated
    sub.subscribe()
    sub.refresh_from_db()
    assert sub.subscribed and not sub.unsubscribed
    assert sub.updated >= before
