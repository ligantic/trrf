import json
from abc import ABC, abstractmethod
from collections.abc import Mapping

from django import forms
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string


class ReportFilterProvider(ABC):
    configuration_version = None
    label = None
    parameter_form_class = None

    @abstractmethod
    def get_matching_patient_ids(self, registry, patient_ids, parameters):
        """Return the matching IDs from the supplied patient batch."""


def get_report_filter_providers(registry):
    providers_by_registry = getattr(
        settings, "REGISTRY_REPORT_FILTER_PROVIDERS", {}
    )
    if not isinstance(providers_by_registry, Mapping):
        raise ImproperlyConfigured(
            "REGISTRY_REPORT_FILTER_PROVIDERS must be a mapping."
        )

    registry_code = getattr(registry, "code", None)
    if not registry_code:
        raise ValueError("A registry with a code is required.")

    registry_providers = providers_by_registry.get(registry_code, {})
    if not isinstance(registry_providers, Mapping):
        raise ImproperlyConfigured(
            f"Report filter providers for registry '{registry_code}' "
            "must be a mapping."
        )

    providers = {}
    for filter_key, provider_path in registry_providers.items():
        if not isinstance(filter_key, str) or not filter_key:
            raise ImproperlyConfigured(
                "Report filter provider keys must be non-empty strings."
            )
        if not isinstance(provider_path, str) or not provider_path:
            raise ImproperlyConfigured(
                "Report filter provider paths must be non-empty strings."
            )

        provider_class = import_string(provider_path)
        if not isinstance(provider_class, type) or not issubclass(
            provider_class, ReportFilterProvider
        ):
            raise ImproperlyConfigured(
                f"Report filter provider '{filter_key}' must subclass "
                f"{ReportFilterProvider.__name__}."
            )

        try:
            provider = provider_class()
        except Exception as error:
            raise ImproperlyConfigured(
                f"Unable to initialize report filter provider '{filter_key}'."
            ) from error
        if (
            isinstance(provider.configuration_version, bool)
            or not isinstance(provider.configuration_version, int)
            or provider.configuration_version < 1
        ):
            raise ImproperlyConfigured(
                f"Report filter provider '{filter_key}' must define a "
                "positive configuration_version."
            )
        if not provider.label:
            raise ImproperlyConfigured(
                f"Report filter provider '{filter_key}' must define a "
                "display label."
            )
        if not isinstance(
            provider.parameter_form_class, type
        ) or not issubclass(provider.parameter_form_class, forms.Form):
            raise ImproperlyConfigured(
                f"Report filter provider '{filter_key}' must define a Django "
                "parameter_form_class."
            )

        providers[filter_key] = provider

    return providers


def validate_report_filter_parameters(provider, parameters):
    if not isinstance(parameters, Mapping):
        raise ValidationError("Filter parameters must be an object.")
    if any(not isinstance(key, str) for key in parameters):
        raise ValidationError("Filter parameter names must be strings.")

    form = provider.parameter_form_class(data=parameters)
    unexpected_parameters = set(parameters) - set(form.fields)
    if unexpected_parameters:
        raise ValidationError(
            "Unexpected filter parameter(s): "
            f"{', '.join(sorted(unexpected_parameters))}."
        )

    if not form.is_valid():
        raise ValidationError(form.errors)

    try:
        json.dumps(form.cleaned_data, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValidationError(
            "Filter parameters must be JSON serializable."
        ) from error

    return form.cleaned_data


def validate_custom_filter_configuration(registry, configuration):
    if configuration == {}:
        return {}
    if not isinstance(configuration, Mapping):
        raise ValidationError("Custom filter configuration must be an object.")
    if set(configuration) != {"schema_version", "filters"}:
        raise ValidationError(
            "Custom filter configuration must contain only "
            "'schema_version' and 'filters'."
        )

    schema_version = configuration["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != 1
    ):
        raise ValidationError(
            f"Unsupported custom filter configuration version: "
            f"{schema_version!r}."
        )
    selected_filters = configuration["filters"]
    if not isinstance(selected_filters, Mapping):
        raise ValidationError("Custom filters must be an object.")
    if not selected_filters:
        return {}

    providers = get_report_filter_providers(registry)
    validated_filters = {}
    for filter_key, filter_configuration in selected_filters.items():
        if not isinstance(filter_key, str) or filter_key not in providers:
            raise ValidationError(
                f"Custom filter '{filter_key}' is not registered for "
                f"registry '{registry.code}'. Remove it or register a "
                "compatible provider."
            )
        if not isinstance(filter_configuration, Mapping) or set(
            filter_configuration
        ) != {"version", "parameters"}:
            raise ValidationError(
                f"Configuration for custom filter '{filter_key}' must "
                "contain only 'version' and 'parameters'."
            )

        provider = providers[filter_key]
        version = filter_configuration["version"]
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version != provider.configuration_version
        ):
            raise ValidationError(
                f"Custom filter '{filter_key}' uses unsupported version "
                f"{version!r}; the registered version is "
                f"{provider.configuration_version}. Remove or update this "
                "filter configuration."
            )
        validated_filters[filter_key] = {
            "version": version,
            "parameters": validate_report_filter_parameters(
                provider, filter_configuration["parameters"]
            ),
        }

    return {
        "schema_version": 1,
        "filters": validated_filters,
    }
