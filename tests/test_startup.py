from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import sys
import tempfile

from config.settings import load_settings
from decision_engine.offline_rules import OfflineDecisionEngine
from fixes.executor import AutonomousFixEngine
from fixes.registry import ApprovedFixRegistry
from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity
from models.problem import DetectedProblem
from services.database import Database
from decision_engine.hybrid_orchestrator import HybridDecisionOrchestrator
from app.bootstrap import bootstrap_application
from ui.desktop_app import DesktopApplication
from decision_engine.issue_classifier import OfflineIssueClassifier
from services.conversation_service import ConversationService
from models.session import TroubleshootingSession
from reports.report_service import ReportService
from reports.sanitization import sanitize
from services.demo_service import DemoService
from core.paths import application_root, runtime_directories
from core.portable_health import validate_portable_environment


class FakeReader:
    def __init__(self, verdicts=None, snapshots=None):
        self.verdicts = verdicts or {}
        self.snapshots = {key: list(value) for key, value in (snapshots or {}).items()}
    def snapshot(self, fix_id, _problem):
        defaults = {
            "network_flush_dns": [{"dns_resolves": False}, {"dns_resolves": True}],
            "network_renew_ip": [{"adapter_name": "Ethernet", "has_valid_ipv4": False, "has_gateway": False}, {"adapter_name": "Ethernet", "has_valid_ipv4": True, "has_gateway": True}],
            "network_restart_adapter": [{"adapter_name": "Ethernet", "adapter_state": "disabled", "connectivity": False}, {"adapter_name": "Ethernet", "adapter_state": "up", "connectivity": True}],
            "restart_print_spooler": [{"service_name": "Spooler", "service_state": "stopped", "service_start_type": "automatic"}, {"service_name": "Spooler", "service_state": "running", "service_start_type": "automatic"}],
            "clear_stuck_print_jobs": [{"service_name": "Spooler", "pending_job_count": 2}, {"service_name": "Spooler", "pending_job_count": 0, "service_state": "running"}],
            "restart_supported_windows_service": [{"service_name": "bits", "service_state": "stopped", "service_start_type": "automatic"}, {"service_name": "bits", "service_state": "running", "service_start_type": "automatic"}],
            "safe_disk_cleanup": [{"temp_directory": _problem.parameters.get("temp_directory"), "eligible_temp_files": 2}, {"temp_directory": _problem.parameters.get("temp_directory"), "eligible_temp_files": 1}],
        }
        values = self.snapshots.get(fix_id, defaults.get(fix_id, [{"state": "before"}, {"state": "after"}]))
        return values.pop(0) if values else {"state": "after"}
    def verify(self, fix_id, before, after):
        verdict = self.verdicts.get(fix_id, True)
        return verdict, (f"{fix_id} verification: {verdict}",), () if verdict else ("symptom remains",)
    def improvement(self, _fix_id, before, after):
        return before != after

class MockProvider:
    def __init__(self, response=None, error=None): self.response, self.error, self.calls = response, error, 0
    def analyze_issue(self, _context):
        self.calls += 1
        if self.error: raise self.error
        return self.response
    def recommend_workflow(self, context): return self.analyze_issue(context)
    def explain_reasoning(self, context): return self.analyze_issue(context)


def problem(fix_id="network_flush_dns", category="DNS"):
    workflow = ApprovedFixRegistry().get(fix_id)
    temp_root = Path(tempfile.gettempdir()).resolve()
    parameters = {
        "network_renew_ip": {"adapter_name": "Ethernet"},
        "network_restart_adapter": {"adapter_name": "Ethernet"},
        "restart_print_spooler": {"service_name": "Spooler"},
        "clear_stuck_print_jobs": {"service_name": "Spooler"},
        "safe_disk_cleanup": {"temp_directory": str(temp_root), "drive": temp_root.anchor.rstrip("\\/")},
        "restart_supported_windows_service": {"service_name": "bits"},
    }.get(fix_id, {})
    return DetectedProblem("problem-1", category, Severity.MEDIUM, 1.0, ("Disabled adapters: Ethernet", "Stopped services: bits"), "test", fix_id,
                           workflow.requires_administrator, False, workflow.risk, parameters)

def ai_response(workflow="network_renew_ip", reasoning="Evidence supports an approved network workflow."):
    return {"issue_summary": "Network issue", "likely_causes": ["configuration"], "diagnostic_reasoning": reasoning,
            "recommended_workflow_id": workflow, "confidence": 0.7, "requires_more_information": False,
            "follow_up_questions": ["Does this affect all applications?"], "escalation_recommendation": None}


class StartupTests(unittest.TestCase):
    def test_database_initializes(self):
        root = Path(__file__).resolve().parents[1]; settings = load_settings(root); database = Database(settings.database_path); database.initialize()
        self.assertTrue(settings.database_path.exists())

    def test_ui_starts_without_ai_api_key(self):
        context = bootstrap_application(Path(__file__).resolve().parents[1])
        self.assertIsNone(context.settings.ai_api_key)
        ui = DesktopApplication(context); ui.root.update_idletasks(); ui.root.destroy()

    def test_diagnostic_result_is_structured(self):
        result = DiagnosticResult("scan-1", "Network", "Connectivity", DiagnosticStatus.PASSED, Severity.INFO, "Reachable", datetime.now(timezone.utc), {"internet": True})
        self.assertEqual(result.details["internet"], True)

    def test_dns_rule_uses_approved_workflow(self):
        result = DiagnosticResult("scan-1", "Network", "Network connectivity", DiagnosticStatus.WARNING, Severity.MEDIUM, "DNS failed", datetime.now(timezone.utc), {"internet_connectivity": True, "dns_resolution": False})
        self.assertEqual(OfflineDecisionEngine(ApprovedFixRegistry()).analyze([result])[0].recommended_fix_workflow, "network_flush_dns")

    def test_successful_verification_captures_before_after(self):
        reader = FakeReader({"network_flush_dns": True}, {"network_flush_dns": [{"dns_resolves": False}, {"dns_resolves": True}]})
        result = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=reader).run(problem())
        self.assertEqual(result.status.value, "resolved"); self.assertEqual(result.assessment.confidence_score, 1.0)
        self.assertEqual(result.before_snapshot["dns_resolves"], False); self.assertEqual(result.after_snapshot["dns_resolves"], True)

    def test_failed_and_partial_verification(self):
        failed = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=FakeReader({"network_flush_dns": False}, {"network_flush_dns": [{"dns_resolves": False}, {"dns_resolves": False}]})).run(problem())
        partial = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=FakeReader({"network_flush_dns": False}, {"network_flush_dns": [{"dns_resolves": False}, {"dns_resolves": True}]})).run(problem())
        self.assertEqual(failed.status.value, "failed"); self.assertEqual(partial.status.value, "partially_resolved")

    def test_fallback_and_retry_limit_and_escalation(self):
        reader = FakeReader({"network_flush_dns": False, "network_renew_ip": False}, {"network_flush_dns": [{"a": 0}, {"a": 0}], "network_renew_ip": [{"b": 0}, {"b": 0}]})
        attempts, escalation = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=reader, max_attempts=2).run_with_recovery(problem(), True)
        self.assertEqual([item.fix_id for item in attempts], ["network_flush_dns", "network_renew_ip"]); self.assertIsNotNone(escalation)
        limited, limited_escalation = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=FakeReader({"network_flush_dns": False}), max_attempts=1).run_with_recovery(problem(), True)
        self.assertEqual(len(limited), 1); self.assertIsNotNone(limited_escalation)

    def test_before_after_persistence(self):
        root = Path(__file__).resolve().parents[1]; db = Database(root / "data" / "phase5_test.db"); db.initialize()
        result = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=FakeReader({"network_flush_dns": True}, {"network_flush_dns": [{"dns_resolves": False}, {"dns_resolves": True}]})).run(problem())
        db.save_fix_attempt(result)
        with sqlite3.connect(db.database_path) as connection:
            row = connection.execute("SELECT before_json, after_json, assessment_json FROM fix_attempts WHERE attempt_id=?", (result.attempt_id,)).fetchone()
        self.assertIn("dns_resolves", row[0]); self.assertIn("success", row[2])

    def test_requested_workflows_route_safely_in_dry_run(self):
        ids = ("network_flush_dns", "network_renew_ip", "network_restart_adapter", "restart_print_spooler", "clear_stuck_print_jobs", "safe_disk_cleanup", "restart_supported_windows_service")
        categories = ("DNS", "Network", "Network Adapter", "Printer", "Printer", "Disk Space", "Windows Services")
        engine = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=FakeReader())
        for fix_id, category in zip(ids, categories):
            self.assertEqual(engine.run(problem(fix_id, category), user_confirmed=True).status.value, "resolved", fix_id)

    def test_offline_classification_and_ambiguity(self):
        classifier = OfflineIssueClassifier()
        self.assertEqual(classifier.classify("My printer is not printing").category, "Printer")
        ambiguous = classifier.classify("Something is wrong")
        self.assertEqual(ambiguous.category, "Unknown"); self.assertTrue(ambiguous.follow_up_questions)
        self.assertEqual(classifier.classify("Check my system health for any issues").category, "System Health")

    def test_conversation_targeted_diagnostics_and_persistence(self):
        root = Path(__file__).resolve().parents[1]; db = Database(root / "data" / "phase7_test.db"); db.initialize()
        service = ConversationService(db, ApprovedFixRegistry(), 10)
        session = service.start("Wi-Fi is connected but websites are not opening")
        finding = DiagnosticResult("scan", "Network", "Network connectivity", DiagnosticStatus.WARNING, Severity.MEDIUM, "DNS issue", datetime.now(timezone.utc), {"internet_connectivity": True, "dns_resolution": False})
        with patch("services.conversation_service.WindowsDiagnosticEngine.run_targeted", return_value=[finding]) as routed:
            session = service.answer_and_diagnose(session, "Other devices work")
        self.assertEqual(session.detected_category, "DNS"); self.assertEqual(session.final_status, "repair_recommended")
        self.assertIn("network_flush_dns", session.recommended_workflows); routed.assert_called_once()
        self.assertTrue(any(item["session_id"] == session.session_id for item in db.recent_sessions()))

    def test_unknown_conversation_does_not_run_diagnostics(self):
        root = Path(__file__).resolve().parents[1]; db = Database(root / "data" / "phase7_unknown.db"); db.initialize()
        session = ConversationService(db, ApprovedFixRegistry(), 10).start("Something seems weird")
        session = ConversationService(db, ApprovedFixRegistry(), 10).answer_and_diagnose(session, "No other details")
        self.assertEqual(session.final_status, "needs_more_information")

    def test_risky_conversation_recommendation_requires_confirmation(self):
        base = problem("restart_print_spooler", "Printer")
        risky = DetectedProblem(base.problem_id, base.category, base.severity, base.confidence, base.evidence, base.likely_cause,
                                base.recommended_fix_workflow, base.requires_administrator, True, base.risk_level, base.parameters)
        result = AutonomousFixEngine(ApprovedFixRegistry(), dry_run=True, reader=FakeReader()).run(risky, user_confirmed=False)
        self.assertEqual(result.status.value, "awaiting_confirmation")

    def test_pdf_csv_json_reports_from_persisted_session(self):
        root = Path(__file__).resolve().parents[1]; db = Database(root / "data" / "phase8_test.db"); db.initialize()
        now = datetime.now(timezone.utc); session = TroubleshootingSession("session-report", now, now, "Internet is not working", "DNS", .9)
        session.user_answers = [{"question": "Other devices?", "answer": "Yes"}]; session.detected_problems = [{"cause": "DNS failure", "evidence": ["DNS false"]}]
        session.recommended_workflows = ["network_flush_dns"]; session.final_status = "resolved"; db.save_session(session)
        reports = root / "data" / "phase8_reports"; service = ReportService(db.database_path, reports, "offline_only")
        report = service.build_session_report(session.session_id)
        self.assertEqual(report["session_id"], session.session_id)
        for fmt in ("json", "csv", "pdf"):
            path = service.export(report, fmt); self.assertTrue(path.exists()); self.assertGreater(path.stat().st_size, 0)
        self.assertTrue(next(reports.glob("*.pdf")).read_bytes().startswith(b"%PDF"))

    def test_report_sanitization_and_partial_data(self):
        clean = sanitize({"api_key": "abc", "nested": {"password": "x", "ok": "value"}})
        self.assertEqual(clean["api_key"], "[REDACTED]"); self.assertEqual(clean["nested"]["password"], "[REDACTED]")
        root = Path(__file__).resolve().parents[1]; db = Database(root / "data" / "phase8_partial.db"); db.initialize()
        now = datetime.now(timezone.utc); session = TroubleshootingSession("session-partial", now, now, "Slow", "System Performance", .8); session.final_status = "partially_resolved"; db.save_session(session)
        report = ReportService(db.database_path, root / "data" / "phase8_reports", "offline_only").build_session_report(session.session_id)
        self.assertEqual(report["executive_summary"]["final_status"], "not_verified")

    def test_portable_path_resolution_and_first_run(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(application_root(), root)
        folders = runtime_directories(root); self.assertEqual(folders["data"], root / "data")
        health_root = root / "data" / "phase9_portable"
        health = validate_portable_environment(health_root, tuple(runtime_directories(health_root)[name] for name in ("data", "logs", "reports", "config")))
        self.assertTrue(health.writable); self.assertTrue((health_root / "reports").exists())

    def test_packaged_path_resolution(self):
        fake_executable = Path("C:/Portable/AI_System_Diagnostic/AI_System_Diagnostic.exe")
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(fake_executable)):
            self.assertEqual(application_root(), fake_executable.parent)

    def test_demo_mode_isolated_and_report_is_simulated(self):
        demo = DemoService(ApprovedFixRegistry())
        with patch("fixes.executor.AutonomousFixEngine._execute", side_effect=AssertionError("real execution is forbidden in demo")):
            outcomes = [demo.run(scenario) for scenario in DemoService.SCENARIOS]
        outcome = outcomes[0]
        self.assertEqual(len(outcomes), 5)
        self.assertTrue(outcome["simulation"]); self.assertTrue(outcome["attempts"])
        root = Path(__file__).resolve().parents[1]; db = Database(root / "data" / "phase10_demo.db"); db.initialize()
        report = ReportService(db.database_path, root / "data" / "phase10_reports", "offline_only").build_demo_report(outcome)
        self.assertTrue(report["simulation"]); self.assertIn("SIMULATED", report["executive_summary"]["notice"])

    def test_hybrid_offline_fallback_missing_key_and_timeout(self):
        base = problem(); low = DetectedProblem(base.problem_id, base.category, base.severity, .5, base.evidence, base.likely_cause, base.recommended_fix_workflow, base.requires_administrator, base.requires_user_confirmation, base.risk_level)
        missing = HybridDecisionOrchestrator(ApprovedFixRegistry(), MockProvider(ai_response()), "hybrid_ai", None).decide([low], [])
        timeout = HybridDecisionOrchestrator(ApprovedFixRegistry(), MockProvider(error=TimeoutError()), "hybrid_ai", "key").decide([low], [])
        self.assertEqual(missing[0].source, "offline_fallback"); self.assertEqual(timeout[0].source, "offline_fallback")

    def test_ai_validation_and_offline_priority(self):
        low = problem(); low = DetectedProblem(low.problem_id, low.category, low.severity, .5, low.evidence, low.likely_cause, low.recommended_fix_workflow, low.requires_administrator, low.requires_user_confirmation, low.risk_level)
        for response in ({}, ai_response("unknown"), ai_response(reasoning="Run PowerShell ipconfig /flushdns")):
            decision = HybridDecisionOrchestrator(ApprovedFixRegistry(), MockProvider(response), "hybrid_ai", "key").decide([low], [])[0]
            self.assertEqual(decision.source, "offline_fallback")
        valid = HybridDecisionOrchestrator(ApprovedFixRegistry(), MockProvider(ai_response()), "hybrid_ai", "key").decide([low], [])[0]
        self.assertEqual(valid.source, "ai_assisted"); self.assertEqual(valid.workflow_id, "network_renew_ip")
        strong_provider = MockProvider(ai_response())
        strong = HybridDecisionOrchestrator(ApprovedFixRegistry(), strong_provider, "hybrid_ai", "key").decide([problem()], [])
        self.assertEqual(strong[0].source, "offline_deterministic"); self.assertEqual(strong_provider.calls, 0)
