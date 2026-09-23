"""Startup validation and application dependency composition."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.settings import AppSettings, load_settings
from core.privileges import is_administrator
from core.startup_validation import validate_startup
from core.portable_health import PortableHealth, validate_portable_environment
from services.database import Database
from utils.logging_config import configure_logging


@dataclass(frozen=True)
class ApplicationContext:
    settings: AppSettings
    database: Database
    is_administrator: bool
    startup_warnings: tuple[str, ...]
    portable_health: PortableHealth


def bootstrap_application(project_root: Path) -> ApplicationContext:
    settings = load_settings(project_root)
    warnings = validate_startup(settings)
    health = validate_portable_environment(settings.project_root, (settings.data_directory, settings.logs_directory, settings.reports_directory, settings.config_directory))
    if not health.writable:
        raise RuntimeError(health.message)
    logger = configure_logging(settings.logs_directory)
    database = Database(settings.database_path)
    database.initialize()
    admin = is_administrator()
    logger.info("Application startup complete. Administrator privileges: %s", admin)
    return ApplicationContext(settings, database, admin, tuple(warnings), health)
