import csv
import io
import json
from datetime import date
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.urls import reverse
from rdrf.models.definition.models import Registry
from rdrf.services.io.defs.exporter import Exporter
from rdrf.services.io.defs.importer import Importer
from registry.groups.models import CustomUser, WorkingGroup
from registry.patients.models import Patient

from report.clinical_data_csv_util import ClinicalDataCsvUtil
from report.forms import (
    ReportDesignerForm,
    get_demographic_field_value,
    get_working_group_field_value,
)
from report.models import ReportCdeHeadingFormat, ReportDesign
from report.report_builder import ReportBuilder


class WorkingGroupExclusionTests(TestCase):
    databases = ("default", "clinical")

    @classmethod
    def setUpTestData(cls):
        cls.registry = Registry.objects.create(code="exclude", name="Exclude")
        cls.default = WorkingGroup.objects.create(
            registry=cls.registry, name="Default"
        )
        cls.test = WorkingGroup.objects.create(
            registry=cls.registry, name="Test accounts"
        )
        cls.other = WorkingGroup.objects.create(
            registry=cls.registry, name="Other"
        )
        cls.design = ReportDesign.objects.create(
            registry=cls.registry,
            title="Exclude test accounts",
            cde_heading_format=ReportCdeHeadingFormat.CODE.value,
        )
        cls.design.reportdemographicfield_set.create(
            model="patient", field="id", sort_order=0
        )
        cls.admin = CustomUser.objects.create(
            username="exclude-admin", is_active=True, is_superuser=True
        )

    def setUp(self):
        self.request = RequestFactory().get("/")
        self.request.user = self.admin
        self.client.force_login(self.admin)

    def patient(self, *groups):
        patient = Patient.objects.create(
            consent=True, date_of_birth=date(2000, 1, 1)
        )
        patient.rdrf_registry.add(self.registry)
        patient.working_groups.set(groups)
        return patient

    def report_ids(self):
        report = ReportBuilder(self.design)
        _, rows = report.build_preview(self.request)
        preview_ids = [row[0] for row in rows]
        csv_export = "".join(
            chunk.decode("utf-8-sig") if isinstance(chunk, bytes) else chunk
            for chunk in report.export_to_csv(self.request)
        )
        csv_ids = [
            row[0] for row in list(csv.reader(io.StringIO(csv_export)))[1:]
        ]
        json_ids = [
            str(json.loads(row)["id"])
            for row in report.export_to_json(self.request)
        ]
        self.assertEqual(preview_ids, csv_ids)
        self.assertEqual(preview_ids, json_ids)
        return preview_ids

    def test_exclusion_wins_when_patient_is_in_both_groups(self):
        included = self.patient(self.default)
        self.patient(self.default, self.test)
        self.patient(self.test)
        self.patient(self.other)
        self.patient()
        self.design.filter_working_groups.add(self.default)
        self.design.exclude_working_groups.add(self.test)
        self.assertEqual(self.report_ids(), [str(included.pk)])

    def test_exclusion_alone_preserves_patients_with_no_working_groups(self):
        included = self.patient(self.default)
        unallocated = self.patient()
        self.patient(self.test)
        self.patient(self.default, self.test)
        self.design.exclude_working_groups.add(self.test)
        self.assertEqual(
            self.report_ids(), [str(included.pk), str(unallocated.pk)]
        )

    def test_any_excluded_group_wins_over_any_included_group(self):
        included = self.patient(self.default, self.other)
        self.patient(self.default, self.test)
        self.patient(self.other)
        self.design.filter_working_groups.add(self.default, self.other)
        self.design.exclude_working_groups.add(self.test, self.other)
        self.assertEqual(self.report_ids(), [])
        included.working_groups.remove(self.other)
        self.assertEqual(self.report_ids(), [str(included.pk)])

    def test_same_group_in_both_filters_excludes_every_member(self):
        self.patient(self.default)
        self.patient(self.default, self.test)
        self.design.filter_working_groups.add(self.default)
        self.design.exclude_working_groups.add(self.default)
        self.assertEqual(self.report_ids(), [])

    def test_no_exclusion_preserves_existing_inclusion_behaviour(self):
        included = self.patient(self.default)
        also_included = self.patient(self.default, self.test)
        self.patient(self.other)
        self.design.filter_working_groups.add(self.default)
        self.assertEqual(
            self.report_ids(), [str(included.pk), str(also_included.pk)]
        )

    def test_exclusions_are_applied_before_preview_pagination(self):
        for _ in range(101):
            self.patient(self.default, self.test)
        included = self.patient(self.default)
        self.design.filter_working_groups.add(self.default)
        self.design.exclude_working_groups.add(self.test)
        response = self.client.get(
            reverse("report:report_preview", args=[self.design.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["rows"], [[str(included.pk)]])

    def test_clinical_header_summary_only_receives_matching_patients(self):
        included = self.patient(self.default)
        self.patient(self.default, self.test)
        self.patient(self.other)
        self.design.filter_working_groups.add(self.default)
        self.design.exclude_working_groups.add(self.test)
        generator = ClinicalDataCsvUtil()
        with patch.object(
            generator,
            "_ClinicalDataCsvUtil__clinical_data_summary",
            return_value={},
        ) as summary:
            generator.csv_headers(self.admin, self.design)
        summary.assert_called_once_with([included.pk], [])

    def form_data(self):
        return {
            "registry": self.registry.code,
            "title": self.design.title,
            "cde_heading_format": ReportCdeHeadingFormat.CODE.value,
            "demographic_fields": [
                get_demographic_field_value("patient", "id")
            ],
            "filter_by_working_groups": True,
            "filter_working_groups": [
                get_working_group_field_value(self.default)
            ],
            "exclude_by_working_groups": True,
            "exclude_working_groups": [
                get_working_group_field_value(self.test)
            ],
        }

    def test_form_saves_restores_and_clears_exclusion(self):
        data = self.form_data()
        form = ReportDesignerForm(data=data, instance=self.design)
        self.assertTrue(form.is_valid(), form.errors)
        form.save_to_model()
        self.assertEqual(
            list(form.instance.exclude_working_groups.all()), [self.test]
        )
        self.assertEqual(
            list(form.instance.filter_working_groups.all()), [self.default]
        )
        restored = ReportDesignerForm(instance=form.instance)
        restored.setup_initials()
        self.assertTrue(restored["exclude_by_working_groups"].value())
        self.assertEqual(
            restored["exclude_working_groups"].value(),
            [get_working_group_field_value(self.test)],
        )
        data["exclude_by_working_groups"] = False
        disabled = ReportDesignerForm(data=data, instance=form.instance)
        self.assertTrue(disabled.is_valid(), disabled.errors)
        disabled.save_to_model()
        self.assertFalse(disabled.instance.exclude_working_groups.exists())
        self.assertTrue(disabled.instance.filter_working_groups.exists())

    def test_form_rejects_nonexistent_excluded_working_group(self):
        data = self.form_data()
        data["exclude_working_groups"] = [
            '{"registry": "exclude", "wg": 999999}'
        ]
        form = ReportDesignerForm(data=data, instance=self.design)
        self.assertFalse(form.is_valid())
        self.assertIn("exclude_working_groups", form.errors)

    def test_designer_places_exclusion_before_inclusion(self):
        response = self.client.get(
            reverse("report:report_designer", args=[self.design.pk])
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertLess(
            html.index('id="id_exclude_by_working_groups"'),
            html.index('id="id_filter_by_working_groups"'),
        )

    def test_registry_definition_round_trip_preserves_exclusion(self):
        self.design.filter_working_groups.add(self.default)
        self.design.exclude_working_groups.add(self.test)
        exported = Exporter(self.registry)._get_reports()
        self.assertEqual(
            exported[0]["exclude_working_groups"], [self.test.name]
        )
        self.design.exclude_working_groups.clear()
        Importer()._create_reports(exported)
        self.assertEqual(
            list(self.design.exclude_working_groups.all()), [self.test]
        )
        self.assertEqual(
            list(self.design.filter_working_groups.all()), [self.default]
        )

    def test_old_definitions_have_no_exclusions(self):
        self.design.exclude_working_groups.add(self.test)
        exported = Exporter(self.registry)._get_reports()
        del exported[0]["exclude_working_groups"]
        Importer()._create_reports(exported)
        self.assertFalse(self.design.exclude_working_groups.exists())

    def test_import_only_selects_excluded_groups_from_report_registry(self):
        other_registry = Registry.objects.create(code="another")
        WorkingGroup.objects.create(
            registry=other_registry, name=self.test.name
        )
        self.design.exclude_working_groups.add(self.test)
        exported = Exporter(self.registry)._get_reports()
        Importer()._create_reports(exported)
        self.assertEqual(
            list(self.design.exclude_working_groups.all()), [self.test]
        )
