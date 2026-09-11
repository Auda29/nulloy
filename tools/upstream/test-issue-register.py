"""Characterization contracts for the complete, versioned upstream register."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]

class IssueRegister(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT/'docs/upstream/issue-register.json').read_text(encoding='utf-8'))
        cls.rows = cls.data['issues']

    def test_exact_original_issue_set_without_duplicates(self):
        original = (ROOT/'docs/UPSTREAM_ISSUES_ANALYSIS.md').read_text(encoding='utf-8')
        expected = set(map(int, re.findall(r'^\| \[#(\d+)\]', original, re.M)))
        numbers = [r['number'] for r in self.rows]
        self.assertEqual(len(expected), 80)
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual(set(numbers), expected)
        self.assertEqual(self.data['issue_count'], len(numbers))

    def test_comment_totals_and_evidence(self):
        comments = []
        for row in self.rows:
            self.assertTrue(row['body_read'])
            self.assertEqual(row['api_asserted_comments'], row['comments_read'])
            self.assertEqual(row['comments_read'], len(row['comment_ids_read']))
            self.assertTrue(row['code_evidence'])
            self.assertTrue(row['rationale'])
            self.assertTrue(row['next_test'])
            self.assertEqual(row['issue_url'], f'https://github.com/nulloy/nulloy/issues/{row["number"]}')
            comments.extend(row['comment_ids_read'])
        self.assertEqual(len(comments), len(set(comments)))
        self.assertEqual(len(comments), self.data['comment_count'])
        self.assertEqual(self.data['comment_count'], 126)
        self.assertRegex(self.data['snapshot_sha256'], r'^[0-9a-f]{64}$')

    def test_display_and_machine_register_match(self):
        text = (ROOT/'docs/upstream/STATUS.md').read_text(encoding='utf-8')
        displayed = list(map(int, re.findall(r'^\| \[#(\d+)\]', text, re.M)))
        self.assertEqual(displayed, [r['number'] for r in self.rows])
        for row in self.rows:
            delivery = row['delivery']
            self.assertTrue(delivery['state'])
            self.assertFalse(delivery.get('original_issue_closed', False))
            for url in delivery['prs']:
                self.assertRegex(url, r'^https://github.com/Auda29/nulloy/pull/[1-9][0-9]*$')
                self.assertIn(url, text)

    def test_acceptance_baseline_keeps_artifacts_and_open_gates_separate(self):
        baseline = json.loads((ROOT / 'docs/upstream/acceptance-baseline.json').read_text(encoding='utf-8'))
        self.assertTrue(baseline['native_acceptance_deferred_by_user'])
        self.assertEqual(baseline['prs']['20']['state'], 'MERGED')
        self.assertEqual(baseline['prs']['25']['state'], 'MERGED')
        self.assertEqual(self.data['delivery_snapshot']['swarm_merged'], 16)
        self.assertEqual(self.data['delivery_snapshot']['swarm_open'], 3)
        for n in ['15', '16', '24']:
            self.assertEqual(baseline['prs'][n]['state'], 'OPEN')
            self.assertTrue(baseline['prs'][n]['isDraft'])
        # Fixed identities copied from the immutable source report, NOT hashes
        # independently calculated from Windows ZIP/EXE bytes. Unknown stays null.
        self.assertEqual(baseline['source_report'],
                         'https://github.com/Auda29/nulloy/blob/'
                         '81160a130ae0641fc8d9f220ec52fdec8fb9b863/'
                         'docs/upstream/WINDOWS_ACCEPTANCE.md')
        self.assertEqual(
            {name: (artifact['commit'], artifact['sha256'])
             for name, artifact in baseline['artifacts'].items()},
            {
                'corrected_zip': (
                    '078c734cf8e31fd561a857fa492c530bd4bb6f76',
                    'e9ce76194d4c8a87b429da7adff0b8f6d5468f99349691dc1f4e46f11f1f7b5a'),
                'earlier_interactive_exe': (
                    None,
                    '855d74e505c670194a2e85ee34a93d9358949da55ade4b8d4308610e45a152b5'),
                'obsolete_package': (
                    'f604c64ded4d9b44a39913b00f9a38317f7683cd', None),
            })
        for artifact in baseline['artifacts'].values():
            if artifact.get('commit'):
                self.assertRegex(artifact['commit'], r'^[0-9a-f]{40}$')
            if artifact.get('sha256'):
                self.assertRegex(artifact['sha256'], r'^[0-9a-f]{64}$')
                self.assertFalse(artifact['hash_verified_here'])
        checks = {check['id']: check for check in baseline['checks']}
        self.assertEqual(len(checks), len(baseline['checks']))
        self.assertEqual(
            {name: check['artifact'] for name, check in checks.items()},
            {
                'qt6-package': 'corrected_zip',
                'qt5-native-trash': None,
                'formats': 'obsolete_package',
                'interactive-slim': 'earlier_interactive_exe',
                'final-trash-matrix': 'corrected_zip',
                'explorer': 'corrected_zip',
                'display': 'corrected_zip',
                'final-formats': 'corrected_zip',
                'macos-original': None,
                'explorer-cleanup': None,
            })
        self.assertEqual(checks['formats']['status'], 'reported_older_only')
        for name in ['final-trash-matrix', 'explorer', 'display', 'final-formats', 'macos-original', 'explorer-cleanup']:
            self.assertEqual(checks[name]['status'], 'open')
        for check in checks.values():
            if check['artifact'] is not None:
                self.assertIn(check['artifact'], baseline['artifacts'])
        by_number = {row['number']: row for row in self.rows}
        for n, pr in [(146, '25'), (255, '15'), (236, '16'), (211, '24')]:
            self.assertEqual(by_number[n]['delivery']['head_sha'], baseline['prs'][pr]['headRefOid'])
            self.assertEqual(by_number[n]['delivery']['pr_state'], baseline['prs'][pr]['state'])

    def test_historical_harness_limitations_are_not_current_acceptance_gaps(self):
        by_number = {row['number']: row for row in self.rows}
        for n in [255, 236, 211]:
            with self.subTest(issue=n):
                delivery = by_number[n]['delivery']
                prior = delivery['prior_test_evidence']
                self.assertIn('limitations', prior)
                self.assertTrue(prior['limitations'])
                self.assertTrue(prior['tests'])
                self.assertTrue(prior['test_commands'])
                self.assertTrue(delivery['limitations'])
                historical_publication = [text for text in prior['limitations']
                                          if 'no push' in text]
                self.assertEqual(len(historical_publication), 1)
                self.assertNotIn(historical_publication[0], delivery['limitations'])
                self.assertNotIn('Qt5 not installed', ' '.join(delivery['limitations']))
                self.assertNotIn('Qt5 runtime', ' '.join(delivery['limitations']))

    def test_isolated_player_followup_does_not_close_final_gates(self):
        followup = self.data.get('package_inspection_followup', {})
        self.assertEqual(followup.get('build_run'), 34572047079)
        self.assertEqual(followup.get('build_commit'), '9e1b3f060e649a64c698b2a5981dbfca1d741b84')
        self.assertEqual(followup.get('qt6_zip_sha256'), '5558a6ed786051224f7dcf3228a230fa45c95959f3e363e5b06b48d446ccb833')
        self.assertEqual(followup.get('qt6_exe_sha256'), 'd7d622c3a0afe88657fa108bebf72f7bfdc69777c9f1f626fe3fe26e589315f9')
        self.assertEqual(followup.get('read_only_run'), 34574196605)
        self.assertEqual(followup.get('selection_run'), 34575720227)
        self.assertEqual(followup.get('selection_inspector_commit'), 'c838b013431ec31d972baa5e128f721fb3e89b9f')
        self.assertEqual(followup.get('selection_status'), 'two_rows_verified_before_context_request')
        self.assertEqual(followup.get('context_menu_status'), 'timeout')
        self.assertEqual(followup.get('postaction_file_integrity'), 'not_verified_on_timeout')
        self.assertEqual(followup.get('final_combined_acceptance'), False)
        self.assertEqual(followup.get('native_trash_matrix'), 'open')
        self.assertEqual(followup.get('macos_original'), 'open')
        self.assertNotEqual(followup['build_commit'], followup['selection_inspector_commit'])

    def test_archived_snapshot_matches_audit_and_register(self):
        archive = ROOT / 'docs/upstream/handoff-evidence'
        raw = (archive / 'audit/snapshot.jsonl').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.data['snapshot_sha256'])
        records = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
        by_number = {r['number']: r for r in self.rows}
        self.assertEqual(len(records), len(by_number))
        self.assertEqual({r['issue']['number'] for r in records}, set(by_number))
        for record in records:
            row = by_number[record['issue']['number']]
            self.assertEqual(record['issue']['comments'], row['api_asserted_comments'])
            self.assertEqual(sorted(c['id'] for c in record['comments']),
                             sorted(row['comment_ids_read']))
        manifest = json.loads((archive / 'manifest.json').read_text(encoding='utf-8'))
        names = [entry['path'] for entry in manifest['files']]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(names)
        for entry in manifest['files']:
            path = (archive / entry['path']).resolve()
            self.assertTrue(path.is_relative_to(archive.resolve()))
            data = path.read_bytes()
            self.assertEqual(len(data), entry['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])

if __name__ == '__main__':
    unittest.main()
