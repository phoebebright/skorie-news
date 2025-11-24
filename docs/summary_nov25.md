Here’s a consolidated **specification for the newsletter system** we’ve been designing/building. You can save this as a doc, and the bit at the end (“Starter prompt for new chat”) can be pasted into a fresh ChatGPT conversation to continue work.

---

## 1. High-level overview

We’re replacing `django-newsletter` with a custom, Mailgun-based newsletter system that:

* Supports **general newsletters** (Fish Publishing etc.).
* Supports **event-specific messaging** (competitors / event teams / event news).
* Handles **users and guests** (email-only) in a **GDPR-compliant** way.
* Uses **Mailgun Batch API** for sending and webhooks for delivery/engagement events.
* Uses **DRF viewsets** for all APIs.
* Uses **Bootstrap 5 + jQuery** for UI; CSRF is handled globally (no per-call header boilerplate).
* Always uses `settings.SITE_URL` when building absolute URLs for emails and links.

The core concepts are: **Newsletter**, **Subscription**, **Article**, **Issue**, **IssueArticle**, **Mailing (formerly Submission)**, **Delivery**, and **EventDispatch**.

---

## 2. Roles and permissions

### 2.1 Roles

* **Admins**

  * Manage newsletters, issues, articles.
  * Manage subscribers (add, unsubscribe/resubscribe, erase).
  * Send issues to newsletter subscribers.
  * Use “manage subscriptions” admin UI with bulk operations.

* **Event organisers**

  * For a given event:

    * Create quick messages (articles) for event updates.
    * Dispatch them to event channels:

      * Event email (competitors/team).
      * Event news page.
      * Social stubs (Bluesky, Facebook, WhatsApp; currently placeholders).
  * Can only send while `event.is_open` is true (unless an admin override is used).

* **End users (subscribers)**

  * May have a **site account** or be **email-only guests**.
  * Can subscribe/unsubscribe.
  * Can manage subscriptions via:

    * **Authenticated account** (immediate change, no email confirmation).
    * **Manage-by-email flow** (confirm via emailed link using a token).

---

## 3. Data model

### 3.1 Newsletter

`Newsletter(EventMixin, CreatedUpdatedMixin)`

Key fields:

* `title` – name of the newsletter.
* `slug` – unique slug, used in URLs and templates.
* `email` – from address.
* `sender` – from name.
* `visible` – controls if this newsletter is shown in public lists.
* `send_html` – whether HTML part is sent.
* `site` – M2M to `Site` (optional; can limit newsletters per site).

Key methods:

* `__str__() -> str` – returns title.
* URL helpers (optional, used where needed):

  * `get_absolute_url()`
  * `subscribe_url()`
  * `unsubscribe_url()`
  * `archive_url()`
* `get_sender -> str` – returns `"Sender Name <email@example.com>"`.
* `get_templates(action)` – returns `(subject_template, text_template, html_template)` using:

  * `newsletter/message/<slug>/<action>_subject.txt`
  * `newsletter/message/<slug>/<action>.txt`
  * `newsletter/message/<slug>/<action>.html` (if `send_html`).
* `sent_since(dt)` – counts Issues for this newsletter created after `dt`.
* `get_subscriptions()` – returns active `Subscription` queryset for this newsletter.
* `@classmethod get_default()` – returns pk of first newsletter, if any.

### 3.2 Subscription

`Subscription(CreatedUpdatedMixin)`

Represents subscription of a **user OR bare email** to a `Newsletter`.

Fields (simplified / intended):

* `user` – FK to `AUTH_USER_MODEL`, nullable.
* `name` – optional display name.
* `email` – optional email (when no user).
* `ip` – last known IP address (for GDPR auditing).
* `newsletter` – FK to `Newsletter`, related_name=`"subscriptions"`.
* `activation_code` – UUID or token (used for confirmation/unsubscribe links).
* `subscribed` / `subscribe_date`
* `unsubscribed` / `unsubscribe_date`
* Additional GDPR/ops flags (some still conceptual / to be added where needed):

  * `gdpr_erased_at`
  * `bounced`
  * `complained`
  * `email_opt_in`
  * `consent_at`

Constraints / logic:

* Exactly **one of** `user` or `email` must be set (XOR).
* Unique per newsletter:

  * `newsletter + user` (if user is set).
  * `newsletter + email` (if user is null and email is set).
* QuerySet: `Subscription.objects.active()` → currently subscribed and not unsubscribed.

Key methods:

* `__str__()` → `"Name or email → newsletter"`.
* `_subscribe()`, `_unsubscribe()` – internal state helpers.
* `subscribe()` – sets subscribed state and timestamps; saves.
* `unsubscribe()` – sets unsubscribed state and timestamps; saves.

Special flows:

* **GDPR erase** (admin):

  * Should mark subscriber as erased (`gdpr_erased_at`) and remove personally identifying data (name/email) while retaining minimal anonymous stats if needed.
* **Status query for managing page**:

  * For authenticated users or for a verified email in session, we can show all `Subscription` objects for available newsletters.

### 3.3 Article

`Article(CreatedUpdatedMixin)`

Represents a piece of content used in issues or event dispatches.

Fields:

* `title`
* `body_html` – main body (TinyMCE).
* `url` – optional “read more” URL.
* `image` – optional single image (newsletters disable inline upload in TinyMCE).
* `image_position` – one of:

  * `"above"`, `"below"`, `"left"`, `"right"` – relative to text.
* `is_template` – if true, appears in “template library” for reuse.

Relationships:

* `attachments` – reverse FK from `Attachment`.
* `issues` – M2M via `IssueArticle` (Issue–Article join table).
* `event_dispatches` – FK from `EventDispatch`.

Key methods:

* `__str__()` – title.

Rendering:

* `render_html(base_url=None, include_attachments=True, include_title=True) -> str`

  * Uses `settings.SITE_URL` if `base_url` not provided.
  * Builds a full HTML snippet:

    * Optional `<h2>` with title.
    * Image rendered in chosen position with inline styles (email-safe).
    * `body_html` inserted as-is.
    * Optional attachments section (list of links with absolute URLs).
    * Clears floats for left/right images.
* `render_text(base_url=None, include_attachments=True, include_title=True) -> str`

  * Strips HTML tags from `body_html` for a plain-text version.
  * Adds:

    * Title
    * “[Image: URL]”
    * Body text
    * “More: URL” if `url` set
    * “Attachments:” with URLs

These render methods are used for **preview** and for the **email HTML/text parts**.

### 3.4 Attachment

`Attachment(CreatedUpdatedMixin)`

Fields:

* `name` – optional nice label.
* `file` – uploaded file (newsletter article attachment).
* `article` – FK to `Article`, related_name=`"attachments"`.

Properties:

* `file_name` → basename of the file.

### 3.5 Issue (a.k.a. Message / Newsletter Issue)

`Issue(CreatedUpdatedMixin)` (currently named `Message` in code; moving conceptually to “Issue”)

Represents an **issue of a newsletter**, containing one or more articles.

Fields:

* `title`
* `slug` – unique per newsletter; auto-generated from title if missing.
* `newsletter` – FK to `Newsletter`, related_name=`"issues"`.
* `published_at` – when this issue was published to blog (if used).
* `articles` – M2M to `Article` through `IssueArticle`.

Key methods:

* `__str__()` – `"title in newsletter"`.
* `save()` – ensures slug.
* `publish_to_blog()` – sets `published_at` to now.
* `ordered_articles()` – returns `IssueArticle` rows with `article` prefetched, ordered by `position, id`.

Rendering:

* `render_html(base_url=None, include_title=True) -> str`

  * Optional `<h1>` for issue title.
  * For each article (in order):

    * Optional `<hr>` separation.
    * Uses `article.render_html(...)`.
* `render_text(base_url=None, include_title=True) -> str`

  * Issue title + underline.
  * For each article (in order):

    * Separator line of `----`.
    * `article.render_text(...)`.

These are used for **issue preview** and **Mailgun HTML/text parts** for full issues.

### 3.6 IssueArticle

`IssueArticle(models.Model)`

Join table representing placement of an article in a given issue.

Fields:

* `issue` – FK to `Issue`, related_name=`"issue_articles"`.
* `article` – FK to `Article`, related_name=`"issue_links"`.
* `position` – integer order.
* `appear_in_blog` – whether this article should appear in the blog view of the issue.

Meta:

* `ordering = ["position", "id"]`.
* `unique_together = (issue, article)`.

Used for:

* Sorting / reordering articles in the issue via drag-and-drop.
* Filtering which articles show in public blog pages.

### 3.7 Mailing (formerly Submission)

`Submission(CreatedUpdatedMixin)` – named “Submission”, but we plan to rename (e.g. `Mailing`) to avoid clashes with another app’s `Submission`.

Represents **sending of an Issue to subscribers**.

Fields:

* `newsletter` – FK to `Newsletter` (copied from `message.newsletter`).
* `message` – FK to `Issue` (Issue/Message).
* `subscriptions` – M2M to `Subscription` (optional subset; if empty, all active subscribers of the newsletter are used).
* `publish_date` – when it should be considered ready to send (or now).
* `publish` – whether to publish to archive.
* `status` – char, with choices:

  * `"0"` = INACTIVE
  * `"1"` = QUEUED
  * `"2"` = SENDING
  * `"3"` = SENT
  * `"9"` = ERROR

Properties:

* Boolean status helpers:

  * `prepared` (currently treated as always True or conceptually “ready”).
  * `sending`, `sent`, `is_active`, `is_inactive`, `is_queued`, `is_sending`, `is_sent`.

Key methods:

* `save()` – on first save, sets `newsletter` from `message.newsletter`.
* `@classmethod from_message(cls, message)` – creates and saves a new Submission, defaulting recipients to all active subscribers of `message.newsletter`.
* `queue()` – sets status to QUEUED (unless already sent).
* `send_via_mailgun()`:

  * Validates `MAILGUN_DOMAIN` and `MAILGUN_API_KEY`.
  * Resolves recipients:

    * Either `self.subscriptions.active()`, or all from `newsletter.get_subscriptions()`.
  * Renders HTML/text via:

    * `issue.render_html(...)`
    * `issue.render_text(...)`
  * Sends via Mailgun Batch API in chunks (e.g. 1000 recipients).
  * Creates `Delivery` rows for each chunk/recipient.
  * Updates status to SENT.

### 3.8 Delivery

`Delivery(models.Model)`

Tracks individual sending outcomes at least at the chunk/recipient level.

Fields:

* `submission` – FK to `Submission`, related_name=`"deliveries"`.
* `email`
* `mailgun_id` – Mailgun message id.
* `status` – `queued/sent/delivered/failed/opened/...` (Mailgun webhooks will update this).
* `timestamp` – auto_now_add.
* `event` – JSON field to store raw webhook payload (or summarised info).

Used for:

* Admin audit.
* “Events” modal in subscriber admin interface.
* Later: open/click tracking, bounce handling.

### 3.9 EventDispatch

`EventDispatch(EventMixin, CreatedUpdatedMixin)`

Represents sending **one Article** in the context of an **Event** via various channels.

Fields:

* `event` – from `EventMixin`.
* `article` – FK to `Article`, related_name=`"event_dispatches"`.
* Channel flags:

  * `to_email_competitors`
  * `to_email_team`
  * `to_event_news`
  * `to_bluesky`
  * `to_facebook`
  * `to_whatsapp`
* Status:

  * `status` – choice: DRAFT / QUEUED / SENT / FAILED
  * `queued_at`
  * `sent_at`
  * `last_error`

Key methods:

* `can_send(user_is_admin=False)` – checks `event.is_open` unless override.
* `queue(user_is_admin=False)` – sets QUEUED (used if we add background processing).
* `send_now(user_is_admin=False)`:

  * If event closed and not admin, raises.
  * If `to_event_news`: creates `News` row via `_post_to_event_news()`.
  * If `to_email_competitors` or `to_email_team`: uses `_send_email_batches()` with Mailgun.
  * Social stubs exist as placeholder methods.
* `_post_to_event_news()` – maps article → `web.models.News` row.
* `_send_email_batches()` – collects competitor/team emails from event helper methods, sends via Mailgun Batch API.

---

## 4. Public and admin flows

### 4.1 Public subscription / unsubscribe

* **Landing subscribe (general newsletter)**

  * Simple Bootstrap card with email (and optional name).
  * jQuery posts to a DRF endpoint (`SubscriptionManageViewSet.request_subscribe`) with `email`, `name`, `newsletter_slug`.
  * For **guests**, an email is sent with a **confirm link** containing a token; subscription is only activated after confirmation.
  * For **authenticated users**, subscription can be immediate (no extra email).

* **Unsubscribe links in emails**

  * Per-recipient unsubscribe URL like:

    * `SITE_URL/news/unsubscribe/<subscription_uuid>/`
    * or `SITE_URL/news/manage/<manage_token>/?newsletter=...&action=unsubscribe`
  * Token is:

    * Long, random (UUID/secure token).
    * Not guessable and not derived from plain email.
  * On hit:

    * `Subscription` is looked up via token.
    * Unsubscribed immediately.
    * Optional: show manage-subscriptions page with confirmation message.

* **Manage-by-email page (guest)**

  * Page shows:

    * “Login” option.
    * Or “Manage by email” form (enter email).
  * POSTing email hits DRF endpoint to:

    * Create/manage token and email a link: `SITE_URL/news/manage/<token>/`.
    * No info about subscription status is revealed until token is used.
  * Once the token is used, the API stores `managed_email` in session and the UI calls `list_current` via API to fetch subscription states.

### 4.2 Authenticated subscription management

* Logged-in users go to “Manage Subscriptions” page.
* Page uses DRF endpoint (`SubscriptionManageViewSet.list_current`) with subject = user.
* Shows all newsletters and whether subscribed or not.
* Buttons/toggles via AJAX to subscribe/unsubscribe per newsletter.
* No extra email confirmation needed for authenticated changes.

### 4.3 Admin: newsletter dashboard

* Main “News / Newsletter” admin area (not Django admin; custom views).
* Pages (non-exhaustive):

  * Newsletter list.
  * Issue list / edit.
  * Article list / edit.
  * Manage subscribers (with DataTables).
  * Event send UI.

### 4.4 Admin: manage subscribers (newsletter-specific)

* **Template**: `manage_subscribers.html` (extended from `admin/newsletter_base.html`).
* Uses **DataTables** to show subscribers for a given `Newsletter`:

  * Columns: Email/Name, Status, Consent, Sub/Unsub dates, Suppression flags, Actions.
* Toolbar:

  * Add & subscribe a new email+name via API.
  * Bulk actions:

    * Unsubscribe
    * Resubscribe
    * Erase (GDPR)
  * Export CSV.
* Row actions:

  * Events – shows an Events modal (powered by DRF endpoint returning `Delivery` / subscription events).
  * Unsub/Resub per subscriber via AJAX.
  * Erase subscriber.
* All data operations use **DRF viewsets** (`SubscriptionViewSet` / `SubscriptionEvents`), not classic views.

### 4.5 Admin: issue list & edit

* **Issue list**:

  * Shows issues for a newsletter: title, created date, status (has queued/sent mailings), publish_at.
  * Buttons for edit, preview, queue/send.

* **Issue edit**:

  * Top card:

    * Title, newsletter selection.
    * Buttons:

      * Save.
      * Preview (opens HTML preview in new tab or modal – uses `issue.render_html()`).
      * Queue issue for sending (calls DRF API: `IssueViewSet.queue`).
      * Publish to blog (calls `issue.publish_to_blog` via API).
      * Send test email: input for test email; calls `IssueViewSet.send_test`:

        * Prepares Mailgun message using `Issue.render_html()` and `Issue.render_text()`.
  * Articles section:

    * Either:

      * Inline editing (earlier approach), **or**:
      * Dedicated “Manage articles” page with drag-and-drop ordering and “Add article to issue” flows.
    * Uses `IssueArticle` for sorting and appear_in_blog flag.

### 4.6 Article edit & preview

* **Article list**:

  * Shows templates vs regular articles.
  * Filter/search.

* **Article edit**:

  * Uses TinyMCE for `body_html`.
  * Attachments managed via inline formset.
  * Buttons:

    * Save
    * Cancel
    * Preview HTML
    * Preview Text
  * Preview uses:

    * `ArticlePreviewHTMLView` → `article.render_html(...)` displayed in iframe/modal.
    * `ArticlePreviewTextView` → `article.render_text(...)` displayed as `<pre>`.

* On future enhancement:

  * For existing articles, fields may be saved on blur using AJAX per-field.

### 4.7 Event send screen (organisers)

* Form allows organiser to:

  * Either write a quick article (ArticleQuickForm) **or** choose from a template/current library.
  * Set dispatch flags:

    * To competitors, team, event news, socials.
  * Optional “send test” email address:

    * Sends via Mailgun directly to that address without updating dispatch status.
  * “Send now” calls `EventDispatch.send_now()`:

    * Posts to event news.
    * Sends email batches via Mailgun batch API.
    * Social stubs (no-op for now).

---

## 5. API design (DRF & jQuery)

General rules:

* **Always use DRF viewsets** (or APIViews) for new endpoints.
* Authentication:

  * Admin APIs: `IsAuthenticated` + custom `IsAdministratorPermission`.
  * Public subscription/unsubscribe actions: `AllowAny` on specific actions.
  * Manage-by-email: token-based, plus storing `managed_email` in session.
* Frontend JS:

  * Always **jQuery**.
  * CSRF is handled globally (no manual headers needed in most cases).
  * For longer operations (archive, send issue etc.), user is **not blocked** – they can leave the page; Ajax call finishes in background.

Examples of viewsets:

* `SubscriptionViewSet`:

  * Admin: list/retrieve/update/destroy.
  * Public:

    * `subscribe` – for user-based or email-based subscription (optionally immediate).
    * `unsubscribe` – triggered from unsubscribe link.
* `SubscriptionManageViewSet`:

  * `list_current` – returns all newsletters + subscription status for current subject (user or managed email).
  * `request_subscribe` – guest enters email; sends confirmation email with token.
  * `confirm_subscribe` – token-based confirmation.
  * `request_manage` – guest enters email to manage; send management token.
  * `clear_session` – drop `managed_email` from session.
* `IssueViewSet`:

  * Admin only.
  * `queue` – create/queue Submission for an issue.
  * `send_test` – send preview of full issue to a single test email.
* `EventDispatch`:

  * Could use a view or viewset to create/trigger dispatch.

---

## 6. Email & Mailgun integration

* Sending:

  * Uses Mailgun Batch API (`/messages`) with:

    * `from` = `newsletter.get_sender` or default event from.
    * `to` = list of recipient emails (batched).
    * `subject` = rendered from templates (for issues) or article title (for event dispatch).
    * `html` = from `Issue.render_html()` or `Article.render_html()`.
    * `text` = from `Issue.render_text()` or `Article.render_text()`.
    * `recipient-variables` for per-recipient metadata if needed later.
  * `Mailgun` config in settings:

    * `MAILGUN_DOMAIN`
    * `MAILGUN_API_KEY`
    * `MAILGUN_API_URL`
* Webhooks:

  * Not fully specified yet, but `Delivery.event` is ready to store payloads.
  * Later, webhooks can map Mailgun events to `Delivery` and `Subscription`:

    * Bounces → set `bounced` / auto-unsubscribe.
    * Complaints → set `complained`.
    * Opens/clicks → analytics.

---

## 7. Non-functional constraints / conventions

* **Frontend**:

  * Bootstrap 5 only.
  * JavaScript: **always jQuery** (no vanilla-only for new code).
  * DataTables used for heavy admin lists (like subscribers).
  * No explicit CSRF headers in each call; rely on global setup where possible.

* **Backend**:

  * DRF for all new APIs.
  * Use `settings.SITE_URL` for full URLs in emails and absolute links.
  * Keep sending and rendering logic in **model methods** (`render_html`, `render_text`, `send_via_mailgun`, `send_now`, etc.) so templates/views remain thin.

* **Privacy & security**:

  * Manage-by-email and unsubscribe links must use **unguessable tokens** (UUID / `secrets.token_urlsafe`).
  * Never reveal whether an email is subscribed/unsubscribed until the user has authenticated (via login or valid token).
  * GDPR erase must actually clear personal data (not just mark flags).

---

## 8. Starter prompt for a new chat

When you start a fresh chat, you can paste this block as your **first message**:

> I have a Django project with a custom newsletter system that has replaced `django-newsletter`. Key models:
>
> * `Newsletter` – defines a mailing list (title, slug, sender/email, visible, send_html).
> * `Subscription` – links either a user or a bare email to a Newsletter; supports `subscribed/unsubscribed`, timestamps, and will grow GDPR fields (erased, bounced, complained, email_opt_in, consent_at). It enforces XOR between `user` and `email` per newsletter.
> * `Article` – newsletter or event content (title, `body_html`, optional `url`, optional `image` with position ABOVE/BELOW/LEFT/RIGHT, `is_template`). It has `render_html()` and `render_text()` methods that generate the HTML and text email bodies, including image placement and attachment links.
> * `Attachment` – file attached to an Article.
> * `Issue` (currently called `Message` in code) – an issue of a Newsletter. It has title, slug, FK to Newsletter, optional `published_at`, and a ManyToMany to `Article` through `IssueArticle`. It has `render_html()` and `render_text()` which loop over ordered articles and call the article render methods to produce the full email/html preview.
> * `IssueArticle` – join model with `issue`, `article`, `position`, and `appear_in_blog`.
> * `Submission` (to be renamed, e.g. `Mailing`) – represents sending an Issue to subscribers. It has `newsletter`, `message` (Issue), optional M2M `subscriptions`, `publish_date`, `publish`, and a `status` field with states INACTIVE/QUEUED/SENDING/SENT/ERROR, plus helpers and `from_message()` and `send_via_mailgun()` methods. `send_via_mailgun()` uses Mailgun Batch API and creates `Delivery` rows.
> * `Delivery` – tracks individual/email-chunk delivery status and stores Mailgun event JSON.
> * `EventDispatch` – event-specific send of a single Article via channels (competitors/team email via Mailgun, event news, and stubs for social).
>
> All APIs are built with DRF ViewSets, and front-end JS is always jQuery plus Bootstrap 5. CSRF is handled globally and we use `settings.SITE_URL` for building absolute URLs in emails. We have:
>
> * Public subscribe/unsubscribe and manage-my-subscriptions flows (authenticated users and email-only guests with token links).
> * An admin “Manage subscribers” screen per newsletter that uses DataTables and DRF APIs for listing, bulk unsubscribe/resubscribe/erase, and event history via a modal.
> * Issue edit screens with preview, queue, send-test, and publish-to-blog capabilities, using the Issue’s `render_html`/`render_text` for both preview and sending.
> * Article edit screens with TinyMCE and attachments, plus HTML/text preview using the Article’s render methods.
> * An event organiser screen to dispatch a single article to competitors/team/event news via `EventDispatch`.
>
> Please assume this architecture and house-style:
>
> * Always use DRF for APIs.
> * Always use jQuery on the frontend (no vanilla-only).
> * Don’t add ad-hoc CSRF code in each AJAX call; assume a global CSRF setup.
> * Always use `settings.SITE_URL` for absolute URLs in emails.
>
> In this new chat, I’ll paste specific files (models, views, serializers, templates) and I’d like you to help me review, refactor, and extend this newsletter system step by step.

You can tweak that “starter prompt” depending on what you want to work on first (e.g. “let’s focus on manage subscriptions UI”, or “let’s finalise the Mailgun webhook handling”).
