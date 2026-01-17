# tests/test_send_verification_code.py
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from rest_framework.test import APIRequestFactory, force_authenticate

# ==== Adjust these imports to your app ====
from users.models import VerificationCode, CommsChannel             # <-- adjust if your app label differs
from django_users.api import SendVerificationCode                          # <-- adjust: module where the view lives


class SendVerificationCodeBase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            email="alice@example.com", password="x", is_active=False
        )
        # Start without a channel in some tests; we’ll create on demand
        self.channel = CommsChannel.objects.create(
            user=self.user, channel_type="email", value="alice@example.com"
        )

        # Disable throttling for these unit tests by clearing the view's throttle classes
        SendVerificationCode.throttle_classes = []


@override_settings(
    VERIFICATION_USE_MAGIC_LINK=True,
    VERIFICATION_CODE_EXPIRY_MINUTES=20,
    VERIFICATION_SEND_COOLDOWN_MINUTES=2,
    SITE_ORIGIN="https://example.test",
)
class SendVerificationCodeMagicLinkTests(SendVerificationCodeBase):
    def _post(self, payload):
        view = SendVerificationCode.as_view()
        req = self.factory.post("/api/send-code/", payload, format="json")
        return view(req)

    def _get(self, email):
        view = SendVerificationCode.as_view()
        req = self.factory.get(f"/api/send-code/?email={email}")
        return view(req)

    @mock.patch("django_users.utils.send_email_magic_link", return_value=True)       # <-- adjust path if needed
    def test_happy_path_magic_link_sends_mail_and_creates_token(self, m_send):
        resp = self._post({"email": "alice@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"status": "ok"})

        vc = VerificationCode.objects.filter(user=self.user, purpose="email_verify").latest("created_at")
        self.assertTrue(vc.token_hash)              # token stored hashed
        self.assertFalse(vc.code_hash)              # no 6-digit code in magic-link mode

        # Mailer called once with verify_url
        self.assertTrue(m_send.called)
        kwargs = m_send.call_args.kwargs
        self.assertEqual(kwargs["user"], self.user)
        self.assertEqual(kwargs["channel"].user_id, self.user.id)
        self.assertIn("verify_url", kwargs)
        self.assertTrue(str(kwargs["verify_url"]).startswith("https://example.test/"))

    @mock.patch("django_users.utils.send_email_magic_link", return_value=True)
    def test_no_user_enumeration_nonexistent_email(self, m_send):
        resp = self._post({"email": "nobody@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"status": "ok"})
        m_send.assert_not_called()
        self.assertFalse(VerificationCode.objects.exists())

    @mock.patch("django_users.utils.send_email_magic_link", return_value=True)
    def test_invalid_email_returns_generic_ok(self, m_send):
        resp = self._post({"email": "not-an-email"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"status": "ok"})
        m_send.assert_not_called()

    @mock.patch("django_users.utils.send_email_magic_link", return_value=True)
    def test_creates_email_channel_if_missing(self, m_send):
        # Remove existing channel
        CommsChannel.objects.filter(user=self.user, channel_type="email").delete()
        resp = self._post({"email": "alice@example.com"})
        self.assertEqual(resp.status_code, 200)

        self.assertTrue(
            CommsChannel.objects.filter(user=self.user, channel_type="email", value="alice@example.com").exists()
        )
        self.assertTrue(VerificationCode.objects.filter(user=self.user).exists())
        self.assertTrue(m_send.called)

    @mock.patch("django_users.utils.send_email_magic_link", return_value=True)
    def test_cooldown_prevents_spam(self, m_send):
        # First send
        resp1 = self._post({"email": "alice@example.com"})
        self.assertEqual(resp1.status_code, 200)
        self.assertTrue(m_send.called)
        first_count = VerificationCode.objects.count()

        m_send.reset_mock()
        # Second send within cooldown window — should not create another nor send
        resp2 = self._post({"email": "alice@example.com"})
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(VerificationCode.objects.count(), first_count)
        m_send.assert_not_called()

    @mock.patch("django_users.utils.send_email_magic_link", return_value=True)
    def test_get_legacy_delegates_to_post(self, m_send):
        resp = self._get("alice@example.com")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"status": "ok"})
        self.assertTrue(m_send.called)


@override_settings(
    VERIFICATION_USE_MAGIC_LINK=False,   # switch to 6-digit code path
    VERIFICATION_CODE_EXPIRY_MINUTES=20,
    VERIFICATION_SEND_COOLDOWN_MINUTES=0,  # disable cooldown to simplify
)
class SendVerificationCodeCodeFlowTests(SendVerificationCodeBase):
    def _post(self, payload):
        view = SendVerificationCode.as_view()
        req = self.factory.post("/api/send-code/", payload, format="json")
        return view(req)


    def test_happy_path_code_flow_sends_code_and_stores_hash(self):
        resp = self._post({"email": "alice@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"status": "ok"})

        vc = VerificationCode.objects.filter(user=self.user, purpose="email_verify").latest("created_at")
        self.assertTrue(vc.code_hash)
        self.assertTrue(vc.code_salt)
        self.assertFalse(vc.token_hash)

        vc.send_verification()



    @mock.patch("django_users.utils.send_email_verification_code", return_value=True)
    def test_resend_replaces_previous_active_record(self, m_send):
        # First send
        self._post({"email": "alice@example.com"})
        first_ids = list(VerificationCode.objects.filter(user=self.user).values_list("id", flat=True))

        # Second send should delete previous active (due to single-active policy in create_* methods)
        self._post({"email": "alice@example.com"})
        second_ids = list(VerificationCode.objects.filter(user=self.user).values_list("id", flat=True))

        # There should be exactly one active row after second send
        self.assertEqual(len(second_ids), 1)
        # And it should be different from the first
        self.assertNotEqual(set(first_ids), set(second_ids))
