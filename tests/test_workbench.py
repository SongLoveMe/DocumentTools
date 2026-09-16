import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import QApplication, QTabWidget

from documenttools.app import MainWindow
from documenttools.ui.conversion_tab import ConversionTab
from documenttools.ui.pdf_workbench import PageOperationPanel
from documenttools.ui.tasking import Task
from documenttools.ui.widgets import FileTable, LogSection, OutputLog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_main_window_has_v2_categories(app):
    window = MainWindow()
    assert [window.navigation.item(index).text() for index in range(window.navigation.count())] == [
        "排列 PDF", "转为 PDF", "从 PDF 转换", "编辑 PDF", "设置"
    ]
    assert window.stack.count() == 5
    assert window.stack.widget(3).findChildren(QTabWidget)[0].tabText(2) == "压缩 PDF"
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


def test_log_section_clears_only_current_log_and_accepts_new_messages(app):
    section = LogSection()
    section.add_message("第一条")
    section.add_message("第二条")
    assert section.log.count() == 2

    section.clear_button.click()
    assert section.log.count() == 0

    section.add_message("后续记录")
    assert section.log.count() == 1


def test_conversion_start_does_not_clear_existing_log(app, monkeypatch, tmp_path: Path):
    tab = ConversionTab(QThreadPool())
    tab.log.add_message("保留：上一次任务记录")
    source = tmp_path / "image.png"
    from PIL import Image
    Image.new("RGB", (8, 8), "white").save(source)
    tab.add_paths([str(source)])

    captured = {}

    def fake_run_actions(actions):
        captured["actions"] = actions

    monkeypatch.setattr(tab, "_run_actions", fake_run_actions)
    tab.start()

    assert tab.log.count() == 1
    assert captured["actions"]


def test_settings_tab_exposes_engine_refresh_and_online_links(app, monkeypatch):
    """The settings page must offer manual re-detection and the online services."""
    from documenttools.ui.settings_tab import SettingsTab
    from documenttools.conversions import ONLINE_CONVERSION_SERVICES
    from PyQt5.QtWidgets import QLabel

    calls: list[int] = []
    original = __import__("documenttools.engines", fromlist=["detect_local_engines"])
    real_detect = original.detect_local_engines

    def counting_detect(*args, **kwargs):
        calls.append(1)
        return real_detect(*args, **kwargs)

    monkeypatch.setattr("documenttools.ui.settings_tab.detect_local_engines", counting_detect)
    tab = SettingsTab()

    # A dedicated button performs the re-detection.
    assert tab.refresh_button.text() == "重新检测引擎"
    before = len(calls)
    tab.refresh_button.click()
    assert len(calls) == before + 1, "the refresh button must re-run detection"
    assert tab.log.count() >= 1, "refreshing must record a log entry"

    # Every online service is documented on the page.
    texts = [label.text() for label in tab.findChildren(QLabel)]
    for name, url in ONLINE_CONVERSION_SERVICES:
        assert any(name in text and url in text for text in texts), name

    # PDF/A and the PDF->Word backend are gone.
    joined = " ".join(texts)
    assert "PDF/A" not in joined
    assert "PDF 转 Word" not in joined
    tab.close()


def test_settings_tab_engine_list_matches_detection(app):
    from documenttools.ui.settings_tab import SettingsTab
    tab = SettingsTab()
    detected = {engine.kind.value for engine in tab.engines}
    listed = {
        tab.engine.itemData(i)
        for i in range(tab.engine.count())
        if tab.engine.itemData(i) != "auto"
    }
    assert listed == detected
    tab.close()
