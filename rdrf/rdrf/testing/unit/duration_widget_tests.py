from rdrf.forms.widgets.widgets import DurationWidgetHelper


def test_duration_compatibile_formats():
    helper = DurationWidgetHelper({})
    assert helper.compatible_formats("P0Y0M0D", "P0Y")
    assert helper.compatible_formats("P0Y0M0D", "P0Y0D")
    assert helper.compatible_formats("P0Y0M0D", "P0M0D")
    assert helper.compatible_formats("P0Y0M0DT0H0M0S", "PT0S")
    assert helper.compatible_formats("P0M0D", "P0D")


def test_duration_incompatible_formats():
    helper = DurationWidgetHelper({})
    assert not helper.compatible_formats("P0Y0M0D", "P0Y0M0DT0H0M0S")
    assert not helper.compatible_formats("P0Y0M0D", "P0Y0M0DT0M")
    assert not helper.compatible_formats("P0Y0M0D", "PT0M0H0S")
    assert not helper.compatible_formats("P0Y0M0DT0H0M", "PT0S")
    assert not helper.compatible_formats("P0M0D", "P0Y0D")
    assert not helper.compatible_formats("P0M0D", "PXTR")
    assert not helper.compatible_formats("ABCD", "XYZ")


def test_current_default_format():
    helper = DurationWidgetHelper(
        {
            "years": True,
            "months": False,
            "days": True,
            "hours": False,
            "minutes": False,
            "seconds": False,
        }
    )
    assert helper.current_format_default() == "P0Y0D"

    helper = DurationWidgetHelper({"weeks_only": True})
    assert helper.current_format_default() == "P0W"

    helper = DurationWidgetHelper(
        {
            "years": False,
            "months": False,
            "days": True,
            "hours": True,
            "minutes": True,
            "seconds": False,
        }
    )
    assert helper.current_format_default() == "P0DT0H0M"


def test_duration_unit_values():
    helper = DurationWidgetHelper(
        {
            "years": True,
            "months": True,
            "days": True,
            "hours": True,
            "minutes": True,
            "seconds": True,
        }
    )
    assert helper.unit_values("P2Y3M4DT5H6M7S") == {
        "years": "2",
        "months": "3",
        "days": "4",
        "hours": "5",
        "minutes": "6",
        "seconds": "7",
    }

from rdrf.forms.widgets.widgets import DurationWidget

def test_week_only_duration_unit_value():
    helper = DurationWidgetHelper({"weeks_only": True})
    assert helper.unit_values("P9W") == {"weeks": "9"}


def test_duration_widget_renders_configured_unit_inputs():
    widget = DurationWidget(attrs={"years": True, "months": True, "days": False})
    rendered = widget.render("age", "P2Y3M", {"id": "id_age"})

    assert 'id="id_age_years"' in rendered
    assert 'id="id_age_months"' in rendered
    assert 'data-duration-label="Years"' in rendered
    assert 'name="age" value="P2Y3M"' in rendered
    assert 'timeDurationPicker' not in rendered
