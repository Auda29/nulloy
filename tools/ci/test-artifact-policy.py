"""Storage policy contracts: Python + PyYAML 6.x; no builds or API writes."""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    # Preserve GitHub's `on` key rather than YAML 1.1's boolean interpretation.
    return yaml.load((ROOT / '.github/workflows' / name).read_text(),
                     Loader=yaml.BaseLoader)


class ArtifactPolicy(unittest.TestCase):
    def setUp(self):
        self.windows = load('windows-cmake.yml')
        self.steps = {s.get('name'): s for s in self.windows['jobs']['windows']['steps']}

    def test_opt_in_package_producer_and_release_consumer(self):
        for event in ('workflow_dispatch', 'workflow_call'):
            config = self.windows['on'][event]
            self.assertIsInstance(config, dict, 'typed upload input is missing')
            spec = config.get('inputs', {}).get('upload_packages', {})
            self.assertEqual(spec.get('type'), 'boolean')
            self.assertEqual(spec.get('default'), 'false')
        upload = self.steps['Upload test package']
        self.assertEqual(upload.get('if'), '${{ inputs.upload_packages == true }}')
        self.assertEqual(upload['with'].get('retention-days'), '3')
        self.assertEqual(upload['with']['name'], 'Nulloy-Qt${{ matrix.qt }}-windows-x64')
        self.assertEqual(upload['with']['path'].splitlines(), [
            '${{ matrix.build }}/*-windows-x64.zip',
            '${{ matrix.build }}/*-windows-x64.zip.sha256'])
        self.assertEqual(upload['with']['if-no-files-found'], 'error')
        release = load('alpha-release.yml')
        caller = release['jobs']['test']
        self.assertEqual(caller['uses'], './.github/workflows/windows-cmake.yml')
        self.assertEqual(caller.get('with', {}).get('upload_packages'), 'true')
        self.assertEqual(release['jobs']['publish']['needs'], ['validate', 'test'])
        downloads = [s['with']['name'] for s in release['jobs']['publish']['steps']
                     if s.get('uses', '').startswith('actions/download-artifact@')]
        self.assertEqual(downloads, ['Nulloy-Qt6-windows-x64', 'Windows-Qt6-test-evidence'])

    def test_all_existing_triggers_are_preserved(self):
        self.assertEqual(self.windows['on']['pull_request'], '')
        self.assertEqual(self.windows['on']['push'], {'branches': [
            'master', 'codex/phase-2-*', 'codex/phase-3-*', 'codex/phase-4-*']})
        self.assertEqual(load('alpha-release.yml')['on']['push']['tags'], ['v*-alpha.*'])

    def test_evidence_is_not_gated_or_shortened(self):
        evidence = self.steps['Upload test evidence']
        self.assertEqual(evidence['if'], 'always()')
        self.assertNotIn('retention-days', evidence['with'])
        self.assertEqual(evidence['with']['name'], 'Windows-Qt${{ matrix.qt }}-test-evidence')
        self.assertEqual(evidence['with']['path'].splitlines(), [
            '${{ matrix.build }}/*-results.txt', '${{ matrix.build }}/toolchain.txt',
            '${{ matrix.build }}/package-check/', '${{ matrix.build }}/format-check/',
            '${{ matrix.build }}/startup-check*/', '${{ matrix.build }}/package-info.json',
            '${{ matrix.build }}/Testing/Temporary/LastTest.log',
            '.phase3/skin-probe/*-results.txt'])

    def test_build_matrix_and_checks_are_not_upload_gated(self):
        job = self.windows['jobs']['windows']
        self.assertNotIn('if', job)
        self.assertNotIn('max-parallel', job['strategy'])
        self.assertEqual(job['strategy']['fail-fast'], 'false')
        matrix = job['strategy']['matrix']['include']
        self.assertEqual([(m['qt'], m['preset'], m['build']) for m in matrix], [
            ('5', 'windows-x64', '.phase2/build'),
            ('6', 'windows-portable-x64', '.phase4/build')])
        names = ['Configure, build and test', 'Package and verify without toolchain PATH',
                 'Verify portable startup and registry recovery',
                 'Verify audio formats and Unicode tag roundtrips',
                 'Test shared Qt 6 skin adapters']
        for name in names:
            step = self.steps[name]
            self.assertNotIn('upload_packages', str(step))
            self.assertEqual(step.get('if'), 'matrix.qt == 6' if name in (
                'Verify portable startup and registry recovery',
                'Test shared Qt 6 skin adapters') else None)
        self.assertIn('ctest --preset', self.steps[names[0]]['run'])
        self.assertIn('tools/release/test-alpha.py', self.steps[names[0]]['run'])
        self.assertIn('tools/phase4/test-import-profile.py', self.steps[names[0]]['run'])

    def test_policy_contract_is_executed_in_ci(self):
        job = self.windows['jobs'].get('artifact-policy')
        self.assertIsInstance(job, dict, 'policy contract CI job is missing')
        self.assertNotIn('if', job)
        commands = '\n'.join(s.get('run', '') for s in job['steps'])
        self.assertIn('python -m pip install PyYAML==6.0.2', commands)
        self.assertIn('python tools/ci/test-artifact-policy.py', commands)


if __name__ == '__main__':
    unittest.main()
