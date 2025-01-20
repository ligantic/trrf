from dateutil.relativedelta import relativedelta
from django import template
from django.conf import settings
from django.utils.translation import gettext as _

register = template.Library()


def _pluralize(count: int, singular: str, plural: str):
    return f"{count} {plural if count != 1 else singular}"


def _readable_timedelta(delta):
    parts = []

    if delta.years > 0:
        parts.append(_pluralize(delta.years, _("year"), _("years")))

    if delta.months > 0:
        parts.append(_pluralize(delta.months, _("month"), _("months")))

    if delta.days > 0:
        parts.append(_pluralize(delta.days, _("day"), _("days")))

    # Don't go too granular if we already have a value for a bigger unit of time
    if not parts:
        if delta.hours > 0:
            parts.append(_pluralize(delta.hours, _("hour"), _("hours")))

        if delta.minutes > 0:
            parts.append(_pluralize(delta.minutes, _("minute"), _("minutes")))

    return ", ".join(parts)


@register.simple_tag
def password_reset_timeout():
    timeout = settings.PASSWORD_RESET_TIMEOUT

    if timeout is None:
        return None

    relative_timeout = relativedelta(seconds=timeout)

    return _readable_timedelta(relative_timeout)
