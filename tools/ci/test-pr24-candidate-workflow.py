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
        self.assertEqual(download['with']['run-id'], '36991823896')
        self.assertEqual(download['with']['name'], 'Nulloy-Qt6-windows-x64')
        commands = '\n'.join(s.get('run', '') for s in steps)
        self.assertIn('--source-sha aa78a3352497ca7ba431e9aa0ff50e820e95048a', commands)
        self.assertIn('Get-FileHash', commands)
        self.assertNotIn('cmake', commands)
        self.assertNotIn('continue-on-error', str(data))
        self.assertEqual(data['jobs']['windows']['strategy']['matrix']['probe'], ['playback', 'ipc'])
        upload = next(s for s in steps if s.get('uses', '').startswith('actions/upload-artifact@'))
        self.assertEqual(upload['if'], 'always()')
        self.assertEqual(upload['with']['retention-days'], '7')

if __name__ == '__main__':
    unittest.main()
