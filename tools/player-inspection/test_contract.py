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


if __name__ == "__main__":
    unittest.main()
