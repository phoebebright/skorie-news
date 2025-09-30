# news/tests/test_message_api.py
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from news.models import Mailing, Issue, Newsletter

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

        url = reverse("news-issue-api-queue", args=[msg.pk])
        resp = self.client.post(url)

        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

        sub = Mailing.objects.get(pk=data["submission_id"])
        self.assertEqual(sub.message, msg)
        self.assertEqual(sub.newsletter, nl)
