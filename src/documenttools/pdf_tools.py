from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PdfOperationError(RuntimeError):
    """A user-facing PDF operation failure."""


TITLE_TEMPLATES = {
    "数字（1. 2. 3.）": "numeric",
    "中文（一. 二. 三.）": "chinese",
    "英文字母（A. B. C.）": "alpha",
    "不加序号": "none",
}


def _chinese_index(index: int) -> str:
    digits = "零一二三四五六七八九"
    if index < 10:
        return digits[index]
    if index < 20:
        return "十" if index == 10 else "十" + digits[index - 10]
    tens, ones = divmod(index, 10)
    return digits[tens] + "十" + (digits[ones] if ones else "")


def format_directory_title(index: int, filename: str, template: str = "numeric") -> str:
    """Build the initial directory title for a 1-based source position."""
    stem = Path(filename).stem
    if template in TITLE_TEMPLATES:
        template = TITLE_TEMPLATES[template]
    if template == "chinese":
        prefix = f"{_chinese_index(index)}. "
    elif template == "alpha":
        prefix = f"{chr(64 + index)}. " if 1 <= index <= 26 else f"{index}. "
    elif template == "none":
        prefix = ""
    else:
        prefix = f"{index}. "
    return prefix + stem


@dataclass
class MergeItem:
    path: Path
    title: str | None = None
    status: str = "待处理"
    page_count: int = 0

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.title:
            self.title = self.path.stem


@dataclass(frozen=True)
class PageSizeConfig:
    preset: str = "A4"
    orientation: str = "portrait"
    width: float | None = None
    height: float | None = None
    preserve_original: bool = False

    PRESETS = {
        "A3": (841.89, 1190.55), "A4": (595.28, 841.89),
        "A5": (419.53, 595.28), "B5": (498.90, 708.66), "Letter": (612.0, 792.0),
    }

    def dimensions(self) -> tuple[float, float]:
        if self.preserve_original:
            return self.PRESETS["A4"]
        width, height = (self.width, self.height) if self.width and self.height else self.PRESETS.get(self.preset, self.PRESETS["A4"])
        return (max(width, height), min(width, height)) if self.orientation.lower().startswith("land") else (min(width, height), max(width, height))


@dataclass(frozen=True)
class TocEntry:
    title: str
    start_page: int
    children: tuple["TocEntry", ...] = ()


@dataclass
class _OutlineNode:
    title: str
    source_page: int
    children: list["_OutlineNode"]


def _require_pdf_packages():
    try:
        from pypdf import PageObject, PdfReader, PdfWriter, Transformation  # type: ignore[import-not-found]
        from reportlab.lib.pagesizes import A4  # type: ignore[import-not-found]
        from reportlab.pdfbase import pdfmetrics  # type: ignore[import-not-found]
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore[import-not-found]
        from reportlab.pdfgen import canvas  # type: ignore[import-not-found]
    except ImportError as exc:
        raise PdfOperationError("PDF 支持未安装，请使用 documenttools 环境安装依赖。") from exc
    return PdfReader, PdfWriter, Transformation, PageObject, A4, pdfmetrics, UnicodeCIDFont, canvas


def _open_reader(path: Path):
    PdfReader, *_ = _require_pdf_packages()
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise PdfOperationError(f"不是可读取的 PDF：{path}")
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise PdfOperationError(f"{path.name} 需要打开密码，无法猜测密码。")
        if not reader.pages:
            raise PdfOperationError(f"{path.name} 没有页面。")
        return reader
    except PdfOperationError:
        raise
    except Exception as exc:
        raise PdfOperationError(f"无法读取 {path.name}：{exc}") from exc


TOC_MARKERS = ("目录", "目次", "contents", "table of contents")


def _is_toc_label(value: str) -> bool:
    return any(marker in value.lower() for marker in TOC_MARKERS)


def _is_documenttools_toc_page(page: Any) -> bool:
    if page.get("/DocumentToolsToc"):
        return True
    # Older DocumentTools files did not carry the explicit marker. Their
    # generated directory pages use STSong-Light, which distinguishes them
    # from normal body pages when an outline already identifies the content.
    try:
        resources = page.get("/Resources").get_object()
        fonts = resources.get("/Font").get_object()
        return any("STSong-Light" in str(font.get_object().get("/BaseFont", "")) for font in fonts.values())
    except Exception:
        return False


def _destination_page_number(reader: Any, node: Any) -> int | None:
    """Resolve both standard destination objects and DocumentTools' numeric destinations."""
    try:
        page = reader.get_destination_page_number(node)
    except Exception:
        page = None
    if isinstance(page, int):
        return page
    try:
        raw_page = node.get("/Page")
        if isinstance(raw_page, int):
            return raw_page
    except Exception:
        pass
    return None


def _source_visual_toc_pages(reader: Any) -> set[int]:
    """Detect a leading visual TOC when source bookmarks identify later content."""
    try:
        outline = reader.outline
    except Exception:
        return set()

    content_pages: list[int] = []
    top_level_count = 0

    def visit(nodes: list[Any], top_level: bool = False) -> None:
        nonlocal top_level_count
        for node in nodes:
            if isinstance(node, list):
                visit(node)
                continue
            if top_level:
                top_level_count += 1
            page = _destination_page_number(reader, node)
            if page is None:
                continue
            if not _is_toc_label(str(getattr(node, "title", ""))):
                content_pages.append(page)

    visit(outline, top_level=True)
    if not content_pages:
        return set()
    first_content_page = min(content_pages)
    if first_content_page <= 0:
        return set()
    try:
        is_documenttools_output = (reader.metadata.creator or "") == "DocumentTools"
    except Exception:
        is_documenttools_output = False
    if is_documenttools_output:
        toc_pages = max(1, math.ceil(top_level_count / 40))
        if first_content_page >= toc_pages:
            return set(range(first_content_page - toc_pages, first_content_page))
    for page_index in range(first_content_page):
        if _is_documenttools_toc_page(reader.pages[page_index]):
            return set(range(page_index, first_content_page))
        try:
            text = reader.pages[page_index].extract_text() or ""
        except Exception:
            text = ""
        if _is_toc_label(text):
            return set(range(page_index, first_content_page))
    return set()


def _outline_nodes(reader: Any, removed_pages: set[int]) -> list[_OutlineNode]:
    try:
        outline = reader.outline
    except Exception:
        return []

    def build_level(nodes: list[Any]) -> list[_OutlineNode]:
        result: list[_OutlineNode] = []
        last_node: _OutlineNode | None = None
        for node in nodes:
            if isinstance(node, list):
                if last_node is not None:
                    last_node.children = build_level(node)
                continue
            source_page = _destination_page_number(reader, node)
            if source_page is None:
                continue
            last_node = _OutlineNode(getattr(node, "title", str(node)), source_page, [])
            result.append(last_node)
        return result

    def prune(nodes: list[_OutlineNode]) -> list[_OutlineNode]:
        result: list[_OutlineNode] = []
        for node in nodes:
            node.children = prune(node.children)
            if node.source_page in removed_pages and _is_toc_label(node.title):
                result.extend(node.children)
            else:
                result.append(node)
        return result

    return prune(build_level(outline))


def _mapped_page(source_page: int, page_map: dict[int, int]) -> int | None:
    page = page_map.get(source_page)
    if page is not None:
        return page
    return next((page_map[index] for index in sorted(page_map) if index > source_page), None)


def _copy_outline(nodes: list[_OutlineNode], writer: Any, parent: Any, page_map: dict[int, int]) -> None:
    for node in nodes:
        page = _mapped_page(node.source_page, page_map)
        if page is None:
            continue
        item = writer.add_outline_item(node.title, page, parent=parent)
        _copy_outline(node.children, writer, item, page_map)


def _toc_entries(nodes: list[_OutlineNode], page_map: dict[int, int]) -> tuple[TocEntry, ...]:
    entries: list[TocEntry] = []
    for node in nodes:
        page = _mapped_page(node.source_page, page_map)
        if page is not None:
            entries.append(TocEntry(node.title, page, _toc_entries(node.children, page_map)))
    return tuple(entries)


def _toc_rows(entries: list[TocEntry] | tuple[TocEntry, ...], level: int = 0) -> list[tuple[TocEntry, int]]:
    rows: list[tuple[TocEntry, int]] = []
    for entry in entries:
        rows.append((entry, level))
        rows.extend(_toc_rows(entry.children, level + 1))
    return rows


def _outline_count(nodes: list[_OutlineNode]) -> int:
    return sum(1 + _outline_count(node.children) for node in nodes)


def _create_toc_pdf(entries: list[TocEntry], target: Path) -> int:
    _, _, _, _, A4, pdfmetrics, UnicodeCIDFont, canvas = _require_pdf_packages()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    width, height = A4
    rows_per_page = 40
    rows = _toc_rows(entries)
    pages = max(1, math.ceil(len(rows) / rows_per_page))
    document = canvas.Canvas(str(target), pagesize=A4)
    for page_index in range(pages):
        document.setFont("STSong-Light", 22)
        document.drawString(54, height - 64, "目录")
        document.setStrokeColorRGB(0.75, 0.78, 0.82)
        document.line(54, height - 78, width - 54, height - 78)
        document.setFont("STSong-Light", 11)
        y = height - 110
        for entry, level in rows[page_index * rows_per_page : (page_index + 1) * rows_per_page]:
            title = (entry.title or "未命名")[:80]
            left = 58 + min(level * 18, 108)
            document.drawString(left, y, title)
            document.drawRightString(width - 58, y, str(entry.start_page))
            document.setDash(2, 2)
            document.line(left + min(350 - level * 18, len(title) * 11), y - 2, width - 78, y - 2)
            document.setDash()
            y -= 16
        document.setFont("STSong-Light", 9)
        document.drawCentredString(width / 2, 36, str(page_index + 1))
        document.showPage()
    document.save()
    return pages


def _cover_to_pdf(cover: Path, target: Path) -> None:
    if cover.suffix.lower() == ".pdf":
        target.write_bytes(cover.read_bytes())
        return
    try:
        from PIL import Image  # type: ignore[import-not-found]
        with Image.open(cover) as image:
            image.convert("RGB").save(target, "PDF", resolution=150.0)
    except Exception as exc:
        raise PdfOperationError(f"无法处理封面 {cover.name}：{exc}") from exc


def _normalized_page(page: Any, config: PageSizeConfig, writer: Any) -> Any:
    if config.preserve_original:
        return page
    _, _, Transformation, PageObject, *_ = _require_pdf_packages()
    width, height = config.dimensions()
    source_width = float(page.mediabox.width)
    source_height = float(page.mediabox.height)
    scale = min(width / source_width, height / source_height)
    left = (width - source_width * scale) / 2
    bottom = (height - source_height * scale) / 2
    canvas_page = PageObject.create_blank_page(width=width, height=height)
    canvas_page.merge_transformed_page(page, Transformation().scale(scale).translate(tx=left, ty=bottom))
    return canvas_page


def merge_pdfs(sources: list[str | Path | MergeItem], output: str | Path, *, cover: str | Path | None = None, page_size: PageSizeConfig | None = None, include_toc: bool = True) -> list[TocEntry]:
    if not sources:
        raise PdfOperationError("请至少添加一个 PDF。")
    PdfReader, PdfWriter, *_ = _require_pdf_packages()
    config = page_size or PageSizeConfig()
    items = [item if isinstance(item, MergeItem) else MergeItem(Path(item)) for item in sources]
    readers = []
    source_page_indexes: list[list[int]] = []
    source_outlines: list[list[_OutlineNode]] = []
    for item in items:
        reader = _open_reader(item.path)
        removed_toc_pages = _source_visual_toc_pages(reader)
        page_indexes = [index for index in range(len(reader.pages)) if index not in removed_toc_pages]
        if not page_indexes:
            raise PdfOperationError(f"{item.path.name} 移除目录页后没有可合并的正文页面。")
        item.page_count = len(page_indexes)
        readers.append(reader)
        source_page_indexes.append(page_indexes)
        source_outlines.append(_outline_nodes(reader, removed_toc_pages))

    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="documenttools-merge-") as temporary:
        writer = PdfWriter()
        cover_pages = 0
        if cover:
            cover_pdf = Path(temporary) / "cover.pdf"
            _cover_to_pdf(Path(cover), cover_pdf)
            cover_reader = PdfReader(str(cover_pdf))
            for page in cover_reader.pages:
                writer.add_page(page)
            cover_pages = len(cover_reader.pages)

        toc_row_count = len(items) + sum(_outline_count(outline) for outline in source_outlines)
        toc_pages = max(1, math.ceil(toc_row_count / 40)) if include_toc else 0
        physical_page = cover_pages + toc_pages + 1
        entries: list[TocEntry] = []
        for item, page_indexes, outline in zip(items, source_page_indexes, source_outlines, strict=True):
            source_page_map = {source_index: physical_page + output_index for output_index, source_index in enumerate(page_indexes)}
            entries.append(TocEntry(item.title or item.path.stem, physical_page, _toc_entries(outline, source_page_map)))
            physical_page += len(page_indexes)
        toc_reader = None
        if include_toc:
            toc_path = Path(temporary) / "toc.pdf"
            _create_toc_pdf(entries, toc_path)
            toc_reader = PdfReader(str(toc_path))
            for page in toc_reader.pages:
                from pypdf.generic import BooleanObject, NameObject  # type: ignore[import-not-found]
                page[NameObject("/DocumentToolsToc")] = BooleanObject(True)
                writer.add_page(page)

        page_offset = cover_pages + (len(toc_reader.pages) if toc_reader else 0)
        for item, reader, page_indexes, outline, entry in zip(items, readers, source_page_indexes, source_outlines, entries, strict=True):
            page_map = {source_index: page_offset + output_index for output_index, source_index in enumerate(page_indexes)}
            parent = writer.add_outline_item(entry.title, page_map[page_indexes[0]])
            for source_index in page_indexes:
                writer.add_page(_normalized_page(reader.pages[source_index], config, writer))
            _copy_outline(outline, writer, parent, page_map)
            page_offset += len(page_indexes)
        writer.add_metadata({"/Title": "合并文档", "/Creator": "DocumentTools"})
        with target.open("wb") as handle:
            writer.write(handle)
    return entries
