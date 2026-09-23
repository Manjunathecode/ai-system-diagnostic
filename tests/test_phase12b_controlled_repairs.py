from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from pypdf import PdfReader

from app.bootstrap import ApplicationContext
from config.settings import AppSettings
from core.portable_health import PortableHealth
from fixes.executor import AutonomousFixEngine
from fixes.registry import ApprovedFixRegistry
from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity
from models.fix_result import AssessmentStatus, FixAssessment, FixExecutionResult, FixStatus
from models.problem import DetectedProblem
from models.session import TroubleshootingSession
from reports.report_service import ReportService
from services.database import Database
from services.demo_service import DemoService
from services.ui_facade import UIFacade
from ui.qt_controller import AppController


def app_context(root: Path) -> ApplicationContext:
    settings = AppSettings(root, root / "data", root / "logs", root / "reports", root / "config",
                           root / "knowledge", root / "data" / "phase12b.db")
    database = Database(settings.database_path)
    database.initialize()
    return ApplicationContext(settings, database, False, (), PortableHealth(root, True, 1, False, "ready"))


def repair_problem(fix_id: str, category: str, parameters: dict | None = None,
                   confirmation: bool | None = None) -> DetectedProblem:
    workflow = ApprovedFixRegistry().get(fix_id)
    return DetectedProblem(
        f"problem-{fix_id}", category, Severity.MEDIUM, .95, ("controlled test evidence",),
        "controlled test condition", fix_id, workflow.requires_administrator,
        workflow.risk.value != "low" if confirmation is None else confirmation,
        workflow.risk, parameters or {},
    )


class SequenceReader:
    def __init__(self, snapshots: dict[str, list[dict]], verdicts: dict[str, bool | None]):
        self.snapshots = {key: list(value) for key, value in snapshots.items()}
        self.verdicts = verdicts
        self.calls = 0

    def snapshot(self, fix_id, _problem):
        self.calls += 1
        return self.snapshots[fix_id].pop(0)

    def verify(self, fix_id, before, after):
        verdict = self.verdicts[fix_id]
        return verdict, (f"{fix_id} exact verification: {verdict}",), () if verdict else ("condition remains",)

    def improvement(self, fix_id, before, after):
        return before != after and self.verdicts[fix_id] is not None


class RepairOutcomeTests(unittest.TestCase):
    def test_healthy_target_fails_precheck_and_executes_nothing(self):
        snapshots = {
            "network_flush_dns": [{"dns_resolves": True}],
            "network_renew_ip": [{"adapter_name": "Wi-Fi", "has_valid_ipv4": True, "has_gateway": True}],
            "network_restart_adapter": [{"adapter_name": "Wi-Fi", "adapter_state": "up"}],
            "restart_print_spooler": [{"service_name": "Spooler", "service_state": "running"}],
            "clear_stuck_print_jobs": [{"service_name": "Spooler", "pending_job_count": 0}],
            "restart_supported_windows_service": [{"service_name": "bits", "service_state": "running"}],
        }
        parameters = {
            "network_flush_dns": ("DNS", {}),
            "network_renew_ip": ("Network", {"adapter_name": "Wi-Fi"}),
            "network_restart_adapter": ("Network Adapter", {"adapter_name": "Wi-Fi"}),
            "restart_print_spooler": ("Printer", {"service_name": "Spooler"}),
            "clear_stuck_print_jobs": ("Printer", {"service_name": "Spooler"}),
            "restart_supported_windows_service": ("Windows Services", {"service_name": "bits"}),
        }
        for fix_id, (category, target) in parameters.items():
            reader = SequenceReader({fix_id: snapshots[fix_id]}, {fix_id: False})
            engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=reader)
            with patch("fixes.executor.is_administrator", return_value=True), patch.object(engine, "_execute") as execute:
                result = engine.run(repair_problem(fix_id, category, target), True)
            self.assertEqual(result.status, FixStatus.PRE_CHECK_FAILED, fix_id)
            execute.assert_not_called()

    def test_execution_success_verification_failure_and_unavailable(self):
        for verdict, assessment_status in ((False, AssessmentStatus.FAILED), (None, AssessmentStatus.VERIFICATION_UNAVAILABLE)):
            reader = SequenceReader({"network_flush_dns": [{"dns_resolves": False}, {"dns_resolves": False}]},
                                    {"network_flush_dns": verdict})
            engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=reader)
            with patch.object(engine, "_execute", return_value={"exit_code": 0}):
                result = engine.run(repair_problem("network_flush_dns", "DNS"), True)
            self.assertTrue(result.execution_succeeded)
            self.assertEqual(result.status, FixStatus.FAILED)
            self.assertEqual(result.assessment.status, assessment_status)

    def test_execution_failure_is_failed(self):
        reader = SequenceReader({"network_flush_dns": [{"dns_resolves": False}]}, {"network_flush_dns": False})
        engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=reader)
        with patch.object(engine, "_execute", side_effect=subprocess.CalledProcessError(1, "ipconfig")):
            result = engine.run(repair_problem("network_flush_dns", "DNS"), True)
        self.assertEqual(result.status, FixStatus.FAILED)
        self.assertFalse(result.execution_succeeded)

    def test_fallback_success_failure_retry_and_escalation(self):
        snapshots = {
            "network_flush_dns": [{"dns_resolves": False}, {"dns_resolves": False}],
            "network_renew_ip": [
                {"adapter_name": "Wi-Fi", "has_valid_ipv4": False, "has_gateway": False},
                {"adapter_name": "Wi-Fi", "has_valid_ipv4": True, "has_gateway": True},
            ],
        }
        problem = repair_problem("network_flush_dns", "DNS", {"adapter_name": "Wi-Fi"})
        success_reader = SequenceReader(snapshots, {"network_flush_dns": False, "network_renew_ip": True})
        success_engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=success_reader, max_attempts=2)
        with patch("fixes.executor.is_administrator", return_value=True), \
                patch.object(success_engine, "_execute", return_value={"exit_code": 0}):
            attempts, escalation = success_engine.run_with_recovery(problem, True)
        self.assertEqual([item.fix_id for item in attempts], ["network_flush_dns", "network_renew_ip"])
        self.assertEqual(attempts[-1].status, FixStatus.RESOLVED)
        self.assertIsNone(escalation)

        failed_reader = SequenceReader({
            "network_flush_dns": [{"dns_resolves": False}, {"dns_resolves": False}],
            "network_renew_ip": [{"adapter_name": "Wi-Fi", "has_valid_ipv4": False, "has_gateway": False},
                                 {"adapter_name": "Wi-Fi", "has_valid_ipv4": False, "has_gateway": False}],
        }, {"network_flush_dns": False, "network_renew_ip": False})
        failed_engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=failed_reader, max_attempts=2)
        with patch("fixes.executor.is_administrator", return_value=True), \
                patch.object(failed_engine, "_execute", return_value={"exit_code": 0}):
            attempts, escalation = failed_engine.run_with_recovery(problem, True)
        self.assertEqual(len(attempts), 2)
        self.assertIsNotNone(escalation)


class ConfirmationAndConcurrencyTests(unittest.TestCase):
    def test_recovery_chain_requests_confirmation_before_higher_risk_fallback(self):
        problem = repair_problem("network_flush_dns", "DNS", {"adapter_name": "Wi-Fi"}, False)
        view = UIFacade.problem_view(problem)
        self.assertTrue(view["requiresConfirmation"])

    def test_decline_and_closed_confirmation_execute_nothing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder).resolve()
            reader = Mock()
            problem = repair_problem("safe_disk_cleanup", "Disk Space",
                                     {"temp_directory": str(root), "drive": root.anchor.rstrip("\\/")}, True)
            engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=reader,
                                         approved_cleanup_directories=(root,))
            with patch.object(engine, "_execute") as execute:
                result = engine.run(problem, False)
            self.assertEqual(result.status, FixStatus.AWAITING_CONFIRMATION)
            execute.assert_not_called()
            reader.snapshot.assert_not_called()

            facade = UIFacade(app_context(root))
            facade.problems = [problem]
            controller = AppController(facade)
            controller._problems = [facade.problem_view(problem)]
            with patch.object(controller, "_run_repair") as run:
                controller.requestRepair(0)
                controller.confirmPendingRepair(False)  # QML reject/close path
            run.assert_not_called()
            self.assertIn("cancelled", controller.statusMessage.lower())

    def test_duplicate_and_incompatible_repairs_are_blocked(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            facade = UIFacade(app_context(Path(folder)))
            first = repair_problem("network_flush_dns", "DNS")
            second = repair_problem("restart_print_spooler", "Printer", {"service_name": "Spooler"})
            facade.problems = [first, second]
            facade._repair_lock.acquire()
            try:
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    facade.execute_problem(1, True)
            finally:
                facade._repair_lock.release()
            facade._attempted_problem_ids.add(first.problem_id)
            with self.assertRaisesRegex(RuntimeError, "already has"):
                facade.execute_problem(0, True)


class PrivilegeAndTargetTests(unittest.TestCase):
    def test_executor_and_verifier_use_identical_canonical_targets(self):
        from fixes.verifiers import WindowsStateReader
        cases = (
            repair_problem("network_flush_dns", "DNS"),
            repair_problem("network_renew_ip", "Network", {"adapter_name": "Wi-Fi"}),
            repair_problem("network_restart_adapter", "Network Adapter", {"adapter_name": "Wi-Fi"}),
            repair_problem("restart_print_spooler", "Printer", {"service_name": "Spooler"}),
            repair_problem("clear_stuck_print_jobs", "Printer", {"service_name": "Spooler"}),
            repair_problem("restart_supported_windows_service", "Windows Services", {"service_name": "bits"}),
        )
        executor = AutonomousFixEngine(ApprovedFixRegistry())
        reader = WindowsStateReader()
        for problem in cases:
            self.assertEqual(executor.target_resource(problem.recommended_fix_workflow, problem),
                             reader.target_resource(problem.recommended_fix_workflow, problem))

    def test_stopped_manual_service_is_not_an_eligible_fault(self):
        engine = AutonomousFixEngine(ApprovedFixRegistry())
        problem = repair_problem("restart_supported_windows_service", "Windows Services", {"service_name": "bits"})
        self.assertFalse(engine._pre_check("restart_supported_windows_service", problem,
                                          {"service_name": "bits", "service_state": "stopped",
                                           "service_start_type": "manual"}))

    def test_standard_user_admin_workflow_does_not_partially_execute(self):
        reader = Mock()
        problem = repair_problem("restart_print_spooler", "Printer", {"service_name": "Spooler"})
        engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=reader)
        with patch("fixes.executor.is_administrator", return_value=False), patch.object(engine, "_execute") as execute:
            result = engine.run(problem, True)
        self.assertEqual(result.status, FixStatus.ESCALATED)
        self.assertIn("Administrator", result.message)
        execute.assert_not_called()
        reader.snapshot.assert_not_called()

    def test_mock_elevated_execution_verifies_and_persists(self):
        reader = SequenceReader({"restart_print_spooler": [
            {"service_name": "Spooler", "service_state": "stopped", "service_start_type": "automatic"},
            {"service_name": "Spooler", "service_state": "running", "service_start_type": "automatic"},
        ]}, {"restart_print_spooler": True})
        engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=reader)
        problem = repair_problem("restart_print_spooler", "Printer", {"service_name": "Spooler"})
        with patch("fixes.executor.is_administrator", return_value=True), patch.object(engine, "_execute", return_value={"service_name": "Spooler"}):
            result = engine.run(problem, True)
        self.assertEqual(result.status, FixStatus.RESOLVED)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            database = Database(Path(folder) / "audit.db"); database.initialize(); database.save_fix_attempt(result)
            stored = database.repair_attempts()[0]
        self.assertEqual(stored["parameters"]["service_name"], "Spooler")
        self.assertTrue(stored["execution_succeeded"])

    def test_service_allowlist_rejects_command_like_targets(self):
        invalid = ("UnknownSvc", "Spooler & whoami", "cmd /c stop Spooler", "Restart-Service Spooler", "$(Get-Service)")
        engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=Mock())
        for target in invalid:
            problem = repair_problem("restart_supported_windows_service", "Windows Services", {"service_name": target})
            with patch.object(engine, "_execute") as execute:
                result = engine.run(problem, True)
            self.assertEqual(result.status, FixStatus.ESCALATED, target)
            execute.assert_not_called()

    def test_network_adapter_operation_uses_only_exact_target(self):
        engine = AutonomousFixEngine(ApprovedFixRegistry())
        problem = repair_problem("network_restart_adapter", "Network Adapter", {"adapter_name": "Wi-Fi"})
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(engine, "_run", return_value=completed) as run:
            details = engine._execute("network_restart_adapter", problem)
        args, _timeout, env = run.call_args.args
        self.assertNotIn("Wi-Fi", " ".join(args))
        self.assertEqual(env["MANJUAI_APPROVED_TARGET"], "Wi-Fi")
        self.assertEqual(details["adapter_name"], "Wi-Fi")


class CleanupSafetyTests(unittest.TestCase):
    def test_documents_desktop_downloads_and_arbitrary_paths_are_rejected(self):
        engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=Mock())
        candidates = (Path.home() / "Documents", Path.home() / "Desktop", Path.home() / "Downloads")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as arbitrary:
            candidates += (Path(arbitrary),)
            for target in candidates:
                problem = repair_problem("safe_disk_cleanup", "Disk Space",
                                         {"temp_directory": str(target), "drive": target.anchor.rstrip("\\/")})
                with patch.object(engine, "_execute") as execute:
                    result = engine.run(problem, True)
                self.assertEqual(result.status, FixStatus.ESCALATED, str(target))
                execute.assert_not_called()

    def test_controlled_temp_cleanup_confirmation_scope_and_evidence(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder).resolve()
            old_file = root / "eligible.tmp"; old_file.write_bytes(b"x" * 4096)
            recent_file = root / "recent.tmp"; recent_file.write_bytes(b"keep")
            nested = root / "nested"; nested.mkdir(); nested_old = nested / "do-not-recurse.tmp"; nested_old.write_bytes(b"keep")
            old_time = datetime.now().timestamp() - 700000
            os.utime(old_file, (old_time, old_time)); os.utime(nested_old, (old_time, old_time))

            class CleanupReader:
                calls = 0
                def snapshot(self, _fix_id, _problem):
                    self.calls += 1
                    count = int(old_file.exists())
                    return {"temp_directory": str(root), "eligible_temp_files": count,
                            "eligible_temp_bytes": 4096 if count else 0,
                            "free_bytes": 100 if self.calls == 1 else 5000}
                def verify(self, fix_id, before, after):
                    from fixes.verifiers import WindowsStateReader
                    return WindowsStateReader().verify(fix_id, before, after)
                def improvement(self, fix_id, before, after):
                    from fixes.verifiers import WindowsStateReader
                    return WindowsStateReader().improvement(fix_id, before, after)

            problem = repair_problem("safe_disk_cleanup", "Disk Space",
                                     {"temp_directory": str(root), "drive": root.anchor.rstrip("\\/")}, True)
            engine = AutonomousFixEngine(ApprovedFixRegistry(), reader=CleanupReader(),
                                         approved_cleanup_directories=(root,))
            declined = engine.run(problem, False)
            self.assertEqual(declined.status, FixStatus.AWAITING_CONFIRMATION)
            self.assertTrue(old_file.exists())
            result = engine.run(problem, True)
            self.assertEqual(result.status, FixStatus.RESOLVED)
            self.assertFalse(old_file.exists())
            self.assertTrue(recent_file.exists())
            self.assertTrue(nested_old.exists())
            self.assertEqual(result.execution_details["files_removed"], 1)
            self.assertEqual(result.execution_details["bytes_removed"], 4096)

    def test_cleanup_permission_failure_is_recorded(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder).resolve(); target = root / "old.tmp"; target.write_text("x", encoding="utf-8")
            old_time = datetime.now().timestamp() - 700000; os.utime(target, (old_time, old_time))
            engine = AutonomousFixEngine(ApprovedFixRegistry(), approved_cleanup_directories=(root,))
            with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
                details = engine._clean_old_temp_files(root)
            self.assertEqual(details["failed_deletions"], 1)
            self.assertTrue(target.exists())

    def test_cleanup_skips_reparse_entries(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder).resolve(); target = root / "reparse-like.tmp"; target.write_text("keep", encoding="utf-8")
            old_time = datetime.now().timestamp() - 700000; os.utime(target, (old_time, old_time))
            engine = AutonomousFixEngine(ApprovedFixRegistry(), approved_cleanup_directories=(root,))
            with patch("fixes.executor.is_reparse_point", side_effect=lambda path: path.name == target.name):
                details = engine._clean_old_temp_files(root)
            self.assertEqual(details["reparse_points_skipped"], 1)
            self.assertTrue(target.exists())


class PersistenceRestartAndDemoTests(unittest.TestCase):
    def test_success_assessment_without_execution_is_not_reported_resolved(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder); context = app_context(root); now = datetime.now(timezone.utc)
            assessment = FixAssessment(AssessmentStatus.SUCCESS, ("simulated state changed",),
                                       {"before": {"dns_resolves": False}, "after": {"dns_resolves": True}}, 1.0)
            attempt = FixExecutionResult("dry-attempt", "dry-problem", "network_flush_dns", FixStatus.RESOLVED,
                                         now, now, "dry", assessment=assessment, execution_succeeded=False)
            context.database.save_fix_attempt(attempt)
            session = TroubleshootingSession("dry-session", now, now, "DNS", "DNS", .9)
            session.fix_attempts = [{"attempt_id": attempt.attempt_id}]; session.final_status = "resolved"
            context.database.save_session(session)
            report = ReportService(context.settings.database_path, context.settings.reports_directory).build_session_report(session.session_id)
            self.assertEqual(report["final_status"], "failed")
            self.assertFalse(report["repair_outcome"]["execution_succeeded"])
            self.assertTrue(report["repair_outcome"]["verification_succeeded"])

    def test_qml_close_path_maps_to_repair_cancellation(self):
        qml = (Path(__file__).resolve().parents[1] / "ui" / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("onRejected: controller.confirmPendingRepair(false)", qml)

    def test_persistence_reports_formats_and_restart_isolation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder); context = app_context(root); now = datetime.now(timezone.utc)
            assessment = FixAssessment(AssessmentStatus.SUCCESS, ("Spooler transitioned to running",),
                                       {"before": {"service_name": "Spooler", "service_state": "stopped"},
                                        "after": {"service_name": "Spooler", "service_state": "running"}}, 1.0)
            attempt = FixExecutionResult("attempt-12b", "problem-12b", "restart_print_spooler", FixStatus.RESOLVED,
                                         now, now, "verified", before_snapshot=assessment.before_after_comparison["before"],
                                         after_snapshot=assessment.before_after_comparison["after"], assessment=assessment,
                                         parameters={"service_name": "Spooler"}, execution_succeeded=True,
                                         execution_details={"operation": "restart_service", "service_name": "Spooler"})
            context.database.save_fix_attempt(attempt)
            session = TroubleshootingSession("session-12b", now, now, "Printer does not print", "Printer", .95)
            session.fix_attempts = [{"attempt_id": attempt.attempt_id}]; session.final_status = "resolved"
            context.database.save_session(session)
            reporter = ReportService(context.settings.database_path, context.settings.reports_directory)
            report = reporter.build_session_report(session.session_id)
            self.assertEqual(report["final_status"], "resolved")
            self.assertEqual(report["fix_attempts"][0]["parameters"]["service_name"], "Spooler")
            paths = {fmt: reporter.export(report, fmt) for fmt in ("json", "csv", "pdf")}
            self.assertEqual(json.loads(paths["json"].read_text(encoding="utf-8"))["final_status"], "resolved")
            self.assertIn("restart_print_spooler", paths["csv"].read_text(encoding="utf-8-sig"))
            pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(paths["pdf"]).pages)
            self.assertIn("Resolved", pdf_text)

            old = DiagnosticResult("old-scan", "Disk Health", "Drive capacity", DiagnosticStatus.WARNING,
                                   Severity.HIGH, "old warning", now, {"drives": []})
            context.database.save_diagnostic_results([old])
            restarted = UIFacade(app_context(root))
            self.assertEqual(restarted.results, [])
            self.assertEqual(restarted.problems, [])
            self.assertEqual(restarted.dashboard()["health"], "Not checked")
            self.assertGreaterEqual(len(restarted.report_history()), 3)

    def test_every_demo_is_isolated_and_simulated(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            context = app_context(Path(folder)); facade = UIFacade(context)
            before = context.database.dashboard_summary()["repairs"]
            with patch("fixes.executor.AutonomousFixEngine._execute", side_effect=AssertionError("demo called real operation")):
                outcomes = [facade.run_demo(name) for name in DemoService.SCENARIOS]
            self.assertTrue(all(item["simulation"] for item in outcomes))
            self.assertEqual(context.database.dashboard_summary()["repairs"], before)
            self.assertEqual(facade.results, [])
            self.assertEqual(facade.problems, [])
            report = facade.reporter.build_demo_report(facade.demo_outcome)
            self.assertTrue(report["simulation"])
            self.assertIn("SIMULATED", report["executive_summary"]["notice"])


if __name__ == "__main__":
    unittest.main()
