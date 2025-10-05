from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from django.conf import settings

from .models import DirectEmail

@dataclass
class PRIORITY:
    now = "now"
    high = "high"
    medium = "medium"
    low = "low"

# create a class that has same params as post_office to make it easier to switch
class mail:
    @staticmethod
    def send(
        recipients: Sequence[str] | str,
        sender: Optional[str] = None,          # this needs to be a user - the person sending the email
        template: Optional[str] = None,
        context: Optional[Mapping] = None,
        subject: Optional[str] = None,
        message: Optional[str] = None,
        html_message: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        priority: str = PRIORITY.now,
        attachments: Optional[Mapping[str, bytes] | Iterable[tuple]] = None,
        cc: Optional[Sequence[str]] = None,
        bcc: Optional[Sequence[str]] = None,
        reply_to: Optional[Sequence[str]] = None,
        scheduled_time=None,
        backend: Optional[str] = None,
            user = None, # the skorie user sending the email (may not be the sender on the email)
            receiver=None,   # User instance - only where there is one recipient, might need to rethink this.
            from_email=None,  # the from email address - if None, use settings.DEFAULT_FROM_EMAIL
        **kwargs,
    ):
        # Normalize to a list
        if isinstance(recipients, str):
            recipients = [recipients]
        elif isinstance(recipients, (tuple, set)):
            receiver = None    # can't have both receipients (plural) and receiver (singular)

        if not from_email:
            from_email = settings.DEFAULT_FROM_EMAIL

        deliveries = []
        for to_email in recipients:
            email = DirectEmail(
                to_email=to_email,
                from_email=from_email,
                subject=subject or "",
                body_text=message or "",
                body_html=html_message or "",
                template=template,
                receiver=receiver,
                creator=user,
                # store any headers you care about in context or add a headers JSONField
            )
            if context:
                email.render(context, save=True)
            else:
                email.save()

            deliveries.append(email.send())


        return deliveries


    def mail_admins(self, subject, message, *args, **kwargs):

        kwargs['recipients'] = settings.ADMINS
        kwargs["subject"] = subject
        kwargs["body_text"] = message
        self.send(**kwargs)
