"""Editable data grid with explicit pending edits and transactional validation."""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import QTableView, QApplication, QHeaderView
from core.elements_data import ALL_SYMBOLS


class ElementTableModel(QAbstractTableModel):
    error = Signal(str)
    committed = Signal()

    def __init__(self, apply_data, parent=None):
        super().__init__(parent)
        self.apply_data = apply_data
        self.values, self.pending = {}, {}
        self.caption = '数值 / 标注'

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(ALL_SYMBOLS)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return ('序数', '元素', self.caption)[section] if orientation == Qt.Orientation.Horizontal else section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        symbol = ALL_SYMBOLS[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return (index.row() + 1, symbol, self.pending.get(symbol, self.values.get(symbol, '')))[index.column()]
        if role == Qt.ItemDataRole.BackgroundRole and index.column() == 2 and symbol in self.pending:
            return QColor('#fff0e8')
        if role == Qt.ItemDataRole.ToolTipRole and symbol in self.pending:
            return '尚未提交：请修正数值，或撤销未提交的输入'

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsEditable if index.column() == 2 else flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid() or index.column() != 2:
            return False
        self.pending[ALL_SYMBOLS[index.row()]] = str(value)
        self.dataChanged.emit(index, index)
        self.flush()
        return True

    def flush(self):
        if not self.pending:
            return True
        patch = {key: value if value.strip() else None for key, value in self.pending.items()}
        try:
            self.apply_data(patch)
        except (ValueError, OSError) as exc:
            self.error.emit(str(exc))
            return False
        for symbol, value in patch.items():
            if value is None:
                self.values.pop(symbol, None)
            else:
                self.values[symbol] = value
        self.pending.clear()
        self.dataChanged.emit(self.index(0, 2), self.index(self.rowCount() - 1, 2))
        self.committed.emit()
        return True

    def set_snapshot(self, values, caption=None, discard_pending=False, protected_symbol=None):
        previous = self.values
        if discard_pending:
            self.beginResetModel()
        self.values = dict(values)
        if discard_pending:
            self.pending.clear()
        if caption is not None:
            self.caption = caption
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 2, 2)
        if discard_pending:
            self.endResetModel()
        else:
            for row, symbol in enumerate(ALL_SYMBOLS):
                if symbol != protected_symbol and previous.get(symbol, '') != self.values.get(symbol, ''):
                    self.dataChanged.emit(self.index(row, 2), self.index(row, 2))


class ElementTable(QTableView):
    pasteRequested = Signal(str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.setModel(model)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0, 64)
        self.setColumnWidth(1, 80)
        self.verticalHeader().setDefaultSectionSize(29)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            cells = self.selectedIndexes()
            if cells:
                rows = range(min(i.row() for i in cells), max(i.row() for i in cells) + 1)
                cols = range(min(i.column() for i in cells), max(i.column() for i in cells) + 1)
                selected = {(i.row(), i.column()) for i in cells}
                text = '\n'.join('\t'.join(str(self.model().data(self.model().index(row, col)))
                    if (row, col) in selected else '' for col in cols) for row in rows)
                QApplication.clipboard().setText(text)
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            text = QApplication.clipboard().text()
            if '\t' not in text and '\n' not in text and self.currentIndex().column() == 2:
                self.model().setData(self.currentIndex(), text)
            else:
                self.pasteRequested.emit(text)
            return
        super().keyPressEvent(event)
