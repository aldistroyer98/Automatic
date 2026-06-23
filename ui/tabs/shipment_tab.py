from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.paths import get_app_paths
from models.shipment import ShipmentAnalysis, ShipmentOptions
from services.shipment_config_service import ShipmentConfigService
from services.shipment_service import ShipmentService
from services.shipment_powerbi_service import ShipmentPowerBIService
from ui.dialogs import ShipmentCategoryDialog


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
        self.category_config = self.config_service.default_state()
        self.analysis: ShipmentAnalysis | None = None
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
        self.category_button = QPushButton("Configurar categorías")
        self.category_button.clicked.connect(self.open_category_dialog)
        file_row.addWidget(load_button)
        file_row.addWidget(self.path_field, 1)
        file_row.addWidget(self.analyze_button)
        file_row.addWidget(self.generate_button)
        file_row.addWidget(self.powerbi_button)
        file_row.addWidget(self.category_button)
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

        self.preview_table = QTableWidget(0, 9)
        self.preview_table.setHorizontalHeaderLabels(
            ("Cliente", "Año", "Línea", "CodProd", "CodEqv", "Producto", "Total", "Meses", "Media")
        )
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_table = QTableWidget(0, 9)
        self.preview_table.setHorizontalHeaderLabels(
            ("Cliente", "Año", "Línea", "CodProd", "CodEqv", "Producto", "Total", "Meses", "Media")
        )
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
            self.category_config = self.config_service.load()
            changed = self.config_service.merge_products(
                self.category_config,
                self.analysis.records,
                self._initial_product_sort_key,
            )
            if changed:
                self.config_service.save(self.category_config)
            self._populate_filters()
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
        kwargs = {
            "create_client_sheets": True,
            "create_summary": True,
            "hide_normalized_data": True,
            "use_category_colors": True,
            "exclude_current_month": True,
            "average_from_first_shipment": True,
        }
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
        self._resize_preview_columns()
        if len(rows) > len(shown):
            self._append(f"Vista previa limitada a {len(shown)} de {len(rows)} filas.")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_preview_columns()

    def _resize_preview_columns(self) -> None:
        if not hasattr(self, "preview_table"):
            return

        ratios = (12, 2, 4, 4, 4, 8, 2, 2, 2)

        total_units = 42
        content_units = sum(ratios)  # 40
        side_units = total_units - content_units  # 2 espacios invisibles

        viewport_width = self.preview_table.viewport().width()
        available = max(420, viewport_width - 2)

        unit = max(1, int(available / total_units))
        invisible_space = unit * side_units

        content_available = max(1, available - invisible_space)

        used = 0
        for column, ratio in enumerate(ratios):
            if column == len(ratios) - 1:
                width = max(1, content_available - used)
            else:
                width = max(1, int(content_available * ratio / content_units))
                used += width

            self.preview_table.setColumnWidth(column, width)

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
        self.category_config = self.config_service.default_state()
        self.path_field.clear()
        self.preview_table.setRowCount(0)
        self.log.clear()
        self.status_label.setText("Carga una base de envíos para comenzar.")
        for box in self.filter_boxes.values():
            box.clear()
            box.addItem("Todos", None)

    def open_category_dialog(self) -> None:
        if self.analysis is None:
            QMessageBox.information(
                self,
                "Categorías",
                "Primero carga y analiza una base de envíos para configurar las categorías.",
            )
            return
        changed = self.config_service.merge_products(
            self.category_config,
            self.analysis.records,
            self._initial_product_sort_key,
        )
        if changed:
            self.config_service.save(self.category_config)
        active_product_keys = {
            self.config_service.product_key_for_record(record)
            for record in self.analysis.records
        }
        dialog = ShipmentCategoryDialog(
            self.category_config,
            self.config_service,
            active_product_keys,
            self,
        )
        dialog.exec()
        self.category_config = self.config_service.load()
        self.refresh_preview()

    def _initial_product_sort_key(self, record, appearance_order: int):
        base = self.service._product_sort(record.cod_prod, record.producto, record.cod_eqv)
        return (base[0], base[2], base[3], appearance_order, base[4], base[5])

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _toggle_detail(self, visible: bool) -> None:
        self.log.setVisible(visible)
        self.detail_button.setText("Ocultar detalle" if visible else "Ver detalle")
