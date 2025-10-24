from anymail.signals import tracking
from django.dispatch import receiver
from .models import Delivery, DeliveryEvent

ROLLUP_STATE_MAP = {
    "delivered": "delivered",
    "opened": "opened",
    "clicked": "clicked",
    "bounced": "failed",
    "rejected": "rejected",
    "complained": "complained",
    "unsubscribed": "unsubscribed",
    "sent": "sending",
    "queued": "queued",
    "deferred": "sending",
}

@receiver(tracking)
def handle_anymail_event(sender, event, esp_name, **kwargs):
    # event.message_id, event.event_type, event.timestamp, event.recipient, event.click_url, event.esp_event, ...
    try:
        delivery = Delivery.objects.get(message_id=event.message_id)
    except Delivery.DoesNotExist:
        # optionally: try fallback via email+recent created
        return

    # Idempotency (Mailgun/others include unique event id)
    esp_event_id = event.esp_event.get("id") or event.event_id or None
    if esp_event_id:
        if DeliveryEvent.objects.filter(esp_event_id=esp_event_id).exists():
            return

    de = DeliveryEvent.objects.create(
        delivery=delivery,
        esp_name=esp_name,
        esp_event_id=esp_event_id or f"{event.message_id}:{event.timestamp.isoformat()}:{event.event_type}",
        message_id=event.message_id,
        event=event.event_type,
        event_type=event.event_type,
        occurred_at=event.timestamp,
        recipient=event.recipient,
        ip=(event.esp_event.get("ip") if event.esp_event else None),
        user_agent=(event.esp_event.get("user-agent") if event.esp_event else ""),
        url=getattr(event, "click_url", "") or "",
        delivery_status=event.esp_event.get("delivery-status", {}) if event.esp_event else {},
        raw_payload=event.esp_event or {},
    )

    # Roll up Delivery
    delivery.last_event = event.event_type
    delivery.last_event_at = event.timestamp

    # first/last timestamps + counters
    if event.event_type == "delivered":
        delivery.delivered_at = delivery.delivered_at or event.timestamp
    elif event.event_type == "opened":
        delivery.open_count += 1
        delivery.last_opened_at = event.timestamp
        delivery.opened_at = delivery.opened_at or event.timestamp
    elif event.event_type == "clicked":
        delivery.click_count += 1
        delivery.last_clicked_at = event.timestamp
        delivery.clicked_at = delivery.clicked_at or event.timestamp
    elif event.event_type in ("bounced", "rejected"):
        delivery.failed_at = delivery.failed_at or event.timestamp

    delivery.state = ROLLUP_STATE_MAP.get(event.event_type, delivery.state)
    delivery.save()
