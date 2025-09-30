
We are building a comprehensive newsletter/messaging system integrated into an existing Django project. The system will handle subscriptions, newsletter issues, articles, and event-based dispatches, with a focus on security, usability, and admin management.  This system is partly done so I want you review the requirements and design and I will upload the existing code in chunks for you to review and suggest improvements.  Start by summarising the steps required to understand where we are now and how to proceed

### Rules for Code in the New Context

1. **No CSRF tokens in AJAX** – assume CSRF middleware/exemption is already handled globally.
2. **Always use jQuery** for AJAX and DOM manipulation.
3. **Always use DRF** for APIs (never plain Django views for data).
4. **Always use `settings.SITE_URL`** when constructing absolute links for emails or external pages.
5. **Admin/management pages** should use Bootstrap 5 + jQuery (optionally DataTables for tables).
6. **Email sending** must use **Mailgun Batch API directly** (not Django email backend).
7. **Secure unsubscribe links** always via tokenized URLs.
8. **Tests** must mock Mailgun network calls but still exercise DB updates.



### Models

* **Newsletter**: basic info (title, slug, sender, email, visibility).
* **Subscription**: can belong to a `User` or just an email. Tracks subscribe/unsubscribe dates, GDPR compliance, and activation codes.
* **Article**: has `title`, `body_html`, optional image with position (above/below/left/right), optional `is_template`. Supports attachments.
* **Issue**: a newsletter issue, `ManyToMany` to `Article` through `IssueArticle` (with order + appear\_in\_blog flag). Can be published to a blog.
* **Mailing**: represents sending an `Issue` to subscribers. Tracks status (queued, sending, sent, error). Uses **Mailgun Batch API** for sending. Creates **Delivery** records.
* **Delivery**: one row per recipient send attempt (email, mailgun\_id, status, event JSON).
* **EventDispatch**: used by event organisers to send a single `Article` to multiple channels (email, event news, Bluesky, FB, WhatsApp).

### Key Features

* Subscriptions:

  * **Users**: immediate subscribe/unsubscribe, reversible.
  * **Guests (email only)**: require confirmation links for subscribe/unsubscribe.
  * **Manage subscriptions page**:

    * Authenticated users → see/manage their subscriptions.
    * Guests → enter email, receive confirmation link.
    * Supports “unsubscribe from all”.
* Sending:

  * **Admins**: can create Issues with multiple Articles, queue/send them to newsletter subscribers, publish to blog.
  * **Admins**: can also do a “Quick Article” (wraps into an Issue automatically).
  * **Event Organisers**: can create Articles and dispatch them to event subscribers + channels. Limited to open events (`event.is_open`).
* Email:

  * Uses **Mailgun Batch API** directly. 
  * All emails include a secure **unsubscribe link** (`/news/unsubscribe/<token>/`).
  * Test sends supported for both Articles and Issues.

### Admin / Frontend

* Admin pages:

  * **Issue form**: edit details, preview, queue, publish to blog, send test.
  * **Article form**: create/edit articles (with TinyMCE), reuse templates, attach files.
  * **Manage subscribers**: searchable, bulk unsubscribe/resubscribe/erase, view subscription events.
  * Tables being converted to **DataTables** for pagination/filtering.
* Frontend landing page:

  * Simple “subscribe by email” form (AJAX → API).
  * Info about newsletter being brought in-house.

### DRF APIs

* **SubscriptionViewSet**: core subscriber management.
* **SubscriptionManageViewSet**: for self-service manage/unsubscribe (auth user or verified guest email in session).
* **AdminSubscriberViewSet**: admin-only, with list/create/bulk actions and per-row actions. Supports `/events/` to show Delivery history.
* **IssueViewSet**: queue, send test, publish to blog.
* **ArticleViewSet**: CRUD for articles.
* **EventDispatchViewSet**: create/queue/send event articles.
