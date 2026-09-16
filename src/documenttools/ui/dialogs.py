"""Shared dialogs for local engine selection and online conversion guidance."""

from __future__ import annotations

import sys

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices, QGuiApplication
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..conversions import ONLINE_CONVERSION_SERVICES
from ..engines import LocalEngineInfo, available_engine_choices


def engine_diagnostics(engines: tuple[LocalEngineInfo, ...] | list[LocalEngineInfo]) -> str:
    """Build the copyable diagnostic block shown to users and support."""
    from .. import __version__

    lines = [
        f"DocumentTools {__version__}",
        f"Python {sys.version.split()[0]}",
        f"平台：{sys.platform}",
    ]
    if not engines:
        lines.append("未检测到本机 Microsoft Office 或 WPS。")
    for engine in engines:
        lines.extend(engine.diagnostics())
    return "\n".join(lines)


class OnlineConversionDialog(QDialog):
    """Tell the user how to convert when no local engine is available."""

    def __init__(self, detail: str = "", engines=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("需要本机 Office 或 WPS")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        heading = QLabel("未检测到可用的本机 Office 或 WPS 引擎")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        layout.addWidget(QLabel(
            "DocumentTools 不内置排版引擎，Office 转 PDF 需要调用本机已安装的 "
            "Microsoft Office 或 WPS。\n"
            "你可以先安装其中任意一款后重试，或改用以下在线服务完成转换："
        ))
        if detail:
            message = QLabel(detail)
            message.setWordWrap(True)
            layout.addWidget(message)

        for name, url in ONLINE_CONVERSION_SERVICES:
            button = QPushButton(f"打开 {name}")
            button.clicked.connect(lambda _=False, target=url: self._open(target))
            layout.addWidget(button)

        actions = QDialogButtonBox()
        copy_button = QPushButton("复制诊断信息")
        actions.addButton(copy_button, QDialogButtonBox.ActionRole)
        copy_button.clicked.connect(lambda: self._copy(engines))
        close_button = actions.addButton("关闭", QDialogButtonBox.RejectRole)
        close_button.clicked.connect(self.reject)
        layout.addWidget(actions)

    def _open(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _copy(self, engines) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(engine_diagnostics(engines))


class EngineChoiceDialog(QDialog):
    """Let the user pick one of the detected engines and remember the choice."""

    def __init__(self, engines, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择转换引擎")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("检测到多个可用的本机引擎，请选择用于转为 PDF 的引擎："))

        self.combo = QComboBox()
        for label, value in available_engine_choices(engines):
            self.combo.addItem(label, value)
        self.remember = QCheckBox("记住我的选择（可在“设置”中修改）")
        self.remember.setChecked(True)

        form = QFormLayout()
        form.addRow("转换引擎", self.combo)
        layout.addLayout(form)
        layout.addWidget(self.remember)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_engine(self) -> str | None:
        return self.combo.currentData()

    def should_remember(self) -> bool:
        return self.remember.isChecked()


__all__ = ["EngineChoiceDialog", "OnlineConversionDialog", "engine_diagnostics"]
