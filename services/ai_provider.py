"""Replaceable provider boundary. Providers return data only, never executable text."""
from __future__ import annotations
from typing import Protocol

class AIProvider(Protocol):
    def analyze_issue(self, context: dict) -> dict: ...
    def recommend_workflow(self, context: dict) -> dict: ...
    def explain_reasoning(self, context: dict) -> dict: ...

class UnavailableAIProvider:
    """Safe default when no configured provider/API key is available."""
    def analyze_issue(self, _context: dict) -> dict: raise RuntimeError("AI provider is unavailable")
    def recommend_workflow(self, _context: dict) -> dict: raise RuntimeError("AI provider is unavailable")
    def explain_reasoning(self, _context: dict) -> dict: raise RuntimeError("AI provider is unavailable")
