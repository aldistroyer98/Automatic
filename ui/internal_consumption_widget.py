from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.equivalence_service import normalize_description

if TYPE_CHECKING:
    from ui.tabs.equivalence_tab import EquivalenceTab


class InternalConsumptionWidget(QWidget):
    closeRequested = Signal()
    dirtyChanged = Signal(bool)

    def __init__(self, tab: "EquivalenceTab", parent: QWidget | None = None) -> None:
        super().__init__(parent or tab)
        self.tab = tab
        self.dirty = False
        self._loading = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("Periodo:"))
        self.period_label = QLabel(self)
        header.addWidget(self.period_label)
        header.addWidget(QLabel("Días calculados:"))
        self.days_label = QLabel(self)
        header.addWidget(self.days_label)
        header.addStretch(1)
        apply_button = QPushButton("Aplicar cálculo", self)
        apply_button.clicked.connect(self.apply_calculation)
        save_button = QPushButton("Guardar reglas", self)
        save_button.clicked.connect(self.save_rules)
        clear_button = QPushButton("Limpiar reglas", self)
        clear_button.clicked.connect(self.clear_rules)
        header.addWidget(apply_button)
        header.addWidget(save_button)
        header.addWidget(clear_button)
        root.addLayout(header)

        self.tabs = QTabWidget(self)
        controls_page = QWidget(self.tabs)
        controls_box = QVBoxLayout(controls_page)

        self.control_table = QTableWidget(0, 5, self)
        self.control_table.setHorizontalHeaderLabels(
            ("Activo", "Control", "Frecuencia/día", "DET RVO", "Cajas")
        )
        self.control_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.control_table.verticalHeader().setVisible(False)
        self.control_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.control_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.control_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.control_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.control_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.control_table.itemSelectionChanged.connect(self._load_control_links)
        controls_box.addWidget(self.control_table, 1)
        self.control_reagents = QListWidget(self)
        self.control_reagents.setSelectionMode(QAbstractItemView.MultiSelection)
        controls_box.addWidget(QLabel("Reactivos vinculados"))
        controls_box.addWidget(self.control_reagents, 1)
        control_actions = QHBoxLayout()
        link_control = QPushButton("Vincular seleccionados", self)
        link_control.clicked.connect(self._save_control_links)
        unlink_control = QPushButton("Desvincular", self)
        unlink_control.clicked.connect(self._clear_control_links)
        control_actions.addWidget(link_control)
        control_actions.addWidget(unlink_control)
        controls_box.addLayout(control_actions)
        self.tabs.addTab(controls_page, "Controles → Reactivos")

        consumables_page = QWidget(self.tabs)
        consumables_box = QVBoxLayout(consumables_page)
        self.consumable_table = QTableWidget(0, 5, self)
        self.consumable_table.setHorizontalHeaderLabels(
            ("Activo", "Consumible", "DET RVO", "Base", "CANT")
        )
        self.consumable_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.consumable_table.verticalHeader().setVisible(False)
        self.consumable_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.consumable_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.consumable_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.consumable_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.consumable_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.consumable_table.itemSelectionChanged.connect(self._load_consumable_links)
        consumables_box.addWidget(self.consumable_table, 1)
        self.consumable_basis = QComboBox(self)
        self.consumable_basis.addItem(
            "Todos los reactivos principales",
            "total_reagent_det_env",
        )
        self.consumable_basis.addItem(
            "Reactivos seleccionados",
            "selected_reagents_det_env",
        )
        consumables_box.addWidget(self.consumable_basis)
        self.consumable_reagents = QListWidget(self)
        self.consumable_reagents.setSelectionMode(QAbstractItemView.MultiSelection)
        consumables_box.addWidget(self.consumable_reagents, 1)
        consumable_actions = QHBoxLayout()
        link_consumable = QPushButton("Guardar base/vínculos", self)
        link_consumable.clicked.connect(self._save_consumable_links)
        clear_consumable = QPushButton("Desvincular", self)
        clear_consumable.clicked.connect(self._clear_consumable_links)
        consumable_actions.addWidget(link_consumable)
        consumable_actions.addWidget(clear_consumable)
        consumables_box.addLayout(consumable_actions)
        self.tabs.addTab(consumables_page, "Consumibles")

        summary_page = QWidget(self.tabs)
        summary_layout = QVBoxLayout(summary_page)
        self.summary_table = QTableWidget(0, 6, self)
        self.summary_table.setHorizontalHeaderLabels(
            ("Producto", "DET OC", "DET interno", "DET ENV", "DET RVO", "CANT")
        )
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 6):
            self.summary_table.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeToContents,
            )
        summary_layout.addWidget(self.summary_table)
        self.tabs.addTab(summary_page, "Resumen de impacto")
        root.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_button = QPushButton("Cerrar", self)
        close_button.clicked.connect(self.closeRequested.emit)
        actions.addWidget(close_button)
        root.addLayout(actions)

        self.control_table.itemChanged.connect(self._mark_dirty)
        self.consumable_table.itemChanged.connect(self._mark_dirty)
        self.control_reagents.itemSelectionChanged.connect(self._mark_dirty)
        self.consumable_reagents.itemSelectionChanged.connect(self._mark_dirty)
        self.consumable_basis.currentIndexChanged.connect(self._mark_dirty)

    def refresh(self) -> None:
        self._loading = True
        try:
            self.period_label.setText(
                f"{self.tab.period_months.value()} meses — {self.tab.period_type.currentText()}"
            )
            self.days_label.setText(
                str(self.tab.service.target_days(self.tab.period_months.value()))
            )
            self._load_products()
            self.apply_calculation()
        finally:
            self._loading = False
        self.set_dirty(False)

    def _load_products(self) -> None:
        settings = self._settings()
        controls = {
            item.get("control_product_key"): item
            for item in settings.get("controls", [])
        }
        consumables = {
            item.get("consumable_product_key"): item
            for item in settings.get("consumables", [])
        }
        control_products = self._products_in_category("control de calidad")
        reagent_products = self._products_in_category("reactivo principal")
        consumable_products = self._products_in_category("consumible")

        self.control_table.setRowCount(len(control_products))
        days = self.tab.service.target_days(self.tab.period_months.value())
        for row, product in enumerate(control_products):
            rule = controls.get(product.key, {})
            enabled = QCheckBox(self.control_table)
            enabled.setChecked(bool(rule.get("enabled", True)))
            enabled.toggled.connect(self._mark_dirty)
            self.control_table.setCellWidget(row, 0, enabled)
            self._set_item(self.control_table, row, 1, product.product, product.key)
            frequency = QDoubleSpinBox(self.control_table)
            frequency.setRange(0, 100)
            frequency.setDecimals(2)
            frequency.setValue(float(rule.get("frequency_per_day", 1)))
            frequency.valueChanged.connect(self._mark_dirty)
            self.control_table.setCellWidget(row, 2, frequency)
            self._set_item(self.control_table, row, 3, self.tab._format_number(product.det_rvo))
            boxes = self.tab.service.control_boxes(days, product.det_rvo, frequency.value())
            self._set_item(self.control_table, row, 4, boxes)

        self.consumable_table.setRowCount(len(consumable_products))
        for row, product in enumerate(consumable_products):
            rule = consumables.get(product.key, {})
            enabled = QCheckBox(self.consumable_table)
            enabled.setChecked(bool(rule.get("enabled", True)))
            enabled.toggled.connect(self._mark_dirty)
            self.consumable_table.setCellWidget(row, 0, enabled)
            self._set_item(self.consumable_table, row, 1, product.product, product.key)
            self._set_item(
                self.consumable_table,
                row,
                2,
                self.tab._format_number(product.det_rvo),
            )
            basis = str(rule.get("basis", "total_reagent_det_env"))
            self._set_item(
                self.consumable_table,
                row,
                3,
                "Seleccionados" if basis == "selected_reagents_det_env" else "Todos",
            )
            self._set_item(self.consumable_table, row, 4, "")

        for list_widget in (self.control_reagents, self.consumable_reagents):
            list_widget.clear()
            for product in reagent_products:
                item = QListWidgetItem(product.product)
                item.setData(Qt.UserRole, product.key)
                list_widget.addItem(item)

    def save_rules(self) -> None:
        self._apply_ui_to_state()
        self.tab._load_state_to_products()
        self.tab.save_state(show_message=False)
        self.apply_calculation(sync_ui=False)
        self.set_dirty(False)

    def _apply_ui_to_state(self) -> None:
        settings = self._settings()
        products = self.tab.service.product_lookup(self.tab.state.products)
        old_controls = {
            item.get("control_product_key"): item
            for item in settings.get("controls", [])
        }
        old_consumables = {
            item.get("consumable_product_key"): item
            for item in settings.get("consumables", [])
        }
        controls = []
        for row in range(self.control_table.rowCount()):
            key = self._item_data(self.control_table, row, 1)
            product = products.get(key)
            if product is not None:
                product.det_rvo = self.tab._optional_number(
                    self.control_table.item(row, 3).text()
                )
            previous = old_controls.get(key, {})
            controls.append(
                {
                    "control_product_key": key,
                    "linked_reagent_keys": list(previous.get("linked_reagent_keys", [])),
                    "frequency_per_day": self.control_table.cellWidget(row, 2).value(),
                    "enabled": self.control_table.cellWidget(row, 0).isChecked(),
                }
            )
        consumables = []
        for row in range(self.consumable_table.rowCount()):
            key = self._item_data(self.consumable_table, row, 1)
            product = products.get(key)
            if product is not None:
                product.det_rvo = self.tab._optional_number(
                    self.consumable_table.item(row, 2).text()
                )
            previous = old_consumables.get(key, {})
            consumables.append(
                {
                    "consumable_product_key": key,
                    "basis": previous.get("basis", "total_reagent_det_env"),
                    "linked_reagent_keys": list(previous.get("linked_reagent_keys", [])),
                    "enabled": self.consumable_table.cellWidget(row, 0).isChecked(),
                }
            )
        self.tab.state.settings["internal_consumption"] = {
            "controls": controls,
            "consumables": consumables,
        }

    def apply_calculation(self, *, sync_ui: bool = True) -> None:
        if sync_ui:
            self._apply_ui_to_state()
        self.tab.recalculate()
        results = self.tab._results
        self.summary_table.setRowCount(len(results))
        for row, result in enumerate(results):
            values = (
                result.product,
                self.tab._format_number(result.det_oc),
                self.tab._format_number(result.det_internal),
                self.tab._format_number(result.det_env),
                self.tab._format_number(result.det_rvo),
                self.tab._format_number(result.quantity),
            )
            for column, value in enumerate(values):
                self._set_item(
                    self.summary_table,
                    row,
                    column,
                    value,
                )
        by_key = {
            self.tab.service._result_product_key(result): result
            for result in results
        }
        for row in range(self.control_table.rowCount()):
            result = by_key.get(self._item_data(self.control_table, row, 1))
            self.control_table.item(row, 4).setText(
                self.tab._format_number(result.quantity if result else 0)
            )
        for row in range(self.consumable_table.rowCount()):
            result = by_key.get(self._item_data(self.consumable_table, row, 1))
            self.consumable_table.item(row, 4).setText(
                self.tab._format_number(result.quantity if result else 0)
            )

    def clear_rules(self) -> None:
        self.tab.state.settings["internal_consumption"] = {
            "controls": [],
            "consumables": [],
        }
        self._loading = True
        try:
            self._load_products()
            self.apply_calculation(sync_ui=False)
        finally:
            self._loading = False
        self.set_dirty(True)

    def _save_control_links(self) -> None:
        row = self.control_table.currentRow()
        if row < 0:
            return
        key = self._item_data(self.control_table, row, 1)
        rule = self._ensure_rule("controls", "control_product_key", key)
        rule["linked_reagent_keys"] = self._selected_keys(self.control_reagents)
        self.set_dirty(True)
        self.apply_calculation()

    def _clear_control_links(self) -> None:
        self.control_reagents.clearSelection()
        self._save_control_links()

    def _save_consumable_links(self) -> None:
        row = self.consumable_table.currentRow()
        if row < 0:
            return
        key = self._item_data(self.consumable_table, row, 1)
        rule = self._ensure_rule("consumables", "consumable_product_key", key)
        rule["basis"] = self.consumable_basis.currentData()
        rule["linked_reagent_keys"] = self._selected_keys(self.consumable_reagents)
        self.set_dirty(True)
        self.apply_calculation()

    def _clear_consumable_links(self) -> None:
        self.consumable_reagents.clearSelection()
        self._save_consumable_links()

    def _load_control_links(self) -> None:
        self._load_links(
            self.control_table,
            1,
            "controls",
            "control_product_key",
            self.control_reagents,
        )

    def _load_consumable_links(self) -> None:
        rule = self._load_links(
            self.consumable_table,
            1,
            "consumables",
            "consumable_product_key",
            self.consumable_reagents,
        )
        if rule:
            self._loading = True
            try:
                index = self.consumable_basis.findData(
                    rule.get("basis", "total_reagent_det_env")
                )
                self.consumable_basis.setCurrentIndex(max(0, index))
            finally:
                self._loading = False

    def _load_links(self, table, key_column, section, key_name, list_widget):
        row = table.currentRow()
        if row < 0:
            return None
        key = self._item_data(table, row, key_column)
        rule = next(
            (
                item
                for item in self._settings().get(section, [])
                if item.get(key_name) == key
            ),
            {},
        )
        selected = set(rule.get("linked_reagent_keys", []))
        self._loading = True
        try:
            for index in range(list_widget.count()):
                item = list_widget.item(index)
                item.setSelected(item.data(Qt.UserRole) in selected)
        finally:
            self._loading = False
        return rule

    def _ensure_rule(self, section: str, key_name: str, key: str) -> dict:
        settings = self._settings()
        rules = settings.setdefault(section, [])
        rule = next((item for item in rules if item.get(key_name) == key), None)
        if rule is None:
            rule = {key_name: key, "linked_reagent_keys": [], "enabled": True}
            rules.append(rule)
        return rule

    def _settings(self) -> dict:
        return self.tab.state.settings.setdefault(
            "internal_consumption",
            {"controls": [], "consumables": []},
        )

    def _products_in_category(self, normalized_category: str):
        return [
            product
            for product in self.tab.service.sorted_products(
                self.tab.state.products,
                self.tab.state.settings.get("product_categories", []),
            )
            if normalize_description(product.category) == normalized_category
        ]

    @staticmethod
    def _selected_keys(list_widget: QListWidget) -> list[str]:
        return [
            str(item.data(Qt.UserRole))
            for item in list_widget.selectedItems()
        ]

    @staticmethod
    def _set_item(table, row, column, value, data=None) -> None:
        item = QTableWidgetItem(str(value))
        item.setTextAlignment(Qt.AlignCenter)
        if data is not None:
            item.setData(Qt.UserRole, data)
        table.setItem(row, column, item)

    @staticmethod
    def _item_data(table, row, column) -> str:
        item = table.item(row, column)
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self.set_dirty(True)

    def set_dirty(self, dirty: bool) -> None:
        dirty = bool(dirty)
        if self.dirty == dirty:
            return
        self.dirty = dirty
        self.dirtyChanged.emit(dirty)
