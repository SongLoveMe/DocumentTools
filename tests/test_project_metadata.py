from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_release_version_is_consistent() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "src" / "documenttools" / "__init__.py").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "DocumentTools.iss").read_text(encoding="utf-8")
    assert 'version = "2.2.0"' in pyproject
    assert '__version__ = "2.2.0"' in package
    assert '#define MyAppVersion "2.2.0"' in installer


def test_maintenance_docs_describe_ui_package() -> None:
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    development = (ROOT / "docs" / "DEVELOPMENT.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "ui/tasking.py" in architecture
    assert "ui/widgets.py" in architecture
    assert "2.2.0" in development
    assert "不要在多个模块复制 `Task`" in agents
    assert "## UI 统一规范" in agents


def test_no_bundled_office_runtime_or_renderer() -> None:
    """DocumentTools must never ship a renderer, runtime or helper executable."""
    src = ROOT / "src" / "documenttools"
    assert not (src / "office_pdf.py").exists()
    assert not (src / "fonts.py").exists()
    assert not (ROOT / "assets" / "fonts").exists()
    assert not (ROOT / "scripts" / "build_font.py").exists()
    assert not (ROOT / "vendor").exists()


def test_build_and_installer_package_dist_only() -> None:
    build = (ROOT / "scripts" / "build.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "DocumentTools.iss").read_text(encoding="utf-8")
    assert 'Source: "..\\dist\\DocumentTools\\*"' in installer
    for forbidden in ("prepare_runtime", "vendor\\libreoffice", "assets\\fonts"):
        assert forbidden not in build, forbidden
    assert "vendor\\libreoffice" not in installer


def test_pywin32_is_a_declared_dependency() -> None:
    """COM automation drives the local engines, so pywin32 must be pinned."""
    requirements = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    assert "pywin32==" in requirements
    assert "openpyxl" not in requirements
    assert "fonttools" not in requirements


def test_ui_has_one_task_implementation() -> None:
    pytest.importorskip("PyQt5")
    from documenttools.ui import pdf_workbench
    from documenttools.ui.tasking import Task
    assert pdf_workbench.Task is Task
    assert not (ROOT / "src" / "documenttools" / "workbench.py").exists()
    assert not (ROOT / "src" / "documenttools" / "outputlog.py").exists()
