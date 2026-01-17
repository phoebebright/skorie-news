from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from skorie_news.model_mixins import EventMixin
from web.roles_and_disciplines import ModelRoles


class Event(models.Model):
    name = models.CharField(max_length=255)
    ref = models.CharField(max_length=5, unique=True, help_text="Unique reference for the event")
    event_group = models.JSONField(default=list, blank=True, help_text="List of event refs in this group")
    date = models.DateField()

    def __str__(self):
        return self.name

class Competition(EventMixin):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='competitions')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.event.name})"

class Competitor(EventMixin):
    role_type = ModelRoles.ROLE_COMPETITOR
    role_name = _("Competitor")
    '''A Competitor at an Event - the link between Role, User, Person and Event for competitors - holding personal info
    just for the duration of the Event - when the Event is archived personal data is deleted.'''

    role = models.ForeignKey("users.Role", on_delete=models.CASCADE, null=True, blank=True,
                             related_name="%(class)s_role")

    name = models.CharField(_("Name"), max_length=60)

    # note that a user can enter a competitor who is not them.  IN this case the user will be the person who entered
    # them (this may change) and the person may be blank.
    # Otherwise the person is the same person as is linked to the user
    person = models.ForeignKey("users.Person", on_delete=models.CASCADE, null=True, blank=True,
                               related_name="%(class)s_person")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                             related_name="%(class)s_user")

    email = models.EmailField(_('email address'), blank=True, null=True, db_index=True,
                              help_text=_("Email used for notifications for this event only"))


class Entry(EventMixin):
    ref = models.CharField(max_length=9, unique=True, null=True, blank=True)
    entryid = models.CharField(max_length=32, blank=True, null=True, db_index=True,
                               help_text=_("Organiser assigned number or reference"))

    competition = models.ForeignKey("Competition", blank=True, null=True, on_delete=models.CASCADE)

    # competitor person details as at this date
    competitor = models.ForeignKey("Competitor", on_delete=models.CASCADE, related_name="entry_competitor", blank=True,
                                   null=True)



class EventRole(models.Model):


    role_type = models.CharField(choices=ModelRoles.EVENT_ROLE_CHOICES, max_length=1)
    name = models.CharField(max_length=60)

    role = models.ForeignKey("users.Role", on_delete=models.SET_NULL, blank=True, null=True)
    role_ref = models.CharField(max_length=7, null=True, blank=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    email = models.EmailField(_('email address'), blank=True, null=True,
                              help_text=_(
                                  "Email used for notifications for this event only - will be removed after event"))
