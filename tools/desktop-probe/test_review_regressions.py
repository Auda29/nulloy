import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import wave
import zipfile
import hashlib
import probe

class Control:
    def __init__(self, name='', children=(), class_name='', control_type=''):
        self.name, self._children = name, list(children)
        self.element_info = SimpleNamespace(class_name=class_name, control_type=control_type)
    def window_text(self):
        return self.name
    def descendants(self, **kwargs):
        return list(self._children)
    def children(self, **kwargs):
        return list(self._children)

class ReviewRegressions(unittest.TestCase):
    def test_primary_traceback_survives_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            args = SimpleNamespace(
                package=Path(tmp) / "package.zip",
                output=output,
                source_sha="0123456789abcdef0123456789abcdef01234567",
                headless_audio=False,
            )
            package = SimpleNamespace(
                archive_sha256="archive",
                executable_sha256="executable",
                contract=SimpleNamespace(
                    files={"Nulloy.exe": "a" * 64},
                    source_commit=args.source_sha,
                    root="Nulloy",
                    executable="Nulloy.exe",
                    portable=False,
                    upstream_update_check=False,
                    qt_major="6",
                ),
            )

            class FailingRuntime:
                cleanup_verified = False
                owned_player_processes = []
                process_cleanup_verified = False

                def __init__(self, *args, **kwargs):
                    pass

                def execute(self):
                    raise RuntimeError("primary probe failure")

                def _cleanup_evidence(self):
                    raise OSError("injected cleanup failure")

            with patch.object(probe, "extract_and_validate", return_value=package), \
                    patch.object(probe, "WindowsDesktopRun", FailingRuntime):
                code, evidence = probe.run_probe(args)

            self.assertEqual(code, 1)
            self.assertEqual(evidence["status"], "FAIL")
            self.assertEqual(evidence["error"], "primary probe failure")
            self.assertIn("RuntimeError: primary probe failure", evidence["error_traceback"])
            self.assertTrue(any("injected cleanup failure" in item for item in evidence["cleanup_errors"]))
            result = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertIn("RuntimeError: primary probe failure", result["error_traceback"])
            self.assertTrue(any("injected cleanup failure" in item for item in result["cleanup_errors"]))

    def test_playlist_waits_for_two_stable_exact_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = object.__new__(probe.WindowsDesktopRun)
            runtime.evidence = Path(tmp)
            snapshots = [
                ["one.wav"],
                ["two.wav", "one.wav"],
                ["one.wav", "two.wav"],
            ]
            with patch.object(runtime, "_playlist_snapshot", side_effect=snapshots) as snapshot, \
                    patch.object(probe.time, "sleep"):
                rows = runtime._read_playlist_rows([Path("one.wav"), Path("two.wav")])
            self.assertEqual(rows, ["one.wav", "two.wav"])
            self.assertEqual(snapshot.call_count, 3)
            observations = (Path(tmp) / "playlist-row-observations.jsonl").read_text().splitlines()
            self.assertEqual([json.loads(line) for line in observations], snapshots)

    def test_player_cleanup_closes_owned_main_window_and_dialog(self):
        class Window(Control):
            def __init__(self, name):
                super().__init__(name)
                self.element_info.process_id = 17
                self.closed = False

            def close(self):
                self.closed = True

            def is_visible(self):
                return not self.closed

        class Process:
            pid = 17

            def __init__(self):
                self.alive = True

            def create_time(self):
                return 123.5

            def exe(self):
                return r"C:\\pkg\\Nulloy.exe"

            def terminate(self):
                self.alive = False

            def wait(self, timeout=None):
                return 0

        class Psutil:
            TimeoutExpired = TimeoutError
            NoSuchProcess = ProcessLookupError

            def __init__(self, process):
                self.process = process

            def Process(self, pid):
                return self.process

            def process_iter(self, attrs):
                return [self.process] if self.process.alive else []

        main = Window("Nulloy")
        dialog = Window("Nulloy Log")
        process = Process()
        runtime = object.__new__(probe.WindowsDesktopRun)
        runtime.player_window = main
        runtime.desktop = SimpleNamespace(windows=lambda: [main, dialog])
        runtime.package = SimpleNamespace(executable=Path(r"C:\\pkg\\Nulloy.exe"))
        runtime.psutil = Psutil(process)
        runtime.owned_player_processes = [probe.ProcessIdentity(17, 123.5, process.exe())]
        runtime.cleanup_errors = []
        runtime.process_cleanup_verified = False
        runtime._find_player = lambda: None
        self.assertTrue(runtime._cleanup_player())
        self.assertTrue(main.closed)
        self.assertTrue(dialog.closed)

    def test_execute_captures_selected_explorer_evidence_before_invoking_verb(self):
        events = []

        class Image:
            pass

        class Explorer(Control):
            def set_focus(self):
                pass

            def capture_as_image(self):
                return Image()

            def type_keys(self, keys):
                events.append("invoke")

        class MenuItem:
            def click_input(self):
                pass

        class Player(Control):
            def capture_as_image(self):
                return Image()

        runtime = object.__new__(probe.WindowsDesktopRun)
        runtime.run_id = "run"
        runtime.evidence = Path(tempfile.mkdtemp())
        runtime.package = SimpleNamespace(executable=Path("Nulloy.exe"))
        runtime.profile = probe.shell_verb_profile("run", Path("Nulloy.exe"))
        runtime.headless_audio = False
        runtime.explorer_window = None
        runtime.player_window = None
        runtime.desktop = SimpleNamespace(windows=lambda: [])
        runtime.cleanup_verified = False
        runtime.cleanup_errors = []
        runtime.owned_player_processes = []
        runtime.process_cleanup_verified = True
        runtime.registry_key_created = False
        runtime.explorer_launch_started = False
        runtime.explorer_identity = None
        runtime.playlist_control_identity = None
        runtime.preflight = lambda: None

        def capture(image, path):
            events.append(path.name)

        with patch.object(probe, "_app_environment", return_value={"PATH": "C:\\\\Windows\\\\System32"}), \
                patch.object(probe, "_make_fixtures", return_value=[Path("one.wav")]), \
                patch.object(probe.subprocess, "Popen"), \
                patch.object(probe, "_wait_for", side_effect=[Explorer("fixtures"), MenuItem(), True, Player()]), \
                patch.object(probe, "_capture_image", side_effect=capture), \
                patch.object(probe, "_dump_uia", side_effect=lambda window, path: events.append(path.name)), \
                patch.object(runtime, "preflight"), \
                patch.object(runtime, "_registry_install"), \
                patch.object(runtime, "_select_all_fixture_files", side_effect=lambda: events.append("select")), \
                patch.object(runtime, "_read_playlist_rows", return_value=["one.wav"]), \
                patch.object(runtime, "_cleanup_player", return_value=True), \
                patch.object(runtime, "_cleanup_explorer", return_value=True), \
                patch.object(runtime, "_registry_cleanup", return_value=True), \
                patch.object(probe.shutil, "rmtree"):
            runtime.execute()

        self.assertLess(events.index("explorer-selection.png"), events.index("invoke"))
        self.assertLess(events.index("explorer-selection-uia.jsonl"), events.index("invoke"))

    def test_extra_playlist_row_must_not_be_filtered_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = object.__new__(probe.WindowsDesktopRun)
            runtime.evidence = Path(tmp)
            playlist = Control(
                children=[Control('one.wav'), Control('two.wav'), Control('unrelated.wav')],
                class_name='NPlaylistWidget',
                control_type='List',
            )
            runtime.player_window = Control(children=[playlist])
            with patch.object(probe, "PLAYLIST_STABILIZATION_TIMEOUT", 0):
                with self.assertRaises(probe.ContractError):
                    runtime._read_playlist_rows([Path('one.wav'), Path('two.wav')])

    def test_playlist_uses_exact_observed_qt_control_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = object.__new__(probe.WindowsDesktopRun)
            runtime.evidence = Path(tmp)
            expected = [Path('one.wav'), Path('two.wav')]
            playlist = Control(
                children=[Control('two.wav'), Control('one.wav')],
                class_name='NPlaylistWidget',
                control_type='List',
            )
            playlist.element_info.automation_id = 'QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget'
            noise = Control(children=[Control('one.wav')], class_name='OtherList', control_type='List')
            runtime.player_window = Control(children=[noise, playlist])
            rows = runtime._read_playlist_rows(expected)
            self.assertEqual(rows, ['one.wav', 'two.wav'])
            self.assertEqual(runtime.playlist_control_identity, {
                'class_name': 'NPlaylistWidget',
                'automation_id': playlist.element_info.automation_id,
            })

    def test_registry_key_is_owned_before_value_writes(self):
        events = []

        class Key:
            def __enter__(self):
                events.append("enter")
                return self
            def __exit__(self, *args):
                events.append("exit")
            def __repr__(self):
                return "<key>"

        class Winreg:
            HKEY_CURRENT_USER = object()
            KEY_WRITE = 1
            REG_SZ = 2
            def CreateKeyEx(self, root, path, reserved, access):
                events.append(("create", path))
                return Key()
            def SetValueEx(self, key, name, reserved, kind, value):
                events.append(("set", name))
                raise OSError("simulated value write failure")
            def OpenKey(self, root, path):
                raise FileNotFoundError(path)
            def DeleteKey(self, root, path):
                events.append(("delete", path))

        runtime = object.__new__(probe.WindowsDesktopRun)
        runtime.profile = probe.shell_verb_profile("run", Path("player.exe"))
        runtime.registry_key_created = False
        with patch.dict(sys.modules, {"winreg": Winreg()}):
            with self.assertRaises(OSError):
                runtime._registry_install()
            self.assertTrue(runtime.registry_key_created)
            with patch.object(probe, "_notify_association_changed") as notify:
                self.assertTrue(runtime._registry_cleanup())
                notify.assert_called_once_with()
        self.assertEqual([event[0] if isinstance(event, tuple) else event for event in events],
                         ["create", "enter", "set", "exit", "delete", "delete"])

    def test_fixture_audio_is_one_second_of_44100_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixtures = probe._make_fixtures(Path(tmp) / "fixtures")
            self.assertEqual(len(fixtures), 3)
            for fixture in fixtures:
                with wave.open(str(fixture), "rb") as audio:
                    self.assertEqual(audio.getframerate(), 44100)
                    self.assertEqual(audio.getnframes(), 44100)
                    self.assertAlmostEqual(audio.getnframes() / audio.getframerate(), 1.0)

    def test_explorer_items_view_excludes_navigation_list_items(self):
        navigation_item = Control("unrelated")
        file_items = [Control("desktop-probe-01"), Control("desktop-probe-02")]
        items_view = Control(children=file_items, class_name="UIItemsView", control_type="List", name="Items View")
        explorer = Control(children=[Control(children=[navigation_item], control_type="Tree"), items_view])
        runtime = object.__new__(probe.WindowsDesktopRun)
        runtime.explorer_window = explorer
        self.assertIs(runtime._find_explorer_items_view(), items_view)
        self.assertEqual(runtime._explorer_file_rows(items_view), file_items)

    def test_explorer_finder_requires_exact_address_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_directory = Path(tmp) / "fixtures"
            runtime = object.__new__(probe.WindowsDesktopRun)
            runtime.fixture_directory = fixture_directory
            runtime.explorer_identity = None
            wrong = Control(
                name="fixtures",
                children=[Control("Address: C:\\other")],
                class_name="CabinetWClass",
            )
            right = Control(
                name="fixtures",
                children=[Control(f"Address: {fixture_directory}")],
                class_name="CabinetWClass",
            )
            wrong.handle = 1
            right.handle = 2
            runtime.desktop = SimpleNamespace(windows=lambda: [wrong, right])
            self.assertIs(runtime._find_explorer(), right)
            self.assertEqual(runtime.explorer_identity, (2, str(fixture_directory).casefold()))

    def test_selection_api_failure_blocks_instead_of_continuing(self):
        class BrokenItem(Control):
            def click_input(self, **kwargs):
                pass
            def is_selected(self):
                raise RuntimeError("selection unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            fixture_directory = Path(tmp) / "fixtures"
            fixture_directory.mkdir()
            (fixture_directory / "desktop-probe-01.wav").touch()
            runtime = object.__new__(probe.WindowsDesktopRun)
            runtime.fixture_directory = fixture_directory
            items_view = Control(
                children=[BrokenItem("desktop-probe-01.wav")],
                class_name="UIItemsView",
                control_type="List",
                name="Items View",
            )
            runtime.explorer_window = Control(children=[items_view])
            with self.assertRaises(probe.ContractError):
                runtime._select_all_fixture_files()

    def test_package_process_identity_requires_pid_creation_time_and_exe(self):
        identity = probe.ProcessIdentity(17, 123.5, r"C:\\pkg\\Nulloy.exe")
        matching = SimpleNamespace(pid=17, create_time=lambda: 123.5,
                                   exe=lambda: r"c:\\pkg\\Nulloy.exe")
        wrong_pid = SimpleNamespace(pid=18, create_time=lambda: 123.5,
                                    exe=lambda: r"C:\\pkg\\Nulloy.exe")
        self.assertTrue(probe.process_identity_matches(matching, identity))
        self.assertFalse(probe.process_identity_matches(wrong_pid, identity))

        class FakeProcess:
            def __init__(self):
                self.pid = 17
                self.alive = True
                self.terminated = False
                self.killed = False
            def create_time(self):
                return 123.5
            def exe(self):
                return r"C:\\pkg\\Nulloy.exe"
            def terminate(self):
                self.terminated = True
                self.alive = False
            def wait(self, timeout=None):
                return 0
            def kill(self):
                self.killed = True
                self.alive = False

        class FakePsutil:
            TimeoutExpired = TimeoutError
            NoSuchProcess = ProcessLookupError
            def __init__(self, process):
                self.process = process
            def process_iter(self, attrs):
                return [self.process] if self.process.alive else []
            def Process(self, pid):
                if pid != 17:
                    raise AssertionError(pid)
                return self.process

        fake_process = FakeProcess()
        fake_psutil = FakePsutil(fake_process)
        runtime = object.__new__(probe.WindowsDesktopRun)
        runtime.psutil = fake_psutil
        runtime.package = SimpleNamespace(executable=Path(r"C:\\pkg\\Nulloy.exe"))
        runtime.player_process_baseline = ()
        runtime.owned_player_processes = [probe.ProcessIdentity(17, 123.5, r"C:\\pkg\\Nulloy.exe")]
        runtime.cleanup_errors = []
        self.assertTrue(runtime._terminate_owned_player_processes())
        self.assertTrue(fake_process.terminated)
        self.assertFalse(fake_process.killed)

    def test_explorer_hidden_extensions_map_exactly(self):
        expected = ['desktop-probe-01.wav', 'desktop-probe-02.wav']
        self.assertEqual(probe.explorer_row_names(['desktop-probe-01', 'desktop-probe-02'], expected), expected)
        self.assertEqual(probe.explorer_row_names(expected, expected), expected)
        for names in [['desktop-probe-01'], ['desktop-probe-01', 'unrelated'], ['desktop-probe-01', 'desktop-probe-01.wav']]:
            with self.subTest(names=names), self.assertRaises(probe.ContractError):
                probe.explorer_row_names(names, expected)

    def test_windows_path_aliases_rejected(self):
        for name in ['C:/escape.exe', 'file.exe:stream', 'CON', 'name.', 'name ', './ok.exe', 'a//b.exe']:
            with self.subTest(name=name), self.assertRaises(probe.ContractError):
                probe._relative_manifest_path(name, 'file')

    def test_primary_probe_error_is_not_masked_by_package_cleanup_error(self):
        source_sha = "0123456789abcdef0123456789abcdef01234567"
        executable = b"fake executable"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_path = root / "package.zip"
            manifest = {
                "source_commit": source_sha,
                "tracked_changes": False,
                "upstream_update_check": False,
                "qt_major": "6",
                "portable": False,
                "root": "Nulloy",
                "executable": "Nulloy.exe",
                "files": {"Nulloy.exe": hashlib.sha256(executable).hexdigest()},
            }
            with zipfile.ZipFile(package_path, "w") as archive:
                archive.writestr("Nulloy/package-manifest.json", json.dumps(manifest))
                archive.writestr("Nulloy/Nulloy.exe", executable)
            args = probe.parse_args([
                "--package", str(package_path), "--output", str(root / "evidence"),
                "--source-sha", source_sha,
            ])
            with patch.object(probe.WindowsDesktopRun, "execute", side_effect=RuntimeError("primary UIA error")):
                with patch.object(probe.shutil, "rmtree", side_effect=PermissionError("locked DLL")):
                    code, evidence = probe.run_probe(args)
            self.assertEqual(code, 1)
            self.assertEqual(evidence["error"], "primary UIA error")
            self.assertTrue(any("package extraction cleanup" in item for item in evidence["cleanup_errors"]))
            self.assertFalse(evidence["cleanup_verified"])
