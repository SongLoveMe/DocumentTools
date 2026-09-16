"""Tests for local Office/WPS engine detection and COM parameter mapping."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from documenttools import engines as E
from documenttools.office_worker import (
    _convert_excel,
    _convert_powerpoint,
    _convert_word,
    _engine_executable_names,
)

OFFICE_CLSID = "{000209FF-0000-0000-C000-000000000046}"
WPS_CLSID = "{000209FF-0000-4b30-A977-D214852036FF}"
OFFICE_SERVER = r"C:\Program Files\Microsoft Office\Root\Office16\WINWORD.EXE /Automation"
WPS_SERVER = r'"D:\WPS Office\12.1.0\office6\wps.exe" /prometheus /wps /Automation'


def fake_registry(mapping):
    def reader(location, subkey, value_name):
        return mapping.get((location, subkey))

    return reader


def test_detects_office_only():
    mapping = {
        ("HKLM", "Word.Application\\CLSID"): OFFICE_CLSID,
        ("HKLM", f"CLSID\\{OFFICE_CLSID}\\LocalServer32"): OFFICE_SERVER,
    }
    engines = E.detect_local_engines(registry=fake_registry(mapping), version_reader=lambda _p: "16.0")
    assert len(engines) == 1
    assert engines[0].kind is E.EngineKind.OFFICE
    assert engines[0].supports(E.AppKind.WORD)
    assert engines[0].binding_for(E.AppKind.WORD).prog_id == "Word.Application"


def test_detects_wps_only():
    mapping = {
        ("HKCU32", "KWPS.Application\\CLSID"): WPS_CLSID,
        ("HKCU32", f"CLSID\\{WPS_CLSID}\\LocalServer32"): WPS_SERVER,
    }
    engines = E.detect_local_engines(registry=fake_registry(mapping), version_reader=lambda _p: "12.1")
    assert len(engines) == 1
    assert engines[0].kind is E.EngineKind.WPS
    assert engines[0].label() == "WPS Office 12.1"


def test_wps_hijacking_microsoft_progid_is_reported_as_wps():
    """WPS often registers the Microsoft ProgIDs; the server path decides."""
    mapping = {
        ("HKCU", "Word.Application\\CLSID"): WPS_CLSID,
        ("HKCU", f"CLSID\\{WPS_CLSID}\\LocalServer32"): WPS_SERVER,
    }
    engines = E.detect_local_engines(registry=fake_registry(mapping), version_reader=lambda _p: "")
    assert len(engines) == 1
    assert engines[0].kind is E.EngineKind.WPS


def test_no_engines_detected_returns_empty():
    assert E.detect_local_engines(registry=fake_registry({}), version_reader=lambda _p: "") == ()


def test_office_wins_when_both_are_present():
    mapping = {
        ("HKLM", "Word.Application\\CLSID"): OFFICE_CLSID,
        ("HKLM", f"CLSID\\{OFFICE_CLSID}\\LocalServer32"): OFFICE_SERVER,
        ("HKCU32", "KWPS.Application\\CLSID"): WPS_CLSID,
        ("HKCU32", f"CLSID\\{WPS_CLSID}\\LocalServer32"): WPS_SERVER,
    }
    engines = E.detect_local_engines(registry=fake_registry(mapping), version_reader=lambda _p: "1.0")
    kinds = {engine.kind for engine in engines}
    assert kinds == {E.EngineKind.OFFICE, E.EngineKind.WPS}
    assert E.engine_for_app(engines, E.AppKind.WORD).kind is E.EngineKind.OFFICE


def test_default_version_reader_returns_empty_on_bad_path():
    assert E._default_version_reader("") == ""
    assert E._default_version_reader("Z:\\does\\not\\exist.exe") == ""


def test_parse_server_path_handles_quotes_and_arguments():
    assert E._parse_server_path('"C:\\Program Files\\x\\wps.exe" /Automation') == "C:\\Program Files\\x\\wps.exe"
    assert E._parse_server_path("C:\\Office\\WINWORD.EXE /Automation") == "C:\\Office\\WINWORD.EXE"
    assert E._parse_server_path("") == ""


def test_engine_choices_expose_labels():
    mapping = {
        ("HKLM", "Word.Application\\CLSID"): OFFICE_CLSID,
        ("HKLM", f"CLSID\\{OFFICE_CLSID}\\LocalServer32"): OFFICE_SERVER,
    }
    engines = E.detect_local_engines(registry=fake_registry(mapping), version_reader=lambda _p: "16")
    assert E.available_engine_choices(engines) == [("Microsoft Office 16", "office")]


def test_app_kind_for_path():
    assert E.app_kind_for_path("a.docx") is E.AppKind.WORD
    assert E.app_kind_for_path("a.DOC") is E.AppKind.WORD
    assert E.app_kind_for_path("a.xlsx") is E.AppKind.EXCEL
    assert E.app_kind_for_path("a.pptx") is E.AppKind.POWERPOINT
    assert E.app_kind_for_path("a.pdf") is None


def test_worker_command_for_source_checkout(monkeypatch):
    monkeypatch.delenv("DOCUMENTTOOLS_WORKER_PYTHON", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    command = E.worker_command(Path("req.json"), Path("res.json"))
    assert E.WORKER_FLAG in command
    assert command[-2:] == ["req.json", "res.json"]


def test_worker_command_for_frozen_build(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    command = E.worker_command(Path("req.json"), Path("res.json"))
    assert command[0] == sys.executable
    assert command[1:] == [E.WORKER_FLAG, "req.json", "res.json"]


class FakeCollection:
    """Models a COM collection such as ``Documents`` or ``Workbooks``."""

    def __init__(self, app, name):
        object.__setattr__(self, "app", app)
        object.__setattr__(self, "name", name)

    def Open(self, *args, **kwargs):
        self.app.record(f"{self.name}.Open", args, kwargs)
        return FakeItem(self.app, f"{self.name}.Open")

    def __getattr__(self, name):
        def recorder(*args, **kwargs):
            self.app.record(f"{self.name}.{name}", args, kwargs)
            return FakeItem(self.app, f"{self.name}.{name}")

        return recorder


class FakeItem:
    """Models an opened document/workbook/presentation."""

    def __init__(self, app, name):
        object.__setattr__(self, "app", app)
        object.__setattr__(self, "name", name)

    def __getattr__(self, name):
        def recorder(*args, **kwargs):
            self.app.record(f"{self.name}.{name}", args, kwargs)
            return None

        return recorder


class FakeApp:
    """Minimal COM double recording property writes and method calls."""

    COLLECTIONS = ("Documents", "Workbooks", "Presentations")

    def __init__(self):
        object.__setattr__(self, "_props", [])
        object.__setattr__(self, "_calls", [])

    @property
    def properties(self):
        return self._props

    @property
    def calls(self):
        return self._calls

    def record(self, name, args, kwargs):
        self._calls.append((name, args, kwargs))

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._props.append((name, value))

    def __getattr__(self, name):
        if name in self.COLLECTIONS:
            return FakeCollection(self, name)

        def recorder(*args, **kwargs):
            self.record(name, args, kwargs)
            return None

        return recorder

def test_engine_executable_names_cover_all_apps():
    for app_kind in E.AppKind:
        assert _engine_executable_names(E.EngineKind.OFFICE, app_kind)
        assert _engine_executable_names(E.EngineKind.WPS, app_kind)


# --------------------------------------------------------------------------
# Worker lifecycle: engine processes must not outlive the worker
# --------------------------------------------------------------------------


def test_reap_engine_pids_ignores_empty_set(monkeypatch):
    """An empty PID set must be a no-op and never call taskkill."""
    from documenttools import office_worker as W

    killed: list[int] = []
    monkeypatch.setattr(W, "_terminate", killed.append)
    W._reap_engine_pids(set())
    assert killed == []


def test_reap_engine_pids_terminates_survivors(monkeypatch):
    """PIDs that are still alive after the grace period must be terminated."""
    from documenttools import office_worker as W

    killed: list[int] = []
    monkeypatch.setattr(W, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(W, "_terminate", killed.append)
    W._reap_engine_pids({111, 222}, grace=0.0)
    assert sorted(killed) == [111, 222]


def test_reap_engine_pids_leaves_already_exited_processes(monkeypatch):
    """A process that exited during the grace window must not be killed."""
    from documenttools import office_worker as W

    killed: list[int] = []
    monkeypatch.setattr(W, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(W, "_terminate", killed.append)
    W._reap_engine_pids({333}, grace=0.5)
    assert killed == []


def test_worker_reaps_only_pids_it_created(tmp_path, monkeypatch):
    """Only engine processes started by this worker may be terminated.

    A Word/WPS instance the user opened themselves is not in the snapshot
    difference, so it must never be handed to the reaper.
    """
    from documenttools import office_worker as W

    user_pid = 4242
    snapshots = [{user_pid}]
    # First call is the "before" snapshot, then the worker's own engine appears.
    def fake_snapshot(_names):
        if len(snapshots) == 1:
            snapshots.append({user_pid, 9999})
            return {user_pid}
        return {user_pid, 9999}

    monkeypatch.setattr(W, "_snapshot_pids", fake_snapshot)
    # The conversion itself is stubbed to avoid touching a real engine.
    monkeypatch.setattr(
        W, "_CONVERTERS",
        {
            W.AppKind.WORD: lambda app, src, out: (
                out.write_bytes(b"%PDF-1.4\n"), []
            )[1],
        },
    )
    monkeypatch.setattr(W, "_engine_executable_names", lambda _e, _a: ("WINWORD.EXE",))
    monkeypatch.setattr(W, "_set_alerts", lambda app: None)
    monkeypatch.setattr(W, "_disable_macros", lambda app: None)

    reaped: list[set] = []
    monkeypatch.setattr(W, "_reap_engine_pids", lambda pids: reaped.append(set(pids)))
    monkeypatch.setattr(W, "_default_prog_id", lambda _e, _a: "Word.Application")

    class FakeDispatch:
        def __init__(self):
            self.Visible = True

        def Quit(self):
            pass

    import win32com.client
    monkeypatch.setattr(win32com.client, "DispatchEx", lambda _prog: FakeDispatch())

    source = tmp_path / "in.docx"
    source.write_bytes(b"x")
    request = {
        "source": str(source),
        "output": str(tmp_path / "out.pdf"),
        "engine_kind": "office",
        "app_kind": "word",
        "pid_file": str(tmp_path / "pids.json"),
    }
    result = W._convert(request)

    assert result["ok"] is True, result
    assert reaped, "the created engine pid should have been reaped"
    assert user_pid not in reaped[0], "the user's own Word must never be reaped"
    assert reaped[0] == {9999}
