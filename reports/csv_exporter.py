"""Lossless path/value CSV export for nested evidence."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _rows(value: Any, path: str = "report"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _rows(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _rows(item, f"{path}[{index}]")
    else:
        yield path, json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value


def export_csv(report: dict, destination: Path) -> Path:
    with destination.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("field", "value"))
        writer.writerows(_rows(report))
    return destination

