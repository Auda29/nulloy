import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import probe

class Control:
    def __init__(self, name='', children=()):
        self.name, self.children = name, children
    def window_text(self):
        return self.name
    def descendants(self, **kwargs):
        return list(self.children)

class ReviewRegressions(unittest.TestCase):
    def test_extra_playlist_row_must_not_be_filtered_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = object.__new__(probe.WindowsDesktopRun)
            runtime.evidence = Path(tmp)
            runtime.player_window = Control(children=[Control(children=[Control('one.wav'), Control('two.wav'), Control('unrelated.wav')])])
            with self.assertRaises(probe.ContractError):
                runtime._read_playlist_rows([Path('one.wav'), Path('two.wav')])

    def test_windows_path_aliases_rejected(self):
        for name in ['C:/escape.exe', 'file.exe:stream', 'CON', 'name.', 'name ', './ok.exe', 'a//b.exe']:
            with self.subTest(name=name), self.assertRaises(probe.ContractError):
                probe._relative_manifest_path(name, 'file')
