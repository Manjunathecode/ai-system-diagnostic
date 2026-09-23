"""Desktop application with a read-only diagnostic report screen."""
from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from tkinter import messagebox

from app.bootstrap import ApplicationContext
from diagnostics.windows_diagnostics import WindowsDiagnosticEngine
from decision_engine.offline_rules import OfflineDecisionEngine
from fixes.registry import ApprovedFixRegistry
from fixes.executor import AutonomousFixEngine
from services.ai_provider import UnavailableAIProvider
from decision_engine.hybrid_orchestrator import HybridDecisionOrchestrator
from services.conversation_service import ConversationService
from reports.report_service import ReportService
from core.privileges import relaunch_as_administrator
from services.demo_service import DemoService
from models.diagnostic import DiagnosticResult


class DesktopApplication:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context
        self.root = tk.Tk()
        self.root.title("AI System Diagnostic")
        self.root.geometry("1100x700")
        self.root.minsize(850, 560)
        self.status = tk.StringVar(value="Ready for a read-only system scan.")
        self.scan_time = tk.StringVar(value="Scan timestamps: not started")
        self.progress = tk.IntVar(value=0)
        self.auto_fix = tk.BooleanVar(value=False)
        self.follow_up_question = tk.StringVar()
        self.follow_up_answer = tk.StringVar()
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="AI System Diagnostic", font=("Segoe UI", 22, "bold")).pack(anchor=tk.W)
        self.dashboard_status = tk.StringVar(value="SYSTEM STATUS: Healthy")
        ttk.Label(frame, textvariable=self.dashboard_status, font=("Segoe UI", 11, "bold")).pack(anchor=tk.W, pady=(2, 4))
        privilege = "Administrator privileges detected" if self.context.is_administrator else "Standard user mode — some diagnostic information may be unavailable"
        ttk.Label(frame, text=privilege).pack(anchor=tk.W, pady=(2, 12))
        ttk.Label(frame, text=f"Privacy mode: {self.context.settings.ai_mode.replace('_', ' ').title()}").pack(anchor=tk.W)
        health = self.context.portable_health
        ttk.Label(frame, text=f"Portable Environment: {'Ready' if health.writable else 'Read-only'} | Free space: {health.free_bytes // (1024 * 1024)} MB").pack(anchor=tk.W, pady=(2, 8))
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X)
        self.scan_button = ttk.Button(controls, text="Start Full System Scan", command=self._start_scan)
        self.scan_button.pack(side=tk.LEFT)
        ttk.Button(controls, text="Dashboard", command=self._refresh_dashboard).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Start New Session", command=self._open_chat).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="Export Latest Diagnostics", command=self._export_diagnostics).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="Open Report Folder", command=lambda: os.startfile(self.context.settings.reports_directory)).pack(side=tk.LEFT)
        ttk.Button(controls, text="Demo Mode", command=self._open_demo).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="About", command=self._show_about).pack(side=tk.LEFT, padx=2)
        if not self.context.is_administrator:
            ttk.Button(controls, text="Restart as Administrator", command=self._request_elevation).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(controls, text="AUTO-FIX low-risk workflows", variable=self.auto_fix).pack(side=tk.LEFT, padx=12)
        self.fix_button = ttk.Button(controls, text="Apply Selected Approved Fix", command=self._apply_selected_fix, state=tk.DISABLED)
        self.fix_button.pack(side=tk.LEFT)
        ttk.Label(controls, textvariable=self.scan_time).pack(side=tk.LEFT, padx=18)
        ttk.Progressbar(controls, variable=self.progress, maximum=100, length=220).pack(side=tk.RIGHT)
        self.cards = ttk.Frame(frame); self.cards.pack(fill=tk.X, pady=(10, 0))
        self.card_vars = {key: tk.StringVar() for key in ("last_scan", "problems", "repairs", "resolved", "escalated")}
        for title, key in (("Last Scan", "last_scan"), ("Problems Detected", "problems"), ("Repairs Attempted", "repairs"), ("Repairs Resolved", "resolved"), ("Escalated Issues", "escalated")):
            card = ttk.LabelFrame(self.cards, text=title, padding=8); card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
            ttk.Label(card, textvariable=self.card_vars[key], font=("Segoe UI", 10, "bold")).pack()
        self._refresh_dashboard()
        columns = ("severity", "category", "finding", "status", "summary")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=16)
        for column, width in (("severity", 75), ("category", 140), ("finding", 170), ("status", 85), ("summary", 560)):
            self.tree.heading(column, text=column.replace("_", " ").title())
            self.tree.column(column, width=width, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=12)
        self.tree.bind("<<TreeviewSelect>>", self._show_details)
        problems = ttk.LabelFrame(frame, text="Detected problems and approved recommended actions", padding=8)
        problems.pack(fill=tk.X, pady=(0, 10))
        problem_columns = ("severity", "category", "likely_cause", "recommended_action")
        self.problem_tree = ttk.Treeview(problems, columns=problem_columns, show="headings", height=5)
        for column, width in (("severity", 75), ("category", 140), ("likely_cause", 430), ("recommended_action", 260)):
            self.problem_tree.heading(column, text=column.replace("_", " ").title())
            self.problem_tree.column(column, width=width, anchor=tk.W)
        self.problem_tree.pack(fill=tk.X)
        self.problem_tree.bind("<<TreeviewSelect>>", lambda _event: self.fix_button.configure(state=tk.NORMAL))
        follow_up = ttk.LabelFrame(frame, text="AI follow-up questions (stored as troubleshooting context only)", padding=6)
        follow_up.pack(fill=tk.X, pady=(0, 10))
        self.question_box = ttk.Combobox(follow_up, textvariable=self.follow_up_question, state="readonly", width=72)
        self.question_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Entry(follow_up, textvariable=self.follow_up_answer, width=30).pack(side=tk.LEFT, padx=6)
        ttk.Button(follow_up, text="Save Answer", command=self._save_follow_up).pack(side=tk.LEFT)
        details = ttk.LabelFrame(frame, text="Selected diagnostic finding (structured details)", padding=8)
        details.pack(fill=tk.BOTH, expand=True)
        self.detail_text = tk.Text(details, height=9, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, textvariable=self.status).pack(anchor=tk.W, pady=(10, 0))

    def _start_scan(self) -> None:
        self.scan_button.configure(state=tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.problem_tree.delete(*self.problem_tree.get_children())
        self.progress.set(0)
        started = datetime.now().astimezone()
        self.scan_time.set(f"Scan started: {started:%Y-%m-%d %H:%M:%S %Z}")
        self.status.set("Collecting diagnostics. No repair actions will be performed.")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        try:
            results = WindowsDiagnosticEngine().run_full_scan(lambda label, value: self.root.after(0, self._progress_update, label, value))
            self.context.database.save_diagnostic_results(results)
            self.root.after(0, self._scan_complete, results)
        except Exception as error:
            self.root.after(0, self._scan_failed, str(error))

    def _progress_update(self, label: str, value: int) -> None:
        self.progress.set(value)
        self.status.set(f"Scanning: {label}")

    def _scan_complete(self, results: list[DiagnosticResult]) -> None:
        for result in results:
            self.tree.insert("", tk.END, values=(result.severity.value.upper(), result.category, result.name, result.status.value.upper(), result.summary))
        finished = datetime.now().astimezone()
        issues = sum(result.status.value in {"warning", "failed", "error", "not_run", "permission_required", "unavailable"} for result in results)
        self.scan_time.set(f"Scan completed: {finished:%Y-%m-%d %H:%M:%S %Z}")
        self.progress.set(100)
        self.status.set(f"Scan complete. {len(results)} findings collected; {issues} require attention.")
        self._results = results
        self.status.set("Diagnosing available scan findings...")
        self._problems = OfflineDecisionEngine(ApprovedFixRegistry(), self.context.settings.disk_free_threshold_percent).analyze(results)
        problems = self._problems
        self._hybrid_decisions = HybridDecisionOrchestrator(ApprovedFixRegistry(), UnavailableAIProvider(), self.context.settings.ai_mode,
                                                            self.context.settings.ai_api_key).decide(problems, results, self.context.database.recent_fix_outcomes())
        for problem in problems:
            self.problem_tree.insert("", tk.END, values=(problem.severity.value.upper(), problem.category, problem.likely_cause,
                                                          problem.recommended_fix_workflow))
        questions = [question for decision in self._hybrid_decisions for question in decision.follow_up_questions]
        self._follow_up_problem_id = problems[0].problem_id if problems else "scan"
        self.question_box["values"] = questions
        if questions: self.follow_up_question.set(questions[0])
        if questions:
            self.detail_text.configure(state=tk.NORMAL); self.detail_text.delete("1.0", tk.END)
            self.detail_text.insert("1.0", json.dumps({"ai_analysis": [item.__dict__ for item in self._hybrid_decisions], "follow_up_questions": questions}, indent=2))
            self.detail_text.configure(state=tk.DISABLED)
        self.scan_button.configure(state=tk.NORMAL)
        self.dashboard_status.set("SYSTEM STATUS: Issues Detected" if issues else "SYSTEM STATUS: Healthy")
        self._refresh_dashboard()
        if self.auto_fix.get():
            low_risk = [problem for problem in problems if not problem.requires_user_confirmation]
            if low_risk:
                self.status.set("Fixing low-risk approved workflow(s)...")
                threading.Thread(target=self._auto_fix_worker, args=(low_risk,), daemon=True).start()

    def _apply_selected_fix(self) -> None:
        selection = self.problem_tree.selection()
        if not selection or not hasattr(self, "_problems"):
            return
        problem = self._problems[self.problem_tree.index(selection[0])]
        workflow = ApprovedFixRegistry().get(problem.recommended_fix_workflow)
        if not workflow or not workflow.executable or any(not problem.parameters.get(name) for name in workflow.required_parameters):
            self.status.set("No executable approved repair is available for this finding.")
            return
        confirmed = True
        if problem.requires_user_confirmation:
            confirmed = messagebox.askyesno("Confirm approved repair", f"{problem.recommended_fix_workflow} may require administrator privileges and has {problem.risk_level.value} risk.\n\nProceed?")
        if confirmed:
            self.fix_button.configure(state=tk.DISABLED)
            self.status.set("Fixing selected approved workflow...")
            threading.Thread(target=self._fix_worker, args=(problem, confirmed), daemon=True).start()

    def _auto_fix_worker(self, problems: list) -> None:
        for problem in problems:
            self._fix_worker(problem, False)

    def _fix_worker(self, problem, confirmed: bool) -> None:
        engine = AutonomousFixEngine(ApprovedFixRegistry(), self._audit_event)
        attempts, escalation = engine.run_with_recovery(problem, user_confirmed=confirmed)
        for result in attempts:
            self.context.database.save_fix_attempt(result)
        self.root.after(0, self._fix_complete, attempts, escalation)

    def _audit_event(self, event: dict) -> None:
        self.context.database.save_fix_audit_event(event)
        labels = {"pre_check": "Fixing", "fixing": "Fixing", "verifying": "Verifying", "resolved": "Resolved",
                  "failed": "Failed", "escalated": "Escalated", "awaiting_confirmation": "Awaiting confirmation"}
        self.root.after(0, self.status.set, f"{labels.get(event['stage'], event['stage'])}: {event['message']}")

    def _fix_complete(self, attempts, escalation) -> None:
        result = attempts[-1] if attempts else None
        if result is None:
            self.status.set("ESCALATED: No approved repair attempt was available.")
        else:
            label = "PARTIALLY RESOLVED" if result.status.value == "partially_resolved" else result.status.value.upper()
            self.status.set(f"{label}: {result.message}")
        timeline = []
        for attempt in attempts:
            assessment = attempt.assessment
            timeline.append({"workflow": attempt.fix_id, "status": attempt.status.value, "before": attempt.before_snapshot,
                             "after": attempt.after_snapshot, "assessment": None if assessment is None else {"status": assessment.status.value,
                             "evidence": assessment.verification_evidence, "confidence": assessment.confidence_score,
                             "unresolved": assessment.unresolved_symptoms}})
        if escalation:
            timeline.append({"escalated": True, "remaining_symptoms": escalation.remaining_symptoms,
                             "recommended_human_action": escalation.recommended_human_action})
        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", json.dumps({"repair_timeline": timeline}, indent=2, default=str))
        self.detail_text.configure(state=tk.DISABLED)
        self.fix_button.configure(state=tk.NORMAL)
        self.dashboard_status.set("SYSTEM STATUS: Escalated" if escalation else "SYSTEM STATUS: Resolved" if result and result.status.value == "resolved" else "SYSTEM STATUS: Issues Detected")
        self._refresh_dashboard()

    def _save_follow_up(self) -> None:
        question, answer = self.follow_up_question.get().strip(), self.follow_up_answer.get().strip()
        if not question or not answer:
            self.status.set("Select an AI follow-up question and provide an answer before saving.")
            return
        self.context.database.save_follow_up_answer(getattr(self, "_follow_up_problem_id", "scan"), question, answer)
        self.follow_up_answer.set("")
        self.status.set("Follow-up answer saved as troubleshooting context; it cannot execute commands.")

    def _open_chat(self) -> None:
        window = tk.Toplevel(self.root); window.title("AI System Diagnostic — Conversational Troubleshooting"); window.geometry("760x620")
        transcript = tk.Text(window, wrap=tk.WORD, state=tk.DISABLED, font=("Segoe UI", 10)); transcript.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        entry = tk.Text(window, height=4, wrap=tk.WORD); entry.pack(fill=tk.X, padx=12)
        service = ConversationService(self.context.database, ApprovedFixRegistry(), self.context.settings.disk_free_threshold_percent)
        state = {"session": None}
        def append(role, message):
            transcript.configure(state=tk.NORMAL); transcript.insert(tk.END, f"{role}: {message}\n\n"); transcript.see(tk.END); transcript.configure(state=tk.DISABLED)
        def send():
            message = entry.get("1.0", tk.END).strip()
            if not message: return
            entry.delete("1.0", tk.END); append("You", message)
            if state["session"] is None:
                session = service.start(message); state["session"] = session
                append("Offline analysis", f"Likely category: {session.detected_category} ({session.classification_confidence:.0%})")
                append("System", session.follow_up_questions[0] if session.follow_up_questions else "Ready for targeted diagnostics.")
            else:
                send_button.configure(state=tk.DISABLED); append("System", "Running relevant approved diagnostics...")
                def work():
                    session = service.answer_and_diagnose(state["session"], message)
                    state["session"] = session
                    self.root.after(0, complete, session)
                threading.Thread(target=work, daemon=True).start()
        def complete(session):
            for message in session.conversation_messages[-2:]:
                if message.role == "system": append("System", message.content)
            append("Session status", session.final_status.replace("_", " ").title())
            repair_button.configure(state=tk.NORMAL if service.recommended_problem(session.session_id) else tk.DISABLED)
            send_button.configure(state=tk.NORMAL)
        def apply_recommended():
            session = state["session"]; selected = service.recommended_problem(session.session_id) if session else None
            if not selected: return
            workflow = ApprovedFixRegistry().get(selected.recommended_fix_workflow)
            if not workflow or not workflow.executable or any(not selected.parameters.get(name) for name in workflow.required_parameters):
                append("System", "No executable approved repair is available for this finding."); return
            approved = True
            if selected.requires_user_confirmation:
                approved = messagebox.askyesno("Confirm approved repair", f"{selected.recommended_fix_workflow} has {selected.risk_level.value} risk. Proceed?", parent=window)
            if not approved: return
            repair_button.configure(state=tk.DISABLED); append("System", "Executing approved workflow and verifying the result...")
            def repair_work():
                attempts, escalation = AutonomousFixEngine(ApprovedFixRegistry(), self.context.database.save_fix_audit_event).run_with_recovery(selected, approved)
                for attempt in attempts: self.context.database.save_fix_attempt(attempt)
                self.root.after(0, repair_complete, attempts, escalation)
            threading.Thread(target=repair_work, daemon=True).start()
        def repair_complete(attempts, escalation):
            if attempts:
                last = attempts[-1]; append("Verification", f"{last.status.value.replace('_', ' ').title()}: {last.message}")
            if escalation: append("Escalation", escalation.recommended_human_action)
            if state["session"]:
                state["session"].fix_attempts.extend({"attempt_id": item.attempt_id, "workflow": item.fix_id, "status": item.status.value,
                                                       "verification_evidence": [] if item.assessment is None else item.assessment.verification_evidence}
                                                      for item in attempts)
                state["session"].final_status = "escalated" if escalation else attempts[-1].status.value
                if escalation:
                    state["session"].escalation = {"original_symptom": state["session"].user_problem_description,
                                                    "diagnostic_evidence": list(escalation.diagnostic_evidence),
                                                    "fixes_attempted": [item.fix_id for item in escalation.fixes_attempted],
                                                    "verification_results": [None if item.assessment is None else item.assessment.status.value for item in escalation.fixes_attempted],
                                                    "fallback_attempts": [item.fix_id for item in escalation.fixes_attempted[1:]],
                                                    "remaining_symptoms": list(escalation.remaining_symptoms),
                                                    "reason": "Approved attempts exhausted without verified resolution.",
                                                    "recommended_human_action": escalation.recommended_human_action,
                                                    "administrator_required": escalation.administrator_required}
                self.context.database.save_session(state["session"])
        def export_session():
            session = state["session"]
            if not session: append("System", "Start a session before exporting a report."); return
            try:
                reporter = ReportService(self.context.settings.database_path, self.context.settings.reports_directory, self.context.settings.ai_mode)
                path = reporter.export(reporter.build_session_report(session.session_id), format_box.get().lower())
                append("Report", f"Saved {path.name}")
            except Exception as error: append("Report", f"Export failed: {error}")
        send_button = ttk.Button(window, text="Send", command=send); send_button.pack(anchor=tk.E, padx=12, pady=10)
        repair_button = ttk.Button(window, text="Apply Recommended Approved Fix", command=apply_recommended, state=tk.DISABLED); repair_button.pack(anchor=tk.E, padx=12, pady=(0, 10))
        export_bar = ttk.Frame(window); export_bar.pack(fill=tk.X, padx=12, pady=(0, 10))
        ttk.Label(export_bar, text="Export session:").pack(side=tk.LEFT)
        format_box = ttk.Combobox(export_bar, values=("PDF", "CSV", "JSON"), state="readonly", width=8); format_box.set("PDF"); format_box.pack(side=tk.LEFT, padx=6)
        ttk.Button(export_bar, text="Export Report", command=export_session).pack(side=tk.LEFT)
        append("System", "Describe the IT problem. Your text is troubleshooting context only and cannot run commands.")

    def _export_diagnostics(self) -> None:
        if not hasattr(self, "_results") or not self._results:
            self.status.set("Run a diagnostic scan before exporting a diagnostic report.")
            return
        try:
            reporter = ReportService(self.context.settings.database_path, self.context.settings.reports_directory, self.context.settings.ai_mode)
            path = reporter.export(reporter.build_diagnostic_report(self._results[0].scan_id), "pdf")
            self.status.set(f"Diagnostic report saved: {path.name}")
        except Exception as error:
            self.status.set(f"Diagnostic report export failed: {error}")

    def _request_elevation(self) -> None:
        if messagebox.askyesno("Administrator mode", "Restart with administrator privileges? Only administrator-required repairs need elevation."):
            self.status.set("Elevation request sent. Close this standard-mode window if the elevated copy opens.") if relaunch_as_administrator() else self.status.set("Windows could not start an elevated copy.")

    def _refresh_dashboard(self) -> None:
        summary = self.context.database.dashboard_summary()
        for key, value in summary.items(): self.card_vars[key].set(str(value))

    def _open_demo(self) -> None:
        window = tk.Toplevel(self.root); window.title("AI System Diagnostic - Simulated Demo Mode"); window.geometry("620x360")
        ttk.Label(window, text="SIMULATED DEMO MODE - no real diagnostics or repairs are performed", foreground="firebrick", font=("Segoe UI", 11, "bold")).pack(padx=15, pady=15)
        scenario = tk.StringVar(value=DemoService.SCENARIOS[0]); ttk.Combobox(window, values=DemoService.SCENARIOS, textvariable=scenario, state="readonly", width=38).pack(pady=6)
        output = tk.Text(window, height=12, wrap=tk.WORD, state=tk.DISABLED); output.pack(fill=tk.BOTH, expand=True, padx=15, pady=8)
        def run_demo():
            result = DemoService(ApprovedFixRegistry()).run(scenario.get())
            reporter = ReportService(self.context.settings.database_path, self.context.settings.reports_directory, "offline_only")
            report_path = reporter.export(reporter.build_demo_report(result), "pdf")
            payload = {"simulation": True, "scenario": result["scenario"], "problems": [item.likely_cause for item in result["problems"]], "attempts": [item.status.value for item in result["attempts"]], "escalated": bool(result["escalation"]), "report": report_path.name}
            output.configure(state=tk.NORMAL); output.delete("1.0", tk.END); output.insert("1.0", json.dumps(payload, indent=2)); output.configure(state=tk.DISABLED)
        ttk.Button(window, text="Run Simulated Scenario and Export Report", command=run_demo).pack(pady=8)

    def _show_about(self) -> None:
        messagebox.showinfo("About AI System Diagnostic", "AI System Diagnostic\nPortable Autonomous AI-Powered IT Troubleshooting & Self-Healing Agent\n\nVersion 0.10.0\n\nOffline diagnostics, controlled approved repairs, verification, privacy modes, portable storage, and reporting.\n\nAutomated fixes are limited to approved workflows; AI cannot execute arbitrary commands.")

    def _scan_failed(self, error: str) -> None:
        self.status.set(f"Scan failed safely: {error}")
        self.scan_button.configure(state=tk.NORMAL)

    def _show_details(self, _event: object) -> None:
        selection = self.tree.selection()
        if not selection or not hasattr(self, "_results"):
            return
        result = self._results[self.tree.index(selection[0])]
        content = json.dumps({"scan_id": result.scan_id, "collected_at": result.collected_at.isoformat(), "details": result.details,
                              "recommendations": result.recommendations}, indent=2, default=str)
        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", content)
        self.detail_text.configure(state=tk.DISABLED)

    def run(self) -> None:
        self.root.mainloop()
