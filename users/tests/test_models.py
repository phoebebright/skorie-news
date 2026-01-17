from unittest import skip
from django.test import TestCase, override_settings
from web.tests.test_models import DCTest
from tools.testing_tools import eq_, ok_, assertDatesMatch as eqdt_
from web.models import *


from django.contrib.auth import get_user_model
User = get_user_model()

@override_settings(TESTING=True)
class TestUser(DCTest):



    def test_setup(self):

        pass


    # probably removing is_unconfirmed - #267
    # def test_is_unconfirmed(self):
    #
    #     new_user = CustomUser.new_user("hi@test.com")
    #     new_user.signup()
    #     new_user.refresh_from_db()
    #
    #
    #     #eq_(new_user.is_anon, False)
    #     eq_(new_user.is_unconfirmed, True)
    #     eq_(new_user.is_registered, False)
    #     eq_(new_user.is_active, True)
    #     eq_(new_user.is_staff, False)
    #     eq_(new_user.is_superuser, False)
    #     eq_(new_user.status, new_user.USER_STATUS_UNCONFIRMED)

    def test_is_registered(self):
        '''once a user has a confirmed email they are registered'''

        new_user = User.objects.create_user("hi@test.com")
        new_user.signup()
        new_user.activate()
        new_user.refresh_from_db()

        #eq_(new_user.is_anon, False)
        eq_(new_user.is_unconfirmed, False)
        eq_(new_user.is_registered, True)
        eq_(new_user.is_active, True)
        eq_(new_user.is_staff, False)
        eq_(new_user.is_superuser, False)
        eq_(new_user.status, new_user.USER_STATUS_TRIAL)


    def test_user_type_list(self):

        newuser = User.objects.create_user(password='12345', email="newuser@skor.ie")
        #eq_(newuser.is_default, True)
        newuser.person.add_roles([ModelRoles.ROLE_MANAGER, ModelRoles.ROLE_COMPETITOR])


        newuser.refresh_from_db()

        #eq_(newuser.is_default, False)
        eq_(newuser.is_manager, True)
        eq_(newuser.is_competitor, True)
        eq_(newuser.is_administrator, False)

    def test_user_roles_no_event(self):
        '''check list of valid roles for this user'''

        # start with a default role
        newuser = User.objects.create_user("hi@test.com")
        default_roles = newuser.user_roles()
        eq_(len(default_roles), 1)

        # add 2 new role
        newuser.person.add_roles([ModelRoles.ROLE_ADMINISTRATOR, ModelRoles.ROLE_COMPETITOR])

        # with description eg. [("A", "Administrator"), ...]
        roles = newuser.user_roles(descriptions=True)
        eq_(len(roles), 3)


        admin_role = [ModelRoles.ROLE_ADMINISTRATOR, ]
        competitor_role = [ModelRoles.ROLE_COMPETITOR, ]
        assert admin_role in roles
        assert competitor_role in roles

        #without description eg ["A", "R"]
        roles = newuser.user_roles(descriptions=False)
        eq_(len(roles), 3)
        admin_role = ModelRoles.ROLE_ADMINISTRATOR
        competitor_role = ModelRoles.ROLE_COMPETITOR
        assert admin_role in roles
        assert competitor_role in roles

    @skip("Not using roles not related to events at the moment")
    def test_user_roles_list_with_event(self):
        '''check list of valid roles for this user including those in current event'''

        new_user = User.objects.create_user("hi@test.com")

        new_user.person.add_roles([ModelRoles.ROLE_ADMINISTRATOR, ModelRoles.ROLE_COMPETITOR])

        eq_(len(new_user.user_roles(event_ref=self.event1.ref)), 3)  # roles assigned + default role
        # print(new_user.user_roles(event_ref=self.event1.ref))
        self.event1.add2team(new_user, [ModelRoles.ROLE_SCORER, ], inviter=self.mary, accept=True)
        # print(new_user.user_roles)
        # print(new_user.user_roles(event_ref=self.event1.ref))

        # pass full list of roles, so in this case you are replacing role of Scorer with role of Writer for this Event
        # BUT, have now created a Role instance of Scorer, so this will be included in the list of non-event roles
        # so the new count is 5 1 event role + 4 non-event roles
        x = EventRole.objects.filter(user=new_user)
        self.event1.add2team(new_user, [ModelRoles.ROLE_WRITER, ],  inviter=self.mary, accept=True)
        # print(new_user.user_roles(event_ref=self.event1.ref))
        eq_(len(new_user.user_roles(event_ref=self.event1.ref)), 5)

        x=EventRole.objects.filter(user=new_user)
        self.event1.add2team(new_user, [ModelRoles.ROLE_WRITER, ModelRoles.ROLE_SCORER], inviter=self.mary, accept=True)
        # print(new_user.user_roles(event_ref=self.event1.ref))
        eq_(len(new_user.user_roles(event_ref=self.event1.ref)), 5)

        #without description
        roles = new_user.user_roles(event_ref=self.event1.ref, descriptions=False)
        eq_(len(roles), 5)
        admin_role = ModelRoles.ROLE_ADMINISTRATOR
        writer_role = ModelRoles.ROLE_WRITER
        assert admin_role in roles
        assert writer_role in roles

        #with description
        roles = new_user.user_roles(event_ref=self.event1.ref, descriptions=True)
        eq_(len(roles), 5)



        admin_role = [ModelRoles.ROLE_ADMINISTRATOR, ModelRoles.ROLES[ModelRoles.ROLE_ADMINISTRATOR]]
        writer_role = [ModelRoles.ROLE_WRITER, ModelRoles.ROLES[ModelRoles.ROLE_WRITER]]
        assert admin_role in roles
        assert writer_role in roles


    def test_set_is_competitor(self):
        '''if the is_competitor attribute is set in the model, make sure a matching Competitor instance can be created'''

        user = User.objects.create_user(password='12345', email="jack@skor.ie")
        user.add_roles([ModelRoles.ROLE_COMPETITOR,])

        user.refresh_from_db()
        eq_(user.is_competitor, True)

        competitor = Role.objects.get(role_type=ModelRoles.ROLE_COMPETITOR, user=user)

        eq_(competitor.user, user)

# tests/test_verification_model.py
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

# Adjust these imports to your app
from users.models import VerificationCode, CommsChannel


@override_settings(
    VERIFICATION_CODE_EXPIRY_MINUTES=20,
    VERIFICATION_MAX_ATTEMPTS=3,
)
class VerificationCodeCodeFlowTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            email="alice@example.com", password="x", is_active=False
        )
        self.channel = CommsChannel.objects.create(
            user=self.user, channel_type="email", value="alice@example.com"
        )

    def test_create_for_code_returns_raw_code_and_hash_is_stored(self):
        obj, context = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")
        self.assertTrue(context['code'].isdigit() and len(context['code']) == 6)
        obj.refresh_from_db()
        # raw code should NOT be stored on the model; only hash/salt present
        self.assertTrue(obj.code_hash)
        self.assertTrue(obj.code_salt)
        self.assertFalse(obj.token_hash)
        self.assertFalse(hasattr(obj, "code"))  # legacy field should be gone

    def test_verify_code_success_sets_consumed_and_calls_channel_verify(self):
        obj, context = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")
        with mock.patch.object(self.channel.__class__, "verify", autospec=True) as m_verify:
            ok = VerificationCode.verify_code(user=self.user, channel=self.channel, code=context['code'], purpose="email_verify")
            self.assertTrue(ok)
            # consumed
            obj.refresh_from_db()
            self.assertIsNotNone(obj.consumed_at)
            # channel.verify() called on the actual instance
            self.channel.refresh_from_db()
            m_verify.assert_called_once_with(self.channel)

    def test_verify_code_fails_with_wrong_code_and_increments_attempts(self):
        obj, context = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")
        for i in range(3):  # VERIFICATION_MAX_ATTEMPTS=3
            ok = VerificationCode.verify_code(user=self.user, channel=self.channel, code="000000", purpose="email_verify")
            self.assertFalse(ok)
            obj.refresh_from_db()
            self.assertEqual(obj.attempts, i + 1)
            self.assertIsNone(obj.consumed_at)

        # Further attempts should still fail (locked by attempts >= MAX)
        ok = VerificationCode.verify_code(user=self.user, channel=self.channel, code=context['token'], purpose="email_verify")
        self.assertFalse(ok)

    def test_verify_code_respects_expiry(self):
        obj, context = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")
        # Force expiry
        VerificationCode.objects.filter(pk=obj.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        ok = VerificationCode.verify_code(user=self.user, channel=self.channel, code=context['code'], purpose="email_verify")
        self.assertFalse(ok)
        obj.refresh_from_db()
        self.assertIsNone(obj.consumed_at)

    def test_verify_code_is_single_use_and_cleans_siblings(self):
        # Create two records (simulate resend) — only the latest is used; on success, siblings are removed
        first, context1 = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")
        # Resend: creation deletes any existing active record
        second, context2 = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")

        # The first should already be gone
        self.assertFalse(VerificationCode.objects.filter(pk=first.pk).exists())

        with mock.patch.object(self.channel.__class__, "verify", autospec=True):
            ok = VerificationCode.verify_code(user=self.user, channel=self.channel, code=context2['code'], purpose="email_verify")
            self.assertTrue(ok)

        # Second is consumed; no other actives remain
        s = VerificationCode.objects.get(pk=second.pk)
        self.assertIsNotNone(s.consumed_at)
        self.assertEqual(
            VerificationCode.objects.filter(
                user=self.user, channel=self.channel, purpose="email_verify", consumed_at__isnull=True
            ).count(),
            0
        )

    def test_verify_code_is_bound_to_user_and_channel(self):
        obj, context = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")

        other_user = self.User.objects.create_user(email="bob@example.com", password="x", is_active=False)
        other_channel = CommsChannel.objects.create(
            user=other_user, channel_type="email", value="bob@example.com"
        )

        # Use token if available, otherwise code
        code_to_use = context.get('token') or context.get('code') or '000000'

        # Wrong user
        ok_wrong_user = VerificationCode.verify_code(user=other_user, channel=self.channel, code=code_to_use, purpose="email_verify")
        self.assertFalse(ok_wrong_user)
        # Wrong channel
        ok_wrong_channel = VerificationCode.verify_code(user=self.user, channel=other_channel, code=code_to_use, purpose="email_verify")
        self.assertFalse(ok_wrong_channel)

    def test_resend_updates_existing_active_code(self):
        # Create first active code
        first_obj, first_context = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")
        first_pk = first_obj.pk
        first_code = first_context['code']
        
        # Resend: should update the same row
        second_obj, second_context = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")
        second_pk = second_obj.pk
        second_code = second_context['code']
        
        self.assertEqual(first_pk, second_pk)
        self.assertNotEqual(first_code, second_code)
        
        # Verify only one row exists
        self.assertEqual(VerificationCode.objects.filter(user=self.user, channel=self.channel, purpose="email_verify").count(), 1)

    def test_duplicate_allowed_if_first_expired(self):
        # Create first code and force expire it
        first = VerificationCode.objects.create(
            user=self.user,
            channel=self.channel,
            purpose="email_verify",
            code_hash="hash1",
            code_salt="salt1",
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        
        # Creating a second one should succeed now because the first is expired
        second = VerificationCode.objects.create(
            user=self.user,
            channel=self.channel,
            purpose="email_verify",
            code_hash="hash2",
            code_salt="salt2",
            expires_at=timezone.now() + timedelta(minutes=20)
        )
        self.assertIsNotNone(second.pk)

    def test_duplicate_allowed_if_first_consumed(self):
        # Create first code and mark as consumed
        first = VerificationCode.objects.create(
            user=self.user,
            channel=self.channel,
            purpose="email_verify",
            code_hash="hash1",
            code_salt="salt1",
            expires_at=timezone.now() + timedelta(minutes=20),
            consumed_at=timezone.now()
        )
        
        # Creating a second one should succeed now because the first is consumed
        second = VerificationCode.objects.create(
            user=self.user,
            channel=self.channel,
            purpose="email_verify",
            code_hash="hash2",
            code_salt="salt2",
            expires_at=timezone.now() + timedelta(minutes=20)
        )
        self.assertIsNotNone(second.pk)

    def test_properties_is_expired_and_is_consumed(self):
        obj, context = VerificationCode.create_for_code(self.user, self.channel, purpose="email_verify")
        self.assertFalse(obj.is_expired)
        self.assertFalse(obj.is_consumed)
        # consume
        with mock.patch.object(self.channel.__class__, "verify", autospec=True):
            self.assertTrue(VerificationCode.verify_code(user=self.user, channel=self.channel, code=context['token'], purpose="email_verify"))
        obj.refresh_from_db()
        self.assertTrue(obj.is_consumed)
        # expire manually
        VerificationCode.objects.filter(pk=obj.pk).update(expires_at=timezone.now() - timedelta(days=1))
        obj.refresh_from_db()
        self.assertTrue(obj.is_expired)


@override_settings(
    VERIFICATION_CODE_EXPIRY_MINUTES=20,
)
class VerificationCodeMagicLinkTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            email="carol@example.com", password="x", is_active=False
        )
        self.channel = CommsChannel.objects.create(
            user=self.user, channel_type="email", value="carol@example.com"
        )

    def test_create_for_magic_link_stores_only_token_hash(self):
        obj, context = VerificationCode.create_for_magic_link(self.user, self.channel, purpose="email_verify")
        obj.refresh_from_db()
        self.assertTrue(obj.token_hash)
        self.assertFalse(obj.code_hash)
        self.assertFalse(obj.code_salt)
        self.assertTrue(isinstance(context['raw_token'], str) and len(context['token']) > 20)  # urlsafe token

    def test_verify_token_success_consumes_and_cleans_siblings(self):
        first, context1 = VerificationCode.create_for_magic_link(self.user, self.channel, purpose="email_verify")
        second, context2 = VerificationCode.create_for_magic_link(self.user, self.channel, purpose="email_verify")

        with mock.patch.object(self.channel.__class__, "verify", autospec=True) as m_verify:
            obj = VerificationCode.verify_token(raw_token=context1['token'], purpose="email_verify")
            self.assertIsNotNone(obj)
            m_verify.assert_called_once_with(self.channel)

        # second is consumed, first is deleted by cleanup
        self.assertTrue(VerificationCode.objects.filter(pk=second.pk).exists())
        self.assertIsNotNone(VerificationCode.objects.get(pk=second.pk).consumed_at)
        self.assertFalse(VerificationCode.objects.filter(pk=first.pk).exists())

        # Reuse should fail
        obj_again = VerificationCode.verify_token(raw_token=context2['token'], purpose="email_verify")
        self.assertIsNone(obj_again)

    def test_verify_token_respects_expiry_and_wrong_token(self):
        obj, context = VerificationCode.create_for_magic_link(self.user, self.channel, purpose="email_verify")
        t = context["token"]
        # Expire it
        VerificationCode.objects.filter(pk=obj.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(VerificationCode.verify_token(raw_token=t, purpose="email_verify"))
        # Wrong token
        self.assertIsNone(VerificationCode.verify_token(raw_token="not-a-real-token", purpose="email_verify"))

    def test_verify_token_bound_to_purpose(self):
        obj, context = VerificationCode.create_for_magic_link(self.user, self.channel, purpose="email_verify")
        t = context["token"]
        self.assertIsNone(VerificationCode.verify_token(raw_token=t, purpose="login"))  # wrong purpose
        # Correct purpose works
        self.assertIsNotNone(VerificationCode.verify_token(raw_token=t, purpose="email_verify"))
