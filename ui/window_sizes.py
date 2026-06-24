from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

BASE_WINDOW_SIZE = QSize(1440, 810)

DIALOG_5_6 = QSize(1200, 675)
DIALOG_3_4 = QSize(1080, 608)
DIALOG_2_3 = QSize(960, 540)
DIALOG_1_2 = QSize(720, 405)
DIALOG_1_3 = QSize(480, 270)
DIALOG_1_4 = QSize(360, 203)


def apply_fixed_window_size(widget: QWidget, size: QSize) -> None:
    """Apply an exact, non-resizable size to a window or dialog."""
    widget.setFixedSize(size)
