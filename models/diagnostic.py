"""Diagnostic result domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DiagnosticStatus(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    NOT_RUN = "not_run"
    PERMISSION_REQUIRED = "permission_required"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class DiagnosticResult:
    scan_id: str
    category: str
    name: str
    status: DiagnosticStatus
    severity: Severity
    summary: str
    collected_at: datetime
    details: dict[str, Any] = field(default_factory=dict)
    recommendations: tuple[str, ...] = ()
