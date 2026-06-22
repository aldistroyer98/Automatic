from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyle, QWidget

try:
    from qfluentwidgets import FluentIcon
except ImportError:  # pragma: no cover - optional visual enhancement
    FluentIcon = None


FLUENT_ICON_MAP = {
    "SP_ComputerIcon": "PEOPLE",
    "SP_FileDialogDetailedView": "TILES",
    "SP_DialogApplyButton": "ACCEPT",
    "SP_DialogOpenButton": "FOLDER",
    "SP_DialogSaveButton": "SAVE_AS",
    "SP_DirIcon": "FILTER",
    "SP_FileIcon": "ADD",
    "SP_FileDialogNewFolder": "COPY",
    "SP_TrashIcon": "DELETE",
    "SP_MessageBoxInformation": "INFO",
    "SP_ArrowRight": "PLAY",
    "SP_DialogResetButton": "BROOM",
}


def _tinted_icon(icon: QIcon, color: str) -> QIcon:
    tinted = QIcon()
    for size in (16, 20, 24, 32):
        pixmap = icon.pixmap(QSize(size, size))
        if pixmap.isNull():
            continue
        target = QPixmap(pixmap.size())
        target.fill(Qt.transparent)
        painter = QPainter(target)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(target.rect(), QColor(color))
        painter.end()
        tinted.addPixmap(target)
    return tinted if not tinted.isNull() else icon


def app_icon(name: str, widget: QWidget | None = None, color: str | None = None) -> QIcon:
    if FluentIcon is not None:
        fluent_name = FLUENT_ICON_MAP.get(name)
        fluent_icon = getattr(FluentIcon, fluent_name, None) if fluent_name else None
        if fluent_icon is not None:
            icon = fluent_icon.icon()
            return _tinted_icon(icon, color) if color else icon

    style = widget.style() if widget is not None else QApplication.style()
    pixmap = getattr(QStyle.StandardPixmap, name, QStyle.StandardPixmap.SP_FileIcon)
    icon = style.standardIcon(pixmap)
    return _tinted_icon(icon, color) if color else icon
