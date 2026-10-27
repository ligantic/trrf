import json
import logging
import runpy
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psycopg2
from django.core.exceptions import ImproperlyConfigured
from django.core.handlers.exception import convert_exception_to_response
from django.db import InterfaceError, OperationalError, ProgrammingError
from django.http import HttpResponseRedirect
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import path, resolve

from rdrf.helpers.log import ReadinessEmailFilter
from rdrf.views.actions import ActionExecutorView
from rdrf.views.health_check import liveness_check, readiness_check

urlpatterns = [
    path("actions", ActionExecutorView.as_view(), name="action"),
    path("live", liveness_check, name="liveness_check"),
    path("ready", readiness_check, name="readiness_check"),
]


@override_settings(
    ROOT_URLCONF=__name__,
    DEBUG=False,
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "OPTIONS": {
                "loaders": [
                    (
                        "django.template.loaders.locmem.Loader",
                        {
                            "403.html": "Forbidden",
                            "404.html": "Not found",
                        },
                    ),
                ]
            },
        }
    ],
)
class ActionPermissionTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get(
            "/actions",
            {
                "action": "form",
                "registry": "test",
                "id": "1372",
                "form_type": "Consents",
            },
        )
        self.request.user = SimpleNamespace(id=1, in_registry=lambda _: True)
        self.patient = SimpleNamespace(id=1372, in_registry=lambda _: True)
        self.view = convert_exception_to_response(ActionExecutorView.as_view())

    @patch("rdrf.views.actions.is_authorised", return_value=False)
    @patch("rdrf.views.actions.get_object_or_404")
    @patch("registry.patients.models.Patient.objects.get")
    def test_denied_patient_returns_403_not_500(
        self, get, registry, authorised
    ):
        get.return_value = self.patient
        with self.assertLogs("rdrf.views.actions", level="WARNING"):
            response = self.view(self.request)
        self.assertEqual(response.status_code, 403)

    @patch("rdrf.views.actions.Action._redirect_consents_form")
    @patch("rdrf.views.actions.is_authorised", return_value=True)
    @patch("rdrf.views.actions.get_object_or_404")
    @patch("registry.patients.models.Patient.objects.get")
    def test_authorised_patient_still_redirects(
        self, get, registry, authorised, redirect
    ):
        get.return_value = self.patient
        redirect.return_value = HttpResponseRedirect("/consent")
        self.assertEqual(self.view(self.request).status_code, 302)

    @patch("rdrf.views.actions.get_object_or_404")
    @patch("registry.patients.models.Patient.objects.get")
    def test_missing_patient_still_returns_404(self, get, registry):
        from registry.patients.models import Patient

        get.side_effect = Patient.DoesNotExist
        self.assertEqual(self.view(self.request).status_code, 404)


class DatabaseConnectionSettingsTests(SimpleTestCase):
    def load_settings(self, **values):
        from ccg_django_utils.conf import EnvConfig

        from rdrf import settings

        original_get = EnvConfig.get

        def get(env, key, default=None):
            return values.get(key, original_get(env, key, default))

        with patch.object(EnvConfig, "get", get):
            return runpy.run_path(settings.__file__)["DATABASES"]

    def test_both_aliases_have_bounded_postgres_connections(self):
        databases = self.load_settings(
            dbtype="pgsql",
            clinical_dbtype="pgsql",
            db_connect_timeout=5,
            db_conn_max_age=0,
        )
        for alias in ("default", "clinical"):
            self.assertEqual(databases[alias]["OPTIONS"]["connect_timeout"], 5)
            self.assertEqual(databases[alias]["CONN_MAX_AGE"], 0)
            self.assertTrue(databases[alias]["CONN_HEALTH_CHECKS"])

    def test_connection_reuse_can_be_enabled_for_qa(self):
        databases = self.load_settings(db_conn_max_age=60)
        for alias in ("default", "clinical"):
            self.assertEqual(databases[alias]["CONN_MAX_AGE"], 60)

    def test_driver_timeout_bounds_a_stalled_connection(self):
        timeout = self.load_settings(db_connect_timeout=5)["default"][
            "OPTIONS"
        ]["connect_timeout"]
        release = threading.Event()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(10)

            def stall():
                connection, _ = listener.accept()
                with connection:
                    release.wait(10)

            thread = threading.Thread(target=stall, daemon=True)
            thread.start()
            started = time.monotonic()
            try:
                with self.assertRaises(psycopg2.OperationalError):
                    psycopg2.connect(
                        host="127.0.0.1",
                        port=listener.getsockname()[1],
                        dbname="timeout_test",
                        user="timeout_test",
                        connect_timeout=timeout,
                    )
                elapsed = time.monotonic() - started
                self.assertGreaterEqual(elapsed, 4)
                self.assertLess(elapsed, 7)
            finally:
                release.set()
                thread.join(timeout=10)

    def test_postgres_options_are_not_passed_to_sqlite(self):
        databases = self.load_settings(
            dbtype="sqlite3",
            clinical_dbtype="sqlite3",
        )
        for alias in ("default", "clinical"):
            self.assertNotIn(
                "connect_timeout", databases[alias].get("OPTIONS", {})
            )

    def test_unbounded_timeout_and_negative_reuse_are_rejected(self):
        for value in (0, -1):
            with self.subTest(timeout=value):
                with self.assertRaises(ImproperlyConfigured):
                    self.load_settings(db_connect_timeout=value)
        with self.assertRaises(ImproperlyConfigured):
            self.load_settings(db_conn_max_age=-1)


@override_settings(ROOT_URLCONF=__name__)
class HealthCheckTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/ready")
        self.connections = {"default": MagicMock(), "clinical": MagicMock()}
        patcher = patch("rdrf.views.health_check.connections", self.connections)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_liveness_is_public_and_does_not_access_databases(self):
        response = self.client.get("/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"success": True})

    def test_readiness_checks_both_databases(self):
        response = readiness_check(self.request)
        self.assertEqual(response.status_code, 200)
        for alias in ("default", "clinical"):
            cursor = self.connections[
                alias
            ].cursor.return_value.__enter__.return_value
            cursor.execute.assert_called_once_with("SELECT 1")
        self.assertEqual(json.loads(response.content), {"success": True})

    def test_readiness_returns_503_for_either_unavailable_database(self):
        for alias in ("default", "clinical"):
            for error in (OperationalError, InterfaceError):
                with self.subTest(alias=alias, error=error):
                    self.connections[alias].reset_mock()
                    self.connections[alias].cursor.side_effect = error(
                        "private details"
                    )
                    with self.assertLogs(
                        "rdrf.views.health_check", level="WARNING"
                    ):
                        response = readiness_check(self.request)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(
                        json.loads(response.content), {"success": False}
                    )
                    self.assertNotIn(b"private details", response.content)
                    self.connections[alias].close.assert_called_once()
                    self.connections[alias].cursor.side_effect = None

    def test_programming_errors_are_not_hidden(self):
        self.connections["default"].cursor.side_effect = ProgrammingError(
            "bad SQL"
        )
        with self.assertRaises(ProgrammingError):
            readiness_check(self.request)

    def test_readiness_is_public_and_uncached(self):
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])

    def test_health_endpoints_reject_post(self):
        for endpoint in ("/ready", "/live"):
            self.assertEqual(self.client.post(endpoint).status_code, 405)

    def test_existing_health_check_response_is_preserved(self):
        from rdrf.views.health_check import health_check

        with patch(
            "rdrf.views.health_check.Registry.objects.count", return_value=2
        ):
            response = health_check(self.request)
        self.assertEqual(
            json.loads(response.content),
            {"success": True, "hosted_registries_count": 2},
        )


class ReadinessEmailFilterTests(SimpleTestCase):
    def record(self, status=503, name="readiness_check"):
        record = logging.LogRecord(
            "django.request", logging.ERROR, "", 0, "", (), None
        )
        record.status_code = status
        record.request = SimpleNamespace(
            resolver_match=SimpleNamespace(url_name=name)
        )
        return record

    @override_settings(READINESS_AGGREGATED_ALERTS_ENABLED=False)
    def test_emails_remain_enabled_until_aggregation_is_configured(self):
        self.assertTrue(ReadinessEmailFilter().filter(self.record()))

    @override_settings(READINESS_AGGREGATED_ALERTS_ENABLED=True)
    def test_only_readiness_503_emails_are_suppressed(self):
        email_filter = ReadinessEmailFilter()
        self.assertFalse(email_filter.filter(self.record()))
        self.assertTrue(email_filter.filter(self.record(status=500)))
        self.assertTrue(email_filter.filter(self.record(name="landing")))
        self.assertTrue(email_filter.filter(logging.makeLogRecord({})))


class ApplicationHealthRoutesTests(SimpleTestCase):
    def test_real_application_routes_are_not_intercepted_by_registry_routes(self):
        self.assertIs(resolve("/live").func, liveness_check)
        self.assertIs(resolve("/ready").func, readiness_check)

    def test_real_application_liveness_is_public_without_database_queries(self):
        response = self.client.get("/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
