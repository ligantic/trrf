import os

from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Update the Django site domain from TRRF_SITE_DOMAIN"

    def handle(self, *args, **options):
        domain = os.environ.get("TRRF_SITE_DOMAIN")
        if not domain:
            self.stdout.write(
                self.style.WARNING("TRRF_SITE_DOMAIN is not set; skipping")
            )
            return

        database_name = os.environ.get("DBNAME", "angelman2")
        site_name = f"Angelman Registry ({database_name})"
        Site.objects.update_or_create(
            pk=1,
            defaults={"domain": domain, "name": site_name},
        )
        self.stdout.write(
            self.style.SUCCESS(f"Django site domain set to {domain}")
        )