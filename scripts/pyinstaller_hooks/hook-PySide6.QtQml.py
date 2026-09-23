"""Collect only the Qt Quick modules used by the desktop interface.

PyInstaller's default QtQml hook includes every installed QML plugin. A full
PySide6 installation can therefore pull WebEngine, 3D, multimedia, and other
unused runtimes into this offline desktop package.
"""
from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

_qml_root = Path(pyside6_library_info.location["QmlImportsPath"])
_destination_root = Path(pyside6_library_info.qt_rel_dir) / "qml"

_root_only = (
    "QtQml",
    "QtQuick",
    "QtQuick/Controls",
)

_module_trees = (
    "QtQml/Models",
    "QtQml/WorkerScript",
    "QtQuick/Controls/Basic",
    "QtQuick/Controls/impl",
    "QtQuick/Layouts",
    "QtQuick/Templates",
    "QtQuick/Window",
)


def _append(source: Path, relative_parent: Path) -> None:
    destination = str(_destination_root / relative_parent)
    item = (str(source), destination)
    if source.suffix.lower() == ".dll":
        binaries.append(item)
    else:
        datas.append(item)


for relative in _root_only:
    source_root = _qml_root / relative
    if source_root.is_dir():
        for source in source_root.iterdir():
            if source.is_file():
                _append(source, Path(relative))

for relative in _module_trees:
    source_root = _qml_root / relative
    if source_root.is_dir():
        for source in source_root.rglob("*"):
            if source.is_file():
                _append(source, Path(relative) / source.relative_to(source_root).parent)
