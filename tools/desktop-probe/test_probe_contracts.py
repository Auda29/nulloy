import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import probe


SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"


class ManifestContractTests(unittest.TestCase):
    def test_accepts_clean_manifest_for_exact_source_sha(self):
        manifest = {
            "source_commit": SOURCE_SHA,
            "tracked_changes": False,
            "root": "Nulloy",
            "executable": "Nulloy.exe",
            "portable": False,
            "upstream_update_check": False,
            "qt_major": "6",
            "files": {"Nulloy.exe": "a" * 64},
        }
        contract = probe.validate_manifest(manifest, SOURCE_SHA)
        self.assertEqual(contract.source_commit, SOURCE_SHA)
        self.assertEqual(contract.executable, "Nulloy.exe")
        self.assertFalse(contract.portable)

    def test_rejects_tracked_package_even_when_sha_matches(self):
        manifest = {"source_commit": SOURCE_SHA, "tracked_changes": True}
        with self.assertRaises(probe.ContractError):
            probe.validate_manifest(manifest, SOURCE_SHA)

    def test_rejects_source_sha_mismatch_and_bad_input_format(self):
        manifest = {"source_commit": SOURCE_SHA, "tracked_changes": False}
        with self.assertRaises(probe.ContractError):
            probe.validate_manifest(manifest, "f" * 40)
        with self.assertRaises(probe.ContractError):
            probe.validate_manifest(manifest, "not-a-sha")

    def test_rejects_enabled_upstream_update_profile(self):
        manifest = {
            "source_commit": SOURCE_SHA,
            "tracked_changes": False,
            "upstream_update_check": True,
        }
        with self.assertRaises(probe.ContractError):
            probe.validate_manifest(manifest, SOURCE_SHA)


class ArchiveContractTests(unittest.TestCase):
    def test_rejects_archive_member_escape(self):
        with self.assertRaises(probe.ContractError):
            probe.validate_archive_members(
                ["Nulloy/package-manifest.json", "Nulloy/../outside.exe"], "Nulloy"
            )

    def test_validates_manifest_file_hashes_and_executable_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Nulloy"
            root.mkdir()
            exe = root / "Nulloy.exe"
            exe.write_bytes(b"fake executable")
            manifest = {
                "source_commit": SOURCE_SHA,
                "tracked_changes": False,
                "upstream_update_check": False,
                "qt_major": "6",
                "portable": False,
                "root": "Nulloy",
                "executable": "Nulloy.exe",
                "files": {"Nulloy.exe": hashlib.sha256(exe.read_bytes()).hexdigest()},
            }
            result = probe.validate_extracted_package(root, manifest, SOURCE_SHA)
            self.assertEqual(result.executable_sha256, hashlib.sha256(exe.read_bytes()).hexdigest())

    def test_cli_parser_requires_exact_contract_arguments(self):
        args = probe.parse_args(["--package", "package.zip", "--output", "evidence", "--source-sha", SOURCE_SHA])
        self.assertEqual(args.package, Path("package.zip"))
        self.assertEqual(args.output, Path("evidence"))
        self.assertEqual(args.source_sha, SOURCE_SHA)


class ShellAndVerdictContractTests(unittest.TestCase):
    def test_shell_command_is_per_file_not_multi_open(self):
        command = probe.shell_command(Path(r"C:\pkg\Nulloy.exe"))
        self.assertIn('"%1"', command)
        self.assertNotIn('"%*"', command)

    def test_document_shell_profile_has_unique_key_and_document_model(self):
        profile = probe.shell_verb_profile("run-abc", Path(r"C:\pkg\Nulloy.exe"))
        self.assertRegex(profile.key_name, r"^NulloyDesktopProbe-run-abc$")
        self.assertEqual(profile.multi_select_model, "Document")
        self.assertIn('"%1"', profile.command)

    def test_pass_requires_every_assertion_and_cleanup(self):
        self.assertEqual(probe.verdict([True, True, True], True), "PASS")
        self.assertEqual(probe.verdict([True, False, True], True), "FAIL")
        self.assertEqual(probe.verdict([True, True, True], False), "FAIL")

    def test_playlist_rows_must_be_exactly_once(self):
        expected = [r"C:\fixtures\one.wav", r"C:\fixtures\two.wav", r"C:\fixtures\three.wav"]
        self.assertTrue(probe.exact_playlist_rows(expected, expected))
        with self.assertRaises(probe.ContractError):
            probe.exact_playlist_rows(expected + [expected[0]], expected)
        with self.assertRaises(probe.ContractError):
            probe.exact_playlist_rows(expected[:2], expected)


if __name__ == "__main__":
    unittest.main()
