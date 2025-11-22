from django.apps import apps
from django.utils.module_loading import import_string
from rest_framework import permissions

from django.conf import settings
from django.utils import timezone

import logging

from .ref import get_obj_from_ref

logger = logging.getLogger('django')

from .exceptions import EventPermissionDenied, UserPermissionDenied, ChangePasswordException

ModelRoles = import_string(settings.MODEL_ROLES_PATH)

def get_event(request, kwargs ):
    '''work out event from request and kwargs'''
    Entry = apps.get_model('web', 'Entry')
    Competition = apps.get_model('web', 'Competition')
    ScoreSheet = apps.get_model('web', 'ScoreSheet')
    Event = apps.get_model('web', 'Event')
    MyEvent = apps.get_model('web', 'MyEvent')
    Competitor = apps.get_model('web', 'Competitor')

    event_ref = None
    event = None

    # do we have an event in the request - should already have dealt with this in th emiddleware
    if hasattr(request, 'event') and request.event:
        # ignore if api
        if not 'api' in request.get_full_path():
            event = request.event
            event_ref = event.ref

    # has event been specified in the request
    if not event:

        if 'event_ref' in getattr(request, 'query_params',[]):
            event_ref = request.query_params.get('event_ref')
        elif 'event_ref' in kwargs:
            event_ref = kwargs['event_ref']

        elif 'ref' in kwargs and kwargs['ref'].startswith('V'):
            event_ref = kwargs['ref']
        elif 'eventref' in kwargs:   # eventref is deprecated
            logger.warning(f"Using eventref for api {request}. eventref is deprecated")
            event_ref = kwargs['eventref']
        elif hasattr(request, 'data') and 'event_ref' in request.data:
            logger.warning(f"Using request.data to get event_ref")
            event_ref = request.data.get('event_ref')

        # should have eventref in the url, but not always...
        elif 'entry_ref' in kwargs:
            event_ref = f"V{kwargs['entry_ref'][1:5]}"
        elif 'entryref' in kwargs:
            try:
                e = Entry.objects.get(ref=kwargs['entryref'])
            except Entry.DoesNotExist:
                pass
            else:
                event = e.event
                event_ref = event.ref
        elif 'compref' in kwargs:
            # should put event ref in the url but just in case...
            c = Competition.objects.get(ref=kwargs['compref'])
            event = c.event
            event_ref = event.ref

        elif 'sheetref' in kwargs or 'ref' in kwargs and kwargs['ref'].startswith('S'):
            # should put event ref in the url but just in case...
            s = ScoreSheet.objects.get(ref=kwargs['ref'])
            event = s.event
            event_ref = event.ref

        elif 'ref' in kwargs and kwargs['ref'].startswith('E'):
            logger.warning(f"Using ref to get entry ref in api {request} - should call with event_ref")
            event_ref = "V" + kwargs['ref'][1:5]

    # specified event overrides request event
    if event and event_ref and event.ref != event_ref:
        logger.warning("Having to override event in request with specified event")
        event = None

    # if we have an event_ref, try to get the event
    if event_ref and not event:
        try:
            event = Event.objects.get(ref=event_ref)
        except Event.DoesNotExist:
            event_ref = None


    # request event will have been picked up from the session if possible in the EventUserPermissions middleware
    # so we use that if we couldn't work it out from the parameters/query
    if not event_ref and not event:
        if hasattr(request, 'event') and request.event:
            # last ditch effort to get event
            if not event and not 'api' in request.get_full_path():
                event = request.event
                event_ref = event.ref
            elif event and event != request.event:
                logger.info(f"having to switch request.event in get_event from {request.event} to {event}")
                request.event = event
            elif event and event_ref and event_ref != event.ref:
                logger.warning(f"Event ref in request {event.ref} does not match event_ref {event_ref} in parameters/url {request} probably don't have event_ref in the url")
                # once this no longer occurs we can trust the session event and put it at the top of this function (where it was) making it faster.


    # # specified event overrides request event
    # if event and event_ref and event.ref != event_ref:
    #     logger.warning("Having to override event in request with specified event")
    #     event = None

    # one last try
    if not event_ref and not event:
        # edge case where creating the event
        # if request._request.method == "POST" and request._request.path_info == '/api/v2/event/':
        #     return None

        logger.warning(f"get_event called without event_ref or event in request {request}")
        if  'ref' in kwargs:
            obj = get_obj_from_ref(kwargs['ref'])
            try:
                event = obj.event
            except:
                pass

    if event_ref and not event:
        try:
            event = Event.objects.get(ref=event_ref)
        except Exception as e:
            raise EventPermissionDenied(f'Unknown event {event_ref} requested by {request.user}')

    # set timezone for this event
    if event:
        timezone.activate(event.timezone)
        #logger.info(f"Set timezone to {event.timezone} in get_event ")


        session_ref = request.session.get('event_ref', None)

        if session_ref and session_ref != event.ref and request.user.is_authenticated:
            # session doesn't seem to be being set elsewhere - so going to do it here
            request.session['event_ref'] = event.ref
    if event and request.user.is_authenticated:
        MyEvent.touch_or_create(event.id, request.user.id)


    return event


def user_role_check(request, event, role_required):

    if not request.user.is_authenticated:
        logger.info("Non-autheticated user requested access ")
        return False


    me = request.user

    # # special case if creating an event - can be done by organisers or competitors
    # if not event and request.method == "POST" and (me.is_manager or me.is_competitor):
    #     return True

    # special case for superuser
    # if me.is_superuser:
    #     return True

    if event:
        # logger.info(f"Checking user {me} has role {role_required} for event {event}")
        result = event.has_role4event(me, role_required)
    else:
        logger.error(f"user_role_check called without event paramter for user {me}")
        result = False



    return result


def user_can_enter_check(request, event):

    if not request.user.is_authenticated:
        logger.info("Non-autheticated user requested access ")
        return False

    # can_enter also checks event is open for entries
    return event.can_enter(request.user)



# add to api permission classes
class CheckEventPermissions(permissions.BasePermission):

    def has_permission(self, request, view):
        view.me = request.user

        if not hasattr(view, 'event')  or not view.event:
            self.message = f"Expecting Event to be in {view} but not found"
            return False

        if settings.SUPERUSER_EVENT_ACCESS and view.me.is_superuser:
            return True

        if view.me.is_administrator:
            return True

        return user_role_check(request, view.event, self.role_required)

# add to api permission classes
class IsAnyRole4EventPermission(CheckEventPermissions):

    role_required = '__any__'

# add to api permission classes
class IsOrganiser4EventPermission(CheckEventPermissions):

    role_required = ModelRoles.ROLE_ORGANISER


# add to api permission classes
class IsJudge4EventPermission(CheckEventPermissions):

    role_required = [ModelRoles.ROLE_JUDGE,]

# add to api permission classes
class IsReader4EventPermission(CheckEventPermissions):

    role_required = ModelRoles.ROLE_AUXJUDGE

# add to api permission classes
class IsJudgeOrReader4EventPermission(CheckEventPermissions):

    role_required = [ModelRoles.ROLE_JUDGE, ModelRoles.ROLE_AUXJUDGE]

class IsCompetitor4EventPermission(CheckEventPermissions):
    # we are not saving the Competitor role in EventRole anymore - so we need to check for Competitor in Competitor
    def has_permission(self, request, view):
        view.me = request.user

        if not hasattr(view, 'event') or not view.event:
            self.message = f"Expecting Event to be in {view} but not found"
            return False

        if settings.SUPERUSER_EVENT_ACCESS and view.me.is_superuser:
            return True

        try:
            Competitor.objects.get(event=view.event, user=view.me)
        except Competitor.DoesNotExist:
            return False
        else:
            return True


# add to api permission classes
class CanEnterEventPermission(CheckEventPermissions):
    # use this one for API calls
    message = 'User does not have permissions to add entries to event.'

    def has_permission(self, request, view):
        self.me = request.user
        if not view.event:
            self.message = "Expecting Event to be in {view} but not found"
            return False

        return user_can_enter_check(request, view.event)

# add to api permission classes
class IsJudgeOrAux4EventPermission(CheckEventPermissions):

    role_required = [ModelRoles.ROLE_JUDGE, ModelRoles.ROLE_AUXJUDGE]


# add to api permission classes
class CheckRolePermissions(permissions.BasePermission):

    def has_permission(self, request, view):
        view.me = request.user
        return view.me.has_role(self.role_required)

# add to api permission classes
class IsManagerPermission(CheckRolePermissions):

    role_required = ModelRoles.ROLE_MANAGER

class IsAdministratorPermission(CheckRolePermissions):

    role_required = ModelRoles.ROLE_ADMINISTRATOR
    

class IsJudgePermission(CheckRolePermissions):

    role_required = ModelRoles.ROLE_JUDGE


class IsRiderPermission(CheckRolePermissions):

    role_required = ModelRoles.ROLE_COMPETITOR




class ChangeMyStuff(permissions.BasePermission):
    """
    If you entered it you can change it
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Instance must have an attribute named `owner`.
        return obj.creator == request.user
