#!/usr/bin/env python3
"""Read-only UIA and initial-playlist inspection for a packaged Nulloy build.

This runner launches one validated portable package with three generated WAV files,
reads only its owned Qt UIA tree, and cleans up only the Popen-owned process and
its own temporary files.  Default mode never invokes a UI control or changes the
playlist; the explicit context-menu mode uses UIA SelectionItem selection and
one guarded keyboard or real-pointer context request, and never invokes a menu
item.  Real-pointer input requires the separate explicit allow flag.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
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

SOURCE_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
FIXTURE_COUNT = 3
FIXTURE_SECONDS = 30
PLAYLIST_CLASS = "NPlaylistWidget"
PLAYLIST_AUTOMATION_ID = "QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget"
WM_CONTEXTMENU = 0x007B
_MENU_LABELS = ("Move To Trash", "Remove From Playlist")
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
            and getattr(window, "is_visible", lambda: True)()
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
        label = _menu_label(item)
        if label:
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


def _is_visible(control: Any) -> bool:
    try:
        return bool(control.is_visible())
    except Exception:
        return True


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


def _owned_context_menus(desktop: Any, main_window: Any, process_pid: int) -> list[Any]:
    candidates = _owned_context_menu_candidates(desktop, main_window, process_pid)
    menus: list[Any] = []
    seen: set[str] = set()
    for control in candidates:
        info = control.element_info
        if (
            getattr(info, "process_id", None) == process_pid
            and getattr(info, "control_type", "") == "Menu"
            and _is_visible(control)
        ):
            key = _runtime_key(control)
            if key not in seen:
                seen.add(key)
                menus.append(control)
    if len(menus) > 1:
        raise ContractError(f"unexpected count of owned visible Menu roots: {len(menus)}")
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
        menus = _owned_context_menus(desktop, main_window, identity["pid"])
        fresh = [menu for menu in menus if _runtime_key(menu) not in baseline_keys]
        if fresh:
            if len(fresh) != 1:
                raise ContractError(f"unexpected newly-visible owned Menu count: {len(fresh)}")
            return fresh[0]
        time.sleep(0.25)
    if diagnostics_path is not None:
        try:
            _write_json(diagnostics_path, _owned_surface_diagnostics(desktop, identity["pid"]))
        except Exception as exc:
            _write_json(diagnostics_path, {"error": repr(exc), "process_pid": identity["pid"]})
    raise RuntimeError("timed out waiting for newly-visible owned context Menu")


def _capture(main_window: Any, output: Path, filename: str) -> str | None:
    try:
        main_window.capture_as_image().save(output / filename)
        return filename
    except Exception as exc:
        _write_json(output / "screenshot-error.json", {"error": repr(exc)})
        return None


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
    args = parser.parse_args(argv)
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

    baseline_menus = _owned_context_menus(desktop, main_window, process_identity["pid"])
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
        import PIL.Image  # noqa: F401 - validates capture dependency
        from pywinauto import Desktop

        process = subprocess.Popen(command, cwd=package_info.root, env=environment)
        identity = _process_identity(process, psutil, package_info.executable)
        cleanup_owner_check = lambda: _verify_process_identity(
            process, psutil, identity, package_info.executable
        )
        report["process_identity"] = identity
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
        durations = [fixture_seconds(path) for path in fixtures]
        expected = expected_playlist_rows(fixtures, durations)
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
        unchanged = _fixtures_unchanged(fixtures, fixture_hashes)
        if not unchanged:
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
        report["error"] = str(exc)
        report["error_type"] = type(exc).__name__
        if main_window is not None:
            try:
                _write_json(output / "player-uia-failure.json", _tree(main_window))
                _capture(main_window, output, "player-failure.png")
            except Exception as capture_exc:
                report["diagnostics_error"] = repr(capture_exc)
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
        cleanup_verified, cleanup_errors = _cleanup(
            process, temp_root, owner_check=cleanup_owner_check
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
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
