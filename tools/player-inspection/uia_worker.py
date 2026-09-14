#!/usr/bin/env python3
"""Owned, read-only UIA snapshot worker for the bounded inspector path."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Sequence

# Must be set before pywinauto/comtypes import.
sys.coinit_flags = 0


class _TransientNotReady(RuntimeError):
    """The owned UI exists natively but UIA has not exposed it yet."""


class _OwnershipError(RuntimeError):
    """The requested UIA/native identity is unsafe or belongs elsewhere."""


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True), flush=True)


def _emit_stage(stage: str, phase: str) -> None:
    _emit({"event": "stage", "stage": stage, "phase": phase})


def _positive_pid(value: Any, owner: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise _OwnershipError(f"{owner} PID is not a positive Python int")
    return value


def _runtime_id(value: Any, owner: str) -> list[int]:
    if not isinstance(value, (list, tuple)) or not value:
        raise _OwnershipError(f"{owner} runtimeID must be a nonempty list or tuple")
    if any(
        not isinstance(part, int)
        or isinstance(part, bool)
        or not -(2**31) <= part <= 2**31 - 1
        for part in value
    ):
        raise _OwnershipError(f"{owner} runtimeID contains a non-native value")
    return list(value)


def _native_handle(value: Any, owner: str, *, required: bool = False) -> int:
    if value is None:
        value = 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _OwnershipError(f"{owner} native handle is malformed")
    if required and value <= 0:
        raise _OwnershipError(f"{owner} native handle is not positive")
    return value


def _identity(process: Any) -> dict[str, Any]:
    return {"pid": int(process.pid), "create_time": float(process.create_time()), "executable": str(process.exe())}


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _native_window_info(hwnd: int) -> dict[str, Any]:
    if os.name != "nt":
        raise _OwnershipError("native HWND ownership requires Windows")
    if not isinstance(hwnd, int) or isinstance(hwnd, bool) or hwnd <= 0:
        raise _OwnershipError("exact owned HWND must be a positive integer")
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
    native = wintypes.HWND(hwnd)
    if not is_window(native):
        raise _OwnershipError(f"HWND is not a live native window: {hwnd}")
    owner_pid = wintypes.DWORD(0)
    if not get_pid(native, ctypes.byref(owner_pid)) or not owner_pid.value:
        raise _OwnershipError(f"GetWindowThreadProcessId failed for HWND {hwnd}")
    return {"hwnd": hwnd, "pid": int(owner_pid.value), "visible": bool(is_visible(native))}


def _validate_identity(process: Any, expected: dict[str, Any], executable: str) -> dict[str, Any]:
    actual = _identity(process)
    if actual["pid"] != int(expected["pid"]):
        raise _OwnershipError("UIA target PID changed")
    if actual["create_time"] != float(expected["create_time"]):
        raise _OwnershipError("UIA target create-time changed")
    if not _same_path(actual["executable"], executable):
        raise _OwnershipError("UIA target executable changed")
    return actual


def _canonical_visible(value: Any, owner: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise _OwnershipError(f"{owner} visibility is malformed")


_MENU_LABELS = ("Move To Trash", "Remove From Playlist")
_MENU_AUTOMATION_IDS = {
    "Move To Trash": "QtSingleApplication.QMenu.MoveToTrashAction",
    "Remove From Playlist": "QtSingleApplication.QMenu.RemoveFromPlaylistAction",
}
_SHORTCUT_RE = re.compile(
    r"(?:(?:Ctrl|Alt|Shift|Meta|Win)\+)*(?:Del|Delete|Backspace|Ins|Insert|Home|End|PageUp|PageDown|Left|Right|Up|Down|F(?:[1-9]|1[0-2])|[A-Za-z0-9])$"
)
WM_CONTEXTMENU = 0x007B
_CONTEXT_HELPERS: Any | None = None


def _context_helpers() -> Any:
    """Load the existing strict row helpers without importing this worker again."""
    global _CONTEXT_HELPERS
    if _CONTEXT_HELPERS is None:
        source = Path(__file__).with_name("inspect_player.py")
        spec = importlib.util.spec_from_file_location("nulloy_context_inspection_helpers", source)
        if spec is None or spec.loader is None:
            raise _OwnershipError("cannot load strict context inspection helpers")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        saved_modules = {
            name: sys.modules.get(name)
            for name in ("nulloy_owned_pointer", "nulloy_uia_supervisor", "nulloy_trash_probe_validator")
        }
        try:
            spec.loader.exec_module(module)
        finally:
            for name, previous in saved_modules.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
        _CONTEXT_HELPERS = module
    return _CONTEXT_HELPERS


def _context_menu_label(control: Any) -> str:
    raw = str(getattr(control.element_info, "name", "") or control.window_text()).strip()
    if raw in _MENU_LABELS:
        return raw
    if "\t" not in raw:
        return ""
    label, shortcut = (part.strip() for part in raw.split("\t", 1))
    return label if label in _MENU_LABELS and _SHORTCUT_RE.fullmatch(shortcut) else ""


def _context_record(control: Any, expected_pid: int) -> dict[str, Any]:
    info = control.element_info
    try:
        pid = _positive_pid(getattr(info, "process_id"), "context record")
        runtime_id = _runtime_id(getattr(info, "runtime_id"), "context record")
        nativehandle = _native_handle(getattr(info, "handle", None), "context record")
        record = {
            "name": str(getattr(info, "name", "") or ""),
            "text": str(control.window_text()),
            "control_type": str(getattr(info, "control_type", "") or ""),
            "automation_id": str(getattr(info, "automation_id", "") or ""),
            "class_name": str(getattr(info, "class_name", "") or ""),
            "process_id": pid,
            "nativehandle": nativehandle,
            "runtimeID": runtime_id,
        }
    except (AttributeError, TypeError, ValueError, _OwnershipError) as exc:
        raise _OwnershipError("context menu record is malformed") from exc
    if pid != expected_pid:
        raise _OwnershipError("context menu record belongs to a foreign process")
    return record


def _validate_context_menu(menu: Any, expected_pid: int) -> dict[str, Any]:
    """Validate one observed owned QMenu/Pane and its four visible entries."""
    info = menu.element_info
    try:
        pid = getattr(info, "process_id")
        control_type = getattr(info, "control_type")
        class_name = getattr(info, "class_name")
        automation_id = getattr(info, "automation_id")
        handle = getattr(info, "handle")
        visible = _canonical_visible(menu.is_visible(), "context menu")
    except (AttributeError, TypeError, ValueError) as exc:
        raise _OwnershipError("context menu root identity is malformed") from exc
    expected_pid = _positive_pid(expected_pid, "expected context")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or pid != expected_pid or not visible:
        raise _OwnershipError("context menu root is foreign or hidden")
    observed_qmenu = (
        control_type == "Pane"
        and class_name == "QMenu"
        and automation_id == "QtSingleApplication.QMenu"
        and isinstance(handle, int)
        and not isinstance(handle, bool)
        and handle > 0
    )
    if not observed_qmenu:
        raise _OwnershipError("context menu root is not the observed QMenu Pane identity")
    try:
        descendants = list(menu.descendants())
    except Exception as exc:
        raise _OwnershipError("context menu descendants are unavailable") from exc
    for child in descendants:
        _context_record(child, expected_pid)
    items = []
    for child in descendants:
        child_info = child.element_info
        if getattr(child_info, "control_type", "") == "MenuItem" and _canonical_visible(
            child.is_visible(), "context menu item"
        ):
            items.append(child)
    if len(items) != 4:
        raise _OwnershipError(f"context menu has {len(items)} visible MenuItems; expected four")
    recognized = []
    for item in items:
        record = _context_record(item, expected_pid)
        label = _context_menu_label(item)
        if label and record["automation_id"] == _MENU_AUTOMATION_IDS[label]:
            recognized.append({"label": label, "record": record})
    counts = {label: sum(entry["label"] == label for entry in recognized) for label in _MENU_LABELS}
    if any(count != 1 for count in counts.values()):
        raise _OwnershipError(f"context menu entries were not distinct exact matches: {counts!r}")
    runtime_ids = [json.dumps(entry["record"]["runtimeID"], sort_keys=True) for entry in recognized]
    if len(runtime_ids) != len(set(runtime_ids)):
        raise _OwnershipError("context menu action entries share a runtime ID")
    return {
        "root": _context_record(menu, expected_pid),
        "menu_items_count": len(items),
        "menu_items": [_context_record(item, expected_pid) for item in items],
        "recognized_items": recognized,
        "menu_items_invoked": False,
    }


def _runtime_key(control: Any) -> str:
    info = control.element_info
    runtime_id = getattr(info, "runtime_id", None)
    if runtime_id is not None:
        return "runtimeID:" + json.dumps(_runtime_id(runtime_id, "UIA control"), sort_keys=True)
    return f"handle:{getattr(info, 'handle', None)!r}"


def _owned_top_level_windows(desktop: Any, pid: int) -> list[Any]:
    windows: list[Any] = []
    seen: set[str] = set()
    for window in desktop.windows():
        if getattr(window.element_info, "process_id", None) != pid:
            continue
        key = _runtime_key(window)
        if key not in seen:
            seen.add(key)
            windows.append(window)
    return windows


def _context_candidates(desktop: Any, main: Any, pid: int) -> list[Any]:
    surfaces = _owned_top_level_windows(desktop, pid)
    main_key = _runtime_key(main)
    if all(_runtime_key(surface) != main_key for surface in surfaces):
        surfaces.append(main)
    candidates: list[Any] = []
    for surface in surfaces:
        candidates.append(surface)
        candidates.extend(
            child for child in surface.descendants()
            if getattr(child.element_info, "process_id", None) == pid
        )
    return candidates


def _validate_qmenu_native(menu: Any, process: Any, expected: dict[str, Any], executable: str) -> None:
    handle = _native_handle(menu.element_info.handle, "observed QMenu", required=True)
    native = _native_window_info(handle)
    actual = _identity(process)
    if (
        native["pid"] != expected["pid"]
        or native["pid"] != actual["pid"]
        or actual["create_time"] != float(expected["create_time"])
        or not _same_path(actual["executable"], executable)
        or not native["visible"]
    ):
        raise _OwnershipError("observed QMenu HWND identity does not match the owned player")


def _observed_qmenu_identity(info: Any) -> bool:
    return (
        getattr(info, "control_type", "") == "Pane"
        and getattr(info, "class_name", "") == "QMenu"
        and getattr(info, "automation_id", "") == "QtSingleApplication.QMenu"
        and isinstance(getattr(info, "handle", None), int)
        and not isinstance(getattr(info, "handle", None), bool)
        and getattr(info, "handle", 0) > 0
    )


def _owned_context_menus(
    desktop: Any,
    main: Any,
    pid: int,
    *,
    process: Any | None = None,
    expected: dict[str, Any] | None = None,
    executable: str | None = None,
) -> list[Any]:
    pid = _positive_pid(pid, "context discovery")
    menus: list[Any] = []
    seen: set[str] = set()
    for control in _context_candidates(desktop, main, pid):
        info = control.element_info
        if getattr(info, "process_id", None) != pid:
            continue
        observed_qmenu = _observed_qmenu_identity(info)
        looks_like_menu = getattr(info, "control_type", "") == "Menu"
        looks_like_qmenu = (
            getattr(info, "control_type", "") == "Pane"
            and (
                getattr(info, "class_name", "") == "QMenu"
                or getattr(info, "automation_id", "") == "QtSingleApplication.QMenu"
            )
        )
        if looks_like_menu or (looks_like_qmenu and not observed_qmenu):
            raise _OwnershipError("owned context-menu candidate is not the observed QMenu Pane identity")
        if not observed_qmenu:
            continue
        if not _canonical_visible(control.is_visible(), "context menu root"):
            continue
        _context_record(control, pid)
        if observed_qmenu and process is not None and expected is not None and executable is not None:
            _validate_qmenu_native(control, process, expected, executable)
        key = _runtime_key(control)
        if key not in seen:
            seen.add(key)
            menus.append(control)
    if len(menus) > 1:
        raise _OwnershipError(f"unexpected count of owned visible context-menu roots: {len(menus)}")
    return menus


def _owned_visible_popups(desktop: Any, main: Any, pid: int) -> list[Any]:
    main_handle = int(getattr(main.element_info, "handle", 0) or 0)
    return [
        window for window in desktop.windows()
        if getattr(window.element_info, "process_id", None) == pid
        and int(getattr(window.element_info, "handle", 0) or 0) != main_handle
        and int(getattr(window.element_info, "handle", 0) or 0) > 0
        and _canonical_visible(window.is_visible(), "owned popup")
    ]


def _context_ownership(
    desktop: Any,
    main: Any,
    pid: int,
    *,
    process: Any,
    expected: dict[str, Any],
    executable: str,
) -> dict[str, Any]:
    popups = _owned_visible_popups(desktop, main, pid)
    menus = _owned_context_menus(
        desktop, main, pid, process=process, expected=expected, executable=executable
    )
    if popups or menus:
        raise _OwnershipError("an owned popup or context menu was already visible")
    return {"owned_popup_count": len(popups), "owned_context_menu_count": len(menus)}


def _wait_for_context_menu(
    desktop: Any,
    main: Any,
    pid: int,
    *,
    process: Any,
    expected: dict[str, Any],
    executable: str,
    baseline_keys: set[str],
    timeout: float,
) -> tuple[Any, dict[str, Any]]:
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("context-menu timeout must be finite and positive")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _validate_identity(process, expected, executable)
        menus = _owned_context_menus(
            desktop, main, pid, process=process, expected=expected, executable=executable
        )
        fresh = [menu for menu in menus if _runtime_key(menu) not in baseline_keys]
        if fresh:
            if len(fresh) != 1:
                raise _OwnershipError(f"unexpected newly-visible owned context menu count: {len(fresh)}")
            return fresh[0], _validate_context_menu(fresh[0], pid)
        time.sleep(0.1)
    raise RuntimeError("timed out waiting for newly-visible owned context menu")


def _post_keyboard_context_menu(hwnd: int) -> None:
    if os.name != "nt":
        raise _OwnershipError("keyboard context-menu transport requires Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    post_message = user32.PostMessageW
    post_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    post_message.restype = wintypes.BOOL
    if not post_message(wintypes.HWND(hwnd), WM_CONTEXTMENU, wintypes.WPARAM(hwnd), wintypes.LPARAM(-1)):
        raise _OwnershipError("PostMessageW(WM_CONTEXTMENU) failed")


def _selected_state(row: Any, expected_name: str) -> bool:
    try:
        return _context_helpers()._selection_state(row)
    except Exception as exc:
        raise _OwnershipError(f"SelectionItem state is unavailable for {expected_name!r}") from exc


def _validate_context_rows(rows: Sequence[Any], expected_rows: Sequence[str], pid: int) -> list[bool]:
    if len(rows) != 3 or len(expected_rows) != 3:
        raise _OwnershipError("bounded context operation requires exactly three playlist rows")
    for row, expected_name in zip(rows, expected_rows):
        info = row.element_info
        if getattr(info, "process_id", None) != pid:
            raise _OwnershipError(f"playlist row PID mismatch for {expected_name!r}")
        if str(getattr(info, "name", "") or "") != expected_name or str(row.window_text()) != expected_name:
            raise _OwnershipError(f"playlist row identity mismatch for {expected_name!r}")
        try:
            getattr(row, "iface_selection_item")
        except Exception as exc:
            raise _OwnershipError(f"row lacks SelectionItem pattern for {expected_name!r}") from exc
    return [_selected_state(row, name) for row, name in zip(rows, expected_rows)]


def _select_context_rows(rows: Sequence[Any], expected_rows: Sequence[str], pid: int) -> list[bool]:
    _validate_context_rows(rows, expected_rows, pid)
    try:
        helpers = _context_helpers()
        helpers.focus_owned_row(rows[0], expected_rows[0], pid)
        helpers.select_exact_rows(rows, expected_rows, pid)
        helpers.verify_owned_row_focus(rows[0], expected_rows[0], pid)
    except Exception as exc:
        raise _OwnershipError("strict UIA focus/SelectionItem context selection failed") from exc
    states = _validate_context_rows(rows, expected_rows, pid)
    if states != [True, True, False]:
        raise _OwnershipError(f"context selection was not exactly the first two rows: {states!r}")
    return states


def _context_inspect_once(
    desktop: Any,
    process: Any,
    expected: dict[str, Any],
    executable: str,
    requested_hwnd: int,
    expected_rows: Sequence[str],
    emit_target: Callable[[dict[str, Any]], None],
    *,
    post_context: Callable[[int], None] = _post_keyboard_context_menu,
    context_timeout: float = 10.0,
) -> dict[str, Any]:
    _emit_stage("root/readiness", "started")
    before_identity = _validate_identity(process, expected, executable)
    root = _find_main(desktop, expected["pid"], requested_hwnd)
    descendants = list(root.descendants())
    for item in descendants:
        _context_record(item, expected["pid"])
    playlists = [
        item for item in descendants
        if getattr(item.element_info, "class_name", "") == "NPlaylistWidget"
        and getattr(item.element_info, "automation_id", "") == "QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget"
    ]
    if len(playlists) > 1:
        raise _OwnershipError(f"owned Qt playlist count is {len(playlists)}, expected one")
    if not playlists:
        raise _TransientNotReady("owned Qt playlist is not ready")
    try:
        rows = list(playlists[0].descendants(control_type="ListItem"))
    except Exception as exc:
        raise _TransientNotReady("playlist rows are not ready") from exc
    try:
        labels = [str(row.window_text()) for row in rows]
    except Exception as exc:
        raise _TransientNotReady("playlist row labels are not ready") from exc
    if labels != list(expected_rows):
        raise _TransientNotReady("exact expected playlist rows are not ready")
    _validate_context_rows(rows, expected_rows, expected["pid"])
    _emit_stage("root/readiness", "completed")
    target = {
        **before_identity,
        "hwnd": requested_hwnd,
        "name": str(getattr(root.element_info, "name", "") or ""),
        "class_name": "NMainWindow",
        "visible": True,
    }
    emit_target(target)
    _emit_stage("focus-selection", "started")
    selected_states = _select_context_rows(rows, expected_rows, expected["pid"])
    _emit_stage("focus-selection", "completed")
    _validate_identity(process, expected, executable)
    _emit_stage("ownership", "started")
    ownership_before = _context_ownership(
        desktop, root, expected["pid"], process=process, expected=expected, executable=executable
    )
    baseline_keys = {
        _runtime_key(menu)
        for menu in _owned_context_menus(
            desktop, root, expected["pid"], process=process, expected=expected, executable=executable
        )
    }
    native = _native_window_info(requested_hwnd)
    if native["pid"] != expected["pid"] or not native["visible"]:
        raise _OwnershipError("owned context root HWND is foreign or hidden")
    _emit_stage("ownership", "completed")
    _emit_stage("postcontext", "started")
    post_context(requested_hwnd)
    _emit_stage("postcontext", "completed")
    _emit_stage("menu-discovery", "started")
    menu, menu_observation = _wait_for_context_menu(
        desktop, root, expected["pid"], process=process, expected=expected, executable=executable,
        baseline_keys=baseline_keys, timeout=context_timeout,
    )
    _emit_stage("menu-discovery", "completed")
    _emit_stage("finalselection", "started")
    after_rows = list(playlists[0].descendants(control_type="ListItem"))
    after_labels = [str(row.window_text()) for row in after_rows]
    if after_labels != list(expected_rows):
        raise _OwnershipError("playlist rows changed while observing context menu")
    after_selected = _validate_context_rows(after_rows, expected_rows, expected["pid"])
    if after_selected != [True, True, False]:
        raise _OwnershipError(f"context selection was not retained: {after_selected!r}")
    _emit_stage("finalselection", "completed")
    _validate_identity(process, expected, executable)
    _validate_main_root(root, expected["pid"], requested_hwnd)
    after_identity = _identity(process)
    ownership_after = {
        "owned_popup_count": len(_owned_visible_popups(desktop, root, expected["pid"])),
        "owned_context_menu_count": len(
            _owned_context_menus(
                desktop, root, expected["pid"], process=process, expected=expected, executable=executable
            )
        ),
    }
    if ownership_after["owned_context_menu_count"] != 1:
        raise _OwnershipError("owned context menu was not retained for final observation")
    _emit({
        "event": "post_target",
        "target": {**after_identity, "hwnd": requested_hwnd, "name": target["name"],
                    "class_name": "NMainWindow", "visible": True},
    })
    return {
        "status": "PASS",
        "pid": expected["pid"],
        "hwnd": requested_hwnd,
        "target_name": target["name"],
        "target_before": target,
        "target_after": {**after_identity, "hwnd": requested_hwnd, "name": target["name"],
                          "class_name": "NMainWindow", "visible": True},
        "snapshot": [_info_record(root, expected["pid"])] + [
            _info_record(item, expected["pid"]) for item in descendants[:512]
        ],
        "playlist_rows": after_labels,
        "context_menu": {
            "stage_diagnostics": {
                "root_playlist_rows_validated": True,
                "focus_and_selection_validated": True,
                "ownership_before_validated": True,
                "keyboard_context_posted_once": True,
                "fresh_menu_validated": True,
                "selection_retained_after_menu": True,
            },
            "ownership_before": ownership_before,
            "ownership_after": ownership_after,
            "selected_rows": list(expected_rows[:2]),
            "selection_state": selected_states,
            "selection_after_menu": after_selected,
            "menu_root": menu_observation["root"],
            "menu_items_count": menu_observation["menu_items_count"],
            "menu_items": menu_observation["menu_items"],
            "recognized_items": menu_observation["recognized_items"],
            "menu_items_invoked": False,
            "transport": "PostMessageW(WM_CONTEXTMENU) keyboard-reason LPARAM=-1",
            "message": {"hwnd": requested_hwnd, "message": WM_CONTEXTMENU,
                        "wparam": requested_hwnd, "lparam": -1},
            "message_posted_once": True,
        },
    }


def _validate_main_root(root: Any, pid: int, requested_hwnd: int) -> Any:
    info = root.element_info
    try:
        info_pid = getattr(info, "process_id")
        handle = getattr(info, "handle")
        class_name = getattr(info, "class_name")
        control_type = getattr(info, "control_type")
    except AttributeError as exc:
        raise _OwnershipError("UIA main window identity is malformed") from exc
    if info_pid != pid:
        raise _OwnershipError("requested HWND UIA root is not owned by target PID")
    if class_name != "NMainWindow" or control_type != "Pane":
        raise _OwnershipError("requested HWND UIA root is not NMainWindow Pane")
    if not isinstance(handle, int) or isinstance(handle, bool) or handle != requested_hwnd:
        raise _OwnershipError("UIA root HWND does not match pinned native HWND")
    try:
        visible = _canonical_visible(root.is_visible(), "UIA main window")
    except Exception as exc:
        raise _OwnershipError("UIA main window visibility is unavailable or malformed") from exc
    if not visible:
        raise _OwnershipError("requested HWND UIA root is not visible")
    native = _native_window_info(requested_hwnd)
    if native["pid"] != pid or not native["visible"]:
        raise _OwnershipError("requested HWND native ownership or visibility changed")
    return root


def _info_record(wrapper: Any, expected_pid: int) -> dict[str, Any]:
    info = wrapper.element_info
    try:
        process_id = getattr(info, "process_id")
        record = {
            "name": str(getattr(info, "name", "") or ""),
            "text": str(wrapper.window_text()),
            "control_type": str(getattr(info, "control_type", "") or ""),
            "automation_id": str(getattr(info, "automation_id", "") or ""),
            "class_name": str(getattr(info, "class_name", "") or ""),
            "process_id": int(process_id),
            "nativehandle": int(getattr(info, "handle", 0) or 0),
            "runtimeID": list(getattr(info, "runtime_id", ()) or ()),
        }
    except (AttributeError, TypeError, ValueError) as exc:
        raise _OwnershipError("UIA snapshot contained a malformed record") from exc
    if record["process_id"] != expected_pid:
        raise _OwnershipError("UIA snapshot contained a foreign process record")
    return record


def _find_main(desktop: Any, pid: int, requested_hwnd: int) -> Any:
    if not isinstance(requested_hwnd, int) or isinstance(requested_hwnd, bool) or requested_hwnd <= 0:
        raise _OwnershipError("bounded worker requires the exact parent-pinned HWND")
    native = _native_window_info(requested_hwnd)
    if native["pid"] != pid or not native["visible"]:
        raise _OwnershipError("requested HWND is foreign or not visible")
    try:
        window = desktop.window(handle=requested_hwnd)
        root = window.wrapper_object()
    except Exception as exc:
        raise _TransientNotReady("pinned main window is not exposed through UIA yet") from exc
    return _validate_main_root(root, pid, requested_hwnd)


def _retry_until_ready(operation: Callable[[], Any], *, timeout: float, interval: float = 0.1) -> Any:
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("UIA readiness timeout must be finite and positive")
    deadline = time.monotonic() + timeout
    while True:
        try:
            return operation()
        except _OwnershipError:
            raise
        except _TransientNotReady as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"UIA target did not become ready: {exc}") from exc
            time.sleep(min(max(0.0, interval), remaining))


def _inspect_once(
    desktop: Any,
    process: Any,
    expected: dict[str, Any],
    executable: str,
    requested_hwnd: int,
    expected_rows: Sequence[str],
    emit_target: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    before_identity = _validate_identity(process, expected, executable)
    root = _find_main(desktop, expected["pid"], requested_hwnd)
    root_info = root.element_info
    target = {
        **before_identity,
        "hwnd": requested_hwnd,
        "name": str(getattr(root_info, "name", "") or ""),
        "class_name": "NMainWindow",
        "visible": True,
    }
    emit_target(target)
    try:
        descendants = list(root.descendants())
    except Exception as exc:
        raise _TransientNotReady("main window descendants are not ready") from exc
    # Check every enumerated record before bounded serialization can hide a foreign one.
    for item in descendants:
        try:
            item_pid = int(getattr(item.element_info, "process_id", 0))
        except (AttributeError, TypeError, ValueError) as exc:
            raise _OwnershipError("UIA descendants contained a malformed process identity") from exc
        if item_pid != expected["pid"]:
            raise _OwnershipError("UIA descendants contained a foreign process record")
    records = [_info_record(root, expected["pid"])] + [
        _info_record(item, expected["pid"]) for item in descendants[:512]
    ]
    playlists = [
        item for item in descendants
        if getattr(item.element_info, "class_name", "") == "NPlaylistWidget"
        and getattr(item.element_info, "automation_id", "") == "QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget"
    ]
    if len(playlists) > 1:
        raise _OwnershipError(f"owned Qt playlist count is {len(playlists)}, expected one")
    if not playlists:
        raise _TransientNotReady("owned Qt playlist is not ready")
    try:
        rows = list(playlists[0].descendants(control_type="ListItem"))
    except Exception as exc:
        raise _TransientNotReady("playlist rows are not ready") from exc
    for row in rows:
        try:
            row_pid = int(getattr(row.element_info, "process_id", 0))
        except (AttributeError, TypeError, ValueError) as exc:
            raise _OwnershipError("playlist rows contained a malformed process identity") from exc
        if row_pid != expected["pid"]:
            raise _OwnershipError("playlist rows contained a foreign process record")
    try:
        playlist_rows = [str(row.window_text()) for row in rows]
    except Exception as exc:
        raise _TransientNotReady("playlist row labels are not ready") from exc
    if playlist_rows != list(expected_rows):
        raise _TransientNotReady("exact expected playlist rows are not ready")

    after_identity = _validate_identity(process, expected, executable)
    _validate_main_root(root, expected["pid"], requested_hwnd)
    after_target = {**after_identity, "hwnd": requested_hwnd, "name": target["name"], "class_name": "NMainWindow", "visible": True}
    _emit({"event": "post_target", "target": after_target})
    return {
        "status": "PASS",
        "pid": expected["pid"],
        "hwnd": requested_hwnd,
        "target_name": target["name"],
        "target_before": target,
        "target_after": after_target,
        "snapshot": records,
        "playlist_rows": playlist_rows,
    }


def inspect_context_target(
    hwnd: int,
    pid: int,
    create_time: float,
    executable: str,
    expected_rows: Sequence[str],
    *,
    retry_timeout: float = 25.0,
    context_timeout: float = 10.0,
) -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "FAIL", "failure_kind": "platform_guard", "detail": "bounded context worker requires Windows"}
    import psutil
    from pywinauto import Desktop

    process = psutil.Process(pid)
    expected = {"pid": pid, "create_time": create_time}
    emitted = False

    def emit_target_once(target: dict[str, Any]) -> None:
        nonlocal emitted
        if not emitted:
            _emit({"event": "target", "target": target})
            emitted = True

    def attempt() -> dict[str, Any]:
        desktop = Desktop(backend="uia", allow_magic_lookup=False)
        return _context_inspect_once(
            desktop, process, expected, executable, hwnd, expected_rows, emit_target_once,
            context_timeout=context_timeout,
        )

    return _retry_until_ready(attempt, timeout=retry_timeout)


def inspect_target(
    hwnd: int,
    pid: int,
    create_time: float,
    executable: str,
    expected_rows: Sequence[str],
    *,
    retry_timeout: float = 25.0,
) -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "FAIL", "failure_kind": "platform_guard", "detail": "bounded UIA worker requires Windows"}
    import psutil
    from pywinauto import Desktop

    process = psutil.Process(pid)
    expected = {"pid": pid, "create_time": create_time}
    emitted = False

    def emit_target_once(target: dict[str, Any]) -> None:
        nonlocal emitted
        if not emitted:
            _emit({"event": "target", "target": target})
            emitted = True

    def attempt() -> dict[str, Any]:
        desktop = Desktop(backend="uia", allow_magic_lookup=False)
        return _inspect_once(
            desktop,
            process,
            expected,
            executable,
            hwnd,
            expected_rows,
            emit_target_once,
        )

    return _retry_until_ready(attempt, timeout=retry_timeout)


def _expected_rows(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise argparse.ArgumentTypeError("--expected-rows must be a JSON array of strings") from exc
    if not isinstance(value, list) or len(value) != 3 or any(not isinstance(item, str) for item in value):
        raise argparse.ArgumentTypeError("--expected-rows must contain exactly three strings")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwnd", required=True, type=lambda raw: int(raw, 0))
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--create-time", required=True, type=float)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--expected-rows", required=True, type=_expected_rows)
    parser.add_argument("--ui-timeout", type=float, default=25.0)
    parser.add_argument("--context-menu", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.hwnd <= 0 or args.pid <= 0 or not math.isfinite(args.create_time) or args.create_time <= 0:
            raise ValueError("target identity values must be positive")
        if not math.isfinite(args.ui_timeout) or args.ui_timeout <= 0:
            raise ValueError("--ui-timeout must be finite and positive")
        _emit({"event": "ready"})
        if args.context_menu:
            result = inspect_context_target(
                args.hwnd, args.pid, args.create_time, args.exe, args.expected_rows,
                retry_timeout=args.ui_timeout,
            )
        else:
            result = inspect_target(
                args.hwnd, args.pid, args.create_time, args.exe, args.expected_rows,
                retry_timeout=args.ui_timeout,
            )
    except Exception as exc:
        result = {"status": "FAIL", "failure_kind": "worker", "detail": f"{type(exc).__name__}: {exc}"}
        print(repr(exc), file=sys.stderr, flush=True)
    _emit(result)
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
