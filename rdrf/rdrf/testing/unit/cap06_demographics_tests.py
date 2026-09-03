"""CAP-06 Participant Demographics UX uplift tests (REQ-06-01).

Covers the template-layer uplift of the demographics edit page:
- the page renders with the left-rail subsection navigation, with one rail
  entry per rendered form section, and rail links target the section anchors
- DemographicFields READONLY rules still render the field readonly
- DemographicFields HIDDEN rules still render the field as a hidden input

Permission semantics (DemographicFields, section blacklist/hidden lists) are
unchanged by CAP-06; these tests guard against template regressions.
"""

import re
import uuid

from django.db import connections
from django.test import TestCase
from django.urls import reverse
from registry.groups import GROUPS as RDRF_GROUPS
from registry.groups.models import CustomUser, WorkingGroup
from registry.patients.models import Patient

from rdrf.models.definition.models import (
    ClinicalData,
    DemographicFields,
    Registry,
)

AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"


class DemographicsEditPageTest(TestCase):
    databases = ["default", "clinical"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # When the clinical DB alias shares the default database (the local
        # test setup), clinical-model migrations are routed away from it and
        # rdrf_clinicaldata never gets created. PatientForm loads
        # registry-specific data from it unconditionally, so create it here.
        # DDL runs inside the class-level atomic, so it is rolled back.
        connection = connections["clinical"]
        table_names = connection.introspection.table_names()
        if ClinicalData._meta.db_table not in table_names:
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(ClinicalData)

    def setUp(self):
        self.registry = Registry.objects.create(code="cap06")

        self.user = CustomUser.objects.create(
            username=str(uuid.uuid4()), is_active=True
        )
        self.user.add_group(RDRF_GROUPS.PATIENT)
        self.user.registry.set([self.registry])

        self.patient = Patient.objects.create(
            consent=True,
            date_of_birth="1990-01-01",
            family_name="Capsix",
            given_names="Demo",
            user=self.user,
        )
        self.patient.rdrf_registry.set([self.registry])
        self.working_group = WorkingGroup.objects.create(
            name="CAP-06 Working Group", registry=self.registry
        )
        self.patient.working_groups.set([self.working_group])

        self.url = reverse(
            "patient_edit", args=[self.registry.code, self.patient.id]
        )
        self.client.force_login(self.user, backend=AUTH_BACKEND)

    def _add_field_rule(self, field, status):
        rule = DemographicFields.objects.create(
            registry=self.registry, field=field, status=status
        )
        rule.groups.set(self.user.groups.all())
        return rule

    def _input_html(self, content, field_name):
        match = re.search(
            r'<input[^>]*name="%s"[^>]*>' % re.escape(field_name), content
        )
        self.assertIsNotNone(
            match, "no <input> rendered for field %r" % field_name
        )
        return match.group(0)

    def test_page_renders_with_rail_entry_per_section(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn("rdrf-subnav-rail", content)

        rail_hrefs = re.findall(
            r'class="rdrf-subnav-rail__item"\s+href="#(demographics-section-\d+-\d+)"',
            content,
        )
        section_ids = re.findall(
            r'<section id="(demographics-section-\d+-\d+)"', content
        )
        self.assertTrue(section_ids, "no demographics section cards rendered")
        # One rail entry per rendered (non-hidden, non-blacklisted) section,
        # in document order, each targeting an existing section anchor.
        self.assertEqual(rail_hrefs, section_ids)
        # rdrf-card styling applied to each section
        self.assertEqual(
            len(re.findall(r'class="rdrf-card demographics-section"', content)),
            len(section_ids),
        )

    def test_patient_identity_is_not_rendered_without_a_patient_link(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        navbar = re.search(
            r'<nav class="navbar.*?</nav>', content, flags=re.DOTALL
        )
        self.assertIsNotNone(navbar)
        self.assertNotIn("rdrf-navbar__participant", navbar.group(0))
        self.assertNotIn(str(self.patient), navbar.group(0))

        banner = re.search(
            r'<div class="banner">.*?</div>\s*</div>',
            content,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(banner)
        self.assertNotIn(str(self.patient), banner.group(0))

    def test_registry_membership_renders_as_checkbox_group(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertNotIn('<select name="rdrf_registry"', content)
        self.assertIn('name="rdrf_registry"', content)

    def test_registry_section_can_be_hidden_from_parents(self):
        rule = self._add_field_rule(
            "SECTION:Registry", DemographicFields.HIDDEN
        )
        rule.is_section = True
        rule.save(update_fields=["is_section"])

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertNotIn('href="#demographics-section-1-1">Registry</a>', content)
        self.assertRegex(
            content,
            r'<div class="section_hidden">\s*<section id="demographics-section-1-1"',
        )

    def test_readonly_demographic_field_renders_readonly(self):
        self._add_field_rule("umrn", DemographicFields.READONLY)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        umrn_input = self._input_html(response.content.decode(), "umrn")
        self.assertIn("readonly", umrn_input)

    def test_hidden_demographic_field_renders_hidden_input(self):
        self._add_field_rule("place_of_birth", DemographicFields.HIDDEN)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        hidden_input = self._input_html(
            response.content.decode(), "place_of_birth"
        )
        self.assertIn('type="hidden"', hidden_input)

    def test_hidden_date_ignores_an_invalid_submitted_value(self):
        self.patient.date_of_migration = "2020-01-01"
        self.patient.save(update_fields=["date_of_migration"])
        self._add_field_rule("date_of_migration", DemographicFields.HIDDEN)

        response = self.client.post(
            self.url,
            {
                "family_name": "Updated",
                "given_names": self.patient.given_names,
                "date_of_birth": "01-01-1990",
                "sex": "1",
                "living_status": "Alive",
                "rdrf_registry": str(self.registry.id),
                "working_groups": str(self.working_group.id),
                "patient_address-TOTAL_FORMS": "0",
                "patient_address-INITIAL_FORMS": "0",
                "patient_address-MIN_NUM_FORMS": "0",
                "patient_address-MAX_NUM_FORMS": "1000",
                "date_of_migration": "not-a-date",
            },
        )

        self.assertFalse(response.context["errors"], response.context["error_messages"])
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.family_name, "UPDATED")
        self.assertEqual(str(self.patient.date_of_migration), "2020-01-01")
