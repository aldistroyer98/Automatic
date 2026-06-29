from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt
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
from models.shipment import (
    ShipmentAnalysis,
    ShipmentFilterState,
    ShipmentOptions,
    ShipmentRecord,
)
from services.shipment_filters import (
    FILTER_FIELDS,
    compute_available_filter_options,
)
from services.shipment_config_service import ShipmentConfigService
from services.shipment_service import ShipmentService
from services.shipment_powerbi_service import ShipmentPowerBIService
from ui.dialogs import ShipmentCategoryDialog, ShipmentForecastDialog


class FullClickComboBox(QComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().installEventFilter(self)

    def set_options(self, values, selected: set[object]) -> None:
        self.blockSignals(True)
        self.clear()
        self.addItem("Todos", None)
        for value in values:
            self.addItem(str(value), value)
        if len(selected) == 1:
            index = self.findData(next(iter(selected)))
            self.setCurrentIndex(index if index >= 0 else 0)
        else:
            self.setCurrentIndex(0)
        self.blockSignals(False)
        self.set_summary(selected)

    def set_summary(self, selected: set[object]) -> None:
        if not selected:
            text = "Todos"
        elif len(selected) == 1:
            text = str(next(iter(selected)))
        else:
            text = f"{len(selected)} seleccionados"
        self.lineEdit().setText(text)
        self.setToolTip(", ".join(sorted(map(str, selected))) if selected else "Todos")

    def eventFilter(self, watched, event) -> bool:
        if watched is self.lineEdit() and event.type() == QEvent.MouseButtonPress:
            self.showPopup()
            return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.showPopup()


class ShipmentFilterDialog(QDialog):
    ALL_ITEM_DATA = "__ALL__"

    def __init__(
        self,
        records: tuple[ShipmentRecord, ...],
        state: ShipmentFilterState,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.records = records
        self.state = state.copy()
        self._updating = False
        self._explicit_empty_fields: set[str] = set()
        self.lists: dict[str, QListWidget] = {}
        self.setWindowTitle("Filtros de envío")
        self.resize(980, 560)
        self._build_ui()
        self._refresh_lists()

    def selected_state(self) -> ShipmentFilterState:
        state = self.state.copy()
        for field, (_record_field, state_field) in FILTER_FIELDS.items():
            available = set(compute_available_filter_options(self.records, state, field))
            selected = set(getattr(state, state_field))
            if selected == available:
                setattr(state, state_field, set())
        return state

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Buscar:", self))
        self.search_field = QLineEdit(self)
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._apply_search)
        search_row.addWidget(self.search_field, 1)
        root.addLayout(search_row)

        filters = QGridLayout()
        labels = (
            ("clients", "Cliente"),
            ("years", "Año"),
            ("lines", "Línea"),
            ("comodatos", "Comodato"),
        )
        for column, (key, label) in enumerate(labels):
            filters.addWidget(QLabel(label, self), 0, column)
            list_widget = QListWidget(self)
            list_widget.itemChanged.connect(
                lambda item, field=key: self._selection_changed(field, item)
            )
            self.lists[key] = list_widget
            filters.addWidget(list_widget, 1, column)
        for column, stretch in enumerate((3, 1, 2, 2)):
            filters.setColumnStretch(column, stretch)
        root.addLayout(filters)

        selection_row = QHBoxLayout()
        select_all_button = QPushButton("Seleccionar todo", self)
        select_all_button.clicked.connect(self._select_all)
        clear_button = QPushButton("Limpiar selección", self)
        clear_button.clicked.connect(self._clear_selection)
        selection_row.addWidget(select_all_button)
        selection_row.addWidget(clear_button)
        selection_row.addStretch(1)
        root.addLayout(selection_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Aplicar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_lists(self) -> None:
        options = compute_available_filter_options(self.records, self.state)
        self._updating = True
        for field, values in options.items():
            list_widget = self.lists[field]
            _record_field, state_field = FILTER_FIELDS[field]
            selected = set(getattr(self.state, state_field))
            all_selected = (
                field not in self._explicit_empty_fields
                and (not selected or selected == set(values))
            )
            list_widget.clear()
            all_item = QListWidgetItem("Todo")
            all_item.setData(Qt.UserRole, self.ALL_ITEM_DATA)
            all_item.setFlags(all_item.flags() | Qt.ItemIsUserCheckable)
            all_item.setCheckState(Qt.Checked if all_selected else Qt.Unchecked)
            list_widget.addItem(all_item)
            for value in values:
                item = QListWidgetItem(str(value))
                item.setData(Qt.UserRole, value)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.Checked if all_selected or value in selected else Qt.Unchecked
                )
                list_widget.addItem(item)
            list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._updating = False
        self._apply_search(self.search_field.text())

    def _selection_changed(self, field: str, changed_item: QListWidgetItem) -> None:
        if self._updating:
            return
        list_widget = self.lists[field]
        all_item = list_widget.item(0)
        if all_item is None:
            return
        if changed_item is all_item:
            check_state = all_item.checkState()
            self._updating = True
            for row in range(1, list_widget.count()):
                list_widget.item(row).setCheckState(check_state)
            self._updating = False
        selected = {
            list_widget.item(row).data(Qt.UserRole)
            for row in range(1, list_widget.count())
            if list_widget.item(row).checkState() == Qt.Checked
        }
        available = {
            list_widget.item(row).data(Qt.UserRole)
            for row in range(1, list_widget.count())
        }
        if selected:
            self._explicit_empty_fields.discard(field)
        else:
            self._explicit_empty_fields.add(field)
        _record_field, state_field = FILTER_FIELDS[field]
        setattr(self.state, state_field, selected)
        self._updating = True
        all_item.setCheckState(
            Qt.Checked if available and selected == available else Qt.Unchecked
        )
        self._updating = False
        self._remove_unavailable_selections()
        self._refresh_lists()

    def _remove_unavailable_selections(self) -> None:
        for field, (_record_field, state_field) in FILTER_FIELDS.items():
            selected = set(getattr(self.state, state_field))
            if selected:
                available = set(
                    compute_available_filter_options(self.records, self.state, field)
                )
                setattr(self.state, state_field, selected & available)

    def _select_all(self) -> None:
        self._explicit_empty_fields.clear()
        for field, (_record_field, state_field) in FILTER_FIELDS.items():
            values = compute_available_filter_options(self.records, self.state, field)
            setattr(self.state, state_field, set(values))
        self._refresh_lists()

    def _clear_selection(self) -> None:
        self.state = ShipmentFilterState()
        self._explicit_empty_fields = set(FILTER_FIELDS)
        self._refresh_lists()

    def _apply_search(self, text: str) -> None:
        needle = text.strip().casefold()
        for list_widget in self.lists.values():
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                item.setHidden(
                    row > 0 and bool(needle) and needle not in item.text().casefold()
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
        self.filter_state = ShipmentFilterState()
        self._updating_filters = False
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
        self.forecast_button = QPushButton("Previsión")
        self.forecast_button.clicked.connect(self.open_forecast_dialog)
        file_row.addWidget(load_button)
        file_row.addWidget(self.path_field, 1)
        file_row.addWidget(self.analyze_button)
        file_row.addWidget(self.category_button)
        file_row.addWidget(self.forecast_button)
        file_row.addWidget(self.generate_button)
        file_row.addWidget(self.powerbi_button)
        layout.addLayout(file_row)

        filters = QGridLayout()
        self.filter_boxes: dict[str, FullClickComboBox] = {}
        labels = (
            ("clients", "Cliente"),
            ("years", "Año"),
            ("lines", "Línea"),
            ("comodatos", "Comodato"),
        )
        for index, (key, label) in enumerate(labels):
            box = FullClickComboBox(self)
            box.addItem("Todos", None)
            box.activated.connect(
                lambda _index, field=key: self._main_filter_changed(field)
            )
            self.filter_boxes[key] = box
            filters.addWidget(QLabel(label), 0, index)
            filters.addWidget(box, 1, index)
        for index, stretch in enumerate((3, 2, 2, 2, 1)):
            filters.setColumnStretch(index, stretch)
        self.client_filter_button = QPushButton("Filtro", self)
        self.client_filter_button.setEnabled(False)
        self.client_filter_button.clicked.connect(self.open_client_filter_dialog)
        filters.addWidget(self.client_filter_button, 1, 4)
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
        self.filter_state = ShipmentFilterState()
        self._refresh_filter_controls()
        self.client_filter_button.setEnabled(True)
        self._update_client_filter_button()

    def _main_filter_changed(self, field: str) -> None:
        if self._updating_filters:
            return
        _record_field, state_field = FILTER_FIELDS[field]
        value = self.filter_boxes[field].currentData()
        setattr(self.filter_state, state_field, {value} if value is not None else set())
        self._remove_unavailable_filter_selections()
        self._refresh_filter_controls()
        self._update_client_filter_button()
        self.refresh_preview()

    def _remove_unavailable_filter_selections(self) -> None:
        if self.analysis is None:
            return
        for field, (_record_field, state_field) in FILTER_FIELDS.items():
            selected = set(getattr(self.filter_state, state_field))
            if selected:
                available = set(
                    compute_available_filter_options(
                        self.analysis.records,
                        self.filter_state,
                        field,
                    )
                )
                setattr(self.filter_state, state_field, selected & available)

    def _refresh_filter_controls(self) -> None:
        if self.analysis is None:
            return
        options = compute_available_filter_options(
            self.analysis.records,
            self.filter_state,
        )
        self._updating_filters = True
        try:
            for field, box in self.filter_boxes.items():
                _record_field, state_field = FILTER_FIELDS[field]
                box.set_options(options[field], set(getattr(self.filter_state, state_field)))
        finally:
            self._updating_filters = False

    def open_client_filter_dialog(self) -> None:
        if self.analysis is None:
            QMessageBox.information(self, "Filtro", "Primero carga y analiza una base de envíos.")
            return

        dialog = ShipmentFilterDialog(
            self.analysis.records,
            self.filter_state,
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        self.filter_state = dialog.selected_state()
        self._remove_unavailable_filter_selections()
        self._refresh_filter_controls()
        self._update_client_filter_button()
        self.refresh_preview()

    def _update_client_filter_button(self) -> None:
        self.client_filter_button.setText("Filtro")
        count = sum(
            bool(getattr(self.filter_state, state_field))
            for _record_field, state_field in FILTER_FIELDS.values()
        )
        if count:
            self.client_filter_button.setToolTip(
                f"Filtro avanzado activo en {count} campo(s)"
            )
        else:
            self.client_filter_button.setToolTip("Abrir filtro avanzado")

    def _options(self) -> ShipmentOptions:
        kwargs = {
            "create_client_sheets": True,
            "create_summary": True,
            "hide_normalized_data": True,
            "use_category_colors": True,
            "exclude_current_month": False,
            "average_from_first_shipment": True,
        }
        kwargs["clients"] = set(self.filter_state.selected_clients)
        kwargs["years"] = set(self.filter_state.selected_years)
        kwargs["lines"] = set(self.filter_state.selected_lines)
        kwargs["comodatos"] = set(self.filter_state.selected_comodatos)
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
                row.producto,
                f"{row.total:.0f}",
                row.meses,
                "" if row.prod is None else f"{row.prod:.1f}",
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
        return any(
            bool(getattr(self.filter_state, state_field))
            for _record_field, state_field in FILTER_FIELDS.values()
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
            output = self.service.generate_report(
                self.analysis,
                path,
                self._options(),
                self.category_config,
                self.category_config.forecast,
            )
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
        self.filter_state = ShipmentFilterState()
        for box in self.filter_boxes.values():
            box.set_options((), set())
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

    def open_forecast_dialog(self) -> None:
        if self.analysis is None:
            QMessageBox.information(
                self,
                "Previsión",
                "Primero carga y analiza una base de envíos para configurar la previsión.",
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
        dialog = ShipmentForecastDialog(
            self.category_config,
            self.config_service,
            active_product_keys,
            self,
        )
        dialog.exec()
        self.category_config = self.config_service.load()

    def _initial_product_sort_key(self, record, appearance_order: int):
        base = self.service._product_sort(record.cod_prod, record.producto, record.cod_eqv)
        return (base[0], base[2], base[3], appearance_order, base[4], base[5])

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _toggle_detail(self, visible: bool) -> None:
        self.log.setVisible(visible)
        self.detail_button.setText("Ocultar detalle" if visible else "Ver detalle")
