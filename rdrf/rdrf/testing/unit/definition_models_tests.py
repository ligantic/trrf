import logging

from django.test import TestCase

from rdrf.models.definition.models import CommonDataElement

logger = logging.getLogger(__name__)


def get_cde_display_value(cde_dict):
    display_value = CommonDataElement.objects.create(
        code=cde_dict["code"],
        abbreviated_name=cde_dict["code"],
        name=cde_dict["code"],
        allow_multiple=cde_dict.get("allow_multiple", False),
        datatype=cde_dict["datatype"],
        widget_name=cde_dict.get("widget_name", ""),
    ).display_value(cde_dict["value"])
    return display_value


class CDETests(TestCase):
    def test_all_datatypes_display_value(self):
        cde_datatypes = [
            value
            for key, value in CommonDataElement.DATA_TYPE_CHOICES
            if not key.startswith("__")
        ]

        self.assertEqual(
            cde_datatypes,
            [
                "Boolean",
                "Calculated",
                "Date",
                "Duration",
                "Email",
                "File",
                "Float",
                "Integer",
                "Range",
                "String",
                "Lookup",
                "Time",
            ],
            "A new data type has been added to CommonDataElement that hasn't been accounted for. "
            "Add the new data type and its expected display_value to this assertion and in the tests for display_value "
            "below.",
        )

        # Test each data type
        cde_dict = [
            {
                "code": "CDE_boolean",
                "datatype": "boolean",
                "value": True,
                "display_value": True,
            },
            {
                "code": "CDE_calculated",
                "datatype": "calculated",
                "value": "17",
                "display_value": "17",
            },
            {
                "code": "CDE_date",
                "datatype": "date",
                "value": "2025-03-04",
                "display_value": "2025-03-04",
            },
            {
                "code": "CDE_duration",
                "datatype": "duration",
                "value": "P0Y0M0D",
                "display_value": "P0Y0M0D",
            },
            {
                "code": "CDE_email",
                "datatype": "email",
                "value": "x",
                "display_value": "x",
            },
            {
                "code": "CDE_file",
                "datatype": "file",
                "value": {"file_name": "myfile.txt", "django_file_id": 1},
                "display_value": "myfile.txt",
            },
            {
                "code": "CDE_float",
                "datatype": "float",
                "value": 140.0,
                "display_value": 140.0,
            },
            {
                "code": "CDE_integer",
                "datatype": "integer",
                "value": 25,
                "display_value": 25,
            },
            {
                "code": "CDE_range",
                "datatype": "range",
                "value": "2YesMost",
                "display_value": "2YesMost",
            },
            {
                "code": "CDE_string",
                "datatype": "string",
                "value": "This is my response.",
                "display_value": "This is my response.",
            },
            {
                "code": "CDE_lookup",
                "widget_name": "XnatWidget",
                "datatype": "lookup",
                "value": "1DEF;2ABC",
                "display_value": "project_id: 1DEF, subject_id: 2ABC",
            },
            {
                "code": "CDE_time",
                "datatype": "time",
                "value": "09:10",
                "display_value": "09:10",
            },
        ]

        for cde in cde_dict:
            # Check singular value
            display_value = get_cde_display_value(cde)
            self.assertEqual(display_value, cde["display_value"])

            # Allowable return types, as expected by graphql schema.
            # More info: https://docs.graphene-python.org/en/latest/types/scalars/
            # More info: https://graphql.org/learn/schema/#scalar-types
            self.assertIsInstance(
                display_value,
                (bool, str, int, float),
                "display_value is required to be a "
                "scalar type for compatibility with graphql",
            )

            # Check multi value
            self.assertEqual(
                get_cde_display_value(
                    {
                        **cde,
                        "code": f"{cde['code']}_multi",
                        "allow_multiple": True,
                    }
                ),
                [cde["display_value"]],
            )
