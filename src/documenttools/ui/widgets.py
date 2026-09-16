from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QUrl, Qt, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget,
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


def button_row(
    table: FileTable,
    chooser: Callable[[], None],
    *,
    add_text: str = "添加文件",
    remove_text: str = "移除选中",
    clear_text: str = "清空列表",
) -> QHBoxLayout:
    row = QHBoxLayout()
    add = QPushButton(add_text)
    add.clicked.connect(chooser)
    remove = QPushButton(remove_text)
    remove.clicked.connect(table.remove_selected)
    clear = QPushButton(clear_text)
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
            item.setToolTip("双击打开：" + str(path))
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
            QMessageBox.warning(self, "文件不存在", "输出文件已不存在：\n" + str(path))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.output_double_clicked.emit(str(path))


class LogSection(QWidget):
    """Shared log heading, clear action and clickable output list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        heading = QHBoxLayout()
        label = QLabel("处理日志（双击输出记录可打开文件）")
        self.clear_button = QPushButton("清除日志")
        self.clear_button.clicked.connect(self.clear)
        heading.addWidget(label)
        heading.addStretch()
        heading.addWidget(self.clear_button)
        layout.addLayout(heading)
        self.log = OutputLog()
        layout.addWidget(self.log)

    def add_message(self, message: str, path: str | Path | None = None) -> None:
        self.log.add_message(message, path)

    def clear(self) -> None:
        self.log.clear_log()

    def clear_log(self) -> None:
        self.clear()


class OutputDirectoryControls(QWidget):
    """Shared output-directory row used by every directory-based workspace."""

    directory_changed = pyqtSignal(str)

    def __init__(self, directory: str | Path, parent=None):
        super().__init__(parent)
        self.directory = Path(directory)
        self.path_label = QLabel()
        self.path_label.setObjectName("outputPath")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setToolTip(str(self.directory))
        self.choose_button = QPushButton("选择输出目录")
        self.open_button = QPushButton("打开输出目录")
        self.choose_button.clicked.connect(self.choose)
        self.open_button.clicked.connect(self.open)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(QLabel("输出目录"))
        layout.addWidget(self.path_label, 1)
        layout.addWidget(self.choose_button)
        layout.addWidget(self.open_button)
        self.set_directory(self.directory)

    def set_directory(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.path_label.setText(str(self.directory))
        self.path_label.setToolTip(str(self.directory))

    def choose(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择输出目录", str(self.directory))
        if selected:
            self.set_directory(selected)
            self.directory_changed.emit(str(self.directory))

    def open(self) -> None:
        if not self.directory.exists():
            QMessageBox.warning(self, "目录不存在", "输出目录不存在：\n" + str(self.directory))
            return
        open_folder(self.directory)


class OutputFileControls(QWidget):
    """Shared output-file row for operations producing one named file."""

    file_changed = pyqtSignal(str)

    def __init__(self, file_path: str | Path, parent=None):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.path_label = QLabel()
        self.path_label.setObjectName("outputPath")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.choose_button = QPushButton("选择输出文件")
        self.open_button = QPushButton("打开输出目录")
        self.choose_button.clicked.connect(self.choose)
        self.open_button.clicked.connect(self.open)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(QLabel("输出文件"))
        layout.addWidget(self.path_label, 1)
        layout.addWidget(self.choose_button)
        layout.addWidget(self.open_button)
        self.set_file(self.file_path)

    def set_file(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.path_label.setText(str(self.file_path))
        self.path_label.setToolTip(str(self.file_path))

    def choose(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(self, "选择输出文件", str(self.file_path), "PDF 文件 (*.pdf)")
        if selected:
            if not selected.lower().endswith(".pdf"):
                selected += ".pdf"
            self.set_file(selected)
            self.file_changed.emit(str(self.file_path))

    def open(self) -> None:
        folder = self.file_path.parent
        if not folder.exists():
            QMessageBox.warning(self, "目录不存在", "输出目录不存在：\n" + str(folder))
            return
        open_folder(folder)


def open_folder(path: str | Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path))))
