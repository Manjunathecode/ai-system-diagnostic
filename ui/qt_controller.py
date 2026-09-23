"""Qt controller and background task bridge for the QML presentation layer."""
from __future__ import annotations

import os
from typing import Any, Callable

from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, Signal, Slot, QUrl, QCoreApplication
from PySide6.QtGui import QDesktopServices

from core.privileges import relaunch_as_administrator
from services.demo_service import DemoService
from services.ui_facade import UIFacade


class WorkerSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int)


class BackgroundWorker(QRunnable):
    """Run one backend operation away from the UI thread."""
    def __init__(self, operation: Callable, *args, with_progress: bool = False) -> None:
        super().__init__()
        self.operation, self.args, self.with_progress = operation, args, with_progress
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            if self.with_progress:
                result = self.operation(*self.args, progress=lambda label, value: self.signals.progress.emit(label, value))
            else:
                result = self.operation(*self.args)
            self.signals.completed.emit(result)
        except Exception as error:  # surfaced in the product; the worker must never terminate Qt
            self.signals.failed.emit(str(error))


class AppController(QObject):
    stateChanged = Signal()
    pageChanged = Signal()
    confirmationRequested = Signal("QVariantMap")
    elevationRequested = Signal("QVariantMap")
    notification = Signal(str, str)

    def __init__(self, facade: UIFacade, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.facade = facade
        self.pool = QThreadPool.globalInstance()
        self._page = 0
        self._busy = False
        self._status = "Ready. No changes will be made without an approved workflow."
        self._progress = 0
        self._progress_label = "Not started"
        self._dashboard = facade.dashboard()
        self._diagnostics: list[dict] = [facade.diagnostic_view(item) for item in facade.results]
        self._problems: list[dict] = [facade.problem_view(item) for item in facade.problems]
        self._scan_sections = self._build_scan_sections(self._diagnostics) if self._diagnostics else self._empty_scan_sections()
        self._chat_messages: list[dict] = []
        self._session: dict = {}
        self._repair_timeline: list[dict] = []
        self._escalation: dict = {}
        self._reports = facade.report_history()
        self._demo: dict = {}
        self._pending_repair: int | None = None
        self._active_worker: BackgroundWorker | None = None
        self._completion_handler: Callable[[Any], None] | None = None

    def _empty_scan_sections(self) -> list[dict]:
        return [{"name": name, "status": "not_run", "statusLabel": "Not run", "summary": "This diagnostic has not run."} for name in UIFacade.SCAN_SECTIONS]

    def _emit(self) -> None:
        self.stateChanged.emit()

    @Property("QVariantMap", notify=stateChanged)
    def branding(self): return self.facade.branding

    @Property("QVariantMap", notify=stateChanged)
    def dashboard(self): return self._dashboard

    @Property("QVariantList", notify=stateChanged)
    def diagnostics(self): return self._diagnostics

    @Property("QVariantList", notify=stateChanged)
    def problems(self): return self._problems

    @Property("QVariantList", notify=stateChanged)
    def scanSections(self): return self._scan_sections

    @Property("QVariantList", notify=stateChanged)
    def chatMessages(self): return self._chat_messages

    @Property("QVariantMap", notify=stateChanged)
    def session(self): return self._session

    @Property("QVariantList", notify=stateChanged)
    def repairTimeline(self): return self._repair_timeline

    @Property("QVariantMap", notify=stateChanged)
    def escalation(self): return self._escalation

    @Property("QVariantList", notify=stateChanged)
    def reports(self): return self._reports

    @Property("QVariantMap", notify=stateChanged)
    def demoResult(self): return self._demo

    @Property(bool, notify=stateChanged)
    def busy(self): return self._busy

    @Property(int, notify=stateChanged)
    def progress(self): return self._progress

    @Property(str, notify=stateChanged)
    def progressLabel(self): return self._progress_label

    @Property(str, notify=stateChanged)
    def statusMessage(self): return self._status

    @Property(int, notify=pageChanged)
    def currentPage(self): return self._page

    @Property(bool, notify=stateChanged)
    def isAdministrator(self): return self.facade.context.is_administrator

    @Property(bool, notify=stateChanged)
    def portableReady(self): return self.facade.context.portable_health.writable

    @Property(str, notify=stateChanged)
    def privacyMode(self): return self.facade.context.settings.ai_mode

    @Property(bool, notify=stateChanged)
    def autoFixLowRisk(self): return self.facade.context.settings.auto_fix_low_risk

    @Property(bool, notify=stateChanged)
    def reduceMotion(self): return self.facade.context.settings.reduce_motion

    @Property(str, notify=stateChanged)
    def reportsDirectory(self): return str(self.facade.context.settings.reports_directory)

    @Slot(int)
    def navigate(self, index: int) -> None:
        if 0 <= index <= 9 and self._page != index:
            self._page = index
            self.pageChanged.emit()

    def _launch(self, worker: BackgroundWorker, completed: Callable[[Any], None]) -> None:
        self._active_worker = worker
        self._completion_handler = completed
        worker.signals.completed.connect(self._worker_complete)
        worker.signals.failed.connect(self._worker_failed)
        self.pool.start(worker)

    @Slot(object)
    def _worker_complete(self, result: Any) -> None:
        completed = self._completion_handler
        self._active_worker = None
        self._completion_handler = None
        self._busy = False
        try:
            if completed:
                completed(result)
        except Exception as error:
            self._worker_failed(str(error))
        self._emit()

    @Slot(str)
    def _worker_failed(self, message: str) -> None:
        self._active_worker = None
        self._completion_handler = None
        self._busy = False
        self._status = f"Operation failed safely: {message}"
        self.notification.emit("Operation failed", self._status)
        self._emit()

    @Slot()
    def startFullScan(self) -> None:
        if self._busy:
            return
        self._busy, self._progress = True, 0
        self._progress_label = "Preparing approved read-only diagnostics"
        self._status = "Scanning. No repair actions are being performed."
        self._scan_sections = self._empty_scan_sections()
        self._session, self._chat_messages, self._problems = {}, [], []
        self._diagnostics = []
        self._repair_timeline, self._escalation, self._demo = [], {}, {}
        self._emit()
        worker = BackgroundWorker(self.facade.full_scan, with_progress=True)
        worker.signals.progress.connect(self._on_progress)
        self._launch(worker, self._scan_complete)

    @Slot(str, int)
    def _on_progress(self, label: str, value: int) -> None:
        self._progress_label, self._progress = label, value
        section_map = {"System Information": "System", "Cpu Memory Health": "CPU & Memory", "Disk Health": "Storage",
                       "Network Diagnostics": "Network", "Windows Services": "Services", "Printer Diagnostics": "Printer",
                       "Device Diagnostics": "Devices"}
        current = section_map.get(label)
        updated = []
        for item in self._scan_sections:
            copy = dict(item)
            if current and copy["name"] == current:
                copy.update(status="running", statusLabel="Scanning", summary="Collector is running.")
            updated.append(copy)
        self._scan_sections = updated
        self._emit()

    def _scan_complete(self, payload: dict) -> None:
        self._progress, self._progress_label = 100, "Scan complete"
        self._diagnostics, self._problems, self._dashboard = payload["diagnostics"], payload["problems"], payload["dashboard"]
        self._scan_sections = self._build_scan_sections(self._diagnostics)
        attention = sum(item["status"] in {"warning", "failed", "error", "permission_required", "unavailable", "not_run"} for item in self._diagnostics)
        self._status = f"Scan completed with {len(self._diagnostics)} findings; {attention} need attention."
        self.notification.emit("System scan complete", self._status)
        if self.autoFixLowRisk:
            eligible = next((index for index, item in enumerate(self._problems)
                             if item["repairAvailable"] and item["risk"] == "low" and not item["requiresConfirmation"]
                             and (not item["requiresAdministrator"] or self.isAdministrator)), None)
            if eligible is not None:
                self._run_repair(eligible, False)

    def _build_scan_sections(self, diagnostics: list[dict]) -> list[dict]:
        routes = {"System Information": ("System",), "CPU and Memory": ("CPU & Memory",), "Disk Health": ("Storage",),
                  "Network": ("Network", "DNS", "Gateway"), "Windows Services": ("Services",), "Printer": ("Printer",), "Devices": ("Devices",)}
        output = []
        for name in UIFacade.SCAN_SECTIONS:
            matches = [item for item in diagnostics if name in routes.get(item["category"], ())]
            if not matches:
                output.append({"name": name, "status": "not_run", "statusLabel": "Not run", "summary": "No evidence was collected."})
                continue
            status = "failed" if any(item["status"] in {"failed", "error"} for item in matches) else \
                "warning" if any(item["status"] == "warning" for item in matches) else \
                "not_run" if any(item["status"] in {"not_run", "permission_required", "unavailable"} for item in matches) else "passed"
            output.append({"name": name, "status": status, "statusLabel": status.replace("_", " ").title(), "summary": " ".join(item["summary"] for item in matches)})
        return output

    @Slot(str)
    def startTroubleshooting(self, description: str) -> None:
        if self._busy:
            return
        try:
            self._session = self.facade.start_troubleshooting(description)
            self._chat_messages = self._session.get("messages", [])
            self._diagnostics, self._problems = [], []
            self._scan_sections = self._empty_scan_sections()
            self._repair_timeline, self._escalation, self._demo = [], {}, {}
            self._dashboard = self.facade.dashboard()
            self._status = "Answer the follow-up question to choose the relevant diagnostics."
            self._page = 1
            self.pageChanged.emit()
            self._emit()
        except Exception as error:
            self.notification.emit("Cannot start", str(error))

    @Slot()
    def resetTroubleshooting(self) -> None:
        if self._busy:
            return
        self.facade.reset_troubleshooting()
        self._session, self._chat_messages, self._diagnostics, self._problems = {}, [], [], []
        self._repair_timeline, self._escalation, self._demo = [], {}, {}
        self._scan_sections = self._empty_scan_sections()
        self._dashboard = self.facade.dashboard()
        self._status = "Describe a new issue. Previous sessions remain in local history."
        self._emit()

    @Slot(str)
    def continueTroubleshooting(self, answer: str) -> None:
        if self._busy:
            return
        if not answer.strip():
            self.notification.emit("Answer needed", "Enter an answer before continuing.")
            return
        self._busy, self._status = True, "Reviewing your answer and selecting relevant checks."
        self._emit()
        worker = BackgroundWorker(self.facade.continue_troubleshooting, answer, with_progress=True)
        worker.signals.progress.connect(self._on_progress)
        self._launch(worker, self._troubleshooting_complete)

    def _troubleshooting_complete(self, session: dict) -> None:
        self._session, self._chat_messages = session, session.get("messages", [])
        self._diagnostics = [self.facade.diagnostic_view(item) for item in self.facade.results]
        self._problems = [self.facade.problem_view(item) for item in self.facade.problems]
        self._dashboard = self.facade.dashboard()
        self._scan_sections = self._build_scan_sections(self._diagnostics)
        self._status = f"Troubleshooting status: {session.get('statusLabel', 'Updated')}."

    @Slot(int)
    def requestRepair(self, index: int) -> None:
        if self._busy or not 0 <= index < len(self._problems):
            return
        problem = self._problems[index]
        if not problem.get("repairAvailable", False):
            self.notification.emit("Repair unavailable", "This finding has no executable approved workflow with a valid target.")
            return
        if problem["requiresAdministrator"] and not self.isAdministrator:
            self._pending_repair = index
            self.elevationRequested.emit(problem)
            return
        if problem["requiresConfirmation"]:
            self._pending_repair = index
            self.confirmationRequested.emit(problem)
            return
        self._run_repair(index, False)

    @Slot(bool)
    def confirmPendingRepair(self, approved: bool) -> None:
        index, self._pending_repair = self._pending_repair, None
        if approved and index is not None:
            self._run_repair(index, True)
        else:
            self._status = "Repair cancelled. No changes were made."
            self._emit()

    def _run_repair(self, index: int, confirmed: bool) -> None:
        if self._busy:
            return
        self._busy, self._status = True, "Running approved pre-check."
        self._page = 4
        self.pageChanged.emit()
        self._emit()
        self._launch(BackgroundWorker(self.facade.execute_problem, index, confirmed), self._repair_complete)

    def _repair_complete(self, payload: dict) -> None:
        self._repair_timeline = payload["attempts"]
        self._escalation = payload.get("escalation", {})
        self._dashboard = payload["dashboard"]
        self._session = self.facade.session_view()
        self._chat_messages = self._session.get("messages", [])
        attempted = {item["problemId"] for item in self._repair_timeline}
        self._problems = [dict(item, repairAvailable=False,
                               repairUnavailableReason="A repair attempt was recorded. Run a new scan to reassess the current state.")
                          if item["problemId"] in attempted else item for item in self._problems]
        if payload["escalated"]:
            self._status = "Repair could not be verified as resolved and was escalated."
        elif self._repair_timeline:
            self._status = f"Final verified result: {self._repair_timeline[-1]['statusLabel']}."
        self.notification.emit("Repair workflow complete", self._status)

    @Slot(str)
    def runDemo(self, scenario: str) -> None:
        if self._busy:
            return
        self._busy, self._status = True, "Running isolated simulated scenario. No real repair is being performed."
        self._emit()
        self._launch(BackgroundWorker(self.facade.run_demo, scenario), self._demo_complete)

    def _demo_complete(self, payload: dict) -> None:
        self._demo = payload
        self._status = "Demo completed with simulated evidence only."

    @Slot(str, str)
    def exportReport(self, report_kind: str, output_format: str) -> None:
        if self._busy:
            return
        self._busy, self._status = True, "Generating a sanitized evidence report."
        self._emit()
        self._launch(BackgroundWorker(self.facade.export_report, report_kind, output_format), self._report_complete)

    def _report_complete(self, path) -> None:
        self._reports = self.facade.report_history()
        self._status = f"Report saved: {path.name}"
        self.notification.emit("Report generated", self._status)

    @Slot()
    def refreshReports(self) -> None:
        self._reports = self.facade.report_history()
        self._emit()

    @Slot()
    def openReportsFolder(self) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(self.reportsDirectory)):
            self.notification.emit("Cannot open folder", "Windows could not open the report folder.")

    @Slot(str)
    def openReport(self, path: str) -> None:
        if path and os.path.isfile(path):
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
                self.notification.emit("Cannot open report", "Windows has no available application for this report format.")
        else:
            self.notification.emit("Report missing", "This report file is no longer available. Refresh the report history.")

    @Slot(str, bool, bool)
    def savePreferences(self, privacy_mode: str, auto_fix: bool, reduce_motion: bool) -> None:
        try:
            self.facade.update_preferences(privacy_mode, auto_fix, reduce_motion)
            self._dashboard = self.facade.dashboard()
            self._status = "Settings saved to portable configuration."
            self._emit()
        except Exception as error:
            self.notification.emit("Settings not saved", str(error))

    @Slot()
    def relaunchElevated(self) -> None:
        self._pending_repair = None
        if relaunch_as_administrator():
            QCoreApplication.quit()
        else:
            self.notification.emit("Administrator mode", "Windows could not start an elevated copy.")
