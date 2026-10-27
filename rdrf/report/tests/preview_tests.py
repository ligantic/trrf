import csv
import io
from collections import OrderedDict
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse
from graphql import ExecutionResult, GraphQLError
from rdrf.models.definition.models import (
    ConsentQuestion,
    ConsentSection,
    Registry,
)
from rdrf.patients.query_data import GraphQLResultError
from registry.groups import GROUPS
from registry.groups.models import CustomUser, WorkingGroup
from registry.patients.models import ConsentValue, Patient

from report.models import ReportDesign
from report.report_builder import ReportBuilder


class ReportPreviewTests(TestCase):
    databases = ("default", "clinical")

    @classmethod
    def setUpTestData(cls):
        cls.registry = Registry.objects.create(code="preview", name="Preview")
        cls.design = ReportDesign.objects.create(
            registry=cls.registry, title="Participant report"
        )
        for index, field in enumerate(["id", "familyName", "dateOfBirth"]):
            cls.design.reportdemographicfield_set.create(
                model="patient", field=field, sort_order=index
            )
        cls.admin = CustomUser.objects.create(
            username="preview-admin", is_active=True, is_superuser=True
        )
        cls.group = Group.objects.create(name=GROUPS.WORKING_GROUP_CURATOR)
        cls.group.permissions.add(
            Permission.objects.get(
                content_type__app_label="report", codename="can_run_reports"
            )
        )
        cls.curator = CustomUser.objects.create(
            username="preview-curator", is_active=True
        )
        cls.curator.groups.add(cls.group)
        cls.curator.registry.add(cls.registry)
        cls.design.access_groups.add(cls.group)

    def setUp(self):
        self.request = RequestFactory().get("/")
        self.request.user = self.admin
        self.url = reverse("report:report_preview", args=[self.design.pk])
        self.client.force_login(self.admin)

    def create_patient(self, **kwargs):
        patient = Patient.objects.create(
            consent=True, date_of_birth=date(2000, 1, 2), **kwargs
        )
        patient.rdrf_registry.add(self.registry)
        return patient

    def test_preview_limits_query_to_100_and_matches_csv(self):
        patients = [
            self.create_patient(family_name=f"Participant {i}")
            for i in range(105)
        ]
        report = ReportBuilder(self.design)
        with patch.object(
            report, "_get_graphql_query", wraps=report._get_graphql_query
        ) as query:
            headers, rows = report.build_preview(self.request)
        query.assert_called_once_with(self.request, limit=100)
        self.assertEqual(len(rows), 100)
        self.assertEqual(
            [row[0] for row in rows], [str(p.pk) for p in patients[:100]]
        )
        export = "".join(
            chunk.decode("utf-8-sig") if isinstance(chunk, bytes) else chunk
            for chunk in report.export_to_csv(self.request)
        )
        csv_rows = list(csv.reader(io.StringIO(export)))
        self.assertEqual(headers, csv_rows[0])
        self.assertEqual(rows, csv_rows[1:101])
        self.assertEqual(len(csv_rows) - 1, 105)

    def test_preview_uses_csv_columns_and_preserves_blank_zero_false(self):
        report = ReportBuilder(self.design)
        headers = OrderedDict(
            [
                ("nested_value", "Nested heading"),
                ("missing", "Missing"),
                ("empty", "Empty"),
                ("zero", "Zero"),
                ("false", "False"),
                ("unused", "Unused"),
            ]
        )
        result = ExecutionResult(
            data={
                "preview": {
                    "allPatients": {
                        "patients": [
                            {
                                "nested": {
                                    "value": "<script>alert(1)</script>"
                                },
                                "empty": None,
                                "zero": 0,
                                "false": False,
                                "extra": "not selected",
                            }
                        ]
                    }
                }
            }
        )
        with (
            patch.object(report, "_get_csv_headers", return_value=headers),
            patch.object(report.schema, "execute", return_value=result),
        ):
            actual_headers, rows = report.build_preview(self.request)
        self.assertEqual(actual_headers, list(headers.values()))
        self.assertEqual(
            rows, [["<script>alert(1)</script>", "", "", "0", "False", ""]]
        )

    def test_preview_query_errors_are_not_presented_as_empty_results(self):
        report = ReportBuilder(self.design)
        with (
            patch.object(
                report.schema,
                "execute",
                return_value=ExecutionResult(
                    errors=[GraphQLError("Query failed")]
                ),
            ),
            self.assertRaisesMessage(GraphQLResultError, "Query failed"),
        ):
            report.build_preview(self.request)

    def test_preview_page_renders_safe_table_and_download_links(self):
        self.create_patient(family_name="<script>alert(1)</script>")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "report_preview.html")
        self.assertContains(response, 'id="report_preview_table"')
        self.assertContains(response, "&lt;SCRIPT&gt;ALERT(1)&lt;/SCRIPT&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(
            response,
            reverse("report:report_download", args=[self.design.pk, "csv"]),
        )
        self.assertContains(
            response,
            reverse("report:report_download", args=[self.design.pk, "json"]),
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_no_matching_records(self):
        response = self.client.get(self.url)
        self.assertContains(response, "No records match this report.")
        self.assertEqual(response.context["rows"], [])

    def test_reports_list_includes_preview_link_for_curator(self):
        self.client.force_login(self.curator)
        response = self.client.get(reverse("report:reports_list"))
        self.assertContains(response, self.url)

    def test_curator_can_preview_accessible_report(self):
        self.client.force_login(self.curator)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "report_preview.html")

    def test_preview_denies_missing_report_group_registry_or_permission(self):
        for restriction in ["group", "registry", "permission"]:
            with self.subTest(restriction=restriction):
                user = CustomUser.objects.create(
                    username=f"no-{restriction}", is_active=True
                )
                if restriction != "registry":
                    user.registry.add(self.registry)
                if restriction == "group":
                    user.user_permissions.add(
                        Permission.objects.get(
                            content_type__app_label="report",
                            codename="can_run_reports",
                        )
                    )
                elif restriction == "registry":
                    user.groups.add(self.group)
                else:
                    group = Group.objects.create(name="No report permission")
                    user.groups.add(group)
                    self.design.access_groups.add(group)
                self.client.force_login(user)
                with patch("report.views.ReportBuilder") as builder:
                    response = self.client.get(self.url)
                self.assertEqual(response.status_code, 403)
                builder.assert_not_called()

    def test_anonymous_user_cannot_preview(self):
        self.client.logout()
        with patch("report.views.ReportBuilder") as builder:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        builder.assert_not_called()

    def test_curator_preview_respects_patient_working_group_access(self):
        group = WorkingGroup.objects.create(
            registry=self.registry, name="Curator patients"
        )
        self.curator.working_groups.add(group)
        included = self.create_patient(family_name="Included")
        included.working_groups.add(group)
        self.create_patient(family_name="Excluded")
        self.client.force_login(self.curator)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row[0] for row in response.context["rows"]], [str(included.pk)]
        )

    def test_preview_preserves_report_working_group_filter(self):
        included_group = WorkingGroup.objects.create(
            registry=self.registry, name="Included"
        )
        self.design.filter_working_groups.add(included_group)
        included = self.create_patient(family_name="Included")
        included.working_groups.add(included_group)
        self.create_patient(family_name="Excluded")
        report = ReportBuilder(self.design)
        _, rows = report.build_preview(self.request)
        self.assertEqual([row[0] for row in rows], [str(included.pk)])

    def test_preview_preserves_report_consent_filter(self):
        section = ConsentSection.objects.create(
            registry=self.registry,
            code="PreviewConsent",
            section_label="Preview consent",
        )
        question = ConsentQuestion.objects.create(
            section=section, code="reporting", position=1
        )
        self.design.filter_consents.add(question)
        included = self.create_patient(family_name="Included")
        excluded = self.create_patient(family_name="Excluded")
        self.create_patient(family_name="Not answered")
        ConsentValue.objects.create(
            patient=included, consent_question=question, answer=True
        )
        ConsentValue.objects.create(
            patient=excluded, consent_question=question, answer=False
        )
        report = ReportBuilder(self.design)
        _, rows = report.build_preview(self.request)
        self.assertEqual([row[0] for row in rows], [str(included.pk)])

    def test_invalid_query_or_duplicate_headers_show_report_errors(self):
        for method, errors in [
            ("validate_query", {"query_bad_key_error": "missing_field"}),
            ("validate_for_csv_export", {"duplicate_headers": {"Heading": []}}),
        ]:
            with self.subTest(method=method):
                with patch("report.views.ReportBuilder") as builder:
                    report = builder.return_value
                    report.validate_query.return_value = (True, None)
                    getattr(report, method).return_value = (False, errors)
                    response = self.client.get(self.url)
                self.assertTemplateUsed(response, "report_download_errors.html")
                self.assertEqual(response.context["errors"], errors)
                report.build_preview.assert_not_called()

    def test_execution_failure_displays_error_page(self):
        with patch("report.views.ReportBuilder") as builder:
            report = builder.return_value
            report.validate_query.return_value = (True, None)
            report.validate_for_csv_export.return_value = (True, {})
            report.build_preview.side_effect = GraphQLResultError(
                "Query failed"
            )
            response = self.client.get(self.url)
        self.assertTemplateUsed(response, "report_download_errors.html")
        self.assertContains(
            response, "An error occurred generating this report."
        )
