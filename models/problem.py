"""Structured offline problem classification models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.diagnostic import Severity
from models.fix_workflow import WorkflowRisk


@dataclass(frozen=True)
class DetectedProblem:
    problem_id: str
    category: str
    severity: Severity
    confidence: float
    evidence: tuple[str, ...]
    likely_cause: str
    recommended_fix_workflow: str
    requires_administrator: bool
    requires_user_confirmation: bool
    risk_level: WorkflowRisk
    parameters: dict[str, Any] = field(default_factory=dict)
