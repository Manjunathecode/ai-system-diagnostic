"""Central product identity used by Python, QML, reports, and packaging."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Branding:
    app_name: str = "AI System Diagnostic"
    app_short_name: str = "AI Diagnostic"
    app_tagline: str = "Portable. Private. In your control."
    app_version: str = "0.11.0"
    app_logo: str = "assets/app-icon.png"
    app_icon: str = "assets/app-icon.ico"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


BRANDING = Branding()
APP_NAME = BRANDING.app_name
APP_SHORT_NAME = BRANDING.app_short_name
APP_TAGLINE = BRANDING.app_tagline
APP_VERSION = BRANDING.app_version
APP_LOGO = BRANDING.app_logo
APP_ICON = BRANDING.app_icon


def resolve_brand_asset(project_root: Path, configured: str) -> str:
    """Return a usable local asset path or an empty value when none is configured."""
    if not configured:
        return ""
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return str(candidate) if candidate.exists() else ""
