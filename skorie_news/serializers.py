# skorie_news/api/serializers.py
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils.html import linebreaks
from rest_framework import serializers
from .models import Newsletter, Subscription, Issue, Mailing, Article, SubscriptionEvent, IssueArticle, DirectEmail

User = get_user_model()

class SubscriptionSerializer(serializers.ModelSerializer):
    # Use the newsletter slug publicly
    newsletter = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Newsletter.objects.all()
    )

    class Meta:
        model = Subscription
        fields = ["id", "newsletter", "email", "name", "created"]
        read_only_fields = ["id", "created"]



class SubscriptionEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionEvent
        fields = ("event", "at", "ip", "user_agent", "meta")


class ArticleSerializer(serializers.ModelSerializer):
    issue = serializers.PrimaryKeyRelatedField(
        queryset=Issue.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    issue_id = serializers.IntegerField(source="issue.id", read_only=True, required=False, allow_null=True)

    class Meta:
        model = Article
        fields = (
            "id",
            "title",
            "body_html",
            "url",
            "image",
            "image_position",
            "is_template",
            "created",
            "updated",
            "issue",       # for linking
            "issue_id",    # for output
        )

    def create(self, validated_data):
        issue = validated_data.pop("issue", None)
        article = super().create(validated_data)

        if issue:
            IssueArticle.objects.create(issue=issue, article=article)

        return article

class ArticleOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order = serializers.IntegerField()
    appear_in_blog = serializers.BooleanField()

    def validate_id(self, value):
        if not Article.objects.filter(id=value).exists():
            raise serializers.ValidationError("Article with this id does not exist.")
        return value

class IssueArticleSerializer(serializers.ModelSerializer):
    # Flatten for the UI
    article_id = serializers.IntegerField(source="article.id", read_only=True)
    article_title = serializers.CharField(source="article.title", read_only=True)

    class Meta:
        model = IssueArticle
        fields = ("id", "article_id", "article_title", "position", "appear_in_blog")

class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Issue
        fields = ("id", "title", "slug", "newsletter", "published_at", "created", "updated")

class IssueArticlesUpdateSerializer(serializers.Serializer):
    """
    Payload for reordering and blog flags.
    articles: [{article: <id>, position: <int>, appear_in_blog: <bool>}]
    """
    articles = serializers.ListField(
        child=serializers.DictField(child=serializers.JSONField())
    )

    def validate_articles(self, value):
        # minimal validation
        for item in value:
            if "article" not in item:
                raise serializers.ValidationError("Each item needs 'article'.")
        return value

class SubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mailing
        fields = ("id", "status", "publish_date")

# assume we only ever see subscriptions for one newsletter
class SubscriptionManageDTSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    user_link = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ["id", "newsletter_id",
            "email", "subscribe_date", "unsubscribe_date",
            "consent_at", "status","user_link"
        ]

    def get_status(self, obj):
        if obj.unsubscribe_date:
            return "unsubscribed"
        return "active"

    def get_user_link(self, obj):
        if obj.user:
            return f'/admin/auth/user/{obj.user.id}/change/'
        return None



class DirectEmailPreviewSerializer(serializers.Serializer):
    article_id = serializers.PrimaryKeyRelatedField(
        queryset=Article.objects.filter(is_template=True, template_type=Article.TEMPLATE_TYPE_EMAIL),
        source="article"
    )
    receiver_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True, source="receiver"
    )
    to_email = serializers.EmailField(required=False, allow_blank=True)
    # optional: future-proof
    context = serializers.JSONField(required=False)

    def validate(self, attrs):
        receiver = attrs.get("receiver")
        to_email = attrs.get("to_email") or (receiver.email if receiver else None)
        if not to_email:
            raise serializers.ValidationError({"to_email": "Recipient email is required."})
        attrs["to_email"] = to_email.strip().lower()
        return attrs

    def to_representation(self, instance):
        # not used — preview returns render only
        return super().to_representation(instance)


class DirectEmailCreateSerializer(serializers.ModelSerializer):
    # sending an email direct to someone - text may be been created with a template (article) or not
    article = serializers.PrimaryKeyRelatedField(required=False,allow_null=True,
        queryset=Article.objects.filter(is_template=True, template_type=Article.TEMPLATE_TYPE_EMAIL)
    )
    receiver = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True
    )
    to_email = serializers.EmailField()
    subject_override = serializers.CharField()
    body_text_override = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = DirectEmail
        fields = ["article", "receiver", "to_email", "subject_override", "body_text_override", "context"]

    def validate(self, attrs):
        receiver = attrs.get("receiver")
        to_email = attrs.get("to_email") or (receiver.email if receiver else None)
        if not to_email:
            raise serializers.ValidationError({"to_email": "Recipient email is required."})
        attrs["to_email"] = to_email.strip().lower()
        return attrs

    def create(self, validated):
        # NOTE: no sending here
        request = self.context["request"]
        direct = DirectEmail(
            article=validated["article"],
            sender=request.user,                 # set sender here
            receiver=validated.get("receiver"),
            to_email=validated["to_email"],
        )
        direct.render(validated.get("context"), save=True)
        if s := validated.get("subject_override"):
            direct.subject = s
            direct.save()
        if s := validated.get("body_text_override"):
            direct.body_text = s
            direct.body_html = linebreaks(s)
            direct.save()
        return direct


class DirectEmailReadSerializer(serializers.ModelSerializer):
    article_title = serializers.CharField(source="article.title", read_only=True)
    receiver_username = serializers.CharField(source="receiver.get_username", read_only=True)

    class Meta:
        model = DirectEmail
        fields = '__all__'
