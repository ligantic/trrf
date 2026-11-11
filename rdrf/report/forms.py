import json
import logging

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.forms import (
    BooleanField,
    CheckboxSelectMultiple,
    ChoiceField,
    ModelChoiceField,
    ModelForm,
    MultipleChoiceField,
    Select,
    SelectMultiple,
)
from django.utils.translation import gettext_lazy as _
from rdrf.helpers.utils import mongo_key
from rdrf.models.definition.models import (
    ConsentQuestion,
    ContextFormGroup,
    Registry,
    RegistryForm,
)
from registry.groups.forms import working_group_optgroup_choices
from registry.groups.models import WorkingGroup

from report.filter_providers import (
    get_report_filter_providers,
    validate_custom_filter_configuration,
    validate_report_filter_parameters,
)
from report.models import (
    ReportClinicalDataField,
    ReportDemographicField,
    ReportDesign,
)
from report.utils import load_report_configuration

logger = logging.getLogger(__name__)


def get_demographic_field_value(model_name, field):
    return json.dumps({"model": model_name, "field": field})


def get_demographic_field_choices(cfg_demographic_model):
    return [
        (
            model_attrs["label"],
            [
                (get_demographic_field_value(model, key), value)
                for key, value in model_attrs["fields"].items()
            ],
        )
        for model, model_attrs in cfg_demographic_model.items()
        if model_attrs.get("show_in_designer", True)
    ]


def get_cde_field_value(context_form_group, cde_key):
    return json.dumps({"cfg": context_form_group.id, "cde_key": cde_key})


def get_cde_choices():
    return [
        (
            get_cde_field_value(
                cfg, mongo_key(form.name, section.code, cde.code)
            ),
            cde.name,
        )
        for cfg in ContextFormGroup.objects.all()
        for form in cfg.forms
        for section in form.section_models
        for cde in section.cde_models
    ]


def get_section_choices():
    def get_field_value(form, section):
        return json.dumps(
            {
                "registry": form.registry.code,
                "form": form.name,
                "section": section.display_name,
            }
        )

    fields = [("", "Show all Clinical Data Fields")]

    fields.extend(
        [
            (
                form.name,
                [
                    (
                        get_field_value(form, section),
                        section.display_name
                        if section.display_name.strip()
                        else "Form",
                    )
                    for section in form.section_models
                ],
            )
            for form in RegistryForm.objects.all()
        ]
    )

    return fields


def get_working_group_field_value(wg):
    return json.dumps(
        {"registry": wg.registry.code if wg.registry else "", "wg": wg.id}
    )


def get_working_group_choices():
    def make_working_group_field(wg):
        return get_working_group_field_value(wg), wg.display_name

    return working_group_optgroup_choices(
        WorkingGroup.objects.all(), make_option_fn=make_working_group_field
    )


def get_filter_consent_field_value(consent_question):
    return json.dumps(
        {
            "registry": consent_question.section.registry.code,
            "consent_question": consent_question.id,
        }
    )


def get_filter_consent_choices():
    return [
        (
            get_filter_consent_field_value(consent_question),
            consent_question.question_label,
        )
        for consent_question in ConsentQuestion.objects.all().order_by(
            "position"
        )
    ]


class ReportDesignerForm(ModelForm):
    registry = ModelChoiceField(
        label=_("Registry"),
        widget=Select(attrs={"class": "form-select"}),
        queryset=Registry.objects.all(),
        to_field_name="code",
    )
    demographic_fields = MultipleChoiceField(
        label=_("Demographic Fields"), required=False
    )
    search_cdes_by_section = ChoiceField(
        label=_("Filter fields by section"),
        widget=Select(attrs={"class": "form-select"}),
        required=False,
    )
    cde_fields = MultipleChoiceField(label=_("Fields"), required=False)
    filter_by_consents = BooleanField(
        label=_("Filter patients by consents"), required=False
    )
    filter_consents = MultipleChoiceField(
        label=_("Consent Items"), widget=CheckboxSelectMultiple, required=False
    )
    filter_by_working_groups = BooleanField(
        label=_("Filter patients by working group"), required=False
    )
    exclude_by_working_groups = BooleanField(
        label=_("Exclude patients by working group"), required=False
    )
    exclude_working_groups = MultipleChoiceField(
        label=_("Excluded working groups"),
        widget=SelectMultiple(attrs={"class": "form-select"}),
        required=False,
    )
    filter_working_groups = MultipleChoiceField(
        label=_("Working groups"),
        widget=SelectMultiple(attrs={"class": "form-select"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        def init_report_configuration():
            return load_report_configuration()["demographic_model"]

        super(ReportDesignerForm, self).__init__(*args, **kwargs)
        report_configuration = init_report_configuration()

        # Initialise choices during object initialisation to avoid compilation errors
        # when attempting to modify the models that are queried to build these choices.
        self.fields[
            "demographic_fields"
        ].choices = get_demographic_field_choices(report_configuration)
        self.fields["search_cdes_by_section"].choices = get_section_choices()
        self.fields["cde_fields"].choices = get_cde_choices()
        self.fields["filter_consents"].choices = get_filter_consent_choices()
        self.fields[
            "filter_working_groups"
        ].choices = get_working_group_choices()
        self.fields["exclude_working_groups"].choices = self.fields[
            "filter_working_groups"
        ].choices
        self.fields["remove_existing_custom_filters"] = BooleanField(
            label=_("Remove existing custom filters"), required=False
        )

        run_report_permission = Permission.objects.get(
            codename="can_run_reports",
            content_type=ContentType.objects.get_for_model(ReportDesign),
        )
        self.fields["access_groups"].queryset = Group.objects.filter(
            permissions=run_report_permission
        ).order_by("name")
        self._init_custom_filter_forms()

    def _init_custom_filter_forms(self):
        stored_configuration = {}
        self._stored_custom_filter_error = None
        if self.instance.pk and self.instance.custom_filters:
            try:
                stored_configuration = validate_custom_filter_configuration(
                    self.instance.registry, self.instance.custom_filters
                )
            except (
                ValidationError,
                ImproperlyConfigured,
                ImportError,
                AttributeError,
            ) as error:
                self._stored_custom_filter_error = str(error)

        stored_filters = stored_configuration.get("filters", {})
        self.custom_filter_groups = []
        self._custom_filter_fields = {}
        field_index = 0
        instance_registry_code = getattr(
            getattr(self.instance, "registry", None), "code", None
        )
        selected_registry_code = (
            self.data.get("registry")
            if self.is_bound
            else instance_registry_code
        )

        for registry in Registry.objects.all().order_by("code"):
            try:
                providers = get_report_filter_providers(registry)
                registry_error = None
            except (
                ImproperlyConfigured,
                ImportError,
                AttributeError,
            ) as error:
                providers = {}
                registry_error = str(error)

            filters = []
            for filter_key, provider in sorted(providers.items()):
                saved = (
                    stored_filters.get(filter_key, {})
                    if registry.code == instance_registry_code
                    else {}
                )
                enabled_name = f"custom_filter_enabled_{field_index}"
                prefix = f"custom_filter_{field_index}"
                initial_parameters = saved.get("parameters", {})
                self.fields[enabled_name] = BooleanField(
                    label=provider.label,
                    required=False,
                    initial=bool(saved),
                )
                parameter_form = provider.parameter_form_class(
                    data=self.data if self.is_bound else None,
                    initial=initial_parameters,
                    prefix=prefix,
                )
                item = {
                    "key": filter_key,
                    "provider": provider,
                    "enabled_field": self[enabled_name],
                    "parameter_form": parameter_form,
                    "enabled_name": enabled_name,
                    "prefix": prefix,
                }
                filters.append(item)
                self._custom_filter_fields[(registry.code, filter_key)] = (
                    enabled_name,
                    parameter_form,
                    provider,
                )
                field_index += 1

            self.custom_filter_groups.append(
                {
                    "registry": registry,
                    "filters": filters,
                    "error": registry_error,
                }
            )

        self.has_existing_custom_filters = bool(
            self.instance.pk and self.instance.custom_filters
        )
        self.custom_filter_registry_changed = bool(
            self.has_existing_custom_filters
            and selected_registry_code
            and selected_registry_code
            != instance_registry_code
        )
        self.custom_filter_configuration_error = (
            self._stored_custom_filter_error
        )

    class Meta:
        model = ReportDesign
        fields = [
            "id",
            "title",
            "description",
            "access_groups",
            "cde_heading_format",
            "cde_include_form_timestamp",
        ]
        labels = {
            "title": _("Title"),
            "description": _("Description"),
            "access_groups": _("Access Groups"),
            "cde_heading_format": _("Heading Format"),
            "cde_include_form_timestamp": _(
                "Include Form Last Updated Timestamp in extract"
            ),
        }

    def setup_initials(self):
        if self.instance.id:
            self.fields["registry"].initial = (
                self.instance.registry.code if self.instance.registry else None
            )
            self.fields["demographic_fields"].initial = [
                get_demographic_field_value(rdf.model, rdf.field)
                for rdf in self.instance.reportdemographicfield_set.all()
            ]
            self.fields["cde_fields"].initial = [
                get_cde_field_value(rcf.context_form_group, rcf.cde_key)
                for rcf in self.instance.reportclinicaldatafield_set.all()
            ]
            self.fields["filter_by_consents"].initial = (
                self.instance.filter_consents.count() > 0
            )
            self.fields["filter_consents"].initial = [
                get_filter_consent_field_value(consent)
                for consent in self.instance.filter_consents.all()
            ]
            self.fields["filter_by_working_groups"].initial = (
                self.instance.filter_working_groups.count() > 0
            )
            self.fields["filter_working_groups"].initial = [
                get_working_group_field_value(wg)
                for wg in self.instance.filter_working_groups.all()
            ]
            self.fields[
                "exclude_by_working_groups"
            ].initial = self.instance.exclude_working_groups.exists()
            self.fields["exclude_working_groups"].initial = [
                get_working_group_field_value(wg)
                for wg in self.instance.exclude_working_groups.all()
            ]

    def clean(self):
        super(ReportDesignerForm, self).clean()
        registry = self.cleaned_data.get("registry")
        remove_existing = self.cleaned_data.get(
            "remove_existing_custom_filters", False
        )

        if (
            self.has_existing_custom_filters
            and not remove_existing
            and self._stored_custom_filter_error
        ):
            self.add_error(
                None,
                _(
                    "The saved custom filter configuration is unavailable "
                    "or invalid: %(error)s. Remove it explicitly or restore "
                    "a compatible provider."
                )
                % {"error": self._stored_custom_filter_error},
            )
        elif (
            self.has_existing_custom_filters
            and not remove_existing
            and registry
            and registry.pk != self.instance.registry_id
        ):
            self.add_error(
                None,
                _(
                    "Remove the saved custom filters explicitly before "
                    "changing this report's registry."
                ),
            )

        selected_filters = {}
        if registry and not remove_existing:
            selected_registry_group = next(
                (
                    group
                    for group in self.custom_filter_groups
                    if group["registry"].code == registry.code
                ),
                None,
            )
            if selected_registry_group and selected_registry_group["error"]:
                self.add_error(None, selected_registry_group["error"])
            for (provider_registry_code, filter_key), (
                enabled_name,
                parameter_form,
                provider,
            ) in self._custom_filter_fields.items():
                if provider_registry_code != registry.code:
                    continue
                if not self.cleaned_data.get(enabled_name, False):
                    continue
                if not parameter_form.is_valid():
                    self.add_error(
                        None,
                        _(
                            "Invalid parameters for custom filter "
                            "'%(filter_key)s': %(errors)s"
                        )
                        % {
                            "filter_key": filter_key,
                            "errors": parameter_form.errors.as_text(),
                        },
                    )
                    continue
                try:
                    parameters = validate_report_filter_parameters(
                        provider, parameter_form.cleaned_data
                    )
                except ValidationError as error:
                    self.add_error(None, error)
                    continue
                selected_filters[filter_key] = {
                    "version": provider.configuration_version,
                    "parameters": parameters,
                }

        self.cleaned_data["custom_filters"] = (
            {
                "schema_version": 1,
                "filters": selected_filters,
            }
            if selected_filters
            else {}
        )

        cleaned_title = self.cleaned_data.get("title", "")
        if registry and (
            not self.instance.id
            or self.instance.title != cleaned_title
            or self.instance.registry_id != registry.pk
        ):
            if ReportDesign.objects.filter(
                registry=registry, title=cleaned_title
            ).first():
                self.add_error(
                    "title",
                    _(
                        'A report in this registry with the title "%s" '
                        "already exists."
                    )
                    % cleaned_title,
                )
        return self.cleaned_data

    def clean_filter_working_groups(self):
        return self._clean_working_groups("filter_working_groups")

    def clean_exclude_working_groups(self):
        return self._clean_working_groups("exclude_working_groups")

    def _clean_working_groups(self, field_name):
        return [
            WorkingGroup.objects.get(id=json.loads(field)["wg"])
            for field in self.cleaned_data[field_name]
        ]

    def clean_filter_consents(self):
        def get_consent_from_field(field):
            field_dict = json.loads(field)
            return ConsentQuestion.objects.get(
                id=field_dict["consent_question"]
            )

        return [
            get_consent_from_field(field)
            for field in self.cleaned_data["filter_consents"]
        ]

    @transaction.atomic
    def save_to_model(self):
        clean_data = self.cleaned_data

        report_design, created = ReportDesign.objects.update_or_create(
            id=self.instance.id,
            defaults={
                "title": clean_data["title"],
                "description": clean_data["description"],
                "registry": clean_data["registry"],
                "cde_heading_format": clean_data["cde_heading_format"],
                "cde_include_form_timestamp": clean_data[
                    "cde_include_form_timestamp"
                ],
                "custom_filters": clean_data["custom_filters"],
            },
        )

        report_design.access_groups.set(clean_data["access_groups"])

        if clean_data["exclude_by_working_groups"]:
            report_design.exclude_working_groups.set(
                clean_data["exclude_working_groups"]
            )
        else:
            report_design.exclude_working_groups.set([])

        if clean_data["filter_by_working_groups"]:
            report_design.filter_working_groups.set(
                clean_data["filter_working_groups"]
            )
        else:
            report_design.filter_working_groups.set([])

        if clean_data["filter_by_consents"]:
            report_design.filter_consents.set(clean_data["filter_consents"])
        else:
            report_design.filter_consents.set([])

        ReportDemographicField.objects.filter(
            report_design=report_design
        ).delete()
        for idx, field in enumerate(clean_data["demographic_fields"]):
            field_dict = json.loads(field)
            ReportDemographicField.objects.create(
                model=field_dict["model"],
                field=field_dict["field"],
                sort_order=idx,
                report_design=report_design,
            )

        ReportClinicalDataField.objects.filter(
            report_design=report_design
        ).delete()
        for field in clean_data["cde_fields"]:
            field_dict = json.loads(field)
            ReportClinicalDataField.objects.create(
                cde_key=field_dict["cde_key"],
                context_form_group=ContextFormGroup.objects.get(
                    id=field_dict["cfg"]
                ),
                report_design=report_design,
            )

        report_design.save()

        self.instance = report_design
