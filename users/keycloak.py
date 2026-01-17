import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakAuthenticationError, KeycloakGetError



logger = logging.getLogger('django')

if getattr(settings, 'USE_KEYCLOAK', False):
    try:
        client_id = settings.KEYCLOAK_CLIENTS['USERS']['CLIENT_ID']
        client_secret = settings.KEYCLOAK_CLIENTS['USERS']['CLIENT_SECRET']
        keycloak_url = settings.KEYCLOAK_CLIENTS['USERS']['URL']
        keycloak_realm = settings.KEYCLOAK_CLIENTS['USERS']['REALM']
    except (AttributeError, KeyError):
        logger.error("Keycloak client ID and secret not found in settings")
        raise

    # Initialize KeycloakAdmin for administrative actions
    keycloak_admin = KeycloakAdmin(
        server_url=f"{keycloak_url}/",
        realm_name=keycloak_realm,
        client_id=client_id,
        client_secret_key=client_secret,
        verify=True
    )
else:
    keycloak_admin = None


def get_access_token(requester):
    '''Get an access token for the Keycloak admin API'''
    if not keycloak_admin:
        return None
    if not requester.is_administrator and not requester.is_manager:
        logger.error(f"User {requester} is not an administrator or manager and cannot request a Keycloak access token")
        return None

    try:
        token = keycloak_admin.token(grant_type="client_credentials")
        logger.info(f"User {requester} requesting Keycloak access token")
        return token['access_token']
    except KeycloakAuthenticationError as e:
        logger.error(f"Failed to get access token: {e}")
        return None



#
#
# def verify_user_without_email(user_id):
#     '''allow user to be enabled and verified in keycloak without clicking the link in the email process'''
#     payload = {
#         'emailVerified': True,
#         'enabled': True,
#         'requiredActions': []
#     }
#
#     try:
#         keycloak_admin.update_user(user_id=user_id, payload=payload)
#         logger.info(f"User {user_id} verified successfully in Keycloak")
#     except Exception as e:
#         logger.error(f"Failed to verify user in Keycloak: {e}")
#
# def search_user_by_email_in_keycloak(email, requester):
#     '''Search for a user by email in Keycloak'''
#
#
#     try:
#         user_id_keycloak = keycloak_admin.get_user_id(email)
#
#     except Exception as e:
#         logger.error(f"Failed to search user by email in Keycloak: {e}")
#         return None
#     except KeycloakGetError as e:
#         pass
#     else:
#         if user_id_keycloak:
#             user = keycloak_admin.get_user(user_id_keycloak)
#             return user
#
#     return None

#
# def update_users(request):
#     # temporary function to update all users with keycloak_id
#     from users.models import CustomUser
#     for user in CustomUser.objects.filter(keycloak_id__isnull=True):
#         try:
#             user.keycloak_id = keycloak_admin.get_user_id(user.email)
#         except Exception as e:
#             print(e)
#         else:
#             user.save(update_fields=['keycloak_id',])
