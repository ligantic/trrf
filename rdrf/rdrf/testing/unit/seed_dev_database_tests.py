import datetime
import os
import tempfile
from unittest.mock import patch

import yaml
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from registry.groups.models import CustomUser
from registry.patients.models import LongitudinalFollowupEntry, Patient

from rdrf.helpers.cde_data_types import CDEDataTypes
from rdrf.models.definition.models import (
    ClinicalData,
    CommonDataElement,
    ContextFormGroup,
    ContextFormGroupItem,
    LongitudinalFollowup,
    Registry,
    RegistryForm,
    Section,
)
from rdrf.services.io.dev_seed import DevelopmentScenarioSeeder


@override_settings(PRODUCTION=False)
class SeedDevDatabaseTests(TestCase):
    databases = {"default", "clinical"}

    def setUp(self):
        self.registry = Registry.objects.create(
            code="seedreg",
            name="Seed Registry",
            version="1.0",
            metadata_json='{"features": ["contexts", "longitudinal_followups"]}',
        )
        self.cde = CommonDataElement.objects.create(
            code="SeedCDE",
            name="Seed value",
            abbreviated_name="Seed value",
            datatype="string",
        )
        section = Section.objects.create(
            code="SeedSection",
            display_name="Seed section",
            abbreviated_name="Seed section",
            elements=self.cde.code,
        )
        form = RegistryForm.objects.create(
            registry=self.registry,
            name="SeedForm",
            abbreviated_name="Seed form",
            sections=section.code,
        )
        context_group = ContextFormGroup.objects.create(
            registry=self.registry,
            code="SeedHistory",
            name="Seed history",
            context_type="M",
            naming_scheme="N",
        )
        ContextFormGroupItem.objects.create(
            context_form_group=context_group,
            registry_form=form,
        )
        LongitudinalFollowup.objects.create(
            name="Seed followup",
            context_form_group=context_group,
            frequency=datetime.timedelta(days=30),
            debounce=datetime.timedelta(days=1),
        )
        self.definition_path = self._write_definition()

    def tearDown(self):
        os.unlink(self.definition_path)

    def _write_definition(self):
        definition = {
            "EXPORT_TYPE": "REGISTRY_PLUS_CDES",
            "REGISTRY_VERSION": "1.0",
            "code": "seedreg",
            "name": "Seed Registry",
            "forms": [{"name": "SeedForm"}],
            "cdes": [{"code": "SeedCDE"}],
            "pvgs": [],
        }
        definition_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        yaml.safe_dump(definition, definition_file)
        definition_file.close()
        return definition_file.name

    def _seed(self):
        with patch.dict(os.environ, {"ENABLE_REGISTRY_SEEDING": "1"}):
            call_command(
                "seed_dev_database",
                registry_file=self.definition_path,
                skip_initial_data=True,
            )

    def test_requires_explicit_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesMessage(CommandError, "ENABLE_REGISTRY_SEEDING=1"):
                call_command(
                    "seed_dev_database",
                    registry_file=self.definition_path,
                    skip_initial_data=True,
                )

    def test_seeds_scenario_matrix_and_is_idempotent(self):
        self._seed()
        self._seed()

        patients = Patient.objects.filter(umrn__startswith="dev-seed-seedreg-")
        self.assertEqual(patients.count(), 4)
        self.assertFalse(
            CustomUser.objects.get(
                username="dev-seed-seedreg-signup-pending@example.test"
            ).is_active
        )
        self.assertTrue(
            CustomUser.objects.get(
                username="dev-seed-seedreg-account-active@example.test"
            ).is_active
        )
        self.assertFalse(patients.get(umrn__endswith="-onboarding").consent)
        self.assertTrue(patients.get(
            umrn__endswith="-consented-no-history").consent)
        self.assertEqual(
            ClinicalData.objects.using("clinical")
            .filter(registry_code="seedreg", collection="cdes", active=True)
            .count(),
            4,
        )

        alerts = LongitudinalFollowupEntry.objects.filter(patient__in=patients)
        self.assertEqual(alerts.count(), 2)
        self.assertEqual(alerts.filter(send_at__lte=timezone.now()).count(), 1)
        self.assertEqual(alerts.filter(send_at__gt=timezone.now()).count(), 1)

    def test_formats_duration_values_for_configured_units(self):
        self.cde.datatype = CDEDataTypes.DURATION
        self.cde.widget_name = "DurationWidget"

        self.cde.widget_settings = '{"years": true, "months": true}'
        self.assertEqual(
            DevelopmentScenarioSeeder._duration_value(self.cde, 3), "P3Y0M"
        )

        self.cde.widget_settings = '{"hours": true}'
        self.assertEqual(
            DevelopmentScenarioSeeder._duration_value(self.cde, 3), "PT3H"
        )

        self.cde.widget_settings = '{"weeks_only": true}'
        self.assertEqual(
            DevelopmentScenarioSeeder._duration_value(self.cde, 3), "P3W"
        )
