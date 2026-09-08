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
