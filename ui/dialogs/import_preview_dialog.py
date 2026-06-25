from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from models.equivalence import ImportPreviewRow, TenderTest

if TYPE_CHECKING:
    from ui.tabs.equivalence_tab import EquivalenceTab


class ImportPreviewDialog(QDialog):
    CRITICAL_STATUSES = {"Fila incompleta", "Revisar código", "Revisar cantidad"}

    def __init__(
        self,
        tab: "EquivalenceTab",
        _path: str | Path,
        rows: list[ImportPreviewRow],
    ) -> None:
        super().__init__(tab)
        self.tab = tab
        self.accepted_tests: list[TenderTest] = []
        self._loading = False
        self.setWindowTitle("Revision de importacion")
        self.resize(1040, 620)
        self._build_ui()
        self._load_rows(rows)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Vista previa editable"))

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(("Código SAP", "Descripción", "Cantidad", "Estado"))
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 160)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._item_changed)
        root.addWidget(self.table, 1)

        edit_row = QHBoxLayout()
        add_button = QPushButton("Agregar", self)
        add_button.clicked.connect(self.add_row)
        manual_button = QPushButton("Editar", self)
        manual_button.clicked.connect(self.edit_current_cell)
        delete_button = QPushButton("Eliminar", self)
        delete_button.clicked.connect(self.delete_rows)
        edit_row.addWidget(add_button)
        edit_row.addWidget(manual_button)
        edit_row.addWidget(delete_button)
        edit_row.addStretch(1)
        confirm_button = QPushButton("Confirmar", self)
        confirm_button.clicked.connect(self.confirm_load)
        cancel_button = QPushButton("Cancelar", self)
        cancel_button.clicked.connect(self.reject)
        edit_row.addWidget(confirm_button)
        edit_row.addWidget(cancel_button)
        root.addLayout(edit_row)

    def add_row(self) -> None:
        self._append_row(ImportPreviewRow(status="Fila incompleta"))
        self.table.selectRow(self.table.rowCount() - 1)
        self.edit_current_cell()

    def delete_rows(self) -> None:
        rows = sorted(
            {index.row() for index in self.table.selectionModel().selectedRows()},
            reverse=True,
        )
        for row in rows:
            self.table.removeRow(row)

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
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column == 3:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
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
