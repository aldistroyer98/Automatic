from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QStackedWidget,
)

from app.paths import get_app_paths
from models.equivalence import EquivalenceResult, ImportPreviewRow, ReagentProduct, TenderTest
from services.equivalence_service import EquivalenceService, normalize_description
from services.equivalence_category_service import EquivalenceCategoryService
from ui.dialogs.homologation_dialog import HomologationWidget
from ui.dialogs.import_preview_dialog import ImportPreviewDialog
from ui.dialogs.product_order_dialog import ProductOrderDialog
from ui.dialogs.shipment_category_dialog import ShipmentCategoryDialog
from ui.internal_consumption_widget import InternalConsumptionWidget


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
        load_file_button = QPushButton("Cargar Excel/CSV", self)
        load_file_button.setText("Cargar CSV")
        load_file_button.clicked.connect(self.load_tender_file)
        homologation_button = QPushButton("Homologar", self)
        homologation_button.clicked.connect(self.show_homologation)
        equivalence_button = QPushButton("Equivalencia", self)
        equivalence_button.clicked.connect(self.show_equivalence)
        internal_button = QPushButton("Consumo interno", self)
        internal_button.clicked.connect(self.show_internal_consumption)
        self.alerts_button = QPushButton("Ver alertas", self)
        self.alerts_button.clicked.connect(self.show_alerts)
        export_button = QPushButton("Exportar Excel", self)
        export_button.clicked.connect(self.export_excel)
        import_row.addWidget(load_file_button)
        import_row.addWidget(homologation_button)
        import_row.addWidget(equivalence_button)
        import_row.addWidget(internal_button)
        import_row.addStretch(1)
        import_row.addWidget(self.alerts_button)
        import_row.addWidget(export_button)
        root.addLayout(import_row)
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
        product_box.addWidget(QLabel("Productos propios"))
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
        self.product_search.setPlaceholderText("Buscar producto")
        self.product_search.textChanged.connect(self._filter_products)
        add_equivalence = QPushButton("Asociar producto", self)
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

        result_page = QWidget(self)
        bottom = QHBoxLayout(result_page)
        bottom.setContentsMargins(0, 0, 0, 0)
        result_box = QVBoxLayout()
        result_box.addWidget(QLabel("Resultado calculado / previsualización final"))
        self.result_table = QTableWidget(0, 10, self)
        self.result_table.setHorizontalHeaderLabels((
            "Codigo SAP", "Descripcion", "CodProd", "CodEqv", "Producto",
            "DET RVO", "DET OC", "DET interno", "DET ENV", "CANT",
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
        self.view_stack = QStackedWidget(self)
        self.result_page = result_page
        self.homologation_widget = HomologationWidget(self)
        self.homologation_widget.closeRequested.connect(self.show_equivalence)
        self.internal_consumption_widget = InternalConsumptionWidget(self)
        self.internal_consumption_widget.closeRequested.connect(self.show_equivalence)
        self.view_stack.addWidget(self.result_page)
        self.view_stack.addWidget(self.homologation_widget)
        self.view_stack.addWidget(self.internal_consumption_widget)
        root.addWidget(self.view_stack, 4)

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

    def load_products_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Cargar base de productos", "", "Datos (*.xlsx *.xlsm *.csv)")
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
        self.show_homologation()

    def show_homologation(self) -> None:
        self.homologation_widget.refresh_all()
        self.view_stack.setCurrentWidget(self.homologation_widget)

    def show_equivalence(self) -> None:
        self.recalculate()
        self.view_stack.setCurrentWidget(self.result_page)

    def show_internal_consumption(self) -> None:
        self.internal_consumption_widget.refresh()
        self.view_stack.setCurrentWidget(self.internal_consumption_widget)

    def open_order_dialog(self) -> None:
        self._sync_products_from_table()
        dialog = ProductOrderDialog(self.state, self)
        if dialog.exec() == QDialog.Accepted:
            self._load_state_to_products()
            self.save_state(show_message=False)
            self.recalculate()

    def open_category_dialog(self) -> None:
        self._sync_products_from_table()
        category_service = EquivalenceCategoryService(self.state, self.service)
        category_state = category_service.dialog_state()
        dialog = ShipmentCategoryDialog(
            category_state,
            category_service,
            category_state.assignments.keys(),
            parent=self,
        )
        dialog.exec()
        self._load_state_to_products()
        self._refresh_equivalences()
        self.recalculate()

    def add_equivalence(self) -> None:
        test = self._selected_test()
        product = self._selected_product()
        if test is None or product is None:
            QMessageBox.information(self, "Equivalencia", "Selecciona una prueba y un producto.")
            return
        key = self.service.test_key(test)
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
        key, _values = self.service.equivalence_entry(self.state, test)
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
        self._results, self._warnings = self.service.calculate_with_internal_consumption(
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
            self.state.products = self.service.sorted_products(
                self.state.products,
                self.state.settings.get("product_categories", []),
            )
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
                    self._optional_number(values[3]),
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
        products_by_key = self.service.product_lookup(self.state.products)
        for product_key in self.service.equivalence_values(self.state, test):
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
                self._format_number(result.det_internal),
                self._format_number(result.det_env),
                result.quantity,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
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
    def _optional_number(value: object) -> float | None:
        text = str(value or "").strip()
        return EquivalenceTab._number(text) if text else None

    @staticmethod
    def _format_number(value: float | None) -> str:
        if value is None:
            return ""
        return str(int(value)) if float(value or 0).is_integer() else f"{value:.2f}"
