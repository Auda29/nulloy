"""Real Qt subprocess contracts; offscreen Linux is not Windows UIA."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import psutil

FIXTURE = Path(__file__).with_name("fixture.py")


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="uia-fixture-contract-")
        self.root = Path(self.temp.name) / "owned-fixture"
        self.process = None
        self.log = open(Path(self.temp.name) / "child.log", "w+b")

    def tearDown(self):
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        self.log.close()
        self.temp.cleanup()

    def start(self, *extra):
        env = dict(os.environ)
        if os.name != "nt":
            env["QT_QPA_PLATFORM"] = "offscreen"
        self.process = subprocess.Popen(
            [sys.executable, str(FIXTURE), "--root", str(self.root),
             "--nonce", "contract-123", "--lifetime", "3", *extra],
            stdout=self.log, stderr=self.log, stdin=subprocess.DEVNULL,
            env=env, shell=False,
        )

    def state(self):
        return json.loads((self.root / "state.json").read_text(encoding="utf-8"))

    def await_state(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if (self.root / "state.json").exists():
                record = self.state()
                if predicate(record):
                    return record
            if self.process.poll() is not None:
                self.log.seek(0)
                self.fail("fixture exited before expected state: " + self.log.read().decode(errors="replace"))
            time.sleep(0.025)
        self.fail("fixture state deadline exceeded")

    def test_requested_gui_stall_stops_heartbeat_then_recovers(self):
        self.start("--block-seconds", "1.4")
        self.await_state(lambda s: s["heartbeat"] >= 2)
        (self.root / "block-request.json").write_text(
            json.dumps({"nonce": "contract-123"}), encoding="utf-8")
        blocked = self.await_state(lambda s: s["phase"] == "blocked")
        time.sleep(0.25)
        still = self.state()
        self.assertEqual(still["phase"], "blocked")
        self.assertEqual(still["heartbeat"], blocked["heartbeat"])
        recovered = self.await_state(lambda s: s["phase"] == "responsive" and s.get("block_count") == 1)
        self.assertGreaterEqual(recovered["block_elapsed"], 1.3)
        self.await_state(lambda s: s["heartbeat"] > recovered["heartbeat"])
        self.assertEqual(self.process.wait(timeout=6), 0)
        self.assertEqual(self.state()["block_count"], 1)

    def test_invalid_bounds_or_nonce_fail_before_creating_fixture_root(self):
        cases = [("--lifetime", v) for v in ("nan", "inf", "0", "-1", "121")]
        cases += [("--block-seconds", v) for v in ("nan", "inf", "0", "-1", "91")]
        cases += [("--nonce", "bad/name"), ("--nonce", "")]
        for index, (option, value) in enumerate(cases):
            with self.subTest(option=option, value=value):
                self.root = Path(self.temp.name) / f"case-{index}"
                self.start(option, value)
                try:
                    self.assertNotEqual(self.process.wait(timeout=5), 0)
                    self.assertFalse(self.root.exists(), "invalid input created fixture files")
                finally:
                    if self.process.poll() is None:
                        self.process.kill()
                        self.process.wait(timeout=5)

    def test_invalid_request_fails_without_blocking(self):
        for index, payload in enumerate(("{", '{"nonce":"foreign"}')):
            with self.subTest(payload=payload):
                self.root = Path(self.temp.name) / f"request-{index}"
                self.start()
                self.await_state(lambda s: s["heartbeat"] >= 2)
                (self.root / "block-request.json").write_text(payload, encoding="utf-8")
                self.assertEqual(self.process.wait(timeout=5), 1)
                state = self.state()
                self.assertEqual(state["phase"], "failed")
                self.assertIn("request", state["error"])
                self.assertEqual(state.get("block_count", 0), 0)

    def test_responsive_qt_heartbeat_and_exact_process_identity(self):
        self.start()
        state = self.await_state(lambda s: s["heartbeat"] >= 2)
        self.assertEqual(state["nonce"], "contract-123")
        self.assertEqual(state["pid"], self.process.pid)
        process = psutil.Process(self.process.pid)
        self.assertEqual(state["create_time"], process.create_time())
        self.assertTrue(os.path.samefile(state["executable"], process.exe()))
        self.assertGreater(state["hwnd"], 0)
        self.assertEqual(state["qt_version"], "6.8.2")
        self.assertEqual(state["phase"], "responsive")
        self.assertEqual(self.process.wait(timeout=6), 0)
        self.assertEqual(self.state()["phase"], "complete")
        self.assertFalse(psutil.pid_exists(self.process.pid))


if __name__ == "__main__":
    unittest.main()
