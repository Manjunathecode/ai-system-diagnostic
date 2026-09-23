"""Non-destructive startup checks."""
from __future__ import annotations

from config.settings import AppSettings
import json


def validate_startup(settings: AppSettings) -> list[str]:
    warnings: list[str] = []
    for directory in (settings.data_directory, settings.logs_directory, settings.reports_directory, settings.config_directory):
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise RuntimeError(f"Required application path is not a directory: {directory}")
    if not settings.project_root.exists():
        raise RuntimeError("Application root could not be located.")
    configuration = settings.config_directory / "portable_settings.json"
    if not configuration.exists():
        configuration.write_text(json.dumps({"portable_mode": True, "privacy_mode": settings.ai_mode, "notes": "Environment variables override portable defaults. Never store API keys here."}, indent=2), encoding="utf-8")
    return warnings
