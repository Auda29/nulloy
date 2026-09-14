#!/usr/bin/env python3
"""Owned, read-only UIA snapshot worker for the bounded inspector path."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
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
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.hwnd <= 0 or args.pid <= 0 or not math.isfinite(args.create_time) or args.create_time <= 0:
            raise ValueError("target identity values must be positive")
        if not math.isfinite(args.ui_timeout) or args.ui_timeout <= 0:
            raise ValueError("--ui-timeout must be finite and positive")
        _emit({"event": "ready"})
        result = inspect_target(
            args.hwnd,
            args.pid,
            args.create_time,
            args.exe,
            args.expected_rows,
            retry_timeout=args.ui_timeout,
        )
    except Exception as exc:
        result = {"status": "FAIL", "failure_kind": "worker", "detail": f"{type(exc).__name__}: {exc}"}
        print(repr(exc), file=sys.stderr, flush=True)
    _emit(result)
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
