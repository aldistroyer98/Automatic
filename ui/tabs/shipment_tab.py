from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.paths import get_app_paths
from models.shipment import ShipmentAnalysis, ShipmentOptions
from models.shipment_config import ProductCategoryAssignment, ShipmentCategoryConfig
from services.shipment_config_service import ShipmentConfigService
from services.shipment_service import ShipmentService
from services.shipment_powerbi_service import ShipmentPowerBIService


class ShipmentTab(QWidget):
    def __init__(
        self,
        service: ShipmentService,
        parent=None,
        powerbi_service: ShipmentPowerBIService | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.powerbi_service = powerbi_service or ShipmentPowerBIService(service)
        self.config_service = ShipmentConfigService(get_app_paths().data_root / "shipment_categories.json")
        self.category_config = self.config_service.load()
        self.analysis: ShipmentAnalysis | None = None
        self._loading_category_ui = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        file_row = QHBoxLayout()
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        load_button = QPushButton("Cargar Base de Envíos")
        load_button.clicked.connect(self.select_source)
        self.analyze_button = QPushButton("Analizar")
        self.analyze_button.clicked.connect(self.analyze_source)
        self.generate_button = QPushButton("Generar Cuadro de Envíos")
        self.generate_button.clicked.connect(self.generate_report)
        self.powerbi_button = QPushButton("Exportar Power BI")
        self.powerbi_button.clicked.connect(self.export_powerbi)
        file_row.addWidget(load_button)
        file_row.addWidget(self.path_field, 1)
        file_row.addWidget(self.analyze_button)
        file_row.addWidget(self.generate_button)
        file_row.addWidget(self.powerbi_button)
        layout.addLayout(file_row)

        filters = QGridLayout()
        self.filter_boxes: dict[str, QComboBox] = {}
        labels = (
            ("clients", "Cliente"),
            ("years", "Año"),
            ("lines", "Línea"),
            ("comodatos", "Comodato"),
        )
        for index, (key, label) in enumerate(labels):
            box = QComboBox()
            box.addItem("Todos", None)
            box.currentIndexChanged.connect(self.refresh_preview)
            self.filter_boxes[key] = box
            filters.addWidget(QLabel(label), 0, index)
            filters.addWidget(box, 1, index)
        layout.addLayout(filters)

        options_row = QHBoxLayout()
        self.option_checks: dict[str, QCheckBox] = {}
        for key, text, checked in (
            ("create_client_sheets", "Crear una hoja por cliente", True),
            ("create_summary", "Crear resumen general", True),
            ("hide_normalized_data", "Ocultar Data_Normalizada", True),
            ("use_category_colors", "Usar colores por tipo", True),
            ("exclude_current_month", "Excluir mes actual", True),
            ("average_from_first_shipment", "Promedio desde primer envío", True),
        ):
            checkbox = QCheckBox(text)
            checkbox.setChecked(checked)
            self.option_checks[key] = checkbox
            options_row.addWidget(checkbox)
        options_row.addStretch(1)
        layout.addLayout(options_row)

        self._build_category_panel(layout)

        self.preview_table = QTableWidget(0, 9)
        self.preview_table.setHorizontalHeaderLabels(
            ("Cliente", "Año", "Línea", "CodProd", "CodEqv", "Producto", "Total", "Meses", "Prod")
        )
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.preview_table, 1)

        action_row = QHBoxLayout()
        clear_button = QPushButton("Limpiar")
        clear_button.clicked.connect(self.clear)
        action_row.addWidget(clear_button)
        self.detail_button = QPushButton("Ver detalle")
        self.detail_button.setCheckable(True)
        self.detail_button.toggled.connect(self._toggle_detail)
        action_row.addWidget(self.detail_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.status_label = QLabel("Carga una base de envíos para comenzar.")
        layout.addWidget(self.status_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMaximumHeight(120)
        self.log.setVisible(False)
        layout.addWidget(self.log)

    def _build_category_panel(self, layout: QVBoxLayout) -> None:
        title = QLabel("Categorías de productos")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        panel = QHBoxLayout()

        category_box = QVBoxLayout()
        category_buttons = QHBoxLayout()
        for text, handler in (
            ("Nueva categoría", self.add_category),
            ("Subir categoría", lambda: self.move_category(-1)),
            ("Bajar categoría", lambda: self.move_category(1)),
            ("Cambiar color", self.change_category_color),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            category_buttons.addWidget(button)
        category_box.addLayout(category_buttons)
        self.category_table = QTableWidget(0, 3)
        self.category_table.setHorizontalHeaderLabels(("Orden", "Categoría", "Color"))
        self.category_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        category_box.addWidget(self.category_table)
        panel.addLayout(category_box, 1)

        product_box = QVBoxLayout()
        product_buttons = QHBoxLayout()
        for text, handler in (
            ("Subir producto", lambda: self.move_product(-1)),
            ("Bajar producto", lambda: self.move_product(1)),
            ("Guardar configuración", self.save_category_config),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            product_buttons.addWidget(button)
        product_box.addLayout(product_buttons)
        self.product_category_table = QTableWidget(0, 5)
        self.product_category_table.setHorizontalHeaderLabels(
            ("Orden", "CodProd", "CodEqv", "Producto", "Categoría")
        )
        self.product_category_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.product_category_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        product_box.addWidget(self.product_category_table)
        panel.addLayout(product_box, 2)

        layout.addLayout(panel)
        self.refresh_category_tables()

    def select_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar base de envíos", "", "Archivos Excel (*.xlsx *.xlsm)"
        )
        if path:
            self.path_field.setText(path)
            self._append(f"Archivo cargado: {path}")

    def analyze_source(self) -> None:
        path = self.path_field.text().strip()
        if not path:
            QMessageBox.warning(self, "Envío", "Selecciona una base de envíos.")
            return
        try:
            self.analysis = self.service.analyze(path)
            changed = self.config_service.merge_products(self.category_config, self.analysis.records)
            if changed:
                self.config_service.save(self.category_config)
            self._populate_filters()
            self.refresh_category_tables()
            self.refresh_preview()
            status = (
                f"Filas leídas: {self.analysis.rows_read} | Clientes: {len(self.analysis.clients)} | "
                f"Años: {', '.join(map(str, self.analysis.years))} | Productos: {len(self.analysis.products)} | "
                f"Ignorados: {self.analysis.ignored_rows}"
            )
            self.status_label.setText(status)
            self._append(status)
            for error in self.analysis.errors[:10]:
                self._append(error)
        except Exception as exc:
            self._append(f"Error: {exc}")
            QMessageBox.critical(self, "Error al analizar", str(exc))

    def _populate_filters(self) -> None:
        assert self.analysis is not None
        records = self.analysis.records
        values = {
            "clients": self.analysis.clients,
            "years": self.analysis.years,
            "lines": self.analysis.lines,
            "comodatos": sorted({record.comodato for record in records if record.comodato}),
        }
        for key, box in self.filter_boxes.items():
            box.blockSignals(True)
            box.clear()
            box.addItem("Todos", None)
            for value in values[key]:
                box.addItem(str(value), value)
            box.blockSignals(False)

    def _options(self) -> ShipmentOptions:
        kwargs = {key: checkbox.isChecked() for key, checkbox in self.option_checks.items()}
        for key, box in self.filter_boxes.items():
            value = box.currentData()
            kwargs[key] = {value} if value is not None else set()
        return ShipmentOptions(**kwargs)

    def refresh_preview(self) -> None:
        if self.analysis is None:
            return
        rows = self.service.preview(self.analysis, self._options(), self.category_config)
        shown = rows[:500]
        self.preview_table.setRowCount(len(shown))
        for row_index, row in enumerate(shown):
            values = (
                row.cliente, row.anio, row.linea, row.cod_prod, row.cod_eqv,
                row.producto, f"{row.total:.0f}", row.meses, f"{row.prod:.1f}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (1, 6, 7, 8):
                    item.setTextAlignment(Qt.AlignCenter)
                self.preview_table.setItem(row_index, column, item)
        self.preview_table.resizeColumnsToContents()
        if len(rows) > len(shown):
            self._append(f"Vista previa limitada a {len(shown)} de {len(rows)} filas.")

    def generate_report(self) -> None:
        if self.analysis is None:
            self.analyze_source()
        if self.analysis is None:
            return
        suggested = self.analysis.source.with_name("Cuadro_de_Envios_Generado.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar cuadro de envíos", str(suggested), "Archivos Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            output = self.service.generate_report(self.analysis, path, self._options(), self.category_config)
            self._append(f"Archivo generado: {output}")
            QMessageBox.information(self, "Envío", f"Reporte generado correctamente:\n{output}")
        except Exception as exc:
            self._append(f"Error: {exc}")
            QMessageBox.critical(self, "Error al generar", str(exc))

    def export_powerbi(self) -> None:
        if self.analysis is None:
            self.analyze_source()
        if self.analysis is None:
            return
        selected = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta para Power BI",
            str(self.analysis.source.parent),
        )
        if not selected:
            return
        output_dir = Path(selected) / "powerbi_envio"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.powerbi_button.setEnabled(False)
        QApplication.processEvents()
        try:
            result = self.powerbi_service.export(
                self.analysis, output_dir, self._options()
            )
            years = ", ".join(map(str, result.years))
            status = (
                f"Power BI: {result.fact_rows} filas | Clientes: {result.clients} | "
                f"Productos: {result.products} | Años: {years}"
            )
            self.status_label.setText(status)
            self._append(f"Dataset Power BI generado: {result.output_dir}")
            QMessageBox.information(
                self,
                "Power BI",
                f"Dataset generado correctamente:\n{result.output_dir}\n\n{status}",
            )
        except Exception as exc:
            self._append(f"Error Power BI: {exc}")
            QMessageBox.critical(self, "Error al exportar Power BI", str(exc))
        finally:
            self.powerbi_button.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def clear(self) -> None:
        self.analysis = None
        self.path_field.clear()
        self.preview_table.setRowCount(0)
        self.product_category_table.setRowCount(0)
        self.log.clear()
        self.status_label.setText("Carga una base de envíos para comenzar.")
        for box in self.filter_boxes.values():
            box.clear()
            box.addItem("Todos", None)

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _toggle_detail(self, visible: bool) -> None:
        self.log.setVisible(visible)
        self.detail_button.setText("Ocultar detalle" if visible else "Ver detalle")

    def refresh_category_tables(self) -> None:
        self._loading_category_ui = True
        try:
            categories = self.category_config.sorted_categories()
            self.category_table.setRowCount(len(categories))
            for row, category in enumerate(categories):
                values = (row + 1, category.name, f"#{category.normalized_color()}")
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column in (0, 2):
                        item.setTextAlignment(Qt.AlignCenter)
                    if column == 2:
                        item.setBackground(QBrush(QColor(f"#{category.normalized_color()}")))
                    self.category_table.setItem(row, column, item)

            assignments = self._sorted_assignments()
            self.product_category_table.setRowCount(len(assignments))
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
                    self.product_category_table.setItem(row, column, item)
                combo = QComboBox()
                combo.addItems(names)
                combo.setCurrentText(assignment.category_name)
                combo.currentTextChanged.connect(
                    lambda value, key=assignment.product_key: self.assign_product_category(key, value)
                )
                self.product_category_table.setCellWidget(row, 4, combo)
            self.category_table.resizeColumnsToContents()
            self.product_category_table.resizeColumnsToContents()
        finally:
            self._loading_category_ui = False

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
        color = QColorDialog.getColor(parent=self, title="Color de categoría")
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
        if self._loading_category_ui:
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
        group = [
            item for item in self._sorted_assignments()
            if item.category_name == assignment.category_name
        ]
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
        self._append("Configuración de categorías guardada.")

    def _persist_and_refresh(self) -> None:
        self.config_service.save(self.category_config)
        self.refresh_category_tables()
        self.refresh_preview()

    def _selected_category(self) -> ShipmentCategoryConfig | None:
        row = self.category_table.currentRow()
        categories = self.category_config.sorted_categories()
        if row < 0 or row >= len(categories):
            QMessageBox.information(self, "Categorías", "Selecciona una categoría.")
            return None
        return categories[row]

    def _selected_assignment(self) -> ProductCategoryAssignment | None:
        row = self.product_category_table.currentRow()
        assignments = self._sorted_assignments()
        if row < 0 or row >= len(assignments):
            QMessageBox.information(self, "Categorías", "Selecciona un producto.")
            return None
        return assignments[row]

    def _sorted_assignments(self) -> list[ProductCategoryAssignment]:
        category_order = {
            category.name: category.order
            for category in self.category_config.categories
        }
        return sorted(
            self.category_config.assignments.values(),
            key=lambda item: (
                category_order.get(item.category_name, 1_000_000),
                item.product_order,
                item.producto.casefold(),
            ),
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
        for row, assignment in enumerate(self._sorted_assignments()):
            if assignment.product_key == key:
                self.product_category_table.selectRow(row)
                break
