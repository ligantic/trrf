from datetime import timedelta

from django import template
from django.conf import settings
from django.template.defaultfilters import timeuntil
from django.utils import timezone
from django.utils.translation import ngettext_lazy

register = template.Library()


# ERP-3331 Copied from `django.template.defaultfilters` as used by the timeuntil function
# Failure to include these time strings in our code base will result in them missing from django.po translations.
TIME_STRINGS = {
    "year": ngettext_lazy("%(num)d year", "%(num)d years", "num"),
    "month": ngettext_lazy("%(num)d month", "%(num)d months", "num"),
    "week": ngettext_lazy("%(num)d week", "%(num)d weeks", "num"),
    "day": ngettext_lazy("%(num)d day", "%(num)d days", "num"),
    "hour": ngettext_lazy("%(num)d hour", "%(num)d hours", "num"),
    "minute": ngettext_lazy("%(num)d minute", "%(num)d minutes", "num"),
}


@register.simple_tag
def timeuntil_expiry():
    now = timezone.now()
    expiry_timedelta = timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
    return timeuntil(now + expiry_timedelta, now, TIME_STRINGS)
