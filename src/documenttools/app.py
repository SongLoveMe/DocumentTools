from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QUrl, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QIcon, QPalette
from PyQt5.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QPlainTextEdit, QProgressBar, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .conversions import convert_file_to_pdf, convert_pdf_to_ppt, convert_pdf_to_word, image_to_pdf
from .engines import EmbeddedOfficeEngine
from .paths import classify_file, unique_path
from .pdf_tools import TITLE_TEMPLATES, MergeItem, PageSizeConfig, format_directory_title, merge_pdfs


class WorkerSignals(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)


class Task(QRunnable):
    def __init__(self, action: Callable[[], object]):
        super().__init__()
        self.action = action
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.completed.emit(self.action())
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class FileTable(QTableWidget):
    paths_dropped = pyqtSignal(list)
    order_changing = pyqtSignal()
    order_changed = pyqtSignal()

    def __init__(self, columns: list[str], parent: QWidget | None = None):
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
        self.setMinimumHeight(190)

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
        else:
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
            self.insertRow(target + offset)
            for column, item in enumerate(row_items):
                self.setItem(target + offset, column, item)
        self.clearSelection()
        for offset in range(len(values)):
            self.selectRow(target + offset)
        self.setCurrentCell(target, 0)
        self.order_changed.emit()


def _button_row(table: FileTable, parent: QWidget, chooser: Callable[[], None]) -> QHBoxLayout:
    row = QHBoxLayout()
    add = QPushButton("添加文件")
    add.clicked.connect(chooser)
    remove = QPushButton("移除选中")
    remove.clicked.connect(table.remove_selected)
    clear = QPushButton("清空列表")
    clear.clicked.connect(lambda: table.setRowCount(0))
    row.addWidget(add); row.addWidget(remove); row.addWidget(clear); row.addStretch()
    return row


class ConversionTab(QWidget):
    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.table = FileTable(["源文件", "导出文件名（不含扩展名）", "状态"])
        self.table.paths_dropped.connect(self.add_paths)
        self.mode = QComboBox()
        self.mode.addItem("Word / WPS / PPT / Excel / 图片 -> PDF", "to_pdf")
        self.mode.addItem("PDF -> Word (.docx)", "to_word")
        self.mode.addItem("PDF -> PPT (.pptx)", "to_ppt")
        self.group_images = QCheckBox("多张图片合并为一个 PDF")
        self.group_images.setChecked(True)
        self.output_path = str(Path.home() / "Documents")
        self.output_label = QLabel(self.output_path)
        self.progress = QProgressBar(); self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        self.start_button = QPushButton("开始处理"); self.open_button = QPushButton("打开输出目录")
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.start_button.clicked.connect(self.start); self.open_button.clicked.connect(self.open_output)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        heading = QLabel("转换"); heading.setObjectName("sectionTitle"); layout.addWidget(heading)
        mode_row = QHBoxLayout(); mode_row.addWidget(QLabel("转换类型")); mode_row.addWidget(self.mode); mode_row.addWidget(self.group_images); mode_row.addStretch(); layout.addLayout(mode_row)
        layout.addWidget(QLabel("可拖放文件；每行可填写自定义导出文件名。WPS 专有格式不在 v1 支持范围内。"))
        layout.addWidget(self.table)
        file_buttons = _button_row(self.table, self, self.choose_files)
        up = QPushButton("上移"); up.clicked.connect(lambda: self.move_selected(-1))
        down = QPushButton("下移"); down.clicked.connect(lambda: self.move_selected(1))
        file_buttons.addWidget(up); file_buttons.addWidget(down)
        layout.addLayout(file_buttons)
        output_row = QHBoxLayout(); output_row.addWidget(QLabel("输出目录")); self.output_label.setFrameStyle(0x0012); output_row.addWidget(self.output_label, 1)
        browse = QPushButton("选择"); browse.clicked.connect(self.choose_output); output_row.addWidget(browse); layout.addLayout(output_row)
        actions = QHBoxLayout(); actions.addWidget(self.start_button); actions.addWidget(self.open_button); actions.addStretch(); layout.addLayout(actions)
        layout.addWidget(self.progress); layout.addWidget(self.log)

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        existing = {self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount())}
        for raw in paths:
            path = Path(raw)
            if not path.is_file() or str(path) in existing:
                continue
            row = self.table.rowCount(); self.table.insertRow(row)
            source = QTableWidgetItem(path.name); source.setData(Qt.UserRole, str(path)); self.table.setItem(row, 0, source)
            self.table.setItem(row, 1, QTableWidgetItem(path.stem)); self.table.setItem(row, 2, QTableWidgetItem("待处理")); existing.add(str(path))

    def choose_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_path)
        if selected: self.output_path = selected; self.output_label.setText(selected)

    def move_selected(self, delta: int) -> None:
        row = self.table.currentRow(); target = row + delta
        if row < 0 or target < 0 or target >= self.table.rowCount(): return
        self.table.move_rows([row], target if delta < 0 else target + 1)

    def _mode_changed(self) -> None:
        mode = self.mode.currentData()
        self.group_images.setVisible(mode == "to_pdf")

    def open_output(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_path))

    def start(self) -> None:
        rows = [(row, Path(self.table.item(row, 0).data(Qt.UserRole)), (self.table.item(row, 1).text().strip() or Path(self.table.item(row, 0).text()).stem)) for row in range(self.table.rowCount())]
        if not rows: QMessageBox.warning(self, "无法开始", "请先添加文件。"); return
        self.log.clear(); actions: list[tuple[int, Callable[[], object]]] = []; mode = self.mode.currentData(); output_dir = Path(self.output_path); output_dir.mkdir(parents=True, exist_ok=True)
        if mode == "to_pdf" and self.group_images.isChecked():
            images = [(row, path, stem) for row, path, stem in rows if classify_file(path) == "image"]
            if len(images) > 1:
                stem = rows[0][2] if len(rows) == len(images) else "图片合集"
                actions.append((-1, lambda images=[item[1] for item in images], stem=stem: (image_to_pdf(images, unique_path(output_dir, stem, ".pdf")), "Pillow")))
                rows = [(row, path, stem) for row, path, stem in rows if classify_file(path) != "image"]
        for row, path, stem in rows:
            if mode == "to_pdf": action = lambda path=path, stem=stem: convert_file_to_pdf(path, output_dir, stem)
            elif mode == "to_word": action = lambda path=path, stem=stem: convert_pdf_to_word(path, output_dir, stem)
            else: action = lambda path=path, stem=stem: convert_pdf_to_ppt(path, output_dir, stem)
            actions.append((row, action))
        self._run_actions(actions)

    def _run_actions(self, actions: list[tuple[int, Callable[[], object]]]) -> None:
        self.start_button.setEnabled(False); self.progress.setRange(0, len(actions)); self.progress.setValue(0); done = {"n": 0}
        def finish(index: int, result: object) -> None:
            done["n"] += 1; self.progress.setValue(done["n"]); label = "图片合集" if index < 0 else self.table.item(index, 0).text() if index < self.table.rowCount() else "任务"
            self.log.appendPlainText(f"完成：{label} -> {result}");
            if index >= 0 and index < self.table.rowCount(): self.table.item(index, 2).setText("完成")
            if done["n"] == len(actions): self.start_button.setEnabled(True)
        def fail(index: int, error: str) -> None:
            done["n"] += 1; self.progress.setValue(done["n"]); label = "图片合集" if index < 0 else self.table.item(index, 0).text(); self.log.appendPlainText(f"失败：{label}：{error}")
            if index >= 0 and index < self.table.rowCount(): self.table.item(index, 2).setText("失败")
            if done["n"] == len(actions): self.start_button.setEnabled(True)
        for index, action in actions:
            task = Task(action); task.signals.completed.connect(lambda result, index=index: finish(index, result)); task.signals.failed.connect(lambda error, index=index: fail(index, error)); self.pool.start(task)


class MergeTab(QWidget):
    def __init__(self, pool: QThreadPool):
        super().__init__(); self.pool = pool; self.table = FileTable(["源文件", "目录名称（可编辑）", "页数", "状态"]); self.table.paths_dropped.connect(self.add_paths)
        self.cover: str | None = None; self.output_path = str(Path.home() / "Documents" / "merged.pdf"); self.output_label = QLabel(self.output_path); self.include_toc = QCheckBox("生成目录页"); self.include_toc.setChecked(True); self.title_template = QComboBox(); [self.title_template.addItem(label, value) for label, value in TITLE_TEMPLATES.items()]; self.title_template.currentIndexChanged.connect(self.apply_title_template); self._updating_titles = False; self.table.order_changing.connect(self._begin_reorder); self.table.order_changed.connect(self.apply_title_template); self.table.itemChanged.connect(self._title_edited)
        self.preset = QComboBox(); self.preset.addItems(["A4", "A3", "A5", "B5", "Letter", "自定义"]); self.orientation = QComboBox(); self.orientation.addItems(["竖版", "横版"]); self.keep_original = QCheckBox("保持原始页面规格（不统一）")
        self.custom_width = QDoubleSpinBox(); self.custom_width.setRange(72, 2880); self.custom_width.setValue(595.28); self.custom_width.setSuffix(" pt")
        self.custom_height = QDoubleSpinBox(); self.custom_height.setRange(72, 2880); self.custom_height.setValue(841.89); self.custom_height.setSuffix(" pt")
        self.cover_label = QLabel("未设置封面"); self.progress = QProgressBar(); self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.start_button = QPushButton("合并 PDF"); self.open_button = QPushButton("打开输出目录")
        self.start_button.clicked.connect(self.start); self.open_button.clicked.connect(self.open_output); self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self); heading = QLabel("PDF 合并"); heading.setObjectName("sectionTitle"); layout.addWidget(heading); layout.addWidget(QLabel("列表顺序就是合并顺序；可关闭自动目录页，源书签仍会保留。")); layout.addWidget(self.table)
        controls = QHBoxLayout(); add = QPushButton("添加 PDF"); add.clicked.connect(self.choose_files); remove = QPushButton("移除"); remove.clicked.connect(self.table.remove_selected); clear = QPushButton("清空列表"); clear.clicked.connect(lambda: self.table.setRowCount(0)); up = QPushButton("上移"); up.clicked.connect(lambda: self.move_selected(-1)); down = QPushButton("下移"); down.clicked.connect(lambda: self.move_selected(1)); cover = QPushButton("设置封面"); cover.clicked.connect(self.choose_cover); [controls.addWidget(button) for button in (add, remove, clear, up, down, cover)]; controls.addStretch(); layout.addLayout(controls)
        settings = QGridLayout(); settings.addWidget(QLabel("目录标题模板"), 0, 0); settings.addWidget(self.title_template, 0, 1, 1, 2); settings.addWidget(self.include_toc, 0, 3, 1, 2); settings.addWidget(QLabel("页面规格"), 1, 0); settings.addWidget(self.preset, 1, 1); settings.addWidget(self.orientation, 1, 2); settings.addWidget(self.keep_original, 1, 3, 1, 2); settings.addWidget(QLabel("自定义宽 / 高"), 2, 0); settings.addWidget(self.custom_width, 2, 1); settings.addWidget(self.custom_height, 2, 2); settings.addWidget(QLabel("仅“自定义”规格生效"), 2, 3, 1, 2); settings.addWidget(QLabel("封面"), 3, 0); settings.addWidget(self.cover_label, 3, 1, 1, 4); layout.addLayout(settings)
        output = QHBoxLayout(); output.addWidget(QLabel("输出文件")); output.addWidget(self.output_label, 1); browse = QPushButton("选择"); browse.clicked.connect(self.choose_output); output.addWidget(browse); layout.addLayout(output)
        actions = QHBoxLayout(); actions.addWidget(self.start_button); actions.addWidget(self.open_button); actions.addStretch(); layout.addLayout(actions); layout.addWidget(self.progress); layout.addWidget(self.log)

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 PDF", filter="PDF 文件 (*.pdf)"); self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        existing = {self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount())}
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() != ".pdf" or not path.is_file() or str(path) in existing: continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            source = QTableWidgetItem(path.name); source.setData(Qt.UserRole, str(path)); self.table.setItem(row, 0, source)
            title = QTableWidgetItem(format_directory_title(row + 1, path.name, self.title_template.currentData()))
            self._updating_titles = True
            self.table.setItem(row, 1, title); title.setData(Qt.UserRole + 1, True)
            self._updating_titles = False
            self.table.setItem(row, 2, QTableWidgetItem("未知")); self.table.setItem(row, 3, QTableWidgetItem("待处理")); existing.add(str(path))

    def apply_title_template(self) -> None:
        self._updating_titles = True
        try:
            for row in range(self.table.rowCount()):
                title = self.table.item(row, 1)
                source = self.table.item(row, 0)
                if title and source and title.data(Qt.UserRole + 1):
                    title.setText(format_directory_title(row + 1, source.text(), self.title_template.currentData()))
        finally:
            self._updating_titles = False

    def _title_edited(self, item: QTableWidgetItem) -> None:
        if item.column() == 1 and not self._updating_titles:
            item.setData(Qt.UserRole + 1, False)

    def _begin_reorder(self) -> None:
        self._updating_titles = True

    def move_selected(self, delta: int) -> None:
        row = self.table.currentRow(); target = row + delta
        if row < 0 or target < 0 or target >= self.table.rowCount(): return
        self.table.move_rows([row], target if delta < 0 else target + 1)

    def choose_cover(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "选择封面", filter="PDF 或图片 (*.pdf *.jpg *.jpeg *.png)")
        if selected: self.cover = selected; self.cover_label.setText(selected)

    def choose_output(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(self, "选择合并输出文件", self.output_path, "PDF 文件 (*.pdf)")
        if selected: self.output_path = selected if selected.lower().endswith(".pdf") else selected + ".pdf"; self.output_label.setText(self.output_path)

    def open_output(self) -> None: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.output_path).parent)))

    def start(self) -> None:
        if self.table.rowCount() < 1: QMessageBox.warning(self, "无法开始", "请至少添加一个 PDF。"); return
        items = [MergeItem(Path(self.table.item(row, 0).data(Qt.UserRole)), self.table.item(row, 1).text().strip() or Path(self.table.item(row, 0).text()).stem) for row in range(self.table.rowCount())]
        target = unique_path(Path(self.output_path).parent, Path(self.output_path).stem, ".pdf"); custom = self.preset.currentText() == "自定义"; config = PageSizeConfig(preset=self.preset.currentText(), orientation="landscape" if self.orientation.currentIndex() else "portrait", width=self.custom_width.value() if custom else None, height=self.custom_height.value() if custom else None, preserve_original=self.keep_original.isChecked())
        self.start_button.setEnabled(False); self.progress.setRange(0, 1); self.progress.setValue(0); task = Task(lambda: merge_pdfs(items, target, cover=self.cover, page_size=config, include_toc=self.include_toc.isChecked())); task.signals.completed.connect(lambda entries: self.done(target, entries, items)); task.signals.failed.connect(self.fail); self.pool.start(task)

    def done(self, target: Path, entries: object, items: list[MergeItem]) -> None:
        self.progress.setValue(1); self.start_button.setEnabled(True); self.output_path = str(target); self.output_label.setText(str(target)); self.log.appendPlainText(f"完成：{target}\n目录条目：{len(entries)}")
        for row, item in enumerate(items): self.table.item(row, 2).setText(str(item.page_count)); self.table.item(row, 3).setText("完成")
    def fail(self, error: str) -> None: self.start_button.setEnabled(True); self.log.appendPlainText(f"失败：{error}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("DocumentTools"); self.resize(980, 720); icon = Path(__file__).parents[2] / "assets" / "documenttools.ico"
        if icon.is_file(): self.setWindowIcon(QIcon(str(icon)))
        self.pool = QThreadPool.globalInstance(); self.pool.setMaxThreadCount(2); tabs = QTabWidget(); tabs.addTab(ConversionTab(self.pool), "转换"); tabs.addTab(MergeTab(self.pool), "PDF 合并"); self.setCentralWidget(tabs); self.statusBar().showMessage(self._engine_message())

    @staticmethod
    def _engine_message() -> str:
        status = EmbeddedOfficeEngine.status(); return f"内置转换运行时：{'可用' if status.available else '未随当前开发目录提供'}"


def _apply_palette(app: QApplication) -> None:
    palette = QPalette(); palette.setColor(QPalette.Window, QColor("#f5f7fa")); palette.setColor(QPalette.Base, QColor("#ffffff")); palette.setColor(QPalette.Text, QColor("#17202a")); palette.setColor(QPalette.WindowText, QColor("#17202a")); palette.setColor(QPalette.Highlight, QColor("#2463eb")); palette.setColor(QPalette.HighlightedText, QColor("#ffffff")); app.setPalette(palette)
    app.setStyleSheet("QMainWindow{background:#f5f7fa} QTabWidget::pane{border:1px solid #d9e0e8;background:#fff} QTabBar::tab{padding:10px 22px;color:#52606d} QTabBar::tab:selected{color:#1f5fd1;border-bottom:2px solid #2463eb} QPushButton{min-height:32px;padding:0 14px;border:1px solid #cbd5e1;border-radius:4px;background:#fff} QPushButton:hover{border-color:#2463eb;color:#1f5fd1} QComboBox,QTableWidget,QPlainTextEdit{border:1px solid #cbd5e1;border-radius:4px;background:#fff} QProgressBar{min-height:10px;border:1px solid #d9e0e8;border-radius:4px;background:#eef2f7;text-align:center} QProgressBar::chunk{background:#2463eb} QLabel#sectionTitle{font-size:20px;font-weight:600;color:#17202a;padding:4px 0}")


def run() -> int:
    app = QApplication(sys.argv); app.setApplicationName("DocumentTools"); _apply_palette(app); window = MainWindow(); window.show(); return app.exec_()
