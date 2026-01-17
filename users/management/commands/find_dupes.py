from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import Lower, Trim
import csv
import sys

class Command(BaseCommand):
    help = "List duplicate user emails ignoring case (and trimming whitespace)."

    def add_arguments(self, parser):
        parser.add_argument("--csv", dest="csv_path", help="Write results to CSV at this path")

    def handle(self, *args, **opts):
        User = get_user_model()

        dup_groups = (
            User.objects
            .exclude(email__isnull=True)
            .exclude(email__exact="")
            .annotate(email_norm=Lower(Trim('email')))
            .values('email_norm')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
            .order_by('-count', 'email_norm')
        )

        if not dup_groups:
            self.stdout.write(self.style.SUCCESS("No duplicate emails found (case-insensitive)."))
            return

        # Gather all users in duplicate groups in one query
        norms = [g['email_norm'] for g in dup_groups]
        users = (
            User.objects
            .annotate(email_norm=Lower(Trim('email')))
            .filter(email_norm__in=norms)
            .only('id', 'email', 'is_active', 'date_joined', 'last_login')
            .order_by('email_norm', 'id')
        )

        # index by norm
        by_norm = {}
        for u in users:
            by_norm.setdefault(u.email_norm, []).append(u)

        if opts.get("csv_path"):
            path = opts["csv_path"]
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["email_norm", "user_id", "email", "is_active", "date_joined", "last_login"])
                for g in dup_groups:
                    for u in by_norm.get(g['email_norm'], []):
                        w.writerow([g['email_norm'], u.id, u.email, u.is_active, u.date_joined, u.last_login])
            self.stdout.write(self.style.SUCCESS(f"Wrote CSV to {path}"))
            return

        # Pretty print to stdout
        for g in dup_groups:
            norm = g['email_norm']
            self.stdout.write(self.style.WARNING(f"\n{norm}  (x{g['count']})"))
            for u in by_norm.get(norm, []):
                self.stdout.write(f"  id={u.id:>6}  email={u.email!r}  active={u.is_active}  joined={u.date_joined}  last_login={u.last_login}")
