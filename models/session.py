"""Local-only conversational troubleshooting session state."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass
class ConversationMessage:
    role: str
    content: str
    created_at: datetime
    kind: str = "conversation"

@dataclass
class TroubleshootingSession:
    session_id: str
    created_at: datetime
    updated_at: datetime
    user_problem_description: str
    detected_category: str
    classification_confidence: float
    conversation_messages: list[ConversationMessage] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    pending_questions: list[str] = field(default_factory=list)
    candidate_categories: list[str] = field(default_factory=list)
    user_answers: list[dict[str, str]] = field(default_factory=list)
    diagnostic_runs: list[dict[str, Any]] = field(default_factory=list)
    diagnostic_findings: list[dict[str, Any]] = field(default_factory=list)
    detected_problems: list[dict[str, Any]] = field(default_factory=list)
    recommended_workflows: list[str] = field(default_factory=list)
    fix_attempts: list[dict[str, Any]] = field(default_factory=list)
    final_status: str = "awaiting_context"
    escalation_id: str | None = None
    escalation: dict[str, Any] | None = None
