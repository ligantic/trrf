import os

import yaml
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection, transaction

from rdrf.models.definition.models import (
    CommonDataElement,
    Registry,
    RegistryForm,
)
from rdrf.services.io.defs.importer import Importer
from rdrf.services.io.dev_seed import DevelopmentScenarioSeeder


class Command(BaseCommand):
    help = "Seeds a development database from a registry definition."

    def add_arguments(self, parser):
        parser.add_argument(
            "--registry-file",
            default=os.environ.get("REGISTRY_DEFINITION_FILE"),
            help="Registry definition YAML (or REGISTRY_DEFINITION_FILE).",
        )
        parser.add_argument(
            "--dataset",
            default=os.environ.get("REGISTRY_SEED_DATASET", "DEV"),
            help="Initial-data dataset to load before the registry definition.",
        )
        parser.add_argument("--update-existing", action="store_true")
        parser.add_argument("--confirm-update", action="store_true")
        parser.add_argument("--skip-initial-data", action="store_true")
        parser.add_argument("--skip-synthetic", action="store_true")
        parser.add_argument("--skip-health-check", action="store_true")

    def handle(self, *args, **options):
        self._check_safety(options)
        definition = self._load_definition(options["registry_file"])

        with transaction.atomic():
            self._acquire_lock(definition["code"])
            if not options["skip_initial_data"]:
                call_command("init", options["dataset"])
            self._import_definition(definition, options)
            registry = Registry.objects.get(code=definition["code"])
            self._verify_definition(registry, definition)
            if not options["skip_synthetic"]:
                with transaction.atomic(using="clinical"):
                    summary = DevelopmentScenarioSeeder(registry).seed()
                self.stdout.write(
                    "Synthetic scenarios: "
                    + ", ".join(f"{key}={value}" for key,
                                value in summary.items())
                )

        if not options["skip_health_check"]:
            call_command("check")
        self.stdout.write(
            self.style.SUCCESS(
                f"Development registry {registry.code} {registry.version} is ready."
            )
        )

    def _check_safety(self, options):
        if settings.PRODUCTION:
            raise CommandError(
                "Development database seeding is disabled in production."
            )
        if os.environ.get("ENABLE_REGISTRY_SEEDING") != "1":
            raise CommandError(
                "Set ENABLE_REGISTRY_SEEDING=1 to enable seeding.")
        if not options["registry_file"]:
            raise CommandError(
                "Provide --registry-file or set REGISTRY_DEFINITION_FILE."
            )
        if options["update_existing"] and not options["confirm_update"]:
            raise CommandError("--update-existing requires --confirm-update.")

    def _load_definition(self, path):
        try:
            with open(path) as definition_file:
                loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
                definition = yaml.load(definition_file, Loader=loader)
        except (OSError, yaml.YAMLError) as exc:
            raise CommandError(
                f"Cannot load registry definition {path}: {exc}"
            ) from exc

        required = ("EXPORT_TYPE", "code", "name", "forms", "cdes", "pvgs")
        missing = [key for key in required if key not in definition]
        if missing:
            raise CommandError(
                f"Registry definition is missing: {', '.join(missing)}")
        return definition

    def _acquire_lock(self, registry_code):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    [f"rdrf-dev-seed:{registry_code}"],
                )

    def _import_definition(self, definition, options):
        existing = Registry.objects.filter(code=definition["code"]).first()
        definition_version = str(definition.get(
            "REGISTRY_VERSION", "")).strip()

        if (
            existing
            and existing.version.strip() == definition_version
            and not options["update_existing"]
        ):
            self.stdout.write(
                f"Registry {existing.code} {definition_version} already matches; skipping import."
            )
            return
        if existing and not options["update_existing"]:
            raise CommandError(
                f"Registry {existing.code} is version {existing.version}; definition is "
                f"{definition_version}. Use --update-existing --confirm-update after backup."
            )

        importer = Importer()
        importer.load_data(definition)
        importer.create_registry()

    def _verify_definition(self, registry, definition):
        expected_forms = {form["name"] for form in definition.get("forms", [])}
        actual_forms = set(
            RegistryForm.objects.filter(registry=registry).values_list(
                "name", flat=True
            )
        )
        if expected_forms != actual_forms:
            raise CommandError(
                "Registry form verification failed: "
                f"definition={len(expected_forms)}, database={len(actual_forms)}, "
                f"missing={len(expected_forms - actual_forms)}, "
                f"extra={len(actual_forms - expected_forms)}."
            )

        expected_cdes = {cde["code"] for cde in definition.get("cdes", [])}
        existing_cdes = set(
            CommonDataElement.objects.filter(code__in=expected_cdes).values_list(
                "code", flat=True
            )
        )
        if expected_cdes != existing_cdes:
            raise CommandError(
                "Registry CDE verification failed: "
                f"definition={len(expected_cdes)}, database={len(existing_cdes)}, "
                f"missing={len(expected_cdes - existing_cdes)}."
            )
