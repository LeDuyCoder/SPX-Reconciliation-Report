from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal


class RecordsTableModel(QAbstractTableModel):
    selection_changed = Signal(object)

    def __init__(self, columns, rows=None, parent=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.rows: list[dict[str, Any]] = rows or []
        self.selected_ids: set[int] = set()
        self.scope_ids: set[int] = set()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns) + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.rows)):
            return None
        if index.column() == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return (Qt.CheckState.Checked if self.rows[index.row()].get("id") in self.selected_ids
                        else Qt.CheckState.Unchecked)
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignCenter)
            return None
        column = self.columns[index.column() - 1]
        value = self.rows[index.row()].get(column.field)
        if role == Qt.ItemDataRole.DisplayRole:
            if value is None:
                return ""
            if column.kind == "number":
                try:
                    return f"{float(value):,.2f}".rstrip("0").rstrip(".")
                except (ValueError, TypeError):
                    pass
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and column.kind == "number":
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.UserRole:
            return self.rows[index.row()].get("_stt")
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and section == 0 and role == Qt.ItemDataRole.CheckStateRole:
            checked = self.scope_ids.intersection(self.selected_ids)
            if not checked:
                return Qt.CheckState.Unchecked
            return Qt.CheckState.Checked if self.scope_ids and checked == self.scope_ids else Qt.CheckState.PartiallyChecked
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and section == 0:
            return ""
        if orientation == Qt.Orientation.Horizontal and 1 <= section <= len(self.columns):
            return self.columns[section - 1].label
        if orientation == Qt.Orientation.Vertical and 0 <= section < len(self.rows):
            return str(self.rows[section].get("_stt", section + 1))
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            return flags | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
            return False
        record_id = self.rows[index.row()].get("id")
        if record_id is None:
            return False
        if value == Qt.CheckState.Checked or value == Qt.CheckState.Checked.value:
            self.selected_ids.add(record_id)
        else:
            self.selected_ids.discard(record_id)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)
        self.selection_changed.emit(set(self.selected_ids))
        return True

    def update_selection(self, selected_ids):
        self.selected_ids = set(selected_ids)
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, 0),
                                  [Qt.ItemDataRole.CheckStateRole])
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def set_scope_ids(self, ids):
        self.scope_ids = set(ids)
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 0)

    def update_rows_selection(self, ids, checked):
        if checked:
            self.selected_ids.update(ids)
        else:
            self.selected_ids.difference_update(ids)
        self.update_selection(self.selected_ids)
        self.selection_changed.emit(set(self.selected_ids))

    def replace(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()
