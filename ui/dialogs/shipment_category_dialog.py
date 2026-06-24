from __future__ import annotations

from collections.abc import Collection

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
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
    normalize_text,
)
from services.shipment_config_service import ShipmentConfigService
from services.category_manager import CategoryManager
from ui.common.table_helpers import (
    center_table_item,
    clear_selection_safe,
    make_readonly_item,
    resize_columns_by_ratio,
)
from ui.window_sizes import DIALOG_3_4, apply_fixed_window_size


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
        self.product_search = ""
        self.setWindowTitle("Configurar categorías")
        apply_fixed_window_size(self, DIALOG_3_4)
        self._build_ui()
        self.refresh_tables()
        QTimer.singleShot(0, self._resize_tables)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        top_row = QGridLayout()

        line_controls = QHBoxLayout()
        line_controls.addWidget(QLabel("Línea:"), 2)
        self.line_combo = QComboBox(self)
        self.line_combo.addItem("Todos", "")
        for line in self.lines:
            self.line_combo.addItem(line, line)
        self.line_combo.currentIndexChanged.connect(self._line_filter_changed)
        line_controls.addWidget(self.line_combo, 6)
        top_row.addLayout(line_controls, 0, 0)

        product_controls = QHBoxLayout()
        product_controls.addWidget(QLabel("Buscar:"), 2)
        self.search_field = QLineEdit(self)
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._product_search_changed)
        product_controls.addWidget(self.search_field, 8)
        product_controls.addWidget(QLabel("Categoría:"), 2)
        self.bulk_category_combo = QComboBox(self)
        product_controls.addWidget(self.bulk_category_combo, 6)
        move_button = QPushButton("Mover", self)
        move_button.clicked.connect(self.move_selected_products_to_category)
        product_controls.addWidget(move_button, 2)
        top_row.addLayout(product_controls, 0, 2)
        top_row.setColumnStretch(0, 9)
        top_row.setColumnMinimumWidth(1, 45)
        top_row.setColumnStretch(2, 16)
        root.addLayout(top_row)

        content = QGridLayout()

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
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.category_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.category_table.currentCellChanged.connect(lambda *_args: self.refresh_products())
        self.category_table.itemSelectionChanged.connect(lambda: self._mark_active("category"))
        left.addWidget(self.category_table, 1)
        category_actions = QHBoxLayout()
        new_button = QPushButton("Nuevo")
        new_button.clicked.connect(self.add_category)
        delete_button = QPushButton("Eliminar")
        delete_button.clicked.connect(self.delete_category)
        color_button = QPushButton("Color")
        color_button.clicked.connect(self.change_category_color)
        for button in (new_button, delete_button, color_button):
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        category_actions.addWidget(new_button, 1)
        category_actions.addWidget(delete_button, 1)
        category_actions.addWidget(color_button, 1)
        left.addLayout(category_actions)
        content.addLayout(left, 0, 0)

        move_box = QVBoxLayout()
        move_box.addStretch(1)
        for text, action in (
            ("⏫", "first"),
            ("⬆", "up"),
            ("⬇", "down"),
            ("⏬", "last"),
        ):
            button = QPushButton(text)
            button.setFixedWidth(45)
            button.clicked.connect(lambda _checked=False, value=action: self.move_selected_to(value))
            move_box.addWidget(button)
        move_box.addStretch(1)
        content.addLayout(move_box, 0, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Productos de la categoría seleccionada"))
        self.product_table = QTableWidget(0, 4)
        self.product_table.setHorizontalHeaderLabels(("Orden", "CodProd", "CodEqv", "Producto"))
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.product_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.product_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.product_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.product_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.product_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.product_table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.product_table.itemChanged.connect(self._product_order_changed)
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
        content.addLayout(right, 0, 2)
        content.setColumnStretch(0, 9)
        content.setColumnMinimumWidth(1, 45)
        content.setColumnStretch(2, 16)

        root.addLayout(content, 1)
        self._resize_tables()

    def refresh_tables(self, selected_category: str = "", selected_product_key: str = "") -> None:
        self._loading = True
        try:
            categories = self._visible_categories()
            self._refresh_bulk_category_combo()
            self.category_table.setRowCount(len(categories))
            selected_row = 0
            for row, category in enumerate(categories):
                if category.name == selected_category:
                    selected_row = row
                values = (
                    row + 1,
                    CategoryManager.visible_name(category.name),
                    f"#{category.normalized_color()}",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.UserRole, category.name)
                    if column in (0, 2):
                        center_table_item(item)
                    if column == 2:
                        item.setBackground(QBrush(QColor(f"#{category.normalized_color()}")))
                    self.category_table.setItem(row, column, item)
            if categories:
                self.category_table.selectRow(min(selected_row, len(categories) - 1))
            self._resize_tables()
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
            selected_row = 0
            for row, assignment in enumerate(assignments):
                if assignment.product_key == selected_product_key:
                    selected_row = row
                order_item = center_table_item(QTableWidgetItem(str(assignment.product_order + 1)))
                order_item.setData(Qt.UserRole, assignment.product_key)
                code_item = make_readonly_item(assignment.cod_prod)
                equivalent_item = make_readonly_item(assignment.cod_eqv)
                product_item = make_readonly_item(assignment.producto)
                product_item.setToolTip(assignment.producto)
                self.product_table.setItem(row, 0, order_item)
                self.product_table.setItem(row, 1, code_item)
                self.product_table.setItem(row, 2, equivalent_item)
                self.product_table.setItem(row, 3, product_item)
            if assignments:
                self.product_table.selectRow(min(selected_row, len(assignments) - 1))
            else:
                clear_selection_safe(self.product_table)
            self._resize_tables()
        finally:
            self._loading = False

    def add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Nueva categoría", "Nombre de categoría:")
        name = CategoryManager.internal_name(name.strip())
        if not ok or not name:
            return
        if CategoryManager.contains_name(self.category_config.category_names(), name):
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
            f'¿Deseas eliminar esta categoría? Los productos asociados se moverán a "{CategoryManager.visible_name(CATEGORY_WITHOUT_CATEGORY)}".',
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
        target = CategoryManager.target_index(index, len(categories), action)
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

    def move_selected_products_to_category(self) -> None:
        target_category = str(self.bulk_category_combo.currentData() or "").strip()
        if not target_category or self.category_config.category_by_name(target_category) is None:
            QMessageBox.information(self, "Categorías", "Selecciona una categoría destino.")
            return
        assignments = self._selected_assignments()
        if not assignments:
            return

        current_category = self._selected_category_name()
        next_order = self._next_product_order(target_category)
        changed = False
        for assignment in assignments:
            if assignment.category_name == target_category:
                continue
            assignment.category_name = target_category
            assignment.product_order = next_order
            next_order += 1
            changed = True
        if changed:
            self._normalize_product_order(current_category)
            self._normalize_product_order(target_category)
            self._persist_and_refresh(current_category)

    def move_product_to(self, action: str) -> None:
        assignment = self._selected_assignment()
        if assignment is None:
            return
        group = self._assignments_for_category(assignment.category_name, include_search=False)
        index = group.index(assignment)
        target = CategoryManager.target_index(index, len(group), action)
        if target == index:
            return
        item = group.pop(index)
        group.insert(target, item)
        for order, current in enumerate(group):
            current.product_order = order
        self._persist_and_refresh(assignment.category_name, assignment.product_key)

    def _product_order_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 0:
            return
        key = str(item.data(Qt.UserRole) or "")
        assignment = self.category_config.assignments.get(key)
        if assignment is None:
            return
        try:
            requested_order = int(item.text())
        except ValueError:
            self.refresh_products(assignment.product_key)
            return
        group = self._assignments_for_category(assignment.category_name, include_search=False)
        if not group:
            return
        target_index = max(0, min(len(group) - 1, requested_order - 1))
        current_index = group.index(assignment)
        if current_index == target_index:
            if assignment.product_order != target_index:
                self._normalize_product_order(assignment.category_name)
                self._persist_and_refresh(assignment.category_name, assignment.product_key)
            return
        group.pop(current_index)
        group.insert(target_index, assignment)
        for order, current in enumerate(group):
            current.product_order = order
        self._persist_and_refresh(assignment.category_name, assignment.product_key)

    def save_category_config(self) -> None:
        self.config_service.save(self.category_config)
        QMessageBox.information(self, "Categorías", "Configuración guardada.")

    def _persist_and_refresh(self, selected_category: str = "", selected_product_key: str = "") -> None:
        self.config_service.save(self.category_config)
        self.refresh_tables(selected_category, selected_product_key)

    def _refresh_bulk_category_combo(self) -> None:
        current = str(self.bulk_category_combo.currentData() or "")
        self.bulk_category_combo.blockSignals(True)
        self.bulk_category_combo.clear()
        for name in self.category_config.category_names():
            self.bulk_category_combo.addItem(CategoryManager.visible_name(name), name)
        index = self.bulk_category_combo.findData(current)
        self.bulk_category_combo.setCurrentIndex(index if index >= 0 else 0)
        self.bulk_category_combo.blockSignals(False)

    def _normalize_product_order(self, category_name: str) -> None:
        CategoryManager.normalize_order(
            self._assignments_for_category(category_name, include_search=False),
            lambda assignment, order: setattr(assignment, "product_order", order),
        )

    def _visible_categories(self) -> list[ShipmentCategoryConfig]:
        active_names = {
            assignment.category_name
            for assignment in self._active_assignments(include_search=False)
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
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def _selected_assignment(self, show_message: bool = True) -> ProductCategoryAssignment | None:
        row = self.product_table.currentRow()
        assignments = self._assignments_for_category(self._selected_category_name())
        if row < 0 or row >= len(assignments):
            if show_message:
                QMessageBox.information(self, "Categorías", "Selecciona un producto.")
            return None
        return assignments[row]

    def _selected_assignments(self, show_message: bool = True) -> list[ProductCategoryAssignment]:
        assignments = self._assignments_for_category(self._selected_category_name())
        selection_model = self.product_table.selectionModel()
        rows = []
        if selection_model is not None:
            rows = sorted({index.row() for index in selection_model.selectedRows()})
        if not rows and self.product_table.currentRow() >= 0:
            rows = [self.product_table.currentRow()]
        result = [
            assignments[row]
            for row in rows
            if 0 <= row < len(assignments)
        ]
        if not result and show_message:
            QMessageBox.information(self, "Categorías", "Selecciona uno o más productos.")
        return result

    def _active_assignments(self, *, include_search: bool = True) -> list[ProductCategoryAssignment]:
        search = normalize_text(self.product_search) if include_search else ""
        return [
            assignment
            for assignment in self.category_config.assignments.values()
            if assignment.product_key in self.active_product_keys
            and (not self.line_filter or assignment.linea == self.line_filter)
            and (
                not search
                or search in normalize_text(
                    f"{assignment.cod_prod} {assignment.cod_eqv} {assignment.producto}"
                )
            )
        ]

    def _assignments_for_category(
        self,
        category_name: str,
        *,
        include_search: bool = True,
    ) -> list[ProductCategoryAssignment]:
        return sorted(
            (
                assignment
                for assignment in self._active_assignments(include_search=include_search)
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

    def _line_filter_changed(self) -> None:
        self.line_filter = str(self.line_combo.currentData() or "")
        self.refresh_tables()

    def _product_search_changed(self, text: str) -> None:
        self.product_search = text
        self.refresh_products()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_tables()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._resize_tables)

    def _resize_tables(self) -> None:
        if not hasattr(self, "category_table") or not hasattr(self, "product_table"):
            return
        resize_columns_by_ratio(self.category_table, (2, 4, 3))
        resize_columns_by_ratio(self.product_table, (2, 3, 3, 8))
