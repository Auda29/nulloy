from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]

class CandidateWorkflow(unittest.TestCase):
    def test_candidate_is_pinned_and_never_rebuilt(self):
        path = ROOT / '.github/workflows/pr24-candidate-acceptance.yml'
        self.assertTrue(path.exists())
        data = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(data['permissions'], {'contents': 'read', 'actions': 'read'})
        self.assertEqual(data['on']['push']['branches'], ['test/pr24-playback-acceptance'])
        steps = data['jobs']['windows']['steps']
        download = next(s for s in steps if s.get('uses', '').startswith('actions/download-artifact@'))
        self.assertEqual(download['with']['run-id'], '36995053598')
        self.assertEqual(download['with']['name'], 'Nulloy-Qt6-windows-x64')
        commands = '\n'.join(s.get('run', '') for s in steps)
        self.assertIn('--source-sha 7b292852a85bd6a40a99cd7d7813660250ed5b3d', commands)
        self.assertIn('Get-FileHash', commands)
        self.assertIn('2327a4a5e5599e7788f595c4babb83595aef37939d2375b8c72cca1edf53614f', commands)
        self.assertIn('--case all', commands)
        self.assertIn('--group $env:PROBE', commands)
        self.assertNotIn('cmake', commands)
        self.assertNotIn('continue-on-error', str(data))
        self.assertEqual(data['jobs']['windows']['strategy']['matrix']['probe'], ['populated', 'restored', 'commands', 'ipc'])
        upload = next(s for s in steps if s.get('uses', '').startswith('actions/upload-artifact@'))
        self.assertEqual(upload['if'], 'always()')
        self.assertEqual(upload['with']['retention-days'], '7')

if __name__ == '__main__':
    unittest.main()
