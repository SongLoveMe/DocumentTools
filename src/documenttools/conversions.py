from __future__ import annotations

import tempfile
from pathlib import Path

from .engines import ConversionEngineError, convert_with_available_engine
from .paths import classify_file, unique_path


class ConversionError(RuntimeError):
    pass


def image_to_pdf(sources: list[str | Path], output: str | Path) -> None:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError("Pillow is not installed in the DocumentTools environment.") from exc
    paths = [Path(source) for source in sources]
    if not paths:
        raise ConversionError("Add at least one image.")
    images = []
    try:
        for path in paths:
            if classify_file(path) != "image":
                raise ConversionError(f"Unsupported image: {path.name}")
            with Image.open(path) as source_image:
                for frame in range(getattr(source_image, "n_frames", 1)):
                    source_image.seek(frame)
                    image = source_image.convert("RGB")
                    images.append(image.copy())
        if not images:
            raise ConversionError("No image pages were available.")
        images[0].save(str(output), "PDF", save_all=True, append_images=images[1:], resolution=150.0)
    finally:
        for image in images:
            image.close()


def convert_file_to_pdf(source: str | Path, output_directory: str | Path, output_stem: str | None = None) -> tuple[Path, str]:
    source_path = Path(source)
    output = unique_path(output_directory, output_stem or source_path.stem, ".pdf")
    file_kind = classify_file(source_path)
    if file_kind == "image":
        image_to_pdf([source_path], output)
        return output, "Pillow"
    if file_kind == "office":
        try:
            engine = convert_with_available_engine(source_path, output)
        except ConversionEngineError as exc:
            raise ConversionError(str(exc)) from exc
        return output, engine
    raise ConversionError(f"Unsupported input format: {source_path.name}")


def convert_pdf_to_word(source: str | Path, output_directory: str | Path, output_stem: str | None = None) -> Path:
    try:
        from pdf2docx import Converter  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError("pdf2docx is not installed. Run pip install -r requirements.lock.") from exc
    source_path = Path(source)
    if classify_file(source_path) != "pdf":
        raise ConversionError("PDF to Word accepts only PDF files.")
    output = unique_path(output_directory, output_stem or source_path.stem, ".docx")
    converter = Converter(str(source_path))
    try:
        converter.convert(str(output))
    except Exception as exc:
        raise ConversionError(f"Could not convert {source_path.name} to Word: {exc}") from exc
    finally:
        converter.close()
    return output


def convert_pdf_to_ppt(source: str | Path, output_directory: str | Path, output_stem: str | None = None) -> Path:
    try:
        import fitz  # type: ignore[import-not-found]
        from pptx import Presentation  # type: ignore[import-not-found]
        from pptx.util import Inches  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError("PDF to PowerPoint support is not installed. Run pip install -r requirements.lock.") from exc
    source_path = Path(source)
    if classify_file(source_path) != "pdf":
        raise ConversionError("PDF to PowerPoint accepts only PDF files.")
    output = unique_path(output_directory, output_stem or source_path.stem, ".pptx")
    try:
        document = fitz.open(source_path)
    except Exception as exc:
        raise ConversionError(f"Could not open {source_path.name}: {exc}") from exc
    if document.needs_pass and not document.authenticate(""):
        document.close()
        raise ConversionError(f"{source_path.name} 需要打开密码，无法猜测密码。")
    if document.page_count == 0:
        document.close()
        raise ConversionError(f"{source_path.name} has no pages.")
    try:
        first = document[0].rect
        presentation = Presentation()
        presentation.slide_width = Inches(13.333)
        presentation.slide_height = int(presentation.slide_width * first.height / first.width)
        blank = presentation.slide_layouts[6]
        with tempfile.TemporaryDirectory(prefix="documenttools-ppt-") as temporary:
            for index, page in enumerate(document):
                raster = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image_path = Path(temporary) / f"page-{index + 1}.png"
                raster.save(str(image_path))
                slide = presentation.slides.add_slide(blank)
                page_ratio = page.rect.width / page.rect.height
                slide_ratio = presentation.slide_width / presentation.slide_height
                if page_ratio >= slide_ratio:
                    width = presentation.slide_width
                    height = int(width / page_ratio)
                    left, top = 0, int((presentation.slide_height - height) / 2)
                else:
                    height = presentation.slide_height
                    width = int(height * page_ratio)
                    left, top = int((presentation.slide_width - width) / 2), 0
                slide.shapes.add_picture(str(image_path), left, top, width=width, height=height)
        presentation.save(str(output))
    finally:
        document.close()
    return output
