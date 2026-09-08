import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("alpha", Path(__file__).with_name("alpha.py"))
alpha = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alpha)


class AlphaTest(unittest.TestCase):
    def test_tag_must_match_version(self):
        presets = {"configurePresets": [{"name": "windows-portable-x64",
                    "cacheVariables": {"NULLOY_VERSION": "0.10.0-alpha.1"}}]}
        self.assertEqual(alpha.version_from_tag("v0.10.0-alpha.1", presets), "0.10.0-alpha.1")
        for tag in ("v0.10.0", "v0.10.0-alpha.0", "v0.10.0-alpha.2", "v0.10.0-alpha.1;echo bad"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                alpha.version_from_tag(tag, presets)

    def test_package_and_reports_must_share_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "test.zip"
            content = b"test binary"
            manifest = {"source_commit": "a" * 40, "version": "0.10.0-alpha.1", "qt_major": "6",
                        "tracked_changes": False, "portable": True, "upstream_update_check": False,
                        "files": {"NulloyFork.exe": hashlib.sha256(content).hexdigest()}}
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("NulloyFork/package-manifest.json", json.dumps(manifest))
                archive.writestr("NulloyFork/NulloyFork.exe", content)
            digest = alpha.sha256(package)
            package.with_suffix(".zip.sha256").write_text(digest + "  test.zip\n")
            report = {"archive_sha256": digest, "qt_major": "6", "skins": ["a", "b", "c", "d"],
                      "portable_process_isolation": True, "unicode_tag_roundtrip": True,
                      "formats": ["wav", "mp3", "flac", "ogg", "opus", "wv"]}
            for folder in ("package-check", "format-check", "startup-check", "startup-check-missing",
                           "startup-check-corrupt", "startup-check-changed-plugin"):
                dest = root / "evidence/nested/build" / folder
                dest.mkdir(parents=True)
                (dest / "verified.json").write_text(json.dumps(report))
            args = (package, manifest["version"], manifest["source_commit"], root / "evidence")
            self.assertEqual(alpha.verify_package(*args)[0], digest)
            with self.assertRaises(ValueError):
                alpha.verify_package(package, manifest["version"], "b" * 40, root / "evidence")
            wrong = copy.deepcopy(report)
            wrong["archive_sha256"] = "0" * 64
            (root / "evidence/nested/build/startup-check/verified.json").write_text(json.dumps(wrong))
            with self.assertRaises(ValueError):
                alpha.verify_package(*args)


if __name__ == "__main__":
    unittest.main()
