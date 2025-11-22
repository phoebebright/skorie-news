# newsletters/management/commands/send_queued_mailings.py
from django.core.management.base import BaseCommand
from skorie_news.models import Mailing  # adjust import to your actual app path


class Command(BaseCommand):
    help = "Send queued newsletter mailings whose publish_date is due."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of mailings to send in one run (default: no limit).",
        )

    def handle(self, *args, **options):
        limit = options.get("limit")
        processed = Mailing.send_due(max_per_run=limit)

        if processed == 0:
            self.stdout.write(self.style.WARNING("No queued mailings due to send."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Processed {processed} queued mailing(s).")
            )
