import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import QApplication

from documenttools.app import MainWindow
from documenttools.ui.pdf_workbench import PageOperationPanel
from documenttools.ui.tasking import Task
from documenttools.ui.widgets import FileTable, OutputLog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_main_window_has_v2_categories(app):
    window = MainWindow()
    assert [window.navigation.item(index).text() for index in range(window.navigation.count())] == [
        "排列 PDF", "转为 PDF", "从 PDF 转换", "编辑 PDF"
    ]
    assert window.stack.count() == 4
    window.close()


def test_page_operation_panel_starts_with_split_mode(app):
    panel = PageOperationPanel(QThreadPool())
    assert panel.operation.currentData() is None
    assert panel.options.currentIndex() == 0
    from PyQt5.QtWidgets import QAbstractItemView
    assert panel.source.pages.dragDropMode() == QAbstractItemView.NoDragDrop
    panel.operation.setCurrentIndex(1)
    assert panel.operation.currentData() == "split"
    assert panel.options.currentIndex() == 1
    assert panel.options.currentWidget() is not panel.range_edit.parentWidget()
    panel.close()
