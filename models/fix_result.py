"""Auditable outcome of one approved repair attempt."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FixStatus(str, Enum):
    PRE_CHECK_FAILED = "pre_check_failed"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    FIXING = "fixing"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    FAILED = "failed"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class FixExecutionResult:
    attempt_id: str
    problem_id: str
    fix_id: str
    status: FixStatus
    started_at: datetime
    completed_at: datetime
    message: str
    audit_events: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    before_snapshot: dict[str, Any] = field(default_factory=dict)
    after_snapshot: dict[str, Any] = field(default_factory=dict)
    assessment: "FixAssessment | None" = None
    parameters: dict[str, Any] = field(default_factory=dict)
    execution_succeeded: bool = False
    execution_details: dict[str, Any] = field(default_factory=dict)


class AssessmentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"


@dataclass(frozen=True)
class FixAssessment:
    status: AssessmentStatus
    verification_evidence: tuple[str, ...]
    before_after_comparison: dict[str, Any]
    confidence_score: float
    unresolved_symptoms: tuple[str, ...] = ()
