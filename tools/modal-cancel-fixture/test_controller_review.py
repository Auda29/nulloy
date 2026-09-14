"""Regression checks for the recovered modal controller's verdict boundary."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from test_controller_observations import native_observations

spec = importlib.util.spec_from_file_location('modal_controller_review', Path(__file__).with_name('controller.py'))
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class ModalControllerReviewTests(unittest.TestCase):
    def _native_case(self, root, *, owner_error=False, cleanup_ok=True, require_live_post=False, supervisor_error=False):
        process = mock.Mock(pid=1234)
        process.poll.return_value = None
        root.mkdir()
        (root / 'sentinel.bin').write_bytes(b'unchanged sentinel')
        nonce = 'modal-testnonce'
        state = {
            'nonce': nonce, 'parent_pid': controller.os.getpid(), 'pid': 1234,
            'create_time': 1.0, 'executable': 'fixture', 'hwnd': 222,
            'qt_version': '6.8.2', 'qt_platform': 'windows',
            'main_title': f'Modal Cancel Fixture Main {nonce}',
            'dialog_title': f'Modal Cancel Fixture {nonce}',
            'dialog_body': f'Benign modal cancellation test {nonce}',
            'heartbeat': 4, 'monotonic': 4.0, 'phase': 'cancelled',
            'dialog_open': False, 'dialog_closed': True,
            'cancel_count': 1, 'yes_count': 0,
        }
        checks = {'state': state, 'counters': {'cancel': 1, 'yes': 0, 'dialog_closed': True, 'nonce': nonce}}
        payload = {
            'status': 'PASS', 'captured_readonly': False, 'native_acceptance': True,
            'modal_absent': True, 'post_identity_verified': True,
            'direct_cancel_invoke': True, 'direct_cancel_invoke_count': 1,
            'yes_invoke_count': 0,
            'action': {'cancel_attempted': 1, 'cancel_completed': 1,
                       'yes_attempted': 0, 'outcome': 'completed'},
            'observations': native_observations(
                nonce=nonce, pid=1234, root_hwnd=222, dialog_hwnd=333,
            ),
        }
        supervisor_report = {
            'status': 'SUCCESS', 'success': True, 'stdout': 'diagnostic sentinel',
            'cleanup_verified': True, 'secondary_errors': [], 'child_payload': payload,
        }
        result = SimpleNamespace(success=True, status='SUCCESS', secondary_errors=[], child_payload=payload,
                                 cleanup_verified=True, to_dict=lambda: supervisor_report)
        cleanup = {'cleanup_verified': cleanup_ok, 'errors': [] if cleanup_ok else ['cleanup sentinel']}
        common_calls = []
        def common(*args, **kwargs):
            common_calls.append(process.poll())
            if require_live_post and process.poll() is not None:
                raise RuntimeError('postcheck after kill')
            return checks
        def reap(*args):
            process.poll.return_value = 0
            return cleanup
        def run_supervised(**kwargs):
            if supervisor_error:
                raise RuntimeError('supervisor primary sentinel')
            return result
        with mock.patch.object(controller, 'os', SimpleNamespace(name='nt', getpid=os.getpid)), mock.patch.object(
            controller, '_nonce', return_value='modal-testnonce'
        ), mock.patch.object(
            controller, '_start_fixture', return_value=(process, root, (1234, 1.0, 'fixture'))
        ), mock.patch.object(controller, '_await_state', return_value=state), mock.patch.object(
            controller, '_common_fixture_checks', side_effect=common
        ), mock.patch.object(controller, '_load_supervisor', return_value=SimpleNamespace(run_supervised=run_supervised)), mock.patch.object(
            controller, '_native_owner_pid', side_effect=[1234, RuntimeError('owner sentinel')] if owner_error else lambda h: 1234
        ), mock.patch.object(controller, '_cleanup', side_effect=reap):
            report = controller.run_native(root.parent / 'output', cancel_once=True)
        return report, supervisor_report, common_calls

    def test_supervisor_exception_still_runs_independent_postcheck(self):
        with tempfile.TemporaryDirectory() as raw:
            report, _, calls = self._native_case(Path(raw) / 'fixture', supervisor_error=True)
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn('supervisor primary sentinel', report['error'])
        self.assertEqual(calls, [None, None])

    def test_native_failure_report_binds_runtime_sources(self):
        import hashlib
        with tempfile.TemporaryDirectory() as raw:
            report, _, _ = self._native_case(Path(raw) / 'fixture', owner_error=True)
        base = Path(controller.__file__).parent
        expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    (base / 'controller.py', base / 'fixture.py', base / 'worker.py', base.parent / 'player-inspection/uia_supervisor.py')}
        self.assertEqual(report.get('source_sha256'), expected)

    def test_postcheck_failure_still_rechecks_sentinel_bytes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as raw:
            report, _, _ = self._native_case(Path(raw) / 'fixture', owner_error=True)
        expected = hashlib.sha256(b'unchanged sentinel').hexdigest()
        self.assertEqual(report['sentinel'], {'before_sha256': expected, 'after_sha256': expected, 'unchanged': True})
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn('owner sentinel', report['error'])

    def test_terminate_error_still_reaps_real_owned_child(self):
        import subprocess
        import sys
        process = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'])
        try:
            with mock.patch.object(process, 'terminate', side_effect=OSError('terminate sentinel')):
                result = controller._cleanup(process, terminate_timeout=0.1, kill_timeout=1)
            self.assertIsNotNone(process.poll(), 'owned child left alive after terminate error')
            self.assertTrue(result['kill_sent'])
            self.assertFalse(result['cleanup_verified'])
            self.assertIn('terminate sentinel', str(result['errors']))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)

    def test_cleanup_failure_revokes_native_acceptance(self):
        with tempfile.TemporaryDirectory() as raw:
            report, _, _ = self._native_case(Path(raw) / 'fixture', cleanup_ok=False)
        self.assertEqual(report['status'], 'FAIL')
        self.assertIs(report['native_acceptance'], False)

    def test_dead_fixture_cannot_substitute_launch_identity(self):
        import os
        process = mock.Mock()
        process.poll.return_value = 0
        state = {'parent_pid': os.getpid(), 'pid': 1234, 'create_time': 1.0,
                 'executable': 'fixture', 'nonce': 'nonce', 'qt_version': '6.8.2', 'qt_platform': 'offscreen'}
        with mock.patch.object(controller, '_read_json', side_effect=[state, {}]):
            with self.assertRaisesRegex(RuntimeError, 'not live'):
                controller._common_fixture_checks(Path('.'), (1234, 1.0, 'fixture'), process, 'nonce')

    def test_live_postcheck_precedes_intentional_fixture_cleanup(self):
        with tempfile.TemporaryDirectory() as raw:
            report, _, calls = self._native_case(Path(raw) / 'fixture', require_live_post=True)
        self.assertEqual(report['status'], 'PASS', report.get('error'))
        self.assertEqual(calls, [None, None])

    def test_postcheck_failure_keeps_supervisor_in_final_report(self):
        import json
        with tempfile.TemporaryDirectory() as raw:
            report, expected, _ = self._native_case(Path(raw) / 'fixture', owner_error=True)
            saved = json.loads((Path(report['run_dir']) / 'final-report.json').read_text())
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn('owner sentinel', report['error'])
        self.assertEqual(report.get('supervisor'), expected)
        self.assertEqual(saved.get('supervisor'), expected)

    def test_native_fixture_never_inherits_internal_cancel_or_offscreen_seams(self):
        import os
        with tempfile.TemporaryDirectory() as raw:
            fake_os = SimpleNamespace(name='nt', environ={**os.environ,
                'MODAL_CANCEL_FIXTURE_TEST_SEAM': 'cancel',
                'MODAL_CANCEL_FIXTURE_TEST_FAIL_CALLBACK': '1',
                'QT_QPA_PLATFORM': 'offscreen'})
            captured = {}
            def spawn(*args, **kwargs):
                captured.update({k: v for k, v in kwargs['env'].items() if k.startswith('MODAL_CANCEL_FIXTURE_TEST_') or k == 'QT_QPA_PLATFORM'})
                raise OSError('stop before spawning')
            with mock.patch.object(controller, 'os', fake_os), mock.patch.object(controller.subprocess, 'Popen', side_effect=spawn):
                with self.assertRaisesRegex(OSError, 'stop before spawning'):
                    controller._start_fixture(Path(raw), 'test-nonce', test_seam=False)
            for key in ('MODAL_CANCEL_FIXTURE_TEST_SEAM', 'MODAL_CANCEL_FIXTURE_TEST_FAIL_CALLBACK', 'QT_QPA_PLATFORM'):
                self.assertNotIn(key, captured)

    def test_spawn_failure_never_claims_native_acceptance(self):
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(controller, 'os', SimpleNamespace(name='nt')), mock.patch.object(
                controller, '_start_fixture', side_effect=OSError('spawn sentinel')
            ):
                result = controller.run_native(Path(raw))
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('spawn sentinel', result['error'])
        self.assertIs(result['native_acceptance'], False)


if __name__ == '__main__':
    unittest.main()
