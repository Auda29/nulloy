import ctypes
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("owned_pointer_under_test", HERE / "owned_pointer.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class _ApiFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class _SendApi:
    def __init__(self, responses):
        self.calls = []
        values = iter(responses)
        self.SendInput = _ApiFunction(lambda count, inputs, size: self._send(next(values), count, inputs, size))
        for name in (
            "SetCursorPos", "GetCursorPos", "WindowFromPoint", "GetAncestor",
            "GetForegroundWindow", "SetForegroundWindow", "IsWindowVisible", "IsIconic",
            "GetAsyncKeyState", "GetWindowRect", "GetProcessWindowStation", "GetCurrentThreadId",
            "GetThreadDesktop", "OpenInputDesktop", "CloseDesktop", "GetUserObjectInformationW",
            "ProcessIdToSessionId", "GetCurrentProcessId",
        ):
            setattr(self, name, _ApiFunction(lambda *args: 0))

    def _send(self, response, count, inputs, size):
        self.calls.append((count, inputs, size))
        return response


class _DesktopApiFake:
    input_desktop = 33
    thread_desktop = 22
    winsta = 11

    def __init__(self):
        self.player_session = 1
        self.closed_desktops = []
        self.closed_handles = []
        self.GetProcessWindowStation = _ApiFunction(lambda: self.winsta)
        self.GetCurrentThreadId = _ApiFunction(lambda: 7)
        self.GetThreadDesktop = _ApiFunction(lambda thread_id: self.thread_desktop)
        self.OpenInputDesktop = _ApiFunction(lambda flags, inherit, access: self.input_desktop)
        self.CloseDesktop = _ApiFunction(lambda handle: self.closed_desktops.append(handle) or 1)
        self.GetCurrentProcessId = _ApiFunction(lambda: 9000)
        self.ProcessIdToSessionId = _ApiFunction(self._session)
        self.GetUserObjectInformationW = _ApiFunction(self._user_info)
        for name in (
            "SendInput", "SetCursorPos", "GetCursorPos", "WindowFromPoint", "GetAncestor",
            "GetForegroundWindow", "SetForegroundWindow", "IsWindowVisible", "IsIconic",
            "GetAsyncKeyState", "GetWindowRect",
        ):
            setattr(self, name, _ApiFunction(lambda *args: 0))

    def _session(self, pid, output):
        output._obj.value = self.player_session if int(getattr(pid, "value", pid)) == 4242 else 1
        return 1

    def _user_info(self, handle, index, buffer, size, needed):
        names = {self.winsta: "WinSta0", self.thread_desktop: "Default", self.input_desktop: "Default"}
        if index == MODULE.UOI_NAME:
            buffer.value = names[handle]
            needed._obj.value = (len(buffer.value) + 1) * ctypes.sizeof(ctypes.c_wchar)
        else:
            ctypes.cast(buffer, ctypes.POINTER(MODULE.DWORD))[0] = MODULE.WSF_VISIBLE
            needed._obj.value = ctypes.sizeof(MODULE.DWORD)
        return 1


class _TargetApiFake:
    def __init__(self):
        self.foreground = 99
        self.visible = True
        self.iconic = False
        self.hit = 100
        self.root = 4242
        self.held = 0

    def IsWindowVisible(self, hwnd):
        return self.visible

    def IsIconic(self, hwnd):
        return self.iconic

    def GetForegroundWindow(self):
        return self.foreground

    def SetForegroundWindow(self, hwnd):
        self.foreground = hwnd
        return 1

    def WindowFromPoint(self, point):
        return self.hit

    def GetAncestor(self, hwnd, relationship):
        return self.root

    def GetAsyncKeyState(self, key):
        return self.held


class PointerContractTests(unittest.TestCase):
    def test_runner_guard_requires_exact_authorized_environment(self):
        with mock.patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "RUNNER_OS": "Windows",
        }, clear=False):
            with mock.patch.object(MODULE, "is_windows_native", return_value=True):
                self.assertEqual(MODULE.validate_runner_environment(), "github-hosted/Windows")
        for key, value in (("GITHUB_ACTIONS", "false"), ("RUNNER_ENVIRONMENT", "self-hosted"), ("RUNNER_OS", "Linux")):
            environment = {
                "GITHUB_ACTIONS": "true",
                "RUNNER_ENVIRONMENT": "github-hosted",
                "RUNNER_OS": "Windows",
                key: value,
            }
            with self.subTest(key=key), mock.patch.dict(os.environ, environment, clear=False):
                with mock.patch.object(MODULE, "is_windows_native", return_value=True), self.assertRaises(MODULE.BlockedError):
                    MODULE.validate_runner_environment()

    def test_input_layout_and_sendinput_signature_are_real_pointer_sized_contracts(self):
        self.assertEqual(ctypes.sizeof(MODULE.ULONG_PTR), ctypes.sizeof(ctypes.c_void_p))
        self.assertEqual(MODULE.INPUT._fields_[0][0], "type")
        self.assertEqual(ctypes.sizeof(MODULE.INPUT), ctypes.sizeof(ctypes.c_void_p) * 5)
        batch = MODULE.make_right_click_batch()
        self.assertEqual(len(batch), 2)
        self.assertEqual(batch[0].type, MODULE.INPUT_MOUSE)
        self.assertEqual(batch[1].type, MODULE.INPUT_MOUSE)
        self.assertEqual(batch[0].union.mi.dwFlags, MODULE.MOUSEEVENTF_RIGHTDOWN)
        self.assertEqual(batch[1].union.mi.dwFlags, MODULE.MOUSEEVENTF_RIGHTUP)

        api = _SendApi([2])
        result = MODULE.send_right_click(api=api)
        self.assertEqual(result["input_count"], 2)
        self.assertEqual(api.SendInput.argtypes[0], ctypes.c_uint)
        self.assertEqual(api.SendInput.argtypes[2], ctypes.c_int)
        self.assertIs(api.SendInput.restype, ctypes.c_uint)

    def test_partial_send_records_and_releases_only_own_injected_down(self):
        api = _SendApi([1, 1])
        with self.assertRaises(MODULE.BlockedError) as raised:
            MODULE.send_right_click(api=api)
        self.assertEqual(raised.exception.diagnostics["input_count"], 1)
        self.assertTrue(raised.exception.diagnostics["partial_release_attempted"])
        self.assertEqual(len(api.calls), 2)
        self.assertEqual(api.calls[1][0], 1)
        sent = api.calls[1][1]
        self.assertEqual(sent[0].union.mi.dwFlags, MODULE.MOUSEEVENTF_RIGHTUP)

    def test_target_requires_strict_interior_and_native_root_hit(self):
        point = MODULE.choose_target_point(
            {"left": 10, "top": 10, "right": 110, "bottom": 60},
            {"left": 0, "top": 0, "right": 200, "bottom": 100},
        )
        self.assertGreater(point.x, 10)
        self.assertLess(point.x, 110)
        self.assertGreater(point.y, 10)
        self.assertLess(point.y, 60)
        with self.assertRaises(MODULE.BlockedError):
            MODULE.choose_target_point(
                {"left": 0, "top": 0, "right": 1, "bottom": 1},
                {"left": 1, "top": 1, "right": 2, "bottom": 2},
            )

    def test_target_preflight_requests_foreground_and_rejects_foreign_or_held_input(self):
        api = _TargetApiFake()
        point = MODULE.POINT(50, 30)
        result = MODULE.validate_pointer_target(
            api,
            root_hwnd=4242,
            point=point,
            row_rect={"left": 10, "top": 10, "right": 110, "bottom": 60},
            main_rect={"left": 0, "top": 0, "right": 200, "bottom": 100},
        )
        self.assertTrue(result["foreground_requested"])
        self.assertEqual(result["ancestor_root"], 4242)

        api.root = 7777
        with self.assertRaises(MODULE.BlockedError):
            MODULE.validate_pointer_target(
                api,
                root_hwnd=4242,
                point=point,
                row_rect={"left": 10, "top": 10, "right": 110, "bottom": 60},
                main_rect={"left": 0, "top": 0, "right": 200, "bottom": 100},
                request_foreground=False,
            )
        api.root = 4242
        api.held = 0x8000
        with self.assertRaises(MODULE.BlockedError):
            MODULE.validate_pointer_target(
                api,
                root_hwnd=4242,
                point=point,
                row_rect={"left": 10, "top": 10, "right": 110, "bottom": 60},
                main_rect={"left": 0, "top": 0, "right": 200, "bottom": 100},
                request_foreground=False,
            )

    def test_desktop_preflight_rejects_session_zero_and_closes_acquired_handle(self):
        api = _DesktopApiFake()
        api.player_session = 0
        with mock.patch.object(MODULE, "is_windows_native", return_value=True), mock.patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Windows"
        }, clear=False), self.assertRaises(MODULE.BlockedError):
            MODULE.inspect_interactive_desktop(4242, api=api)
        self.assertEqual(api.closed_desktops, [api.input_desktop])
        self.assertEqual(api.closed_handles, [])


if __name__ == "__main__":
    unittest.main()
