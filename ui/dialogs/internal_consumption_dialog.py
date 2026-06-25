from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout

from ui.internal_consumption_widget import InternalConsumptionWidget
from ui.window_sizes import DIALOG_5_6, apply_fixed_window_size

if TYPE_CHECKING:
    from ui.tabs.equivalence_tab import EquivalenceTab


class InternalConsumptionDialog(QDialog):
    def __init__(self, tab: "EquivalenceTab") -> None:
        super().__init__(tab)
        self.tab = tab
        self._closing = False
        self._settings_snapshot = deepcopy(tab.state.settings)
        self._det_rvo_snapshot = {
            product.key: product.det_rvo
            for product in tab.state.products
        }
        self.setWindowTitle("Consumo interno")
        apply_fixed_window_size(self, DIALOG_5_6)

        root = QVBoxLayout(self)
        self.widget = InternalConsumptionWidget(tab, self)
        self.widget.closeRequested.connect(self.request_close)
        root.addWidget(self.widget)
        self.widget.refresh()

    def request_close(self) -> None:
        if not self._confirm_pending_changes():
            return
        self._closing = True
        self.accept()

    def closeEvent(self, event) -> None:
        if self._closing or self._confirm_pending_changes():
            self._closing = True
            event.accept()
        else:
            event.ignore()

    def _confirm_pending_changes(self) -> bool:
        if not self.widget.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Consumo interno",
            "Hay cambios sin guardar. ¿Deseas guardar antes de cerrar?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            self.widget.save_rules()
            return True
        self._restore_snapshot()
        return True

    def _restore_snapshot(self) -> None:
        self.tab.state.settings = deepcopy(self._settings_snapshot)
        for product in self.tab.state.products:
            if product.key in self._det_rvo_snapshot:
                product.det_rvo = self._det_rvo_snapshot[product.key]
        self.tab._load_state_to_products()
        self.tab.recalculate()
