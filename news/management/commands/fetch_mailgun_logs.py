import os

import requests
import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

MAILGUN_API_URL = f"{settings.MAILGUN_API_URL}/{settings.MAILGUN_SENDER_DOMAIN}/events"


class Command(BaseCommand):
    help = "Fetch previous day's Mailgun events and save to file or DB"

    def handle(self, *args, **options):
        # Get yesterday's time window
        end = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - datetime.timedelta(days=1)

        self.stdout.write(f"Fetching Mailgun logs from {start} to {end}")

        # Mailgun expects RFC 2822 dates
        params = {
            "begin": start.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "end": end.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "ascending": "yes",
            "limit": 300,   # Mailgun max per page is 300
            "event": "accepted OR delivered OR failed"  # adjust as needed
        }

        logs = []
        next_url = MAILGUN_API_URL

        while next_url:
            resp = requests.get(
                next_url,
                auth=("api", settings.MAILGUN_API_KEY),
                params=params
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("items", [])
            logs.extend(items)

            # Pagination
            next_url = data.get("paging", {}).get("next")

            # Only need params for first request
            params = {}

        # Make sure logs directory exists
        logs_dir = os.path.join(settings.BASE_DIR, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        out_file = os.path.join(logs_dir, f"mailgun_logs_{start.date()}.json")

        with open(out_file, "w", encoding="utf-8") as f:
            import json
            json.dump(logs, f, indent=2)

        self.stdout.write(self.style.SUCCESS(f"Saved {len(logs)} events to {out_file}"))
