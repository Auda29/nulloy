"""Tests for the standalone UIA supervisor spike.

These tests deliberately use real child Python processes. The injected workers
are Linux test fixtures, not evidence of a native COM/UIA hang.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent


class WorkerIdentityTests(unittest.TestCase):
    def test_native_hwnd_owner_is_revalidated_after_uia_traversal(self):
        import worker

        class Info:
            name = "owned"
            control_type = "Window"
            automation_id = "root"
            class_name = "FakeWindow"
            process_id = 1234

        class Root:
            element_info = Info()

            def descendants(self):
                return []

        class DesktopFactory:
            def __init__(self, **kwargs):
                pass

            def window(self, **kwargs):
                return self

            def wrapper_object(self):
                return Root()

        class Process:
            pid = 1234

            def create_time(self):
                return 10.5

            def exe(self):
                return "/owned.exe"

        psutil_module = types.ModuleType("psutil")
        psutil_module.Process = lambda pid: Process()
        pywinauto_module = types.ModuleType("pywinauto")
        pywinauto_module.Desktop = DesktopFactory
        native_pids = iter((1234, 4321))

        with mock.patch.object(worker.os, "name", "nt"):
            with mock.patch.object(worker, "_native_window_pid", side_effect=lambda hwnd: next(native_pids)):
                with mock.patch.dict(sys.modules, {"psutil": psutil_module, "pywinauto": pywinauto_module}):
                    with self.assertRaisesRegex(RuntimeError, "HWND owner changed"):
                        worker.inspect_target("0x10", "1234", "10.5", "/owned.exe")


class SupervisorSubprocessTests(unittest.TestCase):
    def _write_worker(self, directory: Path, body: str) -> Path:
        path = directory / "injected_worker.py"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return path

    def _run(self, worker: Path, output: Path, **kwargs):
        from supervisor import run_supervised

        return run_supervised(
            worker_script=worker,
            output_dir=output,
            readiness_timeout=kwargs.pop("readiness_timeout", 0.5),
            execution_timeout=kwargs.pop("execution_timeout", 0.5),
            terminate_timeout=kwargs.pop("terminate_timeout", 0.2),
            kill_timeout=kwargs.pop("kill_timeout", 0.2),
            output_cap=kwargs.pop("output_cap", 4096),
            worker_args=kwargs.pop("worker_args", ()),
        )

    def test_postspawn_diagnostic_read_failure_is_recorded_and_child_is_cleaned(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import json, time
                print(json.dumps({'event': 'ready'}), flush=True)
                time.sleep(3)
                """,
            )
            output = directory / "run"
            import supervisor

            captured = {}
            real_popen = supervisor.subprocess.Popen

            def capture_popen(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                captured["process"] = process
                return process

            def fail_once(path, cap):
                raise OSError("injected diagnostic read failure")

            with mock.patch.object(supervisor.subprocess, "Popen", side_effect=capture_popen):
                with mock.patch.object(supervisor, "_read_bytes_capped", side_effect=fail_once):
                    result = self._run(worker, output)

            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.failure_kind, "diagnostic_read")
            self.assertTrue(result.cleanup_verified)
            self.assertIn("injected diagnostic read failure", result.primary_error)
            self.assertTrue((output / "result.json").is_file())
            self.assertIsNotNone(captured["process"].poll())

    def test_unexpected_wait_failure_still_reaches_kill_fallback(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import signal, time
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                print('{\"event\": \"ready\"}', flush=True)
                time.sleep(3)
                """,
            )
            output = directory / "run"
            import supervisor

            real_wait = supervisor._wait_for_exit
            calls = {"count": 0}

            def fail_once(process, timeout):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise OSError("injected wait failure")
                return real_wait(process, timeout)

            with mock.patch.object(supervisor, "_wait_for_exit", side_effect=fail_once):
                result = self._run(worker, output, execution_timeout=0.08)

            self.assertEqual(result.status, "TIMEOUT")
            self.assertTrue(result.cleanup_verified)
            self.assertTrue(result.kill_sent)
            self.assertIn("injected wait failure", result.secondary_errors[0])

    def test_failed_result_write_returns_structured_failure_without_masking_child_error(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import json, sys
                print(json.dumps({'event': 'ready'}), flush=True)
                print('primary child failure', file=sys.stderr, flush=True)
                raise RuntimeError('primary child failure')
                """,
            )
            output = directory / "run"
            import supervisor

            with mock.patch.object(
                supervisor, "_write_result", side_effect=OSError("injected result write failure")
            ):
                result = self._run(worker, output)

            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.failure_kind, "child_exit")
            self.assertIn("primary child failure", result.stderr)
            self.assertTrue(any("injected result write failure" in error for error in result.secondary_errors))
            self.assertIn("injected result write failure", result.result_write_error)
            self.assertTrue(result.cleanup_verified)

        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import json, sys
                print(json.dumps({'event': 'ready'}), flush=True)
                print(json.dumps({'status': 'PASS', 'snapshot': {'count': 1}}), flush=True)
                """,
            )
            output = directory / "run"
            result = self._run(worker, output)

            self.assertEqual(result.status, "SUCCESS")
            self.assertTrue(result.cleanup_verified)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.child_payload["status"], "PASS")
            self.assertIn('"event": "ready"', result.stdout)
            self.assertEqual(result.stderr, "")
            self.assertTrue((output / "stdout.txt").is_file())
            self.assertTrue((output / "stderr.txt").is_file())
            self.assertTrue((output / "result.json").is_file())
            saved = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "SUCCESS")

    def test_child_exception_is_fail_and_stderr_is_captured(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import json, sys
                print(json.dumps({'event': 'ready'}), flush=True)
                print('fixture exception', file=sys.stderr, flush=True)
                raise RuntimeError('injected child failure')
                """,
            )
            result = self._run(worker, directory / "run")

            self.assertEqual(result.status, "FAIL")
            self.assertFalse(result.success)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("fixture exception", result.stderr)
            self.assertIn("injected child failure", result.stderr)

    def test_stall_before_ready_is_readiness_timeout(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import time
                time.sleep(3)
                """,
            )
            result = self._run(worker, directory / "run", readiness_timeout=0.08)

            self.assertEqual(result.status, "TIMEOUT")
            self.assertEqual(result.timeout_phase, "readiness")
            self.assertTrue(result.cleanup_verified)
            self.assertEqual(result.returncode, -15 if os.name != "nt" else 1)

    def test_ready_then_stall_is_execution_timeout_and_cleanup_is_verified(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import json, time
                print(json.dumps({'event': 'ready'}), flush=True)
                time.sleep(3)
                """,
            )
            result = self._run(worker, directory / "run", execution_timeout=0.08)

            self.assertEqual(result.status, "TIMEOUT")
            self.assertEqual(result.timeout_phase, "execution")
            self.assertTrue(result.cleanup_verified)
            self.assertTrue(result.terminate_sent or result.kill_sent)

    def test_live_stderr_output_cap_fails_before_execution_deadline(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import json, sys, time
                print(json.dumps({'event': 'ready'}), flush=True)
                sys.stderr.write('e' * 5000)
                sys.stderr.flush()
                time.sleep(3)
                """,
            )
            output = directory / "run"
            result = self._run(worker, output, output_cap=128, execution_timeout=0.8)

            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.failure_kind, "output_cap")
            self.assertFalse(result.timed_out)
            self.assertTrue(result.cleanup_verified)
            self.assertLess(result.supervision_elapsed_s, 0.6)
            self.assertLessEqual(len(result.stderr.encode("utf-8")), 128)

    def test_timeout_remains_primary_when_final_stderr_capture_exceeds_cap(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import json, signal, sys, time
                def on_term(signum, frame):
                    sys.stderr.write('late stderr' * 1000)
                    sys.stderr.flush()
                signal.signal(signal.SIGTERM, on_term)
                print(json.dumps({'event': 'ready'}), flush=True)
                time.sleep(3)
                """,
            )
            output = directory / "run"
            result = self._run(worker, output, output_cap=128, execution_timeout=0.05)

            self.assertEqual(result.status, "TIMEOUT")
            self.assertEqual(result.failure_kind, "timeout")
            self.assertEqual(result.timeout_phase, "execution")
            self.assertTrue(result.timed_out)
            self.assertTrue(any("after timeout primary" in error for error in result.secondary_errors))
            self.assertTrue(result.cleanup_verified)

        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = self._write_worker(
                directory,
                """
                import json, sys
                print(json.dumps({'event': 'ready'}), flush=True)
                sys.stdout.write('x' * 5000)
                sys.stdout.flush()
                """,
            )
            result = self._run(worker, directory / "run", output_cap=128)

            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.failure_kind, "output_cap")
            self.assertFalse(result.timed_out)

    def test_deadlines_reject_nonfinite_and_nonpositive_values(self):
        from supervisor import validate_deadline

        for value in (0, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_deadline(value, "deadline")

    def test_cli_uses_owned_worker_and_serializes_linux_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            output = directory / "cli-run"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "supervisor.py"),
                    "--output-dir",
                    str(output),
                    "--hwnd",
                    "0x10",
                    "--pid",
                    "1234",
                    "--create-time",
                    "10.5",
                    "--exe",
                    "/owned.exe",
                    "--readiness-timeout",
                    "0.5",
                    "--execution-timeout",
                    "0.5",
                ],
                cwd=HERE,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1 if os.name != "nt" else 0)
            cli_result = json.loads(completed.stdout)
            if os.name != "nt":
                self.assertEqual(cli_result["status"], "FAIL")
                self.assertEqual(cli_result["failure_kind"], "child_exit")
            self.assertTrue((output / "result.json").is_file())

    def test_cli_rejects_worker_script_replacement_option(self):
        with tempfile.TemporaryDirectory() as raw:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "supervisor.py"),
                    "--worker-script",
                    str(Path(raw) / "injected.py"),
                    "--output-dir",
                    str(Path(raw) / "run"),
                ],
                cwd=HERE,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
