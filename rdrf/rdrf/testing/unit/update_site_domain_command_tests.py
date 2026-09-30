from unittest import mock

from django.contrib.sites.models import Site
from django.core.management import call_command
from django.test import TestCase


class UpdateSiteDomainCommandTest(TestCase):
    def test_updates_site_from_container_environment(self):
        Site.objects.update_or_create(
            pk=1,
            defaults={"domain": "old.example", "name": "Old site"},
        )

        with mock.patch.dict(
            "os.environ",
            {
                "TRRF_SITE_DOMAIN": "compare.example",
                "DBNAME": "angelman2qa2",
            },
        ):
            call_command("update_site_domain")

        site = Site.objects.get(pk=1)
        self.assertEqual(site.domain, "compare.example")
        self.assertEqual(site.name, "Angelman Registry (angelman2qa2)")