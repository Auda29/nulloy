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

    def _assert_context_menu_milestone_contract(self, milestone):
        self.assertEqual(milestone['status'], 'verified_green_isolated_observation')
        self.assertEqual(milestone['run'], 34584964888)
        self.assertEqual(milestone['inspector_commit'],
                         '5cf2973242321053cd4c793e6518138828baead1')
        self.assertEqual(milestone['package_build_run'], 34572047079)
        self.assertEqual(milestone['package_build_commit'],
                         '9e1b3f060e649a64c698b2a5981dbfca1d741b84')
        self.assertEqual(milestone['qt6_zip_sha256'],
                         '5558a6ed786051224f7dcf3228a230fa45c95959f3e363e5b06b48d446ccb833')
        self.assertEqual(milestone['qt6_exe_sha256'],
                         'd7d622c3a0afe88657fa108bebf72f7bfdc69777c9f1f626fe3fe26e589315f9')
        self.assertEqual(milestone['runtime_script_sha256'],
                         '36e527b210a783a45a66e29f0df74f4b3b76fabd2f81e1d2bddce16934e997ca')
        self.assertEqual(milestone['contracts_passed'], 53)
        self.assertEqual(milestone['selection']['rows_selected'], 2)
        self.assertEqual(milestone['selection']['rows_total'], 3)
        self.assertTrue(milestone['selection']['retained_after_guarded_right_click'])
        self.assertEqual(milestone['selection']['input_count'], 2)
        self.assertEqual(
            milestone['context_menu']['items'],
            [
                {
                    'label': 'Remove From Playlist',
                    'automation_id': 'QtSingleApplication.QMenu.RemoveFromPlaylistAction',
                },
                {
                    'label': 'Move To Trash',
                    'automation_id': 'QtSingleApplication.QMenu.MoveToTrashAction',
                },
            ])
        self.assertEqual(milestone['context_menu']['owner_pid'], 1788)
        self.assertEqual(milestone['context_menu']['runtime_id'], [42, 197778])
        self.assertEqual(milestone['context_menu']['recognized_items'], [
            {
                'label': 'Remove From Playlist',
                'automation_id': 'QtSingleApplication.QMenu.RemoveFromPlaylistAction',
                'pid': 1788,
                'runtime_id': [42, 197778, 4, -2147483613],
            },
            {
                'label': 'Move To Trash',
                'automation_id': 'QtSingleApplication.QMenu.MoveToTrashAction',
                'pid': 1788,
                'runtime_id': [42, 197778, 4, -2147483612],
            },
        ])
        self.assertTrue(milestone['context_menu']['no_menu_invocation'])
        self.assertTrue(milestone['preservation']['filesystem_unchanged_final'])
        self.assertTrue(milestone['preservation']['process_cleanup_verified'])
        self.assertTrue(milestone['preservation']['temp_root_removed'])
        self.assertEqual(milestone['preservation']['errors'], [])
        self.assertFalse(milestone['final_combined_acceptance'])
        self.assertEqual(milestone['open_gates']['pr15_native_trash_matrix'], 'open')
        self.assertEqual(milestone['open_gates']['pr24_explorer'], 'open')
        self.assertEqual(milestone['open_gates']['pr16_dpi_window'], 'open')
        self.assertEqual(milestone['open_gates']['macos_original'], 'open')
        self.assertEqual(milestone['open_gates']['release'], 'not_authorized')

    def test_context_menu_milestone_is_exact_and_keeps_final_gates_open(self):
        milestone = self.data['package_context_menu_milestone']
        self._assert_context_menu_milestone_contract(milestone)
        self.assertEqual(milestone['historical_failures'], [
            {'run': 34582957766, 'inspector_commit': 'ea10d51c2131af941c6e7d8eaaf082a6cca260cd',
             'status': 'FAIL', 'reason': 'Pane/QMenu representation was discovered but recognition failed'},
            {'run': 34584359190, 'inspector_commit': '679bb8915136d5f6db707f259a6950bb49b73d2c',
             'status': 'FAIL', 'reason': 'native observation passed but stdout serialization failed'},
        ])

    def test_context_menu_milestone_negative_controls_are_sensitive(self):
        import copy
        milestone = self.data['package_context_menu_milestone']
        mutations = [
            ('run', lambda value: value.__setitem__('run', 1)),
            ('inspector_commit', lambda value: value.__setitem__('inspector_commit', '0' * 40)),
            ('menu_action', lambda value: value['context_menu'].__setitem__('no_menu_invocation', False)),
            ('final_acceptance', lambda value: value.__setitem__('final_combined_acceptance', True)),
            ('gate', lambda value: value['open_gates'].__setitem__('pr15_native_trash_matrix', 'closed')),
        ]
        for name, mutate in mutations:
            with self.subTest(mutation=name):
                mutated = copy.deepcopy(milestone)
                mutate(mutated)
                with self.assertRaises(AssertionError):
                    self._assert_context_menu_milestone_contract(mutated)

    def test_reviewed_windows_timeout_contract_milestone_is_exact_and_bounded(self):
        milestone = self.data['native_windows_timeout_contract_milestone']
        self.assertEqual(milestone['status'], 'verified_windows_supervisor_qt_fixture_contracts')
        self.assertEqual(milestone['run'], 34595596113)
        self.assertEqual(milestone['workflow_head_sha'],
                         'ca49815db8db16b8704cc82f89336e09f8ed2d70')
        self.assertEqual(milestone['branch'], 'test/windows-uia-timeout-native')
        self.assertEqual(milestone['reviewed_commits'], {
            'supervisor': '68cdc90f369d6c5f507c81cf757befb509dbfeb9',
            'qt_fixture': 'b7d228e885841cb796ed9d31fa79526864dba031',
            'assembled_native': 'ca49815db8db16b8704cc82f89336e09f8ed2d70',
        })
        self.assertEqual(milestone['platform'], {
            'runner': 'Windows-2022',
            'reported_os': 'Windows-10-10.0.20348-SP0',
            'python': '3.11.9',
            'pyside': '6.8.2',
            'qt': '6.8.2',
            'psutil': '7.0.0',
        })
        self.assertEqual(milestone['supervisor'], {
            'tests_run': 18,
            'passed': 16,
            'posix_only_skipped': 2,
            'unexpected_skipped': 0,
        })
        self.assertEqual(milestone['qt_fixture'], {
            'tests_run': 4,
            'passed': 4,
            'skipped': 0,
        })
        self.assertEqual(milestone['script_sha256'], {
            'tools\\uia-timeout-spike\\supervisor.py':
                '6f62c97553a6e513a597bf6a53680a36c9dec9852a8cccb5ab1100744a6737d3',
            'tools\\uia-timeout-spike\\test_spike.py':
                '09c51e8abd8d0e9e9e7c48d7f4bd84fd18c84adf1c292ffda2066a6b20ce3360',
            'tools\\uia-timeout-spike\\worker.py':
                '0b70bfc373904dee5bf96d86da1e6aeb8f55d1f62980c75b2657bdb6ec83d3c0',
            'tools\\uia-timeout-fixture\\fixture.py':
                '50109c32c39bd7863e0273e197e1170299b0f8bdb720251a1b462e251d187da0',
            'tools\\uia-timeout-fixture\\test_fixture.py':
                'f4c6a39fb04771b2d35112c9562c08ea997cfc1e51f8c9523351676761905090',
        })
        self.assertTrue(milestone['hashes_verified'])
        self.assertFalse(milestone['native_uia_query_executed'])
        self.assertFalse(milestone['player_started'])
        self.assertTrue(milestone['hwnd_zero_guard_rejected_before_query'])
        self.assertTrue(milestone['synthetic_pid_is_not_native_query'])
        self.assertFalse(milestone['player_package_present'])
        self.assertFalse(milestone['final_combined_acceptance'])
        self.assertEqual(milestone['open_gates']['com_query'], 'not_executed')
        self.assertEqual(milestone['open_gates']['release'], 'not_authorized')

    def test_player_observation_sixty_contract_milestone_is_exact_and_keeps_prior_53(self):
        milestone = self.data['player_observation_hardening_milestone']
        self.assertEqual(milestone['status'], 'verified_green_isolated_observation')
        self.assertEqual(milestone['run'], 34589940677)
        self.assertEqual(milestone['inspector_commit'],
                         '4ab11fa4eb11ebd6844fc8290b8d362085da1b6d')
        self.assertEqual(milestone['contracts_passed'], 60)
        self.assertEqual(milestone['reports'], 2)
        self.assertEqual(milestone['package_build_run'], 34572047079)
        self.assertEqual(milestone['package_build_commit'],
                         '9e1b3f060e649a64c698b2a5981dbfca1d741b84')
        self.assertEqual(milestone['qt6_zip_sha256'],
                         '5558a6ed786051224f7dcf3228a230fa45c95959f3e363e5b06b48d446ccb833')
        self.assertEqual(milestone['qt6_exe_sha256'],
                         'd7d622c3a0afe88657fa108bebf72f7bfdc69777c9f1f626fe3fe26e589315f9')
        self.assertEqual(milestone['runtime_script_sha256'],
                         'fdab3f890ee1c56af0f57868310779b57bd4f6640970e10298c78741aab0ee05')
        self.assertTrue(milestone['stdout_matches_artifacts'])
        self.assertTrue(milestone['provenance_verified'])
        self.assertTrue(milestone['no_menu_invocation'])
        self.assertTrue(milestone['final_fixture_preservation'])
        self.assertTrue(milestone['cleanup_verified'])
        self.assertEqual(milestone['selection'], {
            'rows_selected': 2,
            'rows_total': 3,
            'retained_after_guarded_right_click': True,
            'input_count': 2,
        })
        self.assertEqual(milestone['prior_53_contract_milestone'], {
            'run': 34584964888,
            'inspector_commit': '5cf2973242321053cd4c793e6518138828baead1',
            'contracts_passed': 53,
        })
        self.assertFalse(milestone['final_combined_acceptance'])
        self.assertEqual(milestone['open_gates']['pr15_native_trash_matrix'], 'open')
        self.assertEqual(milestone['open_gates']['pr24_explorer'], 'open')
        self.assertEqual(milestone['open_gates']['pr16_dpi_window'], 'open')
        self.assertEqual(milestone['open_gates']['macos_original'], 'open')
        self.assertEqual(milestone['open_gates']['release'], 'not_authorized')

    def test_pr30_ci_snapshot_is_not_new_package_acceptance(self):
        snapshot = self.data['pr30_timeout_contracts_followup']
        self.assertEqual(snapshot['source_fetched_at'], '2026-09-11T11:50:53.817380+00:00')
        self.assertEqual(snapshot['pr30'], {
            'state': 'OPEN',
            'isDraft': True,
            'headRefOid': 'c2405a0375b23dfdc3561a5bdd7a1eb56a812902',
        })
        self.assertEqual(snapshot['runs'], {
            'windows_qt5_qt6': {
                'id': 34588893748,
                'conclusion': 'success',
                'headSha': 'c2405a0375b23dfdc3561a5bdd7a1eb56a812902',
            },
            'linux': {
                'id': 34588893721,
                'conclusion': 'success',
                'headSha': 'c2405a0375b23dfdc3561a5bdd7a1eb56a812902',
            },
        })
        self.assertEqual(snapshot['refs'], {
            'integration_upstream_issues': '919468efc32f4d038c96d7276a799794dab2e86e',
            'master': '027d81a583b07457a4fa5f18b3e7dcca50b05b58',
        })
        self.assertTrue(snapshot['windows_matrix_serialization_unchanged'])
        self.assertFalse(snapshot['new_pr30_package_hash_acceptance'])
        self.assertFalse(snapshot['final_combined_acceptance'])
        self.assertEqual(snapshot['open_gates']['release'], 'not_authorized')

    def test_new_milestone_negative_controls_reject_uia_player_and_release_claims(self):
        import shutil
        import subprocess
        import sys
        import tempfile

        timeout_test = 'test_reviewed_windows_timeout_contract_milestone_is_exact_and_bounded'
        observation_test = 'test_player_observation_sixty_contract_milestone_is_exact_and_keeps_prior_53'
        ci_test = 'test_pr30_ci_snapshot_is_not_new_package_acceptance'
        mutations = [
            ('native_windows_timeout_contract_milestone', 'native_uia_query_executed', True, timeout_test),
            ('native_windows_timeout_contract_milestone', 'player_package_present', True, timeout_test),
            ('player_observation_hardening_milestone', 'no_menu_invocation', False, observation_test),
            ('player_observation_hardening_milestone', 'final_combined_acceptance', True, observation_test),
            ('pr30_timeout_contracts_followup', 'new_pr30_package_hash_acceptance', True, ci_test),
        ]
        # Copy only inputs needed by these real contracts, never a live worktree.
        # Explicit test names prevent recursive invocation of this mutation test.
        with tempfile.TemporaryDirectory(prefix='nulloy-register-mutations-') as directory:
            root = Path(directory)
            script = root / 'tools/upstream/test-issue-register.py'
            register = root / 'docs/upstream/issue-register.json'
            script.parent.mkdir(parents=True)
            register.parent.mkdir(parents=True)
            shutil.copyfile(Path(__file__), script)
            original = (ROOT / 'docs/upstream/issue-register.json').read_text(encoding='utf-8')
            register.write_text(original, encoding='utf-8')
            command = [sys.executable, '-B', str(script)]
            baseline = subprocess.run(
                command + ['IssueRegister.' + name for name in (timeout_test, observation_test, ci_test)],
                cwd=root, capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
            self.assertIn('Ran 3 tests', baseline.stderr)
            for key, field, bad, test_name in mutations:
                with self.subTest(key=key, field=field):
                    mutated = json.loads(original)
                    mutated[key][field] = bad
                    register.write_text(json.dumps(mutated), encoding='utf-8')
                    result = subprocess.run(
                        command + ['IssueRegister.' + test_name], cwd=root,
                        capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('Ran 1 test', result.stderr)
                    self.assertIn('FAILED (failures=1)', result.stderr)

    def test_storage_cleanup_followup_is_bounded_and_protects_evidence(self):
        cleanup = self.data['storage_cleanup_followup']
        self.assertTrue(cleanup['approved'])
        self.assertEqual(cleanup['deleted_artifacts'], 29)
        self.assertEqual(cleanup['deleted_artifact_bytes'], 1674672514)
        self.assertEqual(cleanup['deleted_caches'], 31)
        self.assertEqual(cleanup['deleted_cache_bytes'], 10632210125)
        self.assertEqual(cleanup['remaining_artifacts_at_verification'], 309)
        self.assertEqual(cleanup['protected_artifact_ids'], [10188441880, 10188259265])
        self.assertTrue(cleanup['verification_passed'])
        self.assertIn('point-in-time', cleanup['count_scope_note'])

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
