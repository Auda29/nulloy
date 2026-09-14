"""Preserve native provider causes without relaxing any worker verdict."""
import contextlib
import io
import json
import unittest
from unittest import mock
import test_bounded_context as fixtures

worker = fixtures.worker


class WorkerDiagnosticsTests(unittest.TestCase):
    def test_failure_stderr_retains_provider_exception_chain(self):
        def fail(*args, **kwargs):
            try:
                raise OSError('provider rejected focus: diagnostic sentinel')
            except OSError as exc:
                raise worker._OwnershipError('strict selection failed') from exc
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(worker, 'inspect_context_target', side_effect=fail), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = worker.main(['--hwnd', '1001', '--pid', '4242', '--create-time', '12.5', '--exe', 'player.exe', '--expected-rows', json.dumps(fixtures.EXPECTED), '--context-menu'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue().splitlines()[-1])['status'], 'FAIL')
        self.assertIn('provider rejected focus: diagnostic sentinel', stderr.getvalue())
        self.assertIn('strict selection failed', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
