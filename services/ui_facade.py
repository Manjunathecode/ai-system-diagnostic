"""Stable, UI-oriented application boundary for Tkinter, Qt, and tests.

This module contains no Qt types and never accepts executable instructions.
"""
from __future__ import annotations

import json
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.bootstrap import ApplicationContext
from config.branding import BRANDING, resolve_brand_asset
from config.settings import VALID_AI_MODES
from decision_engine.hybrid_orchestrator import HybridDecisionOrchestrator
from decision_engine.offline_rules import OfflineDecisionEngine
from diagnostics.windows_diagnostics import WindowsDiagnosticEngine
from fixes.executor import AutonomousFixEngine
from fixes.registry import ApprovedFixRegistry
from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity
from reports.report_service import ReportService
from services.ai_provider import UnavailableAIProvider
from services.conversation_service import ConversationService
from services.demo_service import DemoService


def _title(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe_value(item) for item in value]
    return value


class UIFacade:
    """Coordinates existing backend services and maps their state for presentation."""

    SCAN_SECTIONS = ("System", "CPU & Memory", "Storage", "Network", "DNS", "Gateway", "Services", "Printer", "Devices")
    REQUIRED_DIAGNOSTICS = frozenset({"System overview", "CPU usage", "Memory usage", "Drive capacity", "Network connectivity",
                                      "Important service status", "Printer diagnostics", "Device status"})

    def __init__(self, context: ApplicationContext) -> None:
        self.context = context
        self.registry = ApprovedFixRegistry()
        self.reporter = ReportService(context.settings.database_path, context.settings.reports_directory, context.settings.ai_mode)
        self.conversation = ConversationService(context.database, self.registry, context.settings.disk_free_threshold_percent)
        # Persisted scans remain history; a new process has no current live scan.
        self.results: list[DiagnosticResult] = []
        self.problems = []
        self.hybrid_decisions = []
        self.session = None
        self.attempts = ()
        self.escalation = None
        self.demo_outcome = None
        self._repair_lock = threading.Lock()
        self._attempted_problem_ids: set[str] = set()

    def _restore_latest_results(self) -> list[DiagnosticResult]:
        restored = []
        for record in self.context.database.diagnostic_records():
            try:
                restored.append(DiagnosticResult(record["scan_id"], record["category"], record["name"], DiagnosticStatus(record["status"]),
                                                 Severity(record.get("severity", "info")), record.get("summary", ""),
                                                 datetime.fromisoformat(record["collected_at"]), record.get("details", {})))
            except (KeyError, TypeError, ValueError):
                continue
        return restored

    @property
    def branding(self) -> dict:
        values = BRANDING.as_dict()
        logo_path = resolve_brand_asset(self.context.settings.project_root, BRANDING.app_logo)
        icon_path = resolve_brand_asset(self.context.settings.project_root, BRANDING.app_icon)
        values["logo_url"] = Path(logo_path).resolve().as_uri() if logo_path else ""
        values["icon_path"] = icon_path
        return values

    @staticmethod
    def diagnostic_view(result: DiagnosticResult) -> dict:
        return {"scanId": result.scan_id, "category": result.category, "name": result.name, "status": result.status.value,
                "statusLabel": _title(result.status.value), "severity": result.severity.value, "severityLabel": _title(result.severity.value),
                "summary": result.summary, "collectedAt": result.collected_at.isoformat(), "details": _safe_value(result.details),
                "detailsText": json.dumps(_safe_value(result.details), indent=2, ensure_ascii=False, default=str)}

    @staticmethod
    def problem_view(problem) -> dict:
        workflow = ApprovedFixRegistry().get(problem.recommended_fix_workflow)
        required_targets_present = bool(workflow) and all(problem.parameters.get(name) for name in workflow.required_parameters)
        recovery_confirmation = AutonomousFixEngine.recovery_requires_confirmation(problem.recommended_fix_workflow,
                                                                                    ApprovedFixRegistry())
        return {"problemId": problem.problem_id, "title": problem.likely_cause, "category": problem.category,
                "severity": problem.severity.value, "severityLabel": _title(problem.severity.value),
                "confidence": round(problem.confidence * 100), "confidenceLabel": f"{problem.confidence:.0%}",
                "evidence": list(problem.evidence), "evidenceText": "\n".join(f"• {item}" for item in problem.evidence),
                "likelyCause": problem.likely_cause, "workflowId": problem.recommended_fix_workflow,
                "workflowLabel": _title(problem.recommended_fix_workflow), "risk": problem.risk_level.value,
                "riskLabel": _title(problem.risk_level.value), "requiresAdministrator": problem.requires_administrator,
                "requiresConfirmation": problem.requires_user_confirmation or recovery_confirmation,
                "parameters": _safe_value(problem.parameters),
                "repairUnavailableReason": "Manual review only: no executable approved workflow." if not workflow or not workflow.executable else
                    "The exact repair target was not collected. Run relevant diagnostics before repairing." if not required_targets_present else
                    "This workflow is disabled." if not workflow.enabled else "",
                "repairAvailable": bool(workflow and workflow.enabled and workflow.executable and required_targets_present)}

    @staticmethod
    def repair_view(result) -> dict:
        assessment = result.assessment
        return {"attemptId": result.attempt_id, "problemId": result.problem_id, "workflowId": result.fix_id,
                "workflowLabel": _title(result.fix_id), "status": result.status.value, "statusLabel": _title(result.status.value),
                "message": result.message, "startedAt": result.started_at.isoformat(), "completedAt": result.completed_at.isoformat(),
                "durationSeconds": round((result.completed_at - result.started_at).total_seconds(), 3),
                "before": _safe_value(result.before_snapshot), "after": _safe_value(result.after_snapshot),
                "beforeText": json.dumps(_safe_value(result.before_snapshot), indent=2, default=str),
                "afterText": json.dumps(_safe_value(result.after_snapshot), indent=2, default=str),
                "verificationEvidence": [] if assessment is None else list(assessment.verification_evidence),
                "verificationText": "Verification evidence unavailable" if assessment is None else "\n".join(assessment.verification_evidence),
                "confidence": 0 if assessment is None else round(assessment.confidence_score * 100),
                "unresolvedSymptoms": [] if assessment is None else list(assessment.unresolved_symptoms),
                "events": [_safe_value(item) for item in result.audit_events]}

    def dashboard(self) -> dict:
        summary = self.context.database.dashboard_summary()
        findings = [self.diagnostic_view(item) for item in self.results]
        needs_attention = [item for item in findings if item["status"] in {"warning", "failed", "error"}]
        incomplete = [item for item in findings if item["status"] in {"not_run", "permission_required", "unavailable"}]
        complete_names = {item["name"] for item in findings}
        if not findings:
            health = "Not checked"
        elif needs_attention:
            health = "Needs attention"
        elif incomplete or not self.REQUIRED_DIAGNOSTICS.issubset(complete_names):
            health = "Incomplete"
        else:
            health = "Healthy"
        metrics = {"cpu": "Awaiting scan", "memory": "Awaiting scan", "storage": "Awaiting scan", "network": "Awaiting scan",
                   "services": "Awaiting scan", "devices": "Awaiting scan"}
        for item in findings:
            details = item.get("details", {})
            if item.get("name") == "CPU usage" and details.get("cpu_percent") is not None:
                metrics["cpu"] = f"{details['cpu_percent']:.0f}%"
            elif item.get("name") == "Memory usage" and details.get("memory_percent") is not None:
                metrics["memory"] = f"{details['memory_percent']}%"
            elif item.get("name") == "Drive capacity":
                drives = details.get("drives", [])
                if drives:
                    metrics["storage"] = f"{min(float(d.get('free_percent', 0)) for d in drives):.0f}% free minimum"
            elif item.get("name") == "Network connectivity":
                metrics["network"] = "Connected" if details.get("internet_connectivity") else "Unavailable"
            elif item.get("name") == "Important service status":
                stopped = details.get("needs_attention", [])
                unavailable = details.get("unavailable_services", [])
                metrics["services"] = f"{len(stopped)} need attention" if stopped else f"{len(unavailable)} unavailable" if unavailable else "All applicable healthy"
            elif item.get("name") == "Device status":
                count = len(details.get("devices_with_errors", [])) + len(details.get("disabled_devices", []))
                metrics["devices"] = "No reported issues" if not count else f"{count} need attention"
        return {"health": health, "healthDetail": "Run a scan to check this device." if not findings else f"{len(findings)} checks recorded; {len(needs_attention)} need attention; {len(incomplete)} incomplete.",
                "hasScan": bool(findings), "lastScan": summary["last_scan"], "metrics": metrics,
                "problemsDetected": len(self.problems) if self.results else len(needs_attention), "repairsAttempted": summary["repairs"],
                "resolvedRepairs": summary["resolved"], "escalatedIssues": summary["escalated"],
                "recentActivity": self.context.database.recent_activity(),
                "privacyMode": self.context.settings.ai_mode, "administrator": self.context.is_administrator,
                "portableReady": self.context.portable_health.writable}

    def full_scan(self, progress: Callable[[str, int], None] | None = None) -> dict:
        self.session, self.attempts, self.escalation, self.demo_outcome = None, (), None, None
        self._attempted_problem_ids.clear()
        self.results = WindowsDiagnosticEngine(self.context.settings.disk_free_threshold_percent).run_full_scan(progress)
        self.context.database.save_diagnostic_results(self.results)
        self.problems = OfflineDecisionEngine(self.registry, self.context.settings.disk_free_threshold_percent).analyze(self.results)
        self.hybrid_decisions = HybridDecisionOrchestrator(self.registry, UnavailableAIProvider(), self.context.settings.ai_mode,
                                                            self.context.settings.ai_api_key).decide(self.problems, self.results, self.context.database.recent_fix_outcomes())
        return {"diagnostics": [self.diagnostic_view(item) for item in self.results],
                "problems": [self.problem_view(item) for item in self.problems], "dashboard": self.dashboard(),
                "scanId": self.results[0].scan_id if self.results else "", "completedAt": datetime.now().astimezone().isoformat()}

    def start_troubleshooting(self, description: str) -> dict:
        clean = description.strip()
        if not clean:
            raise ValueError("Describe what is happening before starting.")
        self.results, self.problems, self.hybrid_decisions = [], [], []
        self.attempts, self.escalation, self.demo_outcome = (), None, None
        self._attempted_problem_ids.clear()
        self.session = self.conversation.start(clean)
        return self.session_view()

    def reset_troubleshooting(self) -> None:
        self.session = None
        self.results, self.problems, self.hybrid_decisions = [], [], []
        self.attempts, self.escalation, self.demo_outcome = (), None, None
        self._attempted_problem_ids.clear()

    def continue_troubleshooting(self, answer: str, progress: Callable[[str, int], None] | None = None) -> dict:
        if self.session is None:
            raise ValueError("Start a troubleshooting session first.")
        if not answer.strip():
            raise ValueError("Enter an answer before continuing.")
        self.session = self.conversation.answer_and_diagnose(self.session, answer.strip(), progress)
        self.results = self.conversation.diagnostic_results(self.session.session_id)
        self.problems = self.conversation.problems(self.session.session_id)
        return self.session_view()

    def session_view(self) -> dict:
        if self.session is None:
            return {}
        return {"sessionId": self.session.session_id, "category": self.session.detected_category,
                "confidence": round(self.session.classification_confidence * 100), "status": self.session.final_status,
                "statusLabel": _title(self.session.final_status), "question": self.session.pending_questions[0] if self.session.pending_questions else "",
                "messages": [{"role": item.role, "content": item.content, "kind": item.kind, "createdAt": item.created_at.isoformat()} for item in self.session.conversation_messages],
                "recommendedWorkflow": self.session.recommended_workflows[0] if self.session.recommended_workflows else ""}

    def execute_problem(self, index: int, user_confirmed: bool = False) -> dict:
        if not 0 <= index < len(self.problems):
            raise IndexError("Select an available problem first")
        problem = self.problems[index]
        if problem.problem_id in self._attempted_problem_ids:
            raise RuntimeError("This problem already has a repair attempt in the current session.")
        if not self._repair_lock.acquire(blocking=False):
            raise RuntimeError("Another approved repair is already running.")
        self._attempted_problem_ids.add(problem.problem_id)
        try:
            engine = AutonomousFixEngine(self.registry, self.context.database.save_fix_audit_event)
            self.attempts, self.escalation = engine.run_with_recovery(problem, user_confirmed=user_confirmed)
            for result in self.attempts:
                self.context.database.save_fix_attempt(result)
        finally:
            self._repair_lock.release()
        if self.session is not None:
            self.session.fix_attempts.extend({"attempt_id": item.attempt_id, "workflow": item.fix_id, "status": item.status.value,
                                              "verification_evidence": [] if item.assessment is None else item.assessment.verification_evidence} for item in self.attempts)
            self.session.final_status = "escalated" if self.escalation else (self.attempts[-1].status.value if self.attempts else "failed")
            if self.escalation:
                self.session.escalation_id = self.escalation.problem.problem_id
                self.session.escalation = {
                    "problem_id": self.escalation.problem.problem_id,
                    "original_symptom": self.session.user_problem_description,
                    "detected_problem": self.escalation.problem.likely_cause,
                    "diagnostics": list(self.session.diagnostic_findings),
                    "diagnostic_evidence": list(self.escalation.diagnostic_evidence),
                    "fixes_attempted": [{"attempt_id": item.attempt_id, "workflow_id": item.fix_id,
                                          "outcome": item.status.value} for item in self.escalation.fixes_attempted],
                    "remaining_symptoms": list(self.escalation.remaining_symptoms),
                    "verification_results": [{"attempt_id": item.attempt_id,
                                               "assessment": None if item.assessment is None else item.assessment.status.value,
                                               "evidence": [] if item.assessment is None else list(item.assessment.verification_evidence)}
                                              for item in self.escalation.fixes_attempted],
                    "fallback_attempts": [item.fix_id for item in self.escalation.fixes_attempted[1:]],
                    "reason": "Maximum compatible approved attempts were exhausted without verified resolution.",
                    "recommended_human_action": self.escalation.recommended_human_action,
                    "administrator_required": self.escalation.administrator_required,
                }
            else:
                self.session.escalation = None
            self.context.database.save_session(self.session)
        return {"attempts": [self.repair_view(item) for item in self.attempts],
                "escalated": self.escalation is not None,
                "escalation": {} if self.escalation is None else {"remainingSymptoms": list(self.escalation.remaining_symptoms),
                    "recommendedHumanAction": self.escalation.recommended_human_action,
                    "administratorRequired": self.escalation.administrator_required}, "dashboard": self.dashboard()}

    def run_demo(self, scenario: str) -> dict:
        self.demo_outcome = DemoService(self.registry).run(scenario)
        return {"simulation": True, "scenario": scenario,
                "findings": [self.diagnostic_view(item) for item in self.demo_outcome["findings"]],
                "problems": [self.problem_view(item) for item in self.demo_outcome["problems"]],
                "attempts": [self.repair_view(item) for item in self.demo_outcome["attempts"]],
                "escalated": self.demo_outcome["escalation"] is not None}

    def export_report(self, report_kind: str, output_format: str) -> Path:
        self.reporter = ReportService(self.context.settings.database_path, self.context.settings.reports_directory, self.context.settings.ai_mode)
        if report_kind == "session":
            if self.session is None:
                sessions = self.context.database.recent_sessions(1)
                if not sessions:
                    raise ValueError("No troubleshooting session is available to export")
                source = sessions[0]["session_id"]
            else:
                source = self.session.session_id
            report = self.reporter.build_session_report(source)
        elif report_kind == "diagnostic":
            scan_id = self.results[0].scan_id if self.results else self.context.database.latest_scan_id()
            if not scan_id:
                raise ValueError("Run a system scan before exporting diagnostics")
            report = self.reporter.build_diagnostic_report(scan_id)
        elif report_kind == "escalation":
            if self.session is None or self.session.final_status != "escalated":
                raise ValueError("No escalated troubleshooting session is available")
            report = self.reporter.build_escalation_report(self.session.session_id)
        elif report_kind == "demo":
            if not self.demo_outcome:
                raise ValueError("Run a Demo Lab scenario before exporting")
            report = self.reporter.build_demo_report(self.demo_outcome)
        elif report_kind == "summary":
            report = self.reporter.build_summary_activity_report()
        else:
            raise ValueError("Unknown report type")
        return self.reporter.export(report, output_format)

    def report_history(self) -> list[dict]:
        return self.reporter.history()

    def update_preferences(self, privacy_mode: str | None = None, auto_fix: bool | None = None, reduce_motion: bool | None = None) -> dict:
        mode = privacy_mode or self.context.settings.ai_mode
        if mode not in VALID_AI_MODES:
            raise ValueError("Unsupported privacy mode")
        values = {"portable_mode": True, "privacy_mode": mode,
                  "auto_fix_low_risk": self.context.settings.auto_fix_low_risk if auto_fix is None else bool(auto_fix),
                  "reduce_motion": self.context.settings.reduce_motion if reduce_motion is None else bool(reduce_motion),
                  "notes": "Credentials remain environment-only and are never stored here."}
        path = self.context.settings.config_directory / "portable_settings.json"
        path.write_text(json.dumps(values, indent=2), encoding="utf-8")
        new_settings = replace(self.context.settings, ai_mode=mode, auto_fix_low_risk=values["auto_fix_low_risk"], reduce_motion=values["reduce_motion"])
        object.__setattr__(self.context, "settings", new_settings)
        return values
