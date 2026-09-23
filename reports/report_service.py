"""Build reports exclusively from persisted SQLite evidence or explicit demo data."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from config.branding import APP_NAME, APP_VERSION
from reports.csv_exporter import export_csv
from reports.json_exporter import export_json
from reports.pdf_generator import export_pdf
from reports.sanitization import sanitize
from services.database import Database


class ReportService:
    FORMATS = ("pdf", "csv", "json")

    def __init__(self, database_path: Path, reports_directory: Path, privacy_mode: str = "offline_only") -> None:
        self.database_path = Path(database_path)
        self.reports_directory = Path(reports_directory)
        self.privacy_mode = privacy_mode
        self.reports_directory.mkdir(parents=True, exist_ok=True)

    def _base(self, report_type: str, source_id: str) -> dict:
        generated = datetime.now(timezone.utc)
        return {"report_id": str(uuid.uuid4()), "report_type": report_type, "generated_at": generated.isoformat(),
                "application_name": APP_NAME, "application_version": APP_VERSION, "privacy_mode": self.privacy_mode,
                "source_id": source_id}

    def build_session_report(self, session_id: str) -> dict:
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute("SELECT created_at, updated_at, category, final_status, payload_json FROM troubleshooting_sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise ValueError(f"Troubleshooting session was not found: {session_id}")
        payload = json.loads(row[4])
        attempt_ids = [item.get("attempt_id") for item in payload.get("fix_attempts", []) if item.get("attempt_id")]
        attempts = Database(self.database_path).repair_attempts_by_ids(attempt_ids)
        escalation = payload.get("escalation")
        final_status, repair_outcome = self._verified_outcome(row[3], attempts, escalation)
        report = self._base("troubleshooting_session", session_id)
        report.update({"session_id": session_id, "created_at": row[0], "updated_at": row[1], "detected_category": row[2],
                       "user_reported_problem": payload.get("user_problem_description"), "follow_up_questions": payload.get("follow_up_questions", []),
                       "user_answers": payload.get("user_answers", []), "diagnostics_performed": payload.get("diagnostic_runs", []),
                       "diagnostic_findings": payload.get("diagnostic_findings", []), "detected_problems": payload.get("detected_problems", []),
                       "recommended_workflows": payload.get("recommended_workflows", []), "fix_attempts": attempts,
                       "stored_session_status": row[3], "final_status": final_status, "repair_outcome": repair_outcome,
                       "escalation": escalation,
                       "executive_summary": {"category": row[2], "final_status": final_status}})
        return sanitize(report)

    @staticmethod
    def _verified_outcome(stored_status: str, attempts: list[dict], escalation: dict | None) -> tuple[str, dict]:
        """Derive report claims from persisted verification, never from a UI status alone."""
        if not attempts:
            final = "escalated" if stored_status == "escalated" and escalation else \
                "failed" if stored_status == "failed" else "not_verified"
            return final, {"attempted": False, "execution_succeeded": False,
                           "verification_succeeded": False, "assessment": None,
                           "evidence_source": "No persisted repair verification exists."}
        last = attempts[-1]
        assessment = last.get("assessment") or {}
        assessment_status = assessment.get("status")
        if escalation:
            final = "escalated"
        elif last["status"] == "resolved" and assessment_status == "success" and last.get("execution_succeeded"):
            final = "resolved"
        elif last["status"] == "partially_resolved" and assessment_status == "partial_success" and last.get("execution_succeeded"):
            final = "partially_resolved"
        elif last["status"] == "awaiting_confirmation":
            final = "awaiting_confirmation"
        elif assessment_status == "verification_unavailable":
            final = "verification_unavailable"
        else:
            final = "failed"
        return final, {"attempted": True,
                       "execution_succeeded": any(item.get("execution_succeeded", False) for item in attempts),
                       "verification_succeeded": assessment_status == "success",
                       "assessment": assessment_status,
                       "verification_evidence": assessment.get("verification_evidence", []),
                       "evidence_source": "Persisted fix attempt and deterministic verification assessment."}

    def build_diagnostic_report(self, scan_id: str | None = None) -> dict:
        with closing(sqlite3.connect(self.database_path)) as connection:
            if scan_id is None:
                found = connection.execute("SELECT scan_id FROM diagnostic_results ORDER BY collected_at DESC LIMIT 1").fetchone()
                scan_id = found[0] if found else "no-scan"
            rows = connection.execute("SELECT category, status, collected_at, payload_json FROM diagnostic_results WHERE scan_id=? ORDER BY id", (scan_id,)).fetchall()
        findings = []
        for category, status, collected_at, payload_json in rows:
            payload = json.loads(payload_json)
            findings.append({"category": category, "status": status, "collected_at": collected_at, **payload})
        report = self._base("system_diagnostic", scan_id)
        report.update({"scan_id": scan_id, "diagnostic_findings": findings,
                       "executive_summary": {"findings_collected": len(findings), "warnings": sum(item["status"] in {"warning", "failed"} for item in findings),
                                             "not_run": sum(item["status"] in {"not_run", "unavailable", "permission_required", "error"} for item in findings), "final_status": "Evidence only"}})
        return sanitize(report)

    def build_repair_report(self, attempt_id: str) -> dict:
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute("SELECT attempt_id, problem_id, fix_id, status, started_at, completed_at, duration_seconds, before_json, after_json, assessment_json, parameters_json, execution_succeeded, audit_json, execution_json FROM fix_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        if row is None:
            raise ValueError(f"Repair attempt was not found: {attempt_id}")
        report = self._base("repair_attempt", attempt_id)
        assessment = json.loads(row[9])
        final = "resolved" if row[3] == "resolved" and assessment.get("status") == "success" and bool(row[11]) else \
            "partially_resolved" if row[3] == "partially_resolved" and assessment.get("status") == "partial_success" and bool(row[11]) else \
            "verification_unavailable" if assessment.get("status") == "verification_unavailable" else "failed"
        report.update({"attempt_id": row[0], "problem_id": row[1], "workflow_id": row[2], "final_status": final,
                       "started_at": row[4], "completed_at": row[5], "duration_seconds": row[6],
                       "before_after_comparison": {"before": json.loads(row[7]), "after": json.loads(row[8])},
                       "verification_evidence": assessment, "parameters": json.loads(row[10]),
                       "execution_succeeded": bool(row[11]), "audit_events": json.loads(row[12]),
                       "execution_details": json.loads(row[13]),
                       "executive_summary": {"final_status": final}})
        return sanitize(report)

    def build_escalation_report(self, session_id: str) -> dict:
        report = self.build_session_report(session_id)
        if report.get("final_status") != "escalated":
            raise ValueError("The selected session has no persisted escalation outcome")
        report["report_type"] = "escalation"
        return report

    def build_summary_activity_report(self) -> dict:
        with closing(sqlite3.connect(self.database_path)) as connection:
            sessions = connection.execute("SELECT final_status, COUNT(*) FROM troubleshooting_sessions GROUP BY final_status").fetchall()
            repairs = connection.execute("SELECT status, execution_succeeded, assessment_json FROM fix_attempts").fetchall()
            scans = connection.execute("SELECT COUNT(DISTINCT scan_id) FROM diagnostic_results").fetchone()[0]
        report = self._base("summary_activity", "local-database")
        verified_counts = {}
        for status, executed, assessment_json in repairs:
            assessment = json.loads(assessment_json)
            if status in {"resolved", "partially_resolved"} and (not executed or assessment.get("status") != {"resolved": "success", "partially_resolved": "partial_success"}[status]):
                status = "not_verified"
            verified_counts[status] = verified_counts.get(status, 0) + 1
        report.update({"scan_count": scans, "stored_session_statuses": dict(sessions), "repair_outcomes": verified_counts,
                       "executive_summary": {"final_status": "Recorded activity only"}})
        return sanitize(report)

    def build_demo_report(self, outcome: dict) -> dict:
        source = f"demo-{uuid.uuid4()}"
        report = self._base("simulated_demo", source)
        attempts = [{"workflow": item.fix_id, "status": item.status.value, "verification": None if item.assessment is None else item.assessment.verification_evidence} for item in outcome.get("attempts", ())]
        report.update({"simulation": True, "scenario": outcome.get("scenario"), "diagnostic_findings": outcome.get("findings", []),
                       "detected_problems": outcome.get("problems", []), "fix_attempts": attempts,
                       "escalation": outcome.get("escalation"), "executive_summary": {"notice": "SIMULATED DATA — NO REAL REPAIR WAS PERFORMED",
                                                                                     "final_status": "Escalated" if outcome.get("escalation") else "Simulated outcome"}})
        return sanitize(report)

    def export(self, report: dict, output_format: str) -> Path:
        fmt = output_format.lower()
        if fmt not in self.FORMATS:
            raise ValueError(f"Unsupported report format: {output_format}")
        clean = sanitize(report)
        metadata = {key: clean.get(key) for key in ("report_id", "report_type", "generated_at", "source_id", "application_version")}
        clean["metadata_sha256"] = hashlib.sha256(json.dumps(metadata, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        source = str(clean.get("source_id", "report")).replace("/", "-").replace("\\", "-")[:40]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = self.reports_directory / f"{clean.get('report_type', 'report')}_{source}_{stamp}.{fmt}"
        return {"json": export_json, "csv": export_csv, "pdf": export_pdf}[fmt](clean, destination)

    def history(self, limit: int = 100) -> list[dict]:
        entries = sorted((path for path in self.reports_directory.iterdir() if path.suffix.lower().lstrip(".") in self.FORMATS), key=lambda item: item.stat().st_mtime, reverse=True)
        return [{"name": path.name, "path": str(path), "format": path.suffix.lstrip(".").upper(),
                 "generated_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(), "size_bytes": path.stat().st_size} for path in entries[:limit]]
