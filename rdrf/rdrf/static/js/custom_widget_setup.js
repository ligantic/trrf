function setupTimepicker($target, hasAMPM, startTimeStr) {
    var params = {
        on_change: function() { $("#main-form").trigger('change'); },
        show_meridian: hasAMPM,
        min_hour_value: hasAMPM ? 1:0,
        max_hour_value: hasAMPM ? 12:23
    }
    if (startTimeStr != "") {
        params.start_time = startTimeStr.split(",").map(Number);
    }
    $target.timepicki(params);
    $target.addClass("form-control");
    $(".meridian .mer_tx input").css("padding","0px"); // fix padding for meridian display
}

function setupDurationWidget(inputName, attributesStr) {
    var initAttrs = attributesStr.split(",");
  var durationInput = $("#id_" + inputName + "_duration");
  var widget = durationInput.closest(".rdrf-duration-widget");
  var units = ["years", "months", "days", "hours", "minutes", "seconds"];
  var suffixes = {
    years: "Y",
    months: "M",
    days: "D",
    hours: "H",
    minutes: "M",
    seconds: "S"
  };

  function unitValue(unit) {
    var value = parseInt(widget.find('[data-duration-unit="' + unit + '"]').val(), 10);
    return isNaN(value) ? 0 : value;
  }

  function updateDuration() {
    if (initAttrs[6] == "true") {
      durationInput.val("P" + unitValue("weeks") + "W");
    } else {
      var date = "";
      var time = "";
      units.forEach(function(unit, index) {
        if (initAttrs[index] == "true") {
          var target = index < 3 ? "date" : "time";
          if (target == "date") {
            date += unitValue(unit) + suffixes[unit];
          } else {
            time += unitValue(unit) + suffixes[unit];
          }
        }
      });
      durationInput.val("P" + date + (time ? "T" + time : ""));
    }
    durationInput.trigger('change');
  }

  widget.find(".duration-input").on("input change", updateDuration);
}
