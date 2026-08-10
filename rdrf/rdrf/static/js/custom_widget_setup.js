function setupTimeWidget(inputName, hasAMPM) {
  var timeInput = document.getElementById("id_" + inputName);
  var widget = $(timeInput).closest(".rdrf-time-widget");

  function applyMask(value) {
    var parts = value.split(":");
    if (parts.length > 1) {
      var hours = parts[0].replace(/\D/g, "").slice(0, 2);
      var minutes = parts[1].replace(/\D/g, "").slice(0, 2);
      if (hours.length === 1 && minutes) {
        hours = "0" + hours;
      }
      return hours + ":" + minutes;
    }

    var digits = value.replace(/\D/g, "").slice(0, 4);
    return digits.length > 2 ? digits.slice(0, 2) + ":" + digits.slice(2) : digits;
  }

  function updateTime() {
    var time = widget.find(".time-input[type='text']").val();
    var match = time.match(/^(\d{2}):(\d{2})$/);

    if (!match || Number(match[1]) > Number(widget.find(".time-input[type='text']").data("time-max")) || Number(match[2]) > 59) {
      $(timeInput).val("").trigger("change");
      return;
    }

    var value = time;
    if (hasAMPM) {
      value += " " + widget.find('[data-time-unit="meridian"]').val();
    }
    $(timeInput).val(value).trigger("change");
  }

  widget.find(".time-input[type='text']").on("input", function () {
    $(this).val(applyMask($(this).val()));
    updateTime();
  }).on("change blur", function () {
    updateTime();
  });

  widget.find('[data-time-unit="meridian"]').on("change", updateTime);
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
