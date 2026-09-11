#!/usr/bin/env python3
"""Fail-closed Win32 right-click transport for the owned player window.

This module deliberately has no UIA, pywinauto, keyboard, or menu-selection
logic.  It only validates the disposable GitHub-hosted Windows environment,
checks an owned target, moves the cursor, and emits one right-button batch.
Boundary checks reduce but cannot eliminate external desktop races; this transport is
therefore restricted to the isolated disposable runner and makes no generic desktop
safety guarantee.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any, Callable


class ContractError(ValueError):
    """The native target or API contract is inconsistent."""


class BlockedError(RuntimeError):
    """A safety precondition prevented native pointer input."""


ULONG_PTR = ctypes.c_size_t
DWORD = ctypes.c_uint32
UINT = ctypes.c_uint32
BOOL = ctypes.c_int32
LONG = ctypes.c_int32
SHORT = ctypes.c_int16
HANDLE = ctypes.c_void_p
HWND = ctypes.c_void_p
HWINSTA = ctypes.c_void_p
HDESK = ctypes.c_void_p
INPUT_MOUSE = 0
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
GA_ROOT = 2
UOI_FLAGS = 1
UOI_NAME = 2
WSF_VISIBLE = 0x0001
DESKTOP_READOBJECTS = 0x0001
DESKTOP_SWITCHDESKTOP = 0x0100
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
VK_XBUTTON1 = 0x05
VK_XBUTTON2 = 0x06
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", DWORD), ("union", _INPUTUNION)]


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", LONG),
        ("top", LONG),
        ("right", LONG),
        ("bottom", LONG),
    ]


class USEROBJECTFLAGS(ctypes.Structure):
    _fields_ = [
        ("fInherit", BOOL),
        ("fReserved", BOOL),
        ("dwFlags", DWORD),
    ]


class _NativeCallError(BlockedError):
    pass


class PointerInputError(BlockedError):
    """SendInput did not complete; diagnostics preserve partial-send cleanup."""

    def __init__(self, message: str, diagnostics: dict[str, Any]):
        super().__init__(message)
        self.diagnostics = diagnostics


def is_windows_native() -> bool:
    return os.name == "nt"


def validate_runner_environment() -> str:
    if not is_windows_native():
        raise BlockedError("owned pointer input requires native Windows")
    expected = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Windows",
    }
    missing_or_wrong = [key for key, value in expected.items() if os.environ.get(key) != value]
    if missing_or_wrong:
        raise BlockedError(
            "owned pointer input requires GITHUB_ACTIONS=true, "
            "RUNNER_ENVIRONMENT=github-hosted, RUNNER_OS=Windows"
        )
    return "github-hosted/Windows"


def _set_signature(api: Any, name: str, argtypes: list[Any], restype: Any) -> None:
    function = getattr(api, name, None)
    if function is None:
        raise BlockedError(f"user32 API is missing {name}")
    function.argtypes = argtypes
    function.restype = restype


def configure_user32(api: Any) -> Any:
    """Apply explicit Win64-safe ctypes declarations to every used entry point."""
    _set_signature(api, "SendInput", [UINT, ctypes.POINTER(INPUT), ctypes.c_int], UINT)
    _set_signature(api, "SetCursorPos", [ctypes.c_int, ctypes.c_int], BOOL)
    _set_signature(api, "GetCursorPos", [ctypes.POINTER(POINT)], BOOL)
    _set_signature(api, "WindowFromPoint", [POINT], HWND)
    _set_signature(api, "GetAncestor", [HWND, UINT], HWND)
    _set_signature(api, "GetForegroundWindow", [], HWND)
    _set_signature(api, "SetForegroundWindow", [HWND], BOOL)
    _set_signature(api, "IsWindowVisible", [HWND], BOOL)
    _set_signature(api, "IsIconic", [HWND], BOOL)
    _set_signature(api, "GetAsyncKeyState", [ctypes.c_int], SHORT)
    _set_signature(api, "GetWindowRect", [HWND, ctypes.POINTER(RECT)], BOOL)
    _set_signature(api, "GetProcessWindowStation", [], HWINSTA)
    _set_signature(api, "GetThreadDesktop", [DWORD], HDESK)
    _set_signature(api, "OpenInputDesktop", [DWORD, BOOL, DWORD], HDESK)
    _set_signature(api, "CloseDesktop", [HDESK], BOOL)
    _set_signature(
        api,
        "GetUserObjectInformationW",
        [HANDLE, ctypes.c_int32, wintypes.LPVOID, DWORD, ctypes.POINTER(DWORD)],
        BOOL,
    )
    return api


def configure_kernel32(api: Any) -> Any:
    """Apply explicit signatures to the process/session APIs from kernel32."""
    _set_signature(api, "GetCurrentThreadId", [], DWORD)
    _set_signature(api, "ProcessIdToSessionId", [DWORD, ctypes.POINTER(DWORD)], BOOL)
    _set_signature(api, "GetCurrentProcessId", [], DWORD)
    return api


def _load_user32() -> Any:
    if not is_windows_native():
        raise BlockedError("native user32 APIs require Windows")
    return configure_user32(ctypes.WinDLL("user32", use_last_error=True))


def _load_kernel32() -> Any:
    if not is_windows_native():
        raise BlockedError("native kernel32 APIs require Windows")
    return configure_kernel32(ctypes.WinDLL("kernel32", use_last_error=True))


def _last_error(name: str) -> _NativeCallError:
    get_last_error = getattr(ctypes, "get_last_error", lambda: 0)
    return _NativeCallError(f"{name} failed (Win32 error {get_last_error()})")


def _get_user_object_name(api: Any, handle: Any) -> str:
    size = 256
    while size <= 4096:
        buffer = ctypes.create_unicode_buffer(size)
        needed = DWORD(0)
        if api.GetUserObjectInformationW(handle, UOI_NAME, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
            return buffer.value
        if needed.value <= ctypes.sizeof(buffer):
            raise _last_error("GetUserObjectInformationW(UOI_NAME)")
        size = int(needed.value // ctypes.sizeof(ctypes.c_wchar) + 1)
    raise BlockedError("desktop/window-station name exceeded bounded buffer")


def _get_user_object_flags(api: Any, handle: Any) -> int:
    flags = USEROBJECTFLAGS()
    needed = DWORD(0)
    if not api.GetUserObjectInformationW(
        handle, UOI_FLAGS, ctypes.byref(flags), ctypes.sizeof(flags), ctypes.byref(needed)
    ):
        raise _last_error("GetUserObjectInformationW(UOI_FLAGS)")
    return int(flags.dwFlags)


def _session_id(kernel32: Any, pid: int) -> int:
    session = DWORD(0)
    if not kernel32.ProcessIdToSessionId(DWORD(pid), ctypes.byref(session)):
        raise _last_error("ProcessIdToSessionId")
    return int(session.value)


def inspect_interactive_desktop(
    player_pid: int, *, api: Any | None = None, kernel32: Any | None = None
) -> dict[str, Any]:
    """Verify WinSta0/input/thread/player desktop state and close only input handle."""
    validate_runner_environment()
    if api is None:
        api = _load_user32()
    if kernel32 is None:
        kernel32 = _load_kernel32()
    configure_user32(api)
    configure_kernel32(kernel32)
    input_desktop = None
    primary_error: BaseException | None = None
    try:
        winsta = api.GetProcessWindowStation()
        if not winsta:
            raise _last_error("GetProcessWindowStation")
        thread_id = kernel32.GetCurrentThreadId()
        thread_desktop = api.GetThreadDesktop(thread_id)
        if not thread_desktop:
            raise _last_error("GetThreadDesktop")
        input_desktop = api.OpenInputDesktop(
            0, BOOL(False), DESKTOP_READOBJECTS | DESKTOP_SWITCHDESKTOP
        )
        if not input_desktop:
            raise _last_error("OpenInputDesktop")
        winsta_name = _get_user_object_name(api, winsta)
        thread_name = _get_user_object_name(api, thread_desktop)
        input_name = _get_user_object_name(api, input_desktop)
        winsta_flags = _get_user_object_flags(api, winsta)
        current_pid = int(kernel32.GetCurrentProcessId())
        current_session = _session_id(kernel32, current_pid)
        player_session = _session_id(kernel32, int(player_pid))
        result = {
            "window_station": winsta_name,
            "window_station_visible": bool(winsta_flags & WSF_VISIBLE),
            "thread_desktop": thread_name,
            "input_desktop": input_name,
            "same_input_and_thread_desktop": input_name == thread_name,
            "current_session": current_session,
            "player_session": player_session,
            "non_session_zero": current_session != 0 and player_session != 0,
            "player_same_session": player_session == current_session,
        }
        if not (
            result["window_station"] == "WinSta0"
            and result["window_station_visible"]
            and result["same_input_and_thread_desktop"]
            and result["non_session_zero"]
            and result["player_same_session"]
        ):
            raise BlockedError(f"interactive desktop preflight rejected: {result!r}")
        return result
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if input_desktop is not None:
            cleanup_error: BaseException | None = None
            try:
                if not api.CloseDesktop(input_desktop):
                    cleanup_error = _last_error("CloseDesktop(input desktop)")
            except BaseException as exc:
                cleanup_error = exc
            if cleanup_error is not None:
                if primary_error is not None:
                    setattr(primary_error, "cleanup_error", cleanup_error)
                else:
                    raise cleanup_error


def _rect_value(rect: Any, name: str) -> int:
    try:
        return int(getattr(rect, name))
    except AttributeError:
        try:
            return int(rect[name])
        except (KeyError, TypeError) as exc:
            raise ContractError(f"rectangle lacks {name}") from exc


def choose_target_point(row_rect: Any, main_rect: Any) -> POINT:
    left = max(_rect_value(row_rect, "left"), _rect_value(main_rect, "left"))
    top = max(_rect_value(row_rect, "top"), _rect_value(main_rect, "top"))
    right = min(_rect_value(row_rect, "right"), _rect_value(main_rect, "right"))
    bottom = min(_rect_value(row_rect, "bottom"), _rect_value(main_rect, "bottom"))
    if not (left + 1 < right and top + 1 < bottom):
        raise BlockedError("selected row has no strictly interior point inside main window")
    return POINT((left + right) // 2, (top + bottom) // 2)


def _point_inside(point: POINT, rect: Any) -> bool:
    return (
        _rect_value(rect, "left") < point.x < _rect_value(rect, "right")
        and _rect_value(rect, "top") < point.y < _rect_value(rect, "bottom")
    )


def _target_window(api: Any, point: POINT) -> tuple[int, int]:
    hit = int(api.WindowFromPoint(point) or 0)
    root = int(api.GetAncestor(hit, GA_ROOT) or 0) if hit else 0
    return hit, root


def _reject_held_input(api: Any, *, allow_owned_pending_rightdown: bool = False) -> None:
    mouse_buttons = (VK_LBUTTON, VK_MBUTTON, VK_XBUTTON1, VK_XBUTTON2)
    if not allow_owned_pending_rightdown:
        mouse_buttons = (VK_LBUTTON, VK_RBUTTON, VK_MBUTTON, VK_XBUTTON1, VK_XBUTTON2)
    keys = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, *mouse_buttons)
    held = [hex(key) for key in keys if int(api.GetAsyncKeyState(key)) & 0x8000]
    if held:
        raise BlockedError(f"physical modifier or mouse button is held: {held}")


def _ensure_foreground(api: Any, root_hwnd: int) -> bool:
    requested = False
    if int(api.GetForegroundWindow() or 0) != root_hwnd:
        requested = True
        if not api.SetForegroundWindow(root_hwnd):
            raise _last_error("SetForegroundWindow")
        if int(api.GetForegroundWindow() or 0) != root_hwnd:
            raise BlockedError("SetForegroundWindow did not produce the owned foreground window")
    return requested


def validate_pointer_target(
    api: Any,
    *,
    root_hwnd: int,
    point: POINT,
    row_rect: Any,
    main_rect: Any,
    request_foreground: bool = True,
    allow_owned_pending_rightdown: bool = False,
) -> dict[str, Any]:
    if not api.IsWindowVisible(root_hwnd):
        raise BlockedError("owned main window is not visible")
    if api.IsIconic(root_hwnd):
        raise BlockedError("owned main window is iconic/minimized")
    if not _point_inside(point, row_rect) or not _point_inside(point, main_rect):
        raise BlockedError("pointer point is not strictly inside the selected row and main window")
    foreground_requested = _ensure_foreground(api, root_hwnd) if request_foreground else False
    if int(api.GetForegroundWindow() or 0) != root_hwnd:
        raise BlockedError("owned main window is not foreground")
    hit, root = _target_window(api, point)
    if hit == 0 or root != root_hwnd:
        raise BlockedError(f"WindowFromPoint/GetAncestor target mismatch: hit={hit:#x}, root={root:#x}")
    _reject_held_input(api, allow_owned_pending_rightdown=allow_owned_pending_rightdown)
    return {
        "root_hwnd": root_hwnd,
        "point": {"x": int(point.x), "y": int(point.y)},
        "window_from_point": hit,
        "ancestor_root": root,
        "foreground": int(api.GetForegroundWindow() or 0),
        "foreground_requested": foreground_requested,
    }


def _cursor(api: Any) -> POINT:
    point = POINT()
    if not api.GetCursorPos(ctypes.byref(point)):
        raise _last_error("GetCursorPos")
    return point


def _same_point(left: POINT, right: POINT) -> bool:
    return int(left.x) == int(right.x) and int(left.y) == int(right.y)


def move_cursor_checked(
    api: Any,
    *,
    root_hwnd: int,
    point: POINT,
    row_rect: Any,
    main_rect: Any,
    revalidate: Callable[[], Any],
) -> dict[str, Any]:
    boundary = revalidate()
    boundary_row_rect = getattr(boundary, "get", lambda key, default: default)("row_rect", row_rect)
    boundary_main_rect = getattr(boundary, "get", lambda key, default: default)("main_rect", main_rect)
    if not api.SetCursorPos(point.x, point.y):
        raise _last_error("SetCursorPos")
    actual = _cursor(api)
    if not _same_point(actual, point):
        raise BlockedError(f"cursor moved during positioning: expected={point.x, point.y}, actual={actual.x, actual.y}")
    validate_pointer_target(
        api,
        root_hwnd=root_hwnd,
        point=actual,
        row_rect=boundary_row_rect,
        main_rect=boundary_main_rect,
        request_foreground=False,
    )
    return {"positioned": True, "cursor": {"x": int(actual.x), "y": int(actual.y)}}


def make_right_click_batch() -> Any:
    batch = (INPUT * 2)()
    batch[0].type = INPUT_MOUSE
    batch[0].mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTDOWN, 0, 0)
    batch[1].type = INPUT_MOUSE
    batch[1].mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTUP, 0, 0)
    return batch


def send_right_click(
    *, api: Any | None = None, release_revalidate: Callable[[], Any] | None = None
) -> dict[str, Any]:
    api = api or _load_user32()
    configure_user32(api)
    batch = make_right_click_batch()
    count = int(api.SendInput(2, batch, ctypes.sizeof(INPUT)))
    diagnostics = {
        "input_requested": 2,
        "input_count": count,
        "input_size": ctypes.sizeof(INPUT),
        "partial_release_attempted": False,
        "partial_release_count": None,
        "release_validation": None,
        "cleanup_blocked": False,
        "outstanding_injected_input": False,
    }
    if count == 2:
        return diagnostics
    if count == 1:
        diagnostics["partial_release_attempted"] = True
        diagnostics["outstanding_injected_input"] = True
        if release_revalidate is None:
            diagnostics["cleanup_blocked"] = True
            diagnostics["cleanup_block_reason"] = "missing fresh release boundary validator"
            raise PointerInputError("partial SendInput cleanup was blocked", diagnostics)
        try:
            diagnostics["release_validation"] = release_revalidate()
        except Exception as exc:
            diagnostics["cleanup_blocked"] = True
            diagnostics["cleanup_block_reason"] = repr(exc)
            raise PointerInputError("partial SendInput cleanup was blocked", diagnostics) from exc
        release = (INPUT * 1)()
        release[0].type = INPUT_MOUSE
        release[0].mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTUP, 0, 0)
        try:
            diagnostics["partial_release_count"] = int(api.SendInput(1, release, ctypes.sizeof(INPUT)))
        except Exception as exc:
            diagnostics["partial_release_failure"] = repr(exc)
            raise PointerInputError("partial SendInput cleanup failed", diagnostics) from exc
        if diagnostics["partial_release_count"] != 1:
            diagnostics["partial_release_failure"] = (
                f"release returned {diagnostics['partial_release_count']}, expected 1"
            )
            raise PointerInputError("partial SendInput cleanup failed", diagnostics)
    raise PointerInputError("SendInput did not deliver exactly one right-click batch", diagnostics)


def click_right_checked(
    api: Any,
    *,
    root_hwnd: int,
    point: POINT,
    revalidate: Callable[[], Any],
    release_revalidate: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    revalidate()
    actual = _cursor(api)
    if not _same_point(actual, point):
        raise BlockedError("cursor moved before right-click boundary")
    if int(api.GetForegroundWindow() or 0) != root_hwnd:
        raise BlockedError("owned main window lost foreground before right-click boundary")
    hit, root = _target_window(api, actual)
    if hit == 0 or root != root_hwnd:
        raise BlockedError("target window changed before right-click boundary")
    _reject_held_input(api)
    return send_right_click(api=api, release_revalidate=release_revalidate)
