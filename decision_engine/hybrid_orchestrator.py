"""Privacy-preserving AI assist that cannot bypass offline safety decisions."""
from __future__ import annotations
from models.ai_reasoning import AIRecommendation, HybridDecision
from models.problem import DetectedProblem

class HybridDecisionOrchestrator:
    _FORBIDDEN = ("powershell", "cmd.exe", "bash", "python ", "reg add", "rm -", "del /", "curl ")
    def __init__(self, registry, provider=None, mode="offline_only", api_key=None, audit=None):
        self.registry, self.provider, self.mode, self.api_key, self.audit = registry, provider, mode, api_key, audit

    def sanitize_context(self, problem: DetectedProblem, findings: list, history: list[dict] | None = None) -> dict:
        related = [item for item in findings if item.category in {problem.category, "Network", "Printer", "Windows Services", "Disk Health"}]
        safe = []
        for item in related:
            details = {k: v for k, v in item.details.items() if isinstance(v, (str, int, float, bool)) and k not in {"computer_name", "user_name", "path", "ip_address"}}
            safe.append({"category": item.category, "finding": item.name, "status": item.status.value, "severity": item.severity.value, "details": details})
        return {"problem": {"category": problem.category, "severity": problem.severity.value, "evidence": problem.evidence, "likely_cause": problem.likely_cause},
                "diagnostics": safe, "previous_outcomes": (history or [])[-3:]}

    def decide(self, problems: list[DetectedProblem], findings: list, history: list[dict] | None = None) -> list[HybridDecision]:
        output = []
        for problem in problems:
            if problem.confidence >= 0.9:
                output.append(HybridDecision(problem.problem_id, problem.recommended_fix_workflow, "offline_deterministic", "High-confidence deterministic rule retained.", problem.confidence)); continue
            if self.mode != "hybrid_ai" or not self.provider or not self.api_key:
                output.append(HybridDecision(problem.problem_id, problem.recommended_fix_workflow, "offline_fallback", "Offline intelligence used; AI is unavailable or disabled.", problem.confidence)); continue
            try:
                recommendation = self._parse(self.provider.analyze_issue(self.sanitize_context(problem, findings, history)))
                rejection = self._validate(recommendation, problem)
                if rejection:
                    self._audit("ai_rejected", rejection)
                    output.append(HybridDecision(problem.problem_id, problem.recommended_fix_workflow, "offline_fallback", "AI recommendation rejected; offline decision retained.", problem.confidence, rejection_reason=rejection))
                else:
                    output.append(HybridDecision(problem.problem_id, recommendation.recommended_workflow_id, "ai_assisted", recommendation.diagnostic_reasoning, recommendation.confidence, recommendation.follow_up_questions))
            except Exception as error:
                self._audit("ai_failure", type(error).__name__)
                output.append(HybridDecision(problem.problem_id, problem.recommended_fix_workflow, "offline_fallback", "AI provider unavailable; offline decision retained.", problem.confidence))
        return output

    def _parse(self, raw: dict) -> AIRecommendation:
        required = {"issue_summary", "likely_causes", "diagnostic_reasoning", "recommended_workflow_id", "confidence", "requires_more_information", "follow_up_questions", "escalation_recommendation"}
        if not isinstance(raw, dict) or set(raw) != required or not isinstance(raw["confidence"], (int, float)) or not 0 <= raw["confidence"] <= 1: raise ValueError("Malformed AI response")
        if not all(isinstance(raw[key], str) or raw[key] is None for key in ("issue_summary", "diagnostic_reasoning", "recommended_workflow_id", "escalation_recommendation")): raise ValueError("Malformed AI response")
        if not isinstance(raw["likely_causes"], list) or not isinstance(raw["follow_up_questions"], list): raise ValueError("Malformed AI response")
        return AIRecommendation(raw["issue_summary"], tuple(raw["likely_causes"]), raw["diagnostic_reasoning"], raw["recommended_workflow_id"], float(raw["confidence"]), raw["requires_more_information"], tuple(raw["follow_up_questions"]), raw["escalation_recommendation"])

    def _validate(self, rec: AIRecommendation, problem: DetectedProblem) -> str | None:
        text = " ".join(str(x) for x in (rec.issue_summary, rec.diagnostic_reasoning, *rec.likely_causes, *rec.follow_up_questions, rec.escalation_recommendation) if x).lower()
        if any(token in text for token in self._FORBIDDEN): return "AI response contained prohibited command-like text."
        workflow = self.registry.get(rec.recommended_workflow_id) if rec.recommended_workflow_id else None
        if workflow is None: return "AI returned an unknown or missing workflow."
        if problem.category not in workflow.supported_problem_types: return "AI workflow is not compatible with the detected problem."
        return None

    def _audit(self, stage, message):
        if self.audit: self.audit({"stage": stage, "message": message})
