"""PySide6 / Qt Quick application startup."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer, Qt, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from app.bootstrap import ApplicationContext
from config.branding import APP_ICON, APP_LOGO, APP_NAME, APP_VERSION, resolve_brand_asset
from services.ui_facade import UIFacade
from ui.qt_controller import AppController


def qml_root() -> Path:
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return bundle / "ui" / "qml"


def run_qt_application(
    context: ApplicationContext,
    smoke_test: bool = False,
    screenshot_path: str | None = None,
    initial_page: int = 0,
    demo_scenario: str | None = None,
) -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    QQuickWindow.setDefaultAlphaBuffer(True)
    QQuickStyle.setStyle("Basic")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("AI System Diagnostic")
    icon_path = resolve_brand_asset(context.settings.project_root, APP_ICON or APP_LOGO)
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    engine = QQmlApplicationEngine()
    controller = AppController(UIFacade(context))
    controller.navigate(initial_page)
    engine.rootContext().setContextProperty("controller", controller)
    qml_file = qml_root() / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        raise RuntimeError(f"Qt Quick interface could not be loaded: {qml_file}")
    if screenshot_path:
        output = Path(screenshot_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        root_window = engine.rootObjects()[0]
        def capture_and_exit() -> None:
            if not root_window.grabWindow().save(str(output), "PNG"):
                print(f"Could not save UI capture to {output}", file=sys.stderr)
            app.quit()
        if demo_scenario:
            QTimer.singleShot(100, lambda: controller.runDemo(demo_scenario))
            QTimer.singleShot(2200, capture_and_exit)
        else:
            QTimer.singleShot(1200, capture_and_exit)
    elif smoke_test:
        QTimer.singleShot(750, app.quit)
    return app.exec()
