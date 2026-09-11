#!/usr/bin/env python3
"""Read-only UIA and initial-playlist inspection for a packaged Nulloy build.

This runner launches one validated portable package with three generated WAV files,
reads only its owned Qt UIA tree, and cleans up only the Popen-owned process and
its own temporary files.  Default mode never invokes a UI control or changes the
playlist; the explicit context-menu mode uses only UIA SelectionItem selection and
one root-HWND WM_CONTEXTMENU post, and never invokes a menu item.
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
    # UIAutomation exposes BOOL (an integer through comtypes), not VARIANT_BOOL.
    # Accept canonical 0/1 only; never infer state from arbitrary Python truthiness.
    if type(value) not in (bool, int) or value not in (0, 1):
        raise ContractError(
            f"SelectionItem.CurrentIsSelected has unsupported value {value!r} "
            f"({type(value).__name__}) for {_row_fullname(row)!r}"
        )
    return bool(value)


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


def _row_center(row: Any) -> tuple[int, int]:
    try:
        rectangle = row.rectangle()
        left, top = int(rectangle.left), int(rectangle.top)
        right, bottom = int(rectangle.right), int(rectangle.bottom)
    except Exception as exc:
        raise BlockedError(f"cannot read selected row rectangle: {exc!r}") from exc
    if right - left <= 2 or bottom - top <= 2:
        raise ContractError("selected row rectangle is too small for a strict interior point")
    return (left + right) // 2, (top + bottom) // 2


def context_message_args(
    main_window: Any,
    selected_row: Any,
    process_identity: dict[str, Any],
    root_identity: dict[str, Any],
    executable: str | Path,
    *,
    point: tuple[int, int] | None = None,
) -> tuple[int, int, int, int]:
    """Validate the owned native root and produce one WM_CONTEXTMENU payload."""
    info = main_window.element_info
    hwnd = int(getattr(info, "handle", 0) or 0)
    if not hwnd:
        raise BlockedError("owned main window has no native HWND")
    if getattr(info, "process_id", None) != process_identity["pid"]:
        raise ContractError("owned main window PID does not match Popen identity")
    if root_identity.get("pid") != process_identity["pid"]:
        raise ContractError("WM_CONTEXTMENU root HWND PID does not match Popen identity")
    if float(root_identity.get("create_time")) != float(process_identity["create_time"]):
        raise ContractError("WM_CONTEXTMENU root HWND create-time does not match Popen identity")
    if not _same_path(root_identity.get("executable", ""), executable):
        raise ContractError("WM_CONTEXTMENU root HWND executable does not match package executable")
    x, y = point if point is not None else _row_center(selected_row)
    rectangle = selected_row.rectangle()
    if not (int(rectangle.left) < x < int(rectangle.right) and int(rectangle.top) < y < int(rectangle.bottom)):
        raise ContractError("WM_CONTEXTMENU point is not strictly inside the selected row rectangle")
    if not (-32768 <= x <= 32767 and -32768 <= y <= 32767):
        raise ContractError("WM_CONTEXTMENU screen point cannot be represented by LPARAM coordinates")
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    return hwnd, WM_CONTEXTMENU, hwnd, lparam


def _post_message_windows(hwnd: int, message: int, wparam: int, lparam: int) -> bool:
    if not is_windows_native():
        raise BlockedError("WM_CONTEXTMENU transport requires native Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    post_message = user32.PostMessageW
    post_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    post_message.restype = wintypes.BOOL
    return bool(post_message(hwnd, message, wparam, lparam))


def post_context_menu(
    main_window: Any,
    selected_row: Any,
    process_identity: dict[str, Any],
    root_identity: dict[str, Any],
    executable: str | Path,
    *,
    post_message: Any | None = None,
    point: tuple[int, int] | None = None,
) -> None:
    """Post exactly one bounded WM_CONTEXTMENU message to the owned root HWND."""
    args = context_message_args(
        main_window, selected_row, process_identity, root_identity, executable, point=point
    )
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


def _owned_context_menus(desktop: Any, main_window: Any, process_pid: int) -> list[Any]:
    candidates = list(desktop.windows()) + list(main_window.descendants())
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
    raise RuntimeError("timed out waiting for newly-visible owned context Menu")


def _capture(main_window: Any, output: Path, filename: str) -> str | None:
    try:
        main_window.capture_as_image().save(output / filename)
        return filename
    except Exception as exc:
        _write_json(output / "screenshot-error.json", {"error": repr(exc)})
        return None


def _cleanup(process: Any, temp_root: Path | None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    stopped = process is None
    if process is not None:
        try:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            stopped = process.poll() is not None
            if not stopped:
                process.kill()
                process.wait(timeout=10)
                stopped = process.poll() is not None
        except Exception as exc:
            errors.append(repr(exc))
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
    return parser.parse_args(argv)


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
) -> None:
    """Perform the opt-in SelectionItem/context-menu observation only."""
    selected = select_exact_rows(rows, expected_rows, process_identity["pid"])
    report["context_menu"] = {
        "selected_rows": selected,
        "menu_items_invoked": False,
        "transport": "PostMessageW(WM_CONTEXTMENU)",
    }

    baseline_menus = _owned_context_menus(desktop, main_window, process_identity["pid"])
    if baseline_menus:
        raise ContractError("an owned Menu was already visible before the context request")
    baseline_keys: set[str] = set()

    _verify_process_identity(process, psutil, process_identity, executable)
    hwnd = int(getattr(main_window.element_info, "handle", 0) or 0)
    root_identity = _window_process_identity(hwnd, psutil)
    _verify_process_identity(process, psutil, process_identity, executable)
    post_context_menu(main_window, rows[0], process_identity, root_identity, executable)
    report["context_menu"]["root_identity"] = root_identity
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

    unchanged = all(
        path.is_file()
        and path.stat().st_size == fixture_hashes[path.name]["size"]
        and _sha256(path) == fixture_hashes[path.name]["sha256"]
        for path in fixtures
    )
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
    try:
        if not is_windows_native():
            raise BlockedError("packaged UIA inspection requires native Windows")
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
        unchanged = all(
            path.is_file() and path.stat().st_size == fixture_hashes[path.name]["size"] and _sha256(path) == fixture_hashes[path.name]["sha256"]
            for path in fixtures
        )
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
        cleanup_verified, cleanup_errors = _cleanup(process, temp_root)
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
