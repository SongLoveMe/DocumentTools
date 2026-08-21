from __future__ import annotations

import math
import re
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


def _marked_documenttools_toc_pages(reader: Any) -> set[int]:
    """Return the leading run of explicitly marked generated TOC pages."""
    marked = [
        index for index, page in enumerate(reader.pages)
        if bool(page.get("/DocumentToolsToc"))
    ]
    if not marked:
        return set()
    start = marked[0]
    end = start
    while end + 1 in marked:
        end += 1
    return set(range(start, end + 1))


def _destination_page_number(reader: Any, node: Any) -> int | None:
    """Resolve both standard destination objects and DocumentTools' numeric destinations."""
    try:
        raw_page = node.get("/Page")
        if isinstance(raw_page, int):
            return int(raw_page)
    except Exception:
        pass
    try:
        page = reader.get_destination_page_number(node)
    except Exception:
        page = None
    if isinstance(page, int):
        return page
    return None


def _source_visual_toc_pages(reader: Any) -> set[int]:
    """Detect a leading visual TOC when source bookmarks identify later content."""
    # Generated pages carry an explicit marker. This must be checked before
    # outline destinations because older pypdf versions can decode numeric
    # destinations as page 0 even when they point into the body.
    marked_pages = _marked_documenttools_toc_pages(reader)
    if marked_pages:
        return marked_pages

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
    positive_content_pages = [page for page in content_pages if page > 0]
    first_content_page = min(positive_content_pages) if positive_content_pages else None
    if first_content_page is None:
        return set()
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
            if node.source_page in removed_pages:
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

PAGE_NUMBER_POSITIONS = {
    "top-left": "\u9876\u90e8\u5de6\u4fa7", "top-center": "\u9876\u90e8\u5c45\u4e2d", "top-right": "\u9876\u90e8\u53f3\u4fa7",
    "middle-left": "\u4e2d\u90e8\u5de6\u4fa7", "middle-center": "\u4e2d\u90e8\u5c45\u4e2d", "middle-right": "\u4e2d\u90e8\u53f3\u4fa7",
    "bottom-left": "\u5e95\u90e8\u5de6\u4fa7", "bottom-center": "\u5e95\u90e8\u5c45\u4e2d", "bottom-right": "\u5e95\u90e8\u53f3\u4fa7",
}

PAGE_NUMBER_FORMATS = {
    "number": "\u6570\u5b57", "dash": "- \u6570\u5b57 -", "chinese": "\u7b2c \u6570\u5b57 \u9875",
}


@dataclass(frozen=True)
class PageNumberConfig:
    """Presentation settings for page-number overlays."""

    position: str = "bottom-center"
    start_number: int = 1
    number_format: str = "number"
    font_size: float = 10.0
    color: str = "#000000"


def _page_count(source: str | Path) -> int:
    return len(_open_reader(Path(source)).pages)


def parse_page_selection(value: str, page_count: int, *, allow_duplicates: bool = False) -> list[int]:
    """Parse 1-based page numbers and ranges such as ``1-3,5,last``."""
    if page_count < 1:
        raise PdfOperationError("PDF has no pages.")
    text = (value or "").strip().lower().replace(" ", "")
    if not text:
        raise PdfOperationError("Enter a page range, for example 1-3,5.")

    def resolve(token: str) -> int:
        token = token.strip().lower()
        if token in {"last", "end", "\u672b\u9875"}:
            return page_count
        if not token.isdigit():
            raise PdfOperationError(f"Invalid page number: {token}.")
        number = int(token)
        if number < 1 or number > page_count:
            raise PdfOperationError(f"Page {number} is outside 1-{page_count}.")
        return number

    pages: list[int] = []
    for item in text.split(","):
        if not item:
            raise PdfOperationError("Page ranges cannot contain empty items.")
        match = re.fullmatch(r"(.+?)-(.+)", item)
        if match:
            start_page, end_page = resolve(match.group(1)), resolve(match.group(2))
            if start_page > end_page:
                raise PdfOperationError(f"Invalid reversed page range: {item}.")
            pages.extend(range(start_page - 1, end_page))
        else:
            pages.append(resolve(item) - 1)
    if not allow_duplicates and len(set(pages)) != len(pages):
        raise PdfOperationError("Page ranges cannot contain duplicates.")
    return pages


def parse_split_breakpoints(value: str, page_count: int) -> list[int]:
    """Return 1-based pages after which a split should be made."""
    if not (value or "").strip():
        raise PdfOperationError("Enter split breakpoints, for example 3,7.")
    values = [index + 1 for index in parse_page_selection(value, page_count)]
    if values[-1] >= page_count:
        raise PdfOperationError("Split breakpoints must be before the last page.")
    return values


def _unique_directory(parent: Path, stem: str) -> Path:
    candidate = parent / stem
    sequence = 1
    while candidate.exists():
        candidate = parent / f"{stem} ({sequence})"
        sequence += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _default_output(source: Path, suffix: str) -> Path:
    from .paths import unique_path
    return unique_path(source.parent, f"{source.stem}_{suffix}", ".pdf")


def _write_page_indexes(reader: Any, indexes: list[int], output: Path, *, title: str | None = None) -> Path:
    if not indexes:
        raise PdfOperationError("The operation must leave at least one page.")
    _, PdfWriter, *_ = _require_pdf_packages()
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for index in indexes:
        writer.add_page(reader.pages[index])
    writer.add_metadata({"/Title": title or output.stem, "/Creator": "DocumentTools"})
    try:
        with output.open("xb") as handle:
            writer.write(handle)
    except FileExistsError as exc:
        raise PdfOperationError(f"Output already exists: {output.name}") from exc
    return output


def extract_pdf_pages(source: str | Path, pages: str, output: str | Path | None = None) -> Path:
    source_path = Path(source)
    reader = _open_reader(source_path)
    indexes = parse_page_selection(pages, len(reader.pages))
    return _write_page_indexes(reader, indexes, Path(output) if output else _default_output(source_path, "\u63d0\u53d6"))


def delete_pdf_pages(source: str | Path, pages: str, output: str | Path | None = None) -> Path:
    source_path = Path(source)
    reader = _open_reader(source_path)
    removed = set(parse_page_selection(pages, len(reader.pages)))
    indexes = [index for index in range(len(reader.pages)) if index not in removed]
    return _write_page_indexes(reader, indexes, Path(output) if output else _default_output(source_path, "\u5220\u9664\u9875\u9762"))


def reorder_pdf_pages(source: str | Path, page_order: str, output: str | Path | None = None) -> Path:
    source_path = Path(source)
    reader = _open_reader(source_path)
    indexes = parse_page_selection(page_order, len(reader.pages), allow_duplicates=True)
    return _write_page_indexes(reader, indexes, Path(output) if output else _default_output(source_path, "\u91cd\u6392\u5e8f"))


def split_pdf(
    source: str | Path,
    *,
    mode: str = "each",
    pages_per_file: int | None = None,
    breakpoints: str | None = None,
    output_directory: str | Path | None = None,
) -> list[Path]:
    """Split a PDF by page, a fixed page count, or explicit breakpoints."""
    source_path = Path(source)
    reader = _open_reader(source_path)
    count = len(reader.pages)
    target_dir = Path(output_directory) if output_directory else _unique_directory(source_path.parent, f"{source_path.stem}_\u62c6\u5206")
    if output_directory:
        if target_dir.exists():
            raise PdfOperationError(f"Output directory already exists: {target_dir.name}")
        target_dir.mkdir(parents=True, exist_ok=False)

    normalized_mode = mode.lower()
    if normalized_mode == "each":
        groups = [[index] for index in range(count)]
    elif normalized_mode == "count":
        if not pages_per_file or pages_per_file < 1:
            raise PdfOperationError("Pages per file must be greater than zero.")
        groups = [list(range(start, min(start + pages_per_file, count))) for start in range(0, count, pages_per_file)]
    elif normalized_mode == "breakpoints":
        points = parse_split_breakpoints(breakpoints or "", count)
        starts = [0, *points]
        ends = [*points, count]
        groups = [list(range(start, end)) for start, end in zip(starts, ends, strict=True)]
    else:
        raise PdfOperationError("Unknown split mode.")

    results: list[Path] = []
    for group in groups:
        output = target_dir / f"{source_path.stem}_{group[0] + 1:04d}-{group[-1] + 1:04d}.pdf"
        results.append(_write_page_indexes(reader, group, output, title=output.stem))
    return results


def rotate_pdf_pages(source: str | Path, pages: str, direction: str, output: str | Path | None = None) -> Path:
    source_path = Path(source)
    reader = _open_reader(source_path)
    selected = set(parse_page_selection(pages, len(reader.pages)))
    normalized = direction.lower()
    if normalized in {"right", "clockwise", "right 90", "\u987a\u65f6\u9488"}:
        angle = 90
    elif normalized in {"left", "counterclockwise", "left 90", "\u9006\u65f6\u9488"}:
        angle = 270
    else:
        raise PdfOperationError("Direction must be left or right.")
    _, PdfWriter, *_ = _require_pdf_packages()
    target = Path(output) if output else _default_output(source_path, "\u65cb\u8f6c")
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for index, source_page in enumerate(reader.pages):
        page = source_page
        if index in selected:
            page.rotate(angle)
        writer.add_page(page)
    writer.add_metadata({"/Title": target.stem, "/Creator": "DocumentTools"})
    with target.open("xb") as handle:
        writer.write(handle)
    return target


def _rgb_color(value: str) -> tuple[float, float, float]:
    text = (value or "#000000").strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        raise PdfOperationError("Page-number color must use #RRGGBB.")
    return tuple(int(text[index:index + 2], 16) / 255 for index in (0, 2, 4))


def _format_page_number(number: int, number_format: str) -> str:
    if number_format == "dash":
        return f"- {number} -"
    if number_format == "chinese":
        return f"\u7b2c {number} \u9875"
    return str(number)


def _page_number_coordinates(position: str, width: float, height: float, margin: float) -> tuple[float, float, str]:
    if position not in PAGE_NUMBER_POSITIONS:
        raise PdfOperationError("Unknown page-number position.")
    vertical, horizontal = position.split("-", maxsplit=1)
    y = height - margin if vertical == "top" else height / 2 if vertical == "middle" else margin
    x = margin if horizontal == "left" else width / 2 if horizontal == "center" else width - margin
    anchor = "left" if horizontal == "left" else "center" if horizontal == "center" else "right"
    return x, y, anchor


def add_pdf_page_numbers(
    source: str | Path,
    *,
    pages: str | None = None,
    config: PageNumberConfig | None = None,
    output: str | Path | None = None,
) -> Path:
    """Overlay configurable page numbers onto requested PDF pages."""
    source_path = Path(source)
    reader = _open_reader(source_path)
    selected = set(parse_page_selection(pages, len(reader.pages))) if pages else set(range(len(reader.pages)))
    settings = config or PageNumberConfig()
    if settings.start_number < 0:
        raise PdfOperationError("Starting page number cannot be negative.")
    if settings.font_size < 4 or settings.font_size > 72:
        raise PdfOperationError("Font size must be between 4 and 72 pt.")
    color = _rgb_color(settings.color)
    _, PdfWriter, _, _, _, _, _, canvas = _require_pdf_packages()
    target = Path(output) if output else _default_output(source_path, "\u6dfb\u52a0\u9875\u7801")
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    with tempfile.TemporaryDirectory(prefix="documenttools-page-number-") as temporary:
        temporary_path = Path(temporary)
        applied_number = 0
        for index, page in enumerate(reader.pages):
            if index in selected:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                overlay_path = temporary_path / f"page-{index}.pdf"
                overlay = canvas.Canvas(str(overlay_path), pagesize=(width, height))
                overlay.setFillColorRGB(*color)
                overlay.setFont("Helvetica", settings.font_size)
                x, y, anchor = _page_number_coordinates(settings.position, width, height, max(settings.font_size * 1.5, 20))
                text = _format_page_number(settings.start_number + applied_number, settings.number_format)
                if anchor == "left":
                    overlay.drawString(x, y, text)
                elif anchor == "right":
                    overlay.drawRightString(x, y, text)
                else:
                    overlay.drawCentredString(x, y, text)
                overlay.save()
                page.merge_page(_open_reader(overlay_path).pages[0])
                applied_number += 1
            writer.add_page(page)
    writer.add_metadata({"/Title": target.stem, "/Creator": "DocumentTools"})
    with target.open("xb") as handle:
        writer.write(handle)
    return target
