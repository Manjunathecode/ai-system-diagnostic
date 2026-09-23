# Phase 11 UI architecture

AI System Diagnostic uses a PySide6 and Qt Quick presentation layer over the existing Python backend.

## Dependency direction

```text
QML pages and reusable components
              ↓ signals and properties
AppController (QObject)
              ↓ asynchronous calls and view mapping
UIFacade (plain Python)
              ↓ approved service APIs
Diagnostic, decision, repair, verification, reporting, and SQLite services
```

QML never imports system collectors, SQLite, subprocess helpers, or repair executors. `AppController` exposes presentation-safe properties and slots. Potentially slow operations run through `QThreadPool`; completion signals update UI state on the Qt event loop.

`UIFacade` is the testable presentation boundary. It maps typed diagnostics, problems, repairs, sessions, and reports into dictionaries suitable for QML while preserving real status, evidence, and unavailable fields.

## Navigation

`Main.qml` provides a persistent sidebar and a `StackLayout` containing ten product areas: Dashboard, AI Troubleshoot, System Scan, Issues, Repair Center, System Health, Reports, Demo Lab, Settings, and About.

Shared components live under `ui/qml/components`, and visual values are centralized in `DesignTokens.qml`. Product naming and assets are centralized in `config/branding.py`.

## State and persistence

At startup, the facade restores the latest stored diagnostic evidence and derives current problem state with the offline decision engine. Scans and repairs persist through the existing `Database` API. Reports rebuild their source models from SQLite instead of relying on transient QML state.

## Safety boundary

The UI can request only high-level operations such as scan, diagnose, execute a selected problem, run an isolated demo, export a report, or save preferences. The backend retains all authority for workflow allow-list validation, risk classification, confirmation, elevation, pre-check, execution, verification, fallback limits, audit logging, and escalation.

User-entered text is never evaluated as code. Hybrid AI output is structured and cannot bypass the Approved Fix Registry.

## Legacy migration

The Tkinter UI remains in `ui/desktop_app.py` and can be launched with `python main.py --legacy-ui`. The Qt interface is the default and uses the same backend services through the facade. Keeping the legacy interface provides a rollback path while packaged field validation continues.
