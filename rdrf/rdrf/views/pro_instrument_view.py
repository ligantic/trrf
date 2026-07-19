"""CAP-08 PRO instrument shell + part views.

Rendering choice: parts are rendered with the same dynamic form machinery
FormView uses (create_form_class_for_section + DataDefinitions +
DynamicDataWrapper), but through a dedicated lightweight view rather than
by delegating to FormView itself. FormView's get/post process *every*
section of a form at once and are entangled with consent checks, wizards,
x-ray instrumentation and file-upload plumbing that a single-part PRO page
does not need. Reusing the underlying primitives keeps answers in the
standard clinical data records (so form progress, reports and future
scoring see them) without forking the form engine.
"""

import logging

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic.base import View
from registry.patients.models import Patient

from rdrf.db.contexts_api import RDRFContextManager
from rdrf.db.dynamic_data import DynamicDataWrapper
from rdrf.forms.dynamic.dynamic_forms import create_form_class_for_section
from rdrf.helpers.registry_features import RegistryFeatures
from rdrf.models.definition.models import DataDefinitions, Registry
from rdrf.models.pro_instruments import (
    PROInstrument,
    PROInstrumentAdministration,
    PROInstrumentPartState,
    PROInstrumentStatus,
)
from rdrf.security.security_checks import security_check_user_patient

logger = logging.getLogger(__name__)

_STATUS_CSS = {
    PROInstrumentStatus.NOT_STARTED: "rdrf-badge--not-started",
    PROInstrumentStatus.IN_PROGRESS: "rdrf-badge--in-progress",
    PROInstrumentStatus.COMPLETE: "rdrf-badge--complete",
}


def _field_key(form_name, section_code, cde_code):
    return "%s%s%s%s%s" % (
        form_name,
        settings.FORM_SECTION_DELIMITER,
        section_code,
        settings.FORM_SECTION_DELIMITER,
        cde_code,
    )


def _has_value(value):
    return value not in (None, "", [], {})


def _part_status_from_data(instrument, section_model, data):
    """COMPLETE if all required CDEs in the section have values, else
    IN_PROGRESS (a saved part is never NOT_STARTED). Sections without any
    required CDEs are complete when every CDE has a value."""
    form_name = instrument.registry_form.name
    cde_models = section_model.cde_models
    required = [cde for cde in cde_models if cde.is_required] or cde_models
    complete = all(
        _has_value(data.get(_field_key(form_name, section_model.code, c.code)))
        for c in required
    )
    return (
        PROInstrumentStatus.COMPLETE
        if complete
        else PROInstrumentStatus.IN_PROGRESS
    )


class ProInstrumentViewBase(View):
    """Shared resolution + authorization for PRO instrument pages."""

    def resolve(self, request, registry_code, slug, patient_id):
        self.registry = get_object_or_404(Registry, code=registry_code)
        if not self.registry.has_feature(RegistryFeatures.PRO_INSTRUMENTS):
            raise Http404
        self.instrument = get_object_or_404(
            PROInstrument, registry=self.registry, slug=slug
        )
        # 404 for nonexistent patients, 403 for existing-but-unlinked
        # (same contract as the parent dashboard — PROPOSALS.md §2).
        self.patient = get_object_or_404(Patient, pk=patient_id)
        security_check_user_patient(request.user, self.patient)
        self.rdrf_context = RDRFContextManager(
            self.registry
        ).get_or_create_default_context(self.patient)

    def get_administration(self):
        return PROInstrumentAdministration.objects.filter(
            instrument=self.instrument,
            patient_id=self.patient.pk,
            context_id=self.rdrf_context.pk,
        ).first()

    def part_states(self, administration):
        states = {}
        if administration:
            states = {
                ps.section_code: ps.status
                for ps in administration.part_states.all()
            }
        return [
            {
                "section": section,
                "status": states.get(
                    section.code, PROInstrumentStatus.NOT_STARTED
                ),
            }
            for section in self.instrument.part_sections
        ]

    def part_url(self, section_code):
        return reverse(
            "pro_instrument_part",
            args=[
                self.registry.code,
                self.instrument.slug,
                self.patient.pk,
                section_code,
            ],
        )

    def shell_url(self):
        return reverse(
            "pro_instrument_shell",
            args=[self.registry.code, self.instrument.slug, self.patient.pk],
        )


class ProInstrumentShellView(ProInstrumentViewBase):
    """Instrument overview: part navigator, overall progress, resume."""

    def get(self, request, registry_code, slug, patient_id):
        self.resolve(request, registry_code, slug, patient_id)
        administration = self.get_administration()
        part_states = self.part_states(administration)

        parts = [
            {
                "section": p["section"],
                "status": p["status"],
                "status_label": PROInstrumentStatus(p["status"]).label,
                "status_css": _STATUS_CSS[p["status"]],
                "url": self.part_url(p["section"].code),
            }
            for p in part_states
        ]
        complete_count = sum(
            1 for p in parts if p["status"] == PROInstrumentStatus.COMPLETE
        )
        progress = (
            int(round(100 * complete_count / len(parts))) if parts else 0
        )
        # Resume at the first non-complete part
        continue_part = next(
            (p for p in parts if p["status"] != PROInstrumentStatus.COMPLETE),
            None,
        )

        context = {
            "instrument": self.instrument,
            "patient": self.patient,
            "parts": parts,
            "progress": progress,
            "continue_url": continue_part["url"] if continue_part else None,
            "overall_status": (
                administration.status
                if administration
                else PROInstrumentStatus.NOT_STARTED
            ),
        }
        return render(request, "pro_instruments/shell.html", context)


class ProInstrumentPartView(ProInstrumentViewBase):
    """One part (form Section): render questions, save, update state."""

    def _get_section(self, section_code):
        for section in self.instrument.part_sections:
            if section.code == section_code:
                return section
        raise Http404

    def _build_form_class(self, request, section_model):
        data_defs = DataDefinitions(self.instrument.registry_form)
        return create_form_class_for_section(
            self.registry,
            data_defs,
            self.instrument.registry_form,
            section_model,
            injected_model="Patient",
            injected_model_id=self.patient.pk,
            is_superuser=request.user.is_superuser,
            user_groups=request.user.groups.all(),
            patient_model=self.patient,
        )

    @staticmethod
    def _relax_required(form):
        # PRO instruments are completed incrementally over multiple
        # sessions (REQ-08-02): partial saves must succeed, so field-level
        # "required" is relaxed and completeness is tracked as part state
        # instead. Datatype validation still applies.
        for field in form.fields.values():
            field.required = False

    def _dynamic_data_wrapper(self, request):
        wrapper = DynamicDataWrapper(
            self.patient, rdrf_context_id=self.rdrf_context.pk
        )
        wrapper.user = request.user
        wrapper.current_form_model = self.instrument.registry_form
        return wrapper

    def _template_context(self, section_model, form):
        parts = self.part_sections_nav(section_model)
        return {
            "instrument": self.instrument,
            "patient": self.patient,
            "section": section_model,
            "form": form,
            "parts": parts,
            "shell_url": self.shell_url(),
        }

    def part_sections_nav(self, current_section):
        administration = self.get_administration()
        return [
            {
                "section": p["section"],
                "status_label": PROInstrumentStatus(p["status"]).label,
                "status_css": _STATUS_CSS[p["status"]],
                "url": self.part_url(p["section"].code),
                "current": p["section"].code == current_section.code,
            }
            for p in self.part_states(administration)
        ]

    def _next_part_url(self, section_model):
        codes = self.instrument.part_codes
        index = codes.index(section_model.code)
        if index + 1 < len(codes):
            return self.part_url(codes[index + 1])
        return None

    def get(self, request, registry_code, slug, patient_id, section_code):
        self.resolve(request, registry_code, slug, patient_id)
        section_model = self._get_section(section_code)
        form_class = self._build_form_class(request, section_model)
        if form_class is None:
            raise Http404

        dynamic_data = (
            self._dynamic_data_wrapper(request).load_dynamic_data(
                self.registry.code, "cdes"
            )
            or {}
        )
        form = form_class(initial=dynamic_data)
        self._relax_required(form)
        return render(
            request,
            "pro_instruments/part.html",
            self._template_context(section_model, form),
        )

    def post(self, request, registry_code, slug, patient_id, section_code):
        self.resolve(request, registry_code, slug, patient_id)
        section_model = self._get_section(section_code)
        form_class = self._build_form_class(request, section_model)
        if form_class is None:
            raise Http404

        form = form_class(request.POST)
        self._relax_required(form)
        if not form.is_valid():
            return render(
                request,
                "pro_instruments/part.html",
                self._template_context(section_model, form),
            )

        part_status = _part_status_from_data(
            self.instrument, section_model, form.cleaned_data
        )

        # Persist answers through the standard clinical data layer, and
        # refresh form progress so dashboard module status stays in sync.
        wrapper = self._dynamic_data_wrapper(request)
        data_defs = DataDefinitions(self.instrument.registry_form)
        wrapper.save_dynamic_data(
            self.registry, "cdes", data_defs, form.cleaned_data
        )
        wrapper.save_form_progress(
            self.registry, context_model=self.rdrf_context
        )

        administration, _created = (
            PROInstrumentAdministration.objects.get_or_create(
                instrument=self.instrument,
                patient_id=self.patient.pk,
                context_id=self.rdrf_context.pk,
            )
        )
        PROInstrumentPartState.objects.update_or_create(
            administration=administration,
            section_code=section_model.code,
            defaults={"status": part_status},
        )
        administration.recalculate_status()

        if "save_exit" in request.POST:
            return redirect(self.shell_url())
        next_url = self._next_part_url(section_model)
        return redirect(next_url or self.shell_url())
