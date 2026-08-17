from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ConversionEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineStatus:
    name: str
    available: bool
    detail: str


class EmbeddedOfficeEngine:
    """Use only the conversion runtime shipped inside DocumentTools."""

    name = "DocumentTools 内置转换运行时"

    @staticmethod
    def executable() -> Path | None:
        package_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parents[2]))
        install_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else package_root
        candidates = [
            package_root / "runtime" / "libreoffice" / "program" / "soffice.exe",
            install_root / "runtime" / "libreoffice" / "program" / "soffice.exe",
            Path(os.environ.get("DOCUMENTTOOLS_RUNTIME", "")) / "program" / "soffice.exe" if os.environ.get("DOCUMENTTOOLS_RUNTIME") else None,
        ]
        return next((path for path in candidates if path and path.is_file()), None)

    @classmethod
    def status(cls) -> EngineStatus:
        executable = cls.executable()
        return EngineStatus(cls.name, executable is not None, str(executable) if executable else "安装包未包含内置转换运行时")

    def convert_to_pdf(self, source: Path, output: Path) -> None:
        executable = self.executable()
        if not executable:
            raise ConversionEngineError("内置转换运行时不可用，请重新安装完整版本的 DocumentTools。")
        with tempfile.TemporaryDirectory(prefix="documenttools-runtime-") as temp_dir:
            completed = subprocess.run(
                [str(executable), "--headless", "--convert-to", "pdf", "--outdir", temp_dir, str(source.resolve())],
                capture_output=True, text=True, check=False,
            )
            converted = Path(temp_dir) / f"{source.stem}.pdf"
            if completed.returncode != 0 or not converted.is_file():
                detail = completed.stderr.strip() or completed.stdout.strip() or "未生成 PDF。"
                raise ConversionEngineError(f"{source.name} 转换失败：{detail}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(converted.read_bytes())


def convert_with_available_engine(source: Path, output: Path) -> str:
    engine = EmbeddedOfficeEngine()
    engine.convert_to_pdf(source, output)
    return engine.name


# Compatibility aliases for callers that display engine status.
LibreOfficeEngine = EmbeddedOfficeEngine
OfficeEngine = EmbeddedOfficeEngine
