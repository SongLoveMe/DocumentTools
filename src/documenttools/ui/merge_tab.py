from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThreadPool, QUrl, Qt
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QTableWidgetItem, QVBoxLayout, QWidget

from ..paths import unique_path
from ..pdf_tools import TITLE_TEMPLATES, MergeItem, PageSizeConfig, format_directory_title, merge_pdfs
from .tasking import Task
from .widgets import FileTable, OutputFileControls, OutputLog

class MergeTab(QWidget):
    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.table = FileTable(["源文件", "目录名称（可编辑）", "页数", "状态"])
        self.table.paths_dropped.connect(self.add_paths)
        self.table.order_changing.connect(self._begin_reorder)
        self.table.order_changed.connect(self.apply_title_template)
        self.cover: str | None = None
        self.output_path = str(Path.home() / "Documents" / "merged.pdf")
        self.output_controls = OutputFileControls(self.output_path)
        self.output_controls.file_changed.connect(self._output_changed)
        self.include_toc = QCheckBox("生成目录页")
        self.include_toc.setChecked(True)
        self.title_template = QComboBox()
        for label, value in TITLE_TEMPLATES.items():
            self.title_template.addItem(label, value)
        self.title_template.currentIndexChanged.connect(self.apply_title_template)
        self._updating_titles = False
        self._auto_title_paths: set[str] = set()
        self.table.itemChanged.connect(self._title_edited)
        self.preset = QComboBox()
        self.preset.addItems(["A4", "A3", "A5", "B5", "Letter", "自定义"])
        self.orientation = QComboBox()
        self.orientation.addItems(["竖版", "横版"])
        self.keep_original = QCheckBox("保持原始页面规格（不统一）")
        self.custom_width = QDoubleSpinBox()
        self.custom_width.setRange(72, 2880)
        self.custom_width.setValue(595.28)
        self.custom_width.setSuffix(" pt")
        self.custom_height = QDoubleSpinBox()
        self.custom_height.setRange(72, 2880)
        self.custom_height.setValue(841.89)
        self.custom_height.setSuffix(" pt")
        self.cover_label = QLabel("未设置封面")
        self.progress = QProgressBar()
        self.log = OutputLog()
        self.start_button = QPushButton("合并 PDF")
        self.start_button.clicked.connect(self.start)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("合并 PDF")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("列表顺序就是合并顺序；可关闭自动目录页，源书签仍会保留。"))
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        add = QPushButton("添加 PDF")
        add.clicked.connect(self.choose_files)
        remove = QPushButton("移除")
        remove.clicked.connect(self.table.remove_selected)
        clear = QPushButton("清空列表")
        clear.clicked.connect(lambda: self.table.setRowCount(0))
        up = QPushButton("上移")
        up.clicked.connect(lambda: self.move_selected(-1))
        down = QPushButton("下移")
        down.clicked.connect(lambda: self.move_selected(1))
        cover = QPushButton("设置封面")
        cover.clicked.connect(self.choose_cover)
        for button in (add, remove, clear, up, down, cover):
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        settings = QGridLayout()
        settings.addWidget(QLabel("目录标题模板"), 0, 0)
        settings.addWidget(self.title_template, 0, 1, 1, 2)
        settings.addWidget(self.include_toc, 0, 3, 1, 2)
        settings.addWidget(QLabel("页面规格"), 1, 0)
        settings.addWidget(self.preset, 1, 1)
        settings.addWidget(self.orientation, 1, 2)
        settings.addWidget(self.keep_original, 1, 3, 1, 2)
        settings.addWidget(QLabel("自定义宽 / 高"), 2, 0)
        settings.addWidget(self.custom_width, 2, 1)
        settings.addWidget(self.custom_height, 2, 2)
        settings.addWidget(QLabel("仅“自定义”规格生效"), 2, 3, 1, 2)
        settings.addWidget(QLabel("封面"), 3, 0)
        settings.addWidget(self.cover_label, 3, 1, 1, 4)
        layout.addLayout(settings)
        layout.addWidget(self.output_controls)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.start_button)
        layout.addLayout(actions)
        layout.addWidget(QLabel("处理日志（双击输出记录可打开文件）"))
        layout.addWidget(self.progress)
        layout.addWidget(self.log)

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要合并的 PDF", filter="PDF 文件 (*.pdf)")
        self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        existing = {self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount())}
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() != ".pdf" or not path.is_file() or str(path) in existing:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            source = QTableWidgetItem(path.name)
            source.setData(Qt.UserRole, str(path))
            self.table.setItem(row, 0, source)
            title = QTableWidgetItem(format_directory_title(row + 1, path.name, self.title_template.currentData()))
            title.setData(Qt.UserRole + 1, True)
            self.table.setItem(row, 1, title)
            self._auto_title_paths.add(str(path))
            self.table.setItem(row, 2, QTableWidgetItem("未知"))
            self.table.setItem(row, 3, QTableWidgetItem("待处理"))
            existing.add(str(path))

    def apply_title_template(self) -> None:
        self._updating_titles = True
        try:
            for row in range(self.table.rowCount()):
                title = self.table.item(row, 1)
                source = self.table.item(row, 0)
                if title and source and source.data(Qt.UserRole) in self._auto_title_paths:
                    title.setText(format_directory_title(row + 1, source.text(), self.title_template.currentData()))
        finally:
            self._updating_titles = False

    def _title_edited(self, item: QTableWidgetItem) -> None:
        if item.column() == 1 and not self._updating_titles:
            row = item.row()
            source = self.table.item(row, 0)
            if source:
                self._auto_title_paths.discard(str(source.data(Qt.UserRole)))
            item.setData(Qt.UserRole + 1, False)

    def _begin_reorder(self) -> None:
        self._updating_titles = True

    def move_selected(self, delta: int) -> None:
        row = self.table.currentRow()
        target = row + delta
        if row >= 0 and 0 <= target < self.table.rowCount():
            self.table.move_rows([row], target if delta < 0 else target + 1)

    def choose_cover(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "选择封面", filter="PDF 或图片 (*.pdf *.jpg *.jpeg *.png)")
        if selected:
            self.cover = selected
            self.cover_label.setText(selected)

    def _output_changed(self, value: str) -> None:
        self.output_path = value

    def start(self) -> None:
        if self.table.rowCount() < 1:
            QMessageBox.warning(self, "无法开始", "请至少添加一个 PDF。")
            return
        items = [
            MergeItem(
                Path(self.table.item(row, 0).data(Qt.UserRole)),
                self.table.item(row, 1).text().strip() or Path(self.table.item(row, 0).text()).stem,
            )
            for row in range(self.table.rowCount())
        ]
        target = unique_path(Path(self.output_path).parent, Path(self.output_path).stem, ".pdf")
        custom = self.preset.currentText() == "自定义"
        config = PageSizeConfig(
            preset=self.preset.currentText(),
            orientation="landscape" if self.orientation.currentIndex() else "portrait",
            width=self.custom_width.value() if custom else None,
            height=self.custom_height.value() if custom else None,
            preserve_original=self.keep_original.isChecked(),
        )
        self.start_button.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        task = Task(lambda: merge_pdfs(items, target, cover=self.cover, page_size=config, include_toc=self.include_toc.isChecked()))
        task.signals.completed.connect(lambda entries: self.done(target, entries, items))
        task.signals.failed.connect(self.fail)
        self.pool.start(task)

    def done(self, target: Path, entries: object, items: list[MergeItem]) -> None:
        self.progress.setValue(1)
        self.start_button.setEnabled(True)
        self.output_path = str(target)
        self.output_controls.set_file(target)
        self.log.add_message(f"完成：{target}（目录条目：{len(entries)}）", target)
        for row, item in enumerate(items):
            self.table.item(row, 2).setText(str(item.page_count))
            self.table.item(row, 3).setText("完成")

    def fail(self, error: str) -> None:
        self.start_button.setEnabled(True)
        self.log.add_message(f"失败：{error}")
