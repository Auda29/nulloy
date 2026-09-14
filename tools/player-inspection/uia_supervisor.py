#!/usr/bin/env python3
"""Finite supervisor for one owned, read-only UIA query worker.

The parent process never imports pywinauto/COM.  UIA calls run in the fixed
sibling worker, whose process and file-backed diagnostics are independently
bounded.  ``worker_script`` is a trusted test-only seam for real hanging-child
fixtures; the operational CLI always uses the owned worker.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable


OWNED_WORKER = Path(__file__).with_name("uia_worker.py")
DEFAULT_OUTPUT_CAP = 1_048_576


@dataclass
class SupervisionResult:
    status: str
    success: bool = False
    failure_kind: str | None = None
    timeout_phase: str | None = None
    timed_out: bool = False
    cleanup_verified: bool = False
    terminate_sent: bool = False
    kill_sent: bool = False
    returncode: int | None = None
    stdout_path: str = ""
    stderr_path: str = ""
    result_path: str = ""
    stdout: str = ""
    stderr: str = ""
    child_payload: dict[str, Any] = field(default_factory=dict)
    target_before: dict[str, Any] = field(default_factory=dict)
    target_after: dict[str, Any] = field(default_factory=dict)
    primary_error: str = ""
    secondary_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _deadline(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _read(path: Path, cap: int) -> tuple[bytes, bool]:
    with path.open("rb") as stream:
        data = stream.read(cap + 1)
    return data[:cap], len(data) > cap


def _json_lines(data: bytes) -> tuple[dict[str, Any], bool, dict[str, Any], dict[str, Any]]:
    payload: dict[str, Any] = {}
    ready = False
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for line in data.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get("event") == "ready":
            ready = True
        elif value.get("event") == "target":
            before = dict(value.get("target") or {})
        elif value.get("event") == "post_target":
            after = dict(value.get("target") or {})
        elif "status" in value:
            payload = value
    return payload, ready, before, after


def _wait(process: subprocess.Popen[bytes], timeout: float) -> bool:
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


def _poll(process: subprocess.Popen[bytes]) -> int | None:
    try:
        return process.poll()
    except Exception as exc:
        raise RuntimeError(f"process poll failed: {type(exc).__name__}: {exc}") from exc


def _cleanup(process: subprocess.Popen[bytes], terminate_timeout: float, kill_timeout: float) -> tuple[bool, bool, bool, list[str]]:
    errors: list[str] = []
    terminate_sent = False
    kill_sent = False
    try:
        exited = process.poll() is not None
    except Exception as exc:
        errors.append(f"initial poll failed: {type(exc).__name__}: {exc}")
        exited = False
    if not exited:
        terminate_sent = True
        try:
            process.terminate()
        except Exception as exc:
            errors.append(f"terminate failed: {type(exc).__name__}: {exc}")
        try:
            exited = _wait(process, terminate_timeout)
        except Exception as exc:
            errors.append(f"terminate wait failed: {type(exc).__name__}: {exc}")
    if not exited:
        kill_sent = True
        try:
            process.kill()
        except Exception as exc:
            errors.append(f"kill failed: {type(exc).__name__}: {exc}")
        try:
            exited = _wait(process, kill_timeout)
        except Exception as exc:
            errors.append(f"kill wait failed: {type(exc).__name__}: {exc}")
    if not exited:
        try:
            exited = process.poll() is not None
        except Exception as exc:
            errors.append(f"final poll failed: {type(exc).__name__}: {exc}")
    return exited, terminate_sent, kill_sent, errors


def _write_result(path: Path, result: SupervisionResult) -> None:
    try:
        path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        result.status = "FAIL"
        result.success = False
        result.failure_kind = result.failure_kind or "result_write"
        result.secondary_errors.append(f"result write failed: {type(exc).__name__}: {exc}")


def run_supervised(
    *,
    output_dir: str | os.PathLike[str],
    worker_script: str | os.PathLike[str] = OWNED_WORKER,
    worker_args: Iterable[str] = (),
    readiness_timeout: float = 10.0,
    execution_timeout: float = 60.0,
    terminate_timeout: float = 2.0,
    kill_timeout: float = 2.0,
    output_cap: int = DEFAULT_OUTPUT_CAP,
) -> SupervisionResult:
    """Run one worker with finite post-spawn deadlines and owned cleanup."""
    readiness_timeout = _deadline(readiness_timeout, "readiness_timeout")
    execution_timeout = _deadline(execution_timeout, "execution_timeout")
    terminate_timeout = _deadline(terminate_timeout, "terminate_timeout")
    kill_timeout = _deadline(kill_timeout, "kill_timeout")
    if not isinstance(output_cap, int) or isinstance(output_cap, bool) or output_cap <= 0:
        raise ValueError("output_cap must be a positive integer")

    run_dir = Path(output_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    result_path = run_dir / "result.json"
    command = [sys.executable, str(Path(worker_script).resolve()), *map(str, worker_args)]
    process: subprocess.Popen[bytes] | None = None
    primary_error = ""
    secondary_errors: list[str] = []
    failure_kind: str | None = None
    timeout_phase: str | None = None
    timed_out = False
    ready = False
    output_capped = False
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                close_fds=True,
            )
    except Exception as exc:
        result = SupervisionResult(
            status="FAIL", failure_kind="spawn", primary_error=f"{type(exc).__name__}: {exc}",
            stdout_path=str(stdout_path), stderr_path=str(stderr_path), result_path=str(result_path),
        )
        if process is not None:
            verified, terminated, killed, errors = _cleanup(process, terminate_timeout, kill_timeout)
            result.cleanup_verified = verified and not errors
            result.terminate_sent = terminated
            result.kill_sent = killed
            result.returncode = process.returncode
            result.secondary_errors.extend(errors)
        _write_result(result_path, result)
        return result

    stdout_data = b""
    stderr_data = b""
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    try:
        deadline = time.monotonic() + readiness_timeout
        while _poll(process) is None and time.monotonic() < deadline:
            stdout_data, out_cap = _read(stdout_path, output_cap)
            stderr_data, err_cap = _read(stderr_path, output_cap)
            output_capped |= out_cap or err_cap
            payload, ready, before, after = _json_lines(stdout_data)
            if output_capped or ready:
                break
            time.sleep(min(0.01, max(0.001, deadline - time.monotonic())))
        if output_capped:
            failure_kind = "output_cap"
        elif not ready and _poll(process) is None:
            timed_out = True
            timeout_phase = "readiness"
        if failure_kind is None and not timed_out and ready and _poll(process) is None:
            deadline = time.monotonic() + execution_timeout
            while _poll(process) is None and time.monotonic() < deadline:
                stdout_data, out_cap = _read(stdout_path, output_cap)
                stderr_data, err_cap = _read(stderr_path, output_cap)
                output_capped |= out_cap or err_cap
                payload, ready, before, after = _json_lines(stdout_data)
                if output_capped:
                    failure_kind = "output_cap"
                    break
                time.sleep(min(0.01, max(0.001, deadline - time.monotonic())))
            if failure_kind is None and _poll(process) is None:
                timed_out = True
                timeout_phase = "execution"
    except Exception as exc:
        failure_kind = "supervision"
        primary_error = f"{type(exc).__name__}: {exc}"
    finally:
        cleanup_verified, terminate_sent, kill_sent, cleanup_errors = _cleanup(
            process, terminate_timeout, kill_timeout
        )
        secondary_errors.extend(cleanup_errors)
        cleanup_verified = cleanup_verified and not cleanup_errors

    try:
        stdout_data, out_cap = _read(stdout_path, output_cap)
        stderr_data, err_cap = _read(stderr_path, output_cap)
        output_capped |= out_cap or err_cap
    except Exception as exc:
        secondary_errors.append(f"final diagnostic read failed: {type(exc).__name__}: {exc}")
        failure_kind = failure_kind or "diagnostic_read"
        stdout_data = stdout_data or b""
        stderr_data = stderr_data or b""
    payload, ready, before, after = _json_lines(stdout_data)
    if timed_out:
        failure_kind = "timeout"
    elif output_capped and failure_kind is None:
        failure_kind = "output_cap"
    try:
        returncode = _poll(process)
    except Exception as exc:
        secondary_errors.append(str(exc))
        returncode = None
    if failure_kind is None:
        if returncode != 0:
            failure_kind = "child_exit"
        elif not ready:
            failure_kind = "protocol"
        elif payload.get("status") != "PASS":
            failure_kind = "child_result"
    if not cleanup_verified:
        failure_kind = failure_kind or "cleanup_uncertain"
    status = "FAIL" if not cleanup_verified or failure_kind not in (None, "timeout") else ("TIMEOUT" if timed_out else "SUCCESS")
    result = SupervisionResult(
        status=status,
        success=status == "SUCCESS",
        failure_kind=failure_kind,
        timeout_phase=timeout_phase,
        timed_out=timed_out,
        cleanup_verified=cleanup_verified,
        terminate_sent=terminate_sent,
        kill_sent=kill_sent,
        returncode=returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        result_path=str(result_path),
        stdout=stdout_data.decode("utf-8", errors="replace"),
        stderr=stderr_data.decode("utf-8", errors="replace"),
        child_payload=payload,
        target_before=before,
        target_after=after,
        primary_error=primary_error,
        secondary_errors=secondary_errors,
    )
    _write_result(result_path, result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--hwnd", required=True)
    parser.add_argument("--pid", required=True)
    parser.add_argument("--create-time", required=True)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--expected-rows", required=True, help="exact three playlist labels as a JSON array")
    parser.add_argument("--readiness-timeout", type=float, default=10.0)
    parser.add_argument("--execution-timeout", type=float, default=60.0)
    parser.add_argument("--terminate-timeout", type=float, default=2.0)
    parser.add_argument("--kill-timeout", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_supervised(
        output_dir=args.output_dir,
        worker_script=OWNED_WORKER,
        worker_args=("--hwnd", args.hwnd, "--pid", args.pid, "--create-time", args.create_time,
                     "--exe", args.exe, "--expected-rows", args.expected_rows),
        readiness_timeout=args.readiness_timeout,
        execution_timeout=args.execution_timeout,
        terminate_timeout=args.terminate_timeout,
        kill_timeout=args.kill_timeout,
    )
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.status == "SUCCESS" else (2 if result.status == "TIMEOUT" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
