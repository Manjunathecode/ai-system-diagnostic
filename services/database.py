"""SQLite storage initialization for portable operation."""
from __future__ import annotations

import sqlite3
import json
from contextlib import closing
from pathlib import Path


class Database:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS application_runs (
                    id INTEGER PRIMARY KEY,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    application_version TEXT NOT NULL,
                    is_administrator INTEGER NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS fix_attempts (
                    attempt_id TEXT PRIMARY KEY, problem_id TEXT NOT NULL, fix_id TEXT NOT NULL,
                    status TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT NOT NULL,
                    duration_seconds REAL NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
                    assessment_json TEXT NOT NULL,
                    parameters_json TEXT NOT NULL DEFAULT '{}',
                    execution_succeeded INTEGER NOT NULL DEFAULT 0,
                    audit_json TEXT NOT NULL DEFAULT '[]',
                    execution_json TEXT NOT NULL DEFAULT '{}'
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS diagnostic_results (
                    id INTEGER PRIMARY KEY, scan_id TEXT NOT NULL, category TEXT NOT NULL,
                    status TEXT NOT NULL, collected_at TEXT NOT NULL, payload_json TEXT NOT NULL
                )
            """)
            existing = {row[1] for row in connection.execute("PRAGMA table_info(fix_attempts)")}
            for name, declaration in (
                ("parameters_json", "TEXT NOT NULL DEFAULT '{}'"),
                ("execution_succeeded", "INTEGER NOT NULL DEFAULT 0"),
                ("audit_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("execution_json", "TEXT NOT NULL DEFAULT '{}'"),
            ):
                if name not in existing:
                    connection.execute(f"ALTER TABLE fix_attempts ADD COLUMN {name} {declaration}")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS fix_audit_events (
                    id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    problem_id TEXT NOT NULL, fix_id TEXT NOT NULL, stage TEXT NOT NULL,
                    message TEXT NOT NULL, payload_json TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS follow_up_context (
                    id INTEGER PRIMARY KEY, problem_id TEXT NOT NULL, question TEXT NOT NULL,
                    answer TEXT NOT NULL, recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS troubleshooting_sessions (
                    session_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    category TEXT NOT NULL, final_status TEXT NOT NULL, payload_json TEXT NOT NULL
                )
            """)

    def save_diagnostic_results(self, results: list) -> None:
        """Persist read-only scan results for later report generation."""
        rows = [(item.scan_id, item.category, item.status.value, item.collected_at.isoformat(),
                 json.dumps({"name": item.name, "severity": item.severity.value, "summary": item.summary, "details": item.details}, default=str)) for item in results]
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.executemany("INSERT INTO diagnostic_results (scan_id, category, status, collected_at, payload_json) VALUES (?, ?, ?, ?, ?)", rows)

    def save_fix_audit_event(self, event: dict) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("INSERT INTO fix_audit_events (problem_id, fix_id, stage, message, payload_json) VALUES (?, ?, ?, ?, ?)",
                               (event["problem_id"], event["fix_id"], event["stage"], event["message"], json.dumps(event)))

    def save_fix_attempt(self, result) -> None:
        assessment = result.assessment
        payload = {} if assessment is None else {"status": assessment.status.value, "verification_evidence": assessment.verification_evidence,
                                                  "comparison": assessment.before_after_comparison, "confidence_score": assessment.confidence_score,
                                                  "unresolved_symptoms": assessment.unresolved_symptoms}
        duration = (result.completed_at - result.started_at).total_seconds()
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("""INSERT OR REPLACE INTO fix_attempts
                (attempt_id, problem_id, fix_id, status, started_at, completed_at, duration_seconds,
                 before_json, after_json, assessment_json, parameters_json, execution_succeeded, audit_json,
                 execution_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (result.attempt_id, result.problem_id, result.fix_id, result.status.value, result.started_at.isoformat(),
                               result.completed_at.isoformat(), duration, json.dumps(result.before_snapshot), json.dumps(result.after_snapshot),
                               json.dumps(payload), json.dumps(result.parameters), int(result.execution_succeeded),
                               json.dumps(result.audit_events, default=str), json.dumps(result.execution_details, default=str)))

    def recent_fix_outcomes(self, limit: int = 3) -> list[dict]:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            rows = connection.execute("SELECT fix_id, status, assessment_json FROM fix_attempts ORDER BY completed_at DESC LIMIT ?", (limit,)).fetchall()
        return [{"workflow_id": row[0], "status": row[1], "assessment": json.loads(row[2]).get("status")} for row in rows]

    def save_follow_up_answer(self, problem_id: str, question: str, answer: str) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("INSERT INTO follow_up_context (problem_id, question, answer) VALUES (?, ?, ?)", (problem_id, question, answer))

    def save_session(self, session) -> None:
        payload = {key: value for key, value in session.__dict__.items() if key not in {"session_id", "created_at", "updated_at", "detected_category", "final_status"}}
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("INSERT OR REPLACE INTO troubleshooting_sessions VALUES (?, ?, ?, ?, ?, ?)",
                               (session.session_id, session.created_at.isoformat(), session.updated_at.isoformat(), session.detected_category,
                                session.final_status, json.dumps(payload, default=str)))

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            rows = connection.execute("SELECT session_id, updated_at, category, final_status FROM troubleshooting_sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [{"session_id": row[0], "updated_at": row[1], "category": row[2], "status": row[3]} for row in rows]

    def dashboard_summary(self) -> dict:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            repair_rows = connection.execute("SELECT status, execution_succeeded, assessment_json FROM fix_attempts").fetchall()
            sessions = connection.execute("SELECT final_status, COUNT(*) FROM troubleshooting_sessions GROUP BY final_status").fetchall()
            latest = connection.execute("SELECT MAX(collected_at) FROM diagnostic_results").fetchone()[0]
        session_counts = dict(sessions)
        verified_resolved = sum(status == "resolved" and bool(executed) and json.loads(assessment).get("status") == "success"
                                for status, executed, assessment in repair_rows)
        escalated_repairs = sum(status == "escalated" for status, _executed, _assessment in repair_rows)
        return {"last_scan": latest or "Not yet run", "problems": sum(session_counts.values()), "repairs": len(repair_rows),
                "resolved": verified_resolved, "escalated": escalated_repairs + session_counts.get("escalated", 0)}

    def latest_scan_id(self) -> str | None:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            row = connection.execute("SELECT scan_id FROM diagnostic_results ORDER BY collected_at DESC, id DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def diagnostic_records(self, scan_id: str | None = None) -> list[dict]:
        target = scan_id or self.latest_scan_id()
        if not target:
            return []
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            rows = connection.execute("SELECT scan_id, category, status, collected_at, payload_json FROM diagnostic_results WHERE scan_id=? ORDER BY id", (target,)).fetchall()
        records = []
        for stored_scan_id, category, status, collected_at, payload_json in rows:
            payload = json.loads(payload_json)
            records.append({"scan_id": stored_scan_id, "category": category, "status": status, "collected_at": collected_at, **payload})
        return records

    def repair_attempts(self, limit: int = 50) -> list[dict]:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            rows = connection.execute("SELECT attempt_id, problem_id, fix_id, status, started_at, completed_at, duration_seconds, before_json, after_json, assessment_json, parameters_json, execution_succeeded, audit_json, execution_json FROM fix_attempts ORDER BY completed_at DESC LIMIT ?", (limit,)).fetchall()
        return [{"attempt_id": row[0], "problem_id": row[1], "fix_id": row[2], "status": row[3], "started_at": row[4], "completed_at": row[5],
                 "duration_seconds": row[6], "before": json.loads(row[7]), "after": json.loads(row[8]), "assessment": json.loads(row[9]),
                 "parameters": json.loads(row[10]), "execution_succeeded": bool(row[11]), "audit_events": json.loads(row[12]),
                 "execution_details": json.loads(row[13])} for row in rows]

    def repair_attempts_by_ids(self, attempt_ids: list[str] | tuple[str, ...]) -> list[dict]:
        if not attempt_ids:
            return []
        placeholders = ",".join("?" for _ in attempt_ids)
        with closing(sqlite3.connect(self.database_path)) as connection:
            rows = connection.execute(
                f"SELECT attempt_id, problem_id, fix_id, status, started_at, completed_at, duration_seconds, before_json, after_json, assessment_json, parameters_json, execution_succeeded, audit_json, execution_json FROM fix_attempts WHERE attempt_id IN ({placeholders})",
                tuple(attempt_ids),
            ).fetchall()
        by_id = {row[0]: {"attempt_id": row[0], "problem_id": row[1], "fix_id": row[2], "status": row[3],
                          "started_at": row[4], "completed_at": row[5], "duration_seconds": row[6],
                          "before": json.loads(row[7]), "after": json.loads(row[8]), "assessment": json.loads(row[9]),
                          "parameters": json.loads(row[10]), "execution_succeeded": bool(row[11]),
                          "audit_events": json.loads(row[12]), "execution_details": json.loads(row[13])} for row in rows}
        return [by_id[item] for item in attempt_ids if item in by_id]

    def recent_activity(self, limit: int = 12) -> list[dict]:
        activity = []
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            scans = connection.execute("SELECT scan_id, MAX(collected_at), COUNT(*), SUM(CASE WHEN status IN ('warning','failed','error','not_run','permission_required','unavailable') THEN 1 ELSE 0 END) FROM diagnostic_results GROUP BY scan_id ORDER BY MAX(collected_at) DESC LIMIT ?", (limit,)).fetchall()
            sessions = connection.execute("SELECT session_id, updated_at, category, final_status FROM troubleshooting_sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            fixes = connection.execute("SELECT attempt_id, completed_at, fix_id, status FROM fix_attempts ORDER BY completed_at DESC LIMIT ?", (limit,)).fetchall()
        activity.extend({"id": row[0], "timestamp": row[1], "kind": "scan", "title": "System scan", "detail": f"{row[2]} checks; {row[3] or 0} need attention"} for row in scans)
        activity.extend({"id": row[0], "timestamp": row[1], "kind": "session", "title": row[2], "detail": row[3].replace("_", " ").title()} for row in sessions)
        activity.extend({"id": row[0], "timestamp": row[1], "kind": "repair", "title": row[2].replace("_", " ").title(), "detail": row[3].replace("_", " ").title()} for row in fixes)
        return sorted(activity, key=lambda item: item["timestamp"], reverse=True)[:limit]

    def session_details(self, session_id: str) -> dict | None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute("SELECT session_id, created_at, updated_at, category, final_status, payload_json FROM troubleshooting_sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return None
        return {"session_id": row[0], "created_at": row[1], "updated_at": row[2], "category": row[3], "status": row[4], **json.loads(row[5])}
