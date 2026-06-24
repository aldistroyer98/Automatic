from __future__ import annotations

from enum import Enum
from functools import lru_cache

from ui.scaling import UiScale


class ThemeMode(str, Enum):
    LIGHT = "light"
    DARK = "dark"


PALETTES = {
    ThemeMode.LIGHT: {
        "bg": "#f5f7fa",
        "surface": "#ffffff",
        "surface_alt": "#f7f9fc",
        "text": "#122033",
        "muted": "#66758a",
        "border": "#d8e0ea",
        "primary": "#17324d",
        "primary_hover": "#204460",
        "accent": "#1f5f99",
        "accent_hover": "#174d80",
        "success": "#0f6b62",
        "warning": "#b85c14",
        "danger": "#b4232f",
        "console": "#0b1420",
        "console_text": "#d8e7f5",
    },
    ThemeMode.DARK: {
        "bg": "#101820",
        "surface": "#172230",
        "surface_alt": "#1e2a38",
        "text": "#e8eef5",
        "muted": "#a8b4c2",
        "border": "#354355",
        "primary": "#0f2133",
        "primary_hover": "#18314a",
        "accent": "#6fa7dc",
        "accent_hover": "#5a94ca",
        "success": "#39a99a",
        "warning": "#d9904a",
        "danger": "#ee7b85",
        "console": "#030712",
        "console_text": "#bfdbfe",
    },
}


def palette(mode: ThemeMode) -> dict:
    return PALETTES[mode]


def stylesheet(mode: ThemeMode, scale: UiScale | None = None) -> str:
    ui_scale = scale or UiScale()
    return _cached_stylesheet(mode.value, ui_scale.factor)


@lru_cache(maxsize=16)
def _cached_stylesheet(mode_value: str, scale_factor: float) -> str:
    return _build_stylesheet(ThemeMode(mode_value), UiScale(scale_factor))


def _build_stylesheet(mode: ThemeMode, scale: UiScale | None = None) -> str:
    c = palette(mode)
    ui_scale = scale or UiScale()
    s = ui_scale.px
    font = ui_scale.font
    disabled_bg = "#e5e7eb" if mode == ThemeMode.LIGHT else "#263244"
    disabled_text = "#64748b" if mode == ThemeMode.LIGHT else "#a8b3c3"
    disabled_border = "#cbd5e1" if mode == ThemeMode.LIGHT else "#40516a"
    invalid_bg = "#fde2e2" if mode == ThemeMode.LIGHT else "#4a1f26"
    invalid_text = "#7f1d1d" if mode == ThemeMode.LIGHT else "#ffe4e6"
    invalid_border = "#fca5a5" if mode == ThemeMode.LIGHT else "#b4535b"
    return f"""
    QWidget {{
        background: {c["bg"]};
        color: {c["text"]};
        font-family: "Segoe UI", "Inter", "Arial";
        font-size: {font(10)}pt;
    }}
    QFrame#AppHeader {{
        background: {c["primary"]};
        border-radius: {s(12)}px;
    }}
    QFrame#HeaderActionsBox {{
        background: transparent;
        border: none;
    }}
    QWidget#HeaderBalance, QWidget#HeaderLogoContainer {{
        background: transparent;
        border: none;
    }}
    QLabel#HeaderTitle {{
        color: #ffffff;
        font-size: {font(25)}px;
        font-weight: 800;
        background: transparent;
    }}
    QLabel#HeaderSubtitle, QLabel#HeaderBrand, QLabel#HeaderPath, QLabel#HeaderLogo {{
        color: #c7d2fe;
        background: transparent;
    }}
    QLabel#StatusBadge {{
        color: #d1fae5;
        background: rgba(15, 118, 110, 0.28);
        border: {s(1)}px solid rgba(167, 243, 208, 0.22);
        border-radius: {s(10)}px;
        padding: {s(6)}px {s(12)}px;
        font-weight: 700;
    }}
    QFrame#Section, QFrame#SummaryCard, QFrame#PanelCard {{
        background: {c["surface"]};
        border: {s(1)}px solid {c["border"]};
        border-radius: {s(10)}px;
    }}
    QFrame#SoftPanel {{
        background: {c["surface_alt"]};
        border: {s(1)}px solid {c["border"]};
        border-radius: {s(10)}px;
    }}
    QWidget#FieldBox, QWidget#CommentPanel {{
        background: transparent;
    }}
    QLabel#SectionTitle {{
        font-size: {font(18)}px;
        font-weight: 800;
        background: transparent;
    }}
    QLabel#Caption, QLabel#FieldLabel, QLabel#CardLabel {{
        color: {c["muted"]};
        font-weight: 700;
        background: transparent;
    }}
    QLabel#CardValue {{
        color: {c["text"]};
        font-size: {font(13)}px;
        font-weight: 800;
        background: transparent;
    }}
    QLabel#FooterLabel {{
        color: {c["muted"]};
        background: transparent;
    }}
    QPushButton {{
        background: {c["surface_alt"]};
        color: {c["text"]};
        border: {s(1)}px solid {c["border"]};
        border-radius: {s(8)}px;
        padding: {s(8)}px {s(14)}px;
        min-height: {s(20)}px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background: {c["surface"]};
        border-color: {c["accent"]};
        color: {c["accent"]};
    }}
    QPushButton:pressed {{
        background: {c["border"]};
        border-color: {c["accent_hover"]};
    }}
    QPushButton:disabled {{
        color: {c["muted"]};
        background: {c["surface_alt"]};
        border-color: {c["border"]};
    }}
    QPushButton[variant="primary"] {{
        background: {c["accent"]};
        color: #ffffff;
        border-color: {c["accent"]};
    }}
    QPushButton[variant="primary"]:hover {{
        background: {c["accent_hover"]};
        border-color: {c["accent_hover"]};
    }}
    QPushButton[variant="success"] {{
        background: {c["success"]};
        color: #ffffff;
        border-color: {c["success"]};
    }}
    QPushButton[variant="success"]:hover {{
        background: {c["success"]};
        border-color: {c["success"]};
        color: #ffffff;
    }}
    QPushButton[variant="danger"] {{
        background: transparent;
        color: {c["danger"]};
        border-color: {c["danger"]};
    }}
    QPushButton#ThemeToggle {{
        background: rgba(255, 255, 255, 0.12);
        color: #ffffff;
        border: {s(1)}px solid rgba(255, 255, 255, 0.25);
        border-radius: {s(8)}px;
        padding: 0;
        font-size: {font(16)}px;
        font-weight: 800;
    }}
    QPushButton#ThemeToggle:hover {{
        background: rgba(255, 255, 255, 0.20);
        color: #ffffff;
    }}
    QComboBox#ScaleSelector {{
        background: rgba(255, 255, 255, 0.12);
        color: #ffffff;
        border: {s(1)}px solid rgba(255, 255, 255, 0.25);
        border-radius: {s(8)}px;
        padding: {s(4)}px {s(8)}px;
        min-height: 0;
        font-weight: 800;
    }}
    QComboBox#ScaleSelector:hover {{
        background: rgba(255, 255, 255, 0.20);
    }}
    QComboBox#ScaleSelector::drop-down {{
        border: none;
        width: {s(16, minimum=12)}px;
    }}
    QComboBox#ScaleSelector::down-arrow {{
        image: none;
        width: 0;
        height: 0;
        border-left: {s(3, minimum=2)}px solid transparent;
        border-right: {s(3, minimum=2)}px solid transparent;
        border-top: {s(4, minimum=3)}px solid #ffffff;
        margin-right: {s(5, minimum=3)}px;
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
        background: {c["surface_alt"]};
        color: {c["text"]};
        border: {s(1)}px solid {c["border"]};
        border-radius: {s(8)}px;
        padding: {s(7)}px {s(10)}px;
        selection-background-color: {c["accent"]};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
        border-color: {c["accent"]};
        background: {c["surface"]};
    }}
    QLineEdit:disabled, QComboBox:disabled, QLineEdit[locked="true"], QComboBox[locked="true"] {{
        background: {disabled_bg};
        color: {disabled_text};
        border-color: {disabled_border};
    }}
    QLineEdit[invalid="true"], QComboBox[invalid="true"] {{
        background: {invalid_bg};
        color: {invalid_text};
        border-color: {invalid_border};
    }}
    QComboBox::drop-down {{
        border: none;
        width: {s(20, minimum=14)}px;
    }}
    QComboBox::down-arrow {{
        image: none;
        width: 0;
        height: 0;
        border-left: {s(4, minimum=3)}px solid transparent;
        border-right: {s(4, minimum=3)}px solid transparent;
        border-top: {s(5, minimum=4)}px solid {c["muted"]};
        margin-right: {s(6, minimum=4)}px;
    }}
    QComboBox QAbstractItemView {{
        background: {c["surface"]};
        color: {c["text"]};
        border: {s(1)}px solid {c["border"]};
        selection-background-color: {c["accent"]};
        selection-color: #ffffff;
        outline: none;
    }}
    QListWidget, QListView {{
        background: {c["surface"]};
        alternate-background-color: {c["surface"]};
        color: {c["text"]};
        border: {s(1)}px solid {c["border"]};
        selection-background-color: {c["accent"]};
        selection-color: #ffffff;
        outline: none;
    }}
    QListWidget::item, QListView::item {{
        padding: {s(4)}px {s(6)}px;
        min-height: {s(18)}px;
    }}
    QListWidget::item:alternate, QListView::item:alternate {{
        background: {c["surface"]};
    }}
    QListWidget::item:hover, QListView::item:hover {{
        background: {c["surface_alt"]};
    }}
    QListWidget::item:selected, QListView::item:selected {{
        background: {c["accent"]};
        color: #ffffff;
    }}
    QTabWidget::pane {{
        border: none;
        background: transparent;
        margin-top: {s(10)}px;
    }}
    QTabBar::tab {{
        background: {c["surface_alt"]};
        color: {c["muted"]};
        border: {s(1)}px solid {c["border"]};
        border-radius: {s(8)}px;
        padding: {s(10)}px {s(18)}px;
        margin-right: {s(7)}px;
        font-weight: 800;
    }}
    QTabBar::tab:selected {{
        color: #ffffff;
        background: {c["accent"]};
        border-color: {c["accent"]};
    }}
    QTableView {{
        background: {c["surface"]};
        alternate-background-color: {c["surface_alt"]};
        gridline-color: {c["border"]};
        border: {s(1)}px solid {c["border"]};
        border-radius: {s(8)}px;
        selection-background-color: rgba(37, 99, 235, 0.18);
        selection-color: {c["text"]};
    }}
    QTableView::item {{
        padding-left: {s(6)}px;
        padding-right: {s(6)}px;
    }}
    QTableView::item:hover {{
        background: rgba(37, 99, 235, 0.10);
    }}
    QTableView::item:selected {{
        background: rgba(37, 99, 235, 0.20);
        color: {c["text"]};
        
    }}
    QHeaderView::section {{
        background: {c["surface_alt"]};
        color: {c["text"]};
        border: none;
        border-bottom: {s(1)}px solid {c["border"]};
        padding: {s(12)}px {s(8)}px;
        min-height: {s(22)}px;
        font-weight: 800;
    }}
    QProgressBar {{
        background: {c["surface_alt"]};
        border: {s(1)}px solid {c["border"]};
        border-radius: {s(6)}px;
        height: {s(12)}px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {c["accent"]};
        border-radius: {s(8)}px;
    }}
    QCheckBox {{
        spacing: {s(8)}px;
        color: {c["text"]};
        background: transparent;
        font-weight: 700;
    }}
    QToolTip {{
        background: {c["primary"]};
        color: #ffffff;
        border: {s(1)}px solid {c["accent"]};
        border-radius: {s(7)}px;
        padding: {s(6)}px;
    }}
    QScrollBar:vertical, QScrollBar:horizontal {{
        background: transparent;
        border: none;
        margin: {s(2)}px;
    }}
    QScrollBar::handle {{
        background: {c["border"]};
        border-radius: {s(5)}px;
        min-height: {s(28)}px;
        min-width: {s(28)}px;
    }}
    QScrollBar::handle:hover {{
        background: {c["muted"]};
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0;
        height: 0;
        background: transparent;
        border: none;
    }}
    QScrollBar::corner {{
        background: transparent;
    }}
    QPlainTextEdit#LogConsole {{
        background: {c["console"]};
        color: {c["console_text"]};
        border-radius: {s(8)}px;
        border: {s(1)}px solid {c["border"]};
        font-family: "Cascadia Mono", "Consolas";
        font-size: {font(10)}pt;
    }}
    QLabel#CalendarWeekday {{
        color: {c["muted"]};
        background: transparent;
        font-weight: 800;
    }}
    QPushButton[calendarDay="true"] {{
        min-width: {s(30)}px;
        padding: {s(7)}px {s(8)}px;
        border-radius: {s(9)}px;
    }}
    QPushButton[calendarDay="true"][today="true"] {{
        border-color: {c["accent"]};
        color: {c["accent"]};
    }}
    QPushButton[calendarDay="true"]:checked {{
        background: {c["accent"]};
        color: #ffffff;
        border-color: {c["accent"]};
    }}
    """
