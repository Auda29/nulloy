import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import probe


class ScenarioTests(unittest.TestCase):
    def test_changed_registry_marker_prevents_deletion(self):
        class Key:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        deleted = []
        registry = SimpleNamespace(HKEY_CURRENT_USER=1,
            OpenKey=lambda *args: Key(), QueryValueEx=lambda *args: ('foreign', 1),
            DeleteKey=lambda *args: deleted.append(args))
        run = object.__new__(probe.WindowsDesktopRun)
        run.registry_key_created = True
        run.run_id = 'ours'
        run.profile = probe.shell_verb_profile('ours', Path('player.exe'))
        with patch.dict(sys.modules, {'winreg': registry}):
            self.assertFalse(run._registry_cleanup())
        self.assertEqual(deleted, [])

    def test_menu_label_in_another_process_cannot_be_invoked(self):
        run = object.__new__(probe.WindowsDesktopRun)
        run.profile = probe.shell_verb_profile('ours', Path('player.exe'))
        explorer = SimpleNamespace(handle=100, element_info=SimpleNamespace(process_id=10))
        foreign = SimpleNamespace(element_info=SimpleNamespace(process_id=11),
            descendants=lambda **kwargs: [SimpleNamespace(window_text=lambda: run.profile.label)])
        run.desktop = SimpleNamespace(windows=lambda: [foreign])
        with patch.object(run, '_find_explorer', return_value=explorer), \
                patch.dict(sys.modules, {'win32gui': SimpleNamespace(GetForegroundWindow=lambda: 100)}):
            self.assertIsNone(run._find_probe_menu_item())

    def test_late_primary_is_discovered_without_losing_exited_client_identity(self):
        run = object.__new__(probe.WindowsDesktopRun)
        run.player_process_baseline = ()
        run.owned_player_processes = []
        client = probe.ProcessIdentity(10, 1.0, 'private/player.exe')
        primary = probe.ProcessIdentity(11, 2.0, 'private/player.exe')
        with patch.object(run, '_process_snapshot', side_effect=[[(None, client)],
                          [(None, primary)], []]):
            self.assertTrue(run._capture_new_player_processes())
            self.assertTrue(run._capture_new_player_processes())
            self.assertFalse(run._capture_new_player_processes())
        self.assertEqual(run.owned_player_processes, [client, primary])

    def test_scenario_preferences_survive_settings_version_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / 'evidence'
            evidence.mkdir()
            package = SimpleNamespace(root=root, executable=root / 'NulloyFork.exe',
                                      contract=SimpleNamespace(portable=True))
            run = probe.WindowsDesktopRun(package, evidence, 'fixture',
                                          scenario=probe.OpenScenario(False, True))
            run._prepare_scenario({'PATH': 'test'})
            settings = (root / 'Data/NulloyFork.cfg').read_text()
            self.assertIn('SettingsVersion=0.8\n', settings)
            self.assertIn('EnqueueFiles=false\n', settings)
            self.assertIn('PlayEnqueued=true\n', settings)
            self.assertIn('RestorePlaylist=false\n', settings)
            self.assertFalse(run.player_launch_started)

    def test_nonportable_settings_are_never_changed(self):
        package = SimpleNamespace(executable=Path('player.exe'),
                                  contract=SimpleNamespace(portable=False))
        run = probe.WindowsDesktopRun(package, Path('.'), 'fixture',
                                      scenario=probe.OpenScenario(True, False))
        with self.assertRaisesRegex(probe.ContractError, 'isolated portable'):
            run._prepare_scenario({})

    def test_larger_selection_creates_distinct_valid_wavs(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = probe._make_fixtures(Path(tmp) / 'fixtures', 12)
            self.assertEqual(len(files), 12)
            self.assertEqual(len(set(files)), 12)
            self.assertTrue(all(path.stat().st_size > 44100 for path in files))


if __name__ == '__main__':
    unittest.main()
