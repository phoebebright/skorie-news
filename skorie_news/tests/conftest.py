import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")  # your module

import django
django.setup()

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.template import Template

from skorie_news.models import Newsletter, Subscription, Article, Issue  # adjust import path

User = get_user_model()

@pytest.fixture
def user(db):
    return User.objects.create_user(username="u1", email="u1@example.com", password="x")

@pytest.fixture
def staff(db):
    return User.objects.create_user(username="staff", email="staff@example.com", password="x", is_staff=True)

@pytest.fixture
def newsletter(db):
    return Newsletter.objects.create(
        title="General", slug="general",
        email="no-reply@example.com", sender="Skorie"
    )

@pytest.fixture
def article_tmpl(db):
    return Article.objects.create(
        title="Welcome {{ user.email }}",
        body_text="Hello {{ user.email }}",
        body_html="<p>Hello {{ user.email }}</p>",
        is_template=True,
        template_type=Article.TEMPLATE_TYPE_EMAIL,
    )

@pytest.fixture
def issue(db, newsletter):
    return Issue.objects.create(title="September Update", newsletter=newsletter)

@pytest.fixture
def mailgun_ok(monkeypatch):
    """
    Mock requests.post used in Mailing.send_via_mailgun and DirectEmail.send.
    Returns {"id": "<2025.abc@mg.example.com>"} and 200.
    """
    class Resp:
        status_code = 200
        def raise_for_status(self): return None
        def json(self): return {"id": "<2025.abc@mg.example.com>"}
        text = '{"id":"<2025.abc@mg.example.com>"}'
    def fake_post(url, auth=None, data=None, timeout=None):
        # You can assert basics here if you want:
        assert "messages" in url
        assert data.get("subject")
        return Resp()
    monkeypatch.setattr("skorie_news.models.requests.post", fake_post)
    return True

@pytest.fixture
def monkeypatch_newsletter_templates(monkeypatch):
    """
    Force Newsletter.get_templates to avoid filesystem templates in tests.
    """
    def fake_get_templates(self, action):
        assert action == "message"
        return (
            Template("Subject for {{ message.title }}"),
            Template("Text for {{ message.title }} to {{ subscription.email|default:'*' }}"),
            Template("<p>HTML for {{ message.title }}</p>"),
        )
    monkeypatch.setattr(Newsletter, "get_templates", fake_get_templates)
