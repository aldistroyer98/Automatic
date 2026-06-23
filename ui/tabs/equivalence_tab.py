from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QComboBox,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.paths import get_app_paths
from models.equivalence import EquivalenceResult, EquivalenceState, ImportPreviewRow, ReagentProduct, TenderTest
from services.equivalence_service import EquivalenceService, normalize_description


class NonNegativeNumberDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        validator = QDoubleValidator(0.0, 999999999999.0, 6, editor)
        validator.setNotation(QDoubleValidator.StandardNotation)
        editor.setValidator(validator)
        return editor


class AlertsDialog(QDialog):
    def __init__(self, warnings: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Alertas de equivalencia")
        self.resize(760, 460)
        root = QVBoxLayout(self)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setPlainText("\n".join(warnings) if warnings else "No hay alertas pendientes")
        root.addWidget(self.text, 1)
        close_button = QPushButton("Cerrar", self)
        close_button.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_button)
        root.addLayout(row)


class ImportPreviewDialog(QDialog):
    CRITICAL_STATUSES = {"Fila incompleta", "Revisar código", "Revisar cantidad"}

    def __init__(
        self,
        tab: "EquivalenceTab",
        path: str | Path,
        rows: list[ImportPreviewRow],
    ) -> None:
        super().__init__(tab)
        self.tab = tab
        self.path = Path(path)
        self.accepted_tests: list[TenderTest] = []
        self._loading = False
        self.setWindowTitle("Revision de importacion")
        self.resize(1040, 620)
        self._build_ui()
        self._load_rows(rows)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Vista previa editable"))

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(("Código SAP", "Descripción", "Cantidad", "Estado", "Observación"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 160)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._item_changed)
        root.addWidget(self.table, 1)

        edit_row = QHBoxLayout()
        add_button = QPushButton("Agregar fila", self)
        add_button.clicked.connect(self.add_row)
        delete_button = QPushButton("Eliminar fila", self)
        delete_button.clicked.connect(self.delete_rows)
        manual_button = QPushButton("Corregir manualmente", self)
        manual_button.clicked.connect(self.edit_current_cell)
        edit_row.addWidget(add_button)
        edit_row.addWidget(delete_button)
        edit_row.addWidget(manual_button)
        edit_row.addStretch(1)
        root.addLayout(edit_row)

        action_row = QHBoxLayout()
        confirm_button = QPushButton("Confirmar carga", self)
        confirm_button.clicked.connect(self.confirm_load)
        reprocess_button = QPushButton(
            "Recargar CSV" if self.path.suffix.lower() == ".csv" else "Reprocesar imagen",
            self,
        )
        reprocess_button.clicked.connect(self.reprocess)
        export_button = QPushButton("Exportar revision", self)
        export_button.clicked.connect(self.export_review)
        cancel_button = QPushButton("Cancelar", self)
        cancel_button.clicked.connect(self.reject)
        for button in (confirm_button, reprocess_button, export_button):
            action_row.addWidget(button)
        action_row.addStretch(1)
        action_row.addWidget(cancel_button)
        root.addLayout(action_row)

    def add_row(self) -> None:
        self._append_row(ImportPreviewRow(status="Fila incompleta"))
        self.table.selectRow(self.table.rowCount() - 1)
        self.edit_current_cell()

    def delete_rows(self) -> None:
        EquivalenceTab._delete_selected_rows(self.table)

    def edit_current_cell(self) -> None:
        row = self.table.currentRow()
        column = self.table.currentColumn()
        if row < 0:
            return
        if column not in (0, 1, 2):
            column = 0
            self.table.setCurrentCell(row, column)
        item = self.table.item(row, column)
        if item is not None:
            self.table.editItem(item)

    def reprocess(self) -> None:
        try:
            if self.path.suffix.lower() == ".csv":
                rows = [
                    self.tab.service.validate_import_row(test.sap_code, test.description, test.quantity)
                    for test in self.tab.service.load_tender_file(self.path)
                ]
            else:
                rows, _text = self.tab.service.extract_import_preview(self.path)
        except RuntimeError as exc:
            QMessageBox.information(
                self,
                "OCR no disponible",
                f"{exc}\n\nPuedes usar pegado manual, Excel/CSV o edicion manual.",
            )
            return
        except Exception as exc:
            QMessageBox.critical(self, "Error al reprocesar", str(exc))
            return
        self._load_rows(rows)

    def export_review(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar revision",
            "Revision_importacion.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not path:
            return
        try:
            output = self.tab.service.export_import_review(path, self._rows_from_table())
            QMessageBox.information(self, "Revision", f"Archivo generado correctamente:\n{output}")
        except Exception as exc:
            QMessageBox.critical(self, "Error al exportar revision", str(exc))

    def confirm_load(self) -> None:
        rows = self._rows_from_table()
        critical = [row for row in rows if row.status in self.CRITICAL_STATUSES]
        if critical:
            QMessageBox.warning(
                self,
                "Revision requerida",
                "Corrige o elimina las filas en rojo antes de confirmar la carga.",
            )
            return
        doubtful = [row for row in rows if row.status != "OK"]
        if doubtful:
            answer = QMessageBox.warning(
                self,
                "Filas dudosas",
                "Hay filas marcadas para revision. Deseas cargarlas de todos modos?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.accepted_tests = [
            TenderTest(row.sap_code, row.description, row.quantity)
            for row in rows
            if row.sap_code and row.description and row.quantity > 0
        ]
        if not self.accepted_tests:
            QMessageBox.information(self, "Revision", "No hay filas validas para cargar.")
            return
        self.accept()

    def _load_rows(self, rows: list[ImportPreviewRow]) -> None:
        self._loading = True
        try:
            self.table.setRowCount(0)
            for row in rows:
                self._append_row(row)
        finally:
            self._loading = False
        self._refresh_all_statuses()

    def _append_row(self, row: ImportPreviewRow) -> None:
        row_index = self.table.rowCount()
        self.table.insertRow(row_index)
        values = (
            row.sap_code,
            row.description,
            self.tab._format_number(row.quantity),
            row.status,
            row.observation,
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column in (3, 4):
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if column in (0, 2, 3):
                item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_index, column, item)
        self._apply_row_color(row_index, row.status)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() not in (0, 1, 2):
            return
        self._refresh_status(item.row())

    def _refresh_all_statuses(self) -> None:
        for row in range(self.table.rowCount()):
            self._refresh_status(row)

    def _refresh_status(self, row: int) -> None:
        data = self._row_from_table(row)
        self._loading = True
        try:
            self.table.item(row, 3).setText(data.status)
            self.table.item(row, 4).setText(data.observation)
        finally:
            self._loading = False
        self._apply_row_color(row, data.status)

    def _apply_row_color(self, row: int, status: str) -> None:
        color = QColor("#F4CCCC") if status in self.CRITICAL_STATUSES else (
            QColor("#FFF2CC") if status != "OK" else QColor("#FFFFFF")
        )
        for column in range(self.table.columnCount()):
            item = self.table.item(row, column)
            if item is not None:
                item.setBackground(color)

    def _rows_from_table(self) -> list[ImportPreviewRow]:
        return [self._row_from_table(row) for row in range(self.table.rowCount())]

    def _row_from_table(self, row: int) -> ImportPreviewRow:
        return self.tab.service.validate_import_row(
            self._item_text(row, 0),
            self._item_text(row, 1),
            self._item_text(row, 2),
        )

    def _item_text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item is not None else ""


class ProductOrderDialog(QDialog):
    def __init__(self, state: EquivalenceState, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self._loading = False
        self._active_table = "category"
        self.search_text = ""
        self.setWindowTitle("Orden / categorías")
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
        order_actions = QHBoxLayout()
        for text, direction in (("Arriba", -1), ("Abajo", 1)):
            button = QPushButton(text, self)
            button.clicked.connect(lambda _checked=False, step=direction: self.move_product(step))
            order_actions.addWidget(button)
            button.hide()
        order_actions.addStretch(1)
        right.addLayout(order_actions)
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
                self.target_category.addItem(category["name"], category["name"])
            self.category_table.setRowCount(len(categories))
            selected_row = 0
            for row, category in enumerate(categories):
                if category["name"] == selected_category:
                    selected_row = row
                values = (row + 1, category["name"], category["color"])
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column in (0, 2):
                        item.setTextAlignment(Qt.AlignCenter)
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
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setTextAlignment(
                        Qt.AlignLeft | Qt.AlignVCenter if column == 3 else Qt.AlignCenter
                    )
                    self.product_table.setItem(row, column, item)
            if products:
                self.product_table.selectRow(min(selected_row, len(products) - 1))
        finally:
            self._loading = False

    def add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Nueva categoría", "Categoría:")
        name = name.strip()
        if not ok or not name:
            return
        if any(item["name"].casefold() == name.casefold() for item in self._categories()):
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
        name, ok = QInputDialog.getText(self, "Editar categoría", "Categoría:", text=old_name)
        if not ok or not name.strip():
            return
        categories[row]["name"] = name.strip()
        for product in self.state.products:
            if product.category == old_name:
                product.category = name.strip()
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

    def move_product(self, step: int) -> None:
        products = self._products_for_category(self._selected_category_name(), include_search=False)
        selected = self._selected_products()
        if not selected or selected[0] not in products:
            return
        row = products.index(selected[0])
        target = max(0, min(len(products) - 1, row + step))
        if target == row:
            return
        item = products.pop(row)
        products.insert(target, item)
        for order, product in enumerate(products):
            product.order = order
        self.refresh_products(item.key)
        self.product_table.selectRow(target)

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
            target = self._target_index(row, len(products), action)
            if row != target:
                product = products.pop(row)
                products.insert(target, product)
                for order, current in enumerate(products):
                    current.order = order
                self.refresh_products(product.key)
            return
        row = self.category_table.currentRow()
        categories = self._categories()
        if row < 0 or row >= len(categories):
            return
        target = self._target_index(row, len(categories), action)
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
        for order, current_product in enumerate(products):
            current_product.order = order
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
        return item.text() if item is not None else ""

    def _product_by_key(self, key: str) -> ReagentProduct | None:
        return next((product for product in self.state.products if product.key == key), None)

    def _sorted_products(self) -> list[ReagentProduct]:
        return sorted(self.state.products, key=lambda item: (item.category.casefold(), item.order, item.product.casefold()))

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
            for order, product in enumerate(
                self._products_for_category(category, include_search=False)
            ):
                product.order = order

    @staticmethod
    def _target_index(index: int, length: int, action: str) -> int:
        if length <= 0:
            return 0
        if action == "first":
            return 0
        if action == "up":
            return max(0, index - 1)
        if action == "down":
            return min(length - 1, index + 1)
        if action == "last":
            return length - 1
        return index

    def _resize_columns(self) -> None:
        self._resize_table(self.category_table, (2, 4, 3))
        self._resize_table(self.product_table, (2, 4, 4, 8))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_columns()

    @staticmethod
    def _resize_table(table: QTableWidget, ratios: tuple[int, ...]) -> None:
        available = max(1, table.viewport().width())
        total = sum(ratios)
        used = 0
        for column, ratio in enumerate(ratios):
            width = available - used if column == len(ratios) - 1 else int(available * ratio / total)
            used += width
            table.setColumnWidth(column, max(1, width))


class HomologationDialog(QDialog):
    def __init__(self, tab: "EquivalenceTab") -> None:
        super().__init__(tab)
        self.tab = tab
        self._loading = False
        self.setWindowTitle("Homologación de equivalencias")
        self.resize(1180, 720)
        self._build_ui()
        self.refresh_all()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self.test_search = QLineEdit(self)
        self.test_search.setPlaceholderText("Buscar prueba")
        self.test_search.textChanged.connect(self._filter_tests)
        self.product_search = QLineEdit(self)
        self.product_search.setPlaceholderText("Buscar reactivo")
        self.product_search.textChanged.connect(self._filter_products)
        search_row.addWidget(QLabel("Pruebas:"))
        search_row.addWidget(self.test_search, 1)
        search_row.addWidget(QLabel("Reactivos:"))
        search_row.addWidget(self.product_search, 1)
        order_top_button = QPushButton("Orden / categorías", self)
        order_top_button.clicked.connect(self.open_product_order)
        search_row.addWidget(order_top_button)
        root.addLayout(search_row)

        top = QHBoxLayout()
        self.test_table = QTableWidget(0, 3, self)
        self.test_table.verticalHeader().setVisible(False)
        self.test_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.test_table.setHorizontalHeaderLabels(("Código SAP", "Descripción", "Cantidad"))
        self.test_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.test_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.test_table.itemChanged.connect(self._tests_changed)
        top.addWidget(self.test_table, 5)

        relation_box = QVBoxLayout()
        relation_box.addStretch(1)
        equal_button = QPushButton("=", self)
        equal_button.clicked.connect(self.add_relation)
        not_equal_button = QPushButton("≠", self)
        not_equal_button.clicked.connect(self.remove_relation)
        relation_box.addWidget(equal_button)
        relation_box.addWidget(not_equal_button)
        relation_box.addStretch(1)
        top.addLayout(relation_box)

        self.product_table = QTableWidget(0, 4, self)
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.product_table.setHorizontalHeaderLabels(("CodProd", "CodEqv", "Producto", "DET RVO"))
        self.product_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_table.setItemDelegateForColumn(3, NonNegativeNumberDelegate(self.product_table))
        self.product_table.itemChanged.connect(self._products_changed)
        product_panel = QVBoxLayout()
        product_panel.addWidget(self.product_table, 1)
        product_actions = QHBoxLayout()
        load_products_top = QPushButton("Cargar", self)
        load_products_top.clicked.connect(self.load_products)
        save_products_top = QPushButton("Guardar", self)
        save_products_top.clicked.connect(self.save_products)
        add_product_top = QPushButton("Agregar", self)
        add_product_top.clicked.connect(self.add_product)
        delete_products_top = QPushButton("Eliminar", self)
        delete_products_top.clicked.connect(self.delete_products)
        for button in (load_products_top, save_products_top, add_product_top, delete_products_top):
            product_actions.addWidget(button, 1)
        product_panel.addLayout(product_actions)
        top.addLayout(product_panel, 5)
        root.addLayout(top, 5)

        self.relation_table = QTableWidget(0, 7, self)
        self.relation_table.verticalHeader().setVisible(False)
        self.relation_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.relation_table.setHorizontalHeaderLabels((
            "Código SAP", "Prueba solicitada", "Cantidad", "CodProd", "CodEqv", "Reactivo propio", "DET RVO"
        ))
        self.relation_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.relation_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.relation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.relation_table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(QLabel("Homologaciones creadas"))
        root.addWidget(self.relation_table, 3)

        bottom = QHBoxLayout()
        delete_tests = QPushButton("Eliminar prueba", self)
        delete_tests.clicked.connect(self.delete_tests)
        bottom.addWidget(delete_tests)
        load_products = QPushButton("Cargar reactivos", self)
        load_products.clicked.connect(self.load_products)
        add_product = QPushButton("Agregar reactivo", self)
        add_product.clicked.connect(self.add_product)
        delete_products = QPushButton("Eliminar reactivo", self)
        delete_products.clicked.connect(self.delete_products)
        order_products = QPushButton("Orden / categorias", self)
        order_products.clicked.connect(self.open_product_order)
        for button in (load_products, add_product, delete_products, order_products):
            bottom.addWidget(button)
            button.hide()
        bottom.addStretch(1)
        close_button = QPushButton("Cerrar", self)
        close_button.clicked.connect(self.accept)
        bottom.addWidget(close_button)
        root.addLayout(bottom)

    def refresh_all(self) -> None:
        self._loading = True
        try:
            self._load_tests()
            self._load_products()
            self._load_relations()
        finally:
            self._loading = False

    def add_relation(self) -> None:
        if not self._sync_products(show_warning=True):
            return
        test = self._selected_test()
        product = self._selected_product()
        if test is None or product is None:
            QMessageBox.information(self, "Homologación", "Selecciona una prueba y un reactivo.")
            return
        values = self.tab.state.equivalences.setdefault(normalize_description(test.description), [])
        if product.key not in values:
            values.append(product.key)
        self.tab.save_state(show_message=False)
        self.tab.recalculate()
        self._load_relations()

    def remove_relation(self) -> None:
        row = self.relation_table.currentRow()
        if row >= 0:
            description = self._item_text(self.relation_table, row, 1)
            product_key = str(self.relation_table.item(row, 3).data(Qt.UserRole) or "")
        else:
            test = self._selected_test()
            product = self._selected_product()
            if test is None or product is None:
                QMessageBox.information(self, "Homologación", "Selecciona una homologación o prueba/reactivo.")
                return
            description = test.description
            product_key = product.key
        key = normalize_description(description)
        self.tab.state.equivalences[key] = [
            value for value in self.tab.state.equivalences.get(key, [])
            if value != product_key
        ]
        self.tab.save_state(show_message=False)
        self.tab.recalculate()
        self._load_relations()

    def delete_tests(self) -> None:
        rows = sorted({index.row() for index in self.test_table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            self.test_table.removeRow(row)
        self._tests_changed()

    def load_products(self) -> None:
        self.tab.load_products_file()
        self.refresh_all()

    def save_products(self) -> None:
        if self._sync_products(show_warning=True):
            self.tab.save_state(show_message=True)
            self.refresh_all()

    def add_product(self) -> None:
        self._loading = True
        try:
            row = self.product_table.rowCount()
            self.product_table.insertRow(row)
            for column in range(self.product_table.columnCount()):
                self.product_table.setItem(row, column, QTableWidgetItem(""))
            self.product_table.selectRow(row)
            self.product_table.setCurrentCell(row, 0)
        finally:
            self._loading = False
        self.product_table.editItem(self.product_table.item(row, 0))

    def delete_products(self) -> None:
        rows = sorted(
            {index.row() for index in self.product_table.selectionModel().selectedRows()},
            reverse=True,
        )
        for row in rows:
            self.product_table.removeRow(row)
        self._products_changed()

    def open_product_order(self) -> None:
        if not self._sync_products(show_warning=True):
            return
        self.tab.open_order_dialog()
        self.refresh_all()

    def _load_tests(self) -> None:
        tests = self.tab._tests_from_table()
        self.test_table.setRowCount(len(tests))
        for row, test in enumerate(tests):
            for column, value in enumerate((test.sap_code, test.description, self.tab._format_number(test.quantity))):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(
                    Qt.AlignLeft | Qt.AlignVCenter if column == 1 else Qt.AlignCenter
                )
                self.test_table.setItem(row, column, item)

    def _load_products(self) -> None:
        products = self.tab.state.products
        self.product_table.setRowCount(len(products))
        for row, product in enumerate(products):
            values = (product.cod_prod, product.cod_eqv, product.product, self.tab._format_number(product.det_rvo))
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, product.key)
                item.setTextAlignment(
                    Qt.AlignLeft | Qt.AlignVCenter if column == 2 else Qt.AlignCenter
                )
                self.product_table.setItem(row, column, item)

    def _load_relations(self) -> None:
        tests = self._tests_from_dialog()
        products = {product.key: product for product in self.tab.state.products if product.key}
        rows = []
        for test in tests:
            for product_key in self.tab.state.equivalences.get(normalize_description(test.description), []):
                product = products.get(product_key)
                if product is not None:
                    rows.append((test, product))
        self.relation_table.setRowCount(len(rows))
        for row, (test, product) in enumerate(rows):
            values = (
                test.sap_code,
                test.description,
                self.tab._format_number(test.quantity),
                product.cod_prod,
                product.cod_eqv,
                product.product,
                self.tab._format_number(product.det_rvo),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 3:
                    item.setData(Qt.UserRole, product.key)
                item.setTextAlignment(
                    Qt.AlignLeft | Qt.AlignVCenter if column in (1, 5) else Qt.AlignCenter
                )
                self.relation_table.setItem(row, column, item)

    def _tests_changed(self, _item=None) -> None:
        if self._loading:
            return
        self.tab._replace_tender_tests(self._tests_from_dialog())
        self.tab.recalculate()
        self._load_relations()

    def _products_changed(self, item=None) -> None:
        if self._loading:
            return
        if item is not None and item.column() == 3:
            value = self._valid_det_rvo(item.text())
            if value is None:
                QMessageBox.warning(
                    self,
                    "DET RVO inválido",
                    "DET RVO debe ser un número mayor o igual a cero.",
                )
                self._loading = True
                item.setText("0")
                self._loading = False
        self._sync_products(show_warning=False)

    def _sync_products(self, *, show_warning: bool) -> bool:
        previous = {product.key: product for product in self.tab.state.products if product.key}
        products = []
        for row in range(self.product_table.rowCount()):
            values = [self._item_text(self.product_table, row, column) for column in range(4)]
            if not any(values):
                continue
            det_rvo = self._valid_det_rvo(values[3])
            if det_rvo is None:
                if show_warning:
                    QMessageBox.warning(
                        self,
                        "DET RVO inválido",
                        f"Fila {row + 1}: DET RVO debe ser numérico y no negativo.",
                    )
                return False
            key = values[0] or values[1] or values[2]
            source = previous.get(key, ReagentProduct())
            products.append(
                ReagentProduct(
                    values[0],
                    values[1],
                    values[2],
                    det_rvo,
                    source.category,
                    source.order if source.key else len(products),
                )
            )
        self.tab._replace_products(products)
        self.tab.save_state(show_message=False)
        self.tab.recalculate()
        self._load_relations()
        return True

    @staticmethod
    def _valid_det_rvo(value: object) -> float | None:
        text = str(value or "").strip().replace(" ", "").replace(",", ".")
        if not text:
            return 0.0
        if not re.fullmatch(r"\d+(?:\.\d+)?", text):
            return None
        number = float(text)
        return number if number >= 0 else None

    def _selected_test(self) -> TenderTest | None:
        row = self.test_table.currentRow()
        tests = self._tests_from_dialog()
        return tests[row] if 0 <= row < len(tests) else None

    def _selected_product(self) -> ReagentProduct | None:
        row = self.product_table.currentRow()
        return self.tab.state.products[row] if 0 <= row < len(self.tab.state.products) else None

    def _tests_from_dialog(self) -> list[TenderTest]:
        tests = []
        for row in range(self.test_table.rowCount()):
            values = [self._item_text(self.test_table, row, column) for column in range(3)]
            if any(values):
                tests.append(TenderTest(values[0], values[1], self.tab._number(values[2])))
        return tests

    def _filter_tests(self, text: str) -> None:
        self._filter_table(self.test_table, text, 3)

    def _filter_products(self, text: str) -> None:
        self._filter_table(self.product_table, text, 4)

    def _filter_table(self, table: QTableWidget, text: str, columns: int) -> None:
        needle = normalize_description(text)
        for row in range(table.rowCount()):
            haystack = normalize_description(" ".join(self._item_text(table, row, column) for column in range(columns)))
            table.setRowHidden(row, bool(needle and needle not in haystack))

    @staticmethod
    def _item_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text().strip() if item is not None else ""


class EquivalenceTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.service = EquivalenceService(get_app_paths().data_root / "equivalence_config.json")
        self.state = self.service.load()
        self._loading = False
        self._results: list[EquivalenceResult] = []
        self._warnings: list[str] = []
        self._build_ui()
        self._apply_settings()
        self._load_state_to_products()
        self._refresh_equivalences()
        self.recalculate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        header = QGridLayout()
        self.customer_field = QLineEdit(self)
        self.customer_field.setPlaceholderText("Cliente/Hospital")
        self.line_field = QLineEdit(self)
        self.line_field.setPlaceholderText("Equipo o línea")
        self.period_months = QSpinBox(self)
        self.period_months.setRange(1, 120)
        self.period_months.setValue(12)
        self.period_type = QComboBox(self)
        self.period_type.addItem("Total del periodo", "total")
        self.period_type.addItem("Mensual", "mensual")
        self.period_type.addItem("Bimensual", "bimensual")
        self.period_months.valueChanged.connect(self.recalculate)
        self.period_type.currentIndexChanged.connect(self.recalculate)
        header.addWidget(QLabel("Cliente:"), 0, 0)
        header.addWidget(self.customer_field, 0, 1)
        header.addWidget(QLabel("Equipo/Línea:"), 0, 2)
        header.addWidget(self.line_field, 0, 3)
        header.addWidget(QLabel("Periodo:"), 0, 4)
        header.addWidget(self.period_months, 0, 5)
        header.addWidget(self.period_type, 0, 6)
        root.addLayout(header)

        import_row = QHBoxLayout()
        paste_button = QPushButton("Pegar licitación", self)
        paste_button.clicked.connect(self.paste_tender)
        load_file_button = QPushButton("Cargar Excel/CSV", self)
        load_file_button.setText("Cargar CSV")
        load_file_button.clicked.connect(self.load_tender_file)
        image_button = QPushButton("Cargar Imagen/PDF", self)
        image_button.clicked.connect(self.load_tender_image)
        homologation_button = QPushButton("Homologar", self)
        homologation_button.clicked.connect(self.open_homologation_dialog)
        self.alerts_button = QPushButton("Ver alertas", self)
        self.alerts_button.clicked.connect(self.show_alerts)
        export_button = QPushButton("Exportar Excel", self)
        export_button.clicked.connect(self.export_excel)
        import_row.addWidget(paste_button)
        import_row.addWidget(load_file_button)
        import_row.addWidget(image_button)
        import_row.addWidget(homologation_button)
        import_row.addWidget(self.alerts_button)
        import_row.addStretch(1)
        import_row.addWidget(export_button)
        root.addLayout(import_row)
        paste_button.hide()
        image_button.hide()

        top = QHBoxLayout()
        tender_box = QVBoxLayout()
        tender_box.addWidget(QLabel("Pruebas solicitadas"))
        self.tender_table = QTableWidget(0, 3, self)
        self.tender_table.setHorizontalHeaderLabels(("Código SAP", "Descripción", "Cantidad"))
        self.tender_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tender_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tender_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.tender_table.setColumnWidth(0, 140)
        self.tender_table.setColumnWidth(2, 110)
        self.tender_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tender_table.itemSelectionChanged.connect(self._refresh_equivalences)
        self.tender_table.itemChanged.connect(lambda _item: self.recalculate())
        tender_actions = QHBoxLayout()
        add_test = QPushButton("Añadir prueba", self)
        add_test.clicked.connect(self.add_tender_row)
        delete_test = QPushButton("Eliminar prueba", self)
        delete_test.clicked.connect(self.delete_tender_rows)
        tender_actions.addWidget(add_test)
        tender_actions.addWidget(delete_test)
        tender_actions.addStretch(1)
        tender_box.addWidget(self.tender_table, 1)
        tender_box.addLayout(tender_actions)
        top.addLayout(tender_box, 5)

        product_box = QVBoxLayout()
        product_box.addWidget(QLabel("Reactivos propios"))
        self.product_table = QTableWidget(0, 5, self)
        self.product_table.setHorizontalHeaderLabels(("CodProd", "CodEqv", "Producto", "DET RVO", "Categoría"))
        self.product_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.product_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.product_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.product_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.product_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.product_table.setColumnWidth(0, 105)
        self.product_table.setColumnWidth(1, 105)
        self.product_table.setColumnWidth(3, 90)
        self.product_table.setColumnWidth(4, 120)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_table.itemChanged.connect(self._products_changed)
        product_actions = QHBoxLayout()
        load_products = QPushButton("Cargar base", self)
        load_products.clicked.connect(self.load_products_file)
        add_product = QPushButton("Añadir", self)
        add_product.clicked.connect(self.add_product_row)
        order_product = QPushButton("Orden", self)
        order_product.clicked.connect(self.open_order_dialog)
        edit_product = QPushButton("Editar", self)
        edit_product.clicked.connect(self.edit_current_product)
        delete_product = QPushButton("Eliminar", self)
        delete_product.clicked.connect(self.delete_product_rows)
        save_products = QPushButton("Guardar base", self)
        save_products.clicked.connect(self.save_state)
        for button in (load_products, add_product, order_product, edit_product, delete_product, save_products):
            product_actions.addWidget(button)
        product_box.addWidget(self.product_table, 1)
        product_box.addLayout(product_actions)
        top.addLayout(product_box, 6)
        self._hide_layout(top)

        equivalence_row = QHBoxLayout()
        self.product_search = QLineEdit(self)
        self.product_search.setPlaceholderText("Buscar reactivo")
        self.product_search.textChanged.connect(self._filter_products)
        add_equivalence = QPushButton("Asociar reactivo", self)
        add_equivalence.clicked.connect(self.add_equivalence)
        remove_equivalence = QPushButton("Quitar asociación", self)
        remove_equivalence.clicked.connect(self.remove_equivalence)
        equivalence_row.addWidget(QLabel("Equivalencias:"))
        equivalence_row.addWidget(self.product_search, 1)
        equivalence_row.addWidget(add_equivalence)
        equivalence_row.addWidget(remove_equivalence)
        self._hide_layout(equivalence_row)

        self.equivalence_list = QListWidget(self)
        self.equivalence_list.setMaximumHeight(80)
        self.equivalence_list.hide()

        bottom = QHBoxLayout()
        result_box = QVBoxLayout()
        result_box.addWidget(QLabel("Resultado calculado / previsualización final"))
        self.result_table = QTableWidget(0, 9, self)
        self.result_table.setHorizontalHeaderLabels(("CodProd", "CodEqv", "Producto", "DET RVO", "DET OC", "DET ENV", "CANT"))
        self.result_table.setHorizontalHeaderLabels((
            "Codigo SAP", "Descripcion", "CodProd", "CodEqv", "Producto",
            "DET RVO", "DET OC", "DET ENV", "CANT",
        ))
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        result_box.addWidget(self.result_table, 1)
        bottom.addLayout(result_box, 7)

        alerts_box = QVBoxLayout()
        alerts_box.addWidget(QLabel("Alertas"))
        self.alerts_list = QListWidget(self)
        alerts_box.addWidget(self.alerts_list, 1)
        self._hide_layout(alerts_box)
        root.addLayout(bottom, 4)

    def paste_tender(self) -> None:
        rows = self.service.parse_clipboard_text(QApplication.clipboard().text())
        if not rows:
            QMessageBox.information(self, "Equivalencia", "No se detectaron filas válidas en el portapapeles.")
            return
        self._append_tender_tests(rows)

    def load_tender_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Cargar licitación", "", "CSV (*.csv)")
        if not path:
            return
        try:
            self._load_csv_with_preview(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error al cargar licitación", str(exc))

    def _load_csv_with_preview(self, path: str | Path) -> None:
        source = Path(path)
        if source.suffix.lower() != ".csv":
            raise ValueError("El flujo principal de Equivalencia acepta archivos CSV.")
        rows = [
            self.service.validate_import_row(test.sap_code, test.description, test.quantity)
            for test in self.service.load_tender_file(source)
        ]
        if not rows:
            rows = [ImportPreviewRow(status="Fila incompleta")]
        dialog = ImportPreviewDialog(self, source, rows)
        if dialog.exec() == QDialog.Accepted:
            self._replace_tender_tests(dialog.accepted_tests)
            self.recalculate()

    def load_tender_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar imagen o PDF",
            "",
            "Imagen o PDF (*.png *.jpg *.jpeg *.pdf)",
        )
        if not path:
            return
        try:
            rows, _text = self.service.extract_import_preview(path)
        except RuntimeError as exc:
            QMessageBox.information(
                self,
                "OCR no disponible",
                f"{exc}\n\nPuedes usar pegado manual, Excel/CSV o edicion manual.",
            )
            return
        except Exception as exc:
            QMessageBox.critical(self, "Error al importar", str(exc))
            return
        if not rows:
            rows = [ImportPreviewRow(status="Fila incompleta")]
            QMessageBox.information(
                self,
                "Importacion",
                "No se detectaron filas. Puedes agregar o corregir filas en la vista previa.",
            )
        dialog = ImportPreviewDialog(self, path, rows)
        if dialog.exec() == QDialog.Accepted:
            self._append_tender_tests(dialog.accepted_tests)

    def load_products_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Cargar base de reactivos", "", "Datos (*.xlsx *.xlsm *.csv)")
        if not path:
            return
        try:
            products = self.service.load_products_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error al cargar base", str(exc))
            return
        self.state.products = products
        self._load_state_to_products()
        self.save_state(show_message=False)
        self.recalculate()

    def export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar equivalencia", "Equivalencia.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        self.recalculate()
        try:
            output = self.service.export_excel(
                path,
                self._tests_from_table(),
                self._results,
                self._warnings,
                customer=self.customer_field.text().strip(),
                line=self.line_field.text().strip(),
                equipment=self.line_field.text().strip(),
                period_label=f"{self.period_months.value()} meses - {self.period_type.currentText()}",
                categories=self.state.settings.get("product_categories", []),
            )
            QMessageBox.information(self, "Equivalencia", f"Excel generado correctamente:\n{output}")
        except Exception as exc:
            QMessageBox.critical(self, "Error al exportar", str(exc))

    def show_alerts(self) -> None:
        AlertsDialog(self._warnings, self).exec()

    def add_tender_row(self) -> None:
        self._append_tender_tests([TenderTest()])

    def delete_tender_rows(self) -> None:
        self._delete_selected_rows(self.tender_table)
        self._refresh_equivalences()
        self.recalculate()

    def add_product_row(self) -> None:
        self._loading = True
        row = self.product_table.rowCount()
        self.product_table.insertRow(row)
        for column in range(self.product_table.columnCount()):
            self.product_table.setItem(row, column, QTableWidgetItem(""))
        self._loading = False
        self.product_table.selectRow(row)
        self.edit_current_product()
        self._products_changed()

    def edit_current_product(self) -> None:
        row = self.product_table.currentRow()
        if row >= 0:
            self.product_table.editItem(self.product_table.item(row, 0))

    def delete_product_rows(self) -> None:
        self._delete_selected_rows(self.product_table)
        self._products_changed()

    def open_homologation_dialog(self) -> None:
        dialog = HomologationDialog(self)
        dialog.exec()
        self._refresh_equivalences()
        self.recalculate()

    def open_order_dialog(self) -> None:
        self._sync_products_from_table()
        dialog = ProductOrderDialog(self.state, self)
        if dialog.exec() == QDialog.Accepted:
            self._load_state_to_products()
            self.save_state(show_message=False)
            self.recalculate()

    def add_equivalence(self) -> None:
        test = self._selected_test()
        product = self._selected_product()
        if test is None or product is None:
            QMessageBox.information(self, "Equivalencia", "Selecciona una prueba y un reactivo.")
            return
        key = normalize_description(test.description)
        values = self.state.equivalences.setdefault(key, [])
        if product.key not in values:
            values.append(product.key)
        self.save_state(show_message=False)
        self._refresh_equivalences()
        self.recalculate()

    def remove_equivalence(self) -> None:
        test = self._selected_test()
        item = self.equivalence_list.currentItem()
        if test is None or item is None:
            return
        key = normalize_description(test.description)
        product_key = str(item.data(Qt.UserRole) or "")
        self.state.equivalences[key] = [
            value for value in self.state.equivalences.get(key, [])
            if value != product_key
        ]
        self.save_state(show_message=False)
        self._refresh_equivalences()
        self.recalculate()

    def save_state(self, show_message: bool = True) -> None:
        self._sync_products_from_table()
        settings = dict(self.state.settings)
        settings.update({
            "customer": self.customer_field.text().strip(),
            "line": self.line_field.text().strip(),
            "period_months": self.period_months.value(),
            "period_type": self.period_type.currentData(),
        })
        self.state.settings = settings
        self.service.save(self.state)
        if show_message:
            QMessageBox.information(self, "Equivalencia", "Base y equivalencias guardadas.")

    def recalculate(self) -> None:
        if self._loading:
            return
        self._sync_products_from_table()
        self._results, self._warnings = self.service.calculate(
            self._tests_from_table(),
            self.state,
            self.period_months.value(),
            str(self.period_type.currentData() or "total"),
        )
        self._load_results()
        self._load_warnings()

    def _append_tender_tests(self, tests: list[TenderTest]) -> None:
        self._loading = True
        try:
            for test in tests:
                row = self.tender_table.rowCount()
                self.tender_table.insertRow(row)
                for column, value in enumerate((test.sap_code, test.description, self._format_number(test.quantity))):
                    self.tender_table.setItem(row, column, QTableWidgetItem(str(value)))
        finally:
            self._loading = False
        self.recalculate()

    def _apply_settings(self) -> None:
        self.customer_field.setText(str(self.state.settings.get("customer", "")))
        self.line_field.setText(str(self.state.settings.get("line", "")))
        self.period_months.setValue(int(self.state.settings.get("period_months", 12) or 12))
        period_type = self.state.settings.get("period_type", "total")
        index = self.period_type.findData(period_type)
        if index >= 0:
            self.period_type.setCurrentIndex(index)

    def _load_state_to_products(self) -> None:
        self._loading = True
        try:
            self.state.products = self.service.sorted_products(self.state.products)
            self.product_table.setRowCount(len(self.state.products))
            for row, product in enumerate(self.state.products):
                values = (product.cod_prod, product.cod_eqv, product.product, self._format_number(product.det_rvo), product.category)
                for column, value in enumerate(values):
                    self.product_table.setItem(row, column, QTableWidgetItem(str(value)))
        finally:
            self._loading = False

    def _products_changed(self, _item=None) -> None:
        if self._loading:
            return
        self._sync_products_from_table()
        self.recalculate()

    def _sync_products_from_table(self) -> None:
        if self._loading:
            return
        products = []
        previous = {product.key: product for product in self.state.products if product.key}
        for row in range(self.product_table.rowCount()):
            values = [self._item_text(self.product_table, row, column) for column in range(5)]
            if not any(values):
                continue
            key = values[0] or values[1] or values[2]
            current = previous.get(key)
            products.append(
                ReagentProduct(
                    values[0],
                    values[1],
                    values[2],
                    self._number(values[3]),
                    values[4],
                    current.order if current is not None else len(products),
                )
            )
        self.state.products = products

    def _replace_tender_tests(self, tests: list[TenderTest]) -> None:
        self._loading = True
        try:
            self.tender_table.setRowCount(0)
            for test in tests:
                row = self.tender_table.rowCount()
                self.tender_table.insertRow(row)
                for column, value in enumerate((test.sap_code, test.description, self._format_number(test.quantity))):
                    self.tender_table.setItem(row, column, QTableWidgetItem(str(value)))
        finally:
            self._loading = False

    def _replace_products(self, products: list[ReagentProduct]) -> None:
        self.state.products = products
        self._load_state_to_products()

    def _tests_from_table(self) -> list[TenderTest]:
        result = []
        for row in range(self.tender_table.rowCount()):
            values = [self._item_text(self.tender_table, row, column) for column in range(3)]
            if not any(values):
                continue
            result.append(TenderTest(values[0], values[1], self._number(values[2])))
        return result

    def _selected_test(self) -> TenderTest | None:
        row = self.tender_table.currentRow()
        tests = self._tests_from_table()
        return tests[row] if 0 <= row < len(tests) else None

    def _selected_product(self) -> ReagentProduct | None:
        row = self.product_table.currentRow()
        self._sync_products_from_table()
        return self.state.products[row] if 0 <= row < len(self.state.products) else None

    def _refresh_equivalences(self) -> None:
        self.equivalence_list.clear()
        test = self._selected_test()
        if test is None:
            return
        products_by_key = {product.key: product for product in self.state.products if product.key}
        for product_key in self.state.equivalences.get(normalize_description(test.description), []):
            product = products_by_key.get(product_key)
            label = f"{product.cod_prod} | {product.product}" if product is not None else product_key
            self.equivalence_list.addItem(label)
            self.equivalence_list.item(self.equivalence_list.count() - 1).setData(Qt.UserRole, product_key)

    def _filter_products(self, text: str) -> None:
        needle = normalize_description(text)
        for row in range(self.product_table.rowCount()):
            haystack = normalize_description(
                " ".join(self._item_text(self.product_table, row, column) for column in range(5))
            )
            self.product_table.setRowHidden(row, bool(needle and needle not in haystack))

    def _load_results(self) -> None:
        self.result_table.setRowCount(len(self._results))
        for row, result in enumerate(self._results):
            values = (
                result.sap_code,
                result.test_description,
                result.cod_prod,
                result.cod_eqv,
                result.product,
                self._format_number(result.det_rvo),
                self._format_number(result.det_oc),
                self._format_number(result.det_env),
                result.quantity,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(
                    Qt.AlignLeft | Qt.AlignVCenter if column in (1, 4) else Qt.AlignCenter
                )
                self.result_table.setItem(row, column, item)
        self.result_table.resizeColumnsToContents()
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

    def _load_warnings(self) -> None:
        self.alerts_list.clear()
        for warning in self._warnings:
            self.alerts_list.addItem(warning)
        count = len(self._warnings)
        self.alerts_button.setText(f"Ver alertas ({count})" if count else "Ver alertas")
        self.alerts_button.setToolTip(
            f"{count} alerta(s) pendiente(s)" if count else "No hay alertas pendientes"
        )

    @staticmethod
    def _hide_layout(layout) -> None:
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.hide()
            elif child_layout is not None:
                EquivalenceTab._hide_layout(child_layout)

    @staticmethod
    def _delete_selected_rows(table: QTableWidget) -> None:
        rows = sorted({index.row() for index in table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            table.removeRow(row)

    @staticmethod
    def _item_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text().strip() if item is not None else ""

    @staticmethod
    def _number(value: object) -> float:
        text = str(value or "").strip().replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text:
            if re.fullmatch(r"\d{1,3}(,\d{3})+", text):
                text = text.replace(",", "")
            else:
                text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return 0.0

    @staticmethod
    def _format_number(value: float) -> str:
        return str(int(value)) if float(value or 0).is_integer() else f"{value:.2f}"
