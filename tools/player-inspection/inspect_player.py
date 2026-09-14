#!/usr/bin/env python3
"""Read-only UIA and initial-playlist inspection for a packaged Nulloy build.

This runner launches one validated portable package with three generated WAV files,
reads only its owned Qt UIA tree, and cleans up only the Popen-owned process and
its own temporary files.  Default mode never invokes a UI control or changes the
playlist; the explicit legacy context-menu mode uses UIA SelectionItem selection
and one guarded keyboard or real-pointer context request, and never invokes a
menu item.  The separate bounded context mode performs its UIA and keyboard-
reason context request in a supervised worker.  Real-pointer input requires the
separate explicit allow flag.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from ctypes import wintypes
from typing import Any, Sequence


_POINTER_SPEC = importlib.util.spec_from_file_location(
    "nulloy_owned_pointer", Path(__file__).with_name("owned_pointer.py")
)
if _POINTER_SPEC is None or _POINTER_SPEC.loader is None:
    raise RuntimeError("cannot load owned pointer transport")
owned_pointer = importlib.util.module_from_spec(_POINTER_SPEC)
_POINTER_SPEC.loader.exec_module(owned_pointer)

_SUPERVISOR_SPEC = importlib.util.spec_from_file_location(
    "nulloy_uia_supervisor", Path(__file__).with_name("uia_supervisor.py")
)
if _SUPERVISOR_SPEC is None or _SUPERVISOR_SPEC.loader is None:
    raise RuntimeError("cannot load bounded UIA supervisor")
uia_supervisor = importlib.util.module_from_spec(_SUPERVISOR_SPEC)
sys.modules[_SUPERVISOR_SPEC.name] = uia_supervisor
_SUPERVISOR_SPEC.loader.exec_module(uia_supervisor)

SOURCE_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
FIXTURE_COUNT = 3
FIXTURE_SECONDS = 30
PLAYLIST_CLASS = "NPlaylistWidget"
PLAYLIST_AUTOMATION_ID = "QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget"
WM_CONTEXTMENU = 0x007B
_MENU_LABELS = ("Move To Trash", "Remove From Playlist")
_MENU_AUTOMATION_IDS = {
    "Move To Trash": "QtSingleApplication.QMenu.MoveToTrashAction",
    "Remove From Playlist": "QtSingleApplication.QMenu.RemoveFromPlaylistAction",
}
_CONTEXT_QMENU_CLASS = "QMenu"
_CONTEXT_QMENU_AUTOMATION_ID = "QtSingleApplication.QMenu"
_SHORTCUT_KEY = r"(?:Del|Delete|Backspace|Ins|Insert|Home|End|PageUp|PageDown|Left|Right|Up|Down|F(?:[1-9]|1[0-2])|[A-Za-z0-9])"
_SHORTCUT_RE = re.compile(
    rf"(?:(?:Ctrl|Alt|Shift|Meta|Win)\+)*{_SHORTCUT_KEY}$"
)


class ContractError(ValueError):
    """The package or observed read-only state violates the contract."""


class BlockedError(RuntimeError):
    """The platform or runner cannot safely perform this inspection."""


def _load_validator_functions() -> tuple[Any, Any]:
    """Load only the existing package validator and fixture-generator functions."""
    source = Path(__file__).resolve().parents[1] / "trash-probe" / "probe.py"
    name = "nulloy_trash_probe_validator"
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise BlockedError(f"cannot load package validator: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.extract_and_validate, module.make_wav_fixtures


extract_and_validate, _make_wav_fixtures = _load_validator_functions()


def is_windows_native() -> bool:
    return os.name == "nt"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_source_hashes() -> dict[str, str]:
    """Hash every runtime helper before package/temp allocation begins."""
    names = ("inspect_player.py", "uia_supervisor.py", "uia_worker.py", "owned_pointer.py")
    return {name: _sha256(Path(__file__).with_name(name)) for name in names}


def parse_source_sha(value: str) -> str:
    if not SOURCE_SHA_RE.fullmatch(value or ""):
        raise ContractError("--source-sha must be exactly 40 hexadecimal characters")
    return value


def parse_archive_sha(value: str) -> str:
    if not SHA256_RE.fullmatch(value or ""):
        raise ContractError("--archive-sha256 must be exactly 64 hexadecimal characters")
    return value.lower()


def fixture_seconds(path: Path) -> int:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        frames = source.getnframes()
    if rate <= 0 or frames % rate:
        raise ContractError(f"fixture duration is not an integral number of seconds: {path}")
    return frames // rate


def _duration_label(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def expected_playlist_rows(paths: Sequence[Path], durations: Sequence[int]) -> list[str]:
    if len(paths) != FIXTURE_COUNT or len(paths) != len(durations):
        raise ContractError("expected exactly three fixture paths and durations")
    names = [path.name for path in paths]
    if len(set(names)) != len(names):
        raise ContractError("fixture basenames are not unique")
    return [f"{name} ({_duration_label(int(duration))})" for name, duration in zip(names, durations)]


def exact_playlist_rows(actual: Sequence[str], expected: Sequence[str]) -> bool:
    actual_list, expected_list = list(actual), list(expected)
    if len(expected_list) != len(set(expected_list)):
        raise ContractError(f"expected playlist labels are duplicated: {expected_list!r}")
    if actual_list != expected_list:
        raise ContractError(
            f"playlist rows differ exactly: expected={expected_list!r}, actual={actual_list!r}"
        )
    return True


def make_fixtures(directory: Path, run_id: str) -> list[Path]:
    """Use the existing generator while pinning this probe's required 30 seconds."""
    validator_name = "nulloy_trash_probe_validator"
    validator = sys.modules[validator_name]
    old_seconds = validator.FIXTURE_SECONDS
    validator.FIXTURE_SECONDS = FIXTURE_SECONDS
    try:
        paths = _make_wav_fixtures(directory, run_id)
    finally:
        validator.FIXTURE_SECONDS = old_seconds
    if len(paths) != FIXTURE_COUNT or any(fixture_seconds(path) != FIXTURE_SECONDS for path in paths):
        raise ContractError("fixture generator did not produce three 30-second WAVs")
    return paths


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _wait_for(predicate: Any, timeout: float, description: str) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    detail = f": {last_error!r}" if last_error else ""
    raise RuntimeError(f"timed out waiting for {description}{detail}")


def _window_text(control: Any) -> str:
    try:
        return str(control.window_text())
    except Exception:
        return str(getattr(getattr(control, "element_info", None), "name", ""))


def _as_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return list(value)
    except TypeError:
        return str(value)


def _control_record(control: Any) -> dict[str, Any]:
    info = control.element_info
    patterns: dict[str, bool] = {}
    for name in ("iface_invoke", "iface_expand_collapse", "iface_selection_item"):
        try:
            patterns[name.removeprefix("iface_")] = getattr(control, name, None) is not None
        except Exception:
            patterns[name.removeprefix("iface_")] = False
    return {
        "pid": getattr(info, "process_id", None),
        "class_name": getattr(info, "class_name", ""),
        "control_type": getattr(info, "control_type", ""),
        "automation_id": getattr(info, "automation_id", ""),
        "nativehandle": getattr(info, "handle", None),
        "runtimeID": _as_json_value(getattr(info, "runtime_id", None)),
        "name": getattr(info, "name", ""),
        "text": _window_text(control),
        "patterns_available": patterns,
    }


def _row_fullname(row: Any) -> str:
    """Return the exact UIA row name without consulting legacy MSAA."""
    info_name = str(getattr(row.element_info, "name", "") or "")
    return info_name or _window_text(row)


def _selection_pattern(row: Any) -> Any:
    try:
        pattern = getattr(row, "iface_selection_item", None)
    except Exception as exc:
        raise BlockedError(f"UIA SelectionItem pattern is unavailable: {exc!r}") from exc
    if pattern is None:
        raise BlockedError(f"row lacks UIA SelectionItem pattern: {_row_fullname(row)!r}")
    return pattern


def _selection_state(row: Any) -> bool:
    pattern = _selection_pattern(row)
    try:
        value = getattr(pattern, "CurrentIsSelected")
    except Exception as exc:
        raise BlockedError(f"cannot read UIA SelectionItem state: {exc!r}") from exc
    return _canonical_bool(value, "SelectionItem.CurrentIsSelected", _row_fullname(row))


def _canonical_bool(value: Any, field: str, owner: str) -> bool:
    """Accept only the 0/1 values exposed by native BOOL properties."""
    if type(value) not in (bool, int) or value not in (0, 1):
        raise ContractError(
            f"{field} has unsupported value {value!r} ({type(value).__name__}) for {owner!r}"
        )
    return bool(value)


def _validate_row_identity(row: Any, expected_name: str, process_pid: int) -> Any:
    info = row.element_info
    if getattr(info, "process_id", None) != process_pid:
        raise ContractError(f"playlist row PID mismatch for {expected_name!r}")
    fullname = _row_fullname(row)
    text = _window_text(row)
    if fullname != expected_name or text != expected_name:
        raise ContractError(
            f"playlist row fullname mismatch: expected={expected_name!r}, fullname={fullname!r}, text={text!r}"
        )
    try:
        element = getattr(info, "element", None)
    except Exception as exc:
        raise BlockedError(f"native UIA row element is unavailable: {exc!r}") from exc
    if element is None:
        raise BlockedError(f"native UIA row element is unavailable for {expected_name!r}")
    return element


def _row_focus_evidence(row: Any, expected_name: str, process_pid: int, element: Any) -> dict[str, Any]:
    try:
        value = getattr(element, "CurrentHasKeyboardFocus")
    except Exception as exc:
        raise BlockedError(f"cannot read native UIA keyboard focus state: {exc!r}") from exc
    focused = _canonical_bool(value, "CurrentHasKeyboardFocus", expected_name)
    if not focused:
        raise ContractError(f"owned playlist row does not have keyboard focus: {expected_name!r}")
    return {
        "name": expected_name,
        "pid": process_pid,
        "has_keyboard_focus": True,
        "source": "row.element_info.element.CurrentHasKeyboardFocus",
    }


def focus_owned_row(row: Any, expected_name: str, process_pid: int) -> dict[str, Any]:
    """Set focus through the direct native UIA element, never the wrapper fallback."""
    element = _validate_row_identity(row, expected_name, process_pid)
    try:
        set_focus = getattr(element, "SetFocus", None)
    except Exception as exc:
        raise BlockedError(f"native UIA row SetFocus is unavailable: {exc!r}") from exc
    if not callable(set_focus):
        raise BlockedError(f"native UIA row SetFocus is unavailable for {expected_name!r}")
    try:
        set_focus()
    except Exception as exc:
        raise BlockedError(f"native UIA row SetFocus failed: {exc!r}") from exc
    return _row_focus_evidence(row, expected_name, process_pid, element)


def verify_owned_row_focus(row: Any, expected_name: str, process_pid: int) -> dict[str, Any]:
    """Re-read direct native focus after selection, without changing focus again."""
    element = _validate_row_identity(row, expected_name, process_pid)
    return _row_focus_evidence(row, expected_name, process_pid, element)


def fresh_pointer_target_context(
    playlist: Any,
    main_window: Any,
    expected_rows: Sequence[str],
    process_pid: int,
    point: Any,
) -> dict[str, Any]:
    """Re-read the exact playlist target without changing selection or retargeting."""
    rows = list(playlist.descendants(control_type="ListItem"))
    if len(rows) != FIXTURE_COUNT or len(expected_rows) != FIXTURE_COUNT:
        raise ContractError("pointer boundary requires exactly three playlist rows")
    exact_playlist_rows([_window_text(row) for row in rows], expected_rows)
    for row, expected_name in zip(rows, expected_rows):
        _validate_row_identity(row, expected_name, process_pid)
    selected = [
        _row_fullname(row)
        for row in rows
        if _selection_state(row)
    ]
    if selected != list(expected_rows[:2]):
        raise ContractError(f"pointer boundary selection changed: {selected!r}")
    row_rect = rows[0].rectangle()
    main_rect = main_window.rectangle()
    if not owned_pointer._point_inside(point, row_rect) or not owned_pointer._point_inside(point, main_rect):
        raise BlockedError("original pointer point is outside freshly-read target geometry")
    return {
        "rows": rows,
        "row": rows[0],
        "row_rect": row_rect,
        "main_rect": main_rect,
        "selected": selected,
    }


def select_exact_rows(rows: Sequence[Any], expected: Sequence[str], process_pid: int) -> list[str]:
    """Select exactly the first two already-recognized rows through SelectionItem only."""
    if len(rows) != len(expected) or len(expected) != FIXTURE_COUNT:
        raise ContractError("selection requires exactly the three recognized playlist rows")
    observed: list[str] = []
    for row, expected_name in zip(rows, expected):
        info = row.element_info
        if getattr(info, "process_id", None) != process_pid:
            raise ContractError(f"playlist row PID mismatch for {expected_name!r}")
        fullname = _row_fullname(row)
        text = _window_text(row)
        if fullname != expected_name or text != expected_name:
            raise ContractError(
                f"playlist row fullname mismatch: expected={expected_name!r}, fullname={fullname!r}, text={text!r}"
            )
        _selection_state(row)
        observed.append(fullname)
    if observed != list(expected):
        raise ContractError(f"playlist row fullnames differ before selection: {observed!r}")

    first_pattern = _selection_pattern(rows[0])
    second_pattern = _selection_pattern(rows[1])
    try:
        first_pattern.Select()
    except Exception as exc:
        raise BlockedError(f"UIA SelectionItem.Select failed: {exc!r}") from exc
    if not _selection_state(rows[0]):
        raise ContractError("first playlist row was not selected by SelectionItem.Select")
    try:
        second_pattern.AddToSelection()
    except Exception as exc:
        raise BlockedError(f"UIA SelectionItem.AddToSelection failed: {exc!r}") from exc

    selected: list[str] = []
    for row, expected_name in zip(rows, expected):
        if _selection_state(row):
            selected.append(_row_fullname(row))
    if selected != list(expected[:2]):
        raise ContractError(f"selection was not exactly the first two rows: {selected!r}")
    return selected


def keyboard_context_message_args(
    main_window: Any,
    process_identity: dict[str, Any],
    root_identity: dict[str, Any],
    executable: str | Path,
) -> tuple[int, int, int, int]:
    """Validate the owned native root and produce the keyboard WM_CONTEXTMENU payload."""
    info = main_window.element_info
    hwnd = int(getattr(info, "handle", 0) or 0)
    if not hwnd:
        raise BlockedError("owned main window has no native HWND")
    if getattr(info, "process_id", None) != process_identity["pid"]:
        raise ContractError("owned main window PID does not match Popen identity")
    if root_identity.get("pid") != process_identity["pid"]:
        raise ContractError("WM_CONTEXTMENU root HWND PID does not match Popen identity")
    try:
        same_create_time = float(root_identity.get("create_time")) == float(process_identity["create_time"])
    except (TypeError, ValueError) as exc:
        raise ContractError("WM_CONTEXTMENU root HWND create-time is not valid") from exc
    if not same_create_time:
        raise ContractError("WM_CONTEXTMENU root HWND create-time does not match Popen identity")
    if not _same_path(root_identity.get("executable", ""), executable):
        raise ContractError("WM_CONTEXTMENU root HWND executable does not match package executable")
    # Win32 documents -1 as the keyboard-originating LPARAM sentinel.
    return hwnd, WM_CONTEXTMENU, hwnd, -1


def _post_message_windows(hwnd: int, message: int, wparam: int, lparam: int) -> bool:
    if not is_windows_native():
        raise BlockedError("WM_CONTEXTMENU transport requires native Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    post_message = user32.PostMessageW
    post_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    post_message.restype = wintypes.BOOL
    return bool(post_message(hwnd, message, wparam, lparam))


def post_keyboard_context_menu(
    main_window: Any,
    process_identity: dict[str, Any],
    root_identity: dict[str, Any],
    executable: str | Path,
    post_message: Any | None = None,
) -> None:
    """Post exactly one keyboard-reason WM_CONTEXTMENU to the owned root HWND."""
    args = keyboard_context_message_args(main_window, process_identity, root_identity, executable)
    transport = post_message or _post_message_windows
    if not transport(*args):
        raise BlockedError("PostMessageW(WM_CONTEXTMENU) failed")


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _portable_config(root: Path, executable: Path) -> Path:
    data = root / "Data"
    data.mkdir(parents=True, exist_ok=True)
    config = data / f"{executable.stem}.cfg"
    config.write_text(
        "SettingsVersion=0.8\n"
        "StartPaused=true\n"
        "RestorePlaylist=false\n"
        "SingleInstance=false\n"
        "EnqueueFiles=false\n"
        "PlayEnqueued=false\n",
        encoding="utf-8",
    )
    return config


def _safe_environment() -> dict[str, str]:
    environment = os.environ.copy()
    system_root = Path(environment.get("SystemRoot", r"C:\\Windows"))
    environment["PATH"] = str(system_root / "System32")
    for key in list(environment):
        if key.startswith(("QT_", "QML", "GST", "MSYS", "MINGW")):
            environment.pop(key, None)
    environment["GST_PLUGIN_FEATURE_RANK"] = (
        "directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0"
    )
    return environment


def _process_identity(process: Any, psutil: Any, executable: Path) -> dict[str, Any]:
    native = psutil.Process(process.pid)
    identity = {
        "pid": process.pid,
        "create_time": float(native.create_time()),
        "executable": str(native.exe()),
    }
    if not _same_path(identity["executable"], executable):
        raise ContractError("Popen process executable does not match the packaged executable")
    return identity


def _verify_process_identity(process: Any, psutil: Any, identity: dict[str, Any], executable: Path) -> None:
    if process.poll() is not None:
        raise RuntimeError(f"packaged player exited with {process.returncode}")
    current = psutil.Process(identity["pid"])
    if float(current.create_time()) != identity["create_time"] or not _same_path(current.exe(), executable):
        raise ContractError("packaged player PID/create-time/fullpath identity changed")


def _owned_main(desktop: Any, identity: dict[str, Any]) -> Any:
    matches = []
    for window in desktop.windows():
        info = window.element_info
        if (
            getattr(info, "process_id", None) == identity["pid"]
            and getattr(info, "class_name", "") == "NMainWindow"
            and getattr(info, "control_type", "") == "Pane"
            and _is_visible(window)
        ):
            matches.append(window)
    if len(matches) != 1:
        raise RuntimeError(f"owned visible NMainWindow Pane count is {len(matches)}, expected one")
    return matches[0]


def _playlist(main_window: Any) -> Any:
    matches = []
    for control in main_window.descendants(control_type="List"):
        info = control.element_info
        if (
            getattr(info, "class_name", "") == PLAYLIST_CLASS
            and getattr(info, "automation_id", "") == PLAYLIST_AUTOMATION_ID
        ):
            matches.append(control)
    if len(matches) != 1:
        raise RuntimeError(f"owned Qt playlist List count is {len(matches)}, expected one")
    return matches[0]


def _tree(main_window: Any) -> list[dict[str, Any]]:
    return [_control_record(control) for control in [main_window, *main_window.descendants()]]


def _menu_label(control: Any) -> str:
    raw = str(getattr(control.element_info, "name", "") or _window_text(control)).strip()
    if raw in _MENU_LABELS:
        return raw
    if "\t" not in raw:
        return ""
    label, shortcut = raw.split("\t", 1)
    label, shortcut = label.strip(), shortcut.strip()
    return label if label in _MENU_LABELS and _SHORTCUT_RE.fullmatch(shortcut) else ""


def recognize_context_menu_items(items: Sequence[Any]) -> list[dict[str, Any]]:
    """Recognize two distinct exact menu entries without invoking either one."""
    recognized: list[dict[str, Any]] = []
    for item in items:
        info = item.element_info
        label = _menu_label(item)
        if label and getattr(info, "automation_id", "") == _MENU_AUTOMATION_IDS[label]:
            recognized.append({"label": label, "record": _control_record(item)})
    counts = {label: sum(entry["label"] == label for entry in recognized) for label in _MENU_LABELS}
    if any(count != 1 for count in counts.values()):
        raise ContractError(f"context menu entries were not distinct exact matches: {counts!r}")
    runtime_ids = [json.dumps(entry["record"].get("runtimeID"), sort_keys=True, default=str) for entry in recognized]
    if len(runtime_ids) != len(set(runtime_ids)):
        raise ContractError("context menu entries share a runtime ID")
    return recognized


def _runtime_key(control: Any) -> str:
    info = control.element_info
    runtime_id = getattr(info, "runtime_id", None)
    if runtime_id is not None:
        return "runtimeID:" + json.dumps(_as_json_value(runtime_id), sort_keys=True, default=str)
    return f"handle:{getattr(info, 'handle', None)!r}"


def _visibility_owner(control: Any) -> str:
    try:
        info = control.element_info
        return (
            f"{getattr(info, 'control_type', '') or type(control).__name__} "
            f"{getattr(info, 'name', '')!r} handle={getattr(info, 'handle', None)!r}"
        )
    except Exception:
        return type(control).__name__


def _is_visible(control: Any) -> bool:
    owner = _visibility_owner(control)
    try:
        value = control.is_visible()
    except Exception as exc:
        raise ContractError(f"visibility check failed for {owner}: {exc!r}") from exc
    return _canonical_bool(value, "visibility", owner)


_CONTEXT_DIAGNOSTIC_MAX_SURFACES = 32
_CONTEXT_DIAGNOSTIC_MAX_DESCENDANTS = 512


def _owned_top_level_windows(desktop: Any, process_pid: int) -> list[Any]:
    """Return only deduplicated top-level UIA surfaces owned by the player."""
    windows: list[Any] = []
    seen: set[str] = set()
    for window in desktop.windows():
        info = window.element_info
        if getattr(info, "process_id", None) != process_pid:
            continue
        key = _runtime_key(window)
        if key in seen:
            continue
        seen.add(key)
        windows.append(window)
    return windows


def _owned_context_menu_candidates(desktop: Any, main_window: Any, process_pid: int) -> list[Any]:
    """Search owned top-level surfaces and their owned descendants only."""
    surfaces = _owned_top_level_windows(desktop, process_pid)
    main_info = main_window.element_info
    if getattr(main_info, "process_id", None) == process_pid:
        main_key = _runtime_key(main_window)
        if all(_runtime_key(surface) != main_key for surface in surfaces):
            surfaces.append(main_window)

    candidates: list[Any] = []
    for surface in surfaces:
        candidates.append(surface)
        candidates.extend(
            control
            for control in surface.descendants()
            if getattr(control.element_info, "process_id", None) == process_pid
        )
    return candidates


def _is_observed_qmenu_pane(control: Any) -> bool:
    info = control.element_info
    if (
        getattr(info, "control_type", "") != "Pane"
        or getattr(info, "class_name", "") != _CONTEXT_QMENU_CLASS
        or getattr(info, "automation_id", "") != _CONTEXT_QMENU_AUTOMATION_ID
    ):
        return False
    handle = getattr(info, "handle", None)
    return isinstance(handle, int) and not isinstance(handle, bool) and handle > 0


def _validate_observed_qmenu_hwnd(
    control: Any,
    process_pid: int,
    process_identity: dict[str, Any] | None,
    psutil: Any | None,
    executable: Path | None,
) -> None:
    """Validate the alternate QMenu root's native HWND when identity is available."""
    if process_identity is None or psutil is None or executable is None:
        return
    handle = int(control.element_info.handle)
    native = _window_process_identity(handle, psutil)
    if (
        native.get("pid") != process_pid
        or float(native.get("create_time")) != float(process_identity["create_time"])
        or not _same_path(native.get("executable", ""), executable)
    ):
        raise ContractError("observed QMenu HWND identity does not match the owned player")


def _owned_context_menus(
    desktop: Any,
    main_window: Any,
    process_pid: int,
    *,
    process_identity: dict[str, Any] | None = None,
    psutil: Any | None = None,
    executable: Path | None = None,
) -> list[Any]:
    candidates = _owned_context_menu_candidates(desktop, main_window, process_pid)
    menus: list[Any] = []
    seen: set[str] = set()
    for control in candidates:
        info = control.element_info
        is_menu = (
            getattr(info, "process_id", None) == process_pid
            and getattr(info, "control_type", "") == "Menu"
            and _is_visible(control)
        )
        is_qmenu = (
            getattr(info, "process_id", None) == process_pid
            and _is_observed_qmenu_pane(control)
            and _is_visible(control)
        )
        if not (is_menu or is_qmenu):
            continue
        if is_qmenu:
            _validate_observed_qmenu_hwnd(control, process_pid, process_identity, psutil, executable)
        key = _runtime_key(control)
        if key not in seen:
            seen.add(key)
            menus.append(control)
    if len(menus) > 1:
        raise ContractError(f"unexpected count of owned visible context-menu roots: {len(menus)}")
    return menus


def _owned_surface_diagnostics(desktop: Any, process_pid: int) -> dict[str, Any]:
    """Bounded diagnostics for owned top-level UIA surfaces, never foreign content."""
    surfaces: list[dict[str, Any]] = []
    owned_windows = _owned_top_level_windows(desktop, process_pid)
    for surface in owned_windows[:_CONTEXT_DIAGNOSTIC_MAX_SURFACES]:
        record: dict[str, Any] = {"surface": _control_record(surface)}
        try:
            all_descendants = list(surface.descendants())
        except Exception as exc:
            record.update({"descendants": [], "descendants_error": repr(exc)})
        else:
            owned_descendants = [
                control
                for control in all_descendants
                if getattr(control.element_info, "process_id", None) == process_pid
            ]
            record.update(
                {
                    "descendants": [
                        _control_record(control)
                        for control in owned_descendants[:_CONTEXT_DIAGNOSTIC_MAX_DESCENDANTS]
                    ],
                    "descendant_count": len(owned_descendants),
                    "descendants_truncated": len(owned_descendants) > _CONTEXT_DIAGNOSTIC_MAX_DESCENDANTS,
                }
            )
        surfaces.append(record)
    return {
        "process_pid": process_pid,
        "top_level_surface_count": len(owned_windows),
        "top_level_surfaces": surfaces,
        "top_level_surfaces_truncated": len(owned_windows) > _CONTEXT_DIAGNOSTIC_MAX_SURFACES,
    }


def _record_exception(report: dict[str, Any], exc: Exception) -> None:
    report["error"] = str(exc)
    report["error_type"] = type(exc).__name__
    supervisor_result = getattr(exc, "supervisor_result", None)
    if supervisor_result is not None:
        report["uia_supervisor"] = supervisor_result
    diagnostics = getattr(exc, "diagnostics", None)
    if diagnostics and diagnostics.get("write_errors"):
        report["diagnostics_error"] = diagnostics


def _owned_visible_popups(desktop: Any, main_window: Any, process_pid: int) -> list[Any]:
    """Reject any additional visible owned top-level window before input."""
    main_handle = int(getattr(main_window.element_info, "handle", 0) or 0)
    popups: list[Any] = []
    for control in desktop.windows():
        info = control.element_info
        handle = int(getattr(info, "handle", 0) or 0)
        if (
            getattr(info, "process_id", None) == process_pid
            and handle
            and handle != main_handle
            and _is_visible(control)
        ):
            popups.append(control)
    return popups


def _menu_items(menu: Any, process_pid: int) -> list[Any]:
    items = []
    for control in menu.descendants():
        info = control.element_info
        if (
            getattr(info, "process_id", None) == process_pid
            and getattr(info, "control_type", "") == "MenuItem"
            and _is_visible(control)
        ):
            items.append(control)
    return items


def _window_process_identity(hwnd: int, psutil: Any) -> dict[str, Any]:
    if not is_windows_native():
        raise BlockedError("native root HWND identity requires Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_pid = user32.GetWindowThreadProcessId
    get_pid.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    get_pid.restype = wintypes.DWORD
    pid = wintypes.DWORD(0)
    if not get_pid(hwnd, ctypes.byref(pid)) or not pid.value:
        raise BlockedError(f"GetWindowThreadProcessId failed for HWND {hwnd:#x}")
    native = psutil.Process(int(pid.value))
    return {
        "pid": int(pid.value),
        "create_time": float(native.create_time()),
        "executable": str(native.exe()),
    }


def _native_window_snapshot(hwnd: int) -> dict[str, Any]:
    """Read only typed Win32 ownership/visibility data; never enters COM."""
    if not is_windows_native():
        raise BlockedError("native HWND discovery requires Windows")
    if not isinstance(hwnd, int) or isinstance(hwnd, bool) or hwnd <= 0:
        raise ContractError("native window handle must be a positive integer")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    is_window = user32.IsWindow
    is_window.argtypes = [wintypes.HWND]
    is_window.restype = wintypes.BOOL
    is_visible = user32.IsWindowVisible
    is_visible.argtypes = [wintypes.HWND]
    is_visible.restype = wintypes.BOOL
    get_pid = user32.GetWindowThreadProcessId
    get_pid.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    get_pid.restype = wintypes.DWORD
    get_class = user32.GetClassNameW
    get_class.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    get_class.restype = ctypes.c_int
    native = wintypes.HWND(hwnd)
    if not is_window(native):
        return {"hwnd": hwnd, "live": False, "visible": False, "pid": 0, "class_name": ""}
    owner_pid = wintypes.DWORD(0)
    if not get_pid(native, ctypes.byref(owner_pid)) or not owner_pid.value:
        return {"hwnd": hwnd, "live": True, "visible": False, "pid": 0, "class_name": ""}
    class_name = ctypes.create_unicode_buffer(256)
    if not get_class(native, class_name, len(class_name)):
        class_value = ""
    else:
        class_value = class_name.value
    return {
        "hwnd": hwnd,
        "live": True,
        "visible": bool(is_visible(native)),
        "pid": int(owner_pid.value),
        "class_name": class_value,
    }


def _validate_bounded_target(
    target: dict[str, Any],
    identity: dict[str, Any],
    executable: Path,
    *,
    expected_hwnd: int | None = None,
    require_uia_main: bool = False,
) -> dict[str, Any]:
    """Reject malformed or swapped identity before accepting worker evidence."""
    if not isinstance(target, dict):
        raise ContractError("bounded target identity is not an object")
    try:
        pid = target["pid"]
        create_time = target["create_time"]
        target_hwnd = target["hwnd"]
        target_exe = target["executable"]
        visible = target["visible"]
        class_name = target["class_name"]
    except (KeyError, TypeError) as exc:
        raise ContractError("bounded target identity is malformed") from exc
    if not isinstance(pid, int) or isinstance(pid, bool):
        raise ContractError("bounded target PID is malformed")
    if not isinstance(target_hwnd, int) or isinstance(target_hwnd, bool) or target_hwnd <= 0:
        raise ContractError("bounded target HWND is malformed")
    if not isinstance(create_time, (int, float)) or isinstance(create_time, bool) or not math.isfinite(float(create_time)):
        raise ContractError("bounded target create-time is malformed")
    if visible is not True or not isinstance(class_name, str) or not class_name:
        raise ContractError("bounded target window visibility/class is invalid")
    if require_uia_main and class_name != "NMainWindow":
        raise ContractError("bounded UIA target is not NMainWindow")
    if pid != int(identity["pid"]) or float(create_time) != float(identity["create_time"]):
        raise ContractError("bounded target PID/create-time identity changed")
    if not _same_path(target_exe, executable):
        raise ContractError("bounded target executable identity changed")
    if expected_hwnd is not None and target_hwnd != expected_hwnd:
        raise ContractError("bounded target HWND changed")
    return target


def _discover_owned_main_hwnd(
    process: Any,
    psutil: Any,
    identity: dict[str, Any],
    executable: Path,
    *,
    timeout: float = 30.0,
    poll_interval: float = 0.25,
    pinned_hwnd: int | None = None,
) -> dict[str, Any]:
    """Pin the sole visible owned top-level HWND; the worker checks its UIA role.

    Win32 GetClassNameW returns Qt's registered QWindow class, not the
    NMainWindow class exposed through UIA. Do not conflate the two namespaces.
    """
    if not math.isfinite(float(timeout)) or timeout <= 0:
        raise ValueError("HWND discovery timeout must be finite and positive")
    if pinned_hwnd is not None and (type(pinned_hwnd) is not int or pinned_hwnd <= 0):
        raise ValueError("pinned HWND must be a positive integer")
    deadline = time.monotonic() + timeout
    while True:
        _verify_process_identity(process, psutil, identity, executable)
        candidates: list[dict[str, Any]] = []
        callback_errors: list[Exception] = []
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        enum_windows = user32.EnumWindows
        callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
        callback = callback_type(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
            lambda hwnd, _lparam: _collect(hwnd, identity, candidates, callback_errors)
        )
        enum_windows.argtypes = [callback_type(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
        enum_windows.restype = wintypes.BOOL
        if not enum_windows(callback, 0):
            raise ContractError("EnumWindows failed")
        if callback_errors:
            raise callback_errors[0]
        if pinned_hwnd is not None:
            # Context inspection intentionally creates a second top-level popup.
            # Recheck only the previously pinned main HWND, never substitute it.
            candidates = [target for target in candidates if target["hwnd"] == pinned_hwnd]
        if len(candidates) > 1:
            raise ContractError(f"owned visible native window count is {len(candidates)}, expected one")
        if candidates:
            target = candidates[0]
            owner = psutil.Process(target["pid"])
            target.update({"create_time": float(owner.create_time()), "executable": str(owner.exe())})
            target["visible"] = True
            _validate_bounded_target(target, identity, executable)
            return target
        if time.monotonic() >= deadline:
            raise TimeoutError("timed out waiting for one owned visible native window")
        time.sleep(min(max(0.0, poll_interval), max(0.0, deadline - time.monotonic())))


def _collect(hwnd: int, identity: dict[str, Any], candidates: list[dict[str, Any]], errors: list[Exception]) -> int:
    try:
        snapshot = _native_window_snapshot(int(hwnd))
        if (
            snapshot["live"]
            and snapshot["visible"]
            and snapshot["pid"] == int(identity["pid"])
        ):
            candidates.append(snapshot)
    except Exception as exc:
        errors.append(exc)
    return 1


def _wait_for_context_menu(
    desktop: Any,
    main_window: Any,
    process: Any,
    psutil: Any,
    identity: dict[str, Any],
    executable: Path,
    baseline_keys: set[str],
    timeout: float,
    diagnostics_path: Path | None = None,
) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _verify_process_identity(process, psutil, identity, executable)
        menus = _owned_context_menus(
            desktop,
            main_window,
            identity["pid"],
            process_identity=identity,
            psutil=psutil,
            executable=executable,
        )
        fresh = [menu for menu in menus if _runtime_key(menu) not in baseline_keys]
        if fresh:
            if len(fresh) != 1:
                raise ContractError(f"unexpected newly-visible owned Menu count: {len(fresh)}")
            return fresh[0]
        time.sleep(0.25)
    timeout_error = RuntimeError("timed out waiting for newly-visible owned context Menu")
    timeout_error.diagnostics = {
        "path": str(diagnostics_path) if diagnostics_path is not None else None,
        "write_errors": [],
    }
    if diagnostics_path is not None:
        try:
            _write_json(diagnostics_path, _owned_surface_diagnostics(desktop, identity["pid"]))
        except Exception as first_error:
            timeout_error.diagnostics["write_errors"].append(
                {"stage": "diagnostics", "error": repr(first_error)}
            )
            try:
                _write_json(diagnostics_path, {"error": repr(first_error), "process_pid": identity["pid"]})
            except Exception as second_error:
                timeout_error.diagnostics["write_errors"].append(
                    {"stage": "fallback", "error": repr(second_error)}
                )
            raise timeout_error from first_error
    raise timeout_error


def _capture(main_window: Any, output: Path, filename: str) -> str | None:
    try:
        main_window.capture_as_image().save(output / filename)
        return filename
    except Exception as exc:
        _write_json(output / "screenshot-error.json", {"error": repr(exc)})
        return None


def _bounded_read_only_snapshot(
    *,
    output: Path,
    process: Any,
    psutil: Any,
    identity: dict[str, Any],
    executable: Path,
    expected_rows: Sequence[str],
    worker_mode_args: Sequence[str] = (),
) -> dict[str, Any]:
    """Run read-only UIA outside this controller with independent HWND checks."""
    parent_before = _discover_owned_main_hwnd(process, psutil, identity, executable)
    _validate_bounded_target(parent_before, identity, executable)
    expected_hwnd = parent_before["hwnd"]
    result: Any | None = None
    primary_exception: Exception | None = None
    try:
        result = uia_supervisor.run_supervised(
            output_dir=output / "uia-supervisor",
            worker_args=(
                "--hwnd", str(expected_hwnd),
                "--pid", str(identity["pid"]),
                "--create-time", str(identity["create_time"]),
                "--exe", str(executable),
                "--expected-rows", json.dumps(list(expected_rows), separators=(",", ":")),
                *worker_mode_args,
            ),
            readiness_timeout=5.0,
            execution_timeout=30.0,
            terminate_timeout=2.0,
            kill_timeout=2.0,
        )
    except Exception as exc:
        primary_exception = exc

    postcheck_error: Exception | None = None
    parent_after: dict[str, Any] | None = None
    try:
        post_options = {"pinned_hwnd": expected_hwnd} if worker_mode_args == ("--context-menu",) else {}
        parent_after = _discover_owned_main_hwnd(process, psutil, identity, executable, timeout=5.0, **post_options)
        _validate_bounded_target(parent_after, identity, executable, expected_hwnd=expected_hwnd)
    except Exception as exc:
        postcheck_error = exc

    if primary_exception is not None:
        result_dict = dict(getattr(primary_exception, "supervisor_result", {}) or {})
        result_dict.setdefault("status", "FAIL")
        result_dict.setdefault("primary_error", f"{type(primary_exception).__name__}: {primary_exception}")
        if postcheck_error is not None:
            result_dict.setdefault("secondary_errors", []).append(
                f"parent HWND postcheck failed: {type(postcheck_error).__name__}: {postcheck_error}"
            )
        primary_exception.supervisor_result = result_dict
        raise primary_exception

    assert result is not None
    result_dict = result.to_dict()
    result_dict["parent_target_before"] = parent_before
    if parent_after is not None:
        result_dict["parent_target_after"] = parent_after
    if postcheck_error is not None:
        result_dict.setdefault("secondary_errors", []).append(
            f"parent HWND postcheck failed: {type(postcheck_error).__name__}: {postcheck_error}"
        )
    if result.status != "SUCCESS" or not result.success or not result.cleanup_verified:
        failure = result.failure_kind or ("cleanup_uncertain" if not result.cleanup_verified else "worker_result")
        error = RuntimeError(f"bounded UIA worker ended with {result.status}: {failure}")
        error.supervisor_result = result_dict
        raise error
    if postcheck_error is not None:
        error = RuntimeError(f"bounded UIA parent HWND postcheck failed: {postcheck_error}")
        error.supervisor_result = result_dict
        raise error

    for label, target in (("worker before", result.target_before), ("worker after", result.target_after)):
        try:
            _validate_bounded_target(target, identity, executable, expected_hwnd=expected_hwnd, require_uia_main=True)
        except Exception as exc:
            error = RuntimeError(f"bounded UIA {label} identity did not match the owned player: {exc}")
            error.supervisor_result = result_dict
            raise error from exc

    payload = result.child_payload
    snapshot = payload.get("snapshot")
    rows = payload.get("playlist_rows")
    if not isinstance(snapshot, list) or not isinstance(rows, list):
        error = RuntimeError("bounded UIA worker returned no primitive snapshot or playlist rows")
        error.supervisor_result = result_dict
        raise error
    return {"result": result_dict, "snapshot": snapshot, "playlist_rows": rows, "target": parent_after}


def _validate_bounded_context_payload(payload: Any, expected_rows: Sequence[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractError("bounded context worker payload is not an object")
    context = payload.get("context_menu")
    if not isinstance(context, dict):
        raise ContractError("bounded context worker returned no context-menu contract")
    if context.get("menu_items_invoked") is not False:
        raise ContractError("bounded context worker did not prove menu_items_invoked=false")
    stages = context.get("stage_diagnostics")
    expected_stages = {
        "root_playlist_rows_validated",
        "focus_and_selection_validated",
        "ownership_before_validated",
        "keyboard_context_posted_once",
        "fresh_menu_validated",
        "selection_retained_after_menu",
    }
    if (
        not isinstance(stages, dict)
        or set(stages) != expected_stages
        or any(value is not True for value in stages.values())
    ):
        raise ContractError("bounded context worker stage diagnostics are incomplete")
    if context.get("selected_rows") != list(expected_rows[:2]):
        raise ContractError("bounded context worker selection is not exactly the first two rows")
    if context.get("selection_state") != [True, True, False]:
        raise ContractError("bounded context worker selection state is not [True, True, False]")
    if context.get("selection_after_menu") != [True, True, False]:
        raise ContractError("bounded context worker did not retain the exact selection")
    if context.get("menu_items_count") != 4 or not isinstance(context.get("menu_items"), list):
        raise ContractError("bounded context worker did not observe exactly four menu items")
    if len(context["menu_items"]) != 4:
        raise ContractError("bounded context worker menu-item list is not exactly four entries")
    expected_pid = payload.get("pid")
    menu_root = context.get("menu_root")
    if (
        type(expected_pid) is not int or expected_pid <= 0
        or not isinstance(menu_root, dict)
        or menu_root.get("process_id") != expected_pid
        or type(menu_root.get("nativehandle")) is not int
        or menu_root["nativehandle"] <= 0
        or menu_root.get("control_type") != "Pane"
        or menu_root.get("class_name") != "QMenu"
        or menu_root.get("automation_id") != "QtSingleApplication.QMenu"
    ):
        raise ContractError("bounded context worker menu root identity is not owned and observed")
    if any(
        not isinstance(record, dict) or record.get("process_id") != expected_pid
        for record in context["menu_items"]
    ):
        raise ContractError("bounded context worker menu items contain a foreign record")
    recognized = context.get("recognized_items")
    if not isinstance(recognized, list) or len(recognized) != 2:
        raise ContractError("bounded context worker returned the wrong recognized menu-item count")
    for record in [menu_root, *context["menu_items"], *(entry.get("record") for entry in recognized if isinstance(entry, dict))]:
        if not isinstance(record, dict) or type(record.get("process_id")) is not int or record["process_id"] != expected_pid:
            raise ContractError("bounded context worker record PID is malformed or foreign")
        runtime = record.get("runtimeID")
        if not isinstance(runtime, list) or not runtime or any(
            type(value) is not int or not -(2**31) <= value < 2**31 for value in runtime
        ):
            raise ContractError("bounded context worker runtime ID is malformed")
    expected_ids = {
        "Move To Trash": "QtSingleApplication.QMenu.MoveToTrashAction",
        "Remove From Playlist": "QtSingleApplication.QMenu.RemoveFromPlaylistAction",
    }
    observed_ids = {
        entry.get("label"): entry.get("record", {}).get("automation_id")
        for entry in recognized
        if isinstance(entry, dict) and isinstance(entry.get("record"), dict)
    }
    if observed_ids != expected_ids:
        raise ContractError(f"bounded context worker menu IDs differ: {observed_ids!r}")
    runtime_ids = [
        json.dumps(entry["record"].get("runtimeID"), sort_keys=True, default=str)
        for entry in recognized
    ]
    if len(set(runtime_ids)) != 2:
        raise ContractError("bounded context worker menu action runtime IDs are not distinct")
    ownership_before = context.get("ownership_before")
    ownership_after = context.get("ownership_after")
    if (
        not isinstance(ownership_before, dict)
        or ownership_before.get("owned_popup_count") != 0
        or ownership_before.get("owned_context_menu_count") != 0
    ):
        raise ContractError("bounded context worker ownership-before state is not empty")
    if not isinstance(ownership_after, dict) or ownership_after.get("owned_context_menu_count") != 1:
        raise ContractError("bounded context worker ownership-after state lacks one menu")
    return context


def _bounded_context_menu_snapshot(
    *,
    output: Path,
    process: Any,
    psutil: Any,
    identity: dict[str, Any],
    executable: Path,
    expected_rows: Sequence[str],
) -> dict[str, Any]:
    bounded = _bounded_read_only_snapshot(
        output=output,
        process=process,
        psutil=psutil,
        identity=identity,
        executable=executable,
        expected_rows=expected_rows,
        worker_mode_args=("--context-menu",),
    )
    try:
        context = _validate_bounded_context_payload(bounded["result"].get("child_payload"), expected_rows)
    except Exception as exc:
        exc.supervisor_result = bounded["result"]
        raise
    bounded["context_menu"] = context
    return bounded


def _fixtures_unchanged(fixtures: Sequence[Path], fixture_hashes: dict[str, dict[str, Any]]) -> bool:
    return all(
        path.is_file()
        and path.stat().st_size == fixture_hashes[path.name]["size"]
        and _sha256(path) == fixture_hashes[path.name]["sha256"]
        for path in fixtures
    )


def _cleanup(
    process: Any,
    temp_root: Path | None,
    *,
    owner_check: Any | None = None,
    retain_temp_root: bool = False,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    stopped = process is None
    if process is not None:
        if process.poll() is not None:
            stopped = True
        elif owner_check is None:
            errors.append("live child ownership was not established")
        else:
            try:
                owner_check()
            except Exception as exc:
                errors.append(f"initial cleanup ownership check failed: {exc!r}")
            else:
                try:
                    process.terminate()
                except Exception as exc:
                    errors.append(f"terminate failed: {exc!r}")
                if process.poll() is None:
                    try:
                        process.wait(timeout=10)
                    except Exception as wait_exc:
                        first_wait_error = wait_exc
                    else:
                        first_wait_error = None
                else:
                    first_wait_error = None
                if process.poll() is None:
                    try:
                        owner_check()
                        process.kill()
                        process.wait(timeout=10)
                    except Exception as exc:
                        errors.append(f"kill/wait failed: {exc!r}")
                stopped = process.poll() is not None
                if not stopped and first_wait_error is not None and not errors:
                    errors.append(f"terminate/wait failed: {first_wait_error!r}")
    if stopped and temp_root is not None:
        if retain_temp_root:
            errors.append("temporary evidence retained because worker cleanup is uncertain")
        else:
            try:
                shutil.rmtree(temp_root)
            except Exception as exc:
                errors.append(repr(exc))
    return stopped and not errors, errors


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument(
        "--inspect-context-menu",
        action="store_true",
        help="opt in to SelectionItem/context-menu observation; never invokes a menu item",
    )
    parser.add_argument(
        "--allow-owned-pointer-input",
        action="store_true",
        help="allow one guarded real right-click; requires --inspect-context-menu",
    )
    parser.add_argument(
        "--bounded-read-only",
        action="store_true",
        help="run read-only UIA traversal in a finite supervised worker; context mode remains separate",
    )
    parser.add_argument(
        "--bounded-context-menu",
        action="store_true",
        help="run finite owned context-menu observation without invoking a menu item",
    )
    args = parser.parse_args(argv)
    if args.bounded_read_only and args.inspect_context_menu:
        parser.error("--bounded-read-only cannot be combined with --inspect-context-menu")
    if args.bounded_context_menu and (
        args.bounded_read_only or args.inspect_context_menu or args.allow_owned_pointer_input
    ):
        parser.error(
            "--bounded-context-menu cannot be combined with bounded-read-only, "
            "legacy context-menu, or pointer input flags"
        )
    if args.allow_owned_pointer_input and not args.inspect_context_menu:
        parser.error("--allow-owned-pointer-input requires --inspect-context-menu")
    return args


def inspect_context_menu(
    *,
    main_window: Any,
    playlist: Any,
    rows: Sequence[Any],
    expected_rows: Sequence[str],
    process: Any,
    psutil: Any,
    process_identity: dict[str, Any],
    executable: Path,
    desktop: Any,
    output: Path,
    fixtures: Sequence[Path],
    fixture_hashes: dict[str, dict[str, Any]],
    report: dict[str, Any],
    allow_owned_pointer_input: bool = False,
) -> None:
    """Perform the opt-in context-menu observation, never a menu action."""
    pointer_desktop: dict[str, Any] | None = None
    if allow_owned_pointer_input:
        try:
            owned_pointer.validate_runner_environment()
        except owned_pointer.BlockedError as exc:
            raise BlockedError(str(exc)) from exc

    focus_evidence = None
    focus_after_selection = None
    if not allow_owned_pointer_input:
        focus_evidence = focus_owned_row(rows[0], expected_rows[0], process_identity["pid"])
    selected = select_exact_rows(rows, expected_rows, process_identity["pid"])
    if not allow_owned_pointer_input:
        focus_after_selection = verify_owned_row_focus(rows[0], expected_rows[0], process_identity["pid"])
    report["context_menu"] = {
        "focused_row": focus_evidence,
        "focus_verified_before_post": focus_after_selection,
        "selected_rows": selected,
        "menu_items_invoked": False,
        "transport": "SendInput(right-down,right-up)" if allow_owned_pointer_input else "PostMessageW(WM_CONTEXTMENU) keyboard-reason LPARAM=-1",
        "reason": "pointer" if allow_owned_pointer_input else "keyboard",
    }
    if not allow_owned_pointer_input:
        report["context_menu"]["message_lparam"] = -1

    baseline_menus = _owned_context_menus(
        desktop,
        main_window,
        process_identity["pid"],
        process_identity=process_identity,
        psutil=psutil,
        executable=executable,
    )
    baseline_popups = _owned_visible_popups(desktop, main_window, process_identity["pid"])
    if baseline_menus or baseline_popups:
        raise ContractError("an owned Menu or popup was already visible before the context request")
    baseline_keys: set[str] = set()

    _verify_process_identity(process, psutil, process_identity, executable)
    hwnd = int(getattr(main_window.element_info, "handle", 0) or 0)
    if not hwnd:
        raise BlockedError("owned main window has no native HWND for context-menu input")

    def revalidate_pointer_ownership() -> dict[str, Any]:
        _verify_process_identity(process, psutil, process_identity, executable)
        if int(getattr(main_window.element_info, "handle", 0) or 0) != hwnd:
            raise ContractError("owned main root HWND changed before pointer input")
        root = _window_process_identity(hwnd, psutil)
        if (
            root.get("pid") != process_identity["pid"]
            or float(root.get("create_time")) != float(process_identity["create_time"])
            or not _same_path(root.get("executable", ""), executable)
        ):
            raise ContractError("owned main root HWND identity no longer matches Popen identity")
        return root

    root_identity = revalidate_pointer_ownership()
    if allow_owned_pointer_input:
        try:
            api = owned_pointer._load_user32()
            kernel32 = owned_pointer._load_kernel32()
            row_rect = rows[0].rectangle()
            main_rect = main_window.rectangle()
            point = owned_pointer.choose_target_point(row_rect, main_rect)

            def revalidate_pointer_boundary(
                allow_owned_pending_rightdown: bool = False,
                require_cursor_at_point: bool = False,
            ) -> dict[str, Any]:
                desktop_check = owned_pointer.inspect_interactive_desktop(
                    process_identity["pid"], api=api, kernel32=kernel32
                )
                boundary_root = revalidate_pointer_ownership()
                if int(api.GetForegroundWindow() or 0) != hwnd:
                    raise BlockedError("owned main window lost foreground at pointer boundary")
                actual = owned_pointer._cursor(api) if require_cursor_at_point else point
                if require_cursor_at_point and not owned_pointer._same_point(actual, point):
                    raise BlockedError("cursor moved from originally chosen point at pointer boundary")
                fresh = fresh_pointer_target_context(
                    playlist, main_window, expected_rows, process_identity["pid"], point
                )
                target = owned_pointer.validate_pointer_target(
                    api,
                    root_hwnd=hwnd,
                    point=actual,
                    row_rect=fresh["row_rect"],
                    main_rect=fresh["main_rect"],
                    request_foreground=False,
                    allow_owned_pending_rightdown=allow_owned_pending_rightdown,
                )
                return {
                    "desktop_preflight": desktop_check,
                    "root_identity": boundary_root,
                    **fresh,
                    **target,
                }

            preflight = revalidate_pointer_boundary()
            pointer_desktop = preflight["desktop_preflight"]
            root_identity = preflight["root_identity"]
            report["context_menu"].update(
                {
                    "desktop_preflight": pointer_desktop,
                    "root_identity": root_identity,
                    "target_point": preflight["point"],
                    "preflight": preflight,
                    "preflight_check_time": time.time(),
                }
            )
            positioned = owned_pointer.move_cursor_checked(
                api,
                root_hwnd=hwnd,
                point=point,
                row_rect=row_rect,
                main_rect=main_rect,
                revalidate=revalidate_pointer_boundary,
            )
            report["context_menu"]["positioning"] = positioned
            try:
                input_result = owned_pointer.click_right_checked(
                    api,
                    root_hwnd=hwnd,
                    point=point,
                    revalidate=lambda: revalidate_pointer_boundary(require_cursor_at_point=True),
                    release_revalidate=lambda: revalidate_pointer_boundary(
                        allow_owned_pending_rightdown=True,
                        require_cursor_at_point=True,
                    ),
                )
            except owned_pointer.PointerInputError as exc:
                report["context_menu"]["input_diagnostics"] = exc.diagnostics
                raise BlockedError(str(exc)) from exc
            report["context_menu"]["input_diagnostics"] = input_result
        except owned_pointer.BlockedError as exc:
            if hasattr(exc, "diagnostics"):
                report["context_menu"]["input_diagnostics"] = exc.diagnostics
            raise BlockedError(str(exc)) from exc
    else:
        _verify_process_identity(process, psutil, process_identity, executable)
        post_keyboard_context_menu(main_window, process_identity, root_identity, executable)
    report["context_menu"]["root_identity"] = root_identity
    if not allow_owned_pointer_input:
        report["context_menu"]["message_posted_once"] = True

    menu = _wait_for_context_menu(
        desktop,
        main_window,
        process,
        psutil,
        process_identity,
        executable,
        baseline_keys,
        timeout=10,
        diagnostics_path=output / "player-context-menu-discovery-diagnostics.json",
    )
    menu_tree = _tree(menu)
    _write_json(output / "player-context-menu-uia.json", menu_tree)
    screenshot = _capture(menu, output, "player-context-menu.png")
    if screenshot is None:
        raise ContractError("context menu screenshot could not be captured")
    report["context_menu"].update(
        {
            "menu_runtimeID": _as_json_value(getattr(menu.element_info, "runtime_id", None)),
            "newly_visible_names": [record["name"] for record in menu_tree if record["name"]],
            "uia_tree_records": len(menu_tree),
            "screenshot": screenshot,
        }
    )
    recognized = recognize_context_menu_items(_menu_items(menu, process_identity["pid"]))
    report["context_menu"]["recognized_items"] = recognized
    report["context_menu"]["menu_items_invoked"] = False

    _verify_process_identity(process, psutil, process_identity, executable)
    after_rows = list(playlist.descendants(control_type="ListItem"))
    after_actual = [_window_text(row) for row in after_rows]
    exact_playlist_rows(after_actual, expected_rows)
    report["context_menu"]["rows_after_menu"] = after_actual
    retained_states: list[bool] = []
    if len(after_rows) == len(expected_rows):
        retained_states = [_selection_state(row) for row in after_rows]
    report["context_menu"]["selection_retained"] = retained_states == [True, True, False]

    unchanged = _fixtures_unchanged(fixtures, fixture_hashes)
    if not unchanged:
        raise ContractError("fixture bytes changed during context-menu inspection")
    report["context_menu"]["filesystem_unchanged"] = True


def run_inspection(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"status": "FAIL", "output": str(output), "cleanup": {}}
    process = None
    temp_root: Path | None = None
    main_window = None
    fixtures: Sequence[Path] = ()
    fixture_hashes: dict[str, dict[str, Any]] = {}
    cleanup_owner_check: Any | None = None
    try:
        if not is_windows_native():
            raise BlockedError("packaged UIA inspection requires native Windows")
        if args.allow_owned_pointer_input:
            try:
                owned_pointer.validate_runner_environment()
            except owned_pointer.BlockedError as exc:
                raise BlockedError(str(exc)) from exc
        source_sha = parse_source_sha(args.source_sha)
        expected_archive_sha = parse_archive_sha(args.archive_sha256)
        report["provenance"] = {
            "package_source_sha": source_sha,
            "automation_script_sha": _sha256(Path(__file__).resolve()),
            "automation_runtime_source_hashes": _runtime_source_hashes(),
            "git_github_sha": os.environ.get("GITHUB_SHA"),
        }
        package = args.package.resolve()
        actual_archive_sha = _sha256(package)
        report["archive_sha256"] = actual_archive_sha
        if actual_archive_sha.lower() != expected_archive_sha:
            raise ContractError(
                f"archive SHA-256 mismatch: expected {expected_archive_sha}, actual {actual_archive_sha}"
            )
        temp_root = Path(tempfile.mkdtemp(prefix="nulloy-player-inspection-"))
        package_info = extract_and_validate(package, temp_root / "package-extract", source_sha)
        report["package"] = {
            "archive_sha256": package_info.archive_sha256,
            "executable_sha256": package_info.executable_sha256,
            "file_hashes_verified": package_info.file_hashes_verified,
            "root": str(package_info.root),
            "executable": str(package_info.executable),
            "source_commit": package_info.contract.source_commit,
        }
        fixtures = make_fixtures(temp_root / "fixtures", "inspect-" + uuid.uuid4().hex[:12])
        fixture_hashes = {
            path.name: {"path": str(path), "sha256": _sha256(path), "size": path.stat().st_size}
            for path in fixtures
        }
        report["fixtures"] = fixture_hashes
        config = _portable_config(package_info.root, package_info.executable)
        report["config"] = str(config)
        environment = _safe_environment()
        command = [str(package_info.executable), *(str(path) for path in fixtures)]
        import psutil

        process = subprocess.Popen(command, cwd=package_info.root, env=environment)
        identity = _process_identity(process, psutil, package_info.executable)
        cleanup_owner_check = lambda: _verify_process_identity(
            process, psutil, identity, package_info.executable
        )
        report["process_identity"] = identity
        durations = [fixture_seconds(path) for path in fixtures]
        expected = expected_playlist_rows(fixtures, durations)

        if args.bounded_read_only:
            bounded = _bounded_read_only_snapshot(
                output=output,
                process=process,
                psutil=psutil,
                identity=identity,
                executable=package_info.executable,
                expected_rows=expected,
            )
            report["read_only_mode"] = "bounded-supervised-worker"
            report["uia_supervisor"] = bounded["result"]
            report["uia_target"] = bounded["target"]
            _write_json(output / "player-uia.json", bounded["snapshot"])
            report["uia_tree_records"] = len(bounded["snapshot"])
            report["screenshot"] = None
            report["screenshot_note"] = "bounded read-only mode serializes primitives; capture remains in the legacy path"
            actual = bounded["playlist_rows"]
            report["playlist"] = {
                "expected_rows": expected,
                "observed_rows": actual,
                "row_count": len(actual),
            }
            exact_playlist_rows(actual, expected)
            if not _fixtures_unchanged(fixtures, fixture_hashes):
                raise ContractError("fixture bytes changed during bounded read-only inspection")
            report["filesystem_unchanged"] = True
        elif args.bounded_context_menu:
            bounded = _bounded_context_menu_snapshot(
                output=output,
                process=process,
                psutil=psutil,
                identity=identity,
                executable=package_info.executable,
                expected_rows=expected,
            )
            report["mode"] = "bounded-context-menu-supervised-worker"
            report["context_menu_mode"] = "selection-and-menu-observation-only"
            report["uia_supervisor"] = bounded["result"]
            report["uia_target"] = bounded["target"]
            report["context_menu"] = bounded["context_menu"]
            _write_json(output / "player-uia.json", bounded["snapshot"])
            report["uia_tree_records"] = len(bounded["snapshot"])
            report["screenshot"] = None
            report["screenshot_note"] = "bounded context mode serializes UIA primitives; no screenshot or menu action is performed"
            actual = bounded["playlist_rows"]
            report["playlist"] = {
                "expected_rows": expected,
                "observed_rows": actual,
                "row_count": len(actual),
            }
            exact_playlist_rows(actual, expected)
            if not _fixtures_unchanged(fixtures, fixture_hashes):
                raise ContractError("fixture bytes changed during bounded context inspection")
            report["filesystem_unchanged"] = True
        else:
            import PIL.Image  # noqa: F401 - validates capture dependency
            from pywinauto import Desktop

            desktop = Desktop(backend="uia", allow_magic_lookup=False)
            main_window = _wait_for(
                lambda: (_verify_process_identity(process, psutil, identity, package_info.executable), _owned_main(desktop, identity))[1],
                30,
                "owned NMainWindow Pane",
            )
            tree = _tree(main_window)
            _write_json(output / "player-uia.json", tree)
            report["uia_tree_records"] = len(tree)
            report["screenshot"] = _capture(main_window, output, "player.png")
            if report["screenshot"] is None:
                raise ContractError("main UI screenshot could not be captured")
            playlist = _playlist(main_window)
            def exact_rows_ready() -> list[Any] | None:
                _verify_process_identity(process, psutil, identity, package_info.executable)
                rows = list(playlist.descendants(control_type="ListItem"))
                actual_rows = [_window_text(row) for row in rows]
                report["playlist"] = {
                    "expected_rows": expected,
                    "observed_rows": actual_rows,
                    "row_count": len(actual_rows),
                }
                return rows if actual_rows == expected else None

            rows = _wait_for(exact_rows_ready, 30, "exact owned playlist rows")
            actual = [_window_text(row) for row in rows]
            exact_playlist_rows(actual, expected)
            if not _fixtures_unchanged(fixtures, fixture_hashes):
                raise ContractError("fixture bytes changed during read-only inspection")
            report["filesystem_unchanged"] = True
            if args.inspect_context_menu:
                inspect_context_menu(
                    main_window=main_window,
                    playlist=playlist,
                    rows=rows,
                    expected_rows=expected,
                    process=process,
                    psutil=psutil,
                    process_identity=identity,
                    executable=package_info.executable,
                    desktop=desktop,
                    output=output,
                    fixtures=fixtures,
                    fixture_hashes=fixture_hashes,
                    report=report,
                    allow_owned_pointer_input=args.allow_owned_pointer_input,
                )
        report["status"] = "PASS"
    except BlockedError as exc:
        report["status"] = "BLOCKED"
        report["error"] = str(exc)
    except Exception as exc:
        report["status"] = "FAIL"
        _record_exception(report, exc)
        if main_window is not None:
            try:
                _write_json(output / "player-uia-failure.json", _tree(main_window))
                _capture(main_window, output, "player-failure.png")
            except Exception as capture_exc:
                report["capture_diagnostics_error"] = repr(capture_exc)
    finally:
        if fixtures and fixture_hashes:
            try:
                final_unchanged = _fixtures_unchanged(fixtures, fixture_hashes)
                report["filesystem_unchanged_final"] = final_unchanged
                if not final_unchanged:
                    if report["status"] == "PASS":
                        report["status"] = "FAIL"
                        report["error"] = "fixture bytes changed during final verification"
                    else:
                        report["final_verification_error"] = "fixture bytes changed during final verification"
            except Exception as verification_exc:
                report["filesystem_unchanged_final"] = False
                if report["status"] == "PASS":
                    report["status"] = "FAIL"
                    report["error"] = f"final fixture verification failed: {verification_exc}"
                else:
                    report["final_verification_error"] = repr(verification_exc)
        retain_temp_root = (
            "uia_supervisor" in report
            and report["uia_supervisor"].get("cleanup_verified") is not True
        )
        cleanup_verified, cleanup_errors = _cleanup(
            process,
            temp_root,
            owner_check=cleanup_owner_check,
            retain_temp_root=retain_temp_root,
        )
        report["cleanup"] = {
            "process_cleanup_verified": cleanup_verified,
            "errors": cleanup_errors,
            "temp_root_removed": temp_root is None or not temp_root.exists(),
        }
        if report["status"] == "PASS" and not cleanup_verified:
            report["status"] = "FAIL"
            report["error"] = "cleanup was not verified"
        _write_json(output / "inspection-report.json", report)
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report["status"]], report


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        code, report = run_inspection(args)
    except Exception as exc:
        output = args.output.resolve()
        report = {"status": "FAIL", "error": str(exc), "error_type": type(exc).__name__}
        _write_json(output / "inspection-report.json", report)
        code = 1
    print(json.dumps(report, sort_keys=True, default=str))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
