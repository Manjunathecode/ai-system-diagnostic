"""Portable-media first-run validation with no system modifications."""
from __future__ import annotations
import shutil
from dataclasses import dataclass
from pathlib import Path
from core.privileges import is_administrator

@dataclass(frozen=True)
class PortableHealth:
    application_path: Path
    writable: bool
    free_bytes: int
    administrator: bool
    message: str

def validate_portable_environment(root: Path, directories: tuple[Path, ...]) -> PortableHealth:
    try:
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".write_probe"
            probe.write_text("ok", encoding="ascii")
            probe.unlink()
        free = shutil.disk_usage(root).free
        return PortableHealth(root, True, free, is_administrator(), "Portable environment is writable and ready.")
    except OSError as error:
        return PortableHealth(root, False, 0, is_administrator(), f"Portable media is not writable: {error}")
