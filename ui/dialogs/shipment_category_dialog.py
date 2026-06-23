from __future__ import annotations

from collections.abc import Collection

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
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
    CATEGORY_WITHOUT_CATEGORY,
    DEFAULT_CATEGORY_COLORS,
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
        active_product_keys: Collection[str],
        lines: Collection[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.category_config = category_config
        self.config_service = config_service
        self.active_product_keys = set(active_product_keys)
        self.lines = tuple(sorted({line for line in (lines or ()) if line}))
        self._loading = False
        self._active_table = ""
        self.line_filter = ""
        self.setWindowTitle("Configurar categorías")
        self.resize(1040, 620)
        self._build_ui()
        self.refresh_tables()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Línea comercial:"))
        self.line_combo = QComboBox(self)
        self.line_combo.addItem("Todos", "")
        for line in self.lines:
            self.line_combo.addItem(line, line)
        self.line_combo.currentIndexChanged.connect(self._line_filter_changed)
        filter_row.addWidget(self.line_combo, 1)
        root.addLayout(filter_row)

        content = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("Categorías"))
        self.category_table = QTableWidget(0, 3)
        self.category_table.setHorizontalHeaderLabels(("Orden", "Categoría", "Color"))
        self.category_table.verticalHeader().setVisible(False)
        self.category_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.category_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.category_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.category_table.setColumnWidth(0, 58)
        self.category_table.currentCellChanged.connect(lambda *_args: self.refresh_products())
        self.category_table.itemSelectionChanged.connect(lambda: self._mark_active("category"))
        left.addWidget(self.category_table, 1)
        category_actions = QHBoxLayout()
        new_button = QPushButton("Nueva categoría")
        new_button.clicked.connect(self.add_category)
        color_button = QPushButton("Cambiar color")
        color_button.clicked.connect(self.change_category_color)
        delete_button = QPushButton("Eliminar categoría")
        delete_button.clicked.connect(self.delete_category)
        category_actions.addWidget(new_button)
        category_actions.addWidget(color_button)
        category_actions.addWidget(delete_button)
        left.addLayout(category_actions)
        content.addLayout(left, 4)

        move_box = QVBoxLayout()
        move_box.addStretch(1)
        for text, action in (
            ("⏫", "first"),
            ("⬆", "up"),
            ("⬇", "down"),
            ("⏬", "last"),
        ):
            button = QPushButton(text)
            button.setFixedWidth(48)
            button.clicked.connect(lambda _checked=False, value=action: self.move_selected_to(value))
            move_box.addWidget(button)
        move_box.addStretch(1)
        content.addLayout(move_box)

        right = QVBoxLayout()
        right.addWidget(QLabel("Productos de la categoría seleccionada"))
        self.product_table = QTableWidget(0, 3)
        self.product_table.setHorizontalHeaderLabels(("Orden", "Producto", "Categoría"))
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.product_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.product_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.product_table.setColumnWidth(0, 58)
        self.product_table.setColumnWidth(2, 190)
        self.product_table.itemSelectionChanged.connect(lambda: self._mark_active("product"))
        right.addWidget(self.product_table, 1)
        product_actions = QHBoxLayout()
        product_actions.addStretch(1)
        save_button = QPushButton("Guardar")
        save_button.clicked.connect(self.save_category_config)
        exit_button = QPushButton("Salir")
        exit_button.clicked.connect(self.accept)
        product_actions.addWidget(save_button)
        product_actions.addWidget(exit_button)
        right.addLayout(product_actions)
        content.addLayout(right, 7)

        root.addLayout(content, 1)

    def refresh_tables(self, selected_category: str = "", selected_product_key: str = "") -> None:
        self._loading = True
        try:
            categories = self._visible_categories()
            self.category_table.setRowCount(len(categories))
            selected_row = 0
            for row, category in enumerate(categories):
                if category.name == selected_category:
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
        finally:
            self._loading = False
        self.refresh_products(selected_product_key)

    def refresh_products(self, selected_product_key: str = "") -> None:
        if self._loading:
            return
        category = self._selected_category()
        assignments = self._assignments_for_category(category.name if category else "")
        self._loading = True
        try:
            self.product_table.setRowCount(len(assignments))
            names = self.category_config.category_names()
            selected_row = 0
            for row, assignment in enumerate(assignments):
                if assignment.product_key == selected_product_key:
                    selected_row = row
                order_item = QTableWidgetItem(str(assignment.product_order + 1))
                order_item.setTextAlignment(Qt.AlignCenter)
                product_item = QTableWidgetItem(assignment.producto)
                product_item.setToolTip(assignment.producto)
                self.product_table.setItem(row, 0, order_item)
                self.product_table.setItem(row, 1, product_item)
                combo = QComboBox()
                combo.addItems(names)
                combo.setCurrentText(assignment.category_name)
                combo.currentTextChanged.connect(
                    lambda value, key=assignment.product_key: self.assign_product_category(key, value)
                )
                self.product_table.setCellWidget(row, 2, combo)
            if assignments:
                self.product_table.selectRow(min(selected_row, len(assignments) - 1))
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
        self._persist_and_refresh(name)

    def change_category_color(self) -> None:
        category = self._selected_category()
        if category is None:
            return
        color = QColorDialog.getColor(QColor(f"#{category.normalized_color()}"), self, "Color de categoría")
        if not color.isValid():
            return
        category.color_hex = color.name().lstrip("#").upper()
        self._persist_and_refresh(category.name)

    def delete_category(self) -> None:
        category = self._selected_category()
        if category is None:
            return
        if category.name == CATEGORY_WITHOUT_CATEGORY:
            QMessageBox.information(self, "Categorías", "No se puede eliminar Sin Categoría.")
            return
        reply = QMessageBox.question(
            self,
            "Eliminar categoría",
            f'¿Deseas eliminar esta categoría? Los productos asociados se moverán a "{CATEGORY_WITHOUT_CATEGORY}".',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.category_config.categories = [
            item for item in self.category_config.categories
            if item.name != category.name
        ]
        next_order = self._next_product_order(CATEGORY_WITHOUT_CATEGORY)
        for assignment in self.category_config.assignments.values():
            if assignment.category_name == category.name:
                assignment.category_name = CATEGORY_WITHOUT_CATEGORY
                assignment.product_order = next_order
                next_order += 1
        for order, item in enumerate(self.category_config.sorted_categories()):
            item.order = order
        self._persist_and_refresh(CATEGORY_WITHOUT_CATEGORY)

    def move_category_to(self, action: str) -> None:
        selected = self._selected_category()
        if selected is None:
            return
        categories = self.category_config.sorted_categories()
        index = categories.index(selected)
        target = self._target_index(index, len(categories), action)
        if target == index:
            return
        item = categories.pop(index)
        categories.insert(target, item)
        for order, category in enumerate(categories):
            category.order = order
        self._persist_and_refresh(selected.name)

    def move_selected_to(self, action: str) -> None:
        if self._active_table == "product" and self._selected_assignment(show_message=False) is not None:
            self.move_product_to(action)
            return
        if self._active_table == "category" and self._selected_category(show_message=False) is not None:
            self.move_category_to(action)
            return
        if self._selected_assignment(show_message=False) is not None:
            self.move_product_to(action)
            return
        if self._selected_category(show_message=False) is not None:
            self.move_category_to(action)
            return
        QMessageBox.information(self, "Categorías", "Selecciona una categoría o producto.")

    def assign_product_category(self, key: str, category_name: str) -> None:
        if self._loading:
            return
        assignment = self.category_config.assignments.get(key)
        if assignment is None or assignment.category_name == category_name:
            return
        current_category = self._selected_category_name()
        assignment.category_name = category_name
        assignment.product_order = self._next_product_order(category_name)
        self._persist_and_refresh(current_category)

    def move_product_to(self, action: str) -> None:
        assignment = self._selected_assignment()
        if assignment is None:
            return
        group = self._assignments_for_category(assignment.category_name)
        index = group.index(assignment)
        target = self._target_index(index, len(group), action)
        if target == index:
            return
        item = group.pop(index)
        group.insert(target, item)
        for order, current in enumerate(group):
            current.product_order = order
        self._persist_and_refresh(assignment.category_name, assignment.product_key)

    def save_category_config(self) -> None:
        self.config_service.save(self.category_config)
        QMessageBox.information(self, "Categorías", "Configuración guardada.")

    def _persist_and_refresh(self, selected_category: str = "", selected_product_key: str = "") -> None:
        self.config_service.save(self.category_config)
        self.refresh_tables(selected_category, selected_product_key)

    def _visible_categories(self) -> list[ShipmentCategoryConfig]:
        active_names = {
            assignment.category_name
            for assignment in self._active_assignments()
        }
        result = []
        for category in self.category_config.sorted_categories():
            is_custom = category.name not in DEFAULT_CATEGORY_COLORS
            if category.name in active_names or is_custom or category.name == CATEGORY_WITHOUT_CATEGORY:
                result.append(category)
        return result

    def _mark_active(self, table_name: str) -> None:
        if not self._loading:
            self._active_table = table_name

    def _selected_category(self, show_message: bool = True) -> ShipmentCategoryConfig | None:
        row = self.category_table.currentRow()
        categories = self._visible_categories()
        if row < 0 or row >= len(categories):
            if show_message and categories:
                QMessageBox.information(self, "Categorías", "Selecciona una categoría.")
            return None
        return categories[row]

    def _selected_category_name(self) -> str:
        row = self.category_table.currentRow()
        item = self.category_table.item(row, 1) if row >= 0 else None
        return item.text() if item is not None else ""

    def _selected_assignment(self, show_message: bool = True) -> ProductCategoryAssignment | None:
        row = self.product_table.currentRow()
        assignments = self._assignments_for_category(self._selected_category_name())
        if row < 0 or row >= len(assignments):
            if show_message:
                QMessageBox.information(self, "Categorías", "Selecciona un producto.")
            return None
        return assignments[row]

    def _active_assignments(self) -> list[ProductCategoryAssignment]:
        return [
            assignment
            for assignment in self.category_config.assignments.values()
            if assignment.product_key in self.active_product_keys
            and (not self.line_filter or assignment.linea == self.line_filter)
        ]

    def _assignments_for_category(self, category_name: str) -> list[ProductCategoryAssignment]:
        return sorted(
            (
                assignment
                for assignment in self._active_assignments()
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

    @staticmethod
    def _target_index(index: int, length: int, action: str) -> int:
        if action == "first":
            return 0
        if action == "up":
            return max(0, index - 1)
        if action == "down":
            return min(length - 1, index + 1)
        if action == "last":
            return length - 1
        return index

    def _line_filter_changed(self) -> None:
        self.line_filter = str(self.line_combo.currentData() or "")
        self.refresh_tables()
