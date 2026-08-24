"""CAP-07 Clinical Module Data Capture tests.

Covers:
- U-1 (PROPOSALS.md §4): per-file upload size validation on
  FileTypeRestrictedFileField — over-limit uploads are rejected with a
  friendly message showing the limit; under-limit uploads pass.
- REQ-07-01/REQ-07-02 template layer: the clinical form page renders with
  the left section rail (.rdrf-subnav-rail) with one entry per section
  targeting the section anchors, section cards (.rdrf-card), the
  reference-vs-capture block split, the form progress bar (.rdrf-progress),
  and multisection entries styled as nested cards.
"""

import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import TestCase, override_settings
from django.urls import reverse
from registry.groups import GROUPS as RDRF_GROUPS
from registry.groups.models import CustomUser
from registry.patients.models import ParentGuardian, Patient

from rdrf.db.contexts_api import RDRFContextManager
from rdrf.forms.dynamic.fields import FileTypeRestrictedFileField
from rdrf.models.definition.models import (
    ClinicalData,
    CommonDataElement,
    Registry,
    RegistryForm,
    Section,
    WhitelistedFileExtension,
)

AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"


class FileFieldMaxSizeValidationTest(TestCase):
    """U-1: FileTypeRestrictedFileField enforces MAX_UPLOAD_FILE_SIZE."""

    def setUp(self):
        WhitelistedFileExtension.objects.create(file_extension=".pdf")
        self.field = FileTypeRestrictedFileField(required=False)

    def _upload(self, size):
        return SimpleUploadedFile(
            "evidence.pdf", b"x" * size, content_type="application/pdf"
        )

    @override_settings(MAX_UPLOAD_FILE_SIZE=1024)
    def test_over_limit_upload_is_rejected_with_limit_in_message(self):
        with self.assertRaises(ValidationError) as ctx:
            self.field.clean(self._upload(1025))
        message = "".join(ctx.exception.messages)
        self.assertIn("too large", message)
        self.assertIn("1.0\xa0KB", message)  # the limit, human readable

    @override_settings(MAX_UPLOAD_FILE_SIZE=1024)
    def test_under_limit_upload_is_accepted(self):
        cleaned = self.field.clean(self._upload(1024))
        self.assertEqual(cleaned.name, "evidence.pdf")

    @override_settings(MAX_UPLOAD_FILE_SIZE=1024)
    def test_over_limit_and_bad_extension_reports_size_first(self):
        bad = SimpleUploadedFile("evidence.exe", b"x" * 2048)
        with self.assertRaises(ValidationError) as ctx:
            self.field.clean(bad)
        self.assertIn("too large", "".join(ctx.exception.messages))

    @override_settings(MAX_UPLOAD_FILE_SIZE=1024)
    def test_extension_whitelist_still_enforced_under_limit(self):
        bad = SimpleUploadedFile("evidence.exe", b"x" * 10)
        with self.assertRaises(ValidationError) as ctx:
            self.field.clean(bad)
        self.assertIn("not a supported file extension",
                      "".join(ctx.exception.messages))


class ClinicalFormPageTest(TestCase):
    """View-smoke test of the CAP-07 clinical form template uplift."""

    databases = ["default", "clinical"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # When the clinical DB alias shares the default database (the local
        # test setup), clinical-model migrations are routed away from it and
        # rdrf_clinicaldata never gets created. The form view loads dynamic
        # data from it unconditionally, so create it here. DDL runs inside
        # the class-level atomic, so it is rolled back.
        connection = connections["clinical"]
        table_names = connection.introspection.table_names()
        if ClinicalData._meta.db_table not in table_names:
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(ClinicalData)

    def setUp(self):
        self.registry = Registry.objects.create(code="cap07")

        self.cde = CommonDataElement.objects.create(
            code="CAP07Q1",
            name="Reason for hospitalisation",
            abbreviated_name="Reason",
            datatype="string",
        )
        CommonDataElement.objects.create(
            code="CAP07Q2",
            name="Medication name",
            abbreviated_name="Medication",
            datatype="string",
        )
        Section.objects.create(
            code="CAP07SEC",
            display_name="Hospitalisations",
            abbreviated_name="Hosp",
            elements="CAP07Q1",
            allow_multiple=False,
        )
        Section.objects.create(
            code="CAP07MULTI",
            display_name="Medications",
            abbreviated_name="Meds",
            elements="CAP07Q2",
            allow_multiple=True,
        )
        self.form = RegistryForm.objects.create(
            name="ClinicalModule",
            registry=self.registry,
            abbreviated_name="Clinical",
            sections="CAP07SEC,CAP07MULTI",
        )
        # progress indicator derives from complete_form_cdes (REQ-07-01)
        self.form.complete_form_cdes.set([self.cde])

        self.user = CustomUser.objects.create(
            username=str(uuid.uuid4()), is_active=True
        )
        self.user.add_group(RDRF_GROUPS.PATIENT)
        self.user.registry.set([self.registry])

        self.patient = Patient.objects.create(
            consent=True,
            date_of_birth="2015-01-01",
            family_name="Capseven",
            given_names="Clinical",
            user=self.user,
        )
        self.patient.rdrf_registry.set([self.registry])

        context_manager = RDRFContextManager(self.registry)
        self.context = context_manager.get_or_create_default_context(
            self.patient
        )

        self.url = reverse(
            "registry_form",
            args=[
                self.registry.code,
                self.form.pk,
                self.patient.pk,
                self.context.pk,
            ],
        )
        self.client.force_login(self.user, backend=AUTH_BACKEND)

    def _get_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_form_page_renders_section_rail_and_cards(self):
        content = self._get_page()

        # REQ-07-01: section rail with an entry per section, anchored to the
        # section card ids, and the horizontal module navigation shell.
        self.assertIn("rdrf-subnav-rail", content)
        self.assertIn('class="col-lg-3 d-none d-lg-block d-print-none"', content)
        self.assertIn("data-rdrf-module-nav", content)
        self.assertNotIn('id="sidebar"', content)
        self.assertNotIn('class="blur"', content)
        self.assertNotIn("toggleSidebar", content)
        self.assertNotIn("sidebar-button", content)
        self.assertIn('data-rdrf-module-nav-source', content)
        self.assertIn('class="col-12 rdrf-clinical-page"', content)
        self.assertRegex(
            content,
            r'(?s)class="card card-info trrf-page-header rdrf-clinical-page-header".*data-rdrf-module-nav',
        )
        self.assertRegex(
            content,
            r'(?s)data-rdrf-module-nav.*rdrf-clinical-summary.*rdrf-form-progress-summary',
        )
        self.assertIn(
            '<h1 class="rdrf-clinical-summary__title">Clinical Module</h1>',
            content,
        )
        self.assertIn('class="rdrf-form-progress-summary__value">0%</span>', content)
        self.assertIn('href="#section_CAP07SEC"', content)
        self.assertIn('href="#section_CAP07MULTI"', content)
        self.assertIn('id="section_CAP07SEC"', content)
        self.assertIn('id="section_CAP07MULTI"', content)

        # Section cards
        self.assertIn("rdrf-section-card", content)
        self.assertIn("rdrf-card__title-row", content)

        # REQ-07-02: editable fields render inside capture blocks
        self.assertIn("rdrf-capture-block", content)

    def test_form_page_renders_progress_bar(self):
        content = self._get_page()
        # complete_form_cdes configured => progress surfaced as rdrf-progress
        self.assertIn("rdrf-progress", content)
        self.assertIn('role="progressbar"', content)
        self.assertNotIn('id="show-cdes-btn"', content)
        self.assertNotIn('id="form-progress-cdes"', content)

    def test_parent_with_multiple_guardian_records_can_view_form(self):
        self.user.add_group(RDRF_GROUPS.PARENT)
        parent_for_patient = ParentGuardian.objects.create(user=self.user)
        parent_for_patient.patient.add(self.patient)
        ParentGuardian.objects.create(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["parent"], parent_for_patient)

    def test_section_rail_rendering_contract(self):
        content = self._get_page()

        # Keep the sub-navigation selector and section anchors stable while
        # the rail is extracted from the page template.
        self.assertIn('data-rdrf-subnav', content)
        self.assertIn('aria-label="Form sections"', content)
        self.assertIn('class="rdrf-clinical-rail__heading"', content)
        self.assertIn('class="rdrf-clinical-rail__items"', content)
        self.assertIn('href="#section_CAP07SEC"', content)
        self.assertIn('href="#section_CAP07MULTI"', content)

    def test_multisection_renders_nested_entry_cards_with_add_remove(self):
        content = self._get_page()
        self.assertIn("rdrf-multisection-entry", content)
        # add/remove affordances still wired to the legacy JS
        self.assertIn("add_form(this,", content)
        self.assertIn("delete_form(this,", content)

    def test_section_header_renders_as_supporting_text(self):
        Section.objects.filter(code="CAP07SEC").update(
            header="<p>Reasons in the last 12 months</p>"
        )
        content = self._get_page()
        self.assertIn(
            'class="rdrf-clinical-section-label__supporting-text"', content
        )
        self.assertIn("Reasons in the last 12 months", content)

    def test_no_reference_block_without_section_header(self):
        content = self._get_page()
        self.assertNotIn('class="rdrf-clinical-section-label__supporting-text"', content)

    def test_section_shell_rendering_contract(self):
        Section.objects.filter(code="CAP07SEC").update(
            header="<p>Section guidance</p>"
        )
        content = self._get_page()

        # Keep each section's anchor, title, configured supporting content,
        # and repeatable-section add hook stable while its visual shell is
        # rendered as a label-and-content composition.
        self.assertIn(
            'class="rdrf-section-card"', content
        )
        self.assertIn('data-name="CAP07SEC"', content)
        self.assertIn("Hospitalisations", content)
        self.assertIn("Section guidance", content)
        self.assertIn('class="rdrf-clinical-section-label__supporting-text"', content)
        self.assertIn('class="rdrf-section-card__body"', content)
        self.assertIn('class="rdrf-capture-block"', content)
        self.assertIn(
            "add_form(this, 'formset_CAP07MULTI')", content
        )

    def test_standard_field_rendering_contract(self):
        content = self._get_page()

        # Keep the standard CDE row's label, control and structural hooks
        # stable while the form renderer is split into partials.
        self.assertIn('class="row rdrf-cde-field invisibutton-container"', content)
        self.assertIn(
            'for="id_ClinicalModule____CAP07SEC____CAP07Q1"', content
        )
        self.assertIn("Reason for hospitalisation", content)
        self.assertIn('name="ClinicalModule____CAP07SEC____CAP07Q1"', content)
        self.assertIn('class="col-sm-3 col-form-label"', content)
        self.assertIn('class="col-sm-9 rdrf-cde-field__control"', content)

    def test_repeatable_field_rendering_contract(self):
        content = self._get_page()

        # Keep the repeatable section's management form, empty-form template,
        # and legacy add/remove hooks stable while its renderer is extracted.
        prefix = "formset_CAP07MULTI"
        self.assertIn(f'id="mgmt_{prefix}"', content)
        self.assertIn(f'id="empty_{prefix}"', content)
        self.assertIn(f'id="forms_{prefix}"', content)
        self.assertIn(
            f'name="{prefix}-__prefix__-ClinicalModule____CAP07MULTI____CAP07Q2"',
            content,
        )
        self.assertIn('class="rdrf-multisection-entry"', content)
        self.assertIn(f"delete_form(this, '{prefix}')", content)

    def test_form_action_rendering_contract(self):
        content = self._get_page()

        self.assertIn('class="rdrf-form-actions rdrf-form-actions--top"', content)
        self.assertIn(
            'class="rdrf-form-actions rdrf-form-actions--footer"', content
        )
        self.assertEqual(content.count('id="submit-btn"'), 1)
        self.assertEqual(content.count('data-rdrf-submit-btn form="main-form"'), 2)
        self.assertIn('form="main-form"', content)
        self.assertIn("Save and exit", content)
        self.assertIn("Cancel", content)
