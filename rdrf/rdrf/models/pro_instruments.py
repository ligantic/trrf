"""Patient-Reported Outcome (PRO) instrument framework (CAP-08).

A PROInstrument is a thin, registry-configurable layer over an existing
RegistryForm: the instrument's *parts* are simply the form's Sections
(no duplication of question definitions). Answers are stored through the
existing clinical data layer (ClinicalData via DynamicDataWrapper); the
models here hold *state only* — per-part and overall completion — to
support save/continue/exit and resume across sessions.

Feature-gated by RegistryFeatures.PRO_INSTRUMENTS.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from rdrf.models.definition.models import Registry, RegistryForm


class PROInstrumentStatus(models.TextChoices):
    NOT_STARTED = "not_started", _("Not started")
    IN_PROGRESS = "in_progress", _("In progress")
    COMPLETE = "complete", _("Complete")


class PROInstrument(models.Model):
    """A configured PRO instrument (e.g. ORCA) in a registry."""

    registry = models.ForeignKey(Registry, on_delete=models.CASCADE)
    registry_form = models.ForeignKey(
        RegistryForm,
        on_delete=models.CASCADE,
        help_text="The CDE form holding the instrument's questions; "
        "the form's sections are the instrument's parts",
    )
    display_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)

    class Meta:
        unique_together = ("registry", "slug")

    def __str__(self):
        return f"{self.registry.code}/{self.slug}"

    @property
    def part_sections(self):
        """The instrument's parts, in form order (part == form Section).

        Multi-entry (allow_multiple) sections are excluded: this increment
        supports simple question-set parts only.
        """
        return [
            s
            for s in self.registry_form.section_models
            if not s.allow_multiple
        ]

    @property
    def part_codes(self):
        return [s.code for s in self.part_sections]


class PROInstrumentAdministration(models.Model):
    """One administration of an instrument for a patient (state only).

    Answers are NOT stored here — they live in the existing clinical data
    records. patient_id/context_id are plain ids following the
    ClinicalData convention (patient data may live in another database).
    """

    instrument = models.ForeignKey(
        PROInstrument, on_delete=models.CASCADE, related_name="administrations"
    )
    patient_id = models.IntegerField(db_index=True)
    context_id = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=PROInstrumentStatus.choices,
        default=PROInstrumentStatus.NOT_STARTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # D-05 scoring extension point (REQ-08-04, awaiting client): a future
    # scoring service will write computed scores here without schema rework.
    # Deliberately unused by any current code path.
    score_payload = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = ("instrument", "patient_id", "context_id")

    def __str__(self):
        return f"{self.instrument} patient={self.patient_id} [{self.status}]"

    def recalculate_status(self):
        """Derive overall status from part states and persist it."""
        section_codes = self.instrument.part_codes
        states = {
            ps.section_code: ps.status for ps in self.part_states.all()
        }
        statuses = [
            states.get(code, PROInstrumentStatus.NOT_STARTED)
            for code in section_codes
        ]
        if statuses and all(
            s == PROInstrumentStatus.COMPLETE for s in statuses
        ):
            self.status = PROInstrumentStatus.COMPLETE
        elif any(s != PROInstrumentStatus.NOT_STARTED for s in statuses):
            self.status = PROInstrumentStatus.IN_PROGRESS
        else:
            self.status = PROInstrumentStatus.NOT_STARTED
        self.save(update_fields=["status", "updated_at"])


class PROInstrumentPartState(models.Model):
    """Completion state for one part (form Section) of an administration."""

    administration = models.ForeignKey(
        PROInstrumentAdministration,
        on_delete=models.CASCADE,
        related_name="part_states",
    )
    section_code = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=PROInstrumentStatus.choices,
        default=PROInstrumentStatus.NOT_STARTED,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("administration", "section_code")

    def __str__(self):
        return f"{self.administration} {self.section_code} [{self.status}]"
