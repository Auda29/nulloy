"""Contracts for isolated, exact-artifact PR24 acceptance (no API calls)."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/pr24-playback-acceptance.yml'

class WorkflowContracts(unittest.TestCase):
    def workflow(self):
        self.assertTrue(WORKFLOW.is_file(), 'dedicated acceptance workflow missing')
        return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)

    def test_only_authorized_branch_or_dispatch_can_execute(self):
        w = self.workflow()
        self.assertEqual(set(w['on']), {'push', 'workflow_dispatch'})
        self.assertEqual(w['on']['push']['branches'], ['test/pr24-playback-acceptance'])
        self.assertEqual(w['permissions'], {'contents': 'read', 'actions': 'read'})
        self.assertEqual(w['jobs']['windows']['runs-on'], 'windows-2022')
        self.assertEqual(w['jobs']['windows']['needs'], 'contracts')

    def test_reuses_exact_package_without_build(self):
        w = self.workflow()
        steps = w['jobs']['windows']['steps']
        download = next(s for s in steps if s.get('uses', '').startswith('actions/download-artifact@'))
        self.assertEqual(download['with']['run-id'], '36843804143')
        self.assertEqual(download['with']['name'], 'Nulloy-Qt6-windows-x64')
        text = '\n'.join(s.get('run', '') for s in steps)
        self.assertIn('039c21768668d69649ee6950b9039f16b6fde0ec0835e2f8f8278ba3a79fe9be', text)
        self.assertIn('be5b1e88286c1ff0bbe7e298e3585bbfb248aba5', text)
        self.assertIn('--group', text)
        self.assertNotIn('cmake', text)
        self.assertNotIn('git push', text)
        self.assertNotIn('gh pr merge', text)

    def test_all_groups_keep_evidence_on_failure(self):
        w = self.workflow()
        job = w['jobs']['windows']
        self.assertEqual(job['strategy']['fail-fast'], 'false')
        self.assertEqual(job['strategy']['matrix']['group'], ['populated', 'restored', 'rapid', 'commands'])
        upload = next(s for s in job['steps'] if s.get('uses', '').startswith('actions/upload-artifact@'))
        self.assertEqual(upload['if'], 'always()')
        self.assertEqual(upload['with']['retention-days'], '7')
        self.assertEqual(upload['with']['if-no-files-found'], 'error')
        self.assertEqual(upload['with']['path'], 'evidence/')
        self.assertNotIn('package', upload['with']['path'])

if __name__ == '__main__':
    unittest.main()
