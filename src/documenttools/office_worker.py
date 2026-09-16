"""Helper process that drives a local Office/WPS engine over COM automation.

The worker runs in its own process because Office automation can block
indefinitely on a modal dialog.  Isolating each conversion lets the parent
application enforce a timeout and kill the engine without touching the files
already converted, and it guarantees the user's own Word/WPS session is never
disturbed.

The engine is always driven with its window suppressed:

* Word and Excel accept ``Visible = False``.
* PowerPoint rejects ``Visible = False`` for both Microsoft Office and WPS, so
  the presentation is opened with ``WithWindow = False`` instead and the
  application window is never shown.

This module must not import PyQt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .engines import APP_LABELS, AppKind, EngineKind, staged_source

# Office constants.
_WD_EXPORT_FORMAT_PDF = 17
_XL_TYPE_PDF = 0
_PP_SAVE_AS_PDF = 32
_PP_FIXED_FORMAT_PDF = 2
_MACRO_DISABLED = 3


def _write_json(path: Path, payload: dict) -> None:
    """Write ``payload`` atomically so a killed process never truncates it."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _engine_executable_names(engine_kind: EngineKind, app_kind: AppKind) -> tuple[str, ...]:
    if engine_kind is EngineKind.OFFICE:
        return {
            AppKind.WORD: ("WINWORD.EXE",),
            AppKind.EXCEL: ("EXCEL.EXE",),
            AppKind.POWERPOINT: ("POWERPNT.EXE",),
        }[app_kind]
    return {
        AppKind.WORD: ("wps.exe", "wpscloudsvr.exe"),
        AppKind.EXCEL: ("et.exe", "wps.exe"),
        AppKind.POWERPOINT: ("wpp.exe", "wps.exe"),
    }[app_kind]


def _snapshot_pids(names: tuple[str, ...]) -> set[int]:
    """Return the PIDs of currently running processes matching ``names``."""
    if not sys.platform.startswith("win"):  # pragma: no cover - platform guard
        return set()
    try:
        import win32api  # type: ignore[import-not-found]
        import win32con  # type: ignore[import-not-found]
        import win32process  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - dependency guard
        return set()

    wanted = {name.lower() for name in names}
    found: set[int] = set()
    for pid in win32process.EnumProcesses():
        handle = None
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            executable = win32process.GetModuleFileNameEx(handle, 0)
        except Exception:
            continue
        finally:
            if handle is not None:
                try:
                    win32api.CloseHandle(handle)
                except Exception:  # pragma: no cover - defensive
                    pass
        if Path(executable).name.lower() in wanted:
            found.add(int(pid))
    return found


def _pid_alive(pid: int) -> bool:
    """Return True while ``pid`` is still running."""
    try:
        import win32api  # type: ignore[import-not-found]
        import win32con  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - dependency guard
        return False
    handle = None
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except Exception:
        return False
    if handle is None:
        return False
    try:
        return win32api.GetExitCodeProcess(handle) == 259  # STILL_ACTIVE
    except Exception:
        return True
    finally:
        try:
            win32api.CloseHandle(handle)
        except Exception:  # pragma: no cover - defensive
            pass


def _terminate(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
    except Exception:  # pragma: no cover - defensive
        pass


def _reap_engine_pids(pids: set[int], grace: float = 3.0) -> None:
    """Terminate engine processes this worker started but that did not exit.

    Office automation servers often survive ``Quit()`` for a short while.
    Only the PIDs captured right after ``DispatchEx`` are considered, so a
    Word/WPS window the user opened themselves is never affected.
    """
    if not pids or not sys.platform.startswith("win"):
        return
    deadline = time.monotonic() + max(0.0, grace)
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        remaining = {pid for pid in remaining if _pid_alive(pid)}
        if not remaining:
            return
        time.sleep(0.2)
    for pid in remaining:
        _terminate(pid)


def _record_engine_pids(pid_file: Path, pids: set[int]) -> None:
    try:
        _write_json(pid_file, {"pids": sorted(pids)})
    except OSError:  # pragma: no cover - defensive
        pass


def _set_alerts(app) -> None:
    for value in (0, False):
        try:
            app.DisplayAlerts = value
            return
        except Exception:
            continue


def _disable_macros(app) -> None:
    """Best effort macro hardening; WPS may not expose the property."""
    try:
        app.AutomationSecurity = _MACRO_DISABLED
    except Exception:
        pass


def _convert_word(app, source: Path, output: Path) -> list[str]:
    try:
        app.Visible = False
    except Exception:
        pass
    _set_alerts(app)
    _disable_macros(app)

    document = app.Documents.Open(
        str(source), ReadOnly=True, AddToRecentFiles=False, Visible=False
    )
    try:
        document.ExportAsFixedFormat(
            str(output), _WD_EXPORT_FORMAT_PDF, False, 0, 0, 0, 0, 0,
            True, True, 0, True, True, False,
        )
    finally:
        try:
            document.Close(False)
        except Exception:
            pass
    return []


def _convert_excel(app, source: Path, output: Path) -> list[str]:
    try:
        app.Visible = False
    except Exception:
        pass
    _set_alerts(app)
    _disable_macros(app)

    workbook = app.Workbooks.Open(str(source), ReadOnly=True, UpdateLinks=0)
    try:
        # IgnorePrintAreas=False keeps the workbook's own print settings,
        # including page orientation, scaling and repeated title rows.
        workbook.ExportAsFixedFormat(_XL_TYPE_PDF, str(output), 0, False, False)
    finally:
        try:
            workbook.Close(False)
        except Exception:
            pass
    return []


def _convert_powerpoint(app, source: Path, output: Path) -> list[str]:
    _set_alerts(app)
    # Deliberately no Visible assignment: PowerPoint refuses Visible=False for
    # both Microsoft Office and WPS.  WithWindow=False keeps it off screen.
    presentation = app.Presentations.Open(
        str(source), ReadOnly=True, Untitled=False, WithWindow=False
    )
    try:
        try:
            presentation.SaveAs(str(output), _PP_SAVE_AS_PDF)
        except Exception:
            presentation.ExportAsFixedFormat(str(output), _PP_FIXED_FORMAT_PDF)
    finally:
        try:
            presentation.Close()
        except Exception:
            pass
    return []


_CONVERTERS = {
    AppKind.WORD: _convert_word,
    AppKind.EXCEL: _convert_excel,
    AppKind.POWERPOINT: _convert_powerpoint,
}


def _convert(request: dict) -> dict:
    try:
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:
        return {
            "ok": False,
            "message": f"本机 Office/WPS 调用组件不可用：{exc}",
        }

    engine_kind = EngineKind(request["engine_kind"])
    app_kind = AppKind(request["app_kind"])
    source = Path(request["source"])
    output = Path(request["output"])
    pid_file = Path(request["pid_file"]) if request.get("pid_file") else None

    binding = (request.get("prog_id") or "").strip()
    if not binding:
        binding = _default_prog_id(engine_kind, app_kind)

    pythoncom.CoInitialize()
    app = None
    staged: Path | None = None
    cleanup = lambda: None
    created_pids: set[int] = set()
    names: tuple[str, ...] = ()
    try:
        staged, cleanup = staged_source(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()

        names = _engine_executable_names(engine_kind, app_kind)
        before = _snapshot_pids(names)
        app = win32com.client.DispatchEx(binding)
        created_pids = _snapshot_pids(names) - before
        if pid_file is not None:
            _record_engine_pids(pid_file, created_pids)

        converter = _CONVERTERS[app_kind]
        warnings = converter(app, staged, output)
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("本机引擎未生成 PDF 文件。")
        return {
            "ok": True,
            "engine": f"{APP_LABELS[app_kind]}",
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": _describe_failure(exc),
            "warnings": [],
        }
    finally:
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass
        # Office keeps its automation server alive for a while after Quit(), so
        # the PIDs started by this worker are terminated explicitly.  Only the
        # engine processes created here are touched, never the user's own
        # Word/WPS session.
        _reap_engine_pids(created_pids)
        cleanup()
        try:
            pythoncom.CoUninitialize()
        except Exception:  # pragma: no cover - defensive
            pass


def _default_prog_id(engine_kind: EngineKind, app_kind: AppKind) -> str:
    if engine_kind is EngineKind.WPS:
        return {
            AppKind.WORD: "KWPS.Application",
            AppKind.EXCEL: "KET.Application",
            AppKind.POWERPOINT: "KWPP.Application",
        }[app_kind]
    return {
        AppKind.WORD: "Word.Application",
        AppKind.EXCEL: "Excel.Application",
        AppKind.POWERPOINT: "PowerPoint.Application",
    }[app_kind]


def _describe_failure(exc: Exception) -> str:
    """Turn a COM error into a message that is useful for support."""
    message = str(exc).strip() or exc.__class__.__name__
    code = getattr(exc, "hresult", None) or getattr(exc, "args", [None])[0]
    if isinstance(code, int) and code != 0:
        return f"{message}（HRESULT 0x{code & 0xFFFFFFFF:08X}）"
    return message


def run(request_path: str | Path, response_path: str | Path) -> int:
    """Execute one conversion request and write the JSON response."""
    request_file = Path(request_path)
    response_file = Path(response_path)
    try:
        request = json.loads(request_file.read_text(encoding="utf-8"))
    except Exception as exc:
        _write_json(response_file, {"ok": False, "message": f"请求无效：{exc}"})
        return 2

    try:
        result = _convert(request)
    except Exception as exc:  # pragma: no cover - defensive
        result = {"ok": False, "message": _describe_failure(exc)}

    _write_json(response_file, result)
    return 0 if result.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2:
        return 2
    return run(arguments[0], arguments[1])


__all__ = ["main", "run"]
