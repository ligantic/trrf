from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from graphql import ExecutionResult, GraphQLError

from rdrf.helpers.registry_features import RegistryFeatures
from rdrf.models.definition.models import Registry
from rdrf.patients.patient_columns import ColumnFullName
from rdrf.patients.patient_list_configuration import PatientListConfiguration
from rdrf.patients.query_data import GraphQLResultError
from rdrf.testing.unit.tests import RDRFTestCase
from rdrf.views.patients_listing import PatientsListingView


class PatientListingQueryTests(SimpleTestCase):
    def _query(self):
        return PatientsListingView()._query_all_patients(
            SimpleNamespace(),
            SimpleNamespace(code="ang"),
            {"search": [{"text": "activ", "fields": ["givenNames", "familyName"]}]},
            ["id"],
            ["familyName", "givenNames"],
            {"offset": 0, "limit": 10},
        )

    @patch("rdrf.patients.query_data.create_dynamic_schema")
    def test_filtered_query_errors_are_not_consumed_as_patient_results(self, create_schema):
        create_schema.return_value.execute.side_effect = [
            ExecutionResult(data={"ang": {"allPatients": {"total": 61}}}),
            ExecutionResult(
                data={"ang": {"allPatients": {"patients": None, "total": None}}},
                errors=[GraphQLError("Search resolver failed")],
            ),
        ]

        with self.assertRaisesMessage(GraphQLResultError, "Search resolver failed"):
            self._query()

    @patch("rdrf.patients.query_data.create_dynamic_schema")
    def test_base_query_errors_stop_execution(self, create_schema):
        create_schema.return_value.execute.return_value = ExecutionResult(
            data=None, errors=[GraphQLError("Total resolver failed")]
        )

        with self.assertRaisesMessage(GraphQLResultError, "Total resolver failed"):
            self._query()

        self.assertEqual(create_schema.return_value.execute.call_count, 1)

    @patch("rdrf.patients.query_data.create_dynamic_schema")
    def test_empty_search_results_preserve_counts(self, create_schema):
        create_schema.return_value.execute.side_effect = [
            ExecutionResult(data={"ang": {"allPatients": {"total": 61}}}),
            ExecutionResult(data={"ang": {"allPatients": {"patients": [], "total": 0}}}),
        ]

        self.assertEqual(self._query(), (61, {"patients": [], "total": 0}))


class PatientListTests(RDRFTestCase):
    def setUp(self):
        self.registry = Registry.objects.get(code="reg1")

    def testDefaultConfigurationWhenNoCustomConfigurationIsDefined(self):
        config_columns = PatientListConfiguration(self.registry).config.get(
            "columns"
        )
        self.assertEqual(
            config_columns,
            [
                "full_name",
                "date_of_birth",
                "code",
                "working_groups",
                "diagnosis_progress",
                "diagnosis_currency",
                "stage",
                "modules",
                "actions",
            ],
        )

    def testCustomConfiguration(self):
        self.registry.metadata_json = '{"patient_list": {"columns": ["full_name", "stage", "date_of_birth"]}}'
        self.registry.save()
        config_columns = PatientListConfiguration(self.registry).config.get(
            "columns"
        )
        self.assertEqual(
            config_columns, ["full_name", "stage", "date_of_birth"]
        )

    def testPatientListColumns(self):
        self.registry.metadata_json = '{"patient_list": {"columns": [{"full_name": {"label": "Full name"}}, "stage", "date_of_birth"]}}'
        self.registry.save()
        columns = PatientListConfiguration(self.registry).get_columns()
        self.assertEqual(
            [
                (key, c.__class__.__name__, c.label, c.perm)
                for key, c in columns.items()
            ],
            [
                (
                    "full_name",
                    "ColumnFullName",
                    "Full name",
                    "patients.can_see_full_name",
                ),
                (
                    "date_of_birth",
                    "ColumnDateOfBirth",
                    "Date of Birth",
                    "patients.can_see_dob",
                ),
            ],
        )

        self.registry.add_feature(RegistryFeatures.STAGES)
        columns = PatientListConfiguration(self.registry).get_columns()
        self.assertEqual(
            [
                (key, c.__class__.__name__, c.label, c.perm)
                for key, c in columns.items()
            ],
            [
                (
                    "full_name",
                    "ColumnFullName",
                    "Full name",
                    "patients.can_see_full_name",
                ),
                (
                    "stage",
                    "ColumnPatientStage",
                    "Stage",
                    "patients.can_see_data_modules",
                ),
                (
                    "date_of_birth",
                    "ColumnDateOfBirth",
                    "Date of Birth",
                    "patients.can_see_dob",
                ),
            ],
        )

    def testGetFacetsWhenNoCustomFacetsDefined(self):
        registry_config = PatientListConfiguration(self.registry)
        self.assertEqual(registry_config.get_facets(), {})

    def testExtensibilityOfPatientListConfiguration(self):
        class ExtendPatientListConfiguration(PatientListConfiguration):
            def __init__(self, registry):
                super().__init__(registry)
                self.AVAILABLE_COLUMNS = {
                    **self.AVAILABLE_COLUMNS,
                    **{
                        "full_name_2": {
                            "label": "Full Name",
                            "permission": "patients.can_see_full_name",
                            "class": ColumnFullName,
                        }
                    },
                }

        self.registry.metadata_json = '{"patient_list": {"columns": [{"full_name": {"label": "Full name"}}, {"full_name_2": {"label": "Full name"}}]}}'
        self.registry.save()

        base_patient_list = PatientListConfiguration(self.registry)
        extended_patient_list = ExtendPatientListConfiguration(self.registry)

        self.assertEqual(len(base_patient_list.get_columns().keys()), 1)
        self.assertEqual(len(extended_patient_list.get_columns().keys()), 2)
