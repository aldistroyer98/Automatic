from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.shipment_config import (
    ProductCategoryAssignment,
    ShipmentCategoryConfig,
    ShipmentCategoryState,
)
from services.shipment_config_service import ShipmentConfigService


class ShipmentCategoryDialog(QDialog):
    def __init__(
        self,
        category_config: ShipmentCategoryState,
        config_service: ShipmentConfigService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.category_config = category_config
        self.config_service = config_service
        self._loading = False
        self.setWindowTitle("Configurar categorías")
        self.resize(980, 620)
        self._build_ui()
        self.refresh_tables()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        content = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("Categorías"))
        category_buttons = QHBoxLayout()
        for text, handler in (
            ("Nueva categoría", self.add_category),
            ("Subir", lambda: self.move_category(-1)),
            ("Bajar", lambda: self.move_category(1)),
            ("Color", self.change_category_color),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            category_buttons.addWidget(button)
        left.addLayout(category_buttons)

        self.category_table = QTableWidget(0, 3)
        self.category_table.setHorizontalHeaderLabels(("Orden", "Categoría", "Color"))
        self.category_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.category_table.currentCellChanged.connect(lambda *_args: self.refresh_products())
        left.addWidget(self.category_table, 1)
        content.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Productos de la categoría seleccionada"))
        product_buttons = QHBoxLayout()
        for text, handler in (
            ("Subir producto", lambda: self.move_product(-1)),
            ("Bajar producto", lambda: self.move_product(1)),
            ("Guardar configuración", self.save_category_config),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            product_buttons.addWidget(button)
        right.addLayout(product_buttons)

        self.product_table = QTableWidget(0, 5)
        self.product_table.setHorizontalHeaderLabels(("Orden", "CodProd", "CodEqv", "Producto", "Categoría"))
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        right.addWidget(self.product_table, 1)
        content.addLayout(right, 2)

        root.addLayout(content, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        root.addWidget(buttons)

    def refresh_tables(self) -> None:
        self._loading = True
        try:
            selected_name = self._selected_category_name()
            categories = self.category_config.sorted_categories()
            self.category_table.setRowCount(len(categories))
            selected_row = 0
            for row, category in enumerate(categories):
                if category.name == selected_name:
                    selected_row = row
                values = (row + 1, category.name, f"#{category.normalized_color()}")
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column in (0, 2):
                        item.setTextAlignment(Qt.AlignCenter)
                    if column == 2:
                        item.setBackground(QBrush(QColor(f"#{category.normalized_color()}")))
                    self.category_table.setItem(row, column, item)
            if categories:
                self.category_table.selectRow(min(selected_row, len(categories) - 1))
            self.category_table.resizeColumnsToContents()
        finally:
            self._loading = False
        self.refresh_products()

    def refresh_products(self) -> None:
        if self._loading:
            return
        category = self._selected_category()
        assignments = self._assignments_for_category(category.name if category else "")
        self._loading = True
        try:
            self.product_table.setRowCount(len(assignments))
            names = self.category_config.category_names()
            for row, assignment in enumerate(assignments):
                values = (
                    assignment.product_order + 1,
                    assignment.cod_prod,
                    assignment.cod_eqv,
                    assignment.producto,
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column == 0:
                        item.setTextAlignment(Qt.AlignCenter)
                    self.product_table.setItem(row, column, item)
                combo = QComboBox()
                combo.addItems(names)
                combo.setCurrentText(assignment.category_name)
                combo.currentTextChanged.connect(
                    lambda value, key=assignment.product_key: self.assign_product_category(key, value)
                )
                self.product_table.setCellWidget(row, 4, combo)
            self.product_table.resizeColumnsToContents()
        finally:
            self._loading = False

    def add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Nueva categoría", "Nombre de categoría:")
        name = name.strip()
        if not ok or not name:
            return
        if self.category_config.category_by_name(name) is not None:
            QMessageBox.information(self, "Categorías", "La categoría ya existe.")
            return
        self.category_config.categories.append(
            ShipmentCategoryConfig(name=name, color_hex="E7E6E6", order=len(self.category_config.categories))
        )
        self._persist_and_refresh()

    def change_category_color(self) -> None:
        category = self._selected_category()
        if category is None:
            return
        color = QColorDialog.getColor(QColor(f"#{category.normalized_color()}"), self, "Color de categoría")
        if not color.isValid():
            return
        category.color_hex = color.name().lstrip("#").upper()
        self._persist_and_refresh()

    def move_category(self, direction: int) -> None:
        selected = self._selected_category()
        if selected is None:
            return
        categories = self.category_config.sorted_categories()
        index = categories.index(selected)
        target = index + direction
        if target < 0 or target >= len(categories):
            return
        categories[index], categories[target] = categories[target], categories[index]
        for order, category in enumerate(categories):
            category.order = order
        self._persist_and_refresh()
        self.category_table.selectRow(target)

    def assign_product_category(self, key: str, category_name: str) -> None:
        if self._loading:
            return
        assignment = self.category_config.assignments.get(key)
        if assignment is None or assignment.category_name == category_name:
            return
        assignment.category_name = category_name
        assignment.product_order = self._next_product_order(category_name)
        self._persist_and_refresh()

    def move_product(self, direction: int) -> None:
        assignment = self._selected_assignment()
        if assignment is None:
            return
        group = self._assignments_for_category(assignment.category_name)
        index = group.index(assignment)
        target = index + direction
        if target < 0 or target >= len(group):
            return
        group[index], group[target] = group[target], group[index]
        for order, item in enumerate(group):
            item.product_order = order
        selected_key = group[target].product_key
        self._persist_and_refresh()
        self._select_product_key(selected_key)

    def save_category_config(self) -> None:
        self.config_service.save(self.category_config)
        QMessageBox.information(self, "Categorías", "Configuración guardada.")

    def _persist_and_refresh(self) -> None:
        self.config_service.save(self.category_config)
        self.refresh_tables()

    def _selected_category(self) -> ShipmentCategoryConfig | None:
        row = self.category_table.currentRow()
        categories = self.category_config.sorted_categories()
        if row < 0 or row >= len(categories):
            QMessageBox.information(self, "Categorías", "Selecciona una categoría.")
            return None
        return categories[row]

    def _selected_category_name(self) -> str:
        row = self.category_table.currentRow()
        item = self.category_table.item(row, 1) if row >= 0 else None
        return item.text() if item is not None else ""

    def _selected_assignment(self) -> ProductCategoryAssignment | None:
        row = self.product_table.currentRow()
        assignments = self._assignments_for_category(self._selected_category_name())
        if row < 0 or row >= len(assignments):
            QMessageBox.information(self, "Categorías", "Selecciona un producto.")
            return None
        return assignments[row]

    def _assignments_for_category(self, category_name: str) -> list[ProductCategoryAssignment]:
        return sorted(
            (
                assignment
                for assignment in self.category_config.assignments.values()
                if assignment.category_name == category_name
            ),
            key=lambda item: (item.product_order, item.producto.casefold()),
        )

    def _next_product_order(self, category_name: str) -> int:
        return max(
            (
                assignment.product_order
                for assignment in self.category_config.assignments.values()
                if assignment.category_name == category_name
            ),
            default=-1,
        ) + 1

    def _select_product_key(self, key: str) -> None:
        for row, assignment in enumerate(self._assignments_for_category(self._selected_category_name())):
            if assignment.product_key == key:
                self.product_table.selectRow(row)
                break
