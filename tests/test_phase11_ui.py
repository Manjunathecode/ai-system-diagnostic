from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from app.bootstrap import ApplicationContext
from config.branding import APP_ICON, APP_LOGO, APP_NAME, APP_SHORT_NAME, APP_TAGLINE, APP_VERSION, BRANDING
from config.settings import load_settings
from core.portable_health import validate_portable_environment
from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity
from models.fix_result import AssessmentStatus, FixAssessment, FixExecutionResult, FixStatus
from models.session import TroubleshootingSession
from services.ui_facade import UIFacade
from services.database import Database
from ui.qt_controller import BackgroundWorker


class Phase11UITests(unittest.TestCase):
    def context(self, root: Path):
        settings = load_settings(root)
        health = validate_portable_environment(root, (settings.data_directory, settings.logs_directory, settings.reports_directory, settings.config_directory))
        database = Database(settings.database_path); database.initialize()
        return ApplicationContext(settings, database, False, (), health)

    def test_branding_is_centralized_and_complete(self):
        self.assertEqual(BRANDING.app_name, APP_NAME)
        self.assertTrue(APP_SHORT_NAME)
        self.assertTrue(APP_TAGLINE)
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertEqual(APP_LOGO, "assets/app-icon.png")
        self.assertEqual(APP_ICON, "assets/app-icon.ico")

    def test_diagnostic_result_mapping_and_not_run(self):
        finding = DiagnosticResult("scan-ui", "Devices", "Device status", DiagnosticStatus.NOT_RUN, Severity.LOW,
                                   "Collector unavailable.", datetime.now(timezone.utc), {})
        mapped = UIFacade.diagnostic_view(finding)
        self.assertEqual(mapped["status"], "not_run")
        self.assertEqual(mapped["statusLabel"], "Not Run")
        self.assertEqual(mapped["summary"], "Collector unavailable.")

    def test_dashboard_does_not_invent_uncollected_values(self):
        with TemporaryDirectory() as folder:
            facade = UIFacade(self.context(Path(folder)))
            dashboard = facade.dashboard()
            self.assertEqual(dashboard["health"], "Not checked")
            self.assertEqual(dashboard["metrics"]["cpu"], "Awaiting scan")
            self.assertFalse(dashboard["hasScan"])

    def test_repair_state_mapping_uses_verification_evidence(self):
        now = datetime.now(timezone.utc)
        assessment = FixAssessment(AssessmentStatus.SUCCESS, ("DNS resolves: True",), {"before": {"dns": False}, "after": {"dns": True}}, 1.0)
        result = FixExecutionResult("attempt-ui", "problem-ui", "network_flush_dns", FixStatus.RESOLVED, now, now,
                                    "Verification confirmed resolution.", before_snapshot={"dns": False}, after_snapshot={"dns": True}, assessment=assessment)
        mapped = UIFacade.repair_view(result)
        self.assertEqual(mapped["status"], "resolved")
        self.assertEqual(mapped["confidence"], 100)
        self.assertIn("DNS resolves", mapped["verificationText"])

    def test_demo_mode_remains_isolated(self):
        with TemporaryDirectory() as folder:
            facade = UIFacade(self.context(Path(folder)))
            with patch("fixes.executor.AutonomousFixEngine._execute", side_effect=AssertionError("real execution must not run")):
                result = facade.run_demo("DNS resolution failure")
            self.assertTrue(result["simulation"])
            self.assertTrue(result["attempts"])

    def test_report_action_uses_persisted_session(self):
        with TemporaryDirectory() as folder:
            context = self.context(Path(folder)); now = datetime.now(timezone.utc)
            session = TroubleshootingSession("ui-report", now, now, "Websites do not open", "DNS", .9)
            session.final_status = "resolved"; context.database.save_session(session)
            facade = UIFacade(context)
            path = facade.export_report("session", "json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["session_id"], "ui-report")
            self.assertEqual(payload["executive_summary"]["final_status"], "not_verified")

    def test_privacy_mode_state_is_local_and_secret_free(self):
        with TemporaryDirectory() as folder:
            context = self.context(Path(folder)); facade = UIFacade(context)
            values = facade.update_preferences("ai_disabled", True, True)
            stored = (context.settings.config_directory / "portable_settings.json").read_text(encoding="utf-8")
            self.assertEqual(values["privacy_mode"], "ai_disabled")
            self.assertNotIn("api_key", stored.lower())
            self.assertNotIn("token", stored.lower())

    def test_background_worker_reports_result_without_touching_ui(self):
        worker = BackgroundWorker(lambda: {"done": True})
        values = []
        worker.signals.completed.connect(values.append)
        worker.run()
        self.assertEqual(values, [{"done": True}])


if __name__ == "__main__":
    unittest.main()
