import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")

from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import QApplication

from documenttools.app import MergeTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_merge_reorder_refreshes_auto_titles_and_keeps_custom_title(tmp_path: Path, app) -> None:
    paths = []
    for name in ("a", "b", "c"):
        path = tmp_path / f"{name}.pdf"
        path.touch()
        paths.append(str(path))

    tab = MergeTab(QThreadPool())
    tab.add_paths(paths)
    tab.table.item(0, 1).setText("保留标题")
    tab.table.setCurrentCell(2, 0)
    tab.move_selected(-1)

    assert [tab.table.item(row, 0).text() for row in range(3)] == ["a.pdf", "c.pdf", "b.pdf"]
    assert [tab.table.item(row, 1).text() for row in range(3)] == ["保留标题", "2. c", "3. b"]


def test_merge_remove_refreshes_auto_titles(tmp_path: Path, app) -> None:
    paths = []
    for name in ("a", "b", "c"):
        path = tmp_path / f"{name}.pdf"
        path.touch()
        paths.append(str(path))

    tab = MergeTab(QThreadPool())
    tab.add_paths(paths)
    tab.table.setCurrentCell(1, 0)
    tab.table.remove_selected()

    assert [tab.table.item(row, 0).text() for row in range(2)] == ["a.pdf", "c.pdf"]
    assert [tab.table.item(row, 1).text() for row in range(2)] == ["1. a", "2. c"]
