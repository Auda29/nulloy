"""Regression checks for the independent safety review; never native acceptance."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('supervisor_regression_target', HERE / 'uia_supervisor.py')
supervisor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = supervisor
spec.loader.exec_module(supervisor)


class SupervisorRegressionTests(unittest.TestCase):
    def test_readiness_timeout_reaps_real_worker_without_ready_event(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            worker = root/'not_ready.py'
            worker.write_text('import time\ntime.sleep(30)\n')
            result = supervisor.run_supervised(output_dir=root/'run',worker_script=worker,
                readiness_timeout=.2,execution_timeout=3,terminate_timeout=1,kill_timeout=1)
            self.assertEqual(result.status, 'TIMEOUT')
            self.assertEqual(result.timeout_phase, 'readiness')
            self.assertTrue(result.cleanup_verified)
            self.assertIsNotNone(result.returncode)

    def test_live_output_cap_reaps_real_worker_for_either_stream(self):
        for stream in ('stdout', 'stderr'):
            with self.subTest(stream=stream), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                worker = root/'verbose.py'
                worker.write_text("import sys,time\nprint('{\"event\":\"ready\"}',flush=True)\n"
                    + f"print('x'*4096,file=sys.{stream},flush=True)\ntime.sleep(30)\n")
                result = supervisor.run_supervised(output_dir=root/'run',worker_script=worker,
                    readiness_timeout=3,execution_timeout=3,terminate_timeout=1,kill_timeout=1,output_cap=1024)
                self.assertEqual(result.status, 'FAIL')
                self.assertEqual(result.failure_kind, 'output_cap')
                self.assertTrue(result.cleanup_verified)
                self.assertLessEqual(len(result.stdout), 1024)
                self.assertLessEqual(len(result.stderr), 1024)

    def test_finite_kill_fallback_with_real_child_and_portable_terminate_noop(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            worker = root/'sleeper.py'
            worker.write_text("import time\nprint('{\"event\":\"ready\"}',flush=True)\ntime.sleep(30)\n")
            children = []
            real_popen = subprocess.Popen
            def popen(*args, **kwargs):
                child = real_popen(*args, **kwargs)
                children.append(child)
                child.terminate = lambda: None  # Windows also reaches the real kill/wait boundary.
                return child
            try:
                with mock.patch.object(supervisor.subprocess, 'Popen', popen):
                    result = supervisor.run_supervised(output_dir=root/'run',worker_script=worker,
                        readiness_timeout=3,execution_timeout=.1,terminate_timeout=.1,kill_timeout=1)
                self.assertEqual(result.status, 'TIMEOUT')
                self.assertEqual(result.timeout_phase, 'execution')
                self.assertTrue(result.terminate_sent)
                self.assertTrue(result.kill_sent)
                self.assertTrue(result.cleanup_verified)
                self.assertIsNotNone(children[0].poll())
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=3)

    def test_cleanup_errors_cannot_certify_success(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            worker = root/'pass_worker.py'
            worker.write_text("print('{\"event\":\"ready\"}',flush=True)\nprint('{\"status\":\"PASS\"}',flush=True)\n")
            real_cleanup = supervisor._cleanup
            def cleanup(*args):
                stopped, terminated, killed, errors = real_cleanup(*args)
                return stopped, terminated, killed, errors + ['injected cleanup verification error']
            with mock.patch.object(supervisor, '_cleanup', cleanup):
                result = supervisor.run_supervised(output_dir=root/'run',worker_script=worker,
                    readiness_timeout=3,execution_timeout=3,terminate_timeout=.2,kill_timeout=.2)
            self.assertEqual(result.status, 'FAIL', result.to_dict())
            self.assertFalse(result.success)
            self.assertFalse(result.cleanup_verified)
            self.assertIn('injected cleanup verification error', result.secondary_errors)

    def test_final_diagnostic_error_cannot_certify_success(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            worker = root/'pass_worker.py'
            worker.write_text("import time\nprint('{\"event\":\"ready\"}',flush=True)\nprint('{\"status\":\"PASS\"}',flush=True)\ntime.sleep(.15)\n")
            real_cleanup, real_read = supervisor._cleanup, supervisor._read
            cleaned = []
            def cleanup(*args):
                value = real_cleanup(*args)
                cleaned.append(True)
                return value
            def read(path, cap):
                if cleaned:
                    raise OSError('injected final diagnostic read failure')
                return real_read(path, cap)
            with mock.patch.object(supervisor, '_cleanup', cleanup), mock.patch.object(supervisor, '_read', read):
                result = supervisor.run_supervised(output_dir=root/'run',worker_script=worker,
                    readiness_timeout=3,execution_timeout=3,terminate_timeout=.2,kill_timeout=.2)
            self.assertEqual(result.status, 'FAIL', result.to_dict())
            self.assertFalse(result.success)
            self.assertTrue(result.cleanup_verified)
            self.assertTrue(any('final diagnostic read' in item for item in result.secondary_errors))

    def test_post_spawn_stream_close_error_still_reaps_owned_worker(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            worker = root / 'sleeper.py'
            worker.write_text('import time\ntime.sleep(30)\n')
            children = []
            original_popen = subprocess.Popen
            original_open = Path.open

            class CloseFailure:
                def __init__(self, stream): self.stream = stream
                def __enter__(self): return self.stream
                def __exit__(self, *args):
                    self.stream.close()
                    raise OSError('injected post-spawn stream close failure')

            def failing_open(p, *args, **kwargs):
                stream = original_open(p, *args, **kwargs)
                if p.name == 'stdout.txt' and args == ('wb',):
                    return CloseFailure(stream)
                return stream

            def record_child(*args, **kwargs):
                child = original_popen(*args, **kwargs)
                children.append(child)
                return child

            try:
                with mock.patch.object(Path, 'open', failing_open), mock.patch.object(supervisor.subprocess, 'Popen', record_child):
                    result = supervisor.run_supervised(output_dir=root/'run', worker_script=worker,
                        readiness_timeout=.5, execution_timeout=.1, terminate_timeout=.2, kill_timeout=.2)
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].poll(), 'supervisor returned with its owned worker still alive')
                self.assertEqual(result.status, 'FAIL')
                self.assertIn('post-spawn', result.primary_error)
                self.assertTrue(result.cleanup_verified)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=3)

    def test_output_capture_reads_at_most_cap_plus_one_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / 'large.log'
            path.write_bytes(b'x' * 65536)
            reads = []
            original_open = Path.open

            class TrackedStream:
                def __init__(self, stream): self.stream = stream
                def __enter__(self): return self
                def __exit__(self, *args): self.stream.close()
                def read(self, size=-1):
                    reads.append(size)
                    return self.stream.read(size)

            def tracking_open(p, *args, **kwargs):
                stream = original_open(p, *args, **kwargs)
                return TrackedStream(stream) if p == path else stream

            with mock.patch.object(Path, 'open', tracking_open):
                data, capped = supervisor._read(path, 1024)
            self.assertEqual(data, b'x' * 1024)
            self.assertTrue(capped)
            self.assertEqual(reads, [1025], 'the I/O operation itself must be bounded')


if __name__ == '__main__':
    unittest.main()
