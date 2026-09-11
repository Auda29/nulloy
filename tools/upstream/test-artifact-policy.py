"""Workflow storage contracts. Run with Python + PyYAML (6.x). No builds/API writes."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    # BaseLoader avoids YAML 1.1 interpreting the GitHub 'on' key as True.
    return yaml.load((ROOT / '.github/workflows' / name).read_text(), Loader=yaml.BaseLoader)


class ArtifactPolicy(unittest.TestCase):
    def setUp(self):
        self.windows = load('windows-cmake.yml')
        self.steps = {s.get('name'): s for s in self.windows['jobs']['windows']['steps']}

    def test_pr_checks_preserved_without_duplicate_tag_build(self):
        self.assertIsNone(self.windows['on']['pull_request'] or None)
        self.assertNotIn('tags', self.windows['on']['push'])
        self.assertEqual(self.windows['on']['push']['branches'],
                         ['master', 'codex/phase-2-*', 'codex/phase-3-*', 'codex/phase-4-*'])

    def test_packages_are_explicit_opt_in(self):
        for event in ('workflow_dispatch', 'workflow_call'):
            self.assertIsInstance(self.windows['on'][event], dict, 'explicit inputs are missing')
            spec = self.windows['on'][event]['inputs']['upload_packages']
            self.assertEqual(spec['type'], 'boolean')
            self.assertEqual(spec['default'], 'false')
        upload = self.steps['Upload test package']
        self.assertEqual(upload.get('if'), '${{ inputs.upload_packages == true }}')
        self.assertEqual(upload['with'].get('retention-days'), '3')
        self.assertEqual(upload['with']['if-no-files-found'], 'error')

    def test_evidence_is_retained_on_failure_but_bounded(self):
        upload = self.steps['Upload test evidence']
        self.assertEqual(upload['if'], 'always()')
        self.assertEqual(upload['with'].get('retention-days'), '7')
        self.assertIn('package-info.json', upload['with']['path'])
        self.assertIn('LastTest.log', upload['with']['path'])

    def test_release_caller_explicitly_requests_packages(self):
        release = load('alpha-release.yml')
        self.assertEqual(release['jobs']['test'].get('with', {}).get('upload_packages'), 'true')
        self.assertEqual(release['on']['push']['tags'], ['v*-alpha.*'])
        self.assertEqual(release['jobs']['test']['uses'], './.github/workflows/windows-cmake.yml')

    def test_build_verification_and_serial_matrix_unchanged(self):
        job = self.windows['jobs']['windows']
        self.assertEqual(job['strategy']['max-parallel'], '1')
        self.assertEqual([x['qt'] for x in job['strategy']['matrix']['include']], ['5', '6'])
        for name in ('Configure, build and test', 'Package and verify without toolchain PATH',
                     'Verify portable startup and registry recovery',
                     'Verify audio formats and Unicode tag roundtrips'):
            self.assertNotIn('upload_packages', str(self.steps[name]))
        self.assertIn('ctest --preset', self.steps['Configure, build and test']['run'])


if __name__ == '__main__':
    unittest.main()
