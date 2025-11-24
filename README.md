# Implementing

## settings

add 'news' to INSTALLED_APPS

May want:

             os.path.join(BASE_DIR, 'templates/newsletter'),

And require:
? but some of these from days of using django-newsletter so not sure if all still needed.

    USE_SUBSCRIBE = True    # provide a subscribe to newsletter option, false to hide

    USE_NEWSLETTER = True

    # these 3 used?
    NEWSLETTER_THUMBNAIL = 'sorl-thumbnail'
    NEWSLETTER_CONFIRM_EMAIL = False
    NEWSLETTER_RICHTEXT_WIDGET = "tinymce.widgets.TinyMCE"



    NEWSLETTER_FROM_EMAIL = "email@skor.ie"
    NEWSLETTER_SENDER = "News From"
    


    NEWSLETTER_GENERAL_SLUG = None.  <--- use this one

    SIGNATURE = "Skorie Support Team, info@skor.ie"

## Include in base.html

          SUBSCRIBE_ME_API_URL = "{% url "newsapi:subscribe_me" %}";
          UNSUBSCRIBE_ME_API_URL = "{% url "newsapi:unsubscribe_me" %}";

## Include in urls.py

    path('api/n1/', include(('skorie_news.urls_api', 'skorie_news'), namespace='newsapi')),
    path('news/', include('skorie_news.urls', namespace="news")),

## Scenarios

table shows differnt possible scenarios.  Not that iContact is the temporary flow for people clicking on a link in a iContact email and to say they want to continue receiving emails.  This will be removed when iContact is no longer used.

### Process for Subscribe
- Guest (email only) - request subscribe, subscribe record is created and confirmation email sent.  On clicking link in email, record is updated to subscribed=True and consent recorded.  Subscription is now active and a confirmation email is sent.
- User (logged in) - request subscribe and immediately confirmed and activated.  No confirmation email sent.
- Admin creating Guest - Subscription created and confirmed.  Optional confirmation email sent.
- Admin creating User - Subscription created and confirmed.  Optional confirmation email sent.
- User (not logged in) - as Guest

### Process for Unsubscribe
- Guest and User - request unsubscribe, all matching records set to unsubscribed=True and active = False. Consent is cleared in case of resubscribe - record still in event log Confirmation email sent.  No confirmation of unsubscribe required.
- Admin - as Gues and User. Optional confirmation email sent.


| #  | Who added         | Is User | Logged in? | Existing status (by newsletter+email) | System action                                                                            | Resulting state                                         | User-facing message                                          | Test | Done |
| -- | ----------------- | ------- | ---------- | ------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------ | ---- | ---- |
| 1  | iContact          | No      | N/A         | **No record**                         | Create **email-only** subscription; **record consent**                                   | `subscribed=True`, `user=None`, `active=True`           | “You are subscribed.”                                        | X    | n/a  |
| 2  | iContact          | Yes     | N/A         | **No record**                         | Create subscription; **record consent**; **auto-link to user by email**                  | `subscribed=True`, `user=user`, `active=True`           | “You are subscribed.”                                        | X    | n/a  |
| 3  | Guest             | No      | N/A         | **No record**                         | Create **email-only** subscription; **send confirmation**; consent captured on follow-up | `subscribed=True`, `user=None`, `active=False`          | “We’ve sent a confirmation email. Or log in to confirm now.” | X    |      |
| 4  | Guest             | No      | N/A         | **Already subscribed**                | No change                                                                                | unchanged                                               | “You’re already subscribed.”                                 | X    |      |
| 5  | Guest             | No      | N/A         | **Previously unsubscribed**           | **Treat as re-subscribe**; set pending; **resend confirmation** (no auto-activation)     | `subscribed=True`, `unsubscribed=False`, `active=False` | “We’ve sent a confirmation email to re-subscribe.”           | X    |      |
| 6  | Guest             | Yes     | N/A        | **No record**                         | Create subscription linked to current user; **record consent**                           | `subscribed=True`, `user=request.user`, `active=True`   | “You are subscribed.”                                        | X    |      |
| 7  | Guest             | Yes     | N/A        | **Already subscribed**                | If duplicate email-only exists, **merge** (keeper=user), else no-op                      | consolidated                                            | “You’re already subscribed.”                                 |      |      |
| 8  | Guest             | Yes     | N/A        | **Previously unsubscribed**           | **Block auto-activation**; require **new consent** (login confirm or email link)         | pending until consent                                   | “Previously unsubscribed—please confirm to re-subscribe.”    |      |      |
| 9  | User (self-serve) | Yes     | Yes        | **No record**                         | Create subscription; **record consent**                                                  | `subscribed=True`, `user=request.user`, `active=True`   | “You are subscribed.”                                        |      |      |
| 10 | User (self-serve) | Yes     | Yes        | **Already subscribed**                | No change (or merge email-only dup → keeper=user)                                        | consolidated/unchanged                                  | “Already subscribed.”                                        |      |      |
| 11 | User (self-serve) | Yes     | Yes        | **Previously unsubscribed**           | **Re-subscribe pending**, then **activate on new consent**                               | pending → active on consent                             | “Please confirm to re-subscribe.”                            |      |      |
| 12 | Admin             | No      | Yes        | **No record**                         | Create **email-only** subscription; **record consent**                                   | `subscribed=True`, `user=None`, `active=True`           | “Subscription created.”                                      |      |      |
| 13 | Admin             | Yes     | Yes        | **No record**                         | Create subscription linked to chosen user; **record consent**                            | `subscribed=True`, `user=<chosen>`, `active=True`       | “Subscription created.”                                      |      |      |
| 14 | Admin             | either  | Yes        | **Already subscribed**                | No-op (or merge duplicates per rules)                                                    | consolidated/unchanged                                  | “Already subscribed.”                                        |      |      |
| 15 | Admin             | either  | Yes        | **Previously unsubscribed**           | **Do not** auto-activate; require **new consent**                                        | pending until consent                                   | “Manual re-subscribe required (confirm to activate).”        |      |      |


## Unsubscribe

| Who initiated     | Logged in? | Existing status  | System action                                                                                                                | Resulting state                            | User-facing message                | Done |
| ----------------- | ---------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------- | --- |
| Guest             | No         | **Active subscription**               | Unsubscribe **all** rows for this (newsletter, email); set `unsubscribed=True`, `unsubscribe_date=now`, `email_opt_in=False` | All matching rows unsubscribed             | “You’re unsubscribed. Sorry to see you go.”                      |
| Guest             | No         | **Already unsubscribed**              | No-op                                                                                                                        | unchanged                                  | “You’re already unsubscribed.”                                   |
| Guest             | No         | **No record**                         | No-op (optionally create a suppression record)                                                                               | unchanged (or new `unsubscribed=True` row) | “We couldn’t find a subscription for this address.”              |
| Guest             | Yes        | **Active subscription**               | Same as above; also detach from user if needed later                                                                         | All matching rows unsubscribed             | “You’re unsubscribed.”                                           |
| Guest             | Yes        | **Already unsubscribed**              | No-op                                                                                                                        | unchanged                                  | “Already unsubscribed.”                                          |
| Guest             | Yes        | **No record**                         | No-op (or create suppression)                                                                                                | unchanged                                  | “No active subscription found.”                                  |
| User | No         | **Active subscription**               | Unsubscribe all matching rows (email-only + any linked)                                                                      | All matching rows unsubscribed             | “You’re unsubscribed. Manage preferences anytime by logging in.” |
| User | No         | **Already unsubscribed**              | No-op                                                                                                                        | unchanged                                  | “Already unsubscribed.”                                          |
| User | No         | **No record**                         | No-op (or create suppression)                                                                                                | unchanged                                  | “No active subscription found.”                                  |
| User | Yes        | **Active subscription**               | Unsubscribe rows for (newsletter, email) **and** any row for (newsletter, user)                                              | All user/email rows unsubscribed           | “You’re unsubscribed.”                                           |
| User | Yes        | **Already unsubscribed**              | No-op                                                                                                                        | unchanged                                  | “Already unsubscribed.”                                          |
| User | Yes        | **No record**                         | No-op (or create suppression)                                                                                                | unchanged                                  | “No active subscription found.”                                  |
| Admin             | No         | **Active subscription**               | Unsubscribe all rows for (newsletter, email); log admin actor                                                                | All matching rows unsubscribed             | “Unsubscribed.”                                                  |
| Admin             | No         | **Already unsubscribed**              | No-op                                                                                                                        | unchanged                                  | “Already unsubscribed.”                                          |
| Admin             | No         | **No record**                         | **Create suppression row** (`unsubscribed=True`, `user=None`, store email)                                                   | Suppression active                         | “Suppression added (no subscription existed).”                   |
| Admin             | Yes        | **Active subscription**               | Unsubscribe all rows for (newsletter, email) and/or (newsletter, user)                                                       | All matching rows unsubscribed             | “Unsubscribed.”                                                  |
| Admin             | Yes        | **Already unsubscribed**              | No-op                                                                                                                        | unchanged                                  | “Already unsubscribed.”                                          |
| Admin             | Yes        | **No record**                         | **Create suppression row** (helps prevent accidental re-subscribe)                                                           | Suppression active                         | “Suppression added.”                                             |


# Install

- add to requirements.txt and run pip install
- Add settings as above
- Add a general newsletter to the newsletter model - give it slug general unless you feel strongly.

### Copy templates
copy news directory in template

### Update URLs

    path('api/n1/', include('skorie_news.urls_api')),
    path('news/', include('skorie_news.urls')),

    from news.api import SubscriptionAdminViewSet as NewsSubscriptionViewSet, \
    SubscriberEventListAPIView, ArticleViewSet, IssueViewSet, \
    SubscriptionPublicViewSet, MailingViewSet, AdminSubscriberViewSet, AdminSubscriptionROViewSet, SubscribeMe, UnSubscribeMe
    
    # news/newsletter APIs
    router.register(r'news/subscription', NewsSubscriptionViewSet, basename='news-subscription-api')
    router.register(r"news/subscription-manage", SubscriptionPublicViewSet, basename="news-sub-manage")  # public endpoint
    # router.register(r'news/admin/subscribers', AdminSubscriberViewSet, basename='news-admin-subscribers')
    router.register(r'news/admin/subscribers', AdminSubscriptionROViewSet, basename='news-admin-subscribers')
    router.register(r'news/mailing', MailingViewSet, basename='news-mailing-api')
    router.register(r"news/articles", ArticleViewSet, basename="news-article")
    router.register(r"news/issues",   IssueViewSet,   basename="news-issue")
    
    path('api/v2/subscribe_me/', SubscribeMe.as_view(), name="subscribe_me"),  # assume user is logged in and just default newsletter
    path('api/v2/unsubscribe_me/', UnSubscribeMe.as_view(), name="unsubscribe_me"),# assume user is logged in and just default newsletter
    path("api/v2/news/subscribers/<int:pk>/events/", SubscriberEventListAPIView.as_view(),
         name="news-subscriber-events"),
    
    path('news/', include('news.urls', namespace='news')),

# TODO
- expire subscriptions that are not confirmed
