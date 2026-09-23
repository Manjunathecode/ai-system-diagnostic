"""Exercise the shipped QML callbacks, using isolated data and mocked repairs."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, QMetaObject, QPointF, Qt, QUrl, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from pypdf import PdfReader

from app.bootstrap import ApplicationContext
from config.settings import load_settings
from core.portable_health import PortableHealth
from decision_engine.issue_classifier import OfflineIssueClassifier
from diagnostics.windows_diagnostics import WindowsDiagnosticEngine
from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity
from models.fix_result import FixExecutionResult, FixAssessment, FixStatus, AssessmentStatus
from models.session import TroubleshootingSession
from services.database import Database
from services.ui_facade import UIFacade
from reports.report_service import ReportService
from ui.qt_controller import AppController

ROOT = Path(__file__).resolve().parents[1]
QML_ROOT = Path(os.environ.get("AISD_TEST_QML_ROOT", str(ROOT / "ui/qml")))


def context(root):
    settings = load_settings(root)
    for path in (settings.data_directory, settings.logs_directory, settings.reports_directory, settings.config_directory):
        path.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_path)
    db.initialize()
    return ApplicationContext(settings, db, False, (), PortableHealth(root, True, 1, False, "ready"))


def finding(status=DiagnosticStatus.WARNING):
    return DiagnosticResult("isolated-scan", "Disk Health", "Drive capacity", status, Severity.HIGH,
                            "C: has 5% free space.", datetime.now(timezone.utc),
                            {"drives": [{"drive": "C:\\", "free_percent": 5, "free_bytes": 1024**3}]})


class QmlInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QQuickStyle.setStyle("Basic")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.facade = UIFacade(context(Path(self.temp.name)))
        self.controller = AppController(self.facade)
        self.messages = []
        self.previous_handler = qInstallMessageHandler(lambda kind, ctx, message: self.messages.append(message))
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty("controller", self.controller)
        self.engine.load(QUrl.fromLocalFile(str(QML_ROOT / "Main.qml")))
        self.assertTrue(self.engine.rootObjects())
        self.window = self.engine.rootObjects()[0]
        self.pump()

    def pump(self):
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self):
        self.controller.pool.waitForDone(5000)
        self.window.close()
        self.engine.deleteLater()
        self.pump()
        qInstallMessageHandler(self.previous_handler)
        self.temp.cleanup()

    def objects(self):
        seen = set()
        def walk(obj):
            if id(obj) in seen:
                return
            seen.add(id(obj))
            yield obj
            children = list(obj.children())
            if isinstance(obj, QQuickItem):
                children += list(obj.childItems())
            for child in children:
                yield from walk(child)
        return list(walk(self.window))

    def buttons(self, text):
        return [o for o in self.objects() if o.property("text") == text and o.metaObject().indexOfSignal("clicked()") >= 0 and o.property("visible")]

    def click(self, button):
        self.assertTrue(button.property("enabled"))
        self.assertTrue(QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection))
        self.pump()

    def page(self, index):
        self.controller.navigate(index)
        self.pump()

    def close_notice(self):
        for o in self.objects():
            if o.objectName() == "noticeDialog":
                QMetaObject.invokeMethod(o, "close", Qt.DirectConnection)
        self.pump()

    def test_all_navigation_and_populated_pages_have_no_qml_errors(self):
        for i, name in enumerate(("Dashboard", "AI Troubleshoot", "System Scan", "Issues", "Repair Center", "System Health", "Reports", "Demo Lab", "Settings", "About")):
            self.click(self.buttons(name)[0])
            self.assertEqual(self.controller.currentPage, i)
        self.controller._session = {"sessionId": "test", "status": "repair_recommended"}
        self.controller._diagnostics = [self.facade.diagnostic_view(finding())]
        self.controller._repair_timeline = [{"workflowLabel": "Test only", "status": "failed", "statusLabel": "Failed", "durationSeconds": 1, "completedAt": "test", "message": "No operation executed", "beforeText": "{}", "afterText": "{}", "verificationText": "Unavailable", "confidence": 0}]
        self.controller._emit()
        for i in range(10):
            self.page(i)
        errors = [m for m in self.messages if any(x in m for x in ("ReferenceError", "TypeError", "Binding loop", "is not defined", "Unable to assign"))]
        self.assertEqual(errors, [])

    def test_repair_click_reaches_correct_issue_and_confirmation_can_cancel(self):
        base = {"title": "Test fault", "category": "DNS", "confidenceLabel": "95%", "severity": "medium", "severityLabel": "Medium", "riskLabel": "Medium", "evidenceText": "Synthetic test evidence", "workflowLabel": "Test workflow", "requiresAdministrator": False, "requiresConfirmation": True, "repairAvailable": True}
        self.controller._problems = [dict(base, problemId="one"), dict(base, problemId="two")]
        self.controller._emit(); self.page(3)
        with patch.object(self.controller, "_run_repair") as execute:
            self.click(self.buttons("Repair")[1])
            self.assertEqual(self.controller._pending_repair, 1)
            dialog = next(o for o in self.objects() if o.objectName() == "repairConfirmation")
            QMetaObject.invokeMethod(dialog, "reject", Qt.DirectConnection)
            self.pump()
            execute.assert_not_called()
            self.click(self.buttons("Repair")[0])
            QMetaObject.invokeMethod(dialog, "accept", Qt.DirectConnection)
            self.pump()
            execute.assert_called_once_with(0, True)

    def test_scan_buttons_dispatch_and_busy_blocks_repeat(self):
        payload = {"diagnostics": [], "problems": [], "dashboard": self.facade.dashboard()}
        with patch.object(self.facade, "full_scan", return_value=payload) as scan:
            self.page(2)
            self.click(self.buttons("Run system scan")[0])
            self.controller.pool.waitForDone(5000); self.pump(); self.close_notice()
            scan.assert_called_once()
            self.assertFalse(self.controller.busy)
        self.controller._busy = True; self.controller._emit(); self.pump()
        self.assertFalse(self.buttons("Scan running…")[0].property("enabled"))
        with patch.object(self.facade, "start_troubleshooting") as start:
            self.controller.startTroubleshooting("printer failed")
            start.assert_not_called()
        self.controller._busy = False

    def test_dashboard_scan_card_accepts_a_mouse_click(self):
        self.page(0)
        action = next(o for o in self.objects() if o.objectName() == "dashboardScanAction")
        with patch.object(self.facade, "full_scan", return_value={"diagnostics": [], "problems": [], "dashboard": self.facade.dashboard()}) as scan:
            position = action.mapToScene(QPointF(action.width()/2, action.height()/2)).toPoint()
            QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, position)
            self.pump(); self.controller.pool.waitForDone(5000); self.pump()
            scan.assert_called_once()
            self.assertEqual(self.controller.currentPage, 2)

    def test_elevation_cancel_and_health_evidence_toggle(self):
        self.controller._problems = [{"title": "Test", "category": "Printer", "confidenceLabel": "95%", "severity": "medium", "severityLabel": "Medium", "riskLabel": "Medium", "evidenceText": "test", "workflowLabel": "Test only", "requiresAdministrator": True, "requiresConfirmation": True, "repairAvailable": True}]
        self.controller._emit(); self.page(3)
        with patch.object(self.controller, "_run_repair") as execute, patch("ui.qt_controller.relaunch_as_administrator") as elevate:
            self.click(self.buttons("Repair")[0])
            dialog = next(o for o in self.objects() if o.objectName() == "elevationConfirmation")
            self.assertTrue(dialog.property("visible"))
            QMetaObject.invokeMethod(dialog, "reject", Qt.DirectConnection); self.pump()
            execute.assert_not_called(); elevate.assert_not_called()
        self.controller._diagnostics = [self.facade.diagnostic_view(finding())]
        self.controller._emit(); self.page(5)
        self.click(self.buttons("View evidence")[0])
        self.assertTrue(self.buttons("Hide evidence"))

    def test_chat_start_followup_and_new_issue(self):
        self.page(1)
        input_item = next(o for o in self.objects() if o.property("placeholderText") == "Describe the issue…")
        input_item.setProperty("text", "my wifi is slow"); self.pump()
        self.click(self.buttons("Start")[0])
        self.assertEqual(self.controller.session["category"], "Network")
        input_item.setProperty("text", "only this computer")
        with patch("services.conversation_service.WindowsDiagnosticEngine.run_targeted", return_value=[finding()]) as scan:
            self.click(self.buttons("Continue")[0])
            self.controller.pool.waitForDone(5000); self.pump()
            scan.assert_called_once()
        self.assertTrue(self.facade.context.database.diagnostic_records())
        self.click(self.buttons("New issue")[0])
        self.assertEqual(self.controller.session, {})
        self.assertEqual(self.controller.problems, [])

    def test_report_buttons_all_formats_and_folder_open(self):
        self.facade.context.database.save_diagnostic_results([finding()])
        now = datetime.now(timezone.utc)
        self.facade.session = TroubleshootingSession("test-session", now, now, "test", "Disk Space", .9)
        self.facade.context.database.save_session(self.facade.session)
        self.controller._session = self.facade.session_view()
        self.controller._dashboard = self.facade.dashboard()
        self.controller._emit(); self.page(6)
        export = self.buttons("Export PDF")
        self.assertEqual([bool(b.property("enabled")) for b in export], [True, True, False, True])
        with patch.object(self.facade, "export_report", wraps=self.facade.export_report) as exporter:
            self.click(export[1]); self.controller.pool.waitForDone(5000); self.pump(); self.close_notice()
            exporter.assert_called_once_with("diagnostic", "pdf")
        self.assertTrue(list(Path(self.temp.name).glob("reports/*.pdf")))
        with patch("ui.qt_controller.QDesktopServices.openUrl", return_value=True) as opener:
            self.click(self.buttons("Open report folder")[0]); self.click(self.buttons("Open")[0])
            self.assertEqual(opener.call_count, 2)
        selector = next(o for o in self.objects() if o.property("displayText") == "PDF")
        for index, fmt in ((1, "csv"), (2, "json")):
            selector.setProperty("currentIndex", index); self.pump()
            self.click(self.buttons("Export " + fmt.upper())[0])
            self.controller.pool.waitForDone(5000); self.pump(); self.close_notice()
            self.assertTrue(list(Path(self.temp.name).glob(f"reports/*.{fmt}")))

    def test_escalation_export_and_missing_source_reports(self):
        self.page(6)
        self.assertEqual([bool(b.property("enabled")) for b in self.buttons("Export PDF")], [False, False, False, True])
        now = datetime.now(timezone.utc)
        self.facade.session = TroubleshootingSession("test-escalation", now, now, "test", "DNS", .9)
        self.facade.session.final_status = "escalated"
        self.facade.session.escalation = {"remaining_symptoms": ["DNS unresolved"], "recommended_human_action": "Ask an IT technician to check network policy."}
        self.facade.context.database.save_session(self.facade.session)
        self.controller._session = self.facade.session_view(); self.controller._emit(); self.pump()
        self.click(self.buttons("Export PDF")[2])
        self.controller.pool.waitForDone(5000); self.pump()
        self.assertTrue(list(Path(self.temp.name).glob("reports/escalation*.pdf")))

    def test_settings_demo_and_errors_return_control(self):
        self.page(8)
        self.click(self.buttons("Save settings")[0])
        self.assertTrue(self.facade.context.settings.config_directory.joinpath("portable_settings.json").exists())
        self.page(7)
        with patch("fixes.executor.AutonomousFixEngine._execute", side_effect=AssertionError("No live repair")):
            for button in self.buttons("Run simulation"):
                self.click(button)
                self.controller.pool.waitForDone(5000); self.pump()
                self.assertTrue(self.controller.demoResult.get("simulation"))
        self.controller._busy = True
        self.controller._worker_failed("test failure")
        self.assertFalse(self.controller.busy)
        self.assertIn("failed safely", self.controller.statusMessage)


class EvidenceRegressionTests(unittest.TestCase):
    def test_classifier_slow_wifi_and_ambiguous_guidance(self):
        classifier = OfflineIssueClassifier()
        self.assertEqual(classifier.classify("my wifi is slow").category, "Network")
        self.assertIn("system health", classifier.classify("something broke").follow_up_questions[0])

    def test_disk_threshold_and_unreadable_drive(self):
        from collections import namedtuple
        Usage = namedtuple("Usage", "total used free")
        engine = WindowsDiagnosticEngine(20)
        with patch("diagnostics.windows_diagnostics.os.path.exists", side_effect=lambda p: p.startswith(("C:", "D:"))), patch("diagnostics.windows_diagnostics.shutil.disk_usage", side_effect=[Usage(100,85,15), PermissionError("Access denied")]):
            result = engine.disk_health()[0]
        self.assertEqual(result.status, DiagnosticStatus.WARNING)
        self.assertEqual(len(result.details["drives"]), 1)
        self.assertEqual(len(result.details["collection_errors"]), 1)

    def test_missing_cpu_sample_is_not_zero_percent_healthy(self):
        with patch("diagnostics.windows_diagnostics._powershell", side_effect=[None, [], []]), patch.object(WindowsDiagnosticEngine, "_memory"):
            with self.assertRaises(ValueError):
                WindowsDiagnosticEngine().cpu_memory_health()

    def test_pdf_is_tabular_complete_and_sanitized(self):
        with tempfile.TemporaryDirectory() as folder:
            ctx = context(Path(folder)); item = finding()
            item.details["long_evidence"] = "recorded " * 2000 + "FINAL_EVIDENCE_MARKER"
            item.details["password"] = "DO_NOT_EXPORT_ME"
            ctx.database.save_diagnostic_results([item])
            service = ReportService(ctx.settings.database_path, ctx.settings.reports_directory)
            report = service.build_diagnostic_report()
            pdf = service.export(report, "pdf")
            reader = PdfReader(pdf)
            text = "\n".join(page.extract_text() for page in reader.pages)
            for expected in ("At a glance", "Issues and next actions", "Recommended next action", "C: has 5% free space", "FINAL_EVIDENCE_MARKER", "No repair attempt"):
                self.assertIn(expected, text)
            self.assertNotIn("DO_NOT_EXPORT_ME", text)
            self.assertNotIn('{"', text)
            self.assertGreater(len(reader.pages), 1)
            for fmt in ("json", "csv"):
                exported = service.export(report, fmt).read_text(encoding="utf-8-sig")
                self.assertIn("FINAL_EVIDENCE_MARKER", exported)
                self.assertNotIn("DO_NOT_EXPORT_ME", exported)

    def test_repair_report_requires_execution_and_summary_does_not_trust_status(self):
        with tempfile.TemporaryDirectory() as folder:
            ctx = context(Path(folder)); now = datetime.now(timezone.utc)
            result = FixExecutionResult("attempt", "problem", "network_flush_dns", FixStatus.RESOLVED, now, now, "untrusted", assessment=FixAssessment(AssessmentStatus.SUCCESS, (), {}, 1))
            ctx.database.save_fix_attempt(result)
            service = ReportService(ctx.settings.database_path, ctx.settings.reports_directory)
            self.assertEqual(service.build_repair_report("attempt")["final_status"], "failed")
            self.assertEqual(service.build_summary_activity_report()["repair_outcomes"], {"not_verified": 1})
