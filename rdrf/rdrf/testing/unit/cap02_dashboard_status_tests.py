from datetime import date, datetime, timedelta, timezone

from django.test import SimpleTestCase

from rdrf.helpers.dashboard_status import (
    STATUS_COMPLETE,
    STATUS_DUE_NOW,
    STATUS_DUE_SOON,
    STATUS_IN_PROGRESS,
    STATUS_NOT_STARTED,
    STATUS_OVERDUE,
    cadence_label,
    module_status,
)


class DashboardModuleStatusTest(SimpleTestCase):
    today = date(2026, 7, 19)

    def test_progress_states(self):
        self.assertEqual(module_status(progress=0), STATUS_NOT_STARTED)
        self.assertEqual(module_status(progress=45), STATUS_IN_PROGRESS)
        self.assertEqual(module_status(progress=100), STATUS_COMPLETE)

    def test_pending_entry_due_states_take_priority(self):
        self.assertEqual(
            module_status(
                progress=100,
                next_due=datetime(2026, 7, 18, tzinfo=timezone.utc),
                today=self.today,
            ),
            STATUS_OVERDUE,
        )
        self.assertEqual(
            module_status(
                next_due=datetime(2026, 7, 19, tzinfo=timezone.utc),
                today=self.today,
            ),
            STATUS_DUE_NOW,
        )
        self.assertEqual(
            module_status(
                next_due=datetime(2026, 8, 2, tzinfo=timezone.utc),
                today=self.today,
            ),
            STATUS_DUE_SOON,
        )

    def test_completion_is_used_when_next_due_is_outside_reminder_window(self):
        self.assertEqual(
            module_status(
                last_completed=datetime(2026, 7, 1, tzinfo=timezone.utc),
                next_due=datetime(2026, 8, 19, tzinfo=timezone.utc),
                today=self.today,
            ),
            STATUS_COMPLETE,
        )

    def test_cadence_label(self):
        self.assertEqual(cadence_label(timedelta(days=730)), "Every 2 years")
        self.assertEqual(cadence_label(timedelta(days=14)), "Every 2 weeks")