from __future__ import annotations

from collections.abc import Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem


def resize_columns_by_ratio(table: QTableWidget, ratios: Sequence[int]) -> None:
    """Resize all table columns to fill the viewport using integer ratios."""
    if not ratios or len(ratios) != table.columnCount():
        return
    available = max(1, table.viewport().width())
    total = max(1, sum(max(0, ratio) for ratio in ratios))
    used = 0
    for column, ratio in enumerate(ratios):
        if column == len(ratios) - 1:
            width = available - used
        else:
            width = int(available * max(0, ratio) / total)
            used += width
        table.setColumnWidth(column, max(1, width))


def center_table_item(item: QTableWidgetItem) -> QTableWidgetItem:
    item.setTextAlignment(Qt.AlignCenter)
    return item


def make_readonly_item(
    value: object = "",
    *,
    alignment: Qt.AlignmentFlag | Qt.Alignment = Qt.AlignCenter,
) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    item.setTextAlignment(alignment)
    return item


def set_table_alignment(
    table: QTableWidget,
    alignment: Qt.AlignmentFlag | Qt.Alignment = Qt.AlignCenter,
    *,
    columns: Iterable[int] | None = None,
) -> None:
    selected_columns = set(columns) if columns is not None else None
    for row in range(table.rowCount()):
        for column in range(table.columnCount()):
            if selected_columns is not None and column not in selected_columns:
                continue
            item = table.item(row, column)
            if item is not None:
                item.setTextAlignment(alignment)


def clear_selection_safe(table: QTableWidget | None) -> None:
    if table is None:
        return
    selection_model = table.selectionModel()
    if selection_model is not None:
        selection_model.clearSelection()
    table.setCurrentItem(None)
