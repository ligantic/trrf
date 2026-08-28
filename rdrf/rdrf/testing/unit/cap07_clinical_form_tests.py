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
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from registry.groups import GROUPS as RDRF_GROUPS
from registry.groups.models import CustomUser
from registry.patients.models import ParentGuardian, Patient
from registry.patients.models import (
    LongitudinalFollowupEntry,
    LongitudinalFollowupQueueState,
)

from rdrf.db.contexts_api import RDRFContextManager
from rdrf.forms.dynamic.fields import FileTypeRestrictedFileField
from rdrf.models.definition.models import (
    ClinicalData,
    CommonDataElement,
    ContextFormGroup,
    ContextFormGroupItem,
    LongitudinalFollowup,
    RDRFContext,
    Registry,
    RegistryForm,
    Section,
    WhitelistedFileExtension,
)
from rdrf.forms.components import RDRFContextLauncherComponent
from rdrf.helpers.registry_features import RegistryFeatures

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


class ParentClinicalModuleNavigationTest(TestCase):
    databases = ["default", "clinical"]

    def setUp(self):
        self.registry = Registry.objects.create(code="cap07nav")
        self.registry.add_feature(RegistryFeatures.CONTEXTS)
        self.navigation_cde = CommonDataElement.objects.create(
            code="CAP07NAVQ1",
            name="Navigation question",
            abbreviated_name="Navigation question",
            datatype="string",
        )
        Section.objects.create(
            code="CAP07NAVSEC",
            display_name="Navigation section",
            abbreviated_name="Navigation",
            elements="CAP07NAVQ1",
        )
        self.form = RegistryForm.objects.create(
            name="NavigationModule",
            registry=self.registry,
            abbreviated_name="Navigation",
            sections="CAP07NAVSEC",
            position=1,
        )
        self.cfg = ContextFormGroup.objects.create(
            registry=self.registry,
            context_type="M",
            code="NAV_CFG",
            name="Navigation contexts",
            abbreviated_name="Navigation",
            sort_order=99,
        )
        ContextFormGroupItem.objects.create(
            context_form_group=self.cfg, registry_form=self.form
        )
        self.user = CustomUser.objects.create(
            username=str(uuid.uuid4()), is_active=True
        )
        self.user.add_group(RDRF_GROUPS.PARENT)
        self.user.registry.set([self.registry])
        self.patient = Patient.objects.create(
            consent=True,
            date_of_birth="2015-01-01",
            family_name="Nav",
            given_names="Parent",
        )
        self.patient.rdrf_registry.set([self.registry])

    def _launcher(self, current_form_name="Demographics"):
        return RDRFContextLauncherComponent(
            self.user,
            self.registry,
            self.patient,
            current_form_name=current_form_name,
        )

    def _context(self, last_updated):
        context = RDRFContext.objects.create(
            registry=self.registry,
            context_form_group=self.cfg,
            object_id=self.patient.pk,
            content_type=ContentType.objects.get_for_model(self.patient),
        )
        RDRFContext.objects.filter(pk=context.pk).update(
            last_updated=last_updated
        )
        return context

    def _second_form(self):
        second_form = RegistryForm.objects.create(
            name="NavigationFollowupModule",
            registry=self.registry,
            abbreviated_name="Follow-up navigation",
            sections="CAP07NAVSEC",
            position=2,
        )
        ContextFormGroupItem.objects.create(
            context_form_group=self.cfg, registry_form=second_form
        )
        return second_form

    def test_parent_multiple_cfg_exposes_each_form_in_position_order(self):
        second_form = self._second_form()
        older = self._context(timezone.now() - timedelta(days=2))
        latest = self._context(timezone.now() - timedelta(days=1))

        with patch.object(
            self.patient, "get_form_timestamp", return_value=None
        ), patch(
            "rdrf.forms.components.FormProgress.get_form_progress",
            return_value=100,
        ):
            groups = self._launcher()._get_parent_context_form_groups()

        self.assertEqual(len(groups), 1)
        forms = groups[0][1].forms
        self.assertEqual([form.text for form in forms], [
            self.form.nice_name,
            second_form.nice_name,
        ])
        self.assertEqual(
            [form.url for form in forms],
            [
                self.form.get_link(self.patient, latest),
                second_form.get_link(self.patient, latest),
            ],
        )
        self.assertNotEqual(forms[0].url, self.form.get_link(self.patient, older))
        self.assertNotEqual(forms[1].url, second_form.get_link(self.patient, older))

    def test_parent_empty_or_due_multiple_cfg_uses_add_link(self):
        second_form = self._second_form()
        add_url, add_text = self.cfg.get_add_action(self.patient)
        with patch(
            "rdrf.forms.components.FormProgress.get_form_progress",
            return_value=100,
        ):
            empty_groups = self._launcher()._get_parent_context_form_groups()
        empty_forms = empty_groups[0][1].forms
        self.assertEqual([form.url for form in empty_forms], [add_url, add_url])
        self.assertEqual(
            [form.text for form in empty_forms],
            [self.form.nice_name, second_form.nice_name],
        )
        self.assertNotEqual(empty_forms[0].text, add_text)

        context = self._context(timezone.now() - timedelta(days=1))
        LongitudinalFollowup.objects.create(
            name="Navigation followup",
            context_form_group=self.cfg,
            frequency=timedelta(days=1),
            debounce=timedelta(days=1),
        )
        with patch.object(
            self.patient,
            "get_form_timestamp",
            return_value=(timezone.now() - timedelta(days=2)).isoformat(),
        ), patch(
            "rdrf.forms.components.FormProgress.get_form_progress",
            return_value=100,
        ):
            due_groups = self._launcher()._get_parent_context_form_groups()
        due_forms = due_groups[0][1].forms
        self.assertEqual([form.url for form in due_forms], [add_url, add_url])
        self.assertEqual(
            [form.text for form in due_forms],
            [self.form.nice_name, second_form.nice_name],
        )
        self.assertNotEqual(due_forms[0].url, self.form.get_link(self.patient, context))

    def test_parent_add_target_is_active_for_current_form(self):
        with patch(
            "rdrf.forms.components.FormProgress.get_form_progress",
            return_value=100,
        ):
            empty_forms = self._launcher(
                self.form.name
            )._get_parent_context_form_groups()[0][1].forms
        self.assertTrue(empty_forms[0].current)

        self._context(timezone.now() - timedelta(days=1))
        followup = LongitudinalFollowup.objects.create(
            name="Navigation active followup",
            context_form_group=self.cfg,
            frequency=timedelta(days=1),
            debounce=timedelta(days=1),
        )
        LongitudinalFollowupEntry.objects.create(
            longitudinal_followup=followup,
            patient=self.patient,
            state=LongitudinalFollowupQueueState.PENDING,
            send_at=timezone.now(),
        )
        with patch(
            "rdrf.forms.components.FormProgress.get_form_progress",
            return_value=100,
        ):
            due_forms = self._launcher(
                self.form.name
            )._get_parent_context_form_groups()[0][1].forms
        self.assertTrue(due_forms[0].current)

    def test_parent_due_statuses_use_add_link(self):
        context = self._context(timezone.now() - timedelta(days=1))
        followup = LongitudinalFollowup.objects.create(
            name="Navigation status followup",
            context_form_group=self.cfg,
            frequency=timedelta(days=1),
            debounce=timedelta(days=1),
        )
        add_url, _ = self.cfg.get_add_action(self.patient)
        now = timezone.now()

        for status, send_at in (
            ("due-soon", now + timedelta(days=7)),
            ("due-now", now),
            ("overdue", now - timedelta(days=1)),
        ):
            with self.subTest(status=status):
                LongitudinalFollowupEntry.objects.create(
                    longitudinal_followup=followup,
                    patient=self.patient,
                    state=LongitudinalFollowupQueueState.PENDING,
                    send_at=send_at,
                )
                with patch(
                    "rdrf.forms.components.FormProgress.get_form_progress",
                    return_value=100,
                ):
                    groups = self._launcher()._get_parent_context_form_groups()

                self.assertEqual(groups[0][1].forms[0].url, add_url)
                LongitudinalFollowupEntry.objects.filter(
                    longitudinal_followup=followup,
                    patient=self.patient,
                ).delete()

    def test_parent_complete_module_with_future_due_date_is_hidden(self):
        context = self._context(timezone.now() - timedelta(days=1))
        LongitudinalFollowup.objects.create(
            name="Navigation future followup",
            context_form_group=self.cfg,
            frequency=timedelta(days=30),
            debounce=timedelta(days=1),
        )
        with patch.object(
            self.patient,
            "get_form_timestamp",
            return_value=timezone.now().isoformat(),
        ), patch(
            "rdrf.forms.components.FormProgress.get_form_progress",
            return_value=100,
        ):
            groups = self._launcher()._get_parent_context_form_groups()

        self.assertEqual(groups, [])
        self.assertNotEqual(
            self.form.get_link(self.patient, context),
            self.cfg.get_add_action(self.patient)[0],
        )

    def test_parent_groups_fixed_modules_before_multiple_modules(self):
        fixed_form = RegistryForm.objects.create(
            name="NavigationFixedModule",
            registry=self.registry,
            abbreviated_name="Fixed navigation",
            sections="CAP07NAVSEC",
            position=3,
        )
        fixed_cfg = ContextFormGroup.objects.create(
            registry=self.registry,
            context_type="F",
            code="NAV_FIXED_CFG",
            name="Fixed navigation contexts",
            abbreviated_name="Fixed navigation",
            sort_order=1,
        )
        fixed_form.complete_form_cdes.set([self.navigation_cde])
        excluded_fixed_form = RegistryForm.objects.create(
            name="NavigationFixedWithoutProgress",
            registry=self.registry,
            abbreviated_name="Fixed without progress",
            sections="CAP07NAVSEC",
            position=4,
        )
        ContextFormGroupItem.objects.create(
            context_form_group=fixed_cfg, registry_form=fixed_form
        )
        ContextFormGroupItem.objects.create(
            context_form_group=fixed_cfg,
            registry_form=excluded_fixed_form,
        )
        second_form = self._second_form()

        with patch(
            "rdrf.forms.components.FormProgress.get_form_progress",
            return_value=100,
        ):
            groups = self._launcher()._get_parent_context_form_groups()

        self.assertEqual([group[1].name for group in groups], [
            fixed_cfg.name,
            self.cfg.name,
        ])
        self.assertEqual(groups[0][1].forms[0].text, fixed_form.nice_name)
        self.assertEqual(len(groups[0][1].forms), 1)
        self.assertEqual(
            [form.text for form in groups[1][1].forms],
            [self.form.nice_name, second_form.nice_name],
        )

    def test_non_parent_multiple_cfg_keeps_instance_launcher_links(self):
        first = self._context(timezone.now() - timedelta(days=2))
        second = self._context(timezone.now() - timedelta(days=1))
        self.user.groups.clear()

        groups = self._launcher()._get_multiple_contexts()

        launcher = groups[self.cfg.sort_order][0]
        self.assertEqual(launcher.existing_links_len, 2)
        self.assertEqual(
            {link.url for link in launcher.existing_links},
            {
                self.form.get_link(self.patient, first),
                self.form.get_link(self.patient, second),
            },
        )
