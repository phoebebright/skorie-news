
from django.urls import reverse

from config import settings
from tools.decorators import notifications_on

from skorie_news.models import get_mail_class
mail = get_mail_class()

@notifications_on
def on_new_user_unverified(instance, message, request=None, user=None):
    from users.models import CustomUser

    mail.mail_admins(f"User signing up {instance} for {settings.SITE_NAME}", reverse("users:admin_user", instance.keycloak_id ) )

@notifications_on
def on_new_user_verified(instance, message, request=None, user=None):
    from users.models import CustomUser

    mail.mail_admins(f"User verified {instance} for {settings.SITE_NAME}", reverse("users:admin_user", instance.keycloak_id ) )
