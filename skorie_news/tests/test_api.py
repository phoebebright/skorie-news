# skorie_news/tests/test_message_api.py
from django.test import TestCase
from django.urls import reverse, NoReverseMatch
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from skorie_news.models import Mailing, Issue, Newsletter

User = get_user_model()

class QueueSubmissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="pass"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_queue_submission_creates_submission(self):
        nl = Newsletter.objects.create(title="Test List", slug="test")
        msg = Issue.objects.create(title="Hello", newsletter=nl)

        # Action name is create-mailing because @action(detail=True, methods=['post'])
        # defaults to method name with underscores replaced by hyphens.
        for name in ["news-issue-create-mailing", "skorie_news:news-issue-create-mailing",
                    "issue-create-mailing", "skorie_news:issue-create-mailing"]:
            try:
                url = reverse(name, args=[msg.pk])
                break
            except NoReverseMatch:
                continue
        
        if not url:
            self.fail("Could not reverse 'skorie_news-issue-create-mailing'")
             
        resp = self.client.post(url)

        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

        sub = Mailing.objects.get(pk=data["submission_id"])
        self.assertEqual(sub.message, msg)
        self.assertEqual(sub.newsletter, nl)
