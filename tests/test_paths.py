from pathlib import Path

from documenttools.paths import classify_file, unique_path


def test_classify_supported_files() -> None:
    assert classify_file("report.docx") == "office"
    assert classify_file("slides.PPTX") == "office"
    assert classify_file("scan.TIFF") == "image"
    assert classify_file("merged.pdf") == "pdf"
    assert classify_file("archive.zip") == "unsupported"


def test_unique_path_never_overwrites(tmp_path: Path) -> None:
    first = tmp_path / "result.pdf"
    second = tmp_path / "result (1).pdf"
    first.touch()
    second.touch()
    assert unique_path(tmp_path, "result", ".pdf") == tmp_path / "result (2).pdf"

