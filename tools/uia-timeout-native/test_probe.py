"""Tests for the native UIA timeout controller.

The direct seam deliberately injects read-only worker results on Linux. Those
runs exercise the real Qt fixture and cleanup protocol, but are not native UIA
acceptance evidence.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent


class ProbeFixtureTests(unittest.TestCase):
    def _run(self, outcomes, *, block_seconds=0.65):
        import run_probe

        seen = []

        def query(target, output_dir, stage):
            seen.append((target.copy(), Path(output_dir), stage))
            return outcomes[stage]

        with tempfile.TemporaryDirectory(prefix="uia-native-test-") as raw:
            report = run_probe.run_probe(
                query_runner=query,
                evidence_root=Path(raw) / "evidence",
                fixture_lifetime=4,
                block_seconds=block_seconds,
                non_native_test=True,
            )
            self.assertTrue(Path(report["evidence_dir"]).is_dir())
            return report, seen

    @staticmethod
    def _success(target, *, title=False):
        text_key = "window_title" if title else "name"
        return {
            "status": "SUCCESS",
            "success": True,
            "cleanup_verified": True,
            "returncode": 0,
            "child_payload": {
                "status": "PASS",
                "pid": target["pid"],
                "hwnd": target["hwnd"],
                "snapshot": [{"process_id": target["pid"], text_key: target["label"] if not title else target["window_title"]}],
            },
        }

    def test_real_fixture_responsive_and_blocked_timeout_are_bounded_and_cleaned(self):
        def query(target, output_dir, stage):
            if stage == "responsive":
                return self._success(target)
            return {
                "status": "TIMEOUT",
                "timed_out": True,
                "timeout_phase": "execution",
                "cleanup_verified": True,
                "returncode": -15,
                "supervision_elapsed_s": 0.06,
                "execution_deadline_s": 0.1,
            }

        import run_probe

        with tempfile.TemporaryDirectory(prefix="uia-native-test-") as raw:
            report = run_probe.run_probe(
                query_runner=query,
                evidence_root=Path(raw) / "evidence",
                fixture_lifetime=4,
                block_seconds=0.65,
                non_native_test=True,
            )
            self.assertEqual(report["outcome"], "PASS")
            self.assertEqual(report["acceptance_label"], "non-native trusted query seam")
            self.assertTrue(report["native_acceptance_false"])
            self.assertTrue(report["responsive"]["verified"])
            self.assertTrue(report["blocked"]["confirmed"])
            self.assertTrue(report["blocked"]["heartbeat_stopped"])
            self.assertEqual(report["blocked"]["query"]["timeout_phase"], "execution")
            self.assertTrue(report["fixture_cleanup"]["verified"])
            self.assertFalse(Path(report["owned_temp_parent"]).exists())
            self.assertEqual(len(report["raw_supervisor_reports"]), 2)

    def test_worker_return_during_block_is_partial_not_timeout_pass(self):
        import run_probe

        def query(target, output_dir, stage):
            return self._success(target)

        with tempfile.TemporaryDirectory(prefix="uia-native-test-") as raw:
            report = run_probe.run_probe(
                query_runner=query,
                evidence_root=Path(raw) / "evidence",
                fixture_lifetime=4,
                block_seconds=0.6,
                non_native_test=True,
            )
            self.assertEqual(report["outcome"], "PARTIAL")
            self.assertEqual(report["blocked"]["classification"], "worker_returned_snapshot_validated")
            self.assertNotIn("timeout-demonstration", report["acceptance_label"])
            self.assertTrue(report["fixture_cleanup"]["verified"])

    def test_responsive_failure_stops_before_block_request(self):
        import run_probe

        calls = []

        def query(target, output_dir, stage):
            calls.append(stage)
            return {"status": "TIMEOUT", "timeout_phase": "readiness", "cleanup_verified": True}

        with tempfile.TemporaryDirectory(prefix="uia-native-test-") as raw:
            report = run_probe.run_probe(
                query_runner=query,
                evidence_root=Path(raw) / "evidence",
                fixture_lifetime=3,
                non_native_test=True,
            )
            self.assertEqual(report["outcome"], "FAIL")
            self.assertEqual(report["failure_kind"], "responsive_query")
            self.assertEqual(calls, ["responsive"])
            self.assertTrue(report["fixture_cleanup"]["verified"])

    def test_nonce_pid_and_snapshot_identity_rejection_is_fail(self):
        import run_probe

        def query(target, output_dir, stage):
            result = self._success(target)
            result["child_payload"]["pid"] += 1
            return result

        with tempfile.TemporaryDirectory(prefix="uia-native-test-") as raw:
            report = run_probe.run_probe(
                query_runner=query,
                evidence_root=Path(raw) / "evidence",
                fixture_lifetime=3,
                non_native_test=True,
            )
            self.assertEqual(report["outcome"], "FAIL")
            self.assertIn("identity", report["failure_kind"])
            self.assertTrue(report["fixture_cleanup"]["verified"])

    def test_worker_error_is_partial_and_report_is_serialized(self):
        import run_probe

        def query(target, output_dir, stage):
            if stage == "responsive":
                return self._success(target)
            return {
                "status": "FAIL",
                "failure_kind": "child_result",
                "primary_error": "injected worker error",
                "cleanup_verified": True,
                "returncode": 1,
            }

        with tempfile.TemporaryDirectory(prefix="uia-native-test-") as raw:
            report = run_probe.run_probe(
                query_runner=query,
                evidence_root=Path(raw) / "evidence",
                fixture_lifetime=3,
                block_seconds=0.5,
                non_native_test=True,
            )
            saved = json.loads((Path(report["evidence_dir"]) / "final-report.json").read_text())
            self.assertEqual(saved["outcome"], "PARTIAL")
            self.assertEqual(saved["blocked"]["classification"], "worker_error")
            self.assertEqual(saved["blocked"]["query"]["primary_error"], "injected worker error")

    def test_cleanup_uncertainty_is_fail_and_temp_is_retained(self):
        import run_probe

        def query(target, output_dir, stage):
            return self._success(target)

        real_cleanup = run_probe._cleanup_fixture

        def uncertain_cleanup(process):
            result = real_cleanup(process)
            result["verified"] = False
            result["primary_error"] = "injected cleanup uncertainty"
            result["returncode"] = None
            return result

        with tempfile.TemporaryDirectory(prefix="uia-native-test-") as raw:
            with mock.patch.object(run_probe, "_cleanup_fixture", side_effect=uncertain_cleanup):
                report = run_probe.run_probe(
                    query_runner=query,
                    evidence_root=Path(raw) / "evidence",
                    fixture_lifetime=3,
                    non_native_test=True,
                )
            self.assertEqual(report["outcome"], "FAIL")
            self.assertEqual(report["failure_kind"], "fixture_cleanup")
            self.assertTrue(Path(report["owned_temp_parent"]).exists())


class ProbeGuardTests(unittest.TestCase):
    def test_cli_rejects_non_windows_before_starting_fixture(self):
        import run_probe

        with tempfile.TemporaryDirectory(prefix="uia-native-cli-") as raw:
            with mock.patch.object(run_probe.os, "name", "posix"):
                status = run_probe.main(["--evidence-root", str(Path(raw) / "evidence")])
            self.assertEqual(status, 1)
            self.assertFalse(any(Path(raw).rglob("state.json")))


if __name__ == "__main__":
    unittest.main()
