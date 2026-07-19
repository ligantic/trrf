from datetime import timedelta


STATUS_NOT_STARTED = "not-started"
STATUS_IN_PROGRESS = "in-progress"
STATUS_COMPLETE = "complete"
STATUS_DUE_SOON = "due-soon"
STATUS_DUE_NOW = "due-now"
STATUS_OVERDUE = "overdue"


def module_status(progress=None, last_completed=None, next_due=None, today=None):
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

    suffix = "" if quantity == 1 else "s"
    return f"Every {quantity} {unit}{suffix}"