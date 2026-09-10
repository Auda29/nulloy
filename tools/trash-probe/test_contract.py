#!/usr/bin/env python3
"""Linux-runnable contract tests for the packaged Windows trash probe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
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
