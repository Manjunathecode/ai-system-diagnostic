"""Application entry point for AI System Diagnostic."""
from __future__ import annotations

import sys
import json


def _configure_import_path():
    from core.paths import application_root
    root = application_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def main() -> int:
    root = _configure_import_path()
    from app.bootstrap import bootstrap_application
    context = bootstrap_application(root)
    if "--portable-health-check" in sys.argv:
        print(json.dumps({"application_path": str(context.portable_health.application_path), "writable": context.portable_health.writable,
                          "administrator": context.portable_health.administrator, "free_bytes": context.portable_health.free_bytes}))
        return 0
    if "--portable-report-smoke-test" in sys.argv:
        from reports.report_service import ReportService
        service = ReportService(context.settings.database_path, context.settings.reports_directory, context.settings.ai_mode)
        report = service.build_diagnostic_report()
        print(service.export(report, "pdf"))
        return 0
    if "--portable-diagnostic-smoke-test" in sys.argv:
        from diagnostics.windows_diagnostics import WindowsDiagnosticEngine
        results = WindowsDiagnosticEngine().run_full_scan()
        context.database.save_diagnostic_results(results)
        output = context.settings.data_directory / "portable_diagnostic_smoke.json"
        output.write_text(json.dumps({
            "generated_at": results[0].collected_at.isoformat() if results else None,
            "findings": len(results),
            "statuses": {status: sum(item.status.value == status for item in results)
                         for status in ("passed", "warning", "failed", "not_run")},
            "repairs_executed": 0,
        }, indent=2), encoding="utf-8")
        return 0
    if "--legacy-ui" in sys.argv:
        from ui.desktop_app import DesktopApplication
        DesktopApplication(context).run()
        return 0
    from ui.qt_app import run_qt_application
    screenshot_path = None
    if "--capture-ui" in sys.argv:
        position = sys.argv.index("--capture-ui")
        if position + 1 >= len(sys.argv):
            raise ValueError("--capture-ui requires an output PNG path")
        screenshot_path = sys.argv[position + 1]
    initial_page = 0
    if "--capture-page" in sys.argv:
        page_position = sys.argv.index("--capture-page")
        if page_position + 1 >= len(sys.argv):
            raise ValueError("--capture-page requires a navigation index")
        initial_page = int(sys.argv[page_position + 1])
    demo_scenario = None
    if "--capture-demo" in sys.argv:
        demo_position = sys.argv.index("--capture-demo")
        if demo_position + 1 >= len(sys.argv):
            raise ValueError("--capture-demo requires a scenario name")
        demo_scenario = sys.argv[demo_position + 1]
    return run_qt_application(
        context,
        smoke_test="--qt-smoke-test" in sys.argv,
        screenshot_path=screenshot_path,
        initial_page=initial_page,
        demo_scenario=demo_scenario,
    )


if __name__ == "__main__":
    raise SystemExit(main())
