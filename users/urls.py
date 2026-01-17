from django.contrib.auth.decorators import user_passes_test, login_required
from django.urls import path, register_converter
from django.conf import settings

if getattr(settings, 'USE_KEYCLOAK', False):
    try:
        from django_users.views import LoginView
        from django_users.urls import urlpatterns as django_users_patterns
    except ImportError:
        from django.contrib.auth.views import LoginView
        django_users_patterns = []
else:
    from django.contrib.auth.views import LoginView
    django_users_patterns = []

from skorie_news.tools.ref import EventRefConverter

from users.views import InviteUser2Event, TellUsAbout

app_name = 'users'

try:
    register_converter(EventRefConverter, 'event_ref')
except Exception:
    pass

def has_role_administrator(user):
    if user and user.is_authenticated:
        return user.is_superuser or user.is_administrator
    else:
        return False

def is_authenticated(user):
    return user and user.is_authenticated



app_name = "users"  # keep the same namespace if you want reverse('django_users:profile')

urlpatterns = [
                path('login/', LoginView.as_view(), name='user_login'),
                  path('invite_user/<event_ref:event_ref>/',
                       user_passes_test(is_authenticated)(InviteUser2Event.as_view()),
                       name='invite-user2event'),

                  path('tell_us_about/', user_passes_test(is_authenticated)(TellUsAbout.as_view()), name='subscribe'),
                  # deprecated
                  path('tell_us_about/', user_passes_test(is_authenticated)(TellUsAbout.as_view()),
                       name='tell_us_about'),


              ] + django_users_patterns  # append the django_users patterns at the end to avoid name conflicts
