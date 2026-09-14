"""Real-process contracts for the isolated harmless modal fixture.

Linux tests exercise PySide6 with the fixture's explicit trusted internal seam;
that is not Windows UIA evidence. The existing supervisor is exercised with a
real bounded child, not a mock process.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture.py"
CONTROLLER = HERE / "controller.py"
WORKER = HERE / "worker.py"
SUPERVISOR = HERE.parent / "player-inspection" / "uia_supervisor.py"


PYTHON = sys.executable


def _run_fixture(root: Path, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    child_env["QT_QPA_PLATFORM"] = "offscreen"
    if env:
        child_env.update(env)
    return subprocess.run(
        [PYTHON, str(FIXTURE), "--root", str(root), "--nonce", "test-nonce", *extra],
        cwd=str(HERE), env=child_env, text=True, capture_output=True, timeout=8,
    )


class FixtureGuardTests(unittest.TestCase):
    def test_invalid_nonce_is_rejected_before_root_creation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "owned-root"
            result = subprocess.run(
                [PYTHON, str(FIXTURE), "--root", str(root), "--nonce", "bad nonce", "--lifetime", "1"],
                cwd=str(HERE), env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                text=True, capture_output=True, timeout=4,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(root.exists())
            self.assertIn("nonce", result.stderr)

    def test_invalid_lifetime_is_rejected_before_root_creation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "owned-root"
            result = _run_fixture(root, "--lifetime", "nan")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(root.exists())
            self.assertIn("lifetime", result.stderr)

    def test_existing_root_is_a_safety_guard_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "owned-root"
            root.mkdir()
            result = _run_fixture(root, "--lifetime", "1")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not already exist", result.stderr)

    def test_guarded_fixture_callback_failure_is_nonzero_real_process(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "owned-root"
            result = _run_fixture(
                root, "--lifetime", "2",
                env={"MODAL_CANCEL_FIXTURE_TEST_FAIL_CALLBACK": "1"},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(root.exists())
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phase"], "failed")
            self.assertIn("callback", state["error"])


class RealQtModalTests(unittest.TestCase):
    def test_internal_cancel_runs_real_qt_modal_and_preserves_sentinel(self):
        sys.path.insert(0, str(HERE))
        try:
            import controller
            with tempfile.TemporaryDirectory() as raw:
                report = controller.run_internal_cancel(Path(raw))
        finally:
            sys.path.pop(0)
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["native_acceptance"])
        self.assertEqual(report["fixture"]["cancel_count"], 1)
        self.assertEqual(report["fixture"]["yes_count"], 0)
        self.assertTrue(report["fixture"]["dialog_closed"])
        self.assertEqual(report["fixture"]["phase"], "cancelled")
        self.assertIsNone(report["fixture"]["returncode"])
        self.assertTrue(report["sentinel"]["unchanged"])
        self.assertTrue(report["cleanup_verified"])
        self.assertEqual(report["direct_cancel_invoke_count"], 0)

    def test_internal_cancel_has_independent_counter_and_sentinel_records(self):
        sys.path.insert(0, str(HERE))
        try:
            import controller
            with tempfile.TemporaryDirectory() as raw:
                report = controller.run_internal_cancel(Path(raw))
                root = Path(report["fixture"]["root"])
                counters = json.loads((root / "counters.json").read_text(encoding="utf-8"))
                self.assertEqual(counters["cancel"], 1)
                self.assertEqual(counters["yes"], 0)
                self.assertEqual(report["sentinel"]["after_sha256"], hashlib.sha256((root / "sentinel.bin").read_bytes()).hexdigest())
        finally:
            sys.path.pop(0)


class WorkerAndSupervisorTests(unittest.TestCase):
    def test_worker_reports_blocked_without_guessing_unpinned_modal_control_type(self):
        if os.name == "nt":
            self.skipTest("Linux-only blocked-path contract")
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            result = subprocess.run(
                [PYTHON, str(WORKER), "--pid", "1", "--create-time", "1", "--exe", "/nope",
                 "--hwnd", "1", "--nonce", "test-nonce", "--root", str(output),
                 "--output-dir", str(output)],
                cwd=str(HERE), text=True, capture_output=True, timeout=4,
            )
            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(payload["status"], "BLOCKED")
            self.assertIn("control type", payload["reason"])
            self.assertFalse(payload["direct_cancel_invoke"])

    def test_existing_supervisor_bounds_and_reaps_real_sleeping_worker(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            worker = directory / "sleeping_worker.py"
            worker.write_text(
                "import json, time\n"
                "print(json.dumps({'event': 'ready'}), flush=True)\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            import importlib.util
            spec = importlib.util.spec_from_file_location("modal_cancel_test_supervisor", SUPERVISOR)
            supervisor = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            sys.modules["modal_cancel_test_supervisor"] = supervisor
            spec.loader.exec_module(supervisor)
            started = time.monotonic()
            result = supervisor.run_supervised(
                output_dir=directory / "supervised",
                worker_script=worker,
                readiness_timeout=0.4,
                execution_timeout=0.15,
                terminate_timeout=0.2,
                kill_timeout=0.2,
            )
            elapsed = time.monotonic() - started
            self.assertEqual(result.status, "TIMEOUT")
            self.assertEqual(result.failure_kind, "timeout")
            self.assertTrue(result.cleanup_verified)
            self.assertLess(elapsed, 3.0)

    def test_controller_cli_is_blocked_on_linux(self):
        if os.name == "nt":
            self.skipTest("Linux-only blocked-path contract")
        sys.path.insert(0, str(HERE))
        try:
            import controller
            with tempfile.TemporaryDirectory() as raw:
                with mock.patch.object(controller.os, "name", "posix"):
                    code = controller.main(["--evidence-root", raw])
                self.assertEqual(code, 2)
                reports = list(Path(raw).glob("*/final-report.json"))
                self.assertEqual(len(reports), 1)
                report = json.loads(reports[0].read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["native_acceptance"])
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
