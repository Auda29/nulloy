import tempfile
import sys
import os
import uuid
import dataclasses
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import probe


class ScenarioTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'native Windows path aliases')
    def test_trace_delivery_accepts_real_short_and_long_paths(self):
        import ctypes
        from ctypes import wintypes

        get_short = ctypes.windll.kernel32.GetShortPathNameW
        get_short.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        profile_temp = Path(os.environ['USERPROFILE']) / 'AppData/Local/Temp'
        with tempfile.TemporaryDirectory(dir=profile_temp, prefix='nulloy-alias-') as temp:
            expected = Path(temp) / 'fixture.wav'
            expected.write_bytes(b'fixture')
            size = get_short(str(expected), None, 0)
            self.assertGreater(size, 0)
            buffer = ctypes.create_unicode_buffer(size)
            self.assertGreater(get_short(str(expected), buffer, size), 0)
            alias = Path(buffer.value)
            if str(alias).casefold() == str(expected).casefold():
                self.skipTest('Volume does not supply distinct short names')
            processes = {'1': [{'event': 'main-start'}, {'event': 'player-connected'},
                               {'event': 'player-message', 'message': str(expected)}]}
            result = probe.startup_delivery(processes, [alias], ['fixture.wav'], 1)
            self.assertEqual(result['launch_count'], 1)

    def test_trace_delivery_requires_client_success_and_matches_ui_order(self):
        processes = {
            '1': [{'event': 'main-start'}, {'event': 'player-connected'},
                  {'event': 'player-message', 'message': 'C:/fixtures/01.wav'},
                  {'event': 'receive-frame', 'message': 'C:/fixtures/02.wav'},
                  {'event': 'receive-dispatch', 'message': 'C:/fixtures/02.wav'},
                  {'event': 'player-message', 'message': 'C:/fixtures/02.wav'}],
            '2': [{'event': 'main-start'},
                  {'event': 'send-begin', 'message': 'C:/fixtures/02.wav'},
                  {'event': 'send-end', 'acknowledged': True},
                  {'event': 'main-exit', 'exit_code': 0, 'role': 'client'}]}
        expected = [Path('C:/fixtures/01.wav'), Path('C:/fixtures/02.wav')]
        rows = ['01.wav', '02.wav']
        self.assertEqual(probe.startup_delivery(processes, expected, rows, 2)['delivery_order'], rows)
        with self.assertRaisesRegex(probe.ContractError, 'order differs'):
            probe.startup_delivery(processes, expected, rows[::-1], 2)
        processes['2'][-1]['exit_code'] = 1
        with self.assertRaisesRegex(probe.ContractError, 'acknowledged delivery'):
            probe.startup_delivery(processes, expected, rows, 2)
        processes['2'][-1]['exit_code'] = 0
        processes['1'].append({'event': 'player-message', 'message': 'C:/fixtures/02.wav'})
        with self.assertRaisesRegex(probe.ContractError, 'exact-once'):
            probe.startup_delivery(processes, expected, rows, 2)

    def test_warm_primary_alone_is_not_a_settled_explorer_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = object.__new__(probe.WindowsDesktopRun)
            run.trace_directory = root
            run.evidence = root
            def trace(pid, events):
                (root / f'{pid}.jsonl').write_text(''.join(
                    json.dumps({'event': event}) + '\n' for event in events))
            trace(1, ['main-start', 'player-connected'])
            self.assertFalse(run._startup_settled(4))
            trace(2, ['main-start', 'send-begin'])
            trace(3, ['main-start', 'main-exit'])
            trace(4, ['main-start', 'main-exit'])
            self.assertFalse(run._startup_settled(4))
            trace(2, ['main-start', 'send-begin', 'main-exit'])
            self.assertTrue(run._startup_settled(4))

    def test_late_second_main_window_invalidates_warm_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = object.__new__(probe.WindowsDesktopRun)
            run.evidence = Path(tmp)
            windows = [SimpleNamespace(handle=pid, window_text=lambda: 'Player',
                       element_info=SimpleNamespace(process_id=pid, class_name='NMainWindow'))
                       for pid in (1, 2)]
            run.player_window = windows[0]
            with patch.object(run, '_capture_new_player_processes'), \
                    patch.object(run, '_owned_player_windows', return_value=windows):
                with self.assertRaisesRegex(probe.ContractError, 'observed 2'):
                    run._assert_one_settled_player()

    @unittest.skipUnless(os.name == 'nt', 'real Win32 registry lifecycle')
    def test_native_registry_install_readback_and_cleanup(self):
        import winreg

        package = SimpleNamespace(executable=Path('private-player.exe'))
        run = probe.WindowsDesktopRun(package, Path('.'), uuid.uuid4().hex)
        path = 'Software\\NulloyProbeContract-' + run.run_id
        run.profile = dataclasses.replace(run.profile, registry_path=path)
        try:
            with patch.object(probe, '_notify_association_changed'):
                run._registry_install()
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                    self.assertEqual(winreg.QueryValueEx(key, 'NulloyProbeOwner')[0], run.run_id)
                self.assertTrue(run._registry_cleanup())
                with self.assertRaises(FileNotFoundError):
                    winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        finally:
            for key in (path + '\\command', path):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
                except FileNotFoundError:
                    pass

    @unittest.skipUnless(os.name == 'nt', 'real Win32 registry contract')
    def test_native_exclusive_registry_handle_and_collision(self):
        import winreg

        path = 'Software\\NulloyProbeContract-' + uuid.uuid4().hex
        created = False
        try:
            with probe._create_exclusive_registry_key(path) as key:
                created = True
                winreg.SetValueEx(key, 'Owner', 0, winreg.REG_SZ, 'original')
            with self.assertRaises(probe.BlockedError):
                probe._create_exclusive_registry_key(path)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                self.assertEqual(winreg.QueryValueEx(key, 'Owner')[0], 'original')
        finally:
            if created:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)

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
