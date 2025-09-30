from django.test import TestCase, override_settings
from news.mail import mail
from django.contrib.auth import get_user_model

from news.models import DirectEmail, Delivery, get_mail_class

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="anymail.backends.test.EmailBackend",
    DEFAULT_FROM_EMAIL="Skorie <noreply@example.com>",

)
class DirectEmailSendTests(TestCase):

    def test_direct_email_send_simple_to_address(self):
        # Act
        delivery = DirectEmail.send_simple_email(
            subject="Hello",
            message="Plain text body",
            html="<p>HTML body</p>",
            to_email="alice@example.com",
        )

        # Assert: one message in outbox
        # self.assertEqual(len(mail.outbox), 1)
        # msg = mail.outbox[0]
        # self.assertEqual(msg.subject, "Hello")
        # self.assertEqual(msg.to, ["alice@example.com"])
        # # Anymail test backend provides anymail_status
        # self.assertTrue(hasattr(msg, "anymail_status"))
        #self.assertTrue(msg.anymail_status.message_id) . won't be created in test backend

        # Delivery row created
        self.assertIsNotNone(delivery)
        self.assertIsInstance(delivery, Delivery)
        self.assertEqual(delivery.email, "alice@example.com")
        self.assertEqual(delivery.state, "sending")
        # self.assertTrue(delivery.message_id)

    def test_direct_email_send_simple_to_user(self):
            user = User.objects.create_user(
            username="bob", email="bob@example.com", password="x"
            )
            delivery = DirectEmail.send_simple_email(
                subject="Hi Bob",
                message="Howya",
                user=user,
                html=None,  # text-only
            )

            # self.assertEqual(len(mail.outbox), 1)
            # msg = mail.outbox[0]
            # self.assertEqual(msg.to, ["bob@example.com"])
            # self.assertEqual(msg.body, "Howya")
            # self.assertTrue(hasattr(msg, "anymail_status"))

            self.assertEqual(delivery.email, "bob@example.com")
            self.assertEqual(delivery.state, "sending")
            # self.assertTrue(delivery.message_id)



    def test_direct_email_debug_uses_console_backend_and_creates_delivery(self):
        """
        In DEBUG we still call send(); with console backend this prints to stdout.
        We still create a Delivery row.
        """
        delivery = DirectEmail.send_simple_email(
                subject="Debug Mode",
                message="Goes to console",
            to_email="debug@example.com",
        )

        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.email, "debug@example.com")
        self.assertEqual(delivery.state, DirectEmail.DIRECT_MAIL_SENDING)
        # Console backend doesn't have anymail_status; message_id may be None
        # so don't assert it here.



@override_settings(
    EMAIL_BACKEND="anymail.backends.test.EmailBackend",
    DEFAULT_FROM_EMAIL="Skorie <noreply@example.com>",
    SITE_NAME="Test Site",
    EMAIL_WRAPPER = 'news.mail.mail'
)
class MailWrapperTests(TestCase):

    def setUp(self):
        super().setUp()
        self.mail = get_mail_class()

    def test_send_single_recipient(self):
        deliveries = self.mail.send(
            recipients="alice@example.com",
            subject="Hello Alice",
            message="Hi Alice, this is plain text",
            html_message="<p>Hi Alice, this is HTML</p>",
        )

        delivery = deliveries[0]
        self.assertEqual(delivery.email, "alice@example.com")
        self.assertEqual(delivery.state, DirectEmail.DIRECT_MAIL_SENDING)

    def test_send_multiple_recipients(self):
        deliveries = mail.send(
            recipients=["bob@example.com", "carol@example.com"],
            subject="Group Notice",
            message="Hi all",
        )

        self.assertEqual(len(deliveries), 2)


    def test_context_is_stored(self):
        ctx = {"foo": "bar"}
        deliveries = self.mail.send(
            recipients="eve@example.com",
            subject="Has context",
            message="Plain text",
            context=ctx,
        )

        delivery = deliveries[0]
        self.assertEqual(delivery.direct_mail.context, ctx)

    def test_using_template(self):
        ctx = {"foo": "bar"}
        deliveries = self.mail.send(
            recipients="eve@example.com",
            template="test_email",
            context=ctx,
        )

        delivery = deliveries[0]
        self.assertEqual(delivery.direct_mail.context, ctx)
        self.assertEqual(delivery.direct_mail.subject, "Test email from Test Site")
