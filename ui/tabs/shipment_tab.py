from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidgetAction,
    QWidget,
)

from app.paths import get_app_paths
from models.shipment import ShipmentAnalysis, ShipmentOptions
from services.shipment_config_service import ShipmentConfigService
from services.shipment_service import ShipmentService
from services.shipment_powerbi_service import ShipmentPowerBIService
from ui.dialogs import ShipmentCategoryDialog


class ClientChecklistFilter(QToolButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPopupMode(QToolButton.InstantPopup)
        self._clients: list[str] = []
        self._selected: set[str] = set()
        self._updating = False
        self._on_changed = None
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.setText("Clientes: Todos")

    def set_on_changed(self, callback) -> None:
        self._on_changed = callback

    def set_clients(self, clients: list[str]) -> None:
        previous_clients = set(self._clients)
        previous_selected = set(self._selected)
        was_all = not previous_clients or previous_selected == previous_clients
        self._clients = list(clients)
        available = set(self._clients)
        self._selected = available if was_all else previous_selected & available
        self._rebuild_menu()
        self._update_text()

    def selected_clients(self) -> set[str]:
        return set(self._selected)

    def _rebuild_menu(self) -> None:
        self._updating = True
        self._menu.clear()
        all_box = QCheckBox("Todo")
        all_box.setChecked(bool(self._clients) and self._selected == set(self._clients))
        all_box.stateChanged.connect(self._toggle_all)
        self._add_checkbox_action(all_box)
        self._menu.addSeparator()
        for client in self._clients:
            box = QCheckBox(client)
            box.setChecked(client in self._selected)
            box.stateChanged.connect(lambda _state, value=client: self._toggle_client(value))
            self._add_checkbox_action(box)
        self._updating = False

    def _add_checkbox_action(self, checkbox: QCheckBox) -> None:
        action = QWidgetAction(self._menu)
        action.setDefaultWidget(checkbox)
        self._menu.addAction(action)

    def _toggle_all(self) -> None:
        if self._updating:
            return
        self._selected = set(self._clients) if self._selected != set(self._clients) else set()
        self._rebuild_menu()
        self._notify()

    def _toggle_client(self, client: str) -> None:
        if self._updating:
            return
        if client in self._selected:
            self._selected.remove(client)
        else:
            self._selected.add(client)
        self._rebuild_menu()
        self._notify()

    def _notify(self) -> None:
        self._update_text()
        if self._on_changed is not None:
            self._on_changed()

    def _update_text(self) -> None:
        if not self._clients or self._selected == set(self._clients):
            self.setText("Clientes: Todos")
        elif not self._selected:
            self.setText("Clientes: Ninguno")
        else:
            self.setText(f"Clientes: {len(self._selected)}")


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
        load_button = QPushButton("Cargar DataBase")
        load_button.clicked.connect(self.select_source)
        self.analyze_button = QPushButton("Analizar")
        self.analyze_button.clicked.connect(self.analyze_source)
        self.generate_button = QPushButton("Exportar Excel")
        self.generate_button.clicked.connect(self.generate_report)
        self.powerbi_button = QPushButton("Exportar Power BI")
        self.powerbi_button.clicked.connect(self.export_powerbi)
        self.category_button = QPushButton("Categorías")
        self.category_button.clicked.connect(self.open_category_dialog)
        file_row.addWidget(load_button)
        file_row.addWidget(self.path_field, 1)
        file_row.addWidget(self.analyze_button)
        file_row.addWidget(self.category_button)
        file_row.addWidget(self.generate_button)
        file_row.addWidget(self.powerbi_button)
        layout.addLayout(file_row)

        filters = QGridLayout()
        self.filter_boxes: dict[str, QComboBox] = {}
        self.client_filter = ClientChecklistFilter(self)
        self.client_filter.set_on_changed(self.refresh_preview)
        filters.addWidget(QLabel("Cliente"), 0, 0)
        filters.addWidget(self.client_filter, 1, 0)
        labels = (
            ("years", "Año"),
            ("lines", "Línea"),
            ("comodatos", "Comodato"),
        )
        for index, (key, label) in enumerate(labels, start=1):
            box = QComboBox()
            box.addItem("Todos", None)
            if key in {"years", "lines"}:
                box.currentIndexChanged.connect(self._handle_filter_changed)
            else:
                box.currentIndexChanged.connect(self.refresh_preview)
            self.filter_boxes[key] = box
            filters.addWidget(QLabel(label), 0, index)
            filters.addWidget(box, 1, index)
        for index, stretch in enumerate((4, 2, 2, 2)):
            filters.setColumnStretch(index, stretch)
        layout.addLayout(filters)

        self.preview_table = QTableWidget(0, 9)
        self.preview_table.setHorizontalHeaderLabels(
            ("Cliente", "Año", "Línea", "CodProd", "CodEqv", "Producto", "Total", "Meses", "Media")
        )
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.preview_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.preview_table.horizontalHeader().setStretchLastSection(False)
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
        self._update_client_filter()

    def _handle_filter_changed(self) -> None:
        self._update_client_filter()
        self.refresh_preview()

    def _update_client_filter(self) -> None:
        if self.analysis is None:
            self.client_filter.set_clients([])
            return
        year = self.filter_boxes["years"].currentData()
        line = self.filter_boxes["lines"].currentData()
        clients = sorted({
            record.cliente
            for record in self.analysis.records
            if (year is None or record.anio == year)
            and (line is None or record.linea == line)
        })
        self.client_filter.set_clients(clients)

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
        selected_clients = self.client_filter.selected_clients()
        visible_clients = set(self.client_filter._clients)
        if visible_clients and not selected_clients:
            kwargs["clients"] = {"__NO_CLIENT_SELECTED__"}
        else:
            kwargs["clients"] = selected_clients if selected_clients != visible_clients else set()
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
        total_units = sum(ratios)  # 40

        viewport_width = self.preview_table.viewport().width()
        available = max(420, viewport_width - 2)

        used = 0
        for column, ratio in enumerate(ratios):
            if column == len(ratios) - 1:
                width = max(1, available - used)
            else:
                width = max(1, int(available * ratio / total_units))
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
        self.client_filter.set_clients([])

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
            self.analysis.lines,
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
