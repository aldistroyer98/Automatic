from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.paths import get_app_paths
from services.shipment_service import ShipmentService
from ui.icons import app_icon
from ui.scaling import AVAILABLE_SCALES, UiScale
from ui.tabs import EquivalenceTab, ShipmentTab
from ui.theme import ThemeMode, palette, stylesheet


class MainWindow(QMainWindow):
    """Main window for the standalone Envio module."""

    def __init__(self) -> None:
        super().__init__()

        self.paths = get_app_paths()
        self.theme_mode = ThemeMode.LIGHT
        self.ui_scale = UiScale()
        self._logo_pixmap = QPixmap()

        self.setWindowTitle("Automatic - Envío")
        self._set_window_icon()
        self._load_logo()

        reference_path = self._shipment_reference_path()
        self.shipment_service = ShipmentService(reference_path)

        self._build_ui()
        self._apply_ui_scale(center=True)

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        self.root_layout = QVBoxLayout(root)
        self.root_layout.addWidget(self._build_header())

        icon_color = "#ffffff" if self.theme_mode == ThemeMode.DARK else palette(self.theme_mode)["accent"]
        self.tabs = QTabWidget(self)
        self.shipment_tab = ShipmentTab(self.shipment_service, self)
        self.tabs.addTab(
            self.shipment_tab,
            app_icon("SP_DriveFDIcon", self, color=icon_color),
            "Envío",
        )
        self.equivalence_tab = EquivalenceTab(self)
        self.tabs.addTab(
            self.equivalence_tab,
            app_icon("SP_FileDialogDetailedView", self, color=icon_color),
            "Equivalencia",
        )
        self.root_layout.addWidget(self.tabs, 1)

        footer = QLabel("Desarrollado por Alonso Espiritu", self)
        footer.setObjectName("FooterLabel")
        footer.setAlignment(Qt.AlignRight)
        self.root_layout.addWidget(footer)

    def _build_header(self) -> QFrame:
        self.header = QFrame(self)
        self.header.setObjectName("AppHeader")

        self.header_layout = QHBoxLayout(self.header)

        self.header_left = QWidget(self.header)
        self.header_left.setObjectName("HeaderLogoContainer")
        self.header_left_layout = QHBoxLayout(self.header_left)
        self.header_left_layout.setContentsMargins(0, 0, 0, 0)
        self.logo_label = QLabel(self.header_left)
        self.logo_label.setObjectName("HeaderLogo")
        self.logo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.logo_label.setScaledContents(False)
        self.logo_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.logo_label.setContentsMargins(8, 4, 8, 4)
        self.header_left_layout.addWidget(self.logo_label)
        self.header_left_layout.addStretch(1)
        self.header_layout.addWidget(self.header_left)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("Automatic", self.header)
        title.setObjectName("HeaderTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel(
            "Módulo independiente de análisis y generación de cuadros de envío",
            self.header,
        )
        subtitle.setObjectName("HeaderSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        self.header_layout.addLayout(title_box, 1)

        self.header_actions = QFrame(self.header)
        self.header_actions.setObjectName("HeaderActionsBox")
        actions_layout = QVBoxLayout(self.header_actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)

        status_row = QHBoxLayout()

        self.status_badge = QLabel("Listo", self.header_actions)
        self.status_badge.setObjectName("StatusBadge")
        status_row.addWidget(self.status_badge)

        self.scale_selector = QComboBox(self.header_actions)
        self.scale_selector.setObjectName("ScaleSelector")
        for scale in AVAILABLE_SCALES:
            self.scale_selector.addItem(UiScale(scale).label, scale)
        self.scale_selector.setCurrentText(self.ui_scale.label)
        self.scale_selector.currentTextChanged.connect(self._change_ui_scale)
        status_row.addWidget(self.scale_selector)

        self.theme_button = QPushButton(self.header_actions)
        self.theme_button.setObjectName("ThemeToggle")
        self.theme_button.clicked.connect(self._toggle_theme)
        status_row.addWidget(self.theme_button)
        actions_layout.addLayout(status_row)

        profile_row = QHBoxLayout()
        self.load_profile_button = QPushButton("Cargar Perfil", self.header_actions)
        self.load_profile_button.clicked.connect(self.load_profile)
        self.save_profile_button = QPushButton("Guardar Perfil", self.header_actions)
        self.save_profile_button.clicked.connect(self.save_profile)
        profile_row.addWidget(self.load_profile_button, 1)
        profile_row.addWidget(self.save_profile_button, 1)
        actions_layout.addLayout(profile_row)

        self.header_layout.addWidget(self.header_actions)
        self._update_theme_button()
        return self.header

    def _set_window_icon(self) -> None:
        icon_path = self.paths.resource("resources/icons/Automatic.png")
        if not icon_path.exists():
            return

        icon = QIcon(str(icon_path))
        if not icon.isNull():
            self.setWindowIcon(icon)

    def _shipment_reference_path(self) -> Path | None:
        reference_path = self.paths.resource("samples/envio/Cuadro de Envios - Formato.xlsx")
        return reference_path if reference_path.exists() else None

    def _load_logo(self) -> None:
        logo_path = self.paths.resource("resources/logos/SISA1.png")
        if logo_path.exists():
            self._logo_pixmap = QPixmap(str(logo_path))

    def _apply_ui_scale(self, *, center: bool = False) -> None:
        s = self.ui_scale.px
        self.root_layout.setContentsMargins(s(16), s(16), s(16), s(10))
        self.root_layout.setSpacing(s(12))
        self.header_layout.setContentsMargins(s(18), s(14), s(18), s(14))
        self.header_layout.setSpacing(s(14))
        self.theme_button.setFixedSize(s(38), s(34))
        self.scale_selector.setFixedWidth(s(88))
        self.status_badge.setMinimumWidth(s(82, minimum=72))
        self.load_profile_button.setMinimumHeight(s(30))
        self.save_profile_button.setMinimumHeight(s(30))
        self.header_left.setFixedWidth(s(310, minimum=250))
        self.header_actions.setFixedWidth(s(310, minimum=270))
        self._update_logo()
        self._update_tab_icon()
        self.setStyleSheet(stylesheet(self.theme_mode, self.ui_scale))
        self._style_logo_label()
        self.resize(self.ui_scale.window_size())
        if center:
            self._center_window()

    def _update_logo(self) -> None:
        if self._logo_pixmap.isNull():
            self.logo_label.setText("SISA")
            self.logo_label.show()
            return
        height = self.ui_scale.px(66, minimum=44)
        width = max(self.ui_scale.px(230, minimum=190), self.header_left.width() - self.ui_scale.px(28))
        pixmap = self._logo_pixmap.scaled(
            QSize(width, height),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.logo_label.clear()
        self.logo_label.setPixmap(pixmap)
        self.logo_label.show()

    def _style_logo_label(self) -> None:
        s = self.ui_scale.px
        self.logo_label.setFixedSize(
            max(s(220), self.header_left.width() - s(20)),
            s(72),
        )
        self.logo_label.setStyleSheet(
            f"QLabel#HeaderLogo {{ background: transparent; border: none; padding: {s(2)}px {s(4)}px; }}"
        )

    def _center_window(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(geometry.center())
        self.move(frame.topLeft())

    def _toggle_theme(self) -> None:
        self.theme_mode = ThemeMode.DARK if self.theme_mode == ThemeMode.LIGHT else ThemeMode.LIGHT
        self._update_theme_button()
        self._apply_ui_scale()

    def _update_theme_button(self) -> None:
        self.theme_button.setText("☾" if self.theme_mode == ThemeMode.LIGHT else "☀")
        self.theme_button.setToolTip("Cambiar tema")

    def _change_ui_scale(self, _label: str) -> None:
        self.ui_scale = UiScale(self.scale_selector.currentData())
        self._apply_ui_scale()

    def _update_tab_icon(self) -> None:
        color = "#ffffff" if self.theme_mode == ThemeMode.DARK else palette(self.theme_mode)["accent"]
        self.tabs.setTabIcon(0, app_icon("SP_DriveFDIcon", self, color=color))
        if self.tabs.count() > 1:
            self.tabs.setTabIcon(1, app_icon("SP_FileDialogDetailedView", self, color=color))

    def save_profile(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar perfil",
            str(self.paths.data_root / "perfil_envio.json"),
            "Archivos JSON (*.json)",
        )
        if not path:
            return
        try:
            output = self.shipment_tab.save_profile(path, self._ui_preferences())
            QMessageBox.information(self, "Perfil", f"Perfil guardado correctamente:\n{output}")
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar perfil", str(exc))

    def load_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar perfil",
            str(self.paths.data_root),
            "Archivos JSON (*.json)",
        )
        if not path:
            return
        try:
            preferences = self.shipment_tab.load_profile(path)
            self._apply_profile_preferences(preferences)
            QMessageBox.information(self, "Perfil", "Perfil cargado correctamente.")
        except Exception as exc:
            QMessageBox.critical(self, "Perfil no válido", str(exc))

    def _ui_preferences(self) -> dict:
        return {
            "theme": self.theme_mode.value,
            "scale": self.ui_scale.factor,
        }

    def _apply_profile_preferences(self, preferences: dict) -> None:
        theme = preferences.get("theme")
        scale = preferences.get("scale")
        changed = False
        if theme in {ThemeMode.LIGHT.value, ThemeMode.DARK.value}:
            self.theme_mode = ThemeMode(theme)
            changed = True
        if isinstance(scale, (int, float)) and scale in AVAILABLE_SCALES:
            self.ui_scale = UiScale(float(scale))
            index = self.scale_selector.findData(float(scale))
            if index >= 0:
                self.scale_selector.blockSignals(True)
                self.scale_selector.setCurrentIndex(index)
                self.scale_selector.blockSignals(False)
            changed = True
        if changed:
            self._update_theme_button()
            self._apply_ui_scale()
