import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from django.conf import settings

User = get_user_model()
logger = logging.getLogger('django')

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def on_user_created_link_subscriptions(sender, instance: User, created, **kwargs):
    if settings.USE_NEWSLETTER and created:
        from skorie_news.models import Subscription
        try:
            Subscription.link_subscriptions_to_user(instance)
        except Exception as e:
            logger.error(e)
            print(f"Error linking subscriptions for user {instance} : {e}")
