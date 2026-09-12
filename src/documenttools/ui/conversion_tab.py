from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QThreadPool, QUrl, Qt
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QProgressBar, QTableWidgetItem, QVBoxLayout, QWidget

from ..conversions import convert_file_to_pdf, image_to_pdf
from ..paths import classify_file, unique_path
from .tasking import Task
from .widgets import FileTable, OutputDirectoryControls, OutputLog, button_row

class ConversionTab(QWidget):
    """Convert only Word/PPT/Excel/image inputs to PDF."""

    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.table = FileTable(["源文件", "导出文件名（不含扩展名）", "状态"])
        self.table.setDragEnabled(False)
        self.table.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.table.paths_dropped.connect(self.add_paths)
        self.table.order_changed.connect(self._refresh_image_merge)
        self.group_images = QCheckBox("将所选图片合并为一个 PDF")
        self.group_images.setChecked(False)
        self.group_images.setVisible(False)
        self.output_dir = Path.home() / "Documents"
        self.output_controls = OutputDirectoryControls(self.output_dir)
        self.output_controls.directory_changed.connect(self._output_changed)
        self.progress = QProgressBar()
        self.log = OutputLog()
        self.start_button = QPushButton("转为 PDF")
        self.start_button.clicked.connect(self.start)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("转为 PDF")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "支持 Word、PowerPoint、Excel 和图片转 PDF。PDF 转 Word/PPT 请到“从 PDF 转换”。"
        ))
        layout.addWidget(self.table)
        controls = button_row(self.table, self.choose_files)
        up = QPushButton("上移")
        up.clicked.connect(lambda: self.move_selected(-1))
        down = QPushButton("下移")
        down.clicked.connect(lambda: self.move_selected(1))
        controls.addWidget(up)
        controls.addWidget(down)
        layout.addLayout(controls)
        layout.addWidget(self.group_images)
        layout.addWidget(self.output_controls)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.start_button)
        layout.addLayout(actions)
        layout.addWidget(self.progress)
        layout.addWidget(QLabel("处理日志（双击输出记录可打开文件）"))
        layout.addWidget(self.log)

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要转为 PDF 的文件",
            filter=("Word/PPT/Excel/图片 (*.doc *.docx *.ppt *.pptx *.xls *.xlsx "
                    "*.jpg *.jpeg *.png *.bmp *.tif *.tiff)"),
        )
        self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        existing = {
            self.table.item(row, 0).data(Qt.UserRole)
            for row in range(self.table.rowCount())
        }
        for raw in paths:
            path = Path(raw)
            if classify_file(path) not in {"office", "image"} or str(path) in existing:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            source = QTableWidgetItem(path.name)
            source.setData(Qt.UserRole, str(path))
            self.table.setItem(row, 0, source)
            self.table.setItem(row, 1, QTableWidgetItem(path.stem))
            self.table.setItem(row, 2, QTableWidgetItem("待处理"))
            existing.add(str(path))
        self._refresh_image_merge()

    def _refresh_image_merge(self) -> None:
        image_count = sum(
            classify_file(Path(self.table.item(row, 0).data(Qt.UserRole))) == "image"
            for row in range(self.table.rowCount())
        )
        visible = image_count >= 2
        self.group_images.setVisible(visible)
        self.group_images.setEnabled(visible)
        if not visible:
            self.group_images.setChecked(False)

    def _output_changed(self, value: str) -> None:
        self.output_dir = Path(value)

    def move_selected(self, delta: int) -> None:
        row = self.table.currentRow()
        target = row + delta
        if row >= 0 and 0 <= target < self.table.rowCount():
            self.table.move_rows([row], target if delta < 0 else target + 1)

    def open_output(self) -> None:
        if self.output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_dir)))
        else:
            QMessageBox.warning(self, "目录不存在", "输出目录不存在：\n" + str(self.output_dir))

    def start(self) -> None:
        rows = [
            (
                row,
                Path(self.table.item(row, 0).data(Qt.UserRole)),
                self.table.item(row, 1).text().strip() or Path(self.table.item(row, 0).text()).stem,
            )
            for row in range(self.table.rowCount())
        ]
        if not rows:
            QMessageBox.warning(self, "无法开始", "请先添加 Word、PPT、Excel 或图片文件。")
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        images = [(row, path, stem) for row, path, stem in rows if classify_file(path) == "image"]
        actions: list[tuple[list[int], str, Callable[[], object]]] = []
        if self.group_images.isChecked() and len(images) >= 2:
            image_rows = [row for row, _, _ in images]
            actions.append((
                image_rows,
                "图片合集",
                lambda images=[path for _, path, _ in images]: (
                    image_to_pdf(images, unique_path(self.output_dir, "图片合集", ".pdf")),
                    "Pillow",
                ),
            ))
        for row, path, stem in rows:
            if self.group_images.isChecked() and len(images) >= 2 and classify_file(path) == "image":
                continue
            actions.append(([row], path.name, lambda path=path, stem=stem: convert_file_to_pdf(path, self.output_dir, stem)))
        self.log.clear_log()
        self.start_button.setEnabled(False)
        self.progress.setRange(0, len(actions))
        self.progress.setValue(0)
        self._run_actions(actions)

    def _run_actions(self, actions: list[tuple[list[int], str, Callable[[], object]]]) -> None:
        def run_next(index: int) -> None:
            if index >= len(actions):
                self.start_button.setEnabled(True)
                return
            rows, label, action = actions[index]
            for row in rows:
                self.table.item(row, 2).setText("处理中")
            task = Task(action)
            task.signals.completed.connect(lambda result, index=index, rows=rows, label=label: done(index, rows, label, result))
            task.signals.failed.connect(lambda error, index=index, rows=rows, label=label: failed(index, rows, label, error))
            self.pool.start(task)

        def done(index: int, rows: list[int], label: str, result: object) -> None:
            output = result[0] if isinstance(result, tuple) else result
            for row in rows:
                self.table.item(row, 2).setText("完成")
            self.log.add_message(f"完成：{label} -> {output}", output)
            self.progress.setValue(index + 1)
            run_next(index + 1)

        def failed(index: int, rows: list[int], label: str, error: str) -> None:
            for row in rows:
                self.table.item(row, 2).setText("失败")
            self.log.add_message(f"失败：{label}：{error}")
            self.progress.setValue(index + 1)
            run_next(index + 1)

        run_next(0)
