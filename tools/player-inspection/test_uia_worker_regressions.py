"""Test-first regressions for bounded parent/worker ownership and cold start."""
from __future__ import annotations

import ctypes
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent

def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_probe_validator = sys.modules.get("nulloy_trash_probe_validator")
inspector = _load("bounded_inspector_regressions", HERE / "inspect_player.py")
if _probe_validator is not None:
    # Do not replace test_contract's validator module with this dynamic import.
    sys.modules["nulloy_trash_probe_validator"] = _probe_validator
worker = _load("bounded_worker_regressions", HERE / "uia_worker.py")

IDENTITY = {"pid": 4242, "create_time": 12.5}
EXE = Path("C:/Nulloy/Nulloy.exe")
TARGET = {
    "pid": 4242,
    "create_time": 12.5,
    "executable": str(EXE),
    "hwnd": 1001,
    "class_name": "NMainWindow",
    "visible": True,
}
EXPECTED = ["one.wav (0:30)", "two.wav (0:30)", "three.wav (0:30)"]


class _FakeProcess:
    pid = 4242
    returncode = None

    def poll(self):
        return None
class _FakeNativeProcess:
    def __init__(self, pid: int, create_time: float = 12.5, exe: str = str(EXE)):
        self.pid = pid
        self._create_time = create_time
        self._exe = exe

    def create_time(self):
        return self._create_time

    def exe(self):
        return self._exe


class _FakePsutil:
    def __init__(self, processes):
        self.processes = processes

    def Process(self, pid):
        return self.processes[pid]


class _FakeElementInfo:
    def __init__(self, *, pid=4242, hwnd=1001, class_name="NMainWindow", control_type="Pane"):
        self.process_id = pid
        self.handle = hwnd
        self.class_name = class_name
        self.control_type = control_type
        self.name = "Nulloy"
        self.automation_id = ""
        self.runtime_id = [pid, hwnd]


class _FakeRoot:
    def __init__(self, **kwargs):
        self.visible = kwargs.pop("visible", True)
        self.element_info = _FakeElementInfo(**kwargs)

    def is_visible(self):
        return self.visible


class _FakeUser32:
    """Faithful enough Win32 double: exports receive typed ctypes args."""

    @staticmethod
    def _hwnd_value(hwnd):
        return int(getattr(hwnd, "value", hwnd))

    def __init__(self, windows, owners, visible=None, classes=None):
        self.windows = windows
        self.owners = owners
        self.visible = visible or {hwnd: True for hwnd in windows}
        self.classes = classes or {hwnd: "NMainWindow" for hwnd in windows}
        self.EnumWindows = self._export(lambda callback, lparam: self._enum_windows(callback, lparam))
        self.IsWindow = self._export(lambda hwnd: self._hwnd_value(hwnd) in self.owners)
        self.IsWindowVisible = self._export(lambda hwnd: self.visible.get(self._hwnd_value(hwnd), False))
        self.GetWindowThreadProcessId = self._export(lambda hwnd, out: self._get_pid(hwnd, out))
        self.GetClassNameW = self._export(lambda hwnd, buffer, length: self._get_class(hwnd, buffer, length))

    @staticmethod
    def _export(function):
        function.argtypes = None
        function.restype = None
        return function

    def _enum_windows(self, callback, _lparam):
        for hwnd in self.windows:
            if not callback(hwnd, 0):
                break
        return 1

    def _get_pid(self, hwnd, out_pid):
        value = self.owners.get(self._hwnd_value(hwnd), 0)
        ctypes.cast(out_pid, ctypes.POINTER(ctypes.c_uint32)).contents.value = value
        return 1 if value else 0

    def _get_class(self, hwnd, buffer, _length):
        buffer.value = self.classes.get(self._hwnd_value(hwnd), "")
        return len(buffer.value)


class _FakeResult:
    def __init__(self, status="TIMEOUT", failure_kind="timeout", primary_error="worker timeout"):
        self.status = status
        self.success = status == "SUCCESS"
        self.failure_kind = failure_kind
        self.timed_out = status == "TIMEOUT"
        self.cleanup_verified = True
        self.primary_error = primary_error
        self.secondary_errors = []
        self.target_before = dict(TARGET)
        self.target_after = dict(TARGET)
        self.child_payload = {"snapshot": [], "playlist_rows": EXPECTED}

    def to_dict(self):
        return {
            "status": self.status,
            "success": self.success,
            "failure_kind": self.failure_kind,
            "timed_out": self.timed_out,
            "primary_error": self.primary_error,
            "secondary_errors": list(self.secondary_errors),
            "target_before": self.target_before,
            "target_after": self.target_after,
            "child_payload": self.child_payload,
        }


class ParentOwnershipRegressions(unittest.TestCase):
    def test_native_qt_window_class_is_not_confused_with_uia_class(self):
        fake_user32 = _FakeUser32([1001], {1001: 4242}, classes={1001: 'Qt682QWindowIcon'})
        psutil = _FakePsutil({4242: _FakeNativeProcess(4242)})
        with mock.patch.object(inspector, 'is_windows_native', return_value=True), \
             mock.patch.object(inspector.ctypes, 'WinDLL', return_value=fake_user32, create=True):
            try:
                target = inspector._discover_owned_main_hwnd(
                    _FakeProcess(), psutil, IDENTITY, EXE, timeout=.001, poll_interval=0)
            except (TimeoutError, inspector.ContractError) as exc:
                self.fail(f'Win32 class was wrongly treated as UIA NMainWindow: {exc}')
        self.assertEqual(target['hwnd'], 1001)
        self.assertEqual(target['class_name'], 'Qt682QWindowIcon')

    def test_parent_native_discovery_rejects_missing_window_before_worker(self):
        fake_user32 = _FakeUser32([], {})
        psutil = _FakePsutil({4242: _FakeNativeProcess(4242)})
        with mock.patch.object(inspector, "is_windows_native", return_value=True), \
             mock.patch.object(inspector.ctypes, "WinDLL", return_value=fake_user32, create=True):
            with self.assertRaises(TimeoutError):
                inspector._discover_owned_main_hwnd(
                    _FakeProcess(), psutil, IDENTITY, EXE, timeout=0.001, poll_interval=0
                )

    def test_parent_native_doubles_verify_typed_exports_and_pid_pointer(self):
        fake_user32 = _FakeUser32([1001], {1001: 9999})
        psutil = _FakePsutil({4242: _FakeNativeProcess(4242), 9999: _FakeNativeProcess(9999, 1.0)})
        with mock.patch.object(inspector, "is_windows_native", return_value=True), \
             mock.patch.object(inspector.ctypes, "WinDLL", return_value=fake_user32, create=True):
            with self.assertRaises(TimeoutError):
                inspector._discover_owned_main_hwnd(
                    _FakeProcess(), psutil, IDENTITY, EXE, timeout=0.001, poll_interval=0
                )
        self.assertEqual(fake_user32.IsWindow.argtypes, [inspector.wintypes.HWND])
        self.assertEqual(fake_user32.IsWindow.restype, inspector.wintypes.BOOL)
        self.assertEqual(fake_user32.IsWindowVisible.argtypes, [inspector.wintypes.HWND])
        self.assertEqual(
            fake_user32.GetWindowThreadProcessId.argtypes,
            [inspector.wintypes.HWND, ctypes.POINTER(inspector.wintypes.DWORD)],
        )
        self.assertEqual(fake_user32.GetWindowThreadProcessId.restype, inspector.wintypes.DWORD)
        self.assertEqual(
            fake_user32.GetClassNameW.argtypes,
            [inspector.wintypes.HWND, inspector.wintypes.LPWSTR, ctypes.c_int],
        )

    def test_parent_native_discovery_rejects_foreign_and_swapped_identity(self):
        fake_user32 = _FakeUser32([1001, 1002, 1003], {1001: 9999, 1002: 4242, 1003: 4242})
        psutil = _FakePsutil({
            4242: _FakeNativeProcess(4242, 12.5),
            9999: _FakeNativeProcess(9999, 1.0),
        })
        with mock.patch.object(inspector, "is_windows_native", return_value=True), \
             mock.patch.object(inspector.ctypes, "WinDLL", return_value=fake_user32, create=True):
            with self.assertRaises(inspector.ContractError):
                inspector._discover_owned_main_hwnd(
                    _FakeProcess(), psutil, IDENTITY, EXE, timeout=0.001, poll_interval=0
                )

    def test_parent_target_validation_rejects_malformed_foreign_and_swapped_fields(self):
        for mutation in (
            {"pid": 9999},
            {"create_time": 99.0},
            {"executable": "C:/other.exe"},
            {"hwnd": 0},
            {"pid": "4242"},
            {"create_time": float("nan")},
        ):
            target = dict(TARGET)
            target.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(inspector.ContractError):
                inspector._validate_bounded_target(target, IDENTITY, EXE, expected_hwnd=1001)

    def test_timeout_keeps_primary_and_records_independent_postcheck_failure(self):
        result = _FakeResult()
        calls = []

        def parent_check(*args, **kwargs):
            calls.append("check")
            if len(calls) == 2:
                raise inspector.ContractError("HWND was swapped after worker timeout")
            return dict(TARGET)

        with mock.patch.object(inspector, "_discover_owned_main_hwnd", side_effect=parent_check), \
             mock.patch.object(inspector.uia_supervisor, "run_supervised", return_value=result) as supervised:
            with self.assertRaises(RuntimeError) as raised:
                inspector._bounded_read_only_snapshot(
                    output=Path("evidence"),
                    process=_FakeProcess(),
                    psutil=mock.Mock(),
                    identity=IDENTITY,
                    executable=EXE,
                    expected_rows=EXPECTED,
                )
        worker_args = supervised.call_args.kwargs["worker_args"]
        self.assertEqual(worker_args[worker_args.index("--hwnd") + 1], "1001")
        self.assertEqual(
            json.loads(worker_args[worker_args.index("--expected-rows") + 1]),
            EXPECTED,
        )
        self.assertEqual(calls, ["check", "check"])
        self.assertIn("TIMEOUT", str(raised.exception))
        self.assertIn("HWND was swapped", raised.exception.supervisor_result["secondary_errors"][0])
        self.assertEqual(raised.exception.supervisor_result["failure_kind"], "timeout")


class WorkerReadinessRegressions(unittest.TestCase):
    def test_unknown_or_failing_visibility_is_not_a_transient_retry(self):
        for value in ('unknown', OSError('provider visibility failure')):
            with self.subTest(value=value):
                root = _FakeRoot(visible=value)
                if isinstance(value, Exception):
                    root.is_visible = mock.Mock(side_effect=value)
                try:
                    worker._validate_main_root(root, 4242, 1001)
                except worker._OwnershipError:
                    pass
                except Exception as exc:
                    self.fail(f'uncertain visibility was incorrectly made retryable: {exc!r}')
                else:
                    self.fail('uncertain visibility was accepted')

    def test_retry_reaches_playlist_after_transient_cold_start_failures(self):
        attempts = []

        def operation():
            attempts.append(len(attempts))
            if len(attempts) < 3:
                raise worker._TransientNotReady("playlist is not ready")
            return "ready"

        with mock.patch.object(worker.time, "sleep", return_value=None):
            self.assertEqual(worker._retry_until_ready(operation, timeout=0.1), "ready")
        self.assertEqual(attempts, [0, 1, 2])

    def test_raised_supervision_error_still_runs_parent_postcheck(self):
        calls = []

        def parent_check(*args, **kwargs):
            calls.append(True)
            return dict(TARGET)

        supervision_error = RuntimeError("supervisor read failure")
        supervision_error.supervisor_result = {
            "status": "FAIL",
            "failure_kind": "supervision",
            "primary_error": "supervisor read failure",
            "secondary_errors": [],
        }
        with mock.patch.object(inspector, "_discover_owned_main_hwnd", side_effect=parent_check), \
             mock.patch.object(inspector.uia_supervisor, "run_supervised", side_effect=supervision_error):
            with self.assertRaises(RuntimeError) as raised:
                inspector._bounded_read_only_snapshot(
                    output=Path("evidence"), process=_FakeProcess(), psutil=mock.Mock(),
                    identity=IDENTITY, executable=EXE, expected_rows=EXPECTED,
                )
        self.assertIs(raised.exception, supervision_error)
        self.assertEqual(calls, [True, True])

    def test_retry_propagates_ownership_error_without_retry(self):
        attempts = []

        def operation():
            attempts.append(True)
            raise worker._OwnershipError("foreign row")

        with mock.patch.object(worker.time, "sleep", return_value=None):
            with self.assertRaises(worker._OwnershipError):
                worker._retry_until_ready(operation, timeout=0.1)
        self.assertEqual(attempts, [True])

    def test_worker_accepts_exact_expected_rows_json_and_rejects_malformed_identity(self):
        parsed = worker._parser().parse_args([
            "--hwnd", "0x3e9", "--pid", "4242", "--create-time", "12.5",
            "--exe", str(EXE), "--expected-rows", json.dumps(EXPECTED),
        ])
        self.assertEqual(parsed.expected_rows, EXPECTED)
        with self.assertRaises(worker._OwnershipError):
            worker._validate_main_root(_FakeRoot(hwnd=1002), 4242, 1001)

    def test_worker_native_double_checks_typed_exports_and_pid_pointer(self):
        fake_user32 = _FakeUser32([1001], {1001: 4242})
        with mock.patch.object(worker.os, "name", "nt"), \
             mock.patch.object(worker.ctypes, "WinDLL", return_value=fake_user32, create=True):
            info = worker._native_window_info(1001)
        self.assertEqual(info, {"hwnd": 1001, "pid": 4242, "visible": True})
        self.assertEqual(fake_user32.IsWindow.argtypes, [worker.wintypes.HWND])
        self.assertEqual(fake_user32.IsWindow.restype, worker.wintypes.BOOL)
        self.assertEqual(fake_user32.IsWindowVisible.argtypes, [worker.wintypes.HWND])
        self.assertEqual(
            fake_user32.GetWindowThreadProcessId.argtypes,
            [worker.wintypes.HWND, ctypes.POINTER(worker.wintypes.DWORD)],
        )
        self.assertEqual(fake_user32.GetWindowThreadProcessId.restype, worker.wintypes.DWORD)

    def test_worker_requires_visible_nmainwindow_pane_for_pinned_hwnd(self):
        for kwargs in (
            {"class_name": "QWidget"},
            {"control_type": "Window"},
            {"hwnd": 1002},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(worker._OwnershipError):
                with mock.patch.object(worker, "_native_window_info", return_value={"hwnd": 1001, "pid": 4242, "visible": True}):
                    worker._validate_main_root(_FakeRoot(**kwargs), 4242, 1001)


class CleanupEvidenceRegressions(unittest.TestCase):
    def test_runtime_report_hashes_cover_all_bounded_helpers(self):
        hashes = inspector._runtime_source_hashes()
        self.assertEqual(
            set(hashes),
            {"inspect_player.py", "uia_supervisor.py", "uia_worker.py", "owned_pointer.py"},
        )
        self.assertTrue(all(len(value) == 64 for value in hashes.values()))

    def test_uncertain_worker_cleanup_retains_temp_root_and_primary_failure(self):
        # The bounded path must not allow player exit to erase uncertain worker evidence.
        with tempfile.TemporaryDirectory() as raw:
            temp_root = Path(raw) / "package"
            temp_root.mkdir()
            process = mock.Mock()
            process.poll.return_value = 0
            report = {
                "status": "FAIL",
                "error": "worker timeout",
                "uia_supervisor": {"status": "TIMEOUT", "cleanup_verified": False},
            }
            retained, errors = inspector._cleanup(
                process, temp_root, owner_check=lambda: None, retain_temp_root=True
            )
            self.assertFalse(retained)
            self.assertTrue(temp_root.exists())
            self.assertTrue(errors)
            self.assertEqual(report["error"], "worker timeout")


if __name__ == "__main__":
    unittest.main()
