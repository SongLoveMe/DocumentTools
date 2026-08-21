from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_release_version_is_consistent() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "src" / "documenttools" / "__init__.py").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "DocumentTools.iss").read_text(encoding="utf-8")
    assert 'version = "2.0.0"' in pyproject
    assert '__version__ = "2.0.0"' in package
    assert '#define MyAppVersion "2.0.0"' in installer


def test_maintenance_docs_describe_ui_package() -> None:
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    development = (ROOT / "docs" / "DEVELOPMENT.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "ui/tasking.py" in architecture
    assert "ui/widgets.py" in architecture
    assert "版本 `2.0.0`" in development
    assert "不要在多个模块复制 `Task`" in agents


def test_ui_has_one_task_implementation() -> None:
    pytest.importorskip("PyQt5")
    from documenttools.ui import pdf_workbench
    from documenttools.ui.tasking import Task
    assert pdf_workbench.Task is Task
    assert not (ROOT / "src" / "documenttools" / "workbench.py").exists()
    assert not (ROOT / "src" / "documenttools" / "outputlog.py").exists()
