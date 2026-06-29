from __future__ import annotations

from collections.abc import Collection

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.shipment_config import (
    DEFAULT_FORECAST_COLORS,
    ShipmentCategoryState,
    ShipmentForecastProductConfig,
)
from services.category_manager import CategoryManager
from services.shipment_config_service import ShipmentConfigService
from ui.window_sizes import DIALOG_5_6, apply_fixed_window_size


class ShipmentForecastDialog(QDialog):
    HEADERS = (
        "Usar",
        "CodProd",
        "CodEqv",
        "Producto",
        "Categoría",
        "Rendimiento (días)",
        "Logística específica",
        "Color rendimiento",
        "Observación",
    )

    def __init__(
        self,
        category_config: ShipmentCategoryState,
        config_service: ShipmentConfigService,
        active_product_keys: Collection[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.category_config = category_config
        self.config_service = config_service
        self.active_product_keys = set(active_product_keys or category_config.assignments)
        self.setWindowTitle("Previsión de envíos")
        apply_fixed_window_size(self, DIALOG_5_6)
        self._build_ui()
        self._load_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        general = QGroupBox("Configuración general", self)
        form = QFormLayout(general)
        self.enabled_check = QCheckBox("Agregar cronograma al reporte Excel", general)
        form.addRow(self.enabled_check)
        self.logistics_spin = QSpinBox(general)
        self.logistics_spin.setRange(0, 365)
        form.addRow("Días de logística/envío:", self.logistics_spin)

        colors = QHBoxLayout()
        self.color_buttons: dict[str, QPushButton] = {}
        labels = (
            ("scheduled", "Fecha programada"),
            ("logistics", "Logística"),
            ("actual_delivery", "Entrega real"),
            ("performance", "Rendimiento"),
            ("expired", "Vencimiento"),
        )
        for name, label in labels:
            colors.addWidget(QLabel(label, general))
            button = QPushButton(general)
            button.setFixedWidth(54)
            button.clicked.connect(lambda _checked=False, key=name: self._choose_color(key))
            self.color_buttons[name] = button
            colors.addWidget(button)
        colors.addStretch(1)
        form.addRow("Colores:", colors)
        root.addWidget(general)

        self.table = QTableWidget(0, len(self.HEADERS), self)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        for text, handler in (
            ("Seleccionar todo", lambda: self._set_all_checked(True)),
            ("Limpiar selección", lambda: self._set_all_checked(False)),
            ("Restablecer colores", self._reset_colors),
        ):
            button = QPushButton(text, self)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch(1)
        save = QPushButton("Guardar", self)
        save.clicked.connect(self.save)
        apply_button = QPushButton("Aplicar", self)
        apply_button.clicked.connect(self.apply)
        close = QPushButton("Cerrar", self)
        close.clicked.connect(self.reject)
        actions.addWidget(save)
        actions.addWidget(apply_button)
        actions.addWidget(close)
        root.addLayout(actions)

    def _load_state(self) -> None:
        forecast = self.category_config.forecast
        self.enabled_check.setChecked(forecast.enabled)
        self.logistics_spin.setValue(forecast.logistics_days)
        for name, button in self.color_buttons.items():
            self._set_button_color(button, forecast.color(name))

        assignments = [
            item
            for item in self.category_config.assignments.values()
            if item.product_key in self.active_product_keys
        ]
        assignments.sort(key=lambda item: (item.category_name.casefold(), item.product_order, item.producto.casefold()))
        self.table.setRowCount(len(assignments))
        for row, assignment in enumerate(assignments):
            product_config = forecast.product(assignment.product_key)
            use_item = QTableWidgetItem()
            use_item.setData(Qt.UserRole, assignment.product_key)
            use_item.setCheckState(Qt.Checked if product_config.enabled else Qt.Unchecked)
            use_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, use_item)
            for column, value in enumerate(
                (
                    assignment.cod_prod,
                    assignment.cod_eqv,
                    assignment.producto,
                    CategoryManager.visible_name(assignment.category_name),
                ),
                start=1,
            ):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, column, item)
            performance = QDoubleSpinBox(self.table)
            performance.setRange(0, 3650)
            performance.setDecimals(2)
            performance.setValue(product_config.performance_days)
            self.table.setCellWidget(row, 5, performance)
            logistics = QSpinBox(self.table)
            logistics.setRange(-1, 365)
            logistics.setSpecialValueText("General")
            logistics.setValue(-1 if product_config.logistics_days is None else product_config.logistics_days)
            self.table.setCellWidget(row, 6, logistics)
            color = QPushButton("General", self.table)
            if product_config.performance_color:
                self._set_button_color(color, product_config.performance_color)
            color.clicked.connect(lambda _checked=False, current=color: self._choose_product_color(current))
            self.table.setCellWidget(row, 7, color)
            self.table.setItem(row, 8, QTableWidgetItem(product_config.observation))

    @staticmethod
    def _set_button_color(button: QPushButton, color: str) -> None:
        normalized = str(color).strip().lstrip("#").upper()
        button.setProperty("color_hex", normalized)
        button.setText(f"#{normalized}")
        button.setStyleSheet(f"background-color: #{normalized};")

    def _choose_color(self, name: str) -> None:
        button = self.color_buttons[name]
        selected = QColorDialog.getColor(QColor(f"#{button.property('color_hex')}"), self)
        if selected.isValid():
            self._set_button_color(button, selected.name())

    def _choose_product_color(self, button: QPushButton) -> None:
        initial = button.property("color_hex") or self.color_buttons["performance"].property("color_hex")
        selected = QColorDialog.getColor(QColor(f"#{initial}"), self)
        if selected.isValid():
            self._set_button_color(button, selected.name())

    def _reset_colors(self) -> None:
        for name, color in DEFAULT_FORECAST_COLORS.items():
            self._set_button_color(self.color_buttons[name], color)

    def _set_all_checked(self, checked: bool) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _collect(self) -> None:
        forecast = self.category_config.forecast
        forecast.enabled = self.enabled_check.isChecked()
        forecast.logistics_days = self.logistics_spin.value()
        forecast.colors = {
            name: str(button.property("color_hex"))
            for name, button in self.color_buttons.items()
        }
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            key = str(item.data(Qt.UserRole))
            performance = self.table.cellWidget(row, 5)
            logistics = self.table.cellWidget(row, 6)
            color = self.table.cellWidget(row, 7)
            value = logistics.value()
            forecast.products[key] = ShipmentForecastProductConfig(
                product_key=key,
                enabled=item.checkState() == Qt.Checked,
                performance_days=performance.value(),
                logistics_days=None if value < 0 else value,
                performance_color=str(color.property("color_hex") or ""),
                observation=self.table.item(row, 8).text().strip(),
            )

    def save(self) -> None:
        self._collect()
        self.config_service.save(self.category_config)
        QMessageBox.information(self, "Previsión", "Configuración guardada.")

    def apply(self) -> None:
        self._collect()
        self.config_service.save(self.category_config)
        self.accept()
