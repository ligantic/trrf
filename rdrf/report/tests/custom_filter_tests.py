import csv
import io
import json
from datetime import date
from typing import ClassVar

from django import forms
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from rdrf.models.definition.models import Registry
from rdrf.services.io.defs.exporter import Exporter
from rdrf.services.io.defs.importer import Importer
from registry.groups.models import CustomUser, WorkingGroup
from registry.patients.models import Patient

from report.filter_providers import (
    ReportFilterProvider,
    validate_custom_filter_configuration,
)
from report.forms import (
    ReportDesignerForm,
    get_demographic_field_value,
)
from report.models import ReportCdeHeadingFormat, ReportDesign
from report.report_builder import ReportBuilder


class PredicateParametersForm(forms.Form):
    mode = forms.ChoiceField(
        choices=(
            ("even", "Even IDs"),
            ("divisible_by_three", "IDs divisible by three"),
            ("none", "No patients"),
        ),
        required=False,
    )


class PredicateFilterProvider(ReportFilterProvider):
    configuration_version = 1
    label = "Synthetic patient ID filter"
    parameter_form_class = PredicateParametersForm
    calls: ClassVar[list[tuple[int, ...]]] = []

    def get_matching_patient_ids(self, registry, patient_ids, parameters):
        self.calls.append(tuple(patient_ids))
        mode = parameters["mode"]
        if mode == "none":
            return set()
        divisor = 2 if mode == "even" else 3
        return {
            patient_id
            for patient_id in patient_ids
            if patient_id % divisor == 0
        }


class TargetIdParametersForm(forms.Form):
    patient_id = forms.IntegerField()


class TargetIdFilterProvider(ReportFilterProvider):
    configuration_version = 1
    label = "Synthetic target patient"
    parameter_form_class = TargetIdParametersForm

    def get_matching_patient_ids(self, registry, patient_ids, parameters):
        return {
            patient_id
            for patient_id in patient_ids
            if patient_id == parameters["patient_id"]
        }


class OutOfBatchFilterProvider(ReportFilterProvider):
    configuration_version = 1
    label = "Invalid synthetic filter"
    parameter_form_class = TargetIdParametersForm
    returned_ids: ClassVar[set[int]] = set()

    def get_matching_patient_ids(self, registry, patient_ids, parameters):
        return self.returned_ids


PROVIDER_SETTINGS = {
    "filters": {
        "wrapper.even": (
            "report.tests.custom_filter_tests.PredicateFilterProvider"
        ),
        "wrapper.third": (
            "report.tests.custom_filter_tests.PredicateFilterProvider"
        ),
    }
}


class CustomReportFilterTests(TestCase):
    databases = ("default", "clinical")

    def setUp(self):
        PredicateFilterProvider.calls.clear()
        OutOfBatchFilterProvider.returned_ids.clear()
        self.registry = Registry.objects.create(
            code="filters", name="Custom filters"
        )
        self.admin = CustomUser.objects.create(
            username="custom-filter-admin",
            is_active=True,
            is_superuser=True,
        )
        self.request = RequestFactory().get("/")
        self.request.user = self.admin
        self.design = ReportDesign.objects.create(
            registry=self.registry,
            title="Custom filter report",
            cde_heading_format=ReportCdeHeadingFormat.CODE.value,
        )
        self.design.reportdemographicfield_set.create(
            model="patient", field="id", sort_order=0
        )

    def patient(self, *working_groups):
        patient = Patient.objects.create(
            consent=True, date_of_birth=date(2000, 1, 1)
        )
        patient.rdrf_registry.add(self.registry)
        patient.working_groups.set(working_groups)
        return patient

    @override_settings(REGISTRY_REPORT_FILTER_PROVIDERS=PROVIDER_SETTINGS)
    def test_multiple_filters_intersect_across_preview_csv_and_json_once(self):
        patients = [self.patient() for _ in range(24)]
        self.design.custom_filters = {
            "schema_version": 1,
            "filters": {
                "wrapper.even": {
                    "version": 1,
                    "parameters": {"mode": "even"},
                },
                "wrapper.third": {
                    "version": 1,
                    "parameters": {"mode": "divisible_by_three"},
                },
            },
        }
        self.design.save()
        report = ReportBuilder(self.design)

        valid, errors = report.validate_query(self.request)

        self.assertTrue(valid, errors)
        headers, preview_rows = report.build_preview(self.request)
        csv_export = "".join(
            chunk.decode("utf-8-sig") if isinstance(chunk, bytes) else chunk
            for chunk in report.export_to_csv(self.request)
        )
        csv_rows = list(csv.reader(io.StringIO(csv_export)))
        json_rows = [
            json.loads(row) for row in report.export_to_json(self.request)
        ]
        expected = [
            str(patient.pk) for patient in patients if patient.pk % 6 == 0
        ]

        self.assertEqual(
            preview_rows, [[patient_id] for patient_id in expected]
        )
        self.assertEqual(csv_rows[0], headers)
        self.assertEqual([row[0] for row in csv_rows[1:]], expected)
        self.assertEqual([str(row["id"]) for row in json_rows], expected)
        self.assertEqual(len(PredicateFilterProvider.calls), 2)
        self.assertEqual(
            [len(batch) for batch in PredicateFilterProvider.calls], [24, 24]
        )

    @override_settings(
        REGISTRY_REPORT_FILTER_PROVIDERS={
            "filters": {
                "wrapper.target": (
                    "report.tests.custom_filter_tests.TargetIdFilterProvider"
                )
            }
        }
    )
    def test_filters_run_before_preview_pagination(self):
        for _ in range(101):
            self.patient()
        matching = self.patient()
        self.design.custom_filters = {
            "schema_version": 1,
            "filters": {
                "wrapper.target": {
                    "version": 1,
                    "parameters": {"patient_id": matching.pk},
                }
            },
        }
        self.design.save()
        report = ReportBuilder(self.design)

        valid, errors = report.validate_query(self.request)

        self.assertTrue(valid, errors)
        _, rows = report.build_preview(self.request)
        self.assertEqual(rows, [[str(matching.pk)]])

    @override_settings(REGISTRY_REPORT_FILTER_PROVIDERS=PROVIDER_SETTINGS)
    def test_provider_evaluation_uses_bounded_patient_batches(self):
        for _ in range(205):
            self.patient()
        self.design.custom_filters = {
            "schema_version": 1,
            "filters": {
                "wrapper.even": {
                    "version": 1,
                    "parameters": {"mode": "even"},
                }
            },
        }
        self.design.save()
        report = ReportBuilder(self.design)

        valid, errors = report.validate_query(self.request)

        self.assertTrue(valid, errors)
        self.assertEqual(
            [len(batch) for batch in PredicateFilterProvider.calls], [200, 5]
        )

    @override_settings(
        REGISTRY_REPORT_FILTER_PROVIDERS={
            "filters": {
                "wrapper.none": (
                    "report.tests.custom_filter_tests.PredicateFilterProvider"
                )
            }
        }
    )
    def test_empty_matching_cohort_stays_empty_in_all_outputs(self):
        self.patient()
        self.design.custom_filters = {
            "schema_version": 1,
            "filters": {
                "wrapper.none": {
                    "version": 1,
                    "parameters": {"mode": "none"},
                }
            },
        }
        self.design.save()
        report = ReportBuilder(self.design)

        valid, errors = report.validate_query(self.request)

        self.assertTrue(valid, errors)
        _, preview_rows = report.build_preview(self.request)
        csv_export = "".join(
            chunk.decode("utf-8-sig") if isinstance(chunk, bytes) else chunk
            for chunk in report.export_to_csv(self.request)
        )
        json_rows = list(report.export_to_json(self.request))

        self.assertEqual(preview_rows, [])
        self.assertEqual(len(list(csv.reader(io.StringIO(csv_export)))), 1)
        self.assertEqual(json_rows, [])

    @override_settings(
        REGISTRY_REPORT_FILTER_PROVIDERS={
            "filters": {
                "wrapper.invalid": (
                    "report.tests.custom_filter_tests.OutOfBatchFilterProvider"
                )
            }
        }
    )
    def test_provider_cannot_include_ids_outside_eligible_batch(self):
        patient = self.patient()
        OutOfBatchFilterProvider.returned_ids = {patient.pk}
        excluded_group = WorkingGroup.objects.create(
            registry=self.registry, name="Excluded"
        )
        excluded_patient = self.patient(excluded_group)
        OutOfBatchFilterProvider.returned_ids.add(excluded_patient.pk)
        self.design.exclude_working_groups.add(excluded_group)
        self.design.custom_filters = {
            "schema_version": 1,
            "filters": {
                "wrapper.invalid": {
                    "version": 1,
                    "parameters": {"patient_id": patient.pk},
                }
            },
        }
        self.design.save()
        report = ReportBuilder(self.design)

        valid, errors = report.validate_query(self.request)

        self.assertFalse(valid)
        self.assertIn("outside its eligible input batch", str(errors))

    @override_settings(REGISTRY_REPORT_FILTER_PROVIDERS=PROVIDER_SETTINGS)
    def test_definition_round_trip_preserves_filters_and_old_definition_clears(
        self,
    ):
        self.design.custom_filters = {
            "schema_version": 1,
            "filters": {
                "wrapper.even": {
                    "version": 1,
                    "parameters": {"mode": "even"},
                }
            },
        }
        self.design.save()

        exported = Exporter(self.registry)._get_reports()
        self.assertEqual(
            exported[0]["custom_filters"], self.design.custom_filters
        )
        Importer()._create_reports(exported)
        self.design.refresh_from_db()
        self.assertEqual(
            self.design.custom_filters, exported[0]["custom_filters"]
        )

        del exported[0]["custom_filters"]
        Importer()._create_reports(exported)
        self.design.refresh_from_db()
        self.assertEqual(self.design.custom_filters, {})

    @override_settings(REGISTRY_REPORT_FILTER_PROVIDERS=PROVIDER_SETTINGS)
    def test_designer_saves_restores_enabled_empty_and_disabled_filters(self):
        base_data = {
            "title": self.design.title,
            "registry": self.registry.code,
            "cde_heading_format": ReportCdeHeadingFormat.CODE.value,
            "demographic_fields": [
                get_demographic_field_value("patient", "id")
            ],
        }
        data = {
            **base_data,
            "custom_filter_enabled_0": "on",
        }
        form = ReportDesignerForm(data=data, instance=self.design)
        self.assertTrue(form.is_valid(), form.errors)
        form.save_to_model()
        self.assertEqual(
            form.instance.custom_filters,
            {
                "schema_version": 1,
                "filters": {
                    "wrapper.even": {
                        "version": 1,
                        "parameters": {"mode": ""},
                    }
                },
            },
        )

        self.design.refresh_from_db()
        restored = ReportDesignerForm(instance=self.design)
        restored.setup_initials()
        self.assertTrue(restored["custom_filter_enabled_0"].value())
        self.assertEqual(
            restored.custom_filter_groups[0]["filters"][0]["parameter_form"][
                "mode"
            ].value(),
            "",
        )

        disabled = ReportDesignerForm(data=base_data, instance=self.design)
        self.assertTrue(disabled.is_valid(), disabled.errors)
        disabled.save_to_model()
        self.design.refresh_from_db()
        self.assertEqual(self.design.custom_filters, {})

    @override_settings(
        REGISTRY_REPORT_FILTER_PROVIDERS={
            "filters": {
                "wrapper.target": (
                    "report.tests.custom_filter_tests.TargetIdFilterProvider"
                )
            }
        }
    )
    def test_designer_parameter_validation_is_conditional_on_filter(self):
        data = {
            "title": self.design.title,
            "registry": self.registry.code,
            "cde_heading_format": ReportCdeHeadingFormat.CODE.value,
            "demographic_fields": [
                get_demographic_field_value("patient", "id")
            ],
        }
        form = ReportDesignerForm(data=data, instance=self.design)
        parameter_form = form.custom_filter_groups[0]["filters"][0][
            "parameter_form"
        ]
        self.assertTrue(parameter_form.fields["patient_id"].required)
        self.assertNotIn(" required", str(parameter_form["patient_id"]))
        self.assertTrue(form.is_valid(), form.errors)

        data["custom_filter_enabled_0"] = "on"
        enabled = ReportDesignerForm(data=data, instance=self.design)
        self.assertFalse(enabled.is_valid())
        self.assertIn("patient_id", str(enabled.non_field_errors()))

        data["custom_filter_0-patient_id"] = "123"
        valid = ReportDesignerForm(data=data, instance=self.design)
        self.assertTrue(valid.is_valid(), valid.errors)

    @override_settings(REGISTRY_REPORT_FILTER_PROVIDERS=PROVIDER_SETTINGS)
    def test_saved_unknown_filter_requires_explicit_removal(self):
        self.design.custom_filters = {
            "schema_version": 1,
            "filters": {
                "wrapper.removed": {
                    "version": 1,
                    "parameters": {},
                }
            },
        }
        self.design.save()
        data = {
            "title": self.design.title,
            "registry": self.registry.code,
            "cde_heading_format": ReportCdeHeadingFormat.CODE.value,
            "demographic_fields": [
                get_demographic_field_value("patient", "id")
            ],
        }

        blocked = ReportDesignerForm(data=data, instance=self.design)
        self.assertFalse(blocked.is_valid())
        self.assertIn("explicitly", str(blocked.non_field_errors()))

        data["remove_existing_custom_filters"] = "on"
        permitted = ReportDesignerForm(data=data, instance=self.design)
        self.assertTrue(permitted.is_valid(), permitted.errors)
        permitted.save_to_model()
        self.design.refresh_from_db()
        self.assertEqual(self.design.custom_filters, {})

    @override_settings(REGISTRY_REPORT_FILTER_PROVIDERS=PROVIDER_SETTINGS)
    def test_custom_filter_configuration_rejects_bad_schema_and_version(self):
        with self.assertRaises(ValidationError):
            validate_custom_filter_configuration(
                self.registry, {"schema_version": 2, "filters": {}}
            )
        with self.assertRaises(ValidationError):
            validate_custom_filter_configuration(
                self.registry,
                {
                    "schema_version": 1,
                    "filters": {
                        "wrapper.even": {
                            "version": 2,
                            "parameters": {"mode": "even"},
                        }
                    },
                },
            )
