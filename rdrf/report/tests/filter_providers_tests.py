from unittest import TestCase

from django import forms
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import override_settings
from django.utils.translation import gettext_lazy as _

from report.filter_providers import (
    ReportFilterProvider,
    get_report_filter_providers,
    validate_report_filter_parameters,
)


class SyntheticFilterParametersForm(forms.Form):
    values = forms.MultipleChoiceField(
        choices=(("first", "First"), ("second", "Second")),
        required=False,
    )


class SyntheticFilterProvider(ReportFilterProvider):
    configuration_version = 1
    label = _("Synthetic filter")
    parameter_form_class = SyntheticFilterParametersForm

    def get_matching_patient_ids(self, registry, patient_ids, parameters):
        return set(patient_ids)


class ReportFilterProvidersTest(TestCase):
    @override_settings(REGISTRY_REPORT_FILTER_PROVIDERS={})
    def test_unconfigured_registry_has_no_providers(self):
        registry = type("Registry", (), {"code": "registry_a"})()

        self.assertEqual(get_report_filter_providers(registry), {})

    @override_settings(
        REGISTRY_REPORT_FILTER_PROVIDERS={
            "registry_a": {
                "wrapper.synthetic": (
                    "report.tests.filter_providers_tests."
                    "SyntheticFilterProvider"
                )
            },
            "registry_b": {},
        }
    )
    def test_registration_is_registry_scoped_and_resolves_provider(self):
        registry_a = type("Registry", (), {"code": "registry_a"})()
        registry_b = type("Registry", (), {"code": "registry_b"})()

        providers = get_report_filter_providers(registry_a)

        self.assertEqual(set(providers), {"wrapper.synthetic"})
        self.assertIsInstance(
            providers["wrapper.synthetic"], SyntheticFilterProvider
        )
        self.assertEqual(get_report_filter_providers(registry_b), {})

    @override_settings(
        REGISTRY_REPORT_FILTER_PROVIDERS={
            "registry_a": {"wrapper.invalid": "builtins.object"}
        }
    )
    def test_provider_must_implement_the_contract(self):
        registry = type("Registry", (), {"code": "registry_a"})()

        with self.assertRaises(ImproperlyConfigured):
            get_report_filter_providers(registry)

    def test_parameter_form_validates_choices_and_returns_canonical_values(
        self,
    ):
        provider = SyntheticFilterProvider()

        parameters = validate_report_filter_parameters(
            provider, {"values": ["second", "first"]}
        )

        self.assertEqual(parameters, {"values": ["second", "first"]})

    def test_parameter_form_rejects_unexpected_and_invalid_values(self):
        provider = SyntheticFilterProvider()

        with self.assertRaises(ValidationError):
            validate_report_filter_parameters(
                provider, {"values": ["first"], "unknown": "value"}
            )
        with self.assertRaises(ValidationError):
            validate_report_filter_parameters(provider, {"values": ["invalid"]})
