from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from django.template.loader import get_template
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

    def test_blank_progress_tracked_form_is_in_progress_after_save(self):
        last_saved = datetime(2026, 7, 1, tzinfo=timezone.utc)

        self.assertEqual(
            module_status(
                progress=0,
                last_completed=last_saved,
                has_progress=True,
            ),
            STATUS_IN_PROGRESS,
        )
        self.assertEqual(
            module_status(
                progress=45,
                last_completed=last_saved,
                has_progress=True,
            ),
            STATUS_IN_PROGRESS,
        )
        self.assertEqual(
            module_status(
                progress=100,
                last_completed=last_saved,
                has_progress=True,
            ),
            STATUS_COMPLETE,
        )

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

    def test_longitudinal_module_actions_follow_status(self):
        Form = namedtuple("Form", "nice_name")
        form_data = {
            Form("Overdue"): {
                "status": STATUS_OVERDUE,
                "link": "/start-overdue",
            },
            Form("Due soon"): {
                "status": STATUS_DUE_SOON,
                "link": "/start-due-soon",
            },
            Form("In progress"): {
                "status": STATUS_IN_PROGRESS,
                "link": "/continue",
            },
            Form("Complete"): {
                "status": STATUS_COMPLETE,
                "link": "/completed",
            },
            Form("Complete scheduled"): {
                "status": STATUS_COMPLETE,
                "link": "/completed-scheduled",
                "next_due": date(2026, 12, 1),
            },
        }
        dashboard = SimpleNamespace(
            patient_status=SimpleNamespace(
                module_progress={"fixed": {}, "multi": {"cfg": form_data}}
            )
        )

        content = get_template("dashboard/widget/module_progress.html").render(
            {"dashboard": dashboard}
        )

        self.assertIn('href="/start-overdue"', content)
        self.assertIn('href="/start-due-soon"', content)
        self.assertIn('href="/continue"', content)
        self.assertIn("Start", content)
        self.assertIn("Continue", content)
        self.assertIn('href="/completed"', content)
        self.assertIn("Edit", content)
        self.assertNotIn('href="/completed-scheduled"', content)