"""Run safe real-machine validation without invoking any repair workflow."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bootstrap import bootstrap_application
from services.ui_facade import UIFacade


def main() -> int:
    facade = UIFacade(bootstrap_application(ROOT))
    payload = facade.full_scan()
    statuses = {}
    for finding in payload["diagnostics"]:
        statuses[finding["status"]] = statuses.get(finding["status"], 0) + 1
    print(json.dumps({"scan_id": payload["scanId"], "findings": len(payload["diagnostics"]),
                      "problems": len(payload["problems"]), "statuses": statuses,
                      "repairs_executed": 0, "mode": "read_only"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
