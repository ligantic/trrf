import datetime
from dataclasses import dataclass

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from registry.groups import GROUPS
from registry.groups.models import CustomUser, WorkingGroup
from registry.patients.models import (
    LongitudinalFollowupEntry,
    LongitudinalFollowupQueueState,
    Patient,
)

from rdrf.helpers.cde_data_types import CDEDataTypes
from rdrf.models.definition.models import (
    CommonDataElement,
    ConsentQuestion,
    LongitudinalFollowup,
    RDRFContext,
    Section,
)


@dataclass(frozen=True)
class Scenario:
    slug: str
    account_active: bool
    creates_patient: bool = False
    registry_consents: bool = False
    history_count: int = 0
    alert: str | None = None


SCENARIOS = (
    Scenario("signup-pending", False),
    Scenario("account-active", True),
    Scenario("onboarding", True, creates_patient=True),
    Scenario(
        "consented-no-history",
        True,
        creates_patient=True,
        registry_consents=True,
    ),
    Scenario(
        "one-history-future-alert",
        True,
        creates_patient=True,
        registry_consents=True,
        history_count=1,
        alert="future",
    ),
    Scenario(
        "many-history-due-alert",
        True,
        creates_patient=True,
        registry_consents=True,
        history_count=3,
        alert="due",
    ),
)


class DevelopmentScenarioSeeder:
    password = "development-only"

    def __init__(self, registry, stdout=None):
        self.registry = registry
        self.stdout = stdout
        self.prefix = f"dev-seed-{registry.code}"
        self.working_group = WorkingGroup.objects.get_unallocated(registry)
        self.patient_group, _ = Group.objects.get_or_create(
            name=GROUPS.PATIENT)
        self.clinical_target = self._find_clinical_target()

    def seed(self):
        for index, scenario in enumerate(SCENARIOS, start=1):
            user = self._seed_user(scenario)
            if scenario.creates_patient:
                patient = self._seed_patient(index, scenario, user)
                self._seed_consents(patient, scenario)
                self._seed_history(patient, scenario)
                self._seed_alert(patient, scenario)
        return self.summary()

    def summary(self):
        usernames = [self._username(scenario) for scenario in SCENARIOS]
        return {
            "accounts": CustomUser.objects.filter(username__in=usernames).count(),
            "patients": Patient.objects.filter(
                umrn__startswith=f"{self.prefix}-"
            ).count(),
            "clinical_contexts": RDRFContext.objects.filter(
                registry=self.registry,
                display_name__startswith=f"{self.prefix}-history-",
            ).count(),
            "alerts": LongitudinalFollowupEntry.objects.filter(
                patient__umrn__startswith=f"{self.prefix}-"
            ).count(),
        }

    def _username(self, scenario):
        return f"{self.prefix}-{scenario.slug}@example.test"

    def _seed_user(self, scenario):
        username = self._username(scenario)
        user, _ = CustomUser.objects.update_or_create(
            username=username,
            defaults={
                "email": username,
                "first_name": scenario.slug.replace("-", " ").title()[:30],
                "last_name": "Dev Seed",
                "is_active": scenario.account_active,
                "is_staff": False,
            },
        )
        user.set_password(self.password)
        user.save(update_fields=["password"])
        user.registry.set([self.registry])
        user.working_groups.set([self.working_group])
        user.groups.add(self.patient_group)
        return user

    def _seed_patient(self, index, scenario, user):
        identifier = f"{self.prefix}-{scenario.slug}"
        patient, _ = Patient.objects.update_or_create(
            umrn=identifier,
            defaults={
                "consent": scenario.registry_consents,
                "family_name": "Dev Seed",
                "given_names": scenario.slug.replace("-", " ").title(),
                "date_of_birth": datetime.date(2000 + index, index, index),
                "sex": str((index % 3) + 1),
                "email": user.email,
                "user": user,
                "active": True,
            },
        )
        patient.rdrf_registry.add(self.registry)
        patient.working_groups.set([self.working_group])
        return patient

    def _seed_consents(self, patient, scenario):
        if not scenario.registry_consents:
            return
        for question in ConsentQuestion.objects.filter(section__registry=self.registry):
            patient.set_consent(question, answer=True)

    def _find_clinical_target(self):
        followups = LongitudinalFollowup.objects.filter(
            context_form_group__registry=self.registry
        ).select_related("context_form_group")
        unsupported = {CDEDataTypes.CALCULATED,
                       CDEDataTypes.FILE, CDEDataTypes.LOOKUP}

        for followup in followups.order_by("name"):
            for item in followup.context_form_group.items.select_related(
                "registry_form"
            ):
                form = item.registry_form
                for section_code in form.get_sections():
                    section = Section.objects.filter(code=section_code).first()
                    if not section:
                        continue
                    for cde_code in section.get_elements():
                        cde = CommonDataElement.objects.filter(
                            code=cde_code).first()
                        if cde and cde.datatype not in unsupported:
                            return followup, form, section, cde
        return None

    def _seed_history(self, patient, scenario):
        if not scenario.history_count:
            return
        if not self.clinical_target:
            raise ValueError(
                f"Registry {self.registry.code} has no writable longitudinal field."
            )

        followup, form, section, cde = self.clinical_target
        content_type = ContentType.objects.get_for_model(patient)
        for sequence in range(1, scenario.history_count + 1):
            display_name = f"{self.prefix}-history-{scenario.slug}-{sequence}"
            context, _ = RDRFContext.objects.get_or_create(
                registry=self.registry,
                content_type=content_type,
                object_id=patient.pk,
                context_form_group=followup.context_form_group,
                display_name=display_name,
            )
            patient.set_form_value(
                self.registry.code,
                form.name,
                section.code,
                cde.code,
                self._value_for(cde, sequence),
                context_model=context,
            )

    def _value_for(self, cde, sequence):
        if cde.pv_group_id:
            permitted = cde.pv_group.permitted_value_set.order_by(
                "position", "code"
            ).first()
            value = permitted.code if permitted else ""
        else:
            value = {
                CDEDataTypes.BOOL: True,
                CDEDataTypes.DATE: f"2025-01-{sequence:02d}",
                CDEDataTypes.DURATION: str(sequence),
                CDEDataTypes.EMAIL: f"history-{sequence}@example.test",
                CDEDataTypes.FLOAT: float(sequence),
                CDEDataTypes.INTEGER: sequence,
                CDEDataTypes.TIME: "09:00",
            }.get(cde.datatype, f"Synthetic history {sequence}")
        return [value] if cde.allow_multiple else value

    def _seed_alert(self, patient, scenario):
        LongitudinalFollowupEntry.objects.filter(
            patient=patient,
            longitudinal_followup__context_form_group__registry=self.registry,
        ).delete()
        if not scenario.alert:
            return
        if not self.clinical_target:
            raise ValueError(
                f"Registry {self.registry.code} has no longitudinal followup."
            )

        followup = self.clinical_target[0]
        send_at = (
            timezone.now() - datetime.timedelta(days=1)
            if scenario.alert == "due"
            else timezone.now() + datetime.timedelta(days=30)
        )
        LongitudinalFollowupEntry.objects.create(
            longitudinal_followup=followup,
            patient=patient,
            created_by=None,
            send_at=send_at,
            state=LongitudinalFollowupQueueState.PENDING,
        )
