from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QUrl, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from ..conversions import convert_pdf_to_excel, convert_pdf_to_images, convert_pdf_to_ppt, convert_pdf_to_word
from .tasking import Task
from .widgets import LogSection, OutputDirectoryControls, open_folder
from ..paths import unique_path
from ..pdf_tools import (
    PAGE_NUMBER_FORMATS, PAGE_NUMBER_POSITIONS, PageNumberConfig, CompressionPreset,
    add_pdf_page_numbers, compress_pdf, delete_pdf_pages, estimate_pdf_compression,
    extract_pdf_pages, reorder_pdf_pages, rotate_pdf_pages, split_pdf,
)








def _unique_folder(parent: Path, stem: str) -> Path:
    candidate = parent / stem
    number = 1
    while candidate.exists():
        candidate = parent / f"{stem} ({number})"
        number += 1
    return candidate


class PdfSourcePanel(QWidget):
    """PDF picker with thumbnails; drag sorting is enabled only for reorder."""

    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.source: Path | None = None
        self.page_count = 0
        self._reorder_enabled = False
        self.source_label = QLabel("尚未选择 PDF")
        self.info_label = QLabel("选择 PDF 后将在后台显示缩略图。")
        self.pages = QListWidget()
        self.pages.setObjectName("pageThumbnails")
        self.pages.setViewMode(QListWidget.IconMode)
        self.pages.setResizeMode(QListWidget.Adjust)
        self.pages.setWrapping(True)
        self.pages.setSpacing(8)
        self.pages.setIconSize(QSize(108, 144))
        self.pages.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pages.setDefaultDropAction(Qt.MoveAction)
        self.pages.setDragDropOverwriteMode(False)
        self.pages.setMinimumHeight(250)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        choose = QPushButton("选择 PDF")
        choose.clicked.connect(self.choose)
        top.addWidget(choose)
        top.addWidget(self.source_label, 1)
        layout.addLayout(top)
        layout.addWidget(self.info_label)
        layout.addWidget(self.pages)
        self.set_reorder_enabled(False)

    def set_reorder_enabled(self, enabled: bool) -> None:
        self._reorder_enabled = enabled
        self.pages.setDragEnabled(enabled)
        self.pages.setDragDropMode(QAbstractItemView.InternalMove if enabled else QAbstractItemView.NoDragDrop)
        for row in range(self.pages.count()):
            item = self.pages.item(row)
            flags = item.flags() | Qt.ItemIsUserCheckable
            if enabled:
                flags |= Qt.ItemIsDragEnabled
            else:
                flags &= ~Qt.ItemIsDragEnabled
            item.setFlags(flags)
        if self.page_count:
            self.info_label.setText(
                "重排序模式：仅此操作允许拖拽缩略图调整顺序。" if enabled
                else "可勾选页面；当前操作不支持拖拽排序。"
            )

    def choose(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        value, _ = QFileDialog.getOpenFileName(self, "选择 PDF", filter="PDF 文件 (*.pdf)")
        if value:
            self.load(Path(value))

    def load(self, source: Path) -> None:
        self.source = source
        self.source_label.setText(str(source))
        self.info_label.setText("正在后台读取页面和生成缩略图…")
        self.pages.clear()

        def render() -> tuple[int, list[tuple[int, bytes]]]:
            import fitz
            document = fitz.open(source)
            try:
                if document.needs_pass and not document.authenticate(""):
                    raise RuntimeError(f"{source.name} 需要打开密码，无法猜测密码。")
                thumbnails = [
                    (number, page.get_pixmap(matrix=fitz.Matrix(.20, .20), alpha=False).tobytes("png"))
                    for number, page in enumerate(document, 1)
                ]
                if not thumbnails:
                    raise RuntimeError(f"{source.name} 没有页面。")
                return len(thumbnails), thumbnails
            finally:
                document.close()

        task = Task(render)
        task.signals.completed.connect(self._loaded)
        task.signals.failed.connect(self._failed)
        self.pool.start(task)

    def _loaded(self, result: object) -> None:
        count, thumbnails = result
        self.page_count = count
        self.pages.clear()
        for number, image in thumbnails:
            pixmap = QPixmap()
            pixmap.loadFromData(image, "PNG")
            item = QListWidgetItem(QIcon(pixmap), f"第 {number} 页")
            item.setData(Qt.UserRole, number)
            item.setCheckState(Qt.Unchecked)
            self.pages.addItem(item)
        self.set_reorder_enabled(self._reorder_enabled)

    def _failed(self, error: str) -> None:
        self.source = None
        self.page_count = 0
        self.pages.clear()
        self.info_label.setText(f"无法加载：{error}")

    def selected_pages(self) -> str:
        return ",".join(
            str(self.pages.item(row).data(Qt.UserRole))
            for row in range(self.pages.count())
            if self.pages.item(row).checkState() == Qt.Checked
        )

    def ordered_pages(self) -> str:
        return ",".join(str(self.pages.item(row).data(Qt.UserRole)) for row in range(self.pages.count()))


class PageOperationPanel(QWidget):
    """Show only the controls belonging to the selected PDF page operation."""

    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.source = PdfSourcePanel(pool)
        self.operation = QComboBox()
        self.operation.addItem("请选择操作", None)
        for label, value in (("拆分 PDF", "split"), ("提取指定页", "extract"), ("删除指定页", "delete"), ("重排序 PDF", "reorder")):
            self.operation.addItem(label, value)
        self.options = QStackedWidget()

        empty = QLabel("选择操作后，这里只显示该操作所需参数。")
        empty.setAlignment(Qt.AlignCenter)
        self.options.addWidget(empty)

        split_box = QWidget()
        split_layout = QVBoxLayout(split_box)
        split_form = QFormLayout()
        self.mode = QComboBox()
        for label, value in (("每页一个文件", "each"), ("每 N 页一个文件", "count"), ("按断点拆分", "breakpoints")):
            self.mode.addItem(label, value)
        split_form.addRow("拆分方式", self.mode)
        split_layout.addLayout(split_form)
        self.split_options = QStackedWidget()
        self.split_options.addWidget(QLabel("每一页生成一个独立 PDF 文件。"))
        count_box = QWidget()
        count_form = QFormLayout(count_box)
        self.count = QSpinBox()
        self.count.setRange(1, 100000)
        self.count.setValue(2)
        count_form.addRow("每份页数", self.count)
        self.split_options.addWidget(count_box)
        breakpoint_box = QWidget()
        breakpoint_form = QFormLayout(breakpoint_box)
        self.breakpoints = QLineEdit()
        self.breakpoints.setPlaceholderText("例如 3,7：在第 3、7 页后切开")
        breakpoint_form.addRow("拆分断点", self.breakpoints)
        self.split_options.addWidget(breakpoint_box)
        split_layout.addWidget(self.split_options)
        self.options.addWidget(split_box)

        page_box = QWidget()
        page_form = QFormLayout(page_box)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("例如 1-3,5")
        self.use_selected = QPushButton("使用勾选页")
        self.use_selected.clicked.connect(lambda: self.range_edit.setText(self.source.selected_pages()))
        page_form.addRow("页面范围", self.range_edit)
        page_form.addRow("快捷选择", self.use_selected)
        self.options.addWidget(page_box)

        delete_box = QWidget()
        delete_form = QFormLayout(delete_box)
        self.delete_range = QLineEdit()
        self.delete_range.setPlaceholderText("例如 2,4-6")
        self.delete_selected = QPushButton("使用勾选页")
        self.delete_selected.clicked.connect(lambda: self.delete_range.setText(self.source.selected_pages()))
        delete_form.addRow("删除范围", self.delete_range)
        delete_form.addRow("快捷选择", self.delete_selected)
        self.options.addWidget(delete_box)

        reorder_box = QWidget()
        reorder_form = QFormLayout(reorder_box)
        self.order_edit = QLineEdit()
        self.order_edit.setPlaceholderText("例如 3,1,2,4-末页")
        self.sync_order = QPushButton("填入当前缩略图顺序")
        self.sync_order.clicked.connect(lambda: self.order_edit.setText(self.source.ordered_pages()))
        reorder_form.addRow("页面顺序", self.order_edit)
        reorder_form.addRow("快捷操作", self.sync_order)
        self.options.addWidget(reorder_box)

        self.output_dir = Path.home() / "Documents"
        self.output_controls = OutputDirectoryControls(self.output_dir)
        self.output_controls.directory_changed.connect(self._output_changed)
        self.run_button = QPushButton("开始处理")
        self.run_button.setObjectName("primaryAction")
        self.log_section = LogSection()
        self.log = self.log_section.log

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("排列 PDF：选择操作后，只显示当前操作需要的参数。"))
        layout.addWidget(self.source)
        operation_row = QHBoxLayout()
        operation_row.addWidget(QLabel("操作"))
        operation_row.addWidget(self.operation, 1)
        layout.addLayout(operation_row)
        layout.addWidget(self.options)
        layout.addWidget(self.output_controls)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.run_button)
        layout.addLayout(actions)
        layout.addWidget(self.log_section)

        self.operation.currentIndexChanged.connect(self.refresh)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.run_button.clicked.connect(self.start)
        self.refresh()

    def refresh(self) -> None:
        operation = self.operation.currentData()
        self.options.setCurrentIndex({None: 0, "split": 1, "extract": 2, "delete": 3, "reorder": 4}[operation])
        self.source.set_reorder_enabled(operation == "reorder")
        if operation == "split":
            self.split_options.setCurrentIndex({"each": 0, "count": 1, "breakpoints": 2}[self.mode.currentData()])
        self.run_button.setEnabled(operation is not None)

    def start(self) -> None:
        operation = self.operation.currentData()
        if operation is None:
            return
        if not self.source.source:
            QMessageBox.warning(self, "无法开始", "请先选择 PDF。")
            return
        source = self.source.source
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if operation == "split":
            split_dir = _unique_folder(self.output_dir, f"{source.stem}_拆分")
            action = lambda: split_pdf(
                source, mode=self.mode.currentData(), pages_per_file=self.count.value(),
                breakpoints=self.breakpoints.text(), output_directory=split_dir,
            )
        else:
            if operation == "reorder":
                pages = self.order_edit.text().strip() or self.source.ordered_pages()
            elif operation == "delete":
                pages = self.delete_range.text().strip() or self.source.selected_pages()
            else:
                pages = self.range_edit.text().strip() or self.source.selected_pages()
            if not pages:
                QMessageBox.warning(self, "无法开始", "请输入页面范围或勾选页面。")
                return
            suffix = {"extract": "提取", "delete": "删除页面", "reorder": "重排序"}[operation]
            target = unique_path(self.output_dir, f"{source.stem}_{suffix}", ".pdf")
            action = {
                "extract": lambda: extract_pdf_pages(source, pages, target),
                "delete": lambda: delete_pdf_pages(source, pages, target),
                "reorder": lambda: reorder_pdf_pages(source, pages, target),
            }[operation]
        self.run_button.setEnabled(False)
        task = Task(action)
        task.signals.completed.connect(self.done)
        task.signals.failed.connect(self.fail)
        self.pool.start(task)

    def _output_changed(self, value: str) -> None:
        self.output_dir = Path(value)


class NumberingPanel(QWidget):
    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.source = PdfSourcePanel(pool)
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("留空为全部页面；也可输入 1-3,5")
        self.position = QComboBox()
        for value, label in PAGE_NUMBER_POSITIONS.items():
            self.position.addItem(label, value)
        self.position.setCurrentIndex(list(PAGE_NUMBER_POSITIONS).index("bottom-center"))
        self.start_number = QSpinBox()
        self.start_number.setRange(0, 999999)
        self.start_number.setValue(1)
        self.format = QComboBox()
        for value, label in PAGE_NUMBER_FORMATS.items():
            self.format.addItem(label, value)
        self.size = QDoubleSpinBox()
        self.size.setRange(4, 72)
        self.size.setValue(10)
        self.size.setSuffix(" pt")
        self.color = QLineEdit("#000000")
        self.output_dir = Path.home() / "Documents"
        self.output_controls = OutputDirectoryControls(self.output_dir)
        self.output_controls.directory_changed.connect(self._output_changed)
        self.run_button = QPushButton("添加页码")
        self.run_button.setObjectName("primaryAction")
        self.log_section = LogSection()
        self.log = self.log_section.log
        form = QFormLayout()
        form.addRow("页面范围", self.pages)
        form.addRow("位置", self.position)
        form.addRow("起始页码", self.start_number)
        form.addRow("格式", self.format)
        form.addRow("字号", self.size)
        form.addRow("颜色", self.color)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("添加页码：默认底部居中、从 1 开始，不覆盖源文件。"))
        layout.addWidget(self.source)
        layout.addLayout(form)
        layout.addWidget(self.output_controls)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.run_button)
        layout.addLayout(actions)
        layout.addWidget(self.log_section)
        self.run_button.clicked.connect(self.start)

    def start(self) -> None:
        if not self.source.source:
            QMessageBox.warning(self, "无法开始", "请先选择 PDF。")
            return
        pages = self.pages.text().strip() or (self.source.selected_pages() or None)
        config = PageNumberConfig(self.position.currentData(), self.start_number.value(), self.format.currentData(), self.size.value(), self.color.text().strip())
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = unique_path(self.output_dir, f"{self.source.source.stem}_添加页码", ".pdf")
        self.run_button.setEnabled(False)
        task = Task(lambda: add_pdf_page_numbers(self.source.source, pages=pages, config=config, output=target))
        task.signals.completed.connect(self.complete)
        task.signals.failed.connect(self.fail)
        self.pool.start(task)

    def _output_changed(self, value: str) -> None:
        self.output_dir = Path(value)

    def complete(self, value: object) -> None:
        self.run_button.setEnabled(True)
        self.log.add_message(f"完成：{value}", value)

    def fail(self, error: str) -> None:
        self.run_button.setEnabled(True)
        self.log.add_message(f"失败：{error}")


class RotationPanel(QWidget):
    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.source = PdfSourcePanel(pool)
        self.pages = QLineEdit()
        self.pages.setPlaceholderText("例如 1-3,5；留空使用勾选页")
        self.direction = QComboBox()
        self.direction.addItem("左转 90°", "left")
        self.direction.addItem("右转 90°", "right")
        self.output_dir = Path.home() / "Documents"
        self.output_controls = OutputDirectoryControls(self.output_dir)
        self.output_controls.directory_changed.connect(self._output_changed)
        self.run_button = QPushButton("旋转页面")
        self.run_button.setObjectName("primaryAction")
        self.log_section = LogSection()
        self.log = self.log_section.log
        form = QFormLayout()
        form.addRow("页面范围", self.pages)
        form.addRow("方向", self.direction)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("旋转页面：对选定页面执行左转或右转 90°。"))
        layout.addWidget(self.source)
        layout.addLayout(form)
        layout.addWidget(self.output_controls)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.run_button)
        layout.addLayout(actions)
        layout.addWidget(self.log_section)
        self.run_button.clicked.connect(self.start)

    def start(self) -> None:
        if not self.source.source:
            QMessageBox.warning(self, "无法开始", "请先选择 PDF。")
            return
        pages = self.pages.text().strip() or self.source.selected_pages()
        if not pages:
            QMessageBox.warning(self, "无法开始", "请输入页面范围或勾选页面。")
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = unique_path(self.output_dir, f"{self.source.source.stem}_旋转", ".pdf")
        self.run_button.setEnabled(False)
        task = Task(lambda: rotate_pdf_pages(self.source.source, pages, self.direction.currentData(), target))
        task.signals.completed.connect(self.complete)
        task.signals.failed.connect(self.fail)
        self.pool.start(task)

    def _output_changed(self, value: str) -> None:
        self.output_dir = Path(value)

    def complete(self, value: object) -> None:
        self.run_button.setEnabled(True)
        self.log.add_message(f"完成：{value}", value)

    def fail(self, error: str) -> None:
        self.run_button.setEnabled(True)
        self.log.add_message(f"失败：{error}")


class FromPdfPanel(QWidget):
    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.source: Path | None = None
        self.source_label = QLabel("尚未选择 PDF")
        self.mode = QComboBox()
        for label, value in (("Word（.docx）", "word"), ("PowerPoint（.pptx）", "ppt"), ("表格 Excel（.xlsx）", "excel"), ("逐页 PNG", "png"), ("逐页 JPG", "jpg")):
            self.mode.addItem(label, value)
        self.dpi = QComboBox()
        for value in (72, 150, 300):
            self.dpi.addItem(f"{value} DPI", value)
        self.dpi_row = QWidget()
        dpi_form = QFormLayout(self.dpi_row)
        dpi_form.setContentsMargins(0, 0, 0, 0)
        dpi_form.addRow("图片分辨率", self.dpi)
        self.output_dir = Path.home() / "Documents"
        self.output_controls = OutputDirectoryControls(self.output_dir)
        self.output_controls.directory_changed.connect(self._output_changed)
        self.run_button = QPushButton("开始转换")
        self.run_button.setObjectName("primaryAction")
        self.log_section = LogSection()
        self.log = self.log_section.log
        form = QFormLayout()
        form.addRow("目标格式", self.mode)
        form.addRow(self.dpi_row)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("从 PDF 转换：Word、PPT、可识别表格 Excel、逐页 PNG/JPG。"))
        top = QHBoxLayout()
        choose = QPushButton("选择 PDF")
        choose.clicked.connect(self.choose)
        top.addWidget(choose)
        top.addWidget(self.source_label, 1)
        layout.addLayout(top)
        layout.addLayout(form)
        layout.addWidget(self.output_controls)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.run_button)
        layout.addLayout(actions)
        layout.addWidget(self.log_section)
        self.mode.currentIndexChanged.connect(lambda: self.dpi_row.setVisible(self.mode.currentData() in {"png", "jpg"}))
        self.run_button.clicked.connect(self.start)
        self.dpi_row.setVisible(False)

    def choose(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        value, _ = QFileDialog.getOpenFileName(self, "选择 PDF", filter="PDF 文件 (*.pdf)")
        if value:
            self.source = Path(value)
            self.source_label.setText(value)

    def _output_changed(self, value: str) -> None:
        self.output_dir = Path(value)

    def start(self) -> None:
        if not self.source:
            QMessageBox.warning(self, "无法开始", "请先选择 PDF。")
            return
        mode = self.mode.currentData()
        if mode == "word":
            action = lambda: convert_pdf_to_word(self.source, self.output_dir)
        elif mode == "ppt":
            action = lambda: convert_pdf_to_ppt(self.source, self.output_dir)
        elif mode == "excel":
            action = lambda: convert_pdf_to_excel(self.source, self.output_dir)
        else:
            action = lambda: convert_pdf_to_images(self.source, image_format=mode, dpi=self.dpi.currentData(), output_directory=self.output_dir)
        self.run_button.setEnabled(False)
        task = Task(action)
        task.signals.completed.connect(self.complete)
        task.signals.failed.connect(self.fail)
        self.pool.start(task)

    def complete(self, result: object) -> None:
        self.run_button.setEnabled(True)
        items = result if isinstance(result, list) else [result]
        for item in items:
            self.log.add_message(f"完成：{item}", item)

    def fail(self, error: str) -> None:
        self.run_button.setEnabled(True)
        self.log.add_message(f"失败：{error}")



class CompressionPanel(QWidget):
    """Local Python PDF compression with quick size estimates."""

    PRESETS = (
        ("无损优化（不明显降低画质）", CompressionPreset.LOSSLESS),
        ("轻度压缩（优先保持清晰度）", CompressionPreset.LIGHT),
        ("平衡压缩（推荐）", CompressionPreset.BALANCED),
        ("强力压缩（优先减小体积）", CompressionPreset.STRONG),
    )

    def __init__(self, pool: QThreadPool):
        super().__init__()
        self.pool = pool
        self.source: Path | None = None
        self.output_dir = Path.home() / "Documents"
        self.source_label = QLabel("尚未选择 PDF")
        self.preset = QComboBox()
        for label, value in self.PRESETS:
            self.preset.addItem(label, value)
        self.estimate_label = QLabel("选择 PDF 后显示预估大小。")
        self.estimate_label.setWordWrap(True)
        self.output_controls = OutputDirectoryControls(self.output_dir)
        self.output_controls.directory_changed.connect(self._output_changed)
        self.choose_button = QPushButton("选择 PDF")
        self.run_button = QPushButton("压缩 PDF")
        self.run_button.setObjectName("primaryAction")
        self.log_section = LogSection()
        self.log = self.log_section.log
        self.choose_button.clicked.connect(self.choose)
        self.preset.currentIndexChanged.connect(self.refresh_estimate)
        self.run_button.clicked.connect(self.start)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("压缩 PDF")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("使用本地 Python 组件压缩 PDF，不调用任何外部程序。"))
        source_row = QHBoxLayout()
        source_row.addWidget(self.choose_button)
        source_row.addWidget(self.source_label, 1)
        layout.addLayout(source_row)
        form = QFormLayout()
        form.addRow("压缩档位", self.preset)
        form.addRow("大小预估", self.estimate_label)
        layout.addLayout(form)
        layout.addWidget(QLabel("预估大小仅供参考，最终大小以实际生成文件为准。"))
        layout.addWidget(self.output_controls)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.run_button)
        layout.addLayout(actions)
        layout.addWidget(self.log_section)

    def choose(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        value, _ = QFileDialog.getOpenFileName(self, "选择 PDF", filter="PDF 文件 (*.pdf)")
        if value:
            self.source = Path(value)
            self.source_label.setText(value)
            self.refresh_estimate()

    def _output_changed(self, value: str) -> None:
        self.output_dir = Path(value)

    def refresh_estimate(self) -> None:
        if not self.source:
            self.estimate_label.setText("选择 PDF 后显示预估大小。")
            return
        try:
            estimate = estimate_pdf_compression(self.source, self.preset.currentData())
        except Exception as exc:
            self.estimate_label.setText(f"无法预估：{exc}")
            return
        original = _format_size(estimate.original_bytes)
        projected = _format_size(estimate.estimated_bytes)
        percent = estimate.estimated_ratio * 100
        self.estimate_label.setText(
            f"原始 {original} → 预计约 {projected}，预计减少 {percent:.1f}%（可信度：{estimate.confidence}）\n{estimate.message}"
        )

    def start(self) -> None:
        if not self.source:
            QMessageBox.warning(self, "无法开始", "请先选择 PDF。")
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = unique_path(self.output_dir, f"{self.source.stem}_压缩", ".pdf")
        self.run_button.setEnabled(False)
        task = Task(lambda: compress_pdf(self.source, target, preset=self.preset.currentData()))
        task.signals.completed.connect(self.complete)
        task.signals.failed.connect(self.fail)
        self.pool.start(task)

    def complete(self, result: object) -> None:
        self.run_button.setEnabled(True)
        output = result
        if hasattr(result, "output_path"):
            saved = result.output_path
            self.log.add_message(
                f"完成：{saved}（{_format_size(result.original_bytes)} → {_format_size(result.output_bytes)}，减少 {result.compression_ratio * 100:.1f}%）",
                saved,
            )
        else:
            self.log.add_message(f"完成：{output}", output)
        self.refresh_estimate()

    def fail(self, error: str) -> None:
        self.run_button.setEnabled(True)
        self.log.add_message(f"失败：{error}")


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"
