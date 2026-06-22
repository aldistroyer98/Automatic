from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QTabWidget

from app.paths import get_app_paths
from services.shipment_service import ShipmentService
from ui.tabs import ShipmentTab


class MainWindow(QMainWindow):
    """Main window for the standalone Envio module."""

    def __init__(self) -> None:
        super().__init__()

        self.paths = get_app_paths()
        self.setWindowTitle("Automatic - Envío")
        self.resize(1180, 760)
        self._set_window_icon()

        reference_path = self._shipment_reference_path()
        self.shipment_service = ShipmentService(reference_path)

        self.tabs = QTabWidget(self)
        self.shipment_tab = ShipmentTab(self.shipment_service, self)
        self.tabs.addTab(self.shipment_tab, "Envío")
        self.setCentralWidget(self.tabs)

    def _set_window_icon(self) -> None:
        icon_path = self.paths.resource("resources/icons/Automy1.png")
        if not icon_path.exists():
            return

        icon = QIcon(str(icon_path))
        if not icon.isNull():
            self.setWindowIcon(icon)

    def _shipment_reference_path(self) -> Path | None:
        reference_path = self.paths.resource("samples/envio/Cuadro de Envios - Formato.xlsx")
        return reference_path if reference_path.exists() else None
