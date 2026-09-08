import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("profile_import", Path(__file__).with_name("import-profile.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProfileImportTest(unittest.TestCase):
    def test_copy_relative_playlist_and_existing_profile_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            target = base / "portable"
            target.mkdir()
            (target / "build-info.json").write_text(json.dumps({"portable": True, "executable": "NulloyFork.exe"}))
            config = base / "copy.cfg"
            playlist = base / "copy.m3u"
            config.write_bytes(b"[General]\nVolume=0.375\n")
            playlist.write_text("#EXTM3U\n#NULLOY:0,2,0.5,title\nGrüße.wav\n", encoding="utf-8")
            original = (config.read_bytes(), playlist.read_bytes())
            with self.assertRaises(ValueError):
                module.migrate(config, playlist, target)
            self.assertFalse((target / "Data/NulloyFork.cfg").exists())
            module.migrate(config, playlist, target, base / "original-profile")
            output = target / "Data/NulloyFork.m3u"
            self.assertIn(str(base / "original-profile/Grüße.wav"), output.read_text(encoding="utf-8"))
            self.assertIn("#NULLOY:0,2,0.5,title", output.read_text(encoding="utf-8"))
            self.assertEqual((target / "Data/NulloyFork.cfg").read_bytes(), original[0])
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                module.migrate(config, playlist, target, base)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual((config.read_bytes(), playlist.read_bytes()), original)


if __name__ == "__main__":
    unittest.main()
