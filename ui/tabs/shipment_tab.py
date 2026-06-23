from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Signal, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from models.shipment import ShipmentAnalysis, ShipmentOptions, ShipmentRecord
from services.shipment_config_service import ShipmentConfigService
from services.shipment_service import ShipmentService
from services.shipment_powerbi_service import ShipmentPowerBIService
from ui.dialogs import ShipmentCategoryDialog


class CheckableComboBox(QComboBox):
    selectionChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.setModel(QStandardItemModel(self))
        self.view().viewport().installEventFilter(self)
        self.set_values(())

    def set_values(self, values) -> None:
        self.model().clear()
        self._append_item("Todos", None, checked=True)
        for value in values:
            self._append_item(str(value), value)
        self._update_summary()

    def selected_data(self) -> set[object]:
        model = self.model()
        return {
            model.item(row).data(Qt.UserRole)
            for row in range(1, model.rowCount())
            if model.item(row).checkState() == Qt.Checked
        }

    def set_selected_data(self, values) -> None:
        selected = set(values or ())
        model = self.model()
        model.item(0).setCheckState(Qt.Checked if not selected else Qt.Unchecked)
        for row in range(1, model.rowCount()):
            item = model.item(row)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in selected else Qt.Unchecked)
        self._normalize_selection()
        self._update_summary()

    def clear_values(self) -> None:
        self.set_values(())

    def eventFilter(self, watched, event) -> bool:
        if watched is self.view().viewport() and event.type() == QEvent.MouseButtonRelease:
            index = self.view().indexAt(event.position().toPoint())
            if index.isValid():
                self._toggle_row(index.row())
                return True
        return super().eventFilter(watched, event)

    def _append_item(self, text: str, data: object, *, checked: bool = False) -> None:
        item = QStandardItem(text)
        item.setData(data, Qt.UserRole)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.model().appendRow(item)

    def _toggle_row(self, row: int) -> None:
        model = self.model()
        if row == 0:
            for index in range(model.rowCount()):
                model.item(index).setCheckState(Qt.Checked if index == 0 else Qt.Unchecked)
        else:
            item = model.item(row)
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
            model.item(0).setCheckState(Qt.Unchecked)
            self._normalize_selection()
        self._update_summary()
        self.selectionChanged.emit()

    def _normalize_selection(self) -> None:
        model = self.model()
        specifics = [model.item(row) for row in range(1, model.rowCount())]
        checked = [item for item in specifics if item.checkState() == Qt.Checked]
        if not checked or (specifics and len(checked) == len(specifics)):
            model.item(0).setCheckState(Qt.Checked)
            for item in specifics:
                item.setCheckState(Qt.Unchecked)

    def _update_summary(self) -> None:
        selected = self.selected_data()
        if not selected:
            text = "Todos"
        elif len(selected) <= 2:
            text = ", ".join(str(value) for value in sorted(selected, key=str))
        else:
            text = f"{len(selected)} seleccionados"
        self.lineEdit().setText(text)
        self.setToolTip(", ".join(str(value) for value in sorted(selected, key=str)) or "Todos")


class ClientFilterDialog(QDialog):
    def __init__(
        self,
        records: tuple[ShipmentRecord, ...],
        selected_clients: set[str],
        initial_filters: dict[str, object],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.records = records
        self._selected_clients = set(selected_clients)
        self._updating = False
        self.filter_boxes: dict[str, QComboBox] = {}
        self.setWindowTitle("Filtro de clientes")
        self.resize(520, 560)
        self._build_ui()
        self._set_initial_filters(initial_filters)
        self._refresh_clients()

    def selected_clients(self) -> set[str]:
        return set(self._selected_clients)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        filters = QGridLayout()
        values = {
            "years": sorted({record.anio for record in self.records}),
            "lines": sorted({record.linea for record in self.records if record.linea}),
            "comodatos": sorted({record.comodato for record in self.records if record.comodato}),
        }
        labels = (
            ("years", "Año"),
            ("lines", "Línea"),
            ("comodatos", "Comodato"),
        )
        for column, (key, label) in enumerate(labels):
            box = QComboBox(self)
            box.addItem("Todos", None)
            for value in values[key]:
                box.addItem(str(value), value)
            box.currentIndexChanged.connect(self._refresh_clients)
            self.filter_boxes[key] = box
            filters.addWidget(QLabel(label, self), 0, column)
            filters.addWidget(box, 1, column)
            filters.setColumnStretch(column, 1)
        root.addLayout(filters)

        self.count_label = QLabel(self)
        root.addWidget(self.count_label)

        self.client_list = QListWidget(self)
        self.client_list.itemChanged.connect(self._client_item_changed)
        root.addWidget(self.client_list, 1)

        selection_row = QHBoxLayout()
        select_visible_button = QPushButton("Seleccionar visibles", self)
        select_visible_button.clicked.connect(self._select_visible_clients)
        clear_button = QPushButton("Limpiar", self)
        clear_button.clicked.connect(self._clear_clients)
        selection_row.addWidget(select_visible_button)
        selection_row.addWidget(clear_button)
        selection_row.addStretch(1)
        root.addLayout(selection_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Aplicar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _set_initial_filters(self, initial_filters: dict[str, object]) -> None:
        for key, value in initial_filters.items():
            box = self.filter_boxes.get(key)
            if box is None:
                continue
            index = box.findData(value)
            if index >= 0:
                box.setCurrentIndex(index)

    def _refresh_clients(self) -> None:
        clients = self._filtered_clients()
        self._updating = True
        self.client_list.clear()
        for client in clients:
            item = QListWidgetItem(client)
            item.setData(Qt.UserRole, client)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if client in self._selected_clients else Qt.Unchecked)
            self.client_list.addItem(item)
        self._updating = False
        self._update_count(len(clients))

    def _client_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating:
            return
        client = str(item.data(Qt.UserRole) or "")
        if item.checkState() == Qt.Checked:
            self._selected_clients.add(client)
        else:
            self._selected_clients.discard(client)
        self._update_count(len(self._filtered_clients()))

    def _select_visible_clients(self) -> None:
        self._selected_clients.update(self._filtered_clients())
        self._refresh_clients()

    def _clear_clients(self) -> None:
        self._selected_clients.clear()
        self._refresh_clients()

    def _filtered_clients(self) -> list[str]:
        year = self.filter_boxes["years"].currentData()
        line = self.filter_boxes["lines"].currentData()
        comodato = self.filter_boxes["comodatos"].currentData()
        return sorted({
            record.cliente
            for record in self.records
            if (year is None or record.anio == year)
            and (line is None or record.linea == line)
            and (comodato is None or record.comodato == comodato)
        })

    def _update_count(self, visible_count: int) -> None:
        self.count_label.setText(
            f"Clientes visibles: {visible_count} | Seleccionados: {len(self._selected_clients)}"
        )


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
        self._advanced_clients_applied = False
        self._advanced_client_selection: set[str] = set()
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
        self.filter_boxes: dict[str, QComboBox | CheckableComboBox] = {}
        self.client_combo = QComboBox(self)
        self.client_combo.addItem("Todos", None)
        self.client_combo.currentIndexChanged.connect(self._handle_client_combo_changed)
        self.client_filter_button = QPushButton("Filtro", self)
        self.client_filter_button.setEnabled(False)
        self.client_filter_button.clicked.connect(self.open_client_filter_dialog)
        client_box = QWidget(self)
        client_layout = QHBoxLayout(client_box)
        client_layout.setContentsMargins(0, 0, 0, 0)
        client_layout.addWidget(self.client_combo, 3)
        client_layout.addWidget(self.client_filter_button, 1)
        filters.addWidget(QLabel("Cliente"), 0, 0)
        filters.addWidget(client_box, 1, 0)
        labels = (
            ("years", "Año"),
            ("lines", "Línea"),
            ("comodatos", "Comodato"),
        )
        for index, (key, label) in enumerate(labels, start=1):
            multiple = key in {"years", "lines"}
            box = CheckableComboBox() if multiple else QComboBox()
            if multiple:
                box.selectionChanged.connect(self.refresh_preview)
            else:
                box.addItem("Todos", None)
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
        self.status_label = QLabel("Carga una base de envíos para comenzar.", self)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        action_row.addWidget(self.status_label, 4)
        layout.addLayout(action_row)

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
            if isinstance(box, CheckableComboBox):
                box.set_values(values[key])
            else:
                box.blockSignals(True)
                box.clear()
                box.addItem("Todos", None)
                for value in values[key]:
                    box.addItem(str(value), value)
                box.blockSignals(False)
        self._advanced_clients_applied = False
        self._advanced_client_selection.clear()
        self._populate_client_combo()
        self.client_filter_button.setEnabled(True)
        self._update_client_filter_button()

    def _handle_client_combo_changed(self) -> None:
        self._advanced_clients_applied = False
        self._advanced_client_selection.clear()
        self._update_client_filter_button()
        self.refresh_preview()

    def _populate_client_combo(self) -> None:
        current = self.client_combo.currentData()
        clients = self.analysis.clients if self.analysis is not None else ()
        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItem("Todos", None)
        for client in clients:
            self.client_combo.addItem(client, client)
        index = self.client_combo.findData(current)
        self.client_combo.setCurrentIndex(index if index >= 0 else 0)
        self.client_combo.blockSignals(False)

    def open_client_filter_dialog(self) -> None:
        if self.analysis is None:
            QMessageBox.information(self, "Filtro", "Primero carga y analiza una base de envíos.")
            return

        all_clients = set(self.analysis.clients)
        selected_client = self.client_combo.currentData()
        if self._advanced_clients_applied:
            initial_selection = set(self._advanced_client_selection)
        elif selected_client is not None:
            initial_selection = {str(selected_client)}
        else:
            initial_selection = set(all_clients)

        dialog = ClientFilterDialog(
            self.analysis.records,
            initial_selection,
            {
                key: (
                    next(iter(box.selected_data()))
                    if isinstance(box, CheckableComboBox) and len(box.selected_data()) == 1
                    else box.currentData() if not isinstance(box, CheckableComboBox) else None
                )
                for key, box in self.filter_boxes.items()
            },
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        selected_clients = dialog.selected_clients()
        self._advanced_client_selection = selected_clients
        self._advanced_clients_applied = selected_clients != all_clients
        self.client_combo.blockSignals(True)
        self.client_combo.setCurrentIndex(0)
        self.client_combo.blockSignals(False)
        self._update_client_filter_button()
        self.refresh_preview()

    def _update_client_filter_button(self) -> None:
        self.client_filter_button.setText("Filtro")
        if self._advanced_clients_applied:
            count = len(self._advanced_client_selection)
            self.client_filter_button.setToolTip(f"Filtro avanzado activo: {count} clientes")
        else:
            self.client_filter_button.setToolTip("Abrir filtro avanzado de clientes")

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
            if isinstance(box, CheckableComboBox):
                kwargs[key] = box.selected_data()
            else:
                value = box.currentData()
                kwargs[key] = {value} if value is not None else set()
        selected_client = self.client_combo.currentData()
        if self._advanced_clients_applied and not self._advanced_client_selection:
            kwargs["clients"] = {"__NO_CLIENT_SELECTED__"}
        elif self._advanced_clients_applied:
            kwargs["clients"] = set(self._advanced_client_selection)
        elif selected_client is not None:
            kwargs["clients"] = {str(selected_client)}
        else:
            kwargs["clients"] = set()
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
        self._update_filtered_status(rows)
        if len(rows) > len(shown):
            self._append(f"Vista previa limitada a {len(shown)} de {len(rows)} filas.")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_preview_columns()

    def _resize_preview_columns(self) -> None:
        if not hasattr(self, "preview_table"):
            return

        ratios = (6, 1, 3, 2, 2, 4, 1, 1, 1)
        total_units = sum(ratios)
        available = max(1, self.preview_table.viewport().width())

        used = 0
        for column, ratio in enumerate(ratios):
            if column == len(ratios) - 1:
                width = max(1, available - used)
            else:
                width = max(1, int(available * ratio / total_units))
                used += width

            self.preview_table.setColumnWidth(column, width)

    def _update_filtered_status(self, rows) -> None:
        if self.analysis is None:
            return
        clients = {row.cliente for row in rows}
        years = sorted({row.anio for row in rows})
        products = {row.producto for row in rows}
        ignored = self.analysis.ignored_rows if not self._has_active_filters() else 0
        status = (
            f"Filas leídas: {len(rows)} | Clientes: {len(clients)} | "
            f"Años: {', '.join(map(str, years)) if years else '-'} | "
            f"Productos: {len(products)} | Ignorados: {ignored}"
        )
        self.status_label.setText(status)

    def _has_active_filters(self) -> bool:
        if self.client_combo.currentData() is not None or self._advanced_clients_applied:
            return True
        return any(
            bool(box.selected_data())
            if isinstance(box, CheckableComboBox)
            else box.currentData() is not None
            for box in self.filter_boxes.values()
        )

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
            if isinstance(box, CheckableComboBox):
                box.clear_values()
            else:
                box.clear()
                box.addItem("Todos", None)
        self._advanced_clients_applied = False
        self._advanced_client_selection.clear()
        self.client_combo.clear()
        self.client_combo.addItem("Todos", None)
        self.client_filter_button.setEnabled(False)
        self._update_client_filter_button()

    def save_profile(self, destination: str | Path, ui_preferences: dict | None = None) -> Path:
        return self.config_service.export_profile(
            self.category_config,
            destination,
            ui_preferences=ui_preferences,
        )

    def load_profile(self, source: str | Path) -> dict:
        state, ui_preferences = self.config_service.import_profile(source)
        self.category_config = state
        if self.analysis is not None:
            changed = self.config_service.merge_products(
                self.category_config,
                self.analysis.records,
                self._initial_product_sort_key,
            )
            if changed:
                self.config_service.save(self.category_config)
            self.refresh_preview()
        else:
            self.config_service.save(self.category_config)
        return ui_preferences

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
