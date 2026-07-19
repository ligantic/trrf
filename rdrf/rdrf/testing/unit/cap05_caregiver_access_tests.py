"""CAP-05 Multi-Participant Caregiver Access tests (REQ-05-03).

Covers the participant-context contract from planning/capabilities/PROPOSALS.md §2:
- 403 for an authenticated caregiver requesting an existing, unlinked patient
- 404 for a nonexistent patient id
- session persistence of the selected participant per registry
- silent fallback to the first linked participant for stale session values
- carer shortcut view handling multiple patients in care
"""

import uuid

from django.test import TestCase
from django.urls import reverse
from registry.groups import GROUPS as RDRF_GROUPS
from registry.groups.models import CustomUser
from registry.patients.models import ParentGuardian, Patient

from rdrf.models.definition.models import Registry, RegistryDashboard

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
        self.session_key = f"selected_patient_{self.registry.code}"

        self.client.force_login(self.user, backend=AUTH_BACKEND)

    def _dashboard_patient(self, response):
        return response.context["dashboard"]["patient"]

    def test_linked_patient_returns_200(self):
        response = self.client.get(
            self.dashboard_url, {"patient_id": self.child_a.id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._dashboard_patient(response), self.child_a)

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
