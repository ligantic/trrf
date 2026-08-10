from rdrf.forms.widgets.widgets import DurationWidget, DurationWidgetHelper, SliderWidget, TimeWidget


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


def test_time_widget_renders_24_hour_masked_input():
    widget = TimeWidget(attrs={"format": "24hour"})
    rendered = widget.render("bedtime", "21:30", {"id": "id_bedtime"})

    assert 'data-time-min="0" data-time-max="23"' in rendered
    assert 'id="id_bedtime_time"' in rendered
    assert 'maxlength="5" pattern="[0-9]{2}:[0-9]{2}" placeholder="HH:MM" value="21:30"' in rendered
    assert 'name="bedtime" class="time-widget" value="21:30"' in rendered
    assert "timepicki" not in rendered


def test_time_widget_renders_meridian_for_12_hour_format():
    widget = TimeWidget(attrs={"format": "12hour"})
    rendered = widget.render("bedtime", "21:30", {"id": "id_bedtime"})

    assert 'data-time-min="1" data-time-max="12"' in rendered
    assert 'data-time-unit="meridian"' in rendered
    assert 'value="PM" selected' in rendered
    assert 'name="bedtime" class="time-widget" value="09:30 PM"' in rendered


def test_slider_widget_renders_clinical_layout_hooks():
    widget = SliderWidget(attrs={"min": 1, "max": 10, "left_label": "Very Bad", "right_label": "Very Good"})
    rendered = widget.render("sleep_rating", "", {"id": "id_sleep_rating"})

    assert 'class="rdrf-cde-slider__label rdrf-cde-slider__label--start">Very Bad' in rendered
    assert 'class="rdrf-cde-slider__control"' in rendered
    assert 'class="rdrf-cde-slider__label rdrf-cde-slider__label--end">Very Good' in rendered
    assert 'id="id_sleep_rating" name="sleep_rating" value=""' in rendered
    assert "bootstrapSlider" in rendered
