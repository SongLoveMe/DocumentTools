from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
reportlab = pytest.importorskip("reportlab")

from documenttools.pdf_tools import (
    PageNumberConfig, PdfOperationError, add_pdf_page_numbers, delete_pdf_pages,
    extract_pdf_pages, parse_page_selection, reorder_pdf_pages, rotate_pdf_pages,
    split_pdf,
)


def make_pdf(path: Path, count: int = 5) -> None:
    from reportlab.pdfgen.canvas import Canvas
    canvas = Canvas(str(path))
    for index in range(1, count + 1):
        canvas.drawString(72, 720, f"page {index}")
        canvas.showPage()
    canvas.save()


def pages(path: Path) -> int:
    return len(pypdf.PdfReader(str(path)).pages)


def test_parse_page_selection_and_validation():
    assert parse_page_selection("1-3,末页", 5) == [0, 1, 2, 4]
    assert parse_page_selection("3,1,2,2", 3, allow_duplicates=True) == [2, 0, 1, 1]
    with pytest.raises(PdfOperationError):
        parse_page_selection("1-4", 3)
    with pytest.raises(PdfOperationError):
        parse_page_selection("1,1", 3)


def test_split_extract_delete_reorder(tmp_path: Path):
    source = tmp_path / "source.pdf"
    make_pdf(source)
    result = split_pdf(source, mode="breakpoints", breakpoints="2,4")
    assert [pages(path) for path in result] == [2, 2, 1]
    assert pages(extract_pdf_pages(source, "1,3,5")) == 3
    assert pages(delete_pdf_pages(source, "2,4")) == 3
    assert pages(reorder_pdf_pages(source, "5,1,1")) == 3


def test_rotate_and_number_pages(tmp_path: Path):
    source = tmp_path / "source.pdf"
    make_pdf(source, 2)
    rotated = rotate_pdf_pages(source, "2", "right")
    assert pypdf.PdfReader(str(rotated)).pages[1].get("/Rotate") == 90
    numbered = add_pdf_page_numbers(source, config=PageNumberConfig(start_number=10, position="bottom-center"))
    assert pages(numbered) == 2
    assert "10" in (pypdf.PdfReader(str(numbered)).pages[0].extract_text() or "")
