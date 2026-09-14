"""Test-first contracts for the strictly opt-in row-focus diagnostic."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent

def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

worker = _load("focus_diagnostic_worker_red", HERE / "uia_worker.py")
_probe_validator = sys.modules.get("nulloy_trash_probe_validator")
inspector = _load("focus_diagnostic_inspector_red", HERE / "inspect_player.py")
if _probe_validator is not None:
    sys.modules["nulloy_trash_probe_validator"] = _probe_validator

EXPECTED = ["one.wav (0:30)", "two.wav (0:30)", "three.wav (0:30)"]
NATIVE_SNAPSHOT = {
    "root_thread_id": 77,
    "owned_thread_focus": {
        "flags": 3,
        "active": {"hwnd": 0, "pid": 0},
        "focus": {"hwnd": 0, "pid": 0},
        "capture": {"hwnd": 0, "pid": 0},
        "menu_owner": {"hwnd": 0, "pid": 0},
        "move_size": {"hwnd": 0, "pid": 0},
        "caret": {"hwnd": 0, "pid": 0},
        "caret_rect": {"left": -1, "top": 2, "right": 3, "bottom": 4},
    },
    "foreground": {"hwnd": 9001, "pid": 9999},
}
IDENTITY = {"pid": 4242, "create_time": 12.5}
EXE = "C:/Nulloy/Nulloy.exe"


class _Info:
    def __init__(self, name, *, pid=4242, control_type="Pane", class_name="", automation_id="", hwnd=0):
        self.name = name
        self.process_id = pid
        self.control_type = control_type
        self.class_name = class_name
        self.automation_id = automation_id
        self.handle = hwnd
        self.runtime_id = [pid, id(self)]
        self.element = None


class _FocusElement:
    def __init__(self, focused=False, actions=None, *, exception=None, return_value=None):
        self.CurrentHasKeyboardFocus = focused
        self.actions = actions if actions is not None else []
        self.exception = exception
        self.return_value = return_value

    def SetFocus(self):
        self.actions.append("SetFocus")
        if self.exception is not None:
            raise self.exception
        return self.return_value


class _Control:
    def __init__(self, name, element, *, pid=4242, control_type="Pane", class_name="", automation_id=""):
        self.element_info = _Info(name, pid=pid, control_type=control_type, class_name=class_name,
                                  automation_id=automation_id)
        self.element_info.element = element
        self._name = name

    def window_text(self):
        return self._name


class _Playlist(_Control):
    def __init__(self, rows, element):
        super().__init__("Playlist", element, control_type="List", class_name="NPlaylistWidget",
                         automation_id="QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget")
        self.rows = rows

    def descendants(self, control_type=None):
        return list(self.rows)


class _Root(_Control):
    def __init__(self, playlist, element):
        super().__init__("Nulloy", element, control_type="Pane", class_name="NMainWindow")
        self.playlist = playlist
        self.element_info.handle = 1001

    def descendants(self):
        return [self.playlist]

    def is_visible(self):
        return True


class _Process:
    pid = 4242

    def create_time(self):
        return 12.5

    def exe(self):
        return EXE


class FocusDiagnosticREDTests(unittest.TestCase):
    def _fixture(self, *, row_pid=4242, row_exception=None):
        actions = []
        rows = []
        for name in EXPECTED:
            row = _Control(name, _FocusElement(False, actions, exception=row_exception),
                           pid=row_pid, control_type="ListItem")
            rows.append(row)
        playlist = _Playlist(rows, _FocusElement(False, actions))
        root = _Root(playlist, _FocusElement(False, actions))
        desktop = mock.Mock()
        return actions, rows, playlist, root, desktop

    def test_qt_faithful_noop_captures_false_before_after_without_selection_or_context(self):
        actions, rows, playlist, root, desktop = self._fixture()
        native_calls = []

        def native_focus(hwnd, expected_pid):
            native_calls.append((hwnd, expected_pid))
            return NATIVE_SNAPSHOT

        with mock.patch.object(worker, "_find_main", return_value=root), mock.patch.object(
            worker, "_validate_main_root", return_value=root
        ):
            result = worker._focus_diagnostic_once(
                desktop, _Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                native_focus=native_focus,
            )

        self.assertTrue(result["diagnostic_only"])
        self.assertFalse(result["context_acceptance"])
        self.assertEqual(actions, ["SetFocus"])
        self.assertEqual(native_calls, [(1001, 4242), (1001, 4242)])
        self.assertEqual(result["focus_diagnostic"]["row"]["before"], False)
        self.assertEqual(result["focus_diagnostic"]["row"]["after"], False)
        self.assertEqual(result["focus_diagnostic"]["playlist"]["before"], False)
        self.assertEqual(result["focus_diagnostic"]["root"]["after"], False)
        self.assertEqual(result["focus_diagnostic"]["set_focus"]["call_count"], 1)
        self.assertNotIn("SelectionItem", " ".join(actions))
        self.assertNotIn("context", result)

    def test_foreign_first_row_is_rejected_before_native_setfocus(self):
        actions, rows, playlist, root, desktop = self._fixture(row_pid=9999)
        native_focus = mock.Mock(side_effect=AssertionError("native focus query must not run"))

        with self.assertRaises(worker._OwnershipError):
            worker._focus_diagnostic_once(
                desktop, _Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                native_focus=native_focus,
            )

        self.assertEqual(actions, [])
        native_focus.assert_not_called()

    def test_setfocus_exception_is_retained_and_post_observation_is_still_captured(self):
        actions, rows, playlist, root, desktop = self._fixture(row_exception=RuntimeError("Qt SetFocus failed"))
        native_focus = mock.Mock(return_value=NATIVE_SNAPSHOT)

        with mock.patch.object(worker, "_find_main", return_value=root), mock.patch.object(
            worker, "_validate_main_root", return_value=root
        ):
            result = worker._focus_diagnostic_once(
                desktop, _Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                native_focus=native_focus,
            )

        self.assertEqual(actions, ["SetFocus"])
        self.assertEqual(result["focus_diagnostic"]["set_focus"]["call_count"], 1)
        self.assertIn("Qt SetFocus failed", result["focus_diagnostic"]["set_focus"]["exception"])
        self.assertIn("after", result["focus_diagnostic"]["row"])

    def test_parent_payload_validator_preserves_diagnostic_scope_and_false_focus_evidence(self):
        actions, rows, playlist, root, desktop = self._fixture()
        native_focus = mock.Mock(return_value=NATIVE_SNAPSHOT)
        with mock.patch.object(worker, "_find_main", return_value=root), mock.patch.object(
            worker, "_validate_main_root", return_value=root
        ):
            payload = worker._focus_diagnostic_once(
                desktop, _Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                native_focus=native_focus,
            )
        diagnostic = inspector._validate_bounded_focus_payload(payload, EXPECTED)
        self.assertFalse(diagnostic["row"]["before"])
        self.assertFalse(diagnostic["row"]["after"])
        payload["focus_diagnostic"]["row"]["before"] = 1
        with self.assertRaises(inspector.ContractError):
            inspector._validate_bounded_focus_payload(payload, EXPECTED)

    def test_worker_focus_flag_is_separate_from_context_flag(self):
        parsed = worker._parser().parse_args([
            "--hwnd", "0x3e9", "--pid", "4242", "--create-time", "12.5",
            "--exe", EXE, "--expected-rows", __import__("json").dumps(EXPECTED),
            "--focus-diagnostic",
        ])
        self.assertTrue(parsed.focus_diagnostic)
        self.assertFalse(parsed.context_menu)

    def test_inspector_focus_flag_is_incompatible_with_every_action_mode(self):
        base = ["--package", "package.zip", "--output", "evidence", "--source-sha", "a" * 40,
                "--archive-sha256", "b" * 64, "--bounded-focus-diagnostic"]
        parsed = inspector.parse_args(base)
        self.assertTrue(parsed.bounded_focus_diagnostic)
        for incompatible in (
            "--inspect-context-menu", "--allow-owned-pointer-input", "--bounded-read-only",
            "--bounded-context-menu",
        ):
            with self.subTest(incompatible=incompatible), self.assertRaises(SystemExit):
                inspector.parse_args([*base, incompatible])

    def test_active_focus_diagnostic_blocks_before_package_launch_on_non_windows(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            args = inspector.parse_args([
                "--package", str(Path(temporary) / "missing.zip"),
                "--output", str(Path(temporary) / "evidence"),
                "--source-sha", "a" * 40, "--archive-sha256", "b" * 64,
                "--bounded-focus-diagnostic",
            ])
            with mock.patch.object(inspector, "is_windows_native", return_value=False), mock.patch.object(
                inspector.subprocess, "Popen"
            ) as popen:
                code, report = inspector.run_inspection(args)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "BLOCKED")
        popen.assert_not_called()

    def test_native_focus_snapshot_uses_gui_thread_info_and_pointer_sized_signatures(self):
        class Export:
            def __init__(self, function):
                self.function = function
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                return self.function(*args)

        class User32:
            def __init__(self):
                self.IsWindow = Export(lambda hwnd: int(getattr(hwnd, "value", hwnd)) == 1001)
                self.GetForegroundWindow = Export(lambda: worker.wintypes.HWND(9001))
                self.GetWindowThreadProcessId = Export(self.get_pid)
                self.GetGUIThreadInfo = Export(self.get_gui_info)
                self.owner_calls = []

            def get_pid(self, hwnd, out):
                value = int(getattr(hwnd, "value", hwnd))
                self.owner_calls.append(value)
                owners = {1001: 4242, 2002: 4242, 9001: 9999}
                out._obj.value = owners.get(value, 0)
                return {1001: 77, 2002: 88, 9001: 99}.get(value, 0)

            def get_gui_info(self, thread_id, out):
                self.thread_id = int(getattr(thread_id, "value", thread_id))
                info = out._obj
                self.cb_size = info.cbSize
                info.flags = 3
                info.hwndActive = 1001
                info.hwndFocus = 2002
                info.hwndCapture = 0
                info.hwndMenuOwner = 0
                info.hwndMoveSize = 0
                info.hwndCaret = 0
                info.rcCaret.left, info.rcCaret.top = 1, 2
                info.rcCaret.right, info.rcCaret.bottom = 3, 4
                return 1

        api = User32()
        with mock.patch.object(worker.os, "name", "nt"), mock.patch.object(
            worker.ctypes, "WinDLL", return_value=api, create=True
        ):
            observed = worker._native_focus_snapshot(1001, 4242)

        self.assertEqual(api.thread_id, 77)
        self.assertEqual(api.cb_size, worker.ctypes.sizeof(worker._GUITHREADINFO))
        self.assertEqual(observed["owned_thread_focus"]["focus"], {"hwnd": 2002, "pid": 4242})
        self.assertEqual(observed["foreground"], {"hwnd": 9001, "pid": 9999})
        self.assertEqual(api.GetGUIThreadInfo.argtypes, [worker.wintypes.DWORD,
                         worker.ctypes.POINTER(worker._GUITHREADINFO)])
        self.assertIs(api.GetGUIThreadInfo.restype, worker.wintypes.BOOL)
        self.assertIs(api.GetWindowThreadProcessId.restype, worker.wintypes.DWORD)
        self.assertIs(api.GetForegroundWindow.restype, worker.wintypes.HWND)

    def test_native_focus_query_failure_is_not_fabricated_as_false(self):
        class Export:
            def __init__(self, function):
                self.function, self.argtypes, self.restype = function, None, None
            def __call__(self, *args):
                return self.function(*args)
        class User32:
            IsWindow = Export(lambda hwnd: 1)
            GetForegroundWindow = Export(lambda: 0)
            GetWindowThreadProcessId = Export(lambda hwnd, out: setattr(out._obj, "value", 4242) or 77)
            GetGUIThreadInfo = Export(lambda thread, out: 0)
        with mock.patch.object(worker.os, "name", "nt"), mock.patch.object(
            worker.ctypes, "WinDLL", return_value=User32(), create=True
        ):
            with self.assertRaises(worker._OwnershipError):
                worker._native_focus_snapshot(1001, 4242)


if __name__ == "__main__":
    unittest.main()
