"""Structured hand-off when bounded approved recovery cannot resolve a problem."""
from __future__ import annotations

from dataclasses import dataclass

from models.fix_result import FixExecutionResult
from models.problem import DetectedProblem


@dataclass(frozen=True)
class EscalationResult:
    problem: DetectedProblem
    diagnostic_evidence: tuple[str, ...]
    fixes_attempted: tuple[FixExecutionResult, ...]
    remaining_symptoms: tuple[str, ...]
    recommended_human_action: str
    administrator_required: bool
