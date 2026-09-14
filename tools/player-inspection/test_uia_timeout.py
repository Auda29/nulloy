from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = Path(__file__).resolve().parent
SUPERVISOR = HERE / "uia_supervisor.py"


class BoundedUIAQueryTests(unittest.TestCase):
    def _hanging_worker(self, directory: Path) -> Path:
        worker = directory / "hanging_worker.py"
        worker.write_text(
            textwrap.dedent(
                """
                import json
                import time
                print(json.dumps({"event": "ready"}), flush=True)
                print("entered simulated blocking UIA call", file=__import__("sys").stderr, flush=True)
                time.sleep(30)
                """
            ),
            encoding="utf-8",
        )
        return worker

    def test_real_hanging_query_is_contained_and_cleanup_is_verified(self):
        spec = __import__("importlib.util").util.spec_from_file_location("uia_supervisor", SUPERVISOR)
        module = __import__("importlib.util").util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix="player-inspection-timeout-") as raw:
            root = Path(raw)
            worker = self._hanging_worker(root)
            started = __import__("time").monotonic()
            result = module.run_supervised(
                output_dir=root / "run",
                worker_script=worker,
                readiness_timeout=0.5,
                execution_timeout=0.15,
                terminate_timeout=0.2,
                kill_timeout=0.2,
            )
            elapsed = __import__("time").monotonic() - started
            self.assertEqual(result.status, "TIMEOUT")
            self.assertEqual(result.timeout_phase, "execution")
            self.assertTrue(result.timed_out)
            self.assertTrue(result.cleanup_verified)
            self.assertTrue(result.terminate_sent)
            self.assertIsNotNone(result.returncode)
            self.assertLess(elapsed, 3.0)
            self.assertIn("simulated blocking UIA call", result.stderr)
            self.assertTrue(Path(result.stdout_path).is_file())
            self.assertTrue(Path(result.stderr_path).is_file())
            saved = json.loads(Path(result.result_path).read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "TIMEOUT")
            self.assertEqual(saved["failure_kind"], "timeout")

    @unittest.skipUnless(os.name == "posix", "SIGTERM handlers are POSIX-only; portable fallback is tested separately")
    def test_real_hanging_query_uses_finite_kill_fallback_when_terminate_is_ignored(self):
        spec = __import__("importlib.util").util.spec_from_file_location("uia_supervisor_kill", SUPERVISOR)
        module = __import__("importlib.util").util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix="player-inspection-kill-") as raw:
            root = Path(raw)
            worker = root / "term_ignoring_worker.py"
            worker.write_text(
                "import json, signal, time\n"
                "signal.signal(signal.SIGTERM, lambda *_: None)\n"
                "print(json.dumps({'event': 'ready'}), flush=True)\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            result = module.run_supervised(
                output_dir=root / "run",
                worker_script=worker,
                readiness_timeout=0.5,
                execution_timeout=0.1,
                terminate_timeout=0.1,
                kill_timeout=0.2,
            )
            self.assertEqual(result.status, "TIMEOUT")
            self.assertTrue(result.terminate_sent)
            self.assertTrue(result.kill_sent)
            self.assertTrue(result.cleanup_verified)

    def test_active_inspector_cli_serializes_bounded_platform_block(self):
        inspector = HERE / "inspect_player.py"
        with tempfile.TemporaryDirectory(prefix="player-inspection-active-cli-") as raw:
            output_dir = Path(raw) / "evidence"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(inspector),
                    "--package", str(Path(raw) / "missing.zip"),
                    "--output", str(output_dir),
                    "--source-sha", "9e1b3f060e649a64c698b2a5981dbfca1d741b84",
                    "--archive-sha256", "5" * 64,
                    "--bounded-read-only",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(completed.returncode, 1 if os.name == "nt" else 2)
            emitted = json.loads(completed.stdout)
            saved = json.loads((output_dir / "inspection-report.json").read_text(encoding="utf-8"))
            self.assertEqual(emitted, saved)
            if os.name == "nt":
                self.assertEqual(saved["status"], "FAIL")
                self.assertEqual(saved["error_type"], "FileNotFoundError")
            else:
                self.assertEqual(saved["status"], "BLOCKED")
                self.assertIn("native Windows", saved["error"])

    def test_bounded_read_only_mode_is_explicit_and_not_context_mode(self):
        spec = __import__("importlib.util").util.spec_from_file_location(
            "player_inspection", HERE / "inspect_player.py"
        )
        module = __import__("importlib.util").util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        base = [
            "--package", "package.zip",
            "--output", "evidence",
            "--source-sha", "9e1b3f060e649a64c698b2a5981dbfca1d741b84",
            "--archive-sha256", "5" * 64,
        ]
        self.assertFalse(module.parse_args(base).bounded_read_only)
        self.assertTrue(module.parse_args([*base, "--bounded-read-only"]).bounded_read_only)
        with self.assertRaises(SystemExit):
            module.parse_args([*base, "--bounded-read-only", "--inspect-context-menu"])

    def test_owned_production_cli_serializes_worker_failure(self):
        with tempfile.TemporaryDirectory(prefix="player-inspection-cli-") as raw:
            output_dir = Path(raw) / "run"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SUPERVISOR),
                    "--output-dir",
                    str(output_dir),
                    "--hwnd",
                    "1",
                    "--pid",
                    str(os.getpid()),
                    "--create-time",
                    "1.0",
                    "--exe",
                    sys.executable,
                    "--expected-rows",
                    json.dumps(["one.wav (0:30)", "two.wav (0:30)", "three.wav (0:30)"]),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(completed.returncode, 1, completed.stderr)
            emitted = json.loads(completed.stdout)
            self.assertEqual(emitted["status"], "FAIL")
            self.assertEqual(emitted["child_payload"]["status"], "FAIL")
            self.assertIn(emitted["child_payload"]["failure_kind"], {"platform_guard", "worker"})
            self.assertNotIn("usage:", emitted["stderr"])
            saved = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(emitted, saved)
            self.assertTrue((output_dir / "stdout.txt").is_file())
            self.assertTrue((output_dir / "stderr.txt").is_file())


if __name__ == "__main__":
    unittest.main()
