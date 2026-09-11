"""Narrow controller for a bounded, read-only Windows UIA fixture probe.

The CLI is Windows-only.  ``run_probe`` has an explicit, trusted test seam so
Linux tests can drive the real Qt fixture without pretending an injected result
is native COM/UIA evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import string
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable

import psutil

FIXTURE = Path(__file__).resolve().parents[1] / "uia-timeout-fixture" / "fixture.py"
SPIKE = Path(__file__).resolve().parents[1] / "uia-timeout-spike"
DEFAULT_STAGE_BUDGET = 10.0 + 5.0 + 2.0 + 2.0

QueryRunner = Callable[[dict[str, Any], Path, str], Any]


class ProbeFailure(RuntimeError):
    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def _nonce() -> str:
    alphabet = string.ascii_letters + string.digits
    return "native-" + "".join(random.SystemRandom().choice(alphabet) for _ in range(20))


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, dict):
        raise TypeError(f"query result must be a dict-like report, got {type(value).__name__}")
    return json.loads(json.dumps(value, sort_keys=True))


def _read_state(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fixture state is not an object")
    return value


def _await_state(process: subprocess.Popen[bytes], path: Path, predicate: Callable[[dict[str, Any]], bool], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "state not published"
    while time.monotonic() < deadline:
        if path.exists():
            try:
                state = _read_state(path)
                if predicate(state):
                    return state
                last_error = f"state predicate not met: phase={state.get('phase')!r}, heartbeat={state.get('heartbeat')!r}"
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                last_error = f"state read: {type(exc).__name__}: {exc}"
        try:
            returncode = process.poll()
        except Exception as exc:
            last_error = f"fixture poll failed: {type(exc).__name__}: {exc}"
            returncode = None
        if returncode is not None:
            raise ProbeFailure("fixture_exit", f"fixture exited before state condition ({returncode}): {last_error}")
        time.sleep(0.025)
    raise ProbeFailure("fixture_readiness", last_error)


def _live_identity(process: subprocess.Popen[bytes]) -> tuple[int, float, str]:
    live = psutil.Process(process.pid)
    return int(live.pid), float(live.create_time()), str(live.exe())


def _validate_target(state: dict[str, Any], process: subprocess.Popen[bytes], *, non_native: bool) -> dict[str, Any]:
    pid, create_time, executable = _live_identity(process)
    nonce = state.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        raise ProbeFailure("fixture_identity", "fixture nonce is missing")
    if state.get("pid") != pid:
        raise ProbeFailure("fixture_identity", f"fixture PID mismatch: record={state.get('pid')!r}, live={pid}")
    if float(state.get("create_time")) != create_time:
        raise ProbeFailure("fixture_identity", "fixture create time differs from live process")
    if str(state.get("executable")) != executable:
        raise ProbeFailure("fixture_identity", "fixture executable differs from live process")
    hwnd = state.get("hwnd")
    if not isinstance(hwnd, int) or isinstance(hwnd, bool) or hwnd <= 0:
        raise ProbeFailure("fixture_identity", f"fixture native HWND is not positive: {hwnd!r}")
    if state.get("qt_version") != "6.8.2":
        raise ProbeFailure("fixture_identity", f"unexpected Qt version: {state.get('qt_version')!r}")
    expected_platform = "offscreen" if non_native else "windows"
    if state.get("qt_platform") != expected_platform:
        raise ProbeFailure(
            "fixture_identity",
            f"unexpected Qt platform: expected={expected_platform!r}, actual={state.get('qt_platform')!r}",
        )
    return {
        "nonce": nonce,
        "pid": pid,
        "create_time": create_time,
        "exe": executable,
        "hwnd": hwnd,
        "qt_version": state["qt_version"],
        "qt_platform": state["qt_platform"],
        "label": f"Harmless UIA heartbeat {nonce}",
        "window_title": f"UIA Timeout Fixture {nonce}",
    }


def _query_default(target: dict[str, Any], output_dir: Path, _stage: str) -> dict[str, Any]:
    sys.path.insert(0, str(SPIKE))
    try:
        import supervisor

        result = supervisor.run_supervised(
            output_dir=output_dir,
            worker_script=supervisor.OWNED_WORKER,
            worker_args=(
                "--hwnd", str(target["hwnd"]),
                "--pid", str(target["pid"]),
                "--create-time", str(target["create_time"]),
                "--exe", target["exe"],
            ),
            readiness_timeout=10.0,
            execution_timeout=5.0,
            terminate_timeout=2.0,
            kill_timeout=2.0,
        )
        return _as_dict(result)
    finally:
        try:
            sys.path.remove(str(SPIKE))
        except ValueError:
            pass


def _snapshot_is_owned(payload: dict[str, Any], target: dict[str, Any]) -> tuple[bool, str]:
    if payload.get("pid") != target["pid"] or payload.get("hwnd") != target["hwnd"]:
        return False, "worker payload identity does not match fixture"
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, list) or not snapshot:
        return False, "worker returned no snapshot records"
    if any(not isinstance(item, dict) or item.get("process_id") != target["pid"] for item in snapshot):
        return False, "snapshot contains a record outside the fixture PID"
    label = target["label"]
    title = target["window_title"]
    if not any(item.get("name") == label or item.get("window_title") == title for item in snapshot):
        return False, "snapshot lacks the exact fixture label/window title carrying the nonce"
    return True, ""


def _validate_responsive(result: dict[str, Any], target: dict[str, Any]) -> tuple[bool, str]:
    if result.get("status") != "SUCCESS" or not result.get("success", False):
        return False, f"responsive query did not succeed: {result.get('status')!r}"
    if not result.get("cleanup_verified", False):
        return False, "responsive worker cleanup is uncertain"
    payload = result.get("child_payload")
    if not isinstance(payload, dict) or payload.get("status") != "PASS":
        return False, "responsive worker did not return a PASS payload"
    return _snapshot_is_owned(payload, target)


def _atomic_request(root: Path, nonce: str) -> None:
    temporary = root / "block-request.tmp"
    temporary.write_text(json.dumps({"nonce": nonce}, sort_keys=True), encoding="utf-8")
    temporary.replace(root / "block-request.json")


def _cleanup_fixture(process: subprocess.Popen[bytes], terminate_timeout: float = 2.0, kill_timeout: float = 2.0) -> dict[str, Any]:
    errors: list[str] = []
    primary = ""
    terminate_sent = False
    kill_sent = False

    def record(label: str, exc: BaseException) -> None:
        nonlocal primary
        message = f"{label}: {type(exc).__name__}: {exc}"
        if not primary:
            primary = message
        else:
            errors.append(message)

    exited = False
    try:
        exited = process.poll() is not None
    except Exception as exc:
        record("initial cleanup poll failed", exc)
    if not exited:
        terminate_sent = True
        try:
            process.terminate()
        except Exception as exc:
            record("terminate failed", exc)
        try:
            process.wait(timeout=terminate_timeout)
            exited = True
        except subprocess.TimeoutExpired:
            pass
        except Exception as exc:
            record("terminate wait failed", exc)
    if not exited:
        kill_sent = True
        try:
            process.kill()
        except Exception as exc:
            record("kill failed", exc)
        try:
            process.wait(timeout=kill_timeout)
            exited = True
        except subprocess.TimeoutExpired as exc:
            record("kill wait timed out", exc)
        except Exception as exc:
            record("kill wait failed", exc)
    try:
        if process.poll() is not None:
            exited = True
    except Exception as exc:
        record("cleanup verification poll failed", exc)
    try:
        if not exited and process.returncode is not None:
            exited = True
    except Exception as exc:
        record("cleanup returncode verification failed", exc)
    return {
        "verified": bool(exited and not errors and not primary),
        "terminate_sent": terminate_sent,
        "kill_sent": kill_sent,
        "returncode": process.returncode,
        "primary_error": primary,
        "secondary_errors": errors,
    }


def _new_evidence_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="probe-", dir=str(root)))


def _write_report(path: Path, report: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_state_copy(evidence_dir: Path, name: str, state: dict[str, Any]) -> None:
    _write_report(evidence_dir / name, state)


def _runtime_hashes() -> dict[str, str]:
    paths = {
        "run_probe.py": Path(__file__),
        "fixture.py": FIXTURE,
        "supervisor.py": SPIKE / "supervisor.py",
        "worker.py": SPIKE / "worker.py",
    }
    return {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in paths.items()
    }


def _workflow_sha() -> str | None:
    value = os.environ.get("GITHUB_SHA")
    if value and len(value) == 40 and all(char in "0123456789abcdefABCDEF" for char in value):
        return value.lower()
    return None


def _record_query(report: dict[str, Any], stage: str, result: dict[str, Any], duration: float) -> None:
    report["raw_supervisor_reports"].append({"stage": stage, "actual_duration_s": duration, "report": result})


def run_probe(
    *,
    query_runner: QueryRunner | None = None,
    evidence_root: str | os.PathLike[str] = "uia-timeout-native-evidence",
    fixture_lifetime: float = 120.0,
    block_seconds: float = 30.0,
    non_native_test: bool = False,
) -> dict[str, Any]:
    """Run the exact fixture protocol and leave a complete evidence report.

    ``query_runner`` and ``non_native_test`` are a trusted Python test seam,
    never exposed by the CLI.  A seam run is explicitly marked non-native.
    """
    if not non_native_test and os.name != "nt":
        raise RuntimeError("native controller requires Windows; use non_native_test with an injected query seam")
    if query_runner is None:
        query_runner = _query_default
    evidence_dir = _new_evidence_dir(Path(evidence_root).resolve())
    temp_parent = Path(tempfile.mkdtemp(prefix="uia-timeout-native-"))
    child_root = temp_parent / "fixture-root"
    nonce = _nonce()
    fixture_stdout_path = evidence_dir / "fixture.stdout"
    fixture_stderr_path = evidence_dir / "fixture.stderr"
    report: dict[str, Any] = {
        "schema_version": 1,
        "outcome": "FAIL",
        "acceptance_label": "non-native trusted query seam" if non_native_test else "native Windows read-only UIA",
        "native_acceptance_false": bool(non_native_test),
        "native_platform": os.name,
        "evidence_dir": str(evidence_dir),
        "owned_temp_parent": str(temp_parent),
        "fixture": {"script": str(FIXTURE), "nonce": nonce, "stdout_path": str(fixture_stdout_path), "stderr_path": str(fixture_stderr_path)},
        "raw_supervisor_reports": [],
        "runtime_sha256": _runtime_hashes(),
        "github_workflow_sha": _workflow_sha(),
        "github_workflow_sha_note": "None is expected for local/non-native execution",
        "configured_stage_budget_s": DEFAULT_STAGE_BUDGET,
        "failure_kind": "",
        "failure_detail": "",
    }
    process: subprocess.Popen[bytes] | None = None
    stdout_handle = None
    stderr_handle = None
    root_state = child_root / "state.json"
    final_state: dict[str, Any] | None = None
    cleanup: dict[str, Any] = {"verified": False, "primary_error": "fixture was not started", "secondary_errors": []}

    try:
        env = dict(os.environ)
        if non_native_test:
            env["QT_QPA_PLATFORM"] = "offscreen"
        stdout_handle = fixture_stdout_path.open("wb")
        stderr_handle = fixture_stderr_path.open("wb")
        process = subprocess.Popen(
            [
                sys.executable,
                str(FIXTURE),
                "--root", str(child_root),
                "--nonce", nonce,
                "--lifetime", str(fixture_lifetime),
                "--block-seconds", str(block_seconds),
            ],
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            shell=False,
            env=env,
            close_fds=True,
        )
        first = _await_state(process, root_state, lambda state: state.get("heartbeat", -1) >= 2 and state.get("phase") == "responsive", 10.0)
        target = _validate_target(first, process, non_native=non_native_test)
        target["initial_heartbeat"] = first["heartbeat"]
        _write_state_copy(evidence_dir, "responsive-state.json", first)
        report["target"] = target

        stage_dir = evidence_dir / "responsive"
        stage_dir.mkdir()
        started = time.monotonic()
        responsive_result = _as_dict(query_runner(target.copy(), stage_dir, "responsive"))
        responsive_duration = time.monotonic() - started
        _record_query(report, "responsive", responsive_result, responsive_duration)
        if not responsive_result.get("cleanup_verified", False):
            raise ProbeFailure("responsive_cleanup", "responsive worker cleanup is uncertain")
        valid, detail = _validate_responsive(responsive_result, target)
        if not valid:
            if "identity" in detail or "snapshot" in detail or "fixture PID" in detail:
                raise ProbeFailure("responsive_identity", detail)
            raise ProbeFailure("responsive_query", detail)
        advanced = _await_state(process, root_state, lambda state: state.get("heartbeat", -1) > first["heartbeat"] and state.get("phase") == "responsive", 2.0)
        report["responsive"] = {"verified": True, "heartbeat_before": first["heartbeat"], "heartbeat_after": advanced["heartbeat"]}

        _atomic_request(child_root, nonce)
        blocked = _await_state(process, root_state, lambda state: state.get("phase") == "blocked" and state.get("block_count") == 1, 5.0)
        _write_state_copy(evidence_dir, "blocked-state.json", blocked)
        blocked_identity = _validate_target(blocked, process, non_native=non_native_test)
        if blocked_identity != {key: target[key] for key in blocked_identity}:
            raise ProbeFailure("blocked_identity", "fixture identity changed at block boundary")
        blocked_heartbeat = blocked["heartbeat"]
        time.sleep(0.2)
        stopped_state = _read_state(root_state)
        _write_state_copy(evidence_dir, "blocked-stopped-state.json", stopped_state)
        heartbeat_stopped = stopped_state.get("phase") == "blocked" and stopped_state.get("heartbeat") == blocked_heartbeat
        report["blocked"] = {
            "confirmed": True,
            "identity": blocked_identity,
            "heartbeat_at_block": blocked_heartbeat,
            "heartbeat_after_0_2s": stopped_state.get("heartbeat"),
            "heartbeat_stopped": heartbeat_stopped,
        }
        if not heartbeat_stopped:
            raise ProbeFailure("blocked_confirmation", "fixture heartbeat did not stop while blocked")

        stage_dir = evidence_dir / "blocked"
        stage_dir.mkdir()
        started = time.monotonic()
        blocked_result = _as_dict(query_runner(target.copy(), stage_dir, "blocked"))
        blocked_duration = time.monotonic() - started
        _record_query(report, "blocked", blocked_result, blocked_duration)
        report["blocked"]["query"] = blocked_result
        capture = _read_state(root_state)
        _write_state_copy(evidence_dir, "blocked-postquery-state.json", capture)
        report["blocked"]["capture_state"] = capture
        continuously_blocked = capture.get("phase") == "blocked" and capture.get("heartbeat") == blocked_heartbeat
        report["blocked"]["query_while_continuously_blocked"] = continuously_blocked
        if not continuously_blocked:
            report["blocked"]["note"] = "fixture resumed before capture; no claim that the query ran while continuously blocked"

        if not blocked_result.get("cleanup_verified", False):
            raise ProbeFailure("blocked_cleanup", "blocked worker cleanup is uncertain")
        status = blocked_result.get("status")
        if status == "TIMEOUT" and blocked_result.get("timeout_phase") == "execution":
            complete = (
                bool(blocked_result.get("timed_out"))
                and blocked_result.get("returncode") is not None
                and continuously_blocked
                and blocked_duration <= DEFAULT_STAGE_BUDGET
            )
            if complete:
                report["blocked"]["classification"] = "execution_timeout_worker_containment_only"
                report["outcome"] = "PASS"
            else:
                report["blocked"]["classification"] = "timeout_conditions_incomplete"
                report["outcome"] = "PARTIAL"
        elif status == "SUCCESS":
            valid, detail = _validate_responsive(blocked_result, target)
            if not valid:
                raise ProbeFailure("blocked_identity", detail)
            report["blocked"]["classification"] = "worker_returned_snapshot_validated"
            report["outcome"] = "PARTIAL"
        elif status == "TIMEOUT" and blocked_result.get("timeout_phase") == "readiness":
            report["blocked"]["classification"] = "readiness_timeout_not_native_COM_bound"
            report["outcome"] = "PARTIAL"
        else:
            report["blocked"]["classification"] = "worker_error"
            report["outcome"] = "PARTIAL"
    except ProbeFailure as exc:
        report["failure_kind"] = exc.kind
        report["failure_detail"] = exc.detail
        report["outcome"] = "FAIL"
    except Exception as exc:
        report["failure_kind"] = "controller_exception"
        report["failure_detail"] = f"{type(exc).__name__}: {exc}"
        report["outcome"] = "FAIL"
    finally:
        if root_state.exists():
            try:
                final_state = _read_state(root_state)
            except Exception as exc:
                report["final_state_error"] = f"{type(exc).__name__}: {exc}"
        if process is not None:
            cleanup = _cleanup_fixture(process)
        report["fixture_cleanup"] = cleanup
        if stdout_handle is not None:
            stdout_handle.close()
        if stderr_handle is not None:
            stderr_handle.close()
        report["final_fixture_state"] = final_state
        if final_state is not None:
            _write_state_copy(evidence_dir, "final-state.json", final_state)
        if not cleanup.get("verified", False):
            report["outcome"] = "FAIL"
            report["failure_kind"] = "fixture_cleanup"
            report["failure_detail"] = cleanup.get("primary_error") or "fixture cleanup could not be verified"
        elif temp_parent.exists():
            try:
                shutil.rmtree(temp_parent)
            except Exception as exc:
                report["outcome"] = "FAIL"
                report["failure_kind"] = "fixture_temp_cleanup"
                report["failure_detail"] = f"{type(exc).__name__}: {exc}"
                report.setdefault("fixture_cleanup", {}).setdefault("secondary_errors", []).append(report["failure_detail"])
        report["owned_temp_parent_retained"] = temp_parent.exists()
        _write_report(evidence_dir / "final-report.json", report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", default="uia-timeout-native-evidence")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if os.name != "nt":
        report = {
            "outcome": "FAIL",
            "failure_kind": "platform_guard",
            "failure_detail": "native UIA controller is Windows-only; no fixture was started",
            "native_acceptance_false": True,
        }
        print(json.dumps(report, sort_keys=True))
        return 1
    try:
        report = run_probe(evidence_root=args.evidence_root)
    except Exception as exc:
        report = {"outcome": "FAIL", "failure_kind": "startup", "failure_detail": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(report, sort_keys=True))
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(report.get("outcome"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
