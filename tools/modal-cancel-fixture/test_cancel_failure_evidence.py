"""Keep action failure evidence coherent through the actual worker CLI."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import test_worker_cancel as setup

worker = setup.worker


def run_cli(root, output):
    setup.Desktop.root_result = root
    args = setup._args(output)
    stdout, stderr = io.StringIO(), io.StringIO()
    with mock.patch.object(worker, 'os', SimpleNamespace(name='nt')), \
         mock.patch.object(worker, '_load_dependencies', return_value=(setup.Psutil(), setup.Desktop)), \
         mock.patch.object(worker, '_native_window_pid', return_value=321), \
         mock.patch.object(worker, '_parser', return_value=SimpleNamespace(parse_args=lambda _: args)), \
         contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = worker.main([])
    return code, json.loads(stdout.getvalue().splitlines()[-1]), stderr.getvalue()


class CancelFailureEvidenceTests(unittest.TestCase):
    def test_failed_pre_invoke_audit_does_not_claim_entered_action(self):
        root, _, _, cancel, yes = setup._qt_tree()
        original = worker._atomic_json
        failed = []
        def fail_once(path, value):
            if (not failed and isinstance(value, list) and value
                    and value[-1].get('stage') == 'cancel_invoke_started'):
                failed.append(True)
                raise OSError('pre-invoke audit write sentinel')
            return original(path, value)
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(worker, '_atomic_json', side_effect=fail_once):
            code, report, stderr = run_cli(root, Path(raw))
            saved_stages = json.loads((Path(raw) / 'worker-stages.json').read_text())
        self.assertEqual(code, 1)
        self.assertEqual(saved_stages, report['stages'])
        self.assertEqual(cancel.invoke_count + yes.invoke_count, 0)
        self.assertEqual(report['action']['cancel_attempted'], 0)
        self.assertIn('pre-invoke audit write sentinel', stderr)
        for stage in report['stages']:
            self.assertNotEqual(stage['stage'], 'cancel_invoke_started')
            self.assertEqual(stage.get('action', {}).get('cancel_attempted', 0), 0)
        self.assertIn('cancel_invoke_not_entered', [s['stage'] for s in report['stages']])

    def test_entered_invoke_failure_is_never_labeled_readonly(self):
        def explode():
            raise RuntimeError('actual entered invoke failed')
        root, _, _, cancel, yes = setup._qt_tree(on_invoke=explode)
        with tempfile.TemporaryDirectory() as raw:
            code, report, stderr = run_cli(root, Path(raw))
        self.assertEqual(code, 1)
        self.assertEqual(cancel.invoke_count, 1)
        self.assertEqual(yes.invoke_count, 0)
        self.assertEqual(report['action']['cancel_attempted'], 1)
        self.assertEqual(report['action']['outcome'], 'unknown')
        self.assertIn('actual entered invoke failed', stderr)
        self.assertIs(report['captured_readonly'], False)


if __name__ == '__main__':
    unittest.main()
