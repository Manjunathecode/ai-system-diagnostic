"""Portable runtime paths for source, PyInstaller one-file, and one-folder launches."""
from __future__ import annotations
import sys
from pathlib import Path

def application_root() -> Path:
    """Return the durable package directory, never PyInstaller's temporary extraction directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]

def runtime_directories(root: Path | None = None) -> dict[str, Path]:
    base = root or application_root()
    return {"root": base, "data": base / "data", "logs": base / "logs", "reports": base / "reports", "config": base / "config", "knowledge": base / "knowledge"}
