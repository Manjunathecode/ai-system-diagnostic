from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.bootstrap import ApplicationContext
from config.settings import AppSettings
from core.portable_health import PortableHealth
from decision_engine.issue_classifier import OfflineIssueClassifier
from decision_engine.offline_rules import OfflineDecisionEngine
from diagnostics.service_state import normalize_service_state
from diagnostics.windows_diagnostics import WindowsDiagnosticEngine
from fixes.executor import AutonomousFixEngine
from fixes.registry import ApprovedFixRegistry
from fixes.verifiers import WindowsStateReader
from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity
from models.fix_result import AssessmentStatus, FixAssessment, FixExecutionResult, FixStatus
from models.problem import DetectedProblem
from models.session import TroubleshootingSession
from reports.report_service import ReportService
from services.conversation_service import ConversationService
from services.database import Database
from services.ui_facade import UIFacade


def finding(name: str, details: dict, status: DiagnosticStatus = DiagnosticStatus.WARNING, category: str = "Audit") -> DiagnosticResult:
    return DiagnosticResult("audit-scan", category, name, status, Severity.MEDIUM, "audit", datetime.now(timezone.utc), details)


def context(root: Path, results: list[DiagnosticResult] | None = None) -> ApplicationContext:
    settings = AppSettings(root, root / "data", root / "logs", root / "reports", root / "config", root / "knowledge", root / "data" / "audit.db")
    database = Database(settings.database_path)
    database.initialize()
    if results:
        database.save_diagnostic_results(results)
    return ApplicationContext(settings, database, False, (), PortableHealth(root, True, 1, False, "ready"))


class ServiceNormalizationTests(unittest.TestCase):
    def test_numeric_and_text_service_states_normalize(self):
        expected = {4: "running", 1: "stopped", 7: "paused", 2: "start_pending", 3: "stop_pending", "Running": "running", "STOPPED": "stopped"}
        for raw, canonical in expected.items():
            self.assertEqual(normalize_service_state(raw), canonical)
        self.assertEqual(normalize_service_state("corrupt"), "unknown")
        self.assertEqual(normalize_service_state(None), "not_run")

    def test_running_print_spooler_is_not_a_problem(self):
        engine = WindowsDiagnosticEngine()
        with patch("diagnostics.windows_diagnostics._powershell", side_effect=[[], [], {"Name": "Spooler", "Status": 4}]):
            result = engine.printer_diagnostics()[0]
        self.assertEqual(result.details["print_spooler"]["state"], "running")
        self.assertEqual(result.status, DiagnosticStatus.PASSED)
        self.assertEqual(OfflineDecisionEngine(ApprovedFixRegistry()).analyze([result]), [])

    def test_stopped_print_spooler_carries_canonical_target(self):
        engine = WindowsDiagnosticEngine()
        with patch("diagnostics.windows_diagnostics._powershell", side_effect=[[], [], {"Name": "Spooler", "Status": 1}]):
            result = engine.printer_diagnostics()[0]
        problems = OfflineDecisionEngine(ApprovedFixRegistry()).analyze([result])
        self.assertEqual(result.details["print_spooler"]["state"], "stopped")
        self.assertEqual(problems[0].parameters["service_name"], "Spooler")

    def test_running_stopped_unknown_and_missing_services(self):
        raw = [
            {"Name": "Spooler", "Status": 4, "StartType": 2},
            {"Name": "Dnscache", "Status": "Running", "StartType": "Automatic"},
            {"Name": "bits", "Status": 1, "StartType": 2},
            {"Name": "Netman", "Status": "malformed", "StartType": 3},
        ]
        with patch("diagnostics.windows_diagnostics._powershell", return_value=raw):
            result = WindowsDiagnosticEngine().windows_services()[0]
        states = {item["Name"]: item["state"] for item in result.details["services"]}
        self.assertEqual(states["Spooler"], "running")
        self.assertEqual(states["Dnscache"], "running")
        self.assertEqual(states["bits"], "stopped")
        self.assertEqual(states["Netman"], "unknown")
        self.assertEqual(states["NlaSvc"], "unavailable")
        self.assertEqual(states["wuauserv"], "unavailable")
        self.assertNotEqual(result.status, DiagnosticStatus.PASSED)

    def test_running_supported_service_is_not_detected(self):
        raw = [{"Name": name, "Status": 4, "StartType": 2}
               for name in ("Spooler", "wuauserv", "bits", "Dnscache", "NlaSvc", "Netman")]
        with patch("diagnostics.windows_diagnostics._powershell", return_value=raw):
            result = WindowsDiagnosticEngine().windows_services()[0]
        self.assertEqual(result.status, DiagnosticStatus.PASSED)
        self.assertEqual(OfflineDecisionEngine(ApprovedFixRegistry()).analyze([result]), [])

    def test_stopped_automatic_supported_service_is_detected(self):
        raw = [{"Name": name, "Status": 4, "StartType": 2}
               for name in ("Spooler", "wuauserv", "bits", "Dnscache", "NlaSvc", "Netman")]
        next(item for item in raw if item["Name"] == "bits")["Status"] = 1
        with patch("diagnostics.windows_diagnostics._powershell", return_value=raw):
            result = WindowsDiagnosticEngine().windows_services()[0]
        problem = OfflineDecisionEngine(ApprovedFixRegistry()).analyze([result])[0]
        self.assertEqual(problem.parameters["service_name"], "bits")
        self.assertEqual(problem.recommended_fix_workflow, "restart_supported_windows_service")

    def test_inaccessible_service_collector_is_not_run(self):
        with patch("diagnostics.windows_diagnostics._powershell", side_effect=PermissionError("access denied")):
            result = WindowsDiagnosticEngine().run_targeted("Windows Services")[0]
        self.assertEqual(result.status, DiagnosticStatus.PERMISSION_REQUIRED)
        self.assertIn("access denied", result.summary.lower())


class HealthAggregationTests(unittest.TestCase):
    def dashboard_for(self, statuses: list[DiagnosticStatus]) -> dict:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            results = [finding(f"check-{index}", {}, status) for index, status in enumerate(statuses)]
            facade = UIFacade(context(Path(folder), results))
            facade.results = results
            return facade.dashboard()

    def test_health_states_never_treat_incomplete_as_healthy(self):
        self.assertEqual(self.dashboard_for([DiagnosticStatus.WARNING])["health"], "Needs attention")
        self.assertEqual(self.dashboard_for([DiagnosticStatus.FAILED])["health"], "Needs attention")
        self.assertEqual(self.dashboard_for([DiagnosticStatus.NOT_RUN])["health"], "Incomplete")
        self.assertEqual(self.dashboard_for([DiagnosticStatus.PERMISSION_REQUIRED])["health"], "Incomplete")
        self.assertEqual(self.dashboard_for([DiagnosticStatus.PASSED, DiagnosticStatus.UNAVAILABLE])["health"], "Incomplete")

    def test_only_complete_required_scan_is_healthy(self):
        names = ("System overview", "CPU usage", "Memory usage", "Drive capacity", "Network connectivity", "Important service status", "Printer diagnostics", "Device status")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            results = [finding(name, {}, DiagnosticStatus.PASSED) for name in names]
            facade = UIFacade(context(Path(folder), results)); facade.results = results
            self.assertEqual(facade.dashboard()["health"], "Healthy")

    def test_issue_and_warning_are_never_healthy(self):
        self.assertEqual(self.dashboard_for([DiagnosticStatus.FAILED])["health"], "Needs attention")
        self.assertEqual(self.dashboard_for([DiagnosticStatus.WARNING])["health"], "Needs attention")

    def test_demo_state_is_removed_before_real_scan(self):
        names = ("System overview", "CPU usage", "Memory usage", "Drive capacity", "Network connectivity",
                 "Important service status", "Printer diagnostics", "Device status")
        healthy = [finding(name, {}, DiagnosticStatus.PASSED) for name in names]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            facade = UIFacade(context(Path(folder)))
            facade.run_demo("DNS resolution failure")
            self.assertIsNotNone(facade.demo_outcome)
            with patch("services.ui_facade.WindowsDiagnosticEngine.run_full_scan", return_value=healthy):
                facade.full_scan()
            self.assertIsNone(facade.demo_outcome)
            self.assertEqual(facade.dashboard()["health"], "Healthy")


class ConversationRegressionTests(unittest.TestCase):
    def test_disk_space_and_specific_symptom_routing(self):
        classifier = OfflineIssueClassifier()
        self.assertEqual(classifier.classify("The drive is full and storage is low").category, "Disk Space")
        self.assertEqual(classifier.classify("Wi-Fi is connected but websites are not opening").category, "DNS")
        self.assertEqual(classifier.classify("WiFi is missing").category, "Network Adapter")
        self.assertEqual(classifier.classify("My printer is not printing").category, "Printer")
        self.assertEqual(classifier.classify("USB is not detected").category, "Device Errors")
        self.assertEqual(classifier.classify("My computer is very slow").category, "System Performance")
        self.assertEqual(classifier.classify("There is no internet connection").category, "Network")
        self.assertEqual(classifier.classify("Something seems wrong").category, "Unknown")

    def test_multiple_symptoms_remain_ambiguous_with_candidates(self):
        result = OfflineIssueClassifier().classify("The computer is slow and the printer is not working")
        self.assertEqual(result.category, "Unknown")
        self.assertEqual(set(result.candidate_categories), {"System Performance", "Printer"})
        self.assertIn("primary", result.follow_up_questions[0].lower())

    def test_declining_health_scan_runs_no_diagnostic(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            database = Database(Path(folder) / "audit.db")
            database.initialize()
            service = ConversationService(database, ApprovedFixRegistry(), 10)
            session = service.start("Check my system health")
            with patch("services.conversation_service.WindowsDiagnosticEngine.run_targeted") as run:
                session = service.answer_and_diagnose(session, "no")
            run.assert_not_called()
            self.assertEqual(session.final_status, "cancelled")

    def test_targeted_diagnostics_and_evidence_are_persisted(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            database = Database(Path(folder) / "audit.db")
            database.initialize()
            service = ConversationService(database, ApprovedFixRegistry(), 10)
            session = service.start("Websites are not opening")
            result = finding("Network connectivity", {"internet_connectivity": True, "dns_resolution": False, "gateway_reachability": True, "adapters": []}, DiagnosticStatus.WARNING, "Network")
            with patch("services.conversation_service.WindowsDiagnosticEngine.run_targeted", return_value=[result]):
                session = service.answer_and_diagnose(session, "Other devices work")
            self.assertEqual(len(database.diagnostic_records(result.scan_id)), 1)
            stored = database.session_details(session.session_id)
            self.assertEqual(stored["diagnostic_runs"][0]["scan_id"], result.scan_id)
            self.assertEqual(stored["diagnostic_findings"][0]["name"], "Network connectivity")

    def test_new_session_clears_previous_current_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder)
            old = finding("Drive capacity", {"drives": [{"drive": "C:\\", "free_percent": 1}]}, DiagnosticStatus.WARNING, "Disk Health")
            facade = UIFacade(context(root, [old]))
            facade.results = [old]
            facade.problems = OfflineDecisionEngine(facade.registry).analyze([old])
            self.assertTrue(facade.problems)
            facade.start_troubleshooting("The internet is not working")
            self.assertEqual(facade.problems, [])
            self.assertEqual(facade.results, [])
            self.assertEqual(facade.dashboard()["health"], "Not checked")


class RegistryAndVerificationTests(unittest.TestCase):
    def problem(self, fix_id: str, category: str, parameters: dict | None = None, evidence: tuple[str, ...] = ()) -> DetectedProblem:
        workflow = ApprovedFixRegistry().get(fix_id)
        return DetectedProblem("problem", category, Severity.MEDIUM, .9, evidence, "audit", fix_id, workflow.requires_administrator, workflow.risk.value != "low", workflow.risk, parameters or {})

    def test_registry_has_implementation_and_verifier_for_every_executable_workflow(self):
        registry = ApprovedFixRegistry()
        self.assertEqual(registry.validate(AutonomousFixEngine.executable_workflow_ids(), WindowsStateReader.verifiable_workflow_ids()), [])

    def test_review_workflows_are_not_executable_or_repairable(self):
        for fix_id in ("performance_resource_review", "device_error_review"):
            workflow = ApprovedFixRegistry().get(fix_id)
            self.assertFalse(workflow.executable)
            problem = self.problem(fix_id, workflow.supported_problem_types[0])
            self.assertFalse(UIFacade.problem_view(problem)["repairAvailable"])

    def test_service_target_is_canonical_and_identical(self):
        problem = self.problem("restart_supported_windows_service", "Windows Services", {"service_name": "bits"})
        reader = WindowsStateReader()
        self.assertEqual(reader.target_resource("restart_supported_windows_service", problem), "bits")
        self.assertEqual(AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True).target_resource("restart_supported_windows_service", problem), "bits")

    def test_unrelated_adapter_or_ip_state_cannot_verify_success(self):
        reader = WindowsStateReader()
        adapter_before = {"adapter_name": "Wi-Fi", "adapter_state": "disabled", "connectivity": False}
        adapter_after = {"adapter_name": "Wi-Fi", "adapter_state": "disabled", "connectivity": True, "other_up_adapters": 3}
        self.assertFalse(reader.verify("network_restart_adapter", adapter_before, adapter_after)[0])
        ip_before = {"adapter_name": "Wi-Fi", "has_valid_ipv4": False, "has_gateway": False}
        ip_after = {"adapter_name": "Ethernet", "has_valid_ipv4": True, "has_gateway": True}
        self.assertFalse(reader.verify("network_renew_ip", ip_before, ip_after)[0])

    def test_worsening_state_is_failed_not_partial(self):
        engine = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True)
        assessment = engine._assessment(False, ("free space decreased",), {"free_bytes": 1000}, {"free_bytes": 900}, ("not improved",), improved=False)
        self.assertEqual(assessment.status, AssessmentStatus.FAILED)

    def test_each_verifier_requires_its_intended_postcondition(self):
        reader = WindowsStateReader()
        cases = {
            "network_flush_dns": ({"dns_resolves": False}, {"dns_resolves": True}),
            "network_renew_ip": ({"adapter_name": "Wi-Fi", "has_valid_ipv4": False, "has_gateway": False},
                                 {"adapter_name": "Wi-Fi", "has_valid_ipv4": True, "has_gateway": True, "gateway_reachable": True}),
            "network_restart_adapter": ({"adapter_name": "Wi-Fi", "adapter_state": "disabled", "connectivity": False},
                                        {"adapter_name": "Wi-Fi", "adapter_state": "up", "connectivity": True}),
            "restart_print_spooler": ({"service_name": "Spooler", "service_state": "stopped"},
                                      {"service_name": "Spooler", "service_state": "running"}),
            "restart_supported_windows_service": ({"service_name": "bits", "service_state": "stopped"},
                                                   {"service_name": "bits", "service_state": "running"}),
            "clear_stuck_print_jobs": ({"service_name": "Spooler", "service_state": "running", "pending_job_count": 2},
                                       {"service_name": "Spooler", "service_state": "running", "pending_job_count": 0}),
            "safe_disk_cleanup": ({"temp_directory": "C:\\Temp", "eligible_temp_files": 2, "eligible_temp_bytes": 1000, "free_bytes": 100},
                                  {"temp_directory": "C:\\Temp", "eligible_temp_files": 1, "eligible_temp_bytes": 400, "free_bytes": 110}),
        }
        for fix_id, (before, after) in cases.items():
            self.assertTrue(reader.verify(fix_id, before, after)[0], fix_id)
            self.assertFalse(reader.verify(fix_id, after, after)[0], fix_id)

    def test_missing_or_unsafe_targets_are_rejected_before_snapshot(self):
        class NoReader:
            def snapshot(self, *_args):
                raise AssertionError("snapshot must not run")
        engine = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=NoReader())
        required = (("network_renew_ip", "Network"), ("network_restart_adapter", "Network Adapter"),
                    ("restart_print_spooler", "Printer"), ("clear_stuck_print_jobs", "Printer"),
                    ("safe_disk_cleanup", "Disk Space"), ("restart_supported_windows_service", "Windows Services"))
        for fix_id, category in required:
            self.assertEqual(engine.run(self.problem(fix_id, category), True).status, FixStatus.ESCALATED)
        unsafe = self.problem("network_restart_adapter", "Network Adapter", {"adapter_name": "Wi-Fi; Remove-Item"})
        self.assertEqual(engine.run(unsafe, True).status, FixStatus.ESCALATED)

    def test_command_success_alone_cannot_resolve(self):
        class Reader:
            def snapshot(self, *_args):
                return {"dns_resolves": False}
            def verify(self, *_args):
                return False, ("DNS still fails",), ("DNS unresolved",)
            def improvement(self, *_args):
                return False
        engine = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=False, reader=Reader())
        with patch.object(engine, "_execute") as execute:
            result = engine.run(self.problem("network_flush_dns", "DNS"), True)
        execute.assert_called_once()
        self.assertTrue(result.execution_succeeded)
        self.assertEqual(result.status, FixStatus.FAILED)

    def test_waiting_for_fallback_confirmation_does_not_escalate(self):
        class Reader:
            def snapshot(self, fix_id, problem):
                return {"dns_resolves": False, "adapter_name": problem.parameters.get("adapter_name", "Wi-Fi"), "has_valid_ipv4": False, "has_gateway": False}
            def verify(self, fix_id, before, after):
                return False, ("not fixed",), ("remaining",)
            def improvement(self, fix_id, before, after):
                return False
        problem = self.problem("network_flush_dns", "DNS", {"adapter_name": "Wi-Fi"})
        attempts, escalation = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=Reader()).run_with_recovery(problem, False)
        self.assertEqual(attempts[-1].status, FixStatus.AWAITING_CONFIRMATION)
        self.assertIsNone(escalation)


class ReportIntegrityTests(unittest.TestCase):
    def test_unverified_resolved_session_is_not_reported_resolved(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder)
            database = Database(root / "audit.db")
            database.initialize()
            now = datetime.now(timezone.utc)
            session = TroubleshootingSession("session", now, now, "DNS issue", "DNS", .9)
            session.final_status = "resolved"
            database.save_session(session)
            report = ReportService(database.database_path, root / "reports").build_session_report(session.session_id)
            self.assertNotEqual(report["final_status"], "resolved")
            self.assertEqual(report["repair_outcome"]["verification_succeeded"], False)

    def test_verified_attempt_drives_report_outcome_and_evidence(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder)
            database = Database(root / "audit.db")
            database.initialize()
            now = datetime.now(timezone.utc)
            assessment = FixAssessment(AssessmentStatus.SUCCESS, ("DNS changed from false to true",), {"before": {"dns": False}, "after": {"dns": True}}, 1.0)
            attempt = FixExecutionResult("attempt", "problem", "network_flush_dns", FixStatus.RESOLVED, now, now, "verified", before_snapshot={"dns": False}, after_snapshot={"dns": True}, assessment=assessment, execution_succeeded=True)
            database.save_fix_attempt(attempt)
            session = TroubleshootingSession("session", now, now, "DNS issue", "DNS", .9)
            session.fix_attempts = [{"attempt_id": attempt.attempt_id, "workflow": attempt.fix_id, "status": attempt.status.value}]
            session.final_status = "resolved"
            database.save_session(session)
            report = ReportService(database.database_path, root / "reports").build_session_report(session.session_id)
            self.assertEqual(report["final_status"], "resolved")
            self.assertTrue(report["repair_outcome"]["verification_succeeded"])
            self.assertEqual(report["fix_attempts"][0]["before"]["dns"], False)

    def test_service_target_persists_into_report(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            root = Path(folder)
            database = Database(root / "audit.db")
            database.initialize()
            now = datetime.now(timezone.utc)
            assessment = FixAssessment(AssessmentStatus.SUCCESS, ("bits transitioned to running",),
                                       {"before": {"service_name": "bits", "service_state": "stopped"},
                                        "after": {"service_name": "bits", "service_state": "running"}}, 1.0)
            attempt = FixExecutionResult("service-attempt", "service-problem", "restart_supported_windows_service",
                                         FixStatus.RESOLVED, now, now, "verified",
                                         before_snapshot=assessment.before_after_comparison["before"],
                                         after_snapshot=assessment.before_after_comparison["after"], assessment=assessment,
                                         parameters={"service_name": "bits"}, execution_succeeded=True)
            database.save_fix_attempt(attempt)
            session = TroubleshootingSession("service-session", now, now, "BITS is stopped", "Windows Services", .9)
            session.fix_attempts = [{"attempt_id": attempt.attempt_id}]
            session.final_status = "resolved"
            database.save_session(session)
            report = ReportService(database.database_path, root / "reports").build_session_report(session.session_id)
            self.assertEqual(report["fix_attempts"][0]["parameters"]["service_name"], "bits")
            self.assertEqual(report["final_status"], "resolved")


if __name__ == "__main__":
    unittest.main()
