from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from models.equivalence import ReagentProduct, TenderTest
from services.equivalence_service import normalize_description
from ui.common.table_helpers import resize_columns_by_ratio, set_table_alignment

if TYPE_CHECKING:
    from ui.tabs.equivalence_tab import EquivalenceTab


class NonNegativeNumberDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        validator = QDoubleValidator(0.0, 999999999999.0, 6, editor)
        validator.setNotation(QDoubleValidator.StandardNotation)
        editor.setValidator(validator)
        return editor


class HomologationWidget(QWidget):
    closeRequested = Signal()

    def __init__(self, tab: "EquivalenceTab") -> None:
        super().__init__(tab)
        self.tab = tab
        self._loading = False
        self._build_ui()
        self.refresh_all()
        QTimer.singleShot(0, self._resize_tables)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self.test_search = QLineEdit(self)
        self.test_search.setPlaceholderText("Buscar prueba")
        self.test_search.textChanged.connect(self._filter_tests)
        self.product_search = QLineEdit(self)
        self.product_search.setPlaceholderText("Buscar producto")
        self.product_search.textChanged.connect(self._filter_products)
        search_row.addWidget(QLabel("Pruebas:"))
        search_row.addWidget(self.test_search, 1)
        search_row.addWidget(QLabel("Producto:"))
        search_row.addWidget(self.product_search, 1)
        order_top_button = QPushButton("Categoría", self)
        order_top_button.clicked.connect(self.open_product_order)
        search_row.addWidget(order_top_button)
        root.addLayout(search_row)

        top = QHBoxLayout()
        self.test_table = QTableWidget(0, 4, self)
        self.test_table.verticalHeader().setVisible(False)
        self.test_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.test_table.setHorizontalHeaderLabels(("Orden", "Código SAP", "Descripción", "Cantidad"))
        self.test_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
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

        self.product_table = QTableWidget(0, 5, self)
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.product_table.setHorizontalHeaderLabels(("Orden", "CodProd", "CodEqv", "Producto", "DET RVO"))
        self.product_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_table.setItemDelegateForColumn(4, NonNegativeNumberDelegate(self.product_table))
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

        self.relation_table = QTableWidget(0, 8, self)
        self.relation_table.verticalHeader().setVisible(False)
        self.relation_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.relation_table.setHorizontalHeaderLabels((
            "Orden", "Código SAP", "Prueba solicitada", "Cantidad",
            "CodProd", "CodEqv", "Producto propio", "DET RVO",
        ))
        self.relation_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.relation_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.relation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.relation_table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(QLabel("Homologaciones creadas"))
        root.addWidget(self.relation_table, 3)

        bottom = QHBoxLayout()
        delete_tests = QPushButton("Eliminar prueba", self)
        delete_tests.clicked.connect(self.delete_tests)
        bottom.addWidget(delete_tests)
        bottom.addStretch(1)
        close_button = QPushButton("Cerrar", self)
        close_button.clicked.connect(self.closeRequested.emit)
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
            QMessageBox.information(self, "Homologación", "Selecciona una prueba y un producto.")
            return
        if self._is_test_used(test) or self._is_product_used(product):
            QMessageBox.information(
                self,
                "Homologación",
                "La prueba o el producto ya pertenece a una homologación activa.",
            )
            return
        values = self.tab.state.equivalences.setdefault(
            self.tab.service.test_key(test),
            [],
        )
        if product.key not in values:
            values.append(product.key)
        self.tab.save_state(show_message=False)
        self.tab.recalculate()
        self.refresh_all()

    def remove_relation(self) -> None:
        row = self.relation_table.currentRow()
        if row >= 0:
            relation_key = str(self.relation_table.item(row, 1).data(Qt.UserRole) or "")
            product_key = str(self.relation_table.item(row, 4).data(Qt.UserRole) or "")
        else:
            test = self._selected_test()
            product = self._selected_product()
            if test is None or product is None:
                QMessageBox.information(self, "Homologación", "Selecciona una homologación o prueba/producto.")
                return
            relation_key = self.tab.service.test_key(test)
            product_key = product.key
        self.tab.state.equivalences[relation_key] = [
            value for value in self.tab.state.equivalences.get(relation_key, [])
            if value != product_key
        ]
        if not self.tab.state.equivalences[relation_key]:
            self.tab.state.equivalences.pop(relation_key, None)
        self.tab.save_state(show_message=False)
        self.tab.recalculate()
        self.refresh_all()

    def delete_tests(self) -> None:
        rows = sorted({index.row() for index in self.test_table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            self.test_table.removeRow(row)
        self._tests_changed()

    def load_products(self) -> None:
        self.tab.load_products_file()
        self.refresh_all()

    def save_products(self) -> None:
        if not self._sync_products(show_warning=True):
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar productos",
            "Productos_Equivalencia.xlsx",
            "Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            output = self.tab.service.export_products_excel(path, self.tab.state.products)
            QMessageBox.information(self, "Productos", f"Archivo generado correctamente:\n{output}")
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar productos", str(exc))

    def add_product(self) -> None:
        self._loading = True
        try:
            row = self.product_table.rowCount()
            self.product_table.insertRow(row)
            for column in range(self.product_table.columnCount()):
                self.product_table.setItem(row, column, QTableWidgetItem(""))
            self.product_table.selectRow(row)
            self.product_table.item(row, 0).setText(str(row + 1))
            self.product_table.setCurrentCell(row, 1)
        finally:
            self._loading = False
        self.product_table.editItem(self.product_table.item(row, 1))

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
        self.tab.open_category_dialog()
        self.refresh_all()

    def _load_tests(self) -> None:
        tests = [
            test
            for test in self.tab._tests_from_table()
            if not self._is_test_used(test)
        ]
        self.test_table.setRowCount(len(tests))
        all_tests = self.tab._tests_from_table()
        for row, test in enumerate(tests):
            order = next(
                (
                    index + 1
                    for index, current in enumerate(all_tests)
                    if self.tab.service.test_key(current) == self.tab.service.test_key(test)
                ),
                row + 1,
            )
            for column, value in enumerate(
                (order, test.sap_code, test.description, self.tab._format_number(test.quantity))
            ):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.test_table.setItem(row, column, item)

    def _load_products(self) -> None:
        used_keys = self._used_product_keys()
        products = [
            product
            for product in self.tab.service.sorted_products(
                self.tab.state.products,
                self.tab.state.settings.get("product_categories", []),
            )
            if product.key not in used_keys
        ]
        self.product_table.setRowCount(len(products))
        for row, product in enumerate(products):
            values = (
                product.order + 1,
                product.cod_prod,
                product.cod_eqv,
                product.product,
                self.tab._format_number(product.det_rvo),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, product.key)
                item.setTextAlignment(Qt.AlignCenter)
                self.product_table.setItem(row, column, item)

    def _load_relations(self) -> None:
        rows = self._active_relations()
        self.relation_table.setRowCount(len(rows))
        for row, (test, product) in enumerate(rows):
            relation_key, _values = self.tab.service.equivalence_entry(
                self.tab.state,
                test,
            )
            values = (
                product.order + 1,
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
                if column == 1:
                    item.setData(Qt.UserRole, relation_key)
                if column == 4:
                    item.setData(Qt.UserRole, product.key)
                item.setTextAlignment(Qt.AlignCenter)
                self.relation_table.setItem(row, column, item)
        set_table_alignment(self.relation_table, Qt.AlignCenter)

    def _tests_changed(self, _item=None) -> None:
        if self._loading:
            return
        used = [
            test
            for test in self.tab._tests_from_table()
            if self._is_test_used(test)
        ]
        self.tab._replace_tender_tests(used + self._tests_from_dialog())
        self.tab.recalculate()
        self.refresh_all()

    def _products_changed(self, item=None) -> None:
        if self._loading:
            return
        if item is not None and item.column() == 4:
            valid, value = self._valid_det_rvo(item.text())
            if not valid:
                QMessageBox.warning(
                    self,
                    "DET RVO inválido",
                    "DET RVO debe ser un número mayor o igual a cero.",
                )
                self._loading = True
                item.setText("")
                self._loading = False
        self._sync_products(show_warning=False)

    def _sync_products(self, *, show_warning: bool) -> bool:
        previous = self.tab.service.product_lookup(self.tab.state.products)
        used_keys = self._used_product_keys()
        products = [
            product
            for product in self.tab.state.products
            if product.key in used_keys
        ]
        for row in range(self.product_table.rowCount()):
            values = [self._item_text(self.product_table, row, column) for column in range(1, 5)]
            if not any(values):
                continue
            valid, det_rvo = self._valid_det_rvo(values[3])
            if not valid:
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

    def _active_relations(self) -> list[tuple[TenderTest, ReagentProduct]]:
        rows = self.tab.service.active_relations(
            self.tab._tests_from_table(),
            self.tab.state,
        )
        categories = self.tab.state.settings.get("product_categories", [])
        return sorted(
            rows,
            key=lambda pair: (
                self.tab.service.category_order(pair[1].category, categories),
                pair[1].order,
                pair[1].product.casefold(),
                self.tab.service.test_key(pair[0]),
            ),
        )

    def _used_product_keys(self) -> set[str]:
        return {product.key for _test, product in self._active_relations()}

    def _is_test_used(self, test: TenderTest) -> bool:
        key = self.tab.service.test_key(test)
        return any(
            self.tab.service.test_key(current) == key
            for current, _product in self._active_relations()
        )

    def _is_product_used(self, product: ReagentProduct) -> bool:
        return product.key in self._used_product_keys()

    @staticmethod
    def _valid_det_rvo(value: object) -> tuple[bool, float | None]:
        text = str(value or "").strip().replace(" ", "").replace(",", ".")
        if not text:
            return (True, None)
        if not re.fullmatch(r"\d+(?:\.\d+)?", text):
            return (False, None)
        number = float(text)
        return (number >= 0, number if number >= 0 else None)

    def _selected_test(self) -> TenderTest | None:
        row = self.test_table.currentRow()
        tests = self._tests_from_dialog()
        return tests[row] if 0 <= row < len(tests) else None

    def _selected_product(self) -> ReagentProduct | None:
        row = self.product_table.currentRow()
        item = self.product_table.item(row, 1) if row >= 0 else None
        key = str(item.data(Qt.UserRole) or "") if item is not None else ""
        return self.tab.service.product_lookup(self.tab.state.products).get(key)

    def _tests_from_dialog(self) -> list[TenderTest]:
        tests = []
        for row in range(self.test_table.rowCount()):
            values = [self._item_text(self.test_table, row, column) for column in range(1, 4)]
            if any(values):
                tests.append(TenderTest(values[0], values[1], self.tab._number(values[2])))
        return tests

    def _filter_tests(self, text: str) -> None:
        self._filter_table(self.test_table, text, 4)

    def _filter_products(self, text: str) -> None:
        self._filter_table(self.product_table, text, 5)

    def _filter_table(self, table: QTableWidget, text: str, columns: int) -> None:
        needle = normalize_description(text)
        for row in range(table.rowCount()):
            haystack = normalize_description(" ".join(self._item_text(table, row, column) for column in range(columns)))
            table.setRowHidden(row, bool(needle and needle not in haystack))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_tables()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._resize_tables)

    def _resize_tables(self) -> None:
        resize_columns_by_ratio(self.test_table, (1, 2, 8, 2))
        resize_columns_by_ratio(self.product_table, (1, 2, 2, 6, 2))
        resize_columns_by_ratio(self.relation_table, (1, 2, 6, 2, 2, 2, 6, 2))

    @staticmethod
    def _item_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text().strip() if item is not None else ""


HomologationDialog = HomologationWidget
