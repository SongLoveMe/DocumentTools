from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")

from documenttools.pdf_tools import MergeItem, PageSizeConfig, PdfOperationError, format_directory_title, merge_pdfs  # noqa: E402


def test_directory_title_templates() -> None:
    assert format_directory_title(3, "report.pdf", "numeric") == "3. report"
    assert format_directory_title(3, "report.pdf", "中文（一. 二. 三.）") == "三. report"
    assert format_directory_title(2, "report.pdf", "英文字母（A. B. C.）") == "B. report"
    assert format_directory_title(3, "report.pdf", "不加序号") == "report"


def _sample_pdf(path: Path, label: str, pages: int) -> None:
    from reportlab.pdfgen.canvas import Canvas

    canvas = Canvas(str(path))
    for page in range(pages):
        canvas.drawString(72, 720, f"{label} page {page + 1}")
        canvas.showPage()
    canvas.save()


def test_merge_adds_toc_and_outlines(tmp_path: Path) -> None:
    first = tmp_path / "A.pdf"
    second = tmp_path / "B.pdf"
    output = tmp_path / "merged.pdf"
    _sample_pdf(first, "A", 2)
    _sample_pdf(second, "B", 1)

    entries = merge_pdfs([first, second], output)

    assert [entry.title for entry in entries] == ["A", "B"]
    assert [entry.start_page for entry in entries] == [2, 4]
    reader = pypdf.PdfReader(str(output))
    assert len(reader.pages) == 4
    assert reader.outline[0].title == "A"
    assert reader.outline[1].title == "B"


def test_merge_uses_custom_titles_cover_and_page_policy(tmp_path: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen.canvas import Canvas

    cover = tmp_path / "cover.pdf"
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "merged.pdf"
    _sample_pdf(cover, "cover", 1)
    _sample_pdf(first, "first", 1)
    canvas = Canvas(str(second), pagesize=letter)
    canvas.drawString(72, 720, "second")
    canvas.save()

    entries = merge_pdfs(
        [MergeItem(first, "第一部分"), MergeItem(second, "第二部分")], output,
        cover=cover, page_size=PageSizeConfig(preset="Letter", orientation="landscape"),
    )

    assert [entry.title for entry in entries] == ["第一部分", "第二部分"]
    assert [entry.start_page for entry in entries] == [3, 4]
    reader = pypdf.PdfReader(str(output))
    assert len(reader.pages) == 4
    assert round(float(reader.pages[2].mediabox.width)) == 792
    assert round(float(reader.pages[2].mediabox.height)) == 612


def test_merge_can_keep_original_size_and_open_empty_password_pdf(tmp_path: Path) -> None:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen.canvas import Canvas

    source = tmp_path / "restricted.pdf"
    temporary = tmp_path / "plain.pdf"
    canvas = Canvas(str(temporary), pagesize=letter)
    canvas.drawString(72, 720, "restricted")
    canvas.save()
    protected = PdfWriter()
    for page in PdfReader(str(temporary)).pages:
        protected.add_page(page)
    protected.encrypt("", "owner-password")
    with source.open("wb") as handle:
        protected.write(handle)

    output = tmp_path / "output.pdf"
    merge_pdfs([source], output, page_size=PageSizeConfig(preserve_original=True))
    reader = PdfReader(str(output))
    assert round(float(reader.pages[1].mediabox.width)) == 612
    assert not reader.is_encrypted


def test_merge_rejects_real_open_password(tmp_path: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    plain = tmp_path / "plain.pdf"
    protected = tmp_path / "protected.pdf"
    _sample_pdf(plain, "plain", 1)
    writer = PdfWriter()
    for page in PdfReader(str(plain)).pages:
        writer.add_page(page)
    writer.encrypt("secret")
    with protected.open("wb") as handle:
        writer.write(handle)

    with pytest.raises(PdfOperationError, match="打开密码"):
        merge_pdfs([protected], tmp_path / "out.pdf")


def test_merge_nests_source_bookmarks_under_custom_entry(tmp_path: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    plain = tmp_path / "plain.pdf"
    source = tmp_path / "bookmarked.pdf"
    _sample_pdf(plain, "source", 2)
    writer = PdfWriter()
    reader = PdfReader(str(plain))
    for page in reader.pages:
        writer.add_page(page)
    section = writer.add_outline_item("源章节", 0)
    writer.add_outline_item("源小节", 1, parent=section)
    with source.open("wb") as handle:
        writer.write(handle)

    output = tmp_path / "merged.pdf"
    merge_pdfs([MergeItem(source, "自定义目录")], output)
    outline = PdfReader(str(output)).outline
    assert outline[0].title == "自定义目录"
    assert outline[1][0].title == "源章节"
    assert outline[1][1][0].title == "源小节"


def test_merge_can_skip_generated_toc_page(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "merged.pdf"
    _sample_pdf(first, "first", 2)
    _sample_pdf(second, "second", 1)

    entries = merge_pdfs([first, second], output, include_toc=False)

    assert [entry.start_page for entry in entries] == [1, 3]
    assert len(pypdf.PdfReader(str(output)).pages) == 3


def test_merge_removes_source_visual_toc_and_keeps_its_bookmarks(tmp_path: Path) -> None:
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen.canvas import Canvas

    source = tmp_path / "source.pdf"
    raw = tmp_path / "raw.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "merged.pdf"
    canvas = Canvas(str(raw))
    for label in ("Contents", "Chapter one content", "Chapter two content"):
        canvas.drawString(72, 720, label)
        canvas.showPage()
    canvas.save()
    writer = PdfWriter()
    for page in PdfReader(str(raw)).pages:
        writer.add_page(page)
    writer.add_outline_item("Chapter one", 1)
    writer.add_outline_item("Chapter two", 2)
    with source.open("wb") as handle:
        writer.write(handle)
    _sample_pdf(second, "second", 1)

    entries = merge_pdfs([MergeItem(source, "Source file"), second], output)

    reader = PdfReader(str(output))
    assert [entry.start_page for entry in entries] == [2, 4]
    assert len(reader.pages) == 4
    assert "Chapter one content" in reader.pages[1].extract_text()
    assert "Contents" not in reader.pages[1].extract_text()
    assert reader.outline[0].title == "Source file"
    assert reader.outline[1][0].title == "Chapter one"
    toc_text = reader.pages[0].extract_text()
    assert "Source file" in toc_text
    assert "Chapter one" in toc_text
    assert "Chapter two" in toc_text


def test_merge_accepts_documenttools_generated_pdf_as_source(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    generated = tmp_path / "generated.pdf"
    output = tmp_path / "output.pdf"
    _sample_pdf(first, "first", 1)
    _sample_pdf(second, "second", 1)

    merge_pdfs([first, second], generated)
    assert pypdf.PdfReader(str(generated)).pages[0].get("/DocumentToolsToc")
    entries = merge_pdfs([MergeItem(generated, "已合并文件"), second], output)

    reader = pypdf.PdfReader(str(output))
    assert [entry.start_page for entry in entries] == [2, 4]
    assert len(reader.pages) == 4
    assert reader.outline[0].title == "已合并文件"
    assert reader.outline[1][0].title == "first"


def test_generated_toc_includes_source_bookmarks_as_children(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    source_with_toc = tmp_path / "source-with-toc.pdf"
    output = tmp_path / "output.pdf"
    _sample_pdf(first, "A", 1)
    _sample_pdf(second, "B-child", 1)

    merge_pdfs([first, second], source_with_toc)
    merge_pdfs([MergeItem(first, "A"), MergeItem(source_with_toc, "B")], output)

    toc_text = pypdf.PdfReader(str(output)).pages[0].extract_text()
    assert "A" in toc_text
    assert "B" in toc_text
    assert "first" in toc_text
    assert "second" in toc_text
