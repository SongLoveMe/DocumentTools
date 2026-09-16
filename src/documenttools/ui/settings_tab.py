"""Settings workspace: engine selection, timeout and engine diagnostics."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QGuiApplication
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..conversions import ONLINE_CONVERSION_SERVICES
from ..engines import (
    MAX_TIMEOUT_SECONDS,
    MIN_TIMEOUT_SECONDS,
    available_engine_choices,
    detect_local_engines,
)
from ..settings import ENGINE_AUTO, ConversionSettings, load_settings, save_settings
from .dialogs import engine_diagnostics
from .widgets import LogSection


class SettingsTab(QWidget):
    """Configure which local engine converts Office documents to PDF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engines = detect_local_engines()
        self.settings = load_settings()

        self.engine = QComboBox()
        self.timeout = QSpinBox()
        self.diagnostics = QLabel()
        self.refresh_button = QPushButton("重新检测引擎")
        self.save_button = QPushButton("保存设置")
        self.save_button.setObjectName("primaryAction")
        self.log_section = LogSection()
        self.log = self.log_section.log

        self._build()
        self._load_into_widgets()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("设置")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "Office 转 PDF 通过本机已安装的 Microsoft Office 或 WPS 完成，"
            "转换过程中不会显示任何软件窗口。"
        ))

        self.timeout.setRange(MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS)
        self.timeout.setSuffix(" 秒")
        self.timeout.setToolTip("单个文件转换的最长等待时间，超时后将强制结束本机转换进程。")

        engine_form = QFormLayout()
        engine_form.addRow("转换引擎", self.engine)
        engine_form.addRow("转换超时", self.timeout)
        layout.addLayout(engine_form)

        diagnostics_title = QLabel("引擎诊断")
        diagnostics_title.setObjectName("sectionTitle")
        layout.addWidget(diagnostics_title)
        layout.addWidget(QLabel(
            "刚安装或升级 Office/WPS 后，点击“重新检测引擎”即可刷新下方状态，"
            "无需重启本程序。"
        ))
        self.diagnostics.setWordWrap(True)
        self.diagnostics.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.diagnostics)

        engine_actions = QHBoxLayout()
        engine_actions.addWidget(self.refresh_button)
        copy_button = QPushButton("复制诊断信息")
        copy_button.clicked.connect(self.copy_diagnostics)
        engine_actions.addWidget(copy_button)
        engine_actions.addStretch()
        engine_actions.addWidget(self.save_button)
        layout.addLayout(engine_actions)

        online_title = QLabel("在线转换服务")
        online_title.setObjectName("sectionTitle")
        layout.addWidget(online_title)
        layout.addWidget(QLabel(
            "本机没有安装 Microsoft Office 或 WPS 时，可用以下第三方在线服务转换文档。"
            "文件会上传到对应服务商，敏感文档请勿使用。"
        ))
        for name, url in ONLINE_CONVERSION_SERVICES:
            link = QLabel('<a href="' + url + '">' + name + '</a>')
            link.setOpenExternalLinks(False)
            link.linkActivated.connect(self._open_url)
            layout.addWidget(link)

        layout.addStretch()
        layout.addWidget(self.log_section)

        self.save_button.clicked.connect(self.save)
        self.refresh_button.clicked.connect(self.refresh_engines)

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _load_into_widgets(self) -> None:
        self._reload_engine_choices()
        self.timeout.setValue(self.settings.timeout_seconds)
        self.refresh_diagnostics()

    def _reload_engine_choices(self) -> None:
        """Repopulate the engine combo from the current detection result."""
        current = self.engine.currentData() or self.settings.engine
        self.engine.blockSignals(True)
        self.engine.clear()
        self.engine.addItem("自动（优先 Microsoft Office，失败后尝试 WPS）", ENGINE_AUTO)
        for label, value in available_engine_choices(self.engines):
            self.engine.addItem("仅使用 " + label, value)
        index = self.engine.findData(current)
        self.engine.setCurrentIndex(index if index >= 0 else 0)
        self.engine.setEnabled(bool(self.engines))
        self.engine.blockSignals(False)

    def refresh_diagnostics(self) -> None:
        self.diagnostics.setText(engine_diagnostics(self.engines))

    def refresh_engines(self) -> None:
        """Re-run engine detection so a freshly installed engine is noticed."""
        self.engines = detect_local_engines()
        self._reload_engine_choices()
        self.refresh_diagnostics()
        if self.engines:
            names = "、".join(engine.label() for engine in self.engines)
            self.log.add_message("已重新检测引擎：" + names)
        else:
            self.log.add_message("已重新检测引擎：未检测到本机 Microsoft Office 或 WPS。")

    def copy_diagnostics(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(engine_diagnostics(self.engines))
        self.log.add_message("已复制引擎诊断信息到剪贴板。")

    def save(self) -> None:
        self.settings = save_settings(
            ConversionSettings(
                engine=self.engine.currentData() or ENGINE_AUTO,
                timeout_seconds=self.timeout.value(),
            )
        )
        self.log.add_message("设置已保存。")


__all__ = ["SettingsTab"]
