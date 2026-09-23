"""Coordinates local chat context, targeted diagnostics, and existing decision logic."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from decision_engine.issue_classifier import OfflineIssueClassifier
from decision_engine.offline_rules import OfflineDecisionEngine
from diagnostics.windows_diagnostics import WindowsDiagnosticEngine
from models.session import ConversationMessage, TroubleshootingSession

class ConversationService:
    def __init__(self, database, registry, disk_threshold: float) -> None:
        self.database, self.registry, self.disk_threshold = database, registry, disk_threshold
        self.classifier = OfflineIssueClassifier()
        self._active_problems = {}
        self._active_results = {}

    def start(self, description: str) -> TroubleshootingSession:
        now = datetime.now(timezone.utc); classification = self.classifier.classify(description)
        session = TroubleshootingSession(str(uuid.uuid4()), now, now, description, classification.category, classification.confidence)
        session.conversation_messages = [ConversationMessage("user", description, now, "user"),
                                         ConversationMessage("system", f"Offline analysis: likely category is {classification.category} ({classification.confidence:.0%} confidence).", now, "offline_analysis")]
        session.follow_up_questions = list(classification.follow_up_questions)
        session.pending_questions = list(classification.follow_up_questions)
        session.candidate_categories = list(classification.candidate_categories)
        session.final_status = "awaiting_follow_up" if classification.category == "Unknown" or classification.follow_up_questions else "ready_for_diagnostics"
        self.database.save_session(session); return session

    def answer_and_diagnose(self, session: TroubleshootingSession, answer: str, progress=None) -> TroubleshootingSession:
        now = datetime.now(timezone.utc)
        current_question = session.pending_questions[0] if session.pending_questions else ""
        if current_question:
            session.user_answers.append({"question": current_question, "answer": answer})
            session.pending_questions.pop(0)
        session.conversation_messages.append(ConversationMessage("user", answer, now, "answer"))
        if session.detected_category == "System Health" and current_question and self._declined(answer):
            session.final_status = "cancelled"
            session.conversation_messages.append(ConversationMessage("system", "System health scan cancelled. No diagnostics or repairs were started.", now, "diagnostic"))
            session.updated_at = now
            self._active_results[session.session_id] = []
            self._active_problems[session.session_id] = []
            self.database.save_session(session)
            return session
        if session.detected_category == "Unknown":
            refined = self.classifier.classify(answer)
            if refined.category == "Unknown":
                refined = self.classifier.classify(f"{session.user_problem_description} {answer}")
            session.detected_category, session.classification_confidence = refined.category, refined.confidence
            session.candidate_categories = list(refined.candidate_categories)
            if refined.category != "Unknown":
                session.conversation_messages.append(ConversationMessage("system", f"Your follow-up clarified the category as {refined.category}.", now, "offline_analysis"))
        if session.detected_category == "Unknown":
            refined_question = self.classifier.classify(f"{session.user_problem_description} {answer}").follow_up_questions[0]
            session.pending_questions = [refined_question]
            if refined_question not in session.follow_up_questions:
                session.follow_up_questions.append(refined_question)
            session.final_status = "needs_more_information"; session.conversation_messages.append(ConversationMessage("system", "The issue is still ambiguous. No diagnostics or repair were started.", now, "offline_analysis")); self.database.save_session(session); return session
        session.conversation_messages.append(ConversationMessage("system", "Starting relevant approved diagnostics.", now, "diagnostic"))
        results = WindowsDiagnosticEngine(self.disk_threshold).run_targeted(session.detected_category, progress)
        if results:
            self.database.save_diagnostic_results(results)
        scan_id = results[0].scan_id if results else None
        session.diagnostic_runs.append({"timestamp": now.isoformat(), "category": session.detected_category, "finding_count": len(results), "scan_id": scan_id})
        session.diagnostic_findings = [{"scan_id": item.scan_id, "category": item.category, "name": item.name,
                                        "status": item.status.value, "severity": item.severity.value,
                                        "summary": item.summary, "collected_at": item.collected_at.isoformat(),
                                        "details": item.details} for item in results]
        problems = OfflineDecisionEngine(self.registry, self.disk_threshold).analyze(results)
        relevant = problems
        session.detected_problems = [{"problem_id": item.problem_id, "category": item.category, "severity": item.severity.value,
                                      "confidence": item.confidence, "cause": item.likely_cause, "evidence": item.evidence,
                                      "workflow": item.recommended_fix_workflow, "risk": item.risk_level.value,
                                      "requires_administrator": item.requires_administrator,
                                      "requires_confirmation": item.requires_user_confirmation,
                                      "parameters": item.parameters} for item in relevant]
        self._active_results[session.session_id] = results
        self._active_problems[session.session_id] = relevant
        session.recommended_workflows = [item.recommended_fix_workflow for item in relevant]
        if relevant:
            item = relevant[0]; session.conversation_messages.append(ConversationMessage("system", f"Finding: {item.likely_cause} Evidence: {'; '.join(item.evidence)} Recommended approved workflow: {item.recommended_fix_workflow}.", now, "recommendation")); session.final_status = "repair_recommended"
        else:
            complete = bool(results) and all(item.status.value == "passed" for item in results)
            message = ("The completed checks found no supported issue. This does not rule out intermittent faults. Start a new issue with an exact symptom if the problem continues."
                       if complete else "Some checks found warnings or could not finish, but no supported automatic repair was identified. Review the diagnostic evidence for manual investigation.")
            session.conversation_messages.append(ConversationMessage("system", message, now, "diagnostic")); session.final_status = "inconclusive"
        session.updated_at = datetime.now(timezone.utc); self.database.save_session(session); return session

    def recommended_problem(self, session_id: str):
        problems = self._active_problems.get(session_id, [])
        return problems[0] if problems else None

    def problems(self, session_id: str):
        return list(self._active_problems.get(session_id, []))

    def diagnostic_results(self, session_id: str):
        return list(self._active_results.get(session_id, []))

    @staticmethod
    def _declined(answer: str) -> bool:
        normalized = answer.strip().lower()
        return normalized in {"no", "n", "nope", "cancel", "stop", "do not", "don't", "not now"} or normalized.startswith("no ")
