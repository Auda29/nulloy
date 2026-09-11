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
QMENU_AUTOMATION_ID = "QtSingleApplication.QMenu"
QMENU_ITEMS = {
    "Remove From Playlist": "QtSingleApplication.QMenu.RemoveFromPlaylistAction",
    "Move To Trash": "QtSingleApplication.QMenu.MoveToTrashAction",
}


def _observed_qmenu(pid=4242, *, visible=True, handle=328542, runtime_id=None, children=None):
    if runtime_id is None:
        runtime_id = [42, handle]
    if children is None:
        children = [
            _FakeMenuItem(
                "Reveal in File Manager...",
                [42, handle, 4, -2147483614],
                "QtSingleApplication.QMenu.RevealInFileManagerAction",
            ),
            _FakeMenuItem(
                "Remove From Playlist",
                [42, handle, 4, -2147483613],
                QMENU_ITEMS["Remove From Playlist"],
            ),
            _FakeMenuItem(
                "Move To Trash",
                [42, handle, 4, -2147483612],
                QMENU_ITEMS["Move To Trash"],
            ),
            _FakeMenuItem(
                "Tag Editor",
                [42, handle, 4, -2147483611],
                "QtSingleApplication.QMenu.TagEditorAction",
            ),
        ]
    return _FakeSurface(
        "NulloyFork",
        pid=pid,
        control_type="Pane",
        visible=visible,
        children=children,
        runtime_id=runtime_id,
        handle=handle,
        class_name="QMenu",
        automation_id=QMENU_AUTOMATION_ID,
    )


class _FakeInfo:
    def __init__(
        self,
        name,
        pid=4242,
        handle=None,
        control_type="ListItem",
        class_name="",
        automation_id="",
    ):
        self.name = name
        self.process_id = pid
        self.handle = handle
        self.control_type = control_type
        self.class_name = class_name
        self.automation_id = automation_id
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


class _FakePlaylist:
    def __init__(self, rows):
        self.rows = rows

    def descendants(self, control_type=None):
        self.calls = getattr(self, "calls", 0) + 1
        return list(self.rows)


class _FakeMainWindow:
    def __init__(self, rect=None):
        self._rect = rect or _FakeRect(left=0, top=0, right=200, bottom=100)

    def rectangle(self):
        return self._rect


class _FakeMenuItem:
    def __init__(self, name, runtime_id, automation_id=""):
        self.element_info = _FakeInfo(
            name,
            pid=4242,
            control_type="MenuItem",
            class_name="NAction",
            automation_id=automation_id,
        )
        self.element_info.runtime_id = runtime_id
        self._name = name

    def window_text(self):
        return self._name

    def descendants(self):
        return []


class _FakeSurface:
    def __init__(
        self,
        name,
        *,
        pid=4242,
        control_type="Pane",
        visible=True,
        children=(),
        runtime_id=None,
        handle=None,
        class_name="",
        automation_id="",
    ):
        self.element_info = _FakeInfo(
            name,
            pid=pid,
            handle=handle,
            control_type=control_type,
            class_name=class_name,
            automation_id=automation_id,
        )
        if runtime_id is not None:
            self.element_info.runtime_id = runtime_id
        self._visible = visible
        self._children = list(children)

    def descendants(self):
        result = []
        for child in self._children:
            result.append(child)
            result.extend(child.descendants())
        return result

    def is_visible(self):
        return self._visible

    def window_text(self):
        return self.element_info.name


class _FakeDesktop:
    def __init__(self, windows):
        self._windows = list(windows)

    def windows(self):
        return list(self._windows)


class _CleanupProcess:
    def __init__(self, wait_results):
        self.wait_results = iter(wait_results)
        self.live = True
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0
        self.returncode = None

    def poll(self):
        return None if self.live else self.returncode

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1

    def wait(self, timeout):
        self.wait_calls += 1
        result = next(self.wait_results)
        if result == "timeout":
            raise subprocess.TimeoutExpired("owned-player", timeout)
        self.live = False
        self.returncode = 0
        return self.returncode


class ContractTests(unittest.TestCase):
    def test_main_serializes_native_report_like_artifact_and_preserves_exit_status(self):
        import io
        from contextlib import redirect_stdout

        for status, expected_code in (("PASS", 0), ("FAIL", 1), ("BLOCKED", 2)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                rect = MODULE.wintypes.RECT(359, 235, 775, 251)
                report = {
                    "status": status,
                    "context_menu": {"preflight": {"row_rect": rect}},
                    "cleanup": {"process_cleanup_verified": True},
                }
                # The real inspection writes its artifact before main emits stdout.
                MODULE._write_json(output / "inspection-report.json", report)
                args = ["--package", str(output / "package.zip"), "--output", str(output),
                        "--source-sha", SOURCE_SHA, "--archive-sha256", ARCHIVE_SHA]
                stream = io.StringIO()
                with mock.patch.object(MODULE, "run_inspection", return_value=(expected_code, report)), \
                     redirect_stdout(stream):
                    code = MODULE.main(args)
                self.assertEqual(code, expected_code)
                emitted = json.loads(stream.getvalue())
                persisted = json.loads((output / "inspection-report.json").read_text())
                self.assertEqual(emitted, persisted)
                self.assertEqual(emitted["status"], status)

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

    def test_pointer_boundary_reenumerates_rows_selection_and_geometry_without_retargeting(self):
        expected = ["one.wav (0:30)", "two.wav (0:30)", "three.wav (0:30)"]
        actions = []
        rows = []
        rows.extend(_FakeRow(name, rows, actions) for name in expected)
        rows[0].selected = True
        rows[1].selected = True
        playlist = _FakePlaylist(rows)
        main = _FakeMainWindow()
        point = MODULE.owned_pointer.POINT(50, 30)

        context = MODULE.fresh_pointer_target_context(
            playlist, main, expected, 4242, point
        )
        self.assertEqual(context["selected"], expected[:2])
        self.assertEqual(context["row"], rows[0])
        self.assertEqual(playlist.calls, 1)
        self.assertEqual(actions, [])

        rows[0]._rect = _FakeRect(left=60, top=20, right=110, bottom=60)
        with self.assertRaises(MODULE.BlockedError):
            MODULE.fresh_pointer_target_context(playlist, main, expected, 4242, point)
        rows[0]._rect = _FakeRect()
        rows[2].selected = True
        with self.assertRaises(MODULE.ContractError):
            MODULE.fresh_pointer_target_context(playlist, main, expected, 4242, point)
        rows[2].selected = False
        rows[1].name = "changed.wav (0:30)"
        with self.assertRaises(MODULE.ContractError):
            MODULE.fresh_pointer_target_context(playlist, main, expected, 4242, point)

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
            _FakeMenuItem("Move To Trash\tShift+Del", [1], QMENU_ITEMS["Move To Trash"]),
            _FakeMenuItem("Remove From Playlist", [2], QMENU_ITEMS["Remove From Playlist"]),
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
                    _FakeMenuItem("Move To Trash", [1], QMENU_ITEMS["Move To Trash"]),
                    _FakeMenuItem("Move To Trash", [2], QMENU_ITEMS["Move To Trash"]),
                    _FakeMenuItem("Remove From Playlist", [3], QMENU_ITEMS["Remove From Playlist"]),
                ]
            )

    def test_observed_qmenu_pane_root_is_discovered_with_four_owned_direct_items(self):
        menu = _observed_qmenu()
        main = _FakeSurface("main")

        roots = MODULE._owned_context_menus(_FakeDesktop([main, menu]), main, 4242)

        self.assertEqual(roots, [menu])
        items = MODULE._menu_items(menu, 4242)
        self.assertEqual(len(items), 4)
        recognized = MODULE.recognize_context_menu_items(items)
        self.assertEqual(
            {item["label"]: item["record"]["automation_id"] for item in recognized},
            QMENU_ITEMS,
        )

    def test_observed_qmenu_pane_validates_native_hwnd_identity(self):
        menu = _observed_qmenu()
        main = _FakeSurface("main")
        identity = {"pid": 4242, "create_time": 12.5, "executable": r"C:\\Nulloy.exe"}

        with mock.patch.object(MODULE, "_window_process_identity", return_value=identity) as validator:
            roots = MODULE._owned_context_menus(
                _FakeDesktop([main, menu]),
                main,
                4242,
                process_identity=identity,
                psutil=object(),
                executable=Path(identity["executable"]),
            )

        self.assertEqual(roots, [menu])
        validator.assert_called_once_with(328542, mock.ANY)

    def test_observed_qmenu_pane_rejects_native_hwnd_identity_mismatch(self):
        menu = _observed_qmenu()
        main = _FakeSurface("main")
        identity = {"pid": 4242, "create_time": 12.5, "executable": r"C:\\Nulloy.exe"}
        foreign_identity = {"pid": 9999, "create_time": 12.5, "executable": r"C:\\Other.exe"}

        with mock.patch.object(MODULE, "_window_process_identity", return_value=foreign_identity):
            with self.assertRaises(MODULE.ContractError):
                MODULE._owned_context_menus(
                    _FakeDesktop([main, menu]),
                    main,
                    4242,
                    process_identity=identity,
                    psutil=object(),
                    executable=Path(identity["executable"]),
                )

    def test_qmenu_pane_rejects_foreign_pid(self):
        menu = _observed_qmenu(pid=9999)
        main = _FakeSurface("main")

        self.assertEqual(MODULE._owned_context_menus(_FakeDesktop([main, menu]), main, 4242), [])

    def test_qmenu_pane_rejects_generic_or_wrong_identity_or_handle(self):
        main = _FakeSurface("main")
        variants = (
            _FakeSurface("generic", handle=328542),
            _FakeSurface("wrong-class", handle=328542, class_name="QWidget", automation_id=QMENU_AUTOMATION_ID),
            _FakeSurface("wrong-automation", handle=328542, class_name="QMenu", automation_id="other"),
            _FakeSurface("missing-handle", class_name="QMenu", automation_id=QMENU_AUTOMATION_ID),
        )

        for root in variants:
            with self.subTest(root=root.element_info.name):
                self.assertEqual(MODULE._owned_context_menus(_FakeDesktop([main, root]), main, 4242), [])

    def test_qmenu_pane_rejects_hidden_root(self):
        menu = _observed_qmenu(visible=False)
        main = _FakeSurface("main")

        self.assertEqual(MODULE._owned_context_menus(_FakeDesktop([main, menu]), main, 4242), [])

    def test_qmenu_pane_deduplicates_same_runtime_id(self):
        runtime_id = [42, 328542]
        first = _observed_qmenu(runtime_id=runtime_id)
        duplicate = _observed_qmenu(runtime_id=runtime_id)
        popup = _FakeSurface("popup", children=[first, duplicate])
        main = _FakeSurface("main")

        self.assertEqual(MODULE._owned_context_menus(_FakeDesktop([main, popup]), main, 4242), [first])

    def test_qmenu_pane_rejects_multiple_distinct_roots(self):
        first = _observed_qmenu(runtime_id=[42, 328542])
        second = _observed_qmenu(handle=328543, runtime_id=[42, 328543])
        popup = _FakeSurface("popup", children=[first, second])
        main = _FakeSurface("main")

        with self.assertRaises(MODULE.ContractError):
            MODULE._owned_context_menus(_FakeDesktop([main, popup]), main, 4242)

    def test_qmenu_items_require_exact_automation_ids(self):
        menu = _observed_qmenu(
            children=[
                _FakeMenuItem("Move To Trash", [1], "wrong.MoveToTrashAction"),
                _FakeMenuItem("Remove From Playlist", [2], QMENU_ITEMS["Remove From Playlist"]),
            ]
        )

        with self.assertRaises(MODULE.ContractError):
            MODULE.recognize_context_menu_items(MODULE._menu_items(menu, 4242))

    def test_qmenu_items_reject_duplicate_exact_entries(self):
        menu = _observed_qmenu(
            children=[
                _FakeMenuItem("Move To Trash", [1], QMENU_ITEMS["Move To Trash"]),
                _FakeMenuItem("Move To Trash", [2], QMENU_ITEMS["Move To Trash"]),
                _FakeMenuItem("Remove From Playlist", [3], QMENU_ITEMS["Remove From Playlist"]),
            ]
        )

        with self.assertRaises(MODULE.ContractError):
            MODULE.recognize_context_menu_items(MODULE._menu_items(menu, 4242))

    def test_qmenu_wait_rejects_stale_baseline_root(self):
        menu = _observed_qmenu()
        main = _FakeSurface("main")
        identity = {"pid": 4242}

        with mock.patch.object(MODULE, "_verify_process_identity"), mock.patch.object(
            MODULE.time, "monotonic", side_effect=[0, 0, 1]
        ), mock.patch.object(MODULE.time, "sleep"):
            with self.assertRaises(RuntimeError):
                MODULE._wait_for_context_menu(
                    _FakeDesktop([main, menu]),
                    main,
                    process=None,
                    psutil=None,
                    identity=identity,
                    executable=Path("Nulloy.exe"),
                    baseline_keys={MODULE._runtime_key(menu)},
                    timeout=0.1,
                )

    def test_owned_menu_discovery_reaches_menu_below_owned_popup_pane(self):
        menu = _FakeSurface("context", control_type="Menu")
        wrapper = _FakeSurface("popup-wrapper", children=[menu])
        popup = _FakeSurface("popup-surface", children=[wrapper])
        main = _FakeSurface("main", children=[])

        menus = MODULE._owned_context_menus(_FakeDesktop([main, popup]), main, 4242)

        self.assertEqual(menus, [menu])

    def test_owned_menu_discovery_excludes_foreign_pid_descendants(self):
        foreign_menu = _FakeSurface("foreign", pid=9999, control_type="Menu")
        foreign_surface = _FakeSurface("foreign-surface", pid=9999, children=[foreign_menu])
        main = _FakeSurface("main", children=[foreign_surface])

        self.assertEqual(MODULE._owned_context_menus(_FakeDesktop([main]), main, 4242), [])

    def test_owned_menu_discovery_rejects_hidden_menu(self):
        hidden_menu = _FakeSurface("hidden", control_type="Menu", visible=False)
        popup = _FakeSurface("popup", children=[hidden_menu])
        main = _FakeSurface("main")

        self.assertEqual(MODULE._owned_context_menus(_FakeDesktop([main, popup]), main, 4242), [])

    def test_owned_menu_discovery_deduplicates_duplicate_runtime_id(self):
        runtime_id = [4242, 77]
        first = _FakeSurface("first", control_type="Menu", runtime_id=runtime_id)
        duplicate = _FakeSurface("duplicate", control_type="Menu", runtime_id=runtime_id)
        popup = _FakeSurface("popup", children=[first, duplicate])
        main = _FakeSurface("main")

        self.assertEqual(MODULE._owned_context_menus(_FakeDesktop([main, popup]), main, 4242), [first])

    def test_owned_menu_discovery_rejects_unexpected_distinct_menu_roots(self):
        first = _FakeSurface("first", control_type="Menu")
        second = _FakeSurface("second", control_type="Menu")
        popup = _FakeSurface("popup", children=[first, second])
        main = _FakeSurface("main")

        with self.assertRaises(MODULE.ContractError):
            MODULE._owned_context_menus(_FakeDesktop([main, popup]), main, 4242)

    def test_owned_surface_diagnostics_include_only_owned_surfaces_and_descendants(self):
        owned_child = _FakeSurface("owned-child")
        foreign_child = _FakeSurface("foreign-child", pid=9999)
        owned_surface = _FakeSurface("owned-surface", children=[owned_child, foreign_child])
        foreign_surface = _FakeSurface("foreign-surface", pid=9999)

        diagnostics = MODULE._owned_surface_diagnostics(
            _FakeDesktop([owned_surface, foreign_surface]), 4242
        )

        self.assertEqual(len(diagnostics["top_level_surfaces"]), 1)
        surface = diagnostics["top_level_surfaces"][0]
        self.assertEqual(
            {surface["surface"][field] for field in ("pid", "class_name", "nativehandle", "control_type")},
            {4242, "", None, "Pane"},
        )
        self.assertEqual([item["name"] for item in surface["descendants"]], ["owned-child"])
        self.assertNotIn("foreign-child", json.dumps(diagnostics))

    def test_context_menu_timeout_writes_bounded_owned_surface_diagnostics(self):
        main = _FakeSurface("main")
        identity = {"pid": 4242}
        with tempfile.TemporaryDirectory() as temporary:
            diagnostics_path = Path(temporary) / "discovery.json"
            with self.assertRaises(RuntimeError):
                MODULE._wait_for_context_menu(
                    _FakeDesktop([main]),
                    main,
                    process=None,
                    psutil=None,
                    identity=identity,
                    executable=Path("Nulloy.exe"),
                    baseline_keys=set(),
                    timeout=0,
                    diagnostics_path=diagnostics_path,
                )
            diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))

        self.assertEqual(diagnostics["process_pid"], 4242)
        self.assertEqual(len(diagnostics["top_level_surfaces"]), 1)
        self.assertEqual(diagnostics["top_level_surfaces"][0]["surface"]["name"], "main")

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
        self.assertFalse(args.allow_owned_pointer_input)

    def test_owned_pointer_flag_requires_context_menu_flag(self):
        with self.assertRaises(SystemExit):
            MODULE.parse_args(
                [
                    "--package", "package.zip",
                    "--output", "evidence",
                    "--source-sha", SOURCE_SHA,
                    "--archive-sha256", ARCHIVE_SHA,
                    "--allow-owned-pointer-input",
                ]
            )
        args = MODULE.parse_args(
            [
                "--package", "package.zip",
                "--output", "evidence",
                "--source-sha", SOURCE_SHA,
                "--archive-sha256", ARCHIVE_SHA,
                "--inspect-context-menu",
                "--allow-owned-pointer-input",
            ]
        )
        self.assertTrue(args.allow_owned_pointer_input)

    def test_cleanup_kills_after_terminate_timeout_and_removes_temp(self):
        process = _CleanupProcess(["timeout", "exit"])
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary) / "owned"
            temp_root.mkdir()
            owner_checks = []
            verified, errors = MODULE._cleanup(
                process,
                temp_root,
                owner_check=lambda: owner_checks.append("checked"),
            )
            self.assertTrue(verified)
            self.assertEqual(errors, [])
            self.assertEqual(process.terminate_calls, 1)
            self.assertEqual(process.kill_calls, 1)
            self.assertEqual(process.wait_calls, 2)
            self.assertEqual(owner_checks, ["checked", "checked"])
            self.assertFalse(temp_root.exists())

    def test_cleanup_retains_temp_when_process_stays_live_after_kill(self):
        process = _CleanupProcess(["timeout", "timeout"])
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary) / "owned"
            temp_root.mkdir()
            verified, errors = MODULE._cleanup(
                process,
                temp_root,
                owner_check=lambda: None,
            )
            self.assertFalse(verified)
            self.assertTrue(errors)
            self.assertEqual(process.kill_calls, 1)
            self.assertTrue(temp_root.exists())

    def test_cleanup_does_not_terminate_live_process_without_ownership(self):
        process = _CleanupProcess(["exit"])
        with tempfile.TemporaryDirectory() as temporary:
            temp_root = Path(temporary) / "owned"
            temp_root.mkdir()
            verified, errors = MODULE._cleanup(
                process,
                temp_root,
                owner_check=lambda: (_ for _ in ()).throw(MODULE.ContractError("identity lost")),
            )
            self.assertFalse(verified)
            self.assertTrue(errors)
            self.assertEqual(process.terminate_calls, 0)
            self.assertEqual(process.kill_calls, 0)
            self.assertTrue(temp_root.exists())


if __name__ == "__main__":
    unittest.main()
