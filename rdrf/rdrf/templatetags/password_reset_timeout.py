from datetime import datetime, timedelta, timezone

from django import template
from django.conf import settings
from django.template.defaultfilters import timeuntil

register = template.Library()


@register.simple_tag
def password_reset_timeout_timedelta():
    return timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)


@register.simple_tag
def now():
    return datetime.now(timezone.utc)


@register.simple_tag
def timeuntil_expiry(from_datetime, expiry_timedelta):
    expiry_datetime = from_datetime + expiry_timedelta
    return timeuntil(expiry_datetime, from_datetime)
