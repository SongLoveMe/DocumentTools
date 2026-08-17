from pathlib import Path

import pytest

pytest.importorskip("PIL")

from documenttools.conversions import image_to_pdf  # noqa: E402


def test_image_group_to_pdf(tmp_path: Path) -> None:
    from PIL import Image

    first = tmp_path / "one.png"
    second = tmp_path / "two.png"
    Image.new("RGB", (80, 60), "white").save(first)
    Image.new("RGB", (80, 60), "black").save(second)
    output = tmp_path / "images.pdf"

    image_to_pdf([first, second], output)

    assert output.exists()
    assert output.stat().st_size > 0


def test_pdf_to_ppt_creates_one_slide_per_page(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    pytest.importorskip("pptx")
    pytest.importorskip("reportlab")
    from pptx import Presentation
    from reportlab.pdfgen.canvas import Canvas

    from documenttools.conversions import convert_pdf_to_ppt

    source = tmp_path / "source.pdf"
    canvas = Canvas(str(source))
    canvas.drawString(72, 720, "first")
    canvas.showPage()
    canvas.drawString(72, 720, "second")
    canvas.save()

    output = convert_pdf_to_ppt(source, tmp_path)

    assert len(Presentation(str(output)).slides) == 2
