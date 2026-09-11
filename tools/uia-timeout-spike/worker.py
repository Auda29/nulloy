"""Owned Windows-only, read-only UIA snapshot worker.

This process has no application-level child-process creation and exposes no
UI action, selection, menu, input, or mutation operation. COM/UIA is imported
only here, after selecting the recommended windowless MTA apartment.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any


# Must be set before pywinauto/comtypes import in this child.
sys.coinit_flags = 0


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True), flush=True)


def _positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw, 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_finite(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite and positive") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _native_window_pid(hwnd: int) -> int:
    """Return the PID owning hwnd using pointer-sized, typed Win64 APIs."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    is_window = user32.IsWindow
    is_window.argtypes = [wintypes.HWND]
    is_window.restype = wintypes.BOOL
    get_pid = user32.GetWindowThreadProcessId
    get_pid.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    get_pid.restype = wintypes.DWORD
    if not is_window(wintypes.HWND(hwnd)):
        raise ValueError(f"HWND is not a live native window: {hwnd}")
    pid = wintypes.DWORD()
    if not get_pid(wintypes.HWND(hwnd), ctypes.byref(pid)):
        error = ctypes.get_last_error()
        raise OSError(error, f"GetWindowThreadProcessId failed for HWND {hwnd}")
    if not pid.value:
        raise ValueError(f"native HWND has no owner PID: {hwnd}")
    return int(pid.value)


def _identity(process: Any) -> tuple[int, float, str]:
    return (int(process.pid), float(process.create_time()), str(process.exe()))


def _read_only_snapshot(hwnd: int, pid: int) -> list[dict[str, Any]]:
    # Import UIA only in the worker, never in supervisor.py.
    from pywinauto import Desktop

    # A handle lookup is exact; do not fall back to Desktop.windows() or a
    # title/class search that could broaden to a foreign window.
    root = Desktop(backend="uia").window(handle=hwnd).wrapper_object()
    records: list[dict[str, Any]] = []
    wrappers = [root, *root.descendants()]  # intentionally unbounded UIA call
    for wrapper in wrappers[:64]:  # output size is a diagnostic cap only
        info = wrapper.element_info
        records.append(
            {
                "name": str(info.name or ""),
                "control_type": str(info.control_type or ""),
                "automation_id": str(info.automation_id or ""),
                "class_name": str(info.class_name or ""),
                "process_id": int(info.process_id),
            }
        )
    if not records or any(record["process_id"] != pid for record in records):
        raise RuntimeError("UIA snapshot contained a record outside the exact target PID")
    return records


def inspect_target(hwnd_raw: str, pid_raw: str, create_time_raw: str, exe: str) -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("native UIA worker requires Windows; Linux tests use injected workers")
    hwnd = _positive_int(hwnd_raw, "hwnd")
    pid = _positive_int(pid_raw, "pid")
    create_time = _positive_finite(create_time_raw, "create_time")
    if not exe:
        raise ValueError("exe must be non-empty")

    native_pid = _native_window_pid(hwnd)
    if native_pid != pid:
        raise RuntimeError(f"HWND PID mismatch: native={native_pid}, requested={pid}")

    import psutil

    process = psutil.Process(pid)
    before = _identity(process)
    expected = (pid, create_time, exe)
    if before != expected:
        raise RuntimeError(f"target identity mismatch before UIA query: expected={expected!r}, actual={before!r}")

    _emit({"event": "ready"})
    snapshot = _read_only_snapshot(hwnd, pid)

    native_pid_after = _native_window_pid(hwnd)
    if native_pid_after != pid:
        raise RuntimeError(
            f"HWND owner changed during UIA query: native={native_pid_after}, requested={pid}"
        )
    after = _identity(psutil.Process(pid))
    if after != before or after != expected:
        raise RuntimeError(f"target identity changed during UIA query: before={before!r}, after={after!r}")
    return {"status": "PASS", "hwnd": hwnd, "pid": pid, "snapshot": snapshot}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwnd", required=True)
    parser.add_argument("--pid", required=True)
    parser.add_argument("--create-time", required=True)
    parser.add_argument("--exe", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = inspect_target(args.hwnd, args.pid, args.create_time, args.exe)
    except Exception as exc:  # preserve the worker error in stderr and status
        _emit({"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
