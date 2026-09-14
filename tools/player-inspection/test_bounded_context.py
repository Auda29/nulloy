"""Contract and containment tests for the bounded context-menu slice."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


inspector = _load("bounded_context_inspector", HERE / "inspect_player.py")
worker = _load("bounded_context_worker", HERE / "uia_worker.py")
supervisor = _load("bounded_context_supervisor", HERE / "uia_supervisor.py")

SOURCE_SHA = "9e1b3f060e649a64c698b2a5981dbfca1d741b84"
BASE_ARGS = [
    "--package", "package.zip",
    "--output", "evidence",
    "--source-sha", SOURCE_SHA,
    "--archive-sha256", "5" * 64,
]
EXPECTED = ["one.wav (0:30)", "two.wav (0:30)", "three.wav (0:30)"]


class _Info:
    def __init__(self, name, *, pid=4242, control_type="MenuItem", automation_id="", runtime_id=None,
                 class_name="NAction", handle=None):
        self.name = name
        self.process_id = pid
        self.control_type = control_type
        self.automation_id = automation_id
        self.runtime_id = runtime_id if runtime_id is not None else [pid, id(self)]
        self.class_name = class_name
        self.handle = handle


class _Item:
    def __init__(self, name, automation_id, runtime_id, *, pid=4242):
        self.element_info = _Info(name, pid=pid, automation_id=automation_id, runtime_id=runtime_id)

    def window_text(self):
        return self.element_info.name

    def is_visible(self):
        return True

    def descendants(self):
        return []


class _Menu:
    def __init__(self, children, *, pid=4242, handle=1002, runtime_id=None, class_name="QMenu",
                 automation_id="QtSingleApplication.QMenu", control_type="Pane", visible=True):
        self.element_info = _Info(
            "Nulloy context menu", pid=pid, control_type=control_type, class_name=class_name,
            automation_id=automation_id, handle=handle, runtime_id=runtime_id or [pid, handle],
        )
        self.children = children
        self.visible = visible

    def window_text(self):
        return self.element_info.name

    def is_visible(self):
        return self.visible

    def descendants(self):
        return list(self.children)


def _valid_menu():
    return _Menu([
        _Item("Reveal in File Manager...", "QtSingleApplication.QMenu.RevealInFileManagerAction", [2, 1]),
        _Item("Remove From Playlist", "QtSingleApplication.QMenu.RemoveFromPlaylistAction", [2, 2]),
        _Item("Move To Trash", "QtSingleApplication.QMenu.MoveToTrashAction", [2, 3]),
        _Item("Tag Editor", "QtSingleApplication.QMenu.TagEditorAction", [2, 4]),
    ])


class _SelectionPattern:
    def __init__(self, row, actions):
        self.row = row
        self.actions = actions

    @property
    def CurrentIsSelected(self):
        return self.row.selected

    def Select(self):
        self.actions.append(("select", self.row.name))
        for row in self.row.container:
            row.selected = False
        self.row.selected = True

    def AddToSelection(self):
        self.actions.append(("add", self.row.name))
        self.row.selected = True


class _NativeElement:
    def __init__(self, actions, *, focus_after_set=True, focus_value=True):
        self.actions = actions
        self.CurrentHasKeyboardFocus = False
        self.focus_after_set = focus_after_set
        self.focus_value = focus_value

    def SetFocus(self):
        self.actions.append("SetFocus")
        self.CurrentHasKeyboardFocus = self.focus_value if self.focus_after_set else False


class _Row:
    def __init__(self, name, container, actions, *, pid=4242):
        self.name = name
        self.container = container
        self.selected = False
        self.element_info = _Info(name, pid=pid, control_type="ListItem")
        self.iface_selection_item = _SelectionPattern(self, actions)

    def window_text(self):
        return self.name


class BoundedContextSelectionTests(unittest.TestCase):
    def test_worker_selects_only_first_two_after_identity_validation(self):
        actions = []
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        playlist = _Playlist(rows)
        playlist.element_info.element = _NativeElement(actions)
        self.assertEqual(worker._select_context_rows(playlist, rows, EXPECTED, 4242), [True, True, False])
        self.assertEqual(actions, ["SetFocus", ("select", EXPECTED[0]), ("add", EXPECTED[1])])

    def test_worker_selection_rejects_foreign_row_before_any_selection_call(self):
        actions = []
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        rows[1].element_info.process_id = 9999
        playlist = _Playlist(rows)
        playlist.element_info.element = _NativeElement(actions)
        with self.assertRaises(worker._OwnershipError):
            worker._select_context_rows(playlist, rows, EXPECTED, 4242)
        self.assertEqual(actions, [])

    def test_qt_faithful_row_setfocus_is_not_required(self):
        actions = []
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        playlist = _Playlist(rows)
        playlist.element_info.element = _NativeElement(actions)
        self.assertEqual(worker._select_context_rows(playlist, rows, EXPECTED, 4242), [True, True, False])

    def test_playlist_setfocus_noop_is_rejected_before_selection(self):
        actions = []
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        playlist = _Playlist(rows)
        playlist.element_info.element = _NativeElement(actions, focus_after_set=False)
        with self.assertRaises(worker._OwnershipError):
            worker._select_context_rows(playlist, rows, EXPECTED, 4242)
        self.assertEqual(actions, ["SetFocus"])

    def test_playlist_focus_loss_after_selection_is_rejected(self):
        actions = []
        playlist_element = _NativeElement(actions)
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        playlist = _Playlist(rows)
        playlist.element_info.element = playlist_element

        original_select = worker._context_helpers().select_exact_rows

        def select_and_lose_focus(*args, **kwargs):
            result = original_select(*args, **kwargs)
            playlist_element.CurrentHasKeyboardFocus = False
            return result

        with mock.patch.object(worker._context_helpers(), "select_exact_rows", side_effect=select_and_lose_focus):
            with self.assertRaises(worker._OwnershipError):
                worker._select_context_rows(playlist, rows, EXPECTED, 4242)
        self.assertEqual(actions, ["SetFocus", ("select", EXPECTED[0]), ("add", EXPECTED[1])])

    def test_malformed_playlist_is_rejected_before_any_ui_action(self):
        for process_pid in (9999, True):
            with self.subTest(process_pid=process_pid):
                actions = []
                rows = []
                rows.extend(_Row(name, rows, actions) for name in EXPECTED)
                playlist = _Playlist(rows)
                playlist.element_info.process_id = process_pid
                playlist.element_info.element = _NativeElement(actions)
                with self.assertRaises(worker._OwnershipError):
                    worker._select_context_rows(playlist, rows, EXPECTED, 4242)
                self.assertEqual(actions, [])

    def test_playlist_identity_and_direct_focus_are_strict_before_action(self):
        for field, value in (
            ("class_name", "QListWidget"),
            ("control_type", "Pane"),
            ("automation_id", "wrong-playlist"),
        ):
            with self.subTest(field=field):
                actions = []
                rows = []
                rows.extend(_Row(name, rows, actions) for name in EXPECTED)
                playlist = _Playlist(rows)
                setattr(playlist.element_info, field, value)
                playlist.element_info.element = _NativeElement(actions)
                with self.assertRaises(worker._OwnershipError):
                    worker._select_context_rows(playlist, rows, EXPECTED, 4242)
                self.assertEqual(actions, [])

        actions = []
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        playlist = _Playlist(rows)
        playlist.element_info.element = object()
        with self.assertRaises(worker._OwnershipError):
            worker._select_context_rows(playlist, rows, EXPECTED, 4242)
        self.assertEqual(actions, [])

    def test_playlist_focus_accepts_native_bool_representations_only(self):
        actions = []
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        playlist = _Playlist(rows)
        element = _NativeElement(actions)
        playlist.element_info.element = element
        for value in (0, 1, False, True):
            with self.subTest(value=value):
                element.CurrentHasKeyboardFocus = value
                self.assertEqual(worker._focus_bool(playlist, "playlist"), bool(value))

        element.CurrentHasKeyboardFocus = "truthy"
        with self.assertRaises(worker._OwnershipError):
            worker._focus_bool(playlist, "playlist")


class BoundedContextContractTests(unittest.TestCase):
    def test_bounded_context_mode_is_explicit_and_excludes_legacy_transports(self):
        args = inspector.parse_args([*BASE_ARGS, "--bounded-context-menu"])
        self.assertTrue(args.bounded_context_menu)
        self.assertFalse(args.inspect_context_menu)
        self.assertFalse(args.allow_owned_pointer_input)
        self.assertFalse(args.bounded_read_only)
        for incompatible in (
            "--inspect-context-menu",
            "--allow-owned-pointer-input",
            "--bounded-read-only",
        ):
            with self.subTest(incompatible=incompatible), self.assertRaises(SystemExit):
                inspector.parse_args([*BASE_ARGS, "--bounded-context-menu", incompatible])

    def test_worker_context_contract_requires_four_owned_items_and_two_exact_actions(self):
        observation = worker._validate_context_menu(_valid_menu(), 4242)
        self.assertEqual(observation["menu_items_count"], 4)
        self.assertEqual(
            [item["label"] for item in observation["recognized_items"]],
            ["Remove From Playlist", "Move To Trash"],
        )
        self.assertFalse(observation["menu_items_invoked"])
        self.assertEqual(
            {item["record"]["automation_id"] for item in observation["recognized_items"]},
            {
                "QtSingleApplication.QMenu.RemoveFromPlaylistAction",
                "QtSingleApplication.QMenu.MoveToTrashAction",
            },
        )

    def test_worker_context_contract_rejects_foreign_menu_and_bad_selection(self):
        with self.assertRaises(worker._OwnershipError):
            worker._validate_context_menu(_Menu(_valid_menu().children, pid=9999), 4242)
        with self.assertRaises(worker._OwnershipError):
            worker._validate_context_menu(_Menu(_valid_menu().children[:2]), 4242)
        duplicate = _valid_menu().children[:]
        duplicate[2] = _Item("Move To Trash", "QtSingleApplication.QMenu.MoveToTrashAction", [2, 2])
        with self.assertRaises(worker._OwnershipError):
            worker._validate_context_menu(_Menu(duplicate), 4242)

    def test_real_hanging_context_operation_is_timeout_and_reaped(self):
        with tempfile.TemporaryDirectory(prefix="bounded-context-hang-") as raw:
            root = Path(raw)
            worker_script = root / "hanging_context_worker.py"
            worker_script.write_text(textwrap.dedent("""
                import json
                import time
                print(json.dumps({"event": "ready"}), flush=True)
                print("entered bounded context operation", file=__import__("sys").stderr, flush=True)
                time.sleep(30)
            """), encoding="utf-8")
            result = supervisor.run_supervised(
                output_dir=root / "run",
                worker_script=worker_script,
                worker_args=("--context-menu",),
                readiness_timeout=.5,
                execution_timeout=.15,
                terminate_timeout=.2,
                kill_timeout=.2,
            )
            self.assertEqual(result.status, "TIMEOUT")
            self.assertEqual(result.timeout_phase, "execution")
            self.assertTrue(result.timed_out)
            self.assertTrue(result.cleanup_verified)
            self.assertIsNotNone(result.returncode)
            self.assertIn("entered bounded context operation", result.stderr)
            self.assertNotIn("PASS", result.child_payload.get("status", ""))

    def test_active_bounded_context_cli_blocks_before_package_launch_on_linux(self):
        with tempfile.TemporaryDirectory(prefix="bounded-context-cli-") as raw:
            output = Path(raw) / "evidence"
            completed = subprocess.run(
                [
                    sys.executable, str(HERE / "inspect_player.py"),
                    "--package", str(Path(raw) / "missing.zip"),
                    "--output", str(output), "--source-sha", SOURCE_SHA,
                    "--archive-sha256", "5" * 64, "--bounded-context-menu",
                ], capture_output=True, text=True, timeout=5, check=False,
            )
            expected_code = 1 if os.name == "nt" else 2
            self.assertEqual(completed.returncode, expected_code)
            emitted = json.loads(completed.stdout)
            saved = json.loads((output / "inspection-report.json").read_text(encoding="utf-8"))
            self.assertEqual(emitted, saved)
            if os.name != "nt":
                self.assertEqual(saved["status"], "BLOCKED")
                self.assertIn("native Windows", saved["error"])


class _Playlist:
    def __init__(self, rows):
        self.rows = rows
        self.element_info = _Info(
            "Playlist", control_type="List", class_name="NPlaylistWidget",
            automation_id="QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget",
            runtime_id=[4242, 2001], handle=2001,
        )

    def descendants(self, control_type=None):
        return list(self.rows)

    def window_text(self):
        return "Playlist"


class _Root:
    def __init__(self, playlist):
        self.playlist = playlist
        self.element_info = _Info(
            "Nulloy", control_type="Pane", class_name="NMainWindow",
            runtime_id=[4242, 1001], handle=1001,
        )

    def descendants(self):
        return [self.playlist]

    def is_visible(self):
        return True

    def window_text(self):
        return self.element_info.name


class _Desktop:
    def __init__(self, root):
        self.root = root
        self.windows_now = [root]

    def window(self, handle):
        self.wrapper = self.windows_now[0]
        return self

    def wrapper_object(self):
        return self.wrapper

    def windows(self):
        return list(self.windows_now)


class _PlayerProcess:
    pid = 4242

    def create_time(self):
        return 12.5

    def exe(self):
        return "C:/Nulloy/Nulloy.exe"


class BoundedContextEndToEndContractTests(unittest.TestCase):
    def test_keyboard_context_transport_is_one_typed_postmessage_call(self):
        class Export:
            def __init__(self):
                self.calls = []
                self.argtypes = None
                self.restype = None

            def __call__(self, *args):
                self.calls.append(args)
                return 1

        class User32:
            def __init__(self):
                self.PostMessageW = Export()

        api = User32()
        with mock.patch.object(worker.os, "name", "nt"), mock.patch.object(
            worker.ctypes, "WinDLL", return_value=api, create=True
        ):
            worker._post_keyboard_context_menu(1001)
        post = api.PostMessageW
        self.assertEqual(post.argtypes, [worker.wintypes.HWND, worker.wintypes.UINT,
                                         worker.wintypes.WPARAM, worker.wintypes.LPARAM])
        self.assertIs(post.restype, worker.wintypes.BOOL)
        self.assertEqual(len(post.calls), 1)
        self.assertEqual(
            [int(getattr(value, "value", value)) for value in post.calls[0]],
            [1001, 0x007B, 1001, -1],
        )

    def test_context_worker_vertical_contract_posts_once_and_returns_owned_snapshot(self):
        actions = []
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        playlist = _Playlist(rows)
        playlist.element_info.element = _NativeElement(actions)
        root = _Root(playlist)
        desktop = _Desktop(root)
        menu = _valid_menu()
        posted = []

        def post(hwnd):
            posted.append(hwnd)
            desktop.windows_now.append(menu)

        emitted = []
        with mock.patch.object(
            worker, "_native_window_info", return_value={"hwnd": 1001, "pid": 4242, "visible": True}
        ), mock.patch.object(worker, "_validate_main_root", return_value=root):
            result = worker._context_inspect_once(
                desktop, _PlayerProcess(), {"pid": 4242, "create_time": 12.5},
                "C:/Nulloy/Nulloy.exe", 1001, EXPECTED, emitted.append,
                post_context=post, context_timeout=.2,
            )

        self.assertEqual(posted, [1001])
        self.assertEqual(result["context_menu"]["selected_rows"], EXPECTED[:2])
        self.assertEqual(result["context_menu"]["selection_after_menu"], [True, True, False])
        self.assertEqual(result["context_menu"]["menu_items_count"], 4)
        self.assertFalse(result["context_menu"]["menu_items_invoked"])
        self.assertEqual(result["context_menu"]["message"]["lparam"], -1)
        validated = inspector._validate_bounded_context_payload(
            {"pid": result["pid"], "context_menu": result["context_menu"]}, EXPECTED
        )
        self.assertEqual(validated["menu_items_count"], 4)
        self.assertEqual(actions, ["SetFocus", ("select", EXPECTED[0]), ("add", EXPECTED[1])])
        self.assertEqual(len(emitted), 1)

    def test_worker_selection_state_rejects_arbitrary_truthy_provider_value(self):
        actions = []
        rows = []
        rows.extend(_Row(name, rows, actions) for name in EXPECTED)
        rows[0].selected = "truthy"
        playlist = _Playlist(rows)
        playlist.element_info.element = _NativeElement(actions)
        with self.assertRaises(worker._OwnershipError):
            worker._select_context_rows(playlist, rows, EXPECTED, 4242)
    def test_context_timeout_runs_independent_parent_postcheck_and_preserves_timeout(self):
        target = {
            "pid": 4242, "create_time": 12.5, "executable": "C:/Nulloy/Nulloy.exe",
            "hwnd": 1001, "class_name": "NMainWindow", "visible": True,
        }

        class TimeoutResult:
            status = "TIMEOUT"
            success = False
            failure_kind = "timeout"
            cleanup_verified = True
            target_before = dict(target)
            target_after = dict(target)
            child_payload = {"snapshot": [], "playlist_rows": EXPECTED}

            def to_dict(self):
                return {
                    "status": self.status, "success": self.success,
                    "failure_kind": self.failure_kind, "cleanup_verified": self.cleanup_verified,
                    "target_before": self.target_before, "target_after": self.target_after,
                    "child_payload": self.child_payload,
                }

        checks = []

        def parent_check(*args, **kwargs):
            checks.append(True)
            if len(checks) == 2:
                raise inspector.ContractError("HWND changed after bounded context timeout")
            return dict(target)

        with mock.patch.object(
            inspector, "_discover_owned_main_hwnd", side_effect=parent_check
        ), mock.patch.object(
            inspector.uia_supervisor, "run_supervised", return_value=TimeoutResult()
        ) as supervised:
            with self.assertRaises(RuntimeError) as raised:
                inspector._bounded_read_only_snapshot(
                    output=Path("evidence"), process=mock.Mock(), psutil=mock.Mock(),
                    identity={"pid": 4242, "create_time": 12.5}, executable=Path("C:/Nulloy/Nulloy.exe"),
                    expected_rows=EXPECTED, worker_mode_args=("--context-menu",),
                )
        self.assertEqual(checks, [True, True])
        self.assertIn("TIMEOUT", str(raised.exception))
        self.assertIn("HWND changed", raised.exception.supervisor_result["secondary_errors"][0])
        args = supervised.call_args.kwargs["worker_args"]
        self.assertIn("--context-menu", args)


if __name__ == "__main__":
    unittest.main()
