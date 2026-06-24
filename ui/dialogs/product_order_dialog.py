from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QStyle, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from models.equivalence import EquivalenceState, ReagentProduct
from services.category_manager import CategoryManager
from services.equivalence_service import normalize_description
from ui.common.table_helpers import (
    center_table_item,
    clear_selection_safe,
    make_readonly_item,
    resize_columns_by_ratio,
)


class ProductOrderDialog(QDialog):
    def __init__(self, state: EquivalenceState, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self._loading = False
        self._active_table = "category"
        self.search_text = ""
        self.setWindowTitle("Categoría")
        self.resize(980, 600)
        self._build_ui()
        self.refresh()
        QTimer.singleShot(0, self._resize_columns)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Buscar:"))
        self.search_field = QLineEdit(self)
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._search_changed)
        controls.addWidget(self.search_field, 2)
        controls.addWidget(QLabel("Categoría:"))
        self.target_category = QComboBox(self)
        controls.addWidget(self.target_category, 1)
        move_button = QPushButton("Mover", self)
        move_button.clicked.connect(self.move_selected_products)
        controls.addWidget(move_button)
        root.addLayout(controls)

        content = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Categorías"))
        self.category_table = QTableWidget(0, 3, self)
        self.category_table.setHorizontalHeaderLabels(("Orden", "Categoría", "Color"))
        self.category_table.verticalHeader().setVisible(False)
        self.category_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.category_table.itemSelectionChanged.connect(self._category_selected)
        left.addWidget(self.category_table, 1)
        category_actions = QHBoxLayout()
        for text, handler in (
            ("Nuevo", self.add_category),
            ("Editar", self.edit_category),
            ("Eliminar", self.delete_category),
            ("Color", self.change_color),
        ):
            button = QPushButton(text, self)
            button.clicked.connect(handler)
            category_actions.addWidget(button)
        left.addLayout(category_actions)
        content.addLayout(left, 4)

        move_box = QVBoxLayout()
        move_box.addStretch(1)
        for icon, action, tooltip in (
            (QStyle.SP_MediaSkipBackward, "first", "Mover al inicio"),
            (QStyle.SP_ArrowUp, "up", "Subir"),
            (QStyle.SP_ArrowDown, "down", "Bajar"),
            (QStyle.SP_MediaSkipForward, "last", "Mover al final"),
        ):
            button = QPushButton(self)
            button.setIcon(self.style().standardIcon(icon))
            button.setFixedWidth(44)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda _checked=False, value=action: self.move_selected_to(value))
            move_box.addWidget(button)
        move_box.addStretch(1)
        content.addLayout(move_box)

        right = QVBoxLayout()
        right.addWidget(QLabel("Productos de la categoría seleccionada"))
        self.product_table = QTableWidget(0, 4, self)
        self.product_table.setHorizontalHeaderLabels(("Orden", "CodProd", "CodEqv", "Producto"))
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.product_table.itemSelectionChanged.connect(lambda: self._mark_active("product"))
        self.product_table.itemChanged.connect(self.product_order_changed)
        right.addWidget(self.product_table, 1)
        content.addLayout(right, 9)
        root.addLayout(content, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Close).setText("Salir")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def refresh(self) -> None:
        selected_category = self._selected_category_name()
        self._loading = True
        try:
            categories = self._categories()
            self.target_category.clear()
            for category in categories:
                self.target_category.addItem(
                    CategoryManager.visible_name(category["name"]),
                    category["name"],
                )
            self.category_table.setRowCount(len(categories))
            selected_row = 0
            for row, category in enumerate(categories):
                if category["name"] == selected_category:
                    selected_row = row
                values = (
                    row + 1,
                    CategoryManager.visible_name(category["name"]),
                    category["color"],
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.UserRole, category["name"])
                    if column in (0, 2):
                        center_table_item(item)
                    if column == 2:
                        item.setBackground(QColor(f"#{category['color']}"))
                    self.category_table.setItem(row, column, item)
            if categories:
                self.category_table.selectRow(min(selected_row, len(categories) - 1))
        finally:
            self._loading = False
        self.refresh_products()
        QTimer.singleShot(0, self._resize_columns)

    def refresh_products(self, selected_key: str = "") -> None:
        products = self._products_for_category(self._selected_category_name())
        self._loading = True
        try:
            self.product_table.setRowCount(len(products))
            selected_row = 0
            for row, product in enumerate(products):
                if product.key == selected_key:
                    selected_row = row
                values = (row + 1, product.cod_prod, product.cod_eqv, product.product)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.UserRole, product.key)
                    if column != 0:
                        item = make_readonly_item(
                            value,
                            alignment=Qt.AlignLeft | Qt.AlignVCenter
                            if column == 3
                            else Qt.AlignCenter,
                        )
                        item.setData(Qt.UserRole, product.key)
                    else:
                        center_table_item(item)
                    self.product_table.setItem(row, column, item)
            if products:
                self.product_table.selectRow(min(selected_row, len(products) - 1))
            else:
                clear_selection_safe(self.product_table)
        finally:
            self._loading = False

    def add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Nueva categoría", "Categoría:")
        name = CategoryManager.internal_name(name.strip())
        if not ok or not name:
            return
        if CategoryManager.contains_name(
            (item["name"] for item in self._categories()),
            name,
        ):
            QMessageBox.information(self, "Categorías", "La categoría ya existe.")
            return
        self._categories().append({"name": name, "color": "E7E6E6"})
        self.refresh()

    def edit_category(self) -> None:
        row = self.category_table.currentRow()
        categories = self._categories()
        if row < 0 or row >= len(categories):
            return
        old_name = categories[row]["name"]
        name, ok = QInputDialog.getText(
            self,
            "Editar categoría",
            "Categoría:",
            text=CategoryManager.visible_name(old_name),
        )
        if not ok or not name.strip():
            return
        new_name = CategoryManager.internal_name(name.strip())
        categories[row]["name"] = new_name
        for product in self.state.products:
            if product.category == old_name:
                product.category = new_name
        self.refresh()

    def delete_category(self) -> None:
        row = self.category_table.currentRow()
        categories = self._categories()
        if row < 0 or row >= len(categories):
            return
        name = categories[row]["name"]
        if normalize_description(name) == "sin categoria":
            QMessageBox.information(self, "Categorías", "No se puede eliminar Sin Categoría.")
            return
        categories.pop(row)
        for product in self.state.products:
            if product.category == name:
                product.category = "Sin Categoría"
        self.refresh()

    def change_color(self) -> None:
        row = self.category_table.currentRow()
        categories = self._categories()
        if row < 0 or row >= len(categories):
            return
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            categories[row]["color"] = color.name().lstrip("#").upper()
            self.refresh()

    def move_selected_products(self) -> None:
        target = str(self.target_category.currentData() or "Sin Categoría")
        selected = self._selected_products()
        for product in selected:
            product.category = target
        self._normalize_order_by_category()
        self.refresh_products()

    def move_selected_to(self, action: str) -> None:
        if self._active_table == "product" and self.product_table.currentRow() >= 0:
            products = self._products_for_category(
                self._selected_category_name(),
                include_search=False,
            )
            selected = self._selected_products()
            if not selected or selected[0] not in products:
                return
            row = products.index(selected[0])
            target = CategoryManager.target_index(row, len(products), action)
            if row != target:
                product = products.pop(row)
                products.insert(target, product)
                CategoryManager.normalize_order(
                    products,
                    lambda current, order: setattr(current, "order", order),
                )
                self.refresh_products(product.key)
            return
        row = self.category_table.currentRow()
        categories = self._categories()
        if row < 0 or row >= len(categories):
            return
        target = CategoryManager.target_index(row, len(categories), action)
        if row != target:
            category = categories.pop(row)
            categories.insert(target, category)
            self.refresh()
            self.category_table.selectRow(target)

    def product_order_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 0:
            return
        products = self._products_for_category(
            self._selected_category_name(),
            include_search=False,
        )
        product = self._product_by_key(str(item.data(Qt.UserRole) or ""))
        if product is None:
            return
        try:
            target = max(0, min(len(products) - 1, int(item.text()) - 1))
        except ValueError:
            self.refresh()
            return
        current = products.index(product)
        products.pop(current)
        products.insert(target, product)
        CategoryManager.normalize_order(
            products,
            lambda current, order: setattr(current, "order", order),
        )
        self.refresh_products(product.key)
        self.product_table.selectRow(target)

    def _category_selected(self) -> None:
        if self._loading:
            return
        self._mark_active("category")
        self.refresh_products()

    def _mark_active(self, table_name: str) -> None:
        if not self._loading:
            self._active_table = table_name

    def _search_changed(self, text: str) -> None:
        self.search_text = text
        self.refresh_products()

    def accept(self) -> None:
        self._normalize_order_by_category()
        parent = self.parent()
        if hasattr(parent, "_load_state_to_products"):
            parent._load_state_to_products()
        super().accept()

    def _categories(self) -> list[dict]:
        categories = self.state.settings.setdefault("product_categories", [])
        if not categories:
            categories.extend([
                {"name": "Control de Calidad", "color": "DDEBF7"},
                {"name": "Reactivo Principal", "color": "FCE4D6"},
                {"name": "Consumible", "color": "E2F0D9"},
                {"name": "Sin Categoría", "color": "E7E6E6"},
            ])
        return categories

    def _selected_products(self) -> list[ReagentProduct]:
        keys = {
            str(self.product_table.item(index.row(), 0).data(Qt.UserRole) or "")
            for index in self.product_table.selectionModel().selectedRows()
        }
        return [product for product in self.state.products if product.key in keys]

    def _selected_category_name(self) -> str:
        row = self.category_table.currentRow()
        item = self.category_table.item(row, 1) if row >= 0 else None
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def _product_by_key(self, key: str) -> ReagentProduct | None:
        return next((product for product in self.state.products if product.key == key), None)

    def _products_for_category(
        self,
        category: str,
        *,
        include_search: bool = True,
    ) -> list[ReagentProduct]:
        needle = normalize_description(self.search_text) if include_search else ""
        return sorted(
            (
                product
                for product in self.state.products
                if (product.category or "Sin Categoría") == category
                and (
                    not needle
                    or needle in normalize_description(
                        f"{product.cod_prod} {product.cod_eqv} {product.product}"
                    )
                )
            ),
            key=lambda item: (item.order, item.product.casefold()),
        )

    def _normalize_order_by_category(self) -> None:
        for category in (item["name"] for item in self._categories()):
            CategoryManager.normalize_order(
                self._products_for_category(category, include_search=False),
                lambda product, order: setattr(product, "order", order),
            )

    def _resize_columns(self) -> None:
        resize_columns_by_ratio(self.category_table, (2, 4, 3))
        resize_columns_by_ratio(self.product_table, (2, 3, 3, 8))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_columns()

