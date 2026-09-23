"""Approved, auditable fix workflow domain models.

Executable workflows are implemented only by the controlled fix engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WorkflowRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class FixStep:
    step_id: str
    title: str
    description: str
    requires_administrator: bool = False


@dataclass(frozen=True)
class FixWorkflow:
    workflow_id: str
    title: str
    description: str
    supported_problem_types: tuple[str, ...]
    risk: WorkflowRisk
    steps: tuple[FixStep, ...] = field(default_factory=tuple)
    requires_administrator: bool = False
    pre_check: str = ""
    execute: str = ""
    verify: str = ""
    rollback_if_available: str | None = None
    audit_log: bool = True
    enabled: bool = False
    executable: bool = True
    required_parameters: tuple[str, ...] = field(default_factory=tuple)
