import logging

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db import models
from typing import Optional, Dict, Any, Set

logger = logging.getLogger('django')


class UnsignedAutoField(models.AutoField):
    def db_type(self, connection):
        return 'integer UNSIGNED AUTO_INCREMENT'

    def rel_db_type(self, connection):
        return 'integer UNSIGNED'




class TrackChangesMixin:
    _snapshot: Optional[Dict[str, Any]] = None
    _track_fields: Optional[Set[str]] = None
    FIELDS_TO_CHECK = None

    def __init__(self, *args, track_fields: Optional[Set[str]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._track_fields = track_fields
        self.take_snapshot()

    def take_snapshot(self):
        self._snapshot = self.as_dict

    @property
    def diff(self) -> Dict[str, Any]:
        if self._snapshot is None:
            raise ValueError("Snapshot wasn't taken; can't determine diff.")
        current_state = self.as_dict
        diffs = {k: (v, current_state[k]) for k, v in self._snapshot.items() if v != current_state.get(k)}
        return diffs

    @property
    def has_changed(self) -> bool:
        return bool(self.diff)

    @property
    def changed_fields(self) -> Set[str]:
        return set(self.diff.keys())

    @property
    def as_dict(self, check_relationship=False, include_primary_key=True):


            """
            Capture the model fields' state as a dictionary.

            Only capture values we are confident are in the database, or would be
            saved to the database if self.save() is called.
            """
            all_field = {}


            deferred_fields = self.get_deferred_fields()

            for field in self._meta.concrete_fields:

                # For backward compatibility reasons, in particular for fkey fields, we check both
                # the real name and the wrapped name (it means that we can specify either the field
                # name with or without the "_id" suffix.
                field_names_to_check = [field.name, field.get_attname()]
                if self.FIELDS_TO_CHECK and (not any(name in self.FIELDS_TO_CHECK for name in field_names_to_check)):
                    continue

                if field.primary_key and not include_primary_key:
                    continue

                # leaving this will discard related fields - still suspect that changes are not being cleared when the object is saved.
                # if field.remote_field:
                #     if not check_relationship:
                #         continue

                if field.get_attname() in deferred_fields:
                    continue

                field_value = getattr(self, field.attname)

                if isinstance(field_value, File):
                    # Uses the name for files due to a perfomance regression caused by Django 3.1.
                    # For more info see: https://github.com/romgar/django-dirtyfields/issues/165
                    field_value = field_value.name

                # If current field value is an expression, we are not evaluating it
                if isinstance(field_value, (BaseExpression, Combinable)):
                    continue

                try:
                    # Store the converted value for fields with conversion
                    field_value = field.to_python(field_value)
                except ValidationError:
                    # The current value is not valid so we cannot convert it
                    pass

                if isinstance(field_value, memoryview):
                    # psycopg2 returns uncopyable type buffer for bytea
                    field_value = bytes(field_value)

                # Explanation of copy usage here :
                # https://github.com/romgar/django-dirtyfields/commit/efd0286db8b874b5d6bd06c9e903b1a0c9cc6b00
                all_field[field.name] = deepcopy(field_value)

            return all_field


class StatusMixin(object):

    def auto_update_status(self, before, save=False):
        raise NotImplementedError()

    def on_status_change(self, user=None):
        raise NotImplementedError()

    def manual_status_update(self, new_status, user=None, force=False):
        '''need to use this so we can trigger on_status_change
        force=True - does not run save method in model - only used in testing'''
        # TODO: what if new_status is less - eg. trying to move scoresheet from final to scoring - does this happen outside of tests?

        print(f"Manual status update for {self} from {self.status} to {new_status}")
        before = self.status
        self.status = new_status

        # must save before calling on_status_change (?)
        if force:
            super().save(update_fields=['status',])
        else:
            self.save(user=user)

        self.on_status_change(before, user)

class CreatedUpdatedMixin(models.Model):

    creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="%(app_label)s_%(class)s_creator", editable=False,blank=True, null=True, on_delete=models.PROTECT)
    created = models.DateTimeField(_('Created Date'), auto_now_add=True, editable=False, db_index=True)
    updator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="%(app_label)s_%(class)s_updator", editable=False,blank=True, null=True, on_delete=models.PROTECT,)
    updated = models.DateTimeField(_('Updated Date'), blank=True, null=True, editable=False, db_index=True)

    class Meta:
        abstract = True

    def save_model(self, request, obj, form, change):
        if obj.pk:
            # handle updator already been set
            if obj.updator != request.user:
                obj.updator = request.user
            obj.updated = timezone.now()

        else:
            # handle creator already been set
            if not obj.creator:
                obj.creator = request.user
            obj.created = timezone.now()

        super().save_model(request, obj, form, change)

    def save(self, *args, **kwargs):

        user = None
        if 'user' in kwargs:
            user = kwargs['user']
            kwargs.pop('user')

            if not (getattr(user, "is_authenticated", False) and isinstance(user, models.Model)):
                logger.warning(f"User {user} passed to save method of {self} is not a User object or is not authenticted")
                user = None

        if self.pk:
            self.updator = user
            self.updated = timezone.now()

        else:
            if not self.creator_id and user:
                self.creator = user
            self.created = timezone.now()

        super().save(*args, **kwargs)

    @property
    def touched(self):
        return self.updated if self.updated else self.created


class CreatedMixin(models.Model):

    creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="%(app_label)s_%(class)s_creator", editable=False, blank=True, null=True, on_delete=models.DO_NOTHING,)
    created = models.DateTimeField(_('Created Date'), auto_now_add=True, editable=False, db_index=True)

    class Meta:
        abstract = True

    def save_model(self, request, obj, form, change):
        if not obj.pk:

            obj.creator = request.user
            obj.created = timezone.now()

        super().save_model(request, obj, form, change)




    @property
    def touched(self):
        return self.created

class TagForDeletionMixin(models.Model):

    for_deletion = models.BooleanField(default=False, help_text=_("Images to be deleted"))
    for_deletion_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="%(app_label)s_%(class)s_for_deletion", blank=True, null=True, editable=False, on_delete=models.DO_NOTHING,)
    for_deletion_set = models.DateTimeField(_('When set for deletion'), editable=False, blank=True, null=True)


    class Meta:
        abstract = True

    def tag_for_deletion(self, user, save=True):
        self.for_deletion = True
        self.for_deletion_by = user
        self.for_deletion_set = timezone.now()

        if save:
            self.save()

    def untag_for_deletion(self, user, save=True):
        self.for_deletion = False
        self.for_deletion_by = user
        self.for_deletion_set = timezone.now()

        if save:
            self.save()



# class EventQueryManager(models.Manager):
#     def get_queryset(self):
#         return PersonQuerySet(self.model, using=self._db)
#
#     def authors(self):
#         return self.get_queryset().authors()


class EventMixin(models.Model):
    '''data is grouped by event and event is added as a denormalised fields to a number of models.  Both event_id that is
    used as a ForeignKey and event_ref which is retained even if the data is moved are included.  The key field for
    Event is not changed to the ref field because it causes a problem in various libraries that expect the key field
    to be a integer.'''

    # lazy loaded models
    _Event = None

    @property
    def Event(self):
        if not self._Event:
            self._Event = apps.get_model('web', 'Event')
        return self._Event

    # event fk used for internal queries for an event
    #TODO: try making event required
    event = models.ForeignKey('web.Event',  blank=True, null=True, on_delete=models.CASCADE)
    # event_ref is used for external queries for an event
    event_ref = models.CharField(max_length=5, db_index=True, blank=True, null=True)  # this should be a required field also



    class Meta:
        abstract = True

    def save(self, *args, **kwargs):


        # make sure event_ref is populated
        if not self.event_ref and self.event:
            self.event_ref = self.event.ref

        if self.event_ref and not self.event:
            cls = apps.get_model(app_label='web', model_name='Event')

            self.event = cls.objects.get(ref=self.event_ref)

        if self.event and  self.event_ref != self.event.ref:
            raise ValidationError("Event ref and event do not match")

        # if not self.event_ref and not self.event :
        #     print("Warning no event - ok if this is in competitor mode but how do we know?")
            #raise ValidationError("No event specified for %s" % self)

        super().save(*args, **kwargs)


    @classmethod
    def get_event(cls, key):

        try:
            return cls.objects.get(event_ref=key)
        except cls.DoesNotExist:
            return cls.objects.get(event_id=id)


    @classmethod
    def filter_event(cls, key):
        try:
            id = int(key)
            return cls.filter(event_id = id)
        except:
            return cls.filter(event_ref = key)


    @classmethod
    def event_qs(cls, event:object, group=True) -> object:
        '''return a queryset of all entries for this event
        if this event is part of a group, return all the objects for this group, unless group=False'''
        if len(event.event_group) > 1 and group:
            return cls.objects.filter(event_ref__in=event.event_group)
        else:
            return cls.objects.filter(event=event)

class NewsletterUserMixin(models.Model):

    def is_subscribed2newsletter(self):
        Subscription = apps.get_model('skorie_news', 'Subscription')
        try:
            sub = Subscription.objects.get(newsletter__slug=settings.NEWSLETTER_GENERAL_PK, user=self).exists()
        except Subscription.DoesNotExist:
            return False

        return True
