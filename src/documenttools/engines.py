"""Detection and invocation of locally installed Office/WPS engines.

DocumentTools never bundles, ships or launches a document-conversion command
line program.  When the user already has Microsoft Office or WPS installed,
this module discovers it by reading the registry only, then drives it through
COM automation inside a dedicated helper process so that a hung engine can be
killed without taking the application down.

Detection must never start Office or WPS, and conversion must never show a
window on screen.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

WORKER_FLAG = "--documenttools-office-worker"
DEFAULT_TIMEOUT_SECONDS = 120
MIN_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 600

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ConversionEngineError(RuntimeError):
    """Raised when no local engine can produce the requested PDF."""


class EngineKind(str, Enum):
    OFFICE = "office"
    WPS = "wps"


class AppKind(str, Enum):
    WORD = "word"
    EXCEL = "excel"
    POWERPOINT = "powerpoint"


DISPLAY_NAMES = {
    EngineKind.OFFICE: "Microsoft Office",
    EngineKind.WPS: "WPS Office",
}

APP_LABELS = {
    AppKind.WORD: "Word",
    AppKind.EXCEL: "Excel",
    AppKind.POWERPOINT: "PowerPoint",
}

APP_EXTENSIONS = {
    AppKind.WORD: {".doc", ".docx"},
    AppKind.EXCEL: {".xls", ".xlsx"},
    AppKind.POWERPOINT: {".ppt", ".pptx"},
}

# Candidate COM identifiers per application.  Microsoft identifiers are probed
# first, then the WPS specific ones, because WPS may or may not hijack the
# Microsoft identifiers depending on how it was installed.
PROG_IDS = {
    AppKind.WORD: ("Word.Application", "KWPS.Application"),
    AppKind.EXCEL: ("Excel.Application", "KET.Application"),
    AppKind.POWERPOINT: ("PowerPoint.Application", "KWPP.Application"),
}

_WPS_PROGID_PREFIXES = ("KWPS.", "KET.", "KWPP.")

_OFFICE_EXECUTABLES = {
    "winword.exe": AppKind.WORD,
    "excel.exe": AppKind.EXCEL,
    "powerpnt.exe": AppKind.POWERPOINT,
}

# WPS uses one executable which selects the application from its command line
# switches, so all three applications share the same candidate names.
_WPS_EXECUTABLES = frozenset({"wps.exe", "et.exe", "wpp.exe"})
_WPS_PATH_MARKERS = ("kingsoft", "wps office")

# Registry locations searched for a ProgID and the LocalServer32 entry of its
# CLSID.  WPS registers its class data under the 32-bit view, which Windows
# maps onto ``WOW6432Node``, so both views must be probed.  The view is stored
# symbolically because the numeric WOW64 flags are easy to confuse and are
# resolved against ``winreg`` at call time.
_LOCATIONS = (
    ("HKLM", "machine", "default", r"Software\Classes"),
    ("HKLM32", "machine", "32", r"Software\Classes"),
    ("HKCU", "user", "default", r"Software\Classes"),
    ("HKCU32", "user", "32", r"Software\Classes"),
)

_REGISTRY_ROOTS = {"user": "HKEY_CURRENT_USER", "machine": "HKEY_LOCAL_MACHINE"}


@dataclass(frozen=True)
class EngineBinding:
    """A concrete COM server able to handle one application kind."""

    prog_id: str
    clsid: str
    server_path: str
    version: str


@dataclass(frozen=True)
class LocalEngineInfo:
    """Detection result for a single engine family."""

    kind: EngineKind
    display_name: str
    applications: dict[AppKind, EngineBinding]

    @property
    def available(self) -> bool:
        return bool(self.applications)

    @property
    def version(self) -> str:
        for binding in self.applications.values():
            if binding.version:
                return binding.version
        return ""

    def label(self) -> str:
        """Human readable label such as ``Microsoft Office 16.0.20326``."""
        return f"{self.display_name} {self.version}".strip()

    def supports(self, app_kind: AppKind) -> bool:
        return app_kind in self.applications

    def binding_for(self, app_kind: AppKind) -> EngineBinding | None:
        return self.applications.get(app_kind)

    def diagnostics(self) -> list[str]:
        lines = [f"{self.display_name}：{'可用' if self.available else '不可用'}"]
        for app_kind in (AppKind.WORD, AppKind.EXCEL, AppKind.POWERPOINT):
            binding = self.applications.get(app_kind)
            label = APP_LABELS[app_kind]
            if binding is None:
                lines.append(f"  {label}：未检测到")
                continue
            lines.append(f"  {label}：{binding.prog_id}")
            lines.append(f"    CLSID：{binding.clsid or '未知'}")
            lines.append(f"    程序：{binding.server_path or '未知'}")
            lines.append(f"    版本：{binding.version or '未知'}")
        return lines


def _default_registry_reader(location: str, subkey: str, value_name: str) -> str | None:
    """Read one registry value without importing winreg on other platforms."""
    if not sys.platform.startswith("win"):  # pragma: no cover - platform guard
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - platform guard
        return None

    entry = next((item for item in _LOCATIONS if item[0] == location), None)
    if entry is None:
        return None
    _name, hive, view, prefix = entry
    # ``KEY_READ`` already carries the 64-bit view flag on 64-bit Python, so the
    # individual access rights are combined here to allow selecting the 32-bit
    # view that WPS registers its automation servers under.
    access = winreg.KEY_QUERY_VALUE | winreg.KEY_ENUMERATE_SUB_KEYS | winreg.KEY_NOTIFY
    if view == "32":
        access |= winreg.KEY_WOW64_32KEY
    root = getattr(winreg, _REGISTRY_ROOTS[hive])
    try:
        key = winreg.OpenKey(root, f"{prefix}\\{subkey}", 0, access)
    except OSError:
        return None
    try:
        data, _kind = winreg.QueryValueEx(key, value_name)
    except OSError:
        return None
    finally:
        try:
            key.Close()
        except Exception:  # pragma: no cover - defensive
            pass
    return str(data) if data else None


def _parse_server_path(raw: str) -> str:
    """Extract the executable path from a ``LocalServer32`` value."""
    text = (raw or "").strip()
    if not text:
        return ""
    if text.startswith('"'):
        closing = text.find('"', 1)
        return text[1:closing] if closing > 0 else text.strip('"')
    lowered = text.lower()
    for marker in (".exe", ".com"):
        index = lowered.find(marker)
        if index >= 0:
            return text[: index + len(marker)].strip()
    return text.split()[0] if text.split() else text


def _read_file_version(executable: str) -> str:
    try:
        import win32api  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - dependency guard
        return ""
    try:
        info = win32api.GetFileVersionInfo(executable, "\\")
        major_minor = info["FileVersionMS"]
        build_revision = info["FileVersionLS"]
    except Exception:
        return ""
    return f"{major_minor >> 16}.{major_minor & 0xFFFF}.{build_revision >> 16}"


def _default_version_reader(server_path: str) -> str:
    try:
        executable = _parse_server_path(server_path)
    except Exception:  # pragma: no cover - defensive
        return ""
    return _read_file_version(executable) if executable else ""


def _is_wps_server(server_path: str) -> bool:
    name = Path(server_path.replace("/", "\\")).name.lower()
    lowered = server_path.lower()
    if name in _WPS_EXECUTABLES:
        return True
    return name.endswith(".exe") and any(marker in lowered for marker in _WPS_PATH_MARKERS)


def _classify_server(app_kind: AppKind, prog_id: str, server_path: str) -> EngineKind | None:
    """Decide whether a resolved COM server belongs to Office or WPS.

    Classification is driven by the resolved executable rather than the ProgID
    alone, because WPS commonly registers itself under the Microsoft
    identifiers and would otherwise be misreported as Microsoft Office.
    """
    name = Path(server_path.replace("/", "\\")).name.lower()
    if _is_wps_server(server_path):
        return EngineKind.WPS
    if _OFFICE_EXECUTABLES.get(name) is app_kind:
        return EngineKind.OFFICE
    if prog_id.upper().startswith(_WPS_PROGID_PREFIXES):
        return EngineKind.WPS
    return None


def _resolve_binding(
    app_kind: AppKind,
    prog_id: str,
    registry: Callable[[str, str, str], str | None],
    version_reader: Callable[[str], str],
) -> tuple[EngineKind, EngineBinding] | None:
    for location, _hive, _view, _prefix in _LOCATIONS:
        clsid = registry(location, f"{prog_id}\\CLSID", "")
        if not clsid:
            continue
        # The CLSID and its server entry are resolved within one registry
        # location: mixing views would pair a WPS class id with an Office
        # server path and misreport which engine will actually run.
        raw_server = registry(location, f"CLSID\\{clsid}\\LocalServer32", "")
        if not raw_server:
            continue
        server_path = _parse_server_path(raw_server)
        if not server_path:
            continue
        engine_kind = _classify_server(app_kind, prog_id, server_path)
        if engine_kind is None:
            continue
        return engine_kind, EngineBinding(
            prog_id=prog_id,
            clsid=clsid,
            server_path=server_path,
            version=version_reader(server_path),
        )
    return None


def detect_local_engines(
    *,
    registry: Callable[[str, str, str], str | None] | None = None,
    version_reader: Callable[[str], str] | None = None,
) -> tuple[LocalEngineInfo, ...]:
    """Detect installed Office and WPS engines without starting them."""
    if not sys.platform.startswith("win"):
        return ()

    reader = registry or _default_registry_reader
    version_of = version_reader or _default_version_reader

    found: dict[EngineKind, dict[AppKind, EngineBinding]] = {
        EngineKind.OFFICE: {},
        EngineKind.WPS: {},
    }
    for app_kind, prog_ids in PROG_IDS.items():
        for prog_id in prog_ids:
            resolved = _resolve_binding(app_kind, prog_id, reader, version_of)
            if resolved is None:
                continue
            engine_kind, binding = resolved
            found[engine_kind].setdefault(app_kind, binding)

    results: list[LocalEngineInfo] = []
    for engine_kind in (EngineKind.OFFICE, EngineKind.WPS):
        applications = found[engine_kind]
        if not applications:
            continue
        results.append(
            LocalEngineInfo(
                kind=engine_kind,
                display_name=DISPLAY_NAMES[engine_kind],
                applications=dict(applications),
            )
        )
    return tuple(results)


def app_kind_for_path(path: str | Path) -> AppKind | None:
    suffix = Path(path).suffix.lower()
    for app_kind, extensions in APP_EXTENSIONS.items():
        if suffix in extensions:
            return app_kind
    return None


def engine_by_kind(
    engines: tuple[LocalEngineInfo, ...] | list[LocalEngineInfo], kind: EngineKind
) -> LocalEngineInfo | None:
    for info in engines:
        if info.kind is kind:
            return info
    return None


def available_engine_labels(
    engines: tuple[LocalEngineInfo, ...] | list[LocalEngineInfo],
) -> list[str]:
    return [info.label() for info in engines if info.available]


def available_engine_choices(
    engines: tuple[LocalEngineInfo, ...] | list[LocalEngineInfo],
) -> list[tuple[str, str]]:
    """Return ``(label, value)`` pairs for the settings engine combo box."""
    return [(info.label(), info.kind.value) for info in engines if info.available]


def engine_for_app(
    engines: tuple[LocalEngineInfo, ...] | list[LocalEngineInfo],
    app_kind: AppKind,
    *,
    preferred: EngineKind | None = None,
) -> LocalEngineInfo | None:
    """Pick the best engine able to convert ``app_kind``.

    ``preferred`` is honoured first; otherwise Microsoft Office is tried before
    WPS so the higher fidelity engine wins by default.
    """
    checked: set[EngineKind] = set()
    for kind in (preferred, EngineKind.OFFICE, EngineKind.WPS):
        if kind is None or kind in checked:
            continue
        checked.add(kind)
        info = engine_by_kind(engines, kind)
        if info is not None and info.supports(app_kind):
            return info
    return None


def _worker_script() -> Path:
    return Path(__file__).resolve().parents[2] / "main.py"


def worker_command(request_path: Path, response_path: Path) -> list[str]:
    """Return the command line that runs the hidden COM helper process."""
    arguments = [WORKER_FLAG, str(request_path), str(response_path)]
    if getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    python = os.environ.get("DOCUMENTTOOLS_WORKER_PYTHON") or sys.executable
    return [python, str(_worker_script()), *arguments]


def _terminate_process(pid: int) -> None:
    if pid <= 0:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            creationflags=_CREATE_NO_WINDOW,
            check=False,
        )
    except Exception:  # pragma: no cover - defensive
        pass


def _kill_engine_pids(pid_file: Path) -> None:
    try:
        payload = json.loads(pid_file.read_text(encoding="utf-8"))
    except Exception:
        return
    candidates = payload.get("pids", []) if isinstance(payload, dict) else payload
    if not isinstance(candidates, list):
        return
    for raw_pid in candidates:
        try:
            _terminate_process(int(raw_pid))
        except (TypeError, ValueError):
            continue


def _spawn_worker(
    request_path: Path, response_path: Path, timeout_seconds: int, pid_file: Path
) -> dict:
    try:
        process = subprocess.Popen(
            worker_command(request_path, response_path),
            creationflags=_CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ConversionEngineError(f"无法启动本机转换进程：{exc}") from exc

    try:
        _stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process(process.pid)
        try:
            process.communicate(timeout=15)
        except Exception:  # pragma: no cover - defensive
            process.kill()
        _kill_engine_pids(pid_file)
        raise ConversionEngineError(
            f"转换超时（超过 {timeout_seconds} 秒），已强制结束本机转换进程。"
        )

    response: dict = {}
    if response_path.is_file():
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
        except Exception:
            response = {}
    if not response:
        detail = (stderr or b"").decode("utf-8", "replace").strip()
        detail = detail.splitlines()[-1] if detail else "未返回结果"
        raise ConversionEngineError(f"本机转换进程异常退出：{detail}")
    return response


_LAST_WARNINGS: list[str] = []


def consume_last_warnings() -> list[str]:
    """Return and clear warnings produced by the previous conversion."""
    warnings = list(_LAST_WARNINGS)
    _LAST_WARNINGS.clear()
    return warnings


def convert_with_local_engine(
    source: str | Path,
    output: str | Path,
    *,
    engine_kind: EngineKind,
    app_kind: AppKind,
    prog_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    spawn: Callable[[Path, Path, int, Path], dict] | None = None,
) -> str:
    """Convert one Office document to PDF through a local Office/WPS engine.

    Returns the label of the engine that produced the file.  Raises
    :class:`ConversionEngineError` on any failure, including a timeout.
    """
    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if not source_path.is_file():
        raise ConversionEngineError(f"源文件不存在：{source_path}")

    timeout = max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, int(timeout_seconds)))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="documenttools-worker-") as temporary:
        workspace = Path(temporary)
        request_path = workspace / "request.json"
        response_path = workspace / "response.json"
        pid_file = workspace / "engine-pids.json"
        request = {
            "source": str(source_path),
            "output": str(output_path),
            "engine_kind": engine_kind.value,
            "app_kind": app_kind.value,
            "prog_id": prog_id or "",
            "pid_file": str(pid_file),
        }
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

        runner = spawn or _spawn_worker
        response = runner(request_path, response_path, timeout, pid_file)

    if not response.get("ok"):
        message = str(response.get("message") or "本机引擎转换失败")
        raise ConversionEngineError(message)

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise ConversionEngineError("本机引擎未生成 PDF 输出。")
    if not _is_valid_pdf(output_path):
        _discard(output_path)
        raise ConversionEngineError("本机引擎生成的文件不是有效的 PDF。")

    _LAST_WARNINGS.clear()
    _LAST_WARNINGS.extend(str(item) for item in response.get("warnings") or [])
    return str(response.get("engine") or DISPLAY_NAMES[engine_kind])


def _is_valid_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                return False
    except OSError:
        return False
    try:
        import fitz  # type: ignore[import-not-found]

        with fitz.open(path) as document:
            return document.page_count > 0
    except Exception:
        return True


def _discard(path: Path) -> None:
    try:
        path.unlink()
    except OSError:  # pragma: no cover - defensive
        pass


def staged_source(source: str | Path) -> tuple[Path, Callable[[], None]]:
    """Return a locally readable copy of ``source`` when it may be untrusted.

    Files on network shares or carrying the Mark-of-the-Web alternate data
    stream can open in Office Protected View, which blocks headless conversion.
    A plain local copy drops both conditions.
    """
    source_path = Path(source)
    text = str(source_path)
    needs_copy = text.startswith("\\\\")
    if not needs_copy and sys.platform.startswith("win") and source_path.exists():
        try:
            needs_copy = os.path.exists(text + ":Zone.Identifier")
        except OSError:  # pragma: no cover - defensive
            needs_copy = False
    if not needs_copy:
        return source_path, lambda: None

    staging = Path(tempfile.mkdtemp(prefix="documenttools-staging-"))
    target = staging / source_path.name
    try:
        target.write_bytes(source_path.read_bytes())
    except OSError as exc:
        raise ConversionEngineError(f"无法读取源文件：{exc}") from exc

    def cleanup() -> None:
        try:
            target.unlink()
        except OSError:
            pass
        try:
            staging.rmdir()
        except OSError:
            pass

    return target, cleanup


__all__ = [
    "APP_EXTENSIONS",
    "APP_LABELS",
    "AppKind",
    "ConversionEngineError",
    "DEFAULT_TIMEOUT_SECONDS",
    "DISPLAY_NAMES",
    "EngineBinding",
    "EngineKind",
    "LocalEngineInfo",
    "MAX_TIMEOUT_SECONDS",
    "MIN_TIMEOUT_SECONDS",
    "PROG_IDS",
    "WORKER_FLAG",
    "app_kind_for_path",
    "available_engine_choices",
    "available_engine_labels",
    "consume_last_warnings",
    "convert_with_local_engine",
    "detect_local_engines",
    "engine_by_kind",
    "engine_for_app",
    "staged_source",
    "worker_command",
]
