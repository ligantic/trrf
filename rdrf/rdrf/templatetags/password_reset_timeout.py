from datetime import timedelta

from django import template
from django.conf import settings
from django.template.defaultfilters import timeuntil
from django.utils import timezone

register = template.Library()


@register.simple_tag
def timeuntil_expiry():
    now = timezone.now()
    expiry_timedelta = timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
    return timeuntil(now + expiry_timedelta, now)
