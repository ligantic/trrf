import logging
import re
from collections import defaultdict
from datetime import timezone as datetime_timezone

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.module_loading import import_string
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from registry.patients.models import (
    ConsentValue,
    LongitudinalFollowupEntry,
    LongitudinalFollowupQueueState,
    ParentGuardian,
    Patient,
)
from report.utils import get_graphql_result_value

from rdrf.forms.progress.form_progress import FormProgress
from rdrf.helpers.dashboard_status import (
    cadence_label,
    is_form_complete,
    module_status,
)
from rdrf.helpers.registry_features import RegistryFeatures
from rdrf.helpers.utils import consent_check, consent_status_for_patient
from rdrf.models.definition.models import (
    ClinicalData,
    ConsentQuestion,
    ContextFormGroup,
    LongitudinalFollowup,
    RDRFContext,
    Registry,
    RegistryDashboard,
)
from rdrf.models.pro_instruments import (
    PROInstrument,
    PROInstrumentAdministration,
    PROInstrumentStatus,
)
from rdrf.patients.query_data import query_patient

logger = logging.getLogger(__name__)


class ParentDashboard(object):
    def __init__(self, request, dashboard, patient):
        self.dashboard = dashboard
        self.registry = dashboard.registry
        self.patient = patient

        self._request = request
        self._contexts = self._load_contexts()

    def _load_contexts(self):
        def last_context(context_form_group):
            return (
                contexts.filter(context_form_group=context_form_group)
                .order_by("-last_updated")
                .first()
            )

        context_form_groups = ContextFormGroup.objects.filter(
            registry=self.registry
        )
        contexts = RDRFContext.objects.get_for_patient(
            self.patient, self.registry
        )

        return {
            context_form_group: last_context(context_form_group)
            for context_form_group in context_form_groups
        }

    def _get_patient_context(self, context_form_group):
        context = self._contexts.get(context_form_group)
        if context:
            return context

        if context_form_group.is_fixed:
            return self.patient.default_context(self.registry)

        return None

    def _get_saved_responses(self):
        user = self._request.user
        if not self.patient or not user.has_perm("patients.can_see_data_modules"):
            return []

        forms_by_group = {}
        for context_form_group in ContextFormGroup.objects.filter(
            registry=self.registry
        ):
            if not (
                context_form_group.is_multiple
                and context_form_group.supports_direct_linking
            ):
                continue

            form = context_form_group.forms[0]
            if user.can_view(form) and form.applicable_to(self.patient):
                forms_by_group[context_form_group.id] = form

        contexts = list(
            RDRFContext.objects.get_for_patient(self.patient, self.registry)
            .filter(context_form_group_id__in=forms_by_group)
            .select_related("context_form_group")
        )
        if not contexts:
            return []

        context_by_id = {context.id: context for context in contexts}
        data_by_context = {}
        records = (
            ClinicalData.objects.collection(self.registry.code, "cdes")
            .find(self.patient)
            .filter(context_id__in=context_by_id)
            .order_by("pk")
        )
        for record in records:
            data_by_context.setdefault(record.context_id, record.data)

        rows = []
        form_progress = FormProgress(self.registry)
        for context_id, data in data_by_context.items():
            context = context_by_id[context_id]
            form = forms_by_group[context.context_form_group_id]
            try:
                saved_at = parse_datetime(data.get(form.name + "_timestamp"))
            except (TypeError, ValueError):
                continue
            if saved_at is None:
                continue
            has_progress = form.has_progress_indicator
            progress = (
                form_progress.get_form_progress(form, self.patient, context)
                if has_progress
                else None
            )
            if not is_form_complete(progress, saved_at, has_progress):
                continue

            rows.append(
                {
                    "form": form,
                    "context": context,
                    "saved_at": saved_at,
                    "url": reverse(
                        "registry_form_view",
                        args=(
                            self.registry.code,
                            form.pk,
                            self.patient.pk,
                            context.pk,
                        ),
                    ),
                }
            )

        def sort_key(row):
            saved_at = row["saved_at"]
            comparable_time = (
                saved_at.replace(tzinfo=datetime_timezone.utc)
                if timezone.is_naive(saved_at)
                else saved_at.astimezone(datetime_timezone.utc)
            )
            return comparable_time, row["context"].id

        return sorted(rows, key=sort_key, reverse=True)

    def _get_form_link(self, context_form_group, registry_form, context=None):
        if not context:
            context = self._get_patient_context(context_form_group)

        if context:
            return registry_form.get_link(self.patient, context)

        if context_form_group.is_multiple:
            link, title = context_form_group.get_add_action(self.patient)
            return link
        return None

    def _patient_consent_summary(self):
        registry_consent_questions = list(
            ConsentQuestion.objects.filter(section__registry=self.registry)
            .order_by("section__code", "position", "pk")
        )
        patient_consents = list(ConsentValue.objects.filter(
            patient=self.patient,
            consent_question__section__registry=self.registry,
        ).select_related("consent_question"))
        consent_answers = {
            consent.consent_question_id: consent for consent in patient_consents
        }
        consented = []
        not_consented = []
        not_completed = []

        for question in registry_consent_questions:
            translated_question_label = _(question.question_label)
            question_label = re.sub(
                r"^\s*\d+\.\s+", "", translated_question_label
            )
            consent = consent_answers.get(question.pk)
            if consent is None:
                not_completed.append(question_label)
            elif consent.answer:
                consented.append(question_label)
            else:
                not_consented.append(question_label)

        completed = len(consent_answers)
        total = len(registry_consent_questions)
        if completed == 0:
            status_css = "not-started"
            status_label = _("Not started")
        elif completed == total:
            status_css = "complete"
            status_label = _("Complete")
        else:
            status_css = "in-progress"
            status_label = _("In progress")

        return {
            "valid": consent_status_for_patient(
                self.registry.code, self.patient
            ),
            "completed": completed,
            "total": total,
            "status_css": status_css,
            "status_label": status_label,
            "consented": consented,
            "not_consented": not_consented,
            "not_completed": not_completed,
            "last_updated": max(
                (consent.last_update for consent in patient_consents if consent.last_update),
                default=None,
            ),
        }

    def _get_module_progress(self):
        if not self._request.user.has_perm("patients.can_see_data_modules"):
            return None

        form_progress = FormProgress(self.registry)
        multi_context_group_ids = [
            cfg.id for cfg in self._contexts if cfg.is_multiple
        ]
        followups = {
            followup.context_form_group_id: followup
            for followup in LongitudinalFollowup.objects.filter(
                context_form_group_id__in=multi_context_group_ids
            )
        }
        pending_entries = {}
        for entry in LongitudinalFollowupEntry.objects.filter(
            patient=self.patient,
            state=LongitudinalFollowupQueueState.PENDING,
            longitudinal_followup__context_form_group_id__in=multi_context_group_ids,
        ).select_related("longitudinal_followup").order_by("send_at"):
            pending_entries.setdefault(
                entry.longitudinal_followup.context_form_group_id, entry
            )

        modules_progress = defaultdict(dict)  # {'fixed': {}, 'multi': {}}

        for cfg, context in self._contexts.items():
            forms_progress = {}
            key = None
            for form in cfg.forms:
                if not (
                    self._request.user.can_view(form)
                    and form.applicable_to(self.patient)
                ):
                    continue

                progress_dict = {}

                if cfg.is_fixed:
                    if not form.has_progress_indicator:
                        continue

                    key = "fixed"
                    progress_dict["link"] = self._get_form_link(
                        cfg, form, context=context
                    )
                    progress_dict["progress"] = form_progress.get_form_progress(
                        form, self.patient, context
                    )
                    progress_dict["status"] = module_status(
                        progress=progress_dict["progress"],
                        has_progress=form.has_progress_indicator,
                    )
                elif cfg.is_multiple:
                    key = "multi"
                    last_completed = None
                    progress = form_progress.get_form_progress(
                        form, self.patient, context
                    )

                    if context:
                        form_timestamp = self.patient.get_form_timestamp(
                            form, context
                        )
                        if form_timestamp:
                            last_completed = parse_datetime(form_timestamp)

                    followup = followups.get(cfg.id)
                    pending_entry = pending_entries.get(cfg.id)
                    next_due = (
                        pending_entry.send_at
                        if pending_entry
                        else (
                            last_completed + followup.frequency
                            if last_completed and followup
                            else None
                        )
                    )
                    status = module_status(
                        progress=progress,
                        last_completed=last_completed,
                        next_due=next_due,
                        today=(
                            timezone.localtime().date()
                            if timezone.is_aware(timezone.now())
                            else timezone.now().date()
                        ),
                        has_progress=form.has_progress_indicator,
                    )
                    progress_dict["link"] = self._get_form_link(
                        cfg, form, context=context
                    )
                    progress_dict.update(
                        {
                            "progress": progress,
                            "last_completed": last_completed,
                            "next_due": next_due,
                            "cadence": cadence_label(
                                followup.frequency if followup else None
                            ),
                            "status": status,
                        }
                    )

                forms_progress.update({form: progress_dict})
            if key:
                modules_progress[key].update({cfg: forms_progress})

        return modules_progress

    def _get_pro_instruments(self):
        if not self.registry.has_feature(RegistryFeatures.PRO_INSTRUMENTS):
            return []

        administrations = {}
        for administration in PROInstrumentAdministration.objects.filter(
            instrument__registry=self.registry,
            patient_id=self.patient.pk,
        ).order_by("-updated_at"):
            administrations.setdefault(
                administration.instrument_id, administration)

        instruments = []
        for instrument in PROInstrument.objects.filter(registry=self.registry).order_by(
            "display_name"
        ):
            administration = administrations.get(instrument.pk)
            status = (
                administration.status
                if administration
                else PROInstrumentStatus.NOT_STARTED
            )
            instruments.append(
                {
                    "name": instrument.display_name,
                    "url": reverse(
                        "pro_instrument_shell",
                        args=[
                            self.registry.code,
                            instrument.slug,
                            self.patient.pk,
                        ],
                    ),
                    "status_label": PROInstrumentStatus(status).label,
                    "status_css": status.replace("_", "-"),
                }
            )
        return instruments

    def _get_cde_data(self, cfg, form, section, cde):
        context = self._get_patient_context(cfg)

        if not context:
            return None

        try:
            form_value = self.patient.get_form_value(
                self.registry.code,
                form.name,
                section.code,
                cde.code,
                multisection=section.allow_multiple,
                context_id=context.id,
            )
        except KeyError:
            # Value not filled out yet
            return None

        if section.allow_multiple and cde.allow_multiple:
            # Then the value will be like [[1,2],[2, 3,4]], and will require some flattening
            flattened_value = {
                value
                for multisection_entry in form_value
                for value in multisection_entry
            }
            form_value = sorted(flattened_value)

        return cde.display_value(form_value)

    def _get_demographic_data(self, widget):
        config = {
            demographic.field: _(demographic.label)
            for demographic in widget.demographics.all()
            if demographic.model == "patient"
        }
        fields = config.keys()

        if fields:
            result = query_patient(
                self._request, self.registry, self.patient.id, fields
            )
            if result:
                return {
                    k: {
                        "label": v,
                        "value": get_graphql_result_value(result, k),
                    }
                    for k, v in config.items()
                }

        return {}

    def _get_registry_plugin(self, widget):
        provider_path = getattr(
            settings, "REGISTRY_DASHBOARD_WIDGET_PROVIDERS", {}
        ).get(widget.provider)
        if not provider_path:
            logger.warning(
                "No dashboard widget provider configured for '%s'", widget.provider
            )
            return None

        plugin = import_string(provider_path)(self, widget)
        if not plugin:
            return None
        plugin["widget"] = {
            "title": _(widget.title),
            "free_text": _(widget.free_text),
        }
        return plugin

    def _get_registry_plugins(self):
        plugins = defaultdict(list)
        for widget in self.dashboard.widgets.filter(widget_type="registry_plugin"):
            plugin = self._get_registry_plugin(widget)
            if plugin:
                plugins[plugin.get("placement", "secondary")].append(plugin)
        return plugins

    def _get_widget_summary(self):
        return {
            widget.widget_type: {
                "title": _(widget.title),
                "free_text": _(widget.free_text),
                "form_links": [
                    {
                        "label": _(link.label),
                        "url": self._get_form_link(
                            link.context_form_group, link.registry_form
                        ),
                    }
                    for link in widget.links.all()
                    if self._request.user.can_view(link.registry_form)
                ],
                "clinical_data": [
                    {
                        "label": _(cde.label),
                        "data": self._get_cde_data(
                            cde.context_form_group,
                            cde.registry_form,
                            cde.section,
                            cde.cde,
                        ),
                    }
                    for cde in widget.cdes.all()
                ],
                "demographic_data": self._get_demographic_data(widget),
            }
            for widget in self.dashboard.widgets.exclude(widget_type="registry_plugin")
        }

    def template(self):
        return {
            "registry": self.registry,
            "patient": self.patient,
            "patient_status": {
                "consent": self._patient_consent_summary(),
                "module_progress": self._get_module_progress(),
            },
            "pro_instruments": self._get_pro_instruments(),
            "widgets": self._get_widget_summary(),
            "registry_plugins": self._get_registry_plugins(),
        }


class BaseDashboardView(View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = None
        self.parent = None

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        registry_code = kwargs.get("registry_code")
        parent_id = request.GET.get("parent_id")

        user_allowed = user.is_superuser or user.is_parent
        if not user_allowed:
            raise PermissionDenied

        if registry_code:
            self.registry = get_object_or_404(
                Registry, code=kwargs["registry_code"]
            )
            if not request.user.in_registry(self.registry):
                raise PermissionDenied

        if user.is_superuser and parent_id:
            self.parent = get_object_or_404(ParentGuardian, pk=parent_id)
        else:
            self.parent = ParentGuardian.objects.filter(user=user).first()

        if not self.parent:
            if user.is_superuser:
                raise Http404(_("parent_id is a required parameter"))
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)


class DashboardListView(BaseDashboardView):
    def get(self, request):
        if request.user.is_superuser:
            dashboards = self.parent.user.dashboards
        else:
            dashboards = request.user.dashboards

        if not dashboards:
            raise Http404(_("No Dashboards for this user"))

        if len(dashboards) == 1:
            return redirect(
                reverse(
                    "parent_dashboard", args=[dashboards.first().registry.code]
                )
            )

        context = {"dashboards": dashboards}

        return render(request, "dashboard/dashboards_list.html", context)


class ParentDashboardView(BaseDashboardView):
    @staticmethod
    def _session_key(registry_code):
        return f"selected_patient_{registry_code}"

    @staticmethod
    def _get_patient(user, patients, requested_patient_id):
        if requested_patient_id:
            patient = get_object_or_404(Patient, pk=requested_patient_id)
            if user.is_parent and patient not in patients:
                raise PermissionDenied
            else:
                return patient

        if len(patients) > 0:
            return patients[0]
        return None

    @staticmethod
    def _get_session_patient(patients, session_patient_id):
        if session_patient_id is None:
            return None
        return next(
            (
                patient
                for patient in patients
                if patient.id == session_patient_id
            ),
            None,
        )

    def _resolve_patient(self, request):
        patients = [
            patient
            for patient in self.parent.children
            if self.registry in patient.rdrf_registry.all()
        ]

        session_key = self._session_key(self.registry.code)
        patient_id = request.GET.get("patient_id")

        if patient_id:
            # Explicit switch: 404 if the id doesn't exist, 403 if it exists
            # but isn't linked to this parent. Persist the selection.
            patient = self._get_patient(request.user, patients, patient_id)
            if patient:
                request.session[session_key] = patient.id
        else:
            # Session-stored selection, only honoured if still authorised;
            # otherwise silently fall back to the first linked participant.
            patient = self._get_session_patient(
                patients, request.session.get(session_key)
            ) or self._get_patient(request.user, patients, None)

        if patient and not consent_check(
            self.registry, request.user, patient, "see_patient"
        ):
            consent_redirect = redirect(
                reverse(
                    "consent_form_view",
                    kwargs={
                        "registry_code": self.registry.code,
                        "patient_id": patient.id,
                    },
                )
            )
            return patients, patient, consent_redirect

        return patients, patient, None

    def get(self, request, registry_code):
        dashboard = get_object_or_404(
            RegistryDashboard, registry=self.registry)
        patients, patient, response = self._resolve_patient(request)
        if response:
            return response

        context = {
            "parent": self.parent,
            "patients": patients,
            "registry_code": self.registry.code,
            "parent_id": request.GET.get("parent_id"),
            "dashboard": ParentDashboard(
                request, dashboard, patient
            ).template(),
        }

        return render(request, "dashboard/parent_dashboard.html", context)


class ParentSavedResponsesView(ParentDashboardView):
    page_size = 20

    def get(self, request, registry_code):
        dashboard = get_object_or_404(
            RegistryDashboard, registry=self.registry
        )
        patients, patient, response = self._resolve_patient(request)
        if response:
            return response

        if not request.user.has_perm("patients.can_see_data_modules"):
            raise PermissionDenied
        if patient and not consent_status_for_patient(
            self.registry.code, patient
        ):
            raise PermissionDenied

        rows = (
            ParentDashboard(request, dashboard, patient)._get_saved_responses()
            if patient
            else []
        )
        page_obj = Paginator(rows, self.page_size).get_page(
            request.GET.get("page")
        )
        return render(
            request,
            "dashboard/saved_responses.html",
            {
                "parent": self.parent,
                "patients": patients,
                "registry": self.registry,
                "patient": patient,
                "parent_id": request.GET.get("parent_id"),
                "page_obj": page_obj,
            },
        )
