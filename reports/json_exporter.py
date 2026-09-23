"""JSON report export."""
from __future__ import annotations

import json
from pathlib import Path


def export_json(report: dict, destination: Path) -> Path:
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return destination

