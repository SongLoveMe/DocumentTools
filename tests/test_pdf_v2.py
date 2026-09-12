from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
reportlab = pytest.importorskip("reportlab")
pytest.importorskip("fitz")

from documenttools.pdf_tools import (
    CompressionPreset, PageNumberConfig, PdfOperationError, add_pdf_page_numbers, compress_pdf,
    delete_pdf_pages, estimate_pdf_compression,
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


def test_pdf_compression_presets_keep_page_count_and_input(tmp_path: Path):
    source = tmp_path / "source.pdf"
    make_pdf(source, 3)
    original_size = source.stat().st_size

    estimate = estimate_pdf_compression(source, CompressionPreset.BALANCED)
    assert estimate.original_bytes == original_size
    assert estimate.estimated_bytes > 0
    assert 0 <= estimate.estimated_ratio <= 1
    assert estimate.confidence

    outputs = []
    for preset in CompressionPreset:
        output = tmp_path / f"compressed-{preset.value}.pdf"
        result = compress_pdf(source, output, preset=preset)
        outputs.append(output)
        assert result.output_path == output
        assert output.exists()
        assert len(pypdf.PdfReader(str(output)).pages) == 3
        assert source.stat().st_size == original_size

    assert len(outputs) == 4


def test_pdf_compression_rejects_overwrite_and_real_password(tmp_path: Path):
    source = tmp_path / "source.pdf"
    make_pdf(source, 1)
    with pytest.raises(PdfOperationError, match="覆盖"):
        compress_pdf(source, source)

    protected = tmp_path / "protected.pdf"
    writer = pypdf.PdfWriter()
    for page in pypdf.PdfReader(str(source)).pages:
        writer.add_page(page)
    writer.encrypt("secret")
    with protected.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(PdfOperationError, match="打开密码"):
        compress_pdf(protected, tmp_path / "protected-output.pdf")
