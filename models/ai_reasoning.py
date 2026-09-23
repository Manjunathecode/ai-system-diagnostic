"""Strict, non-executable structured AI reasoning contract."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class AIRecommendation:
    issue_summary: str
    likely_causes: tuple[str, ...]
    diagnostic_reasoning: str
    recommended_workflow_id: str | None
    confidence: float
    requires_more_information: bool
    follow_up_questions: tuple[str, ...]
    escalation_recommendation: str | None

@dataclass(frozen=True)
class HybridDecision:
    problem_id: str
    workflow_id: str | None
    source: str
    explanation: str
    confidence: float
    follow_up_questions: tuple[str, ...] = ()
    rejected_reason: str | None = None
