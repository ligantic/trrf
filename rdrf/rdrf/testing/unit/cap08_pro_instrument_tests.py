"""CAP-08 PRO Instrument framework tests.

Covers the first increment (scoring explicitly out of scope — D-05):
- feature flag off -> 404
- shell renders parts with per-part status badges and overall progress
- saving a part with all required values marks it COMPLETE and the
  administration progresses
- save-and-exit redirects to the shell; save-and-continue advances
- partial save transitions part state NOT_STARTED -> IN_PROGRESS
- existing-but-unlinked patient -> 403; nonexistent patient -> 404
"""

import uuid

from django.db import connections
from django.test import TestCase
from django.urls import reverse
from registry.groups import GROUPS as RDRF_GROUPS
from registry.groups.models import CustomUser
from registry.patients.models import Patient

from rdrf.helpers.registry_features import RegistryFeatures
from rdrf.models.definition.models import (
    ClinicalData,
    CommonDataElement,
    Registry,
    RegistryForm,
    Section,
)
from rdrf.models.pro_instruments import (
    PROInstrument,
    PROInstrumentAdministration,
    PROInstrumentStatus,
)

AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"

FORM_NAME = "OrcaMeasure"
DELIMITER = "____"


def field_key(section_code, cde_code):
    return f"{FORM_NAME}{DELIMITER}{section_code}{DELIMITER}{cde_code}"


class ProInstrumentTestBase(TestCase):
    databases = ["default", "clinical"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # When the clinical DB alias shares the default database (the local
        # test setup), clinical-model migrations are routed away from it and
        # rdrf_clinicaldata never gets created. The part view saves dynamic
        # data to it unconditionally, so create it here. DDL runs inside
        # the class-level atomic, so it is rolled back.
        connection = connections["clinical"]
        table_names = connection.introspection.table_names()
        if ClinicalData._meta.db_table not in table_names:
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(ClinicalData)

    def setUp(self):
        self.registry = Registry.objects.create(
            code="cap08",
            metadata_json='{"features": ["pro_instruments"]}',
        )
        assert self.registry.has_feature(RegistryFeatures.PRO_INSTRUMENTS)

        for code, name, required in [
            ("CAP08Q1", "Question 1", True),
            ("CAP08Q2", "Question 2", True),
            ("CAP08Q3", "Question 3", True),
        ]:
            CommonDataElement.objects.create(
                code=code,
                name=name,
                abbreviated_name=code,
                datatype="string",
                is_required=required,
            )
        Section.objects.create(
            code="CAP08PART1",
            display_name="Part 1",
            abbreviated_name="P1",
            elements="CAP08Q1,CAP08Q2",
        )
        Section.objects.create(
            code="CAP08PART2",
            display_name="Part 2",
            abbreviated_name="P2",
            elements="CAP08Q3",
        )
        self.form = RegistryForm.objects.create(
            name=FORM_NAME,
            registry=self.registry,
            abbreviated_name="Orca",
            sections="CAP08PART1,CAP08PART2",
        )
        self.instrument = PROInstrument.objects.create(
            registry=self.registry,
            registry_form=self.form,
            display_name="ORCA Measure",
            slug="orca",
        )

        self.user = CustomUser.objects.create(
            username=str(uuid.uuid4()), is_active=True
        )
        self.user.add_group(RDRF_GROUPS.PATIENT)
        self.user.registry.set([self.registry])

        self.patient = Patient.objects.create(
            consent=True,
            date_of_birth="2015-01-01",
            family_name="Capeight",
            given_names="Pro",
            user=self.user,
        )
        self.patient.rdrf_registry.set([self.registry])

        self.unlinked_patient = Patient.objects.create(
            consent=True,
            date_of_birth="2015-01-01",
            family_name="Unlinked",
        )
        self.unlinked_patient.rdrf_registry.set([self.registry])

        self.client.force_login(self.user, backend=AUTH_BACKEND)

    def shell_url(self, patient_id=None):
        return reverse(
            "pro_instrument_shell",
            args=[self.registry.code, "orca", patient_id or self.patient.pk],
        )

    def part_url(self, section_code, patient_id=None):
        return reverse(
            "pro_instrument_part",
            args=[
                self.registry.code,
                "orca",
                patient_id or self.patient.pk,
                section_code,
            ],
        )

    def administration(self):
        return PROInstrumentAdministration.objects.filter(
            instrument=self.instrument, patient_id=self.patient.pk
        ).first()

    def part_status(self, section_code):
        administration = self.administration()
        if administration is None:
            return PROInstrumentStatus.NOT_STARTED
        state = administration.part_states.filter(
            section_code=section_code
        ).first()
        return state.status if state else PROInstrumentStatus.NOT_STARTED


class FeatureFlagTest(ProInstrumentTestBase):
    def test_shell_404_when_feature_disabled(self):
        self.registry.metadata_json = "{}"
        self.registry.save()
        response = self.client.get(self.shell_url())
        self.assertEqual(response.status_code, 404)

    def test_part_404_when_feature_disabled(self):
        self.registry.metadata_json = "{}"
        self.registry.save()
        response = self.client.get(self.part_url("CAP08PART1"))
        self.assertEqual(response.status_code, 404)


class ShellPageTest(ProInstrumentTestBase):
    def test_shell_lists_parts_with_status_badges_and_progress(self):
        response = self.client.get(self.shell_url())
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn("ORCA Measure", content)
        self.assertIn("Part 1", content)
        self.assertIn("Part 2", content)
        self.assertIn("rdrf-subnav-rail", content)
        self.assertIn("rdrf-badge--not-started", content)
        self.assertIn("rdrf-progress", content)
        self.assertIn('role="progressbar"', content)
        self.assertIn('aria-valuenow="0"', content)

    def test_continue_targets_first_non_complete_part(self):
        response = self.client.get(self.shell_url())
        self.assertContains(response, self.part_url("CAP08PART1"))
        # Complete part 1 -> continue should target part 2
        self.client.post(
            self.part_url("CAP08PART1"),
            {
                field_key("CAP08PART1", "CAP08Q1"): "yes",
                field_key("CAP08PART1", "CAP08Q2"): "no",
                "save_exit": "1",
            },
        )
        response = self.client.get(self.shell_url())
        content = response.content.decode()
        continue_index = content.index(">Continue<")
        href_index = content.rindex("href=", 0, continue_index)
        self.assertIn(self.part_url("CAP08PART2"), content[href_index:continue_index])

    def test_nonexistent_instrument_404(self):
        url = reverse(
            "pro_instrument_shell",
            args=[self.registry.code, "nope", self.patient.pk],
        )
        self.assertEqual(self.client.get(url).status_code, 404)


class PartSaveTest(ProInstrumentTestBase):
    def test_part_page_renders_section_fields(self):
        response = self.client.get(self.part_url("CAP08PART1"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(field_key("CAP08PART1", "CAP08Q1"), content)
        self.assertIn(field_key("CAP08PART1", "CAP08Q2"), content)
        self.assertIn("Save and continue", content)
        self.assertIn("Save and exit", content)

    def test_full_save_marks_part_complete_and_advances_administration(self):
        response = self.client.post(
            self.part_url("CAP08PART1"),
            {
                field_key("CAP08PART1", "CAP08Q1"): "yes",
                field_key("CAP08PART1", "CAP08Q2"): "no",
                "save_continue": "1",
            },
        )
        # save-and-continue -> next part
        self.assertRedirects(
            response,
            self.part_url("CAP08PART2"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.part_status("CAP08PART1"), PROInstrumentStatus.COMPLETE
        )
        self.assertEqual(
            self.administration().status, PROInstrumentStatus.IN_PROGRESS
        )

    def test_partial_save_marks_part_in_progress(self):
        self.assertEqual(
            self.part_status("CAP08PART1"), PROInstrumentStatus.NOT_STARTED
        )
        self.client.post(
            self.part_url("CAP08PART1"),
            {
                field_key("CAP08PART1", "CAP08Q1"): "yes",
                field_key("CAP08PART1", "CAP08Q2"): "",
                "save_exit": "1",
            },
        )
        self.assertEqual(
            self.part_status("CAP08PART1"), PROInstrumentStatus.IN_PROGRESS
        )
        self.assertEqual(
            self.administration().status, PROInstrumentStatus.IN_PROGRESS
        )

    def test_save_and_exit_redirects_to_shell(self):
        response = self.client.post(
            self.part_url("CAP08PART1"),
            {
                field_key("CAP08PART1", "CAP08Q1"): "yes",
                "save_exit": "1",
            },
        )
        self.assertRedirects(
            response, self.shell_url(), fetch_redirect_response=False
        )

    def test_completing_all_parts_completes_administration(self):
        self.client.post(
            self.part_url("CAP08PART1"),
            {
                field_key("CAP08PART1", "CAP08Q1"): "yes",
                field_key("CAP08PART1", "CAP08Q2"): "no",
                "save_continue": "1",
            },
        )
        self.client.post(
            self.part_url("CAP08PART2"),
            {
                field_key("CAP08PART2", "CAP08Q3"): "sometimes",
                "save_exit": "1",
            },
        )
        self.assertEqual(
            self.administration().status, PROInstrumentStatus.COMPLETE
        )
        # shell shows 100% and no stale statuses
        response = self.client.get(self.shell_url())
        self.assertContains(response, 'aria-valuenow="100"')

    def test_saved_answers_are_prefilled_on_return(self):
        self.client.post(
            self.part_url("CAP08PART1"),
            {
                field_key("CAP08PART1", "CAP08Q1"): "yes",
                "save_exit": "1",
            },
        )
        response = self.client.get(self.part_url("CAP08PART1"))
        self.assertContains(response, 'value="yes"')

    def test_score_payload_extension_point_defaults_empty(self):
        # D-05: scoring is out of scope; the extension point must exist
        # and stay unused.
        self.client.post(
            self.part_url("CAP08PART1"),
            {
                field_key("CAP08PART1", "CAP08Q1"): "yes",
                "save_exit": "1",
            },
        )
        self.assertIsNone(self.administration().score_payload)


class AuthorizationTest(ProInstrumentTestBase):
    def test_unlinked_patient_returns_403(self):
        response = self.client.get(
            self.shell_url(patient_id=self.unlinked_patient.pk)
        )
        self.assertEqual(response.status_code, 403)

    def test_unlinked_patient_part_returns_403(self):
        response = self.client.get(
            self.part_url("CAP08PART1", patient_id=self.unlinked_patient.pk)
        )
        self.assertEqual(response.status_code, 403)

    def test_nonexistent_patient_returns_404(self):
        nonexistent_id = Patient.objects.latest("id").id + 1000
        response = self.client.get(self.shell_url(patient_id=nonexistent_id))
        self.assertEqual(response.status_code, 404)
