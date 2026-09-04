from datetime import timedelta

from django.utils.translation import ngettext


STATUS_NOT_STARTED = "not-started"
STATUS_IN_PROGRESS = "in-progress"
STATUS_COMPLETE = "complete"
STATUS_DUE_SOON = "due-soon"
STATUS_DUE_NOW = "due-now"
STATUS_OVERDUE = "overdue"


def module_status(
    progress=None,
    last_completed=None,
    next_due=None,
    today=None,
    has_progress=False,
):
    """Return the RDRF badge variant for a dashboard module row."""
    if next_due and today:
        due_date = next_due.date() if hasattr(next_due, "date") else next_due
        if due_date < today:
            return STATUS_OVERDUE
        if due_date == today:
            return STATUS_DUE_NOW
        if due_date <= today + timedelta(days=14):
            return STATUS_DUE_SOON

    if progress is not None:
        if progress >= 100:
            return STATUS_COMPLETE
        if progress > 0:
            return STATUS_IN_PROGRESS

    if has_progress:
        return STATUS_IN_PROGRESS if last_completed else STATUS_NOT_STARTED
    return STATUS_COMPLETE if last_completed else STATUS_NOT_STARTED


def cadence_label(frequency):
    """Return a compact, display-ready cadence for a follow-up frequency."""
    if not frequency:
        return None

    days = frequency.days
    if days and days % 365 == 0:
        quantity, unit = days // 365, "year"
    elif days and days % 30 == 0:
        quantity, unit = days // 30, "month"
    elif days and days % 7 == 0:
        quantity, unit = days // 7, "week"
    else:
        quantity, unit = days, "day"

    messages = {
        "year": ("Every %(quantity)d year", "Every %(quantity)d years"),
        "month": ("Every %(quantity)d month", "Every %(quantity)d months"),
        "week": ("Every %(quantity)d week", "Every %(quantity)d weeks"),
        "day": ("Every %(quantity)d day", "Every %(quantity)d days"),
    }
    singular, plural = messages[unit]
    return ngettext(singular, plural, quantity) % {"quantity": quantity}