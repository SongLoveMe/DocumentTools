from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QUrl, Qt, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QTableWidget,
)


class FileTable(QTableWidget):
    paths_dropped = pyqtSignal(list)
    order_changing = pyqtSignal()
    order_changed = pyqtSignal()

    def __init__(self, columns: list[str], parent=None):
        super().__init__(0, len(columns), parent)
        self.setHorizontalHeaderLabels(columns)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.setMinimumHeight(170)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        if event.source() is self:
            target = self.indexAt(event.pos()).row()
            if target < 0:
                target = self.rowCount()
            else:
                target += int(event.pos().y() > self.visualRect(self.model().index(target, 0)).center().y())
            rows = sorted({index.row() for index in self.selectedIndexes()})
            if rows:
                self.move_rows(rows, target)
            event.acceptProposedAction()
            return
        if event.mimeData().hasUrls():
            self.paths_dropped.emit([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self.order_changing.emit()
        for row in rows:
            self.removeRow(row)
        self.order_changed.emit()

    def move_rows(self, rows: list[int], target: int) -> None:
        rows = sorted(set(rows))
        if not rows or target < 0 or target > self.rowCount():
            return
        self.order_changing.emit()
        values = [[self.takeItem(row, column) for column in range(self.columnCount())] for row in rows]
        for row in reversed(rows):
            self.removeRow(row)
        target -= sum(row < target for row in rows)
        for offset, row_items in enumerate(values):
            row = target + offset
            self.insertRow(row)
            for column, item in enumerate(row_items):
                self.setItem(row, column, item)
        self.clearSelection()
        for offset in range(len(values)):
            self.selectRow(target + offset)
        self.setCurrentCell(target, 0)
        self.order_changed.emit()


def button_row(table: FileTable, chooser: Callable[[], None]) -> QHBoxLayout:
    row = QHBoxLayout()
    add = QPushButton("添加文件")
    add.clicked.connect(chooser)
    remove = QPushButton("移除选中")
    remove.clicked.connect(table.remove_selected)
    clear = QPushButton("清空列表")
    clear.clicked.connect(table.clearContents)
    clear.clicked.connect(lambda: table.setRowCount(0))
    row.addWidget(add)
    row.addWidget(remove)
    row.addWidget(clear)
    row.addStretch()
    return row


class OutputLog(QListWidget):
    """Clickable, structured output log."""

    output_double_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("outputLog")
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setMinimumHeight(110)
        self.itemDoubleClicked.connect(self._open_item)

    def add_message(self, message: str, path: str | Path | None = None) -> None:
        item = QListWidgetItem(message)
        if path is not None:
            item.setData(Qt.UserRole, str(path))
            item.setToolTip("Double-click to open: " + str(path))
        self.addItem(item)
        self.scrollToBottom()

    def clear_log(self) -> None:
        self.clear()

    def _open_item(self, item: QListWidgetItem) -> None:
        raw = item.data(Qt.UserRole)
        if not raw:
            return
        path = Path(str(raw))
        if not path.exists():
            QMessageBox.warning(self, "File not found", "The output no longer exists:\n" + str(path))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.output_double_clicked.emit(str(path))


def open_folder(path: str | Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path))))
