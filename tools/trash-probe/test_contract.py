#!/usr/bin/env python3
"""Linux-runnable contract tests for the packaged Windows trash probe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
import probe  # noqa: E402


SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"


def valid_manifest(**updates: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "source_commit": SOURCE_SHA,
        "tracked_changes": False,
        "upstream_update_check": False,
        "root": "NulloyFork",
        "executable": "NulloyFork.exe",
        "portable": True,
        "qt_major": "6",
        "files": {
            "NulloyFork.exe": "a" * 64,
            "build-info.json": "b" * 64,
        },
    }
    manifest.update(updates)
    return manifest


class ContractTests(unittest.TestCase):
    def test_live_process_without_identity_preserves_temp_files(self) -> None:
        class LiveProcess:
            returncode = None

            def poll(self):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            scenario = probe.WindowsScenario(Path("package.zip"), SOURCE_SHA, evidence, "test")
            scenario.temp_root = Path(temporary) / "generated"
            scenario.temp_root.mkdir()
            scenario.process = LiveProcess()

            result = scenario.cleanup()

            self.assertFalse(result["cleanup_verified"])
            self.assertFalse(result["process_cleanup_verified"])
            self.assertTrue(scenario.temp_root.exists())

    def test_exited_owned_popen_without_identity_can_be_removed(self) -> None:
        class ExitedProcess:
            returncode = 0

            def poll(self):
                return self.returncode

        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            scenario = probe.WindowsScenario(Path("package.zip"), SOURCE_SHA, evidence, "test")
            scenario.temp_root = Path(temporary) / "generated"
            scenario.temp_root.mkdir()
            scenario.process = ExitedProcess()

            result = scenario.cleanup()

            self.assertTrue(result["cleanup_verified"])
            self.assertFalse(scenario.temp_root.exists())

    def test_focused_non_default_button_is_not_treated_as_default(self) -> None:
        class FocusedButton:
            def get_properties(self):
                return {}

            def has_focus(self):
                return True

        self.assertFalse(probe.WindowsScenario._button_is_default(FocusedButton()))

    def test_legacy_default_state_proves_default_without_focus(self) -> None:
        class Legacy:
            def __init__(self):
                self.calls = 0

            def __call__(self):
                self.calls += 1
                return {"State": 0x100}

        class Button:
            legacy = Legacy()

            def get_properties(self):
                return {}

            def has_focus(self):
                return False

            def legacy_properties(self):
                return self.legacy()

        self.assertTrue(probe.WindowsScenario._button_is_default(Button()))

    def test_confirmation_transition_accepts_replacement_dialog(self) -> None:
        class Control:
            def __init__(self, text: str):
                self.text = text

            def window_text(self):
                return self.text

        class Button(Control):
            def __init__(self, text: str, on_click=None):
                super().__init__(text)
                self.on_click = on_click

            def get_properties(self):
                return {"is_default": self.text == "Cancel"}

            def has_focus(self):
                return False

            def invoke(self):
                if self.on_click:
                    self.on_click()

            def click_input(self):
                raise AssertionError("dialog buttons must not use click_input")

            def wrapper_object(self):
                return self

        class Dialog:
            def __init__(self, fixture: str, on_answer):
                self.fixture = fixture
                self.answer = Button("Yes", on_answer)
                self.cancel = Button("Cancel")

            def window_text(self):
                return "Confirmation"

            def is_visible(self):
                return True

            def descendants(self, control_type=None):
                buttons = [self.answer, self.cancel]
                if control_type == "Button":
                    return buttons
                return [Control("Confirmation"), Control(self.fixture), *buttons]

            def child_window(self, title, control_type):
                return next(button for button in self.descendants("Button") if button.text == title)

            def wrapper_object(self):
                return self

        class Scenario(probe.WindowsScenario):
            def __init__(self):
                super().__init__(Path("package.zip"), SOURCE_SHA, Path("evidence"), "test")
                self.dialog = None
                self.next_dialog = Dialog("second.wav", lambda: None)
                self.dialog = Dialog("first.wav", self._replace)

            def _replace(self):
                self.dialog = self.next_dialog

            def _verify_process(self):
                return None

            def _dialog_candidates(self):
                return [] if self.dialog is None else [self.dialog]

        scenario = Scenario()
        scenario.fixtures = [
            probe.Fixture(Path("first.wav"), "a", 1),
            probe.Fixture(Path("second.wav"), "b", 1),
        ]
        scenario._drive_confirmation("first.wav", "Yes")
        self.assertIs(scenario.dialog, scenario.next_dialog)

    def test_confirmation_trash_error_is_cancelled_and_blocked(self) -> None:
        class Button:
            def __init__(self, text, on_click=None):
                self.text = text
                self.on_click = on_click

            def window_text(self):
                return self.text

            def get_properties(self):
                return {"is_default": self.text == "Cancel"}

            def has_focus(self):
                return False

            def invoke(self):
                if self.on_click:
                    self.on_click()

            def click_input(self):
                raise AssertionError("dialog buttons must not use click_input")

            def wrapper_object(self):
                return self

        class Dialog:
            def __init__(self, on_cancel):
                self.cancel = Button("Cancel", on_cancel)
                self.yes = Button("Yes", on_cancel)

            def window_text(self):
                return "Confirmation"

            def descendants(self, control_type=None):
                if control_type == "Button":
                    return [self.yes, self.cancel]
                return [Button("Confirmation"), Button("first.wav"), *self.descendants("Button")]

            def child_window(self, title, control_type):
                return self.cancel if title == "Cancel" else self.yes

            def wrapper_object(self):
                return self

        class ErrorDialog(Dialog):
            def window_text(self):
                return "Trash Error"

            def descendants(self, control_type=None):
                if control_type == "Button":
                    return [self.cancel]
                return [Button("Trash Error"), *self.descendants("Button")]

        class Scenario(probe.WindowsScenario):
            def __init__(self):
                super().__init__(Path("package.zip"), SOURCE_SHA, Path("evidence"), "test")
                self.dialog = None
                self.dialog = Dialog(self._show_error)

            def _show_error(self):
                self.dialog = ErrorDialog(self._close)

            def _close(self):
                self.dialog = None

            def _verify_process(self):
                return None

            def _dialog_candidates(self):
                return [] if self.dialog is None else [self.dialog]

        scenario = Scenario()
        scenario.fixtures = [probe.Fixture(Path("first.wav"), "a", 1)]
        with self.assertRaises(probe.BlockedError):
            scenario._drive_confirmation("first.wav", "Yes")
        self.assertIsNone(scenario.dialog)

    def test_stop_requires_evidence_of_active_loaded_playback(self) -> None:
        class StopButton:
            element_info = type("Info", (), {"automation_id": "stopButton"})()

        class ZeroSlider:
            element_info = type(
                "Info", (), {"class_name": "NWaveformSlider", "automation_id": "waveformSlider"}
            )()

            def get_value(self):
                return 0.0

        class Window:
            def descendants(self, control_type=None):
                if control_type == "Button":
                    return [StopButton()]
                return [StopButton(), ZeroSlider()]

            def set_focus(self):
                return None

        scenario = probe.WindowsScenario(Path("package.zip"), SOURCE_SHA, Path("evidence"), "test")
        scenario.main_window = Window()
        scenario._verify_process = lambda: None
        keyboard = type("Keyboard", (), {"send_keys": staticmethod(lambda keys: None)})
        with mock.patch.dict(sys.modules, {"pywinauto.keyboard": keyboard}):
            with self.assertRaises(probe.BlockedError):
                scenario._stop_and_verify()

    def test_stop_does_not_require_unobserved_stop_button(self) -> None:
        class Slider:
            element_info = type(
                "Info", (), {"class_name": "NWaveformSlider", "automation_id": "waveformSlider"}
            )()

            def __init__(self):
                self.values = iter((0.1, 0.2, 0.3, 0.0, 0.0, 0.0))

            def get_value(self):
                return next(self.values, 0.0)

        class Window:
            def __init__(self):
                self.slider = Slider()

            def descendants(self, control_type=None):
                if control_type == "Button":
                    return []
                return [self.slider]

        scenario = probe.WindowsScenario(Path("package.zip"), SOURCE_SHA, Path("evidence"), "test")
        scenario.main_window = Window()
        scenario._verify_process = lambda: None
        sent = []
        scenario._send_targeted_keys = lambda target, keys: sent.append((target, keys))
        clock = type("Clock", (), {"now": 0.0})()
        with mock.patch.object(probe.time, "monotonic", side_effect=lambda: clock.now), \
             mock.patch.object(probe.time, "sleep", side_effect=lambda seconds: setattr(clock, "now", clock.now + seconds)):
            scenario._stop_and_verify()
        self.assertEqual(sent, [(scenario.main_window, "V")])

    def test_stop_requires_repeated_zero_after_stop_operation(self) -> None:
        class StopButton:
            element_info = type("Info", (), {"automation_id": "stopButton"})()

        class Slider:
            element_info = type(
                "Info", (), {"class_name": "NWaveformSlider", "automation_id": "waveformSlider"}
            )()

            def __init__(self):
                self.values = iter((0.1, 0.2, 0.3, 0.0, 0.0, 0.1, 0.1, 0.1))

            def get_value(self):
                return next(self.values, 0.1)

        class Window:
            def __init__(self):
                self.slider = Slider()

            def descendants(self, control_type=None):
                if control_type == "Button":
                    return [StopButton()]
                return [StopButton(), self.slider]

            def set_focus(self):
                return None

        scenario = probe.WindowsScenario(Path("package.zip"), SOURCE_SHA, Path("evidence"), "test")
        scenario.main_window = Window()
        scenario._verify_process = lambda: None
        scenario._send_targeted_keys = lambda target, keys: None
        clock = type("Clock", (), {"now": 0.0})()
        with mock.patch.object(probe.time, "monotonic", side_effect=lambda: clock.now), \
             mock.patch.object(probe.time, "sleep", side_effect=lambda seconds: setattr(clock, "now", clock.now + seconds)):
            with self.assertRaises(probe.BlockedError):
                scenario._stop_and_verify()

    def test_keyboard_shortcut_blocks_when_control_focus_is_not_owned(self) -> None:
        class Playlist:
            handle = 222

            def set_focus(self):
                return None

            def has_keyboard_focus(self):
                return False

        scenario = probe.WindowsScenario(Path("package.zip"), SOURCE_SHA, Path("evidence"), "test")
        scenario.identity = probe.ProcessIdentity(123, 1.0, "player.exe")
        scenario.main_window = type("Window", (), {"handle": 111})()
        scenario._verify_process = lambda: None
        scenario._playlist = lambda: Playlist()
        with mock.patch.object(probe.os, "name", "nt"), \
             self.assertRaises(probe.BlockedError):
            scenario._send_move_to_trash()

    def test_keyboard_shortcut_blocks_when_foreground_pid_is_not_owned(self) -> None:
        class Playlist:
            handle = 222

            def set_focus(self):
                return None

            def has_keyboard_focus(self):
                return True

        playlist = Playlist()
        scenario = probe.WindowsScenario(Path("package.zip"), SOURCE_SHA, Path("evidence"), "test")
        scenario.identity = probe.ProcessIdentity(123, 1.0, "player.exe")
        scenario.main_window = type("Window", (), {"handle": 111})()
        scenario._verify_process = lambda: None
        scenario._playlist = lambda: playlist
        with mock.patch.object(probe, "_win32_window_pid", side_effect=lambda hwnd: 999 if hwnd == 333 else 123), \
             mock.patch.object(probe, "_win32_foreground_window", return_value=333), \
             self.assertRaises(probe.BlockedError):
            scenario._send_move_to_trash()

    def test_keyboard_shortcut_messages_are_targeted_to_owned_hwnd(self) -> None:
        class Playlist:
            handle = 222

            def set_focus(self):
                return None

            def has_keyboard_focus(self):
                return True

        playlist = Playlist()
        scenario = probe.WindowsScenario(Path("package.zip"), SOURCE_SHA, Path("evidence"), "test")
        scenario.identity = probe.ProcessIdentity(123, 1.0, "player.exe")
        scenario.main_window = type("Window", (), {"handle": 111})()
        scenario._verify_process = lambda: None
        sent = []
        with mock.patch.object(probe, "_win32_window_pid", return_value=123), \
             mock.patch.object(probe, "_win32_foreground_window", return_value=333), \
             mock.patch.object(probe, "_win32_root_window", return_value=111), \
             mock.patch.object(probe, "_win32_send_key", side_effect=lambda *args: sent.append(args)):
            scenario._send_targeted_keys(playlist, "Ctrl+Delete")
        self.assertEqual([call[0] for call in sent], [222, 222, 222, 222])

    def test_cleanup_error_preserves_primary_and_blocks_remaining_scenarios(self) -> None:
        contract = probe.validate_manifest(valid_manifest(), SOURCE_SHA)
        package = probe.ExtractedPackage(
            archive_sha256="archive",
            executable_sha256="executable",
            file_hashes_verified=2,
            root=Path("NulloyFork"),
            executable=Path("NulloyFork/NulloyFork.exe"),
            contract=contract,
        )

        class FakeScenario:
            created = []

            def __init__(self, *args, **kwargs):
                self.created.append(kwargs.get("name", args[-1]))
                self.process = object()

            def run(self, selected, answers):
                raise RuntimeError("primary native failure")

            def _capture_failure_evidence(self):
                return None

            def cleanup(self):
                raise OSError("cleanup failure")

        with tempfile.TemporaryDirectory() as temporary:
            args = probe.parse_args([
                "--package", str(Path(temporary) / "package.zip"),
                "--source-sha", SOURCE_SHA,
                "--output", str(Path(temporary) / "evidence"),
            ])
            patches = [
                mock.patch.object(probe, "is_windows_native", return_value=True),
                mock.patch.object(probe, "_manifest_from_archive", return_value=("archive", valid_manifest())),
                mock.patch.object(probe, "extract_and_validate", return_value=package),
                mock.patch.object(probe, "WindowsScenario", FakeScenario),
            ]
            with patches[0], patches[1], patches[2], patches[3]:
                code, result = probe.run_probe(args)

        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(FakeScenario.created, ["ordinary-cancellation"])
        first = result["scenarios"]["ordinary-cancellation"]
        self.assertIn("primary native failure", first["error"])
        self.assertIn("cleanup failure", first["cleanup_errors"][0])
        self.assertFalse(first["cleanup_verified"])
        self.assertEqual(
            result["scenarios"]["successful-recycling"]["status"], "BLOCKED"
        )

    def test_source_sha_is_exactly_forty_hex_characters(self) -> None:
        self.assertEqual(probe.parse_source_sha(SOURCE_SHA), SOURCE_SHA)
        for value in ("", "f" * 39, "f" * 41, "g" * 40):
            with self.subTest(value=value):
                with self.assertRaises(probe.ContractError):
                    probe.parse_source_sha(value)

    def test_manifest_fails_closed_for_source_and_safety_metadata(self) -> None:
        for field, value in (
            ("source_commit", "f" * 40),
            ("tracked_changes", True),
            ("portable", False),
            ("qt_major", "5"),
        ):
            manifest = valid_manifest(**{field: value})
            with self.subTest(field=field):
                with self.assertRaises(probe.ContractError):
                    probe.validate_manifest(manifest, SOURCE_SHA)

    def test_manifest_requires_build_info_and_executable_hash(self) -> None:
        for files in (
            {"NulloyFork.exe": "a" * 64},
            {"build-info.json": "b" * 64},
        ):
            with self.subTest(files=files):
                with self.assertRaises(probe.ContractError):
                    probe.validate_manifest(valid_manifest(files=files), SOURCE_SHA)

    def test_archive_contract_rejects_traversal_and_outside_members(self) -> None:
        for members in (
            ["NulloyFork/package-manifest.json", "NulloyFork/../escape.txt"],
            ["NulloyFork/package-manifest.json", "other/file.txt"],
            ["NulloyFork/package-manifest.json", "/absolute.txt"],
        ):
            with self.subTest(members=members):
                with self.assertRaises(probe.ContractError):
                    probe.validate_archive_members(members, "NulloyFork")

    def test_safe_extract_verifies_build_info_and_every_manifest_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "package.zip"
            build_info = {
                "source_commit": SOURCE_SHA,
                "tracked_changes": False,
                "executable": "NulloyFork.exe",
                "portable": True,
            }
            executable = b"not-a-real-pe-fixture"
            build_info_bytes = (json.dumps(build_info, sort_keys=True) + "\n").encode()
            manifest = valid_manifest(
                files={
                    "NulloyFork.exe": hashlib.sha256(executable).hexdigest(),
                    "build-info.json": hashlib.sha256(build_info_bytes).hexdigest(),
                }
            )
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("NulloyFork/NulloyFork.exe", executable)
                archive.writestr("NulloyFork/build-info.json", build_info_bytes)
                archive.writestr(
                    "NulloyFork/package-manifest.json",
                    json.dumps(manifest).encode() + b"\n",
                )
            extracted = probe.extract_and_validate(
                archive_path, Path(temporary) / "extracted", SOURCE_SHA
            )
            self.assertEqual(extracted.executable_sha256, hashlib.sha256(executable).hexdigest())
            self.assertEqual(extracted.file_hashes_verified, 2)

    def test_recycle_metadata_decoder_requires_a_windows_original_path(self) -> None:
        original = r"C:\Users\runneradmin\AppData\Local\Temp\fixture.wav"
        raw = (1).to_bytes(8, "little") + (123).to_bytes(8, "little")
        raw += (456).to_bytes(8, "little") + (original + "\0").encode("utf-16le")
        self.assertEqual(probe.recycle_metadata_original_path(raw), original)
        self.assertIsNone(probe.recycle_metadata_original_path(b"short"))
        self.assertIsNone(probe.recycle_metadata_original_path(("not-a-path\0").encode("utf-16le")))

    def test_wav_fixture_generation_is_disposable_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = probe.make_wav_fixtures(Path(temporary), "run-test")
            self.assertEqual(len(paths), 3)
            self.assertTrue(all(path.suffix == ".wav" for path in paths))
            first = paths[0].read_bytes()
            self.assertGreater(len(first), 44)
            self.assertEqual(first, paths[0].read_bytes())
            self.assertTrue(all(path.parent.name == "run-test" for path in paths))

    def test_verdict_is_fail_closed_when_cleanup_is_not_verified(self) -> None:
        self.assertEqual(probe.verdict([True, True], True), "PASS")
        self.assertEqual(probe.verdict([True, False], True), "FAIL")
        self.assertEqual(probe.verdict([True, True], False), "FAIL")
        self.assertEqual(probe.status_exit_code("PASS"), 0)
        self.assertEqual(probe.status_exit_code("FAIL"), 1)
        self.assertEqual(probe.status_exit_code("BLOCKED"), 2)

    def test_linux_cli_is_blocked_without_claiming_windows_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            args = probe.parse_args(
                [
                    "--package",
                    str(Path(temporary) / "missing.zip"),
                    "--source-sha",
                    SOURCE_SHA,
                    "--output",
                    str(output),
                    "--headless-audio",
                ]
            )
            code, result = probe.run_probe(args)
            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("Windows", result["error"])
            written = json.loads((output / "result.json").read_text())
            self.assertEqual(written["status"], "BLOCKED")
            self.assertFalse(written.get("execution_started", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
