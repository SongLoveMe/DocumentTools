from __future__ import annotations

from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
# Legacy binary formats are supported because a locally installed Office or WPS
# engine can open them directly.
OFFICE_EXTENSIONS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
PDF_EXTENSIONS = {".pdf"}


def classify_file(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in OFFICE_EXTENSIONS:
        return "office"
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    return "unsupported"


def unique_path(folder: str | Path, stem: str, suffix: str) -> Path:
    """Return a non-existing path without overwriting a prior output."""
    directory = Path(folder)
    candidate = directory / f"{stem}{suffix}"
    sequence = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({sequence}){suffix}"
        sequence += 1
    return candidate
