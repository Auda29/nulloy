import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("player_inspection_under_test", HERE / "inspect_player.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SOURCE_SHA = "9e1b3f060e649a64c698b2a5981dbfca1d741b84"
ARCHIVE_SHA = "5" * 64


class _FakeInfo:
    def __init__(self, name, pid=4242, handle=None, control_type="ListItem"):
        self.name = name
        self.process_id = pid
        self.handle = handle
        self.control_type = control_type
        self.class_name = ""
        self.automation_id = ""
        self.runtime_id = [pid, id(self)]


class _FakeRect:
    def __init__(self, left=10, top=20, right=110, bottom=60):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class _FakeSelectionItem:
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


class _FakeNativeElement:
    def __init__(self, focused=False, actions=None):
        self.CurrentHasKeyboardFocus = focused
        self.actions = actions if actions is not None else []

    def SetFocus(self):
        self.actions.append("SetFocus")
        self.CurrentHasKeyboardFocus = True


class _FakeRow:
    def __init__(self, name, container, actions, pid=4242, rect=None):
        self.name = name
        self.selected = False
        self.container = container
        self.element_info = _FakeInfo(name, pid=pid)
        self.iface_selection_item = _FakeSelectionItem(self, actions)
        self._rect = rect or _FakeRect()
        self.element_info.element = _FakeNativeElement(actions=actions)

    def window_text(self):
        return self.name

    def rectangle(self):
        return self._rect

    def set_focus(self):
        raise AssertionError("wrapper set_focus must not be used")


class _FakeMenuItem:
    def __init__(self, name, runtime_id):
        self.element_info = _FakeInfo(name, pid=4242, control_type="MenuItem")
        self.element_info.runtime_id = runtime_id
        self._name = name

    def window_text(self):
        return self._name


class ContractTests(unittest.TestCase):
    def test_archive_mismatch_blocks_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package.zip"
            package.write_bytes(b"not-the-provenance")
            args = MODULE.parse_args(
                [
                    "--package", str(package),
                    "--output", str(Path(temporary) / "evidence"),
                    "--source-sha", SOURCE_SHA,
                    "--archive-sha256", ARCHIVE_SHA,
                ]
            )
            with mock.patch.object(MODULE, "is_windows_native", return_value=True), mock.patch.object(
                MODULE.subprocess, "Popen"
            ) as popen:
                code, report = MODULE.run_inspection(args)
            self.assertEqual(code, 1)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("archive SHA-256", report["error"])
            popen.assert_not_called()

    def test_exact_rows_reject_duplicates_and_partial_labels(self):
        fixtures = [
            Path("inspect-01.wav"),
            Path("inspect-02.wav"),
            Path("inspect-03.wav"),
        ]
        expected = MODULE.expected_playlist_rows(fixtures, [30, 30, 30])
        self.assertTrue(MODULE.exact_playlist_rows(expected, expected))
        for actual in (
            [expected[0], expected[0], expected[2]],
            [fixtures[0].name, expected[1], expected[2]],
            expected[:2],
        ):
            with self.subTest(actual=actual):
                with self.assertRaises(MODULE.ContractError):
                    MODULE.exact_playlist_rows(actual, expected)

    def test_non_windows_is_blocked_without_process_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = MODULE.parse_args(
                [
                    "--package", str(Path(temporary) / "missing.zip"),
                    "--output", str(Path(temporary) / "evidence"),
                    "--source-sha", SOURCE_SHA,
                    "--archive-sha256", ARCHIVE_SHA,
                ]
            )
            with mock.patch.object(MODULE, "is_windows_native", return_value=False), mock.patch.object(
                MODULE.subprocess, "Popen"
            ) as popen:
                code, report = MODULE.run_inspection(args)
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], "BLOCKED")
            popen.assert_not_called()

    def test_fixture_duration_is_read_from_wav_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_dir = Path(temporary)
            paths = MODULE.make_fixtures(fixture_dir, "run-test")
            self.assertEqual(len(paths), 3)
            self.assertEqual(MODULE.fixture_seconds(paths[0]), 30)
            self.assertEqual(
                MODULE.expected_playlist_rows(paths, [MODULE.fixture_seconds(p) for p in paths]),
                [f"{p.name} (0:30)" for p in paths],
            )

    def test_fixture_hash_verification_detects_post_action_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture.wav"
            fixture.write_bytes(b"stable")
            hashes = {fixture.name: {"size": fixture.stat().st_size, "sha256": hashlib.sha256(b"stable").hexdigest()}}
            self.assertTrue(MODULE._fixtures_unchanged([fixture], hashes))
            fixture.write_bytes(b"changed")
            self.assertFalse(MODULE._fixtures_unchanged([fixture], hashes))

    def test_selection_state_accepts_native_bool_integers_not_truthy_objects(self):
        row = _FakeRow("one.wav (0:30)", [], [])
        for value, expected in ((0, False), (1, True), (False, False), (True, True)):
            with self.subTest(value=value):
                row.selected = value
                self.assertIs(MODULE._selection_state(row), expected)
        for value in (None, "false", "1", 0.0, 1.0, 2, object()):
            with self.subTest(invalid=repr(value)):
                row.selected = value
                with self.assertRaises(MODULE.ContractError):
                    MODULE._selection_state(row)

    def test_selection_uses_first_select_then_second_add_and_no_extra_row(self):
        expected = ["one.wav (0:30)", "two.wav (0:30)", "three.wav (0:30)"]
        actions = []
        rows = []
        rows.extend(_FakeRow(name, rows, actions) for name in expected)

        selected = MODULE.select_exact_rows(rows, expected, 4242)

        self.assertEqual(selected, expected[:2])
        self.assertEqual(actions, [("select", expected[0]), ("add", expected[1])])
        self.assertEqual([row.name for row in rows if row.selected], expected[:2])

    def test_selection_rejects_pid_or_fullname_mismatch_before_action(self):
        expected = ["one.wav (0:30)", "two.wav (0:30)", "three.wav (0:30)"]
        actions = []
        rows = []
        rows.extend(_FakeRow(name, rows, actions) for name in expected)
        rows[1].element_info.process_id = 9999

        with self.assertRaises(MODULE.ContractError):
            MODULE.select_exact_rows(rows, expected, 4242)
        self.assertEqual(actions, [])

    def test_direct_focus_requires_owned_row_identity_and_native_focus(self):
        row = _FakeRow("one.wav (0:30)", [], [])
        evidence = MODULE.focus_owned_row(row, row.name, 4242)
        self.assertEqual(evidence["name"], row.name)
        self.assertEqual(evidence["pid"], 4242)
        self.assertTrue(evidence["has_keyboard_focus"])
        self.assertEqual(row.element_info.element.actions, ["SetFocus"])

    def test_direct_focus_rejects_missing_or_wrong_focus_without_fallback(self):
        row = _FakeRow("one.wav (0:30)", [], [])
        row.element_info.element = None
        with self.assertRaises(MODULE.BlockedError):
            MODULE.focus_owned_row(row, row.name, 4242)

        row = _FakeRow("one.wav (0:30)", [], [])
        row.element_info.element.CurrentHasKeyboardFocus = False
        row.element_info.element.SetFocus = lambda: None
        with self.assertRaises(MODULE.ContractError):
            MODULE.focus_owned_row(row, row.name, 4242)
        self.assertEqual(row.element_info.element.actions, [])

        for bad_value in (None, "true", "1", 0.0, 1.0, 2, object()):
            row = _FakeRow("one.wav (0:30)", [], [])
            row.element_info.element.CurrentHasKeyboardFocus = bad_value
            row.element_info.element.SetFocus = lambda: None
            with self.subTest(invalid=repr(bad_value)):
                with self.assertRaises(MODULE.ContractError):
                    MODULE.focus_owned_row(row, row.name, 4242)

    def test_direct_focus_rejects_pid_or_fullname_before_native_action(self):
        for pid, name in ((9999, "one.wav (0:30)"), (4242, "wrong.wav (0:30)")):
            row = _FakeRow("one.wav (0:30)", [], [], pid=pid)
            with self.subTest(pid=pid, name=name):
                with self.assertRaises(MODULE.ContractError):
                    MODULE.focus_owned_row(row, name, 4242)
            self.assertEqual(row.element_info.element.actions, [])

    def test_keyboard_context_message_requires_owned_root_and_uses_keyboard_lparam(self):
        main = mock.Mock()
        main.element_info = _FakeInfo("main", pid=4242, handle=0x1234, control_type="Pane")
        identity = {"pid": 4242, "create_time": 12.5, "executable": r"C:\Nulloy.exe"}
        root = {"pid": 4242, "create_time": 12.5, "executable": r"C:\Nulloy.exe"}

        message = MODULE.keyboard_context_message_args(main, identity, root, identity["executable"])
        self.assertEqual(message, (0x1234, 0x007B, 0x1234, -1))

        with self.assertRaises(MODULE.ContractError):
            MODULE.keyboard_context_message_args(
                main,
                identity,
                {**root, "pid": 9999},
                identity["executable"],
            )

    def test_keyboard_context_post_uses_one_exact_root_message_without_retry(self):
        main = mock.Mock()
        main.element_info = _FakeInfo("main", pid=4242, handle=0x1234, control_type="Pane")
        identity = {"pid": 4242, "create_time": 12.5, "executable": r"C:\Nulloy.exe"}
        root = {"pid": 4242, "create_time": 12.5, "executable": r"C:\Nulloy.exe"}
        posted = []

        MODULE.post_keyboard_context_menu(
            main,
            identity,
            root,
            identity["executable"],
            post_message=lambda *args: posted.append(args) or True,
        )

        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0][0], 0x1234)
        self.assertEqual(posted[0][1], 0x007B)
        self.assertEqual(posted[0][2:], (0x1234, -1))

    def test_menu_recognition_accepts_exact_entries_with_narrow_shortcut_suffix(self):
        items = [
            _FakeMenuItem("Move To Trash\tShift+Del", [1]),
            _FakeMenuItem("Remove From Playlist", [2]),
        ]

        recognized = MODULE.recognize_context_menu_items(items)

        self.assertEqual([item["label"] for item in recognized], ["Move To Trash", "Remove From Playlist"])

    def test_menu_recognition_rejects_lookalikes_and_duplicate_entries(self):
        with self.assertRaises(MODULE.ContractError):
            MODULE.recognize_context_menu_items(
                [_FakeMenuItem("Move To Trash (permanent)", [1]), _FakeMenuItem("Remove From Playlist", [2])]
            )
        with self.assertRaises(MODULE.ContractError):
            MODULE.recognize_context_menu_items(
                [
                    _FakeMenuItem("Move To Trash", [1]),
                    _FakeMenuItem("Move To Trash", [2]),
                    _FakeMenuItem("Remove From Playlist", [3]),
                ]
            )

    def test_context_menu_flag_is_opt_in_and_default_mode_has_no_action(self):
        args = MODULE.parse_args(
            [
                "--package", "package.zip",
                "--output", "evidence",
                "--source-sha", SOURCE_SHA,
                "--archive-sha256", ARCHIVE_SHA,
            ]
        )
        self.assertFalse(args.inspect_context_menu)


if __name__ == "__main__":
    unittest.main()
