# tests/test_mail_anymail.py
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core import mail
from django.template import Template
from django.utils import timezone

from news.models import Newsletter, Issue, Article, Subscription, Mailing, DirectEmail, Delivery
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="anymail.backends.test.EmailBackend",
    DEFAULT_FROM_EMAIL="Skorie <noreply@example.com>",
)
class MailingTests(TestCase):
    def setUp(self):
        # Patch Newsletter.get_templates to avoid filesystem lookups
        def fake_get_templates(_self, action):
            assert action == "message"  # your code calls action="message" for issues
            return (
                Template("Subject: {{ message.title }}"),
                Template("Text for {{ message.title }}"),
                Template("<p>HTML for {{ message.title }}</p>"),
            )

        self.tpl_patch = patch.object(Newsletter, "get_templates", fake_get_templates)
        self.tpl_patch.start()

        # Minimal data
        self.site = Site.objects.get_current()

        self.newsletter = Newsletter.objects.create(
            title="General",
            slug="general",
            email="noreply@example.com",
            sender="Skorie",
            visible=True,
            public=True,
            send_html=True,
        )

        # Subscribers (active)
        self.sub1 = Subscription.objects.create(
            newsletter=self.newsletter,
            email="alice@example.com",
            subscribed=True,
            consent_at=timezone.now(),
            active=True,
        )
        self.sub2 = Subscription.objects.create(
            newsletter=self.newsletter,
            email="bob@example.com",
            subscribed=True,
            consent_at=timezone.now(),
            active=True,
        )

        self.article = Article.objects.create(
            template_type=Article.TEMPLATE_TYPE_NEWSLETTER,
            title="Hello World",
            body_html="<p>HTML for Hello World</p>",
            body_text="Text for Hello World",
        )
        self.issue = Issue.objects.create(
            title="Hello World",
            newsletter=self.newsletter,
        )
        self.issue.articles.add(self.article)

    def tearDown(self):
        self.tpl_patch.stop()

    def test_send_issue_via_anymail_creates_deliveries(self):
        """
        send_via_anymail should:
        - send a single AnymailMessage with multiple recipients (merge_data)
        - create one Delivery row per recipient
        - mark Mailing status SENT
        """
        mailing = Mailing.send_issue(self.issue)
        # implementation expected: your Mailing has a method renamed to Anymail version (per refactor)
        # If you kept the same name, adjust to mailing.send_via_anymail()
        mailing.send_via_anymail()

        # One message in outbox, addressed to both recipients
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn("Subject: Hello World", msg.subject)
        self.assertCountEqual(msg.to, ["alice@example.com", "bob@example.com"])

        # Anymail test backend supplies anymail_status
        self.assertTrue(hasattr(msg, "anymail_status"))
        status = msg.anymail_status
        self.assertIsNotNone(status.message_id or status.recipients)  # either is fine in test backend

        # Delivery rows
        deliveries = Delivery.objects.filter(mailing=mailing).order_by("email")
        self.assertEqual(deliveries.count(), 2)
        self.assertEqual(deliveries[0].email, "alice@example.com")
        self.assertEqual(deliveries[1].email, "bob@example.com")
        for d in deliveries:
            self.assertEqual(d.state, "sending")  # accepted by ESP (simulated)
            self.assertTrue(d.message_id)         # copied from anymail_status
            self.assertEqual(d.esp_name, "test")  # Anymail test backend uses 'test'

        mailing.refresh_from_db()
        self.assertTrue(mailing.is_sent)

    def test_direct_email_send_simple(self):
        """
        DirectEmail.send_simple_email should:
        - enqueue an AnymailMessage to outbox
        - create a Delivery linked to the DirectEmail
        """
        delivery = DirectEmail.send_simple_email(
            subject="Ping",
            message="Text body",
            html="<p>HTML body</p>",
            to_email="carol@example.com",
        )

        # Outbox
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Ping")
        self.assertEqual(msg.to, ["carol@example.com"])
        self.assertTrue(hasattr(msg, "anymail_status"))

        # Delivery
        self.assertIsNotNone(delivery)
        self.assertIsInstance(delivery, Delivery)
        self.assertEqual(delivery.email, "carol@example.com")
        self.assertEqual(delivery.state, "sending")
        self.assertTrue(delivery.message_id)
        self.assertEqual(delivery.esp_name, "test")

    @override_settings(
        DEBUG=True,
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        DEFAULT_FROM_EMAIL="Skorie <noreply@example.com>",
    )
    def test_direct_email_debug_console_backend(self):
        """
        In DEBUG, DirectEmail.send() still sends, but via the console backend.
        Delivery is created.
        """
        delivery = DirectEmail.send_simple_email(
            subject="Debug Mode",
            message="Goes to console",
            to_email="debug@example.com",
        )
        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.email, "debug@example.com")
        self.assertEqual(delivery.state, "sending")
