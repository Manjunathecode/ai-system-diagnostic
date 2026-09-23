"""Environment-first settings with portable defaults beside the executable."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from core.paths import runtime_directories


VALID_AI_MODES = ("offline_only", "hybrid_ai", "ai_disabled")


def _boolean(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _path(root: Path, value: str | None, fallback: Path) -> Path:
    candidate = Path(value) if value else fallback
    return candidate if candidate.is_absolute() else root / candidate


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    data_directory: Path
    logs_directory: Path
    reports_directory: Path
    config_directory: Path
    knowledge_directory: Path
    database_path: Path
    online_ai_enabled: bool = False
    disk_free_threshold_percent: float = 10.0
    ai_mode: str = "offline_only"
    ai_provider: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None
    ai_timeout_seconds: int = 15
    auto_fix_low_risk: bool = False
    reduce_motion: bool = False


def _portable_preferences(config_directory: Path) -> dict:
    path = config_directory / "portable_settings.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def load_settings(project_root: Path) -> AppSettings:
    root = Path(project_root).resolve()
    defaults = runtime_directories(root)
    data = _path(root, os.getenv("AISD_DATA_DIR"), defaults["data"])
    logs = _path(root, os.getenv("AISD_LOGS_DIR"), defaults["logs"])
    reports = _path(root, os.getenv("AISD_REPORTS_DIR"), defaults["reports"])
    config = _path(root, os.getenv("AISD_CONFIG_DIR"), defaults["config"])
    knowledge = _path(root, os.getenv("AISD_KNOWLEDGE_DIR"), defaults["knowledge"])
    database = _path(root, os.getenv("AISD_DATABASE_PATH"), data / "ai_system_diagnostic.db")
    preferences = _portable_preferences(config)
    mode = os.getenv("AISD_AI_MODE", str(preferences.get("privacy_mode", "offline_only"))).strip().lower()
    if mode not in VALID_AI_MODES:
        mode = "offline_only"
    return AppSettings(
        project_root=root,
        data_directory=data,
        logs_directory=logs,
        reports_directory=reports,
        config_directory=config,
        knowledge_directory=knowledge,
        database_path=database,
        online_ai_enabled=_boolean(os.getenv("AISD_ONLINE_AI_ENABLED")),
        disk_free_threshold_percent=float(os.getenv("AISD_DISK_FREE_THRESHOLD_PERCENT", "10")),
        ai_mode=mode,
        ai_provider=os.getenv("AISD_AI_PROVIDER") or None,
        ai_api_key=os.getenv("AISD_AI_API_KEY") or None,
        ai_model=os.getenv("AISD_AI_MODEL") or None,
        ai_timeout_seconds=int(os.getenv("AISD_AI_TIMEOUT_SECONDS", "15")),
        auto_fix_low_risk=bool(preferences.get("auto_fix_low_risk", False)),
        reduce_motion=bool(preferences.get("reduce_motion", False)),
    )


def with_runtime_preferences(settings: AppSettings, **changes) -> AppSettings:
    """Return a new immutable settings value after validating UI-controlled fields."""
    if "ai_mode" in changes and changes["ai_mode"] not in VALID_AI_MODES:
        raise ValueError("Unsupported privacy mode")
    return replace(settings, **changes)
