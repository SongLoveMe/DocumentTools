from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")
pytest.importorskip("xlsxwriter")

from documenttools.conversions import ConversionError, convert_pdf_to_excel, convert_pdf_to_images


def table_pdf(path: Path) -> None:
    document = fitz.open()
    for page_number in range(2):
        page = document.new_page(width=300, height=200)
        for x in (50, 150, 250):
            page.draw_line((x, 40), (x, 150))
        for y in (40, 80, 115, 150):
            page.draw_line((50, y), (250, y))
        for row, y in enumerate((65, 100, 135)):
            page.insert_text((60, y), f"p{page_number + 1}-{row}")
            page.insert_text((160, y), str(row))
    document.save(path)
    document.close()


def test_pdf_to_images_png_and_jpg(tmp_path: Path):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page()
    document.new_page()
    document.save(source)
    document.close()
    png = convert_pdf_to_images(source, image_format="png", dpi=72)
    jpg = convert_pdf_to_images(source, image_format="jpg", dpi=72)
    assert len(png) == len(jpg) == 2
    assert all(path.suffix == ".png" for path in png)
    assert all(path.suffix == ".jpg" for path in jpg)


def test_pdf_to_images_rejects_invalid_dpi(tmp_path: Path):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page()
    document.save(source)
    document.close()
    with pytest.raises(ConversionError):
        convert_pdf_to_images(source, dpi=100)


def test_pdf_to_excel_extracts_tables(tmp_path: Path):
    source = tmp_path / "tables.pdf"
    table_pdf(source)
    output = convert_pdf_to_excel(source)
    assert output.exists()
    import zipfile
    with zipfile.ZipFile(output) as archive:
        names = [name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")]
    assert len(names) >= 2
