"""Independent RED/GREEN behavior checks for the focus-diagnostic review."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load("focus_review_base", HERE / "test_focus_diagnostic.py")
worker = base.worker
inspector = base.inspector
EXPECTED = base.EXPECTED
NATIVE = base.NATIVE_SNAPSHOT
IDENTITY = base.IDENTITY
EXE = base.EXE


class FocusReviewFixes(unittest.TestCase):
    def _fixture(self, **kwargs):
        return base.FocusDiagnosticREDTests()._fixture(**kwargs)

    def test_cold_start_empty_root_then_ready_retries_and_sets_focus_once(self):
        actions, _rows, _playlist, ready_root, desktop = self._fixture()
        empty_root = mock.Mock()
        empty_root.element_info = ready_root.element_info
        empty_root.descendants = lambda: []
        with mock.patch.object(worker, "_find_main", side_effect=[empty_root, ready_root]), mock.patch.object(
            worker, "_validate_main_root", return_value=ready_root
        ), mock.patch.object(worker.time, "sleep", return_value=None):
            result = worker._retry_until_ready(
                lambda: worker._focus_diagnostic_once(
                    desktop, base._Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                    native_focus=lambda hwnd, pid: NATIVE,
                ),
                timeout=0.1,
                interval=0,
            )
        self.assertEqual(result["focus_diagnostic"]["set_focus"]["call_count"], 1)
        self.assertEqual(actions, ["SetFocus"])

    def test_known_provider_not_ready_retries_but_unknown_provider_failure_is_fatal(self):
        class ElementNotAvailableError(RuntimeError):
            pass

        actions, _rows, _playlist, ready_root, desktop = self._fixture()
        transient_root = mock.Mock()
        transient_root.element_info = ready_root.element_info
        transient_root.descendants = mock.Mock(
            side_effect=ElementNotAvailableError("UIA_E_ELEMENTNOTAVAILABLE")
        )
        with mock.patch.object(worker, "_find_main", side_effect=[transient_root, ready_root]), mock.patch.object(
            worker, "_validate_main_root", return_value=ready_root
        ), mock.patch.object(worker.time, "sleep", return_value=None):
            result = worker._retry_until_ready(
                lambda: worker._focus_diagnostic_once(
                    desktop, base._Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                    native_focus=lambda hwnd, pid: NATIVE,
                ),
                timeout=0.1,
                interval=0,
            )
        self.assertEqual(actions, ["SetFocus"])
        self.assertEqual(result["status"], "PASS")

        fatal_root = ready_root
        fatal_root.descendants = mock.Mock(side_effect=OSError("provider failure sentinel"))
        with mock.patch.object(worker, "_find_main", return_value=fatal_root), mock.patch.object(
            worker, "_validate_main_root", return_value=fatal_root
        ):
            with self.assertRaises(worker._OwnershipError) as raised:
                worker._focus_diagnostic_once(
                    desktop, base._Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                    native_focus=lambda hwnd, pid: NATIVE,
                )
        self.assertIn("provider failure sentinel", repr(raised.exception.__cause__))
        self.assertEqual(actions, ["SetFocus"])

    def test_parent_requires_actual_native_snapshot_and_consistent_thread(self):
        actions, _rows, _playlist, root, desktop = self._fixture()
        with mock.patch.object(worker, "_find_main", return_value=root), mock.patch.object(
            worker, "_validate_main_root", return_value=root
        ):
            payload = worker._focus_diagnostic_once(
                desktop, base._Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                native_focus=lambda hwnd, pid: NATIVE,
            )
        self.assertEqual(inspector._validate_bounded_focus_payload(payload, EXPECTED)["native"]["before"]["root_thread_id"], 77)

        malformed = json.loads(json.dumps(payload))
        malformed["focus_diagnostic"]["native"]["before"] = {}
        with self.assertRaises(inspector.ContractError):
            inspector._validate_bounded_focus_payload(malformed, EXPECTED)

        mismatched = json.loads(json.dumps(payload))
        mismatched["focus_diagnostic"]["native"]["after"]["root_thread_id"] = 78
        with self.assertRaises(inspector.ContractError):
            inspector._validate_bounded_focus_payload(mismatched, EXPECTED)

    def test_native_snapshot_bounds_windows_integers_and_allows_signed_rect(self):
        actions, _rows, _playlist, root, desktop = self._fixture()
        with mock.patch.object(worker, "_find_main", return_value=root), mock.patch.object(
            worker, "_validate_main_root", return_value=root
        ):
            payload = worker._focus_diagnostic_once(
                desktop, base._Process(), IDENTITY, EXE, 1001, EXPECTED, lambda value: None,
                native_focus=lambda hwnd, pid: NATIVE,
            )
        diagnostic = payload["focus_diagnostic"]
        self.assertEqual(inspector._validate_bounded_focus_payload(payload, EXPECTED), diagnostic)
        max_hwnd = (1 << (inspector.ctypes.sizeof(inspector.ctypes.c_void_p) * 8)) - 1
        max_pid = (1 << 32) - 1
        for field, value in (("hwnd", max_hwnd + 1), ("pid", max_pid + 1)):
            malformed = json.loads(json.dumps(payload))
            malformed["focus_diagnostic"]["native"]["before"]["foreground"][field] = value
            with self.subTest(field=field), self.assertRaises(inspector.ContractError):
                inspector._validate_bounded_focus_payload(malformed, EXPECTED)

        malformed = json.loads(json.dumps(payload))
        malformed["focus_diagnostic"]["native"]["before"]["owned_thread_focus"]["focus"] = {
            "hwnd": 1001,
            "pid": 0,
        }
        with self.assertRaises(inspector.ContractError):
            inspector._validate_bounded_focus_payload(malformed, EXPECTED)

    def test_run_inspection_saves_supervisor_evidence_when_focus_contract_fails(self):
        supervisor = {
            "status": "SUCCESS",
            "success": True,
            "cleanup_verified": True,
            "stdout": "SETFOCUS_SUPERVISOR_STDOUT",
            "stderr": "SUPERVISOR_STDERR",
            "child_payload": {
                "status": "PASS",
                "diagnostic_only": True,
                "context_acceptance": False,
                "capture_completed": True,
                "playlist_rows": EXPECTED,
                "focus_diagnostic": {"native": {}},
            },
        }
        bounded = {"result": supervisor, "target": {
            "pid": 4242, "create_time": 12.5, "executable": EXE,
            "hwnd": 1001, "class_name": "NMainWindow", "visible": True,
        }, "snapshot": [], "playlist_rows": EXPECTED}
        package_info = types.SimpleNamespace(
            archive_sha256="a" * 64, executable_sha256="b" * 64,
            file_hashes_verified=True, root=Path("package-root"),
            executable=Path("package-root/Nulloy.exe"),
            contract=types.SimpleNamespace(source_commit="fixture"),
        )
        args = types.SimpleNamespace(
            output=Path(tempfile.mkdtemp()), package=Path("package.zip"),
            source_sha="a" * 40, archive_sha256="c" * 64,
            allow_owned_pointer_input=False, bounded_read_only=False,
            bounded_context_menu=False, bounded_focus_diagnostic=True,
            inspect_context_menu=False,
        )
        process = mock.Mock()
        process.poll.return_value = 0
        with mock.patch.object(inspector, "is_windows_native", return_value=True), mock.patch.object(
            inspector, "parse_source_sha", return_value=args.source_sha
        ), mock.patch.object(inspector, "parse_archive_sha", return_value=args.archive_sha256), mock.patch.object(
            inspector, "_sha256", return_value="c" * 64
        ), mock.patch.object(inspector, "extract_and_validate", return_value=package_info), mock.patch.object(
            inspector, "make_fixtures", return_value=[]
        ), mock.patch.object(inspector, "expected_playlist_rows", return_value=EXPECTED), mock.patch.object(
            inspector, "_portable_config", return_value=Path("config.ini")
        ), mock.patch.object(inspector.subprocess, "Popen", return_value=process), mock.patch.object(
            inspector, "_process_identity", return_value=IDENTITY
        ), mock.patch.object(inspector, "_bounded_read_only_snapshot", return_value=bounded), mock.patch.dict(
            sys.modules, {"psutil": types.SimpleNamespace()}
        ):
            code, report = inspector.run_inspection(args)

        saved = json.loads((args.output / "inspection-report.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        for observed in (report, saved):
            self.assertEqual(observed["status"], "FAIL")
            self.assertTrue(observed["diagnostic_only"])
            self.assertFalse(observed["context_acceptance"])
            self.assertEqual(observed["uia_supervisor"]["stdout"], "SETFOCUS_SUPERVISOR_STDOUT")
            self.assertTrue(observed["cleanup"]["process_cleanup_verified"])

    def test_real_child_retains_setfocus_and_postquery_failures_without_retry(self):
        script = f'''\
import importlib.util, sys
from unittest import mock
spec = importlib.util.spec_from_file_location("child_focus_base", {str(HERE / "test_focus_diagnostic.py")!r})
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)
worker = base.worker
actions, rows, playlist, root, desktop = base.FocusDiagnosticREDTests()._fixture(
    row_exception=RuntimeError("SETFOCUS_SENTINEL"))
process = base._Process()
identity_calls = []
def create_time():
    identity_calls.append(True)
    if len(identity_calls) > 1:
        raise RuntimeError("POST_QUERY_SENTINEL")
    return 12.5
process.create_time = create_time
worker.inspect_focus_target = lambda hwnd, pid, create_time_value, exe, expected_rows, retry_timeout=25.0: worker._retry_until_ready(
    lambda: worker._focus_diagnostic_once(
        desktop, process, {{"pid": pid, "create_time": create_time_value}}, exe, hwnd, expected_rows,
        lambda value: None, native_focus=lambda hwnd_value, pid_value: base.NATIVE_SNAPSHOT),
    timeout=retry_timeout, interval=0)
with mock.patch.object(worker, "_find_main", return_value=root), mock.patch.object(
    worker, "_validate_main_root", return_value=root
):
    rc = worker.main(["--hwnd", "1001", "--pid", "4242", "--create-time", "12.5",
                      "--exe", base.EXE, "--expected-rows", __import__("json").dumps(base.EXPECTED),
                      "--focus-diagnostic"])
print("ACTIONS=" + repr(actions))
print("POST_CALLS=" + str(len(identity_calls)))
raise SystemExit(rc)
'''
        completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("SETFOCUS_SENTINEL", completed.stdout)
        self.assertIn("POST_QUERY_SENTINEL", completed.stderr)
        self.assertNotIn('"status": "PASS"', completed.stdout)
        self.assertIn("ACTIONS=['SetFocus']", completed.stdout)
        self.assertIn("POST_CALLS=2", completed.stdout)


if __name__ == "__main__":
    unittest.main()
