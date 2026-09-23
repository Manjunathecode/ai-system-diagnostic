"""Structured report metadata shared by export formats."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReportMetadata:
    report_id: str
    report_type: str
    generated_at: datetime
    source_id: str
    application_name: str
    application_version: str
    privacy_mode: str

