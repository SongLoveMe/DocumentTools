from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import QThreadPool
from PyQt5.QtGui import QColor, QIcon, QPalette
from PyQt5.QtWidgets import QApplication, QListWidget, QMainWindow, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget

from ..engines import available_engine_labels, detect_local_engines
from .conversion_tab import ConversionTab
from .merge_tab import MergeTab
from .pdf_workbench import CompressionPanel, FromPdfPanel, NumberingPanel, PageOperationPanel, RotationPanel
from .settings_tab import SettingsTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DocumentTools")
        self.resize(1180, 820)
        icon = Path(__file__).parents[3] / "assets" / "documenttools.ico"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(3)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(210)
        self.navigation.setSpacing(4)
        self.stack = QStackedWidget()
        categories = [
            ("排列 PDF", self._arrangement_page()),
            ("转为 PDF", ConversionTab(self.pool)),
            ("从 PDF 转换", FromPdfPanel(self.pool)),
            ("编辑 PDF", self._editing_page()),
            ("设置", SettingsTab()),
        ]
        for label, widget in categories:
            self.navigation.addItem(label)
            self.stack.addWidget(widget)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        splitter = QSplitter()
        splitter.addWidget(self.navigation)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)
        self.statusBar().showMessage(self._engine_message())

    def _arrangement_page(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(MergeTab(self.pool), "合并")
        tabs.addTab(PageOperationPanel(self.pool), "拆分 / 页面操作")
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(tabs)
        return page

    def _editing_page(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(NumberingPanel(self.pool), "添加页码")
        tabs.addTab(RotationPanel(self.pool), "旋转页面")
        tabs.addTab(CompressionPanel(self.pool), "压缩 PDF")
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(tabs)
        return page

    @staticmethod
    def _engine_message() -> str:
        """Describe the detected local conversion engines in the status bar."""
        labels = available_engine_labels(detect_local_engines())
        if labels:
            return "转换引擎：" + "、".join(labels)
        return "转换引擎：未检测到本机 Microsoft Office 或 WPS"

def _apply_palette(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#f6f8fb"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.Text, QColor("#17202a"))
    palette.setColor(QPalette.WindowText, QColor("#17202a"))
    palette.setColor(QPalette.Highlight, QColor("#2563eb"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(
        "QMainWindow{background:#f6f8fb}"
        "QListWidget#navigation{background:#172033;color:#dbe5f1;border:0;padding:14px 9px;font-size:15px}"
        "QListWidget#navigation::item{padding:12px;border-radius:7px}"
        "QListWidget#navigation::item:selected{background:#2563eb;color:#fff}"
        "QListWidget#outputLog{background:#fbfcfe;border:1px solid #d7dee8;border-radius:8px;padding:4px}"
        "QListWidget#pageThumbnails{background:#f8fafc;border:1px solid #d7dee8;border-radius:8px;padding:8px}"
        "QTabWidget::pane{border:1px solid #d7dee8;background:#fff;border-radius:8px}"
        "QTabBar::tab{padding:10px 20px;color:#52606d}"
        "QTabBar::tab:selected{color:#1d4ed8;border-bottom:2px solid #2563eb}"
        "QPushButton{min-height:34px;padding:0 14px;border:1px solid #cbd5e1;border-radius:6px;background:#fff}"
        "QPushButton#primaryAction{background:#2563eb;color:#fff;border-color:#2563eb;font-weight:600}"
        "QLabel#outputPath{color:#52606d}"
        "QPushButton:hover{border-color:#2563eb;color:#1d4ed8}"
        "QPushButton:disabled{color:#9aa5b1;background:#f1f4f8}"
        "QComboBox,QLineEdit,QTableWidget{border:1px solid #cbd5e1;border-radius:6px;background:#fff;padding:4px}"
        "QProgressBar{min-height:10px;border:1px solid #d7dee8;border-radius:5px;background:#edf2f7;text-align:center}"
        "QProgressBar::chunk{background:#2563eb;border-radius:5px}"
        "QLabel#sectionTitle{font-size:22px;font-weight:650;color:#17202a;padding:4px 0}"
    )

def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DocumentTools")
    app.setApplicationDisplayName("DocumentTools")
    app.setWindowIcon(QIcon(str(Path(__file__).parents[3] / "assets" / "documenttools.ico")))
    _apply_palette(app)
    window = MainWindow()
    window.show()
    return app.exec_()
