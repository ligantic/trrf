"""CAP-05 Multi-Participant Caregiver Access tests (REQ-05-03).

Covers the participant-context contract from planning/capabilities/PROPOSALS.md §2:
- 403 for an authenticated caregiver requesting an existing, unlinked patient
- 404 for a nonexistent patient id
- session persistence of the selected participant per registry
- silent fallback to the first linked participant for stale session values
- carer shortcut view handling multiple patients in care
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from registry.groups import GROUPS as RDRF_GROUPS
from registry.groups.models import CustomUser
from registry.patients.models import ParentGuardian, Patient

from rdrf.helpers.utils import is_authorised
from rdrf.models.definition.models import (
    ClinicalData,
    ContextFormGroup,
    RDRFContext,
    Registry,
    RegistryDashboard,
    RegistryForm,
    Section,
)
from rdrf.patients.patient_columns import ColumnContextMenu

AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"


def create_patient(registry=None, family_name="", **kwargs):
    # Patient.Meta orders by family_name, so distinct names make
    # "first linked participant" deterministic.
    patient = Patient.objects.create(
        consent=True,
        date_of_birth="2015-01-01",
        family_name=family_name,
        **kwargs,
    )
    if registry:
        patient.rdrf_registry.set([registry])
    return patient


def create_user(group, registry=None):
    user = CustomUser.objects.create(
        username=str(uuid.uuid4()), is_active=True
    )
    user.add_group(group)
    if registry:
        user.registry.set([registry])
    return user


class ParentDashboardCaregiverAccessTest(TestCase):
    databases = ["default", "clinical"]

    def setUp(self):
        self.registry = Registry.objects.create(code="cap05")
        RegistryDashboard.objects.create(registry=self.registry)

        self.child_a = create_patient(self.registry, family_name="Aardvark")
        self.child_b = create_patient(self.registry, family_name="Baker")
        self.unlinked_patient = create_patient(
            self.registry, family_name="Zulu"
        )

        self.user = create_user(RDRF_GROUPS.PARENT, self.registry)
        self.parent = ParentGuardian.objects.create(user=self.user)
        self.parent.patient.set([self.child_a, self.child_b])

        self.dashboard_url = reverse(
            "parent_dashboard", args=[self.registry.code]
        )
        self.saved_responses_url = reverse(
            "parent_historical_data", args=[self.registry.code]
        )
        self.session_key = f"selected_patient_{self.registry.code}"

        self.client.force_login(self.user, backend=AUTH_BACKEND)

    def _dashboard_patient(self, response):
        return response.context["dashboard"]["patient"]

    def _grant_module_view_permission(self):
        permission = Permission.objects.get(codename="can_see_data_modules")
        parent_group = self.user.groups.get(name=RDRF_GROUPS.PARENT)
        parent_group.permissions.add(permission)

    def _create_saved_responses(self, patient, count):
        section = Section.objects.create(
            code="HISTORY_SECTION",
            abbreviated_name="History Section",
            elements="",
        )
        form = RegistryForm.objects.create(
            name="HistoryForm",
            registry=self.registry,
            abbreviated_name="History Form",
            sections=section.code,
            position=1,
        )
        cfg = ContextFormGroup.objects.create(
            registry=self.registry,
            code="HISTORY",
            context_type="M",
        )
        cfg.items.create(registry_form=form)
        content_type = ContentType.objects.get_for_model(patient)
        contexts = []
        for index in range(count):
            context = RDRFContext.objects.create(
                registry=self.registry,
                context_form_group=cfg,
                object_id=patient.id,
                content_type=content_type,
            )
            saved_at = datetime(2026, 1, 1) + timedelta(days=index)
            ClinicalData.objects.create(
                registry_code=self.registry.code,
                django_id=patient.id,
                django_model="Patient",
                collection="cdes",
                context_id=context.id,
                data={form.name + "_timestamp": saved_at.isoformat()},
            )
            contexts.append(context)
        return form, contexts

    def test_linked_patient_returns_200(self):
        response = self.client.get(
            self.dashboard_url, {"patient_id": self.child_a.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._dashboard_patient(response), self.child_a)

    @patch("rdrf.views.dashboard_view.consent_check", return_value=False)
    def test_patient_without_required_consent_redirects_to_consent_form(
        self, consent_check
    ):
        response = self.client.get(
            self.dashboard_url, {"patient_id": self.child_a.id}
        )

        self.assertRedirects(
            response,
            reverse(
                "consent_form_view", args=[self.registry.code, self.child_a.id]
            ),
            fetch_redirect_response=False,
        )
        consent_check.assert_called_once_with(
            self.registry, self.user, self.child_a, "see_patient"
        )

    def test_saved_responses_requires_module_view_permission(self):
        response = self.client.get(self.saved_responses_url)

        self.assertEqual(response.status_code, 403)

    def test_saved_responses_redirects_when_consent_check_fails(self):
        self._grant_module_view_permission()
        with patch(
            "rdrf.views.dashboard_view.consent_check", return_value=False
        ):
            response = self.client.get(self.saved_responses_url)

        self.assertRedirects(
            response,
            reverse(
                "consent_form_view", args=[self.registry.code, self.child_a.id]
            ),
            fetch_redirect_response=False,
        )

    def test_saved_responses_rejects_invalid_consent_status(self):
        self._grant_module_view_permission()
        with patch(
            "rdrf.views.dashboard_view.consent_status_for_patient",
            return_value=False,
        ):
            response = self.client.get(self.saved_responses_url)

        self.assertEqual(response.status_code, 403)

    def test_saved_responses_patient_selection_and_isolation(self):
        self._grant_module_view_permission()

        response = self.client.get(
            self.saved_responses_url, {"patient_id": self.child_b.id}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["patient"], self.child_b)
        self.assertContains(response, "No saved responses yet.")
        self.assertContains(response, "rdrf-segmented__option--active")
        self.assertContains(response, 'aria-current="page"')
        self.assertEqual(
            self.client.session.get(self.session_key), self.child_b.id
        )

        response = self.client.get(
            self.saved_responses_url,
            {"patient_id": self.unlinked_patient.id},
        )
        self.assertEqual(response.status_code, 403)

    def test_saved_responses_missing_patient_returns_404(self):
        self._grant_module_view_permission()
        nonexistent_id = Patient.objects.latest("id").id + 1000

        response = self.client.get(
            self.saved_responses_url, {"patient_id": nonexistent_id}
        )

        self.assertEqual(response.status_code, 404)

    def test_dashboard_links_to_saved_responses_when_longitudinal_forms_exist(
        self,
    ):
        self._grant_module_view_permission()
        self._create_saved_responses(self.child_a, 1)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Historical Data")
        self.assertContains(
            response,
            f"{self.saved_responses_url}?patient_id={self.child_a.id}",
        )

    def test_submissions_lists_all_responses_with_start_date_and_edit_link(
        self,
    ):
        self._grant_module_view_permission()
        form, contexts = self._create_saved_responses(self.child_a, 1)
        incomplete_context = RDRFContext.objects.create(
            registry=self.registry,
            context_form_group=contexts[0].context_form_group,
            object_id=self.child_a.id,
            content_type=ContentType.objects.get_for_model(self.child_a),
        )
        ClinicalData.objects.create(
            registry_code=self.registry.code,
            django_id=self.child_a.id,
            django_model="Patient",
            collection="cdes",
            context_id=incomplete_context.id,
            data={"partial_response": True},
        )
        submissions_url = reverse(
            "patient_submissions",
            kwargs={
                "registry_code": self.registry.code,
                "patient_id": self.child_a.id,
            },
        )

        response = self.client.get(submissions_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start date")
        self.assertContains(response, "Progress")
        self.assertContains(response, "100%")
        self.assertContains(response, "Not tracked")
        rows = response.context["page_obj"].object_list
        self.assertEqual(
            {row["context"].pk for row in rows},
            {contexts[0].pk, incomplete_context.pk},
        )
        incomplete_row = next(
            row for row in rows if row["context"] == incomplete_context
        )
        complete_row = next(
            row for row in rows if row["context"] == contexts[0]
        )
        self.assertEqual(
            incomplete_row["started_at"], incomplete_context.created_at
        )
        self.assertEqual(complete_row["progress"], 100)
        self.assertIsNone(incomplete_row["progress"])
        self.assertEqual(
            incomplete_row["url"],
            reverse(
                "registry_form",
                args=(
                    self.registry.code,
                    form.pk,
                    self.child_a.pk,
                    incomplete_context.pk,
                ),
            ),
        )

    def test_modules_column_links_to_patient_submissions(self):
        self._grant_module_view_permission()
        column = ColumnContextMenu(
            "Modules", "patients.can_see_data_modules"
        )
        column.configure(self.registry, self.user, 0)

        rendered = column.cell(self.child_a)

        self.assertIn("Submissions", rendered)
        self.assertIn(
            reverse(
                "patient_submissions",
                kwargs={
                    "registry_code": self.registry.code,
                    "patient_id": self.child_a.id,
                },
            ),
            rendered,
        )

    def test_submissions_rejects_patient_not_linked_to_parent(self):
        self._grant_module_view_permission()
        submissions_url = reverse(
            "patient_submissions",
            kwargs={
                "registry_code": self.registry.code,
                "patient_id": self.unlinked_patient.id,
            },
        )

        response = self.client.get(submissions_url)

        self.assertEqual(response.status_code, 403)

    def test_submissions_requires_module_view_permission(self):
        submissions_url = reverse(
            "patient_submissions",
            kwargs={
                "registry_code": self.registry.code,
                "patient_id": self.child_a.id,
            },
        )

        response = self.client.get(submissions_url)

        self.assertEqual(response.status_code, 403)

    def test_saved_responses_paginate_and_link_to_each_context(self):
        self._grant_module_view_permission()
        form, contexts = self._create_saved_responses(self.child_a, 21)

        first_page = self.client.get(self.saved_responses_url)
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(first_page.context["page_obj"].object_list), 20)
        self.assertEqual(
            first_page.context["page_obj"].object_list[0]["url"],
            reverse(
                "registry_form_view",
                args=(
                    self.registry.code,
                    form.pk,
                    self.child_a.pk,
                    contexts[-1].pk,
                ),
            ),
        )

        second_page = self.client.get(self.saved_responses_url, {"page": 2})
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.context["page_obj"].object_list), 1)
        self.assertEqual(
            second_page.context["page_obj"].object_list[0]["url"],
            reverse(
                "registry_form_view",
                args=(
                    self.registry.code,
                    form.pk,
                    self.child_a.pk,
                    contexts[0].pk,
                ),
            ),
        )
        self.assertContains(second_page, f"patient_id={self.child_a.id}")

    def test_existing_unlinked_patient_returns_403(self):
        response = self.client.get(
            self.dashboard_url, {"patient_id": self.unlinked_patient.id}
        )
        self.assertEqual(response.status_code, 403)

    def test_nonexistent_patient_returns_404(self):
        nonexistent_id = Patient.objects.latest("id").id + 1000
        response = self.client.get(
            self.dashboard_url, {"patient_id": nonexistent_id}
        )
        self.assertEqual(response.status_code, 404)

    def test_second_guardian_record_grants_access_to_its_child(self):
        secondary_parent = ParentGuardian.objects.create(user=self.user)
        secondary_parent.patient.add(self.child_b)

        self.assertTrue(is_authorised(self.user, self.child_b))

    def test_parent_page_allows_duplicate_guardian_records(self):
        ParentGuardian.objects.create(user=self.user)

        response = self.client.get(
            reverse("registry:parent_page", args=[self.registry.code])
        )

        self.assertEqual(response.status_code, 200)

    def test_default_selection_is_first_linked_participant(self):
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._dashboard_patient(response), self.child_a)

    def test_explicit_switch_persists_in_session(self):
        response = self.client.get(
            self.dashboard_url, {"patient_id": self.child_b.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session.get(self.session_key), self.child_b.id
        )

        # Next load without a param keeps showing child B
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._dashboard_patient(response), self.child_b)

    def test_stale_session_unlinked_patient_falls_back_to_first(self):
        session = self.client.session
        session[self.session_key] = self.unlinked_patient.id
        session.save()

        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._dashboard_patient(response), self.child_a)

    def test_stale_session_nonexistent_patient_falls_back_to_first(self):
        session = self.client.session
        session[self.session_key] = Patient.objects.latest("id").id + 1000
        session.save()

        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._dashboard_patient(response), self.child_a)


class CarerShortcutViewTest(TestCase):
    def setUp(self):
        self.registry = Registry.objects.create(code="cap05")
        self.carer = create_user(RDRF_GROUPS.CARER, self.registry)
        self.shortcut_url = reverse(
            "registry:patient_page", args=[self.registry.code]
        )
        self.client.force_login(self.carer, backend=AUTH_BACKEND)

    def test_carer_with_one_patient_redirects_to_patient_edit(self):
        patient = create_patient(self.registry, carer=self.carer)
        response = self.client.get(self.shortcut_url)
        self.assertRedirects(
            response,
            reverse("patient_edit", args=[self.registry.code, patient.id]),
            fetch_redirect_response=False,
        )

    def test_carer_with_two_patients_redirects_to_patient_listing(self):
        create_patient(self.registry, carer=self.carer)
        create_patient(self.registry, carer=self.carer)
        response = self.client.get(self.shortcut_url)
        self.assertRedirects(
            response,
            reverse("patientslisting"),
            fetch_redirect_response=False,
        )

    def test_carer_with_no_patients_returns_404(self):
        response = self.client.get(self.shortcut_url)
        self.assertEqual(response.status_code, 404)
