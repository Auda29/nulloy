"""Bounded parent supervisor for the read-only Windows UIA worker spike.

The parent never imports UIA/COM. It starts the owned helper with the fixed
interpreter, captures both streams in files, and bounds readiness, execution,
and cleanup independently. ``worker_script`` is a trusted test-only API seam;
the operational CLI always uses the owned worker and exposes no replacement
script option.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


READY_EVENT = "event"
READY_VALUE = "ready"
DEFAULT_OUTPUT_CAP = 1_048_576
OWNED_WORKER = Path(__file__).with_name("worker.py")


class DiagnosticReadError(RuntimeError):
    """A live diagnostic stream could not be read."""


class ProcessPollError(RuntimeError):
    """A process-state inspection failed."""


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
    spawn_elapsed_s: float = 0.0
    supervision_elapsed_s: float = 0.0
    readiness_deadline_s: float = 0.0
    execution_deadline_s: float = 0.0
    stdout_path: str = ""
    stderr_path: str = ""
    result_path: str = ""
    stdout: str = ""
    stderr: str = ""
    child_payload: dict[str, Any] = field(default_factory=dict)
    primary_error: str = ""
    secondary_errors: list[str] = field(default_factory=list)
    result_write_error: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_deadline(value: float, name: str) -> float:
    """Return a finite, strictly positive timeout or reject it."""
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _read_bytes_capped(path: Path, cap: int) -> tuple[bytes, bool]:
    with path.open("rb") as stream:
        data = stream.read(cap + 1)
    return data[:cap], len(data) > cap


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _payload_from_stdout(data: bytes) -> tuple[dict[str, Any], bool]:
    payload: dict[str, Any] = {}
    ready = False
    for raw_line in data.splitlines():
        try:
            value = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get(READY_EVENT) == READY_VALUE:
            ready = True
        elif "status" in value:
            payload = value
    return payload, ready


def _wait_for_exit(process: subprocess.Popen[bytes], timeout: float) -> bool:
    """Wait at most timeout seconds; return whether the child exited."""
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


def _cached_returncode(process: subprocess.Popen[bytes]) -> int | None:
    """Read Popen's cached return code without another poll inspection."""
    try:
        return process.returncode
    except Exception:
        return None


def _poll_or_raise(process: subprocess.Popen[bytes]) -> int | None:
    try:
        return process.poll()
    except Exception as exc:
        raise ProcessPollError(f"process poll failed: {type(exc).__name__}: {exc}") from exc


def _cleanup(
    process: subprocess.Popen[bytes],
    terminate_timeout: float,
    kill_timeout: float,
) -> tuple[bool, bool, bool, list[str]]:
    """Use finite terminate/kill/wait stages, even when a wait raises."""
    terminate_sent = False
    kill_sent = False
    errors: list[str] = []
    try:
        returncode = process.poll()
    except Exception as exc:
        errors.append(f"cleanup poll failed: {type(exc).__name__}: {exc}")
        returncode = _cached_returncode(process)
    exited = returncode is not None
    if not exited:
        terminate_sent = True
        try:
            process.terminate()
        except Exception as exc:
            errors.append(f"terminate failed: {type(exc).__name__}: {exc}")
        try:
            exited = _wait_for_exit(process, terminate_timeout)
        except Exception as exc:
            errors.append(f"terminate wait failed: {type(exc).__name__}: {exc}")
            exited = False
    if not exited:
        kill_sent = True
        try:
            process.kill()
        except Exception as exc:
            errors.append(f"kill failed: {type(exc).__name__}: {exc}")
        try:
            exited = _wait_for_exit(process, kill_timeout)
        except Exception as exc:
            errors.append(f"kill wait failed: {type(exc).__name__}: {exc}")
            exited = False
    if not exited:
        returncode = _cached_returncode(process)
        if returncode is not None:
            exited = True
        else:
            try:
                exited = process.poll() is not None
            except Exception as exc:
                errors.append(f"cleanup verification poll failed: {type(exc).__name__}: {exc}")
    return exited, terminate_sent, kill_sent, errors


def _read_live_streams(stdout_path: Path, stderr_path: Path, cap: int) -> tuple[bytes, bool, bytes, bool]:
    """Read both live files; a read error is a primary supervision failure."""
    try:
        stdout_data, stdout_capped = _read_bytes_capped(stdout_path, cap)
    except Exception as exc:
        raise DiagnosticReadError(f"stdout diagnostic read failed: {exc}") from exc
    try:
        stderr_data, stderr_capped = _read_bytes_capped(stderr_path, cap)
    except Exception as exc:
        raise DiagnosticReadError(f"stderr diagnostic read failed: {exc}") from exc
    return stdout_data, stdout_capped, stderr_data, stderr_capped


def _read_final_stream(path: Path, cap: int, label: str) -> tuple[bytes, bool, str | None]:
    try:
        data, capped = _read_bytes_capped(path, cap)
    except Exception as exc:
        return b"", False, f"{label} final diagnostic read failed: {type(exc).__name__}: {exc}"
    return data, capped, None


def _write_result_safely(path: Path, result: SupervisionResult) -> None:
    try:
        _write_result(path, result)
    except Exception as exc:
        error = f"result write failed: {type(exc).__name__}: {exc}"
        result.result_write_error = error
        result.secondary_errors.append(error)
        result.status = "FAIL"
        result.success = False
        if result.failure_kind is None:
            result.failure_kind = "result_write"


def _write_result(path: Path, result: SupervisionResult) -> None:
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    """Run one exact helper process and return a serializable verdict.

    ``worker_script`` and ``worker_args`` are a trusted test-only seam for
    real Linux child-process fixtures, not a security sandbox. The public CLI
    calls this function only with ``OWNED_WORKER`` and fixed target arguments.
    Popen creation is intentionally not claimed to be bounded: the measured
    spawn duration is recorded and all post-spawn stages are finite.
    """
    readiness_timeout = validate_deadline(readiness_timeout, "readiness_timeout")
    execution_timeout = validate_deadline(execution_timeout, "execution_timeout")
    terminate_timeout = validate_deadline(terminate_timeout, "terminate_timeout")
    kill_timeout = validate_deadline(kill_timeout, "kill_timeout")
    if not isinstance(output_cap, int) or isinstance(output_cap, bool) or output_cap <= 0:
        raise ValueError("output_cap must be a positive integer")

    run_dir = Path(output_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = (run_dir / "stdout.txt").resolve()
    stderr_path = (run_dir / "stderr.txt").resolve()
    result_path = (run_dir / "result.json").resolve()
    script = Path(worker_script).resolve()
    command = [sys.executable, str(script), *[str(arg) for arg in worker_args]]
    base = dict(stdout_path=str(stdout_path), stderr_path=str(stderr_path), result_path=str(result_path))

    process: subprocess.Popen[bytes] | None = None
    spawn_started = time.monotonic()
    try:
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                shell=False,
                close_fds=True,
            )
    except (OSError, ValueError) as exc:
        result = SupervisionResult(status="FAIL", failure_kind="spawn", primary_error=str(exc), **base)
        _write_result_safely(result_path, result)
        return result
    spawn_elapsed = time.monotonic() - spawn_started

    started = time.monotonic()
    timed_out = False
    timeout_phase: str | None = None
    failure_kind: str | None = None
    primary_error = ""
    secondary_errors: list[str] = []
    ready = False
    stdout_data = b""
    stderr_data = b""
    stdout_capped = False
    stderr_capped = False
    cleanup_verified = True
    terminate_sent = False
    kill_sent = False
    cleanup_errors: list[str] = []

    try:
        readiness_deadline = time.monotonic() + readiness_timeout
        while _poll_or_raise(process) is None and time.monotonic() < readiness_deadline:
            stdout_data, stdout_capped, stderr_data, stderr_capped = _read_live_streams(
                stdout_path, stderr_path, output_cap
            )
            if stdout_capped or stderr_capped:
                failure_kind = "output_cap"
                break
            _, ready = _payload_from_stdout(stdout_data)
            if ready:
                break
            time.sleep(min(0.01, max(0.001, readiness_deadline - time.monotonic())))
        if failure_kind is None and not ready and _poll_or_raise(process) is None:
            timed_out = True
            timeout_phase = "readiness"
        if failure_kind is None and not timed_out and ready and _poll_or_raise(process) is None:
            execution_deadline = time.monotonic() + execution_timeout
            while _poll_or_raise(process) is None and time.monotonic() < execution_deadline:
                stdout_data, stdout_capped, stderr_data, stderr_capped = _read_live_streams(
                    stdout_path, stderr_path, output_cap
                )
                if stdout_capped or stderr_capped:
                    failure_kind = "output_cap"
                    break
                time.sleep(min(0.01, max(0.001, execution_deadline - time.monotonic())))
            if failure_kind is None and _poll_or_raise(process) is None:
                timed_out = True
                timeout_phase = "execution"
    except ProcessPollError as exc:
        failure_kind = "supervision"
        primary_error = str(exc)
    except DiagnosticReadError as exc:
        failure_kind = "diagnostic_read"
        primary_error = str(exc)
    except Exception as exc:
        failure_kind = "supervision"
        primary_error = f"{type(exc).__name__}: {exc}"
    finally:
        cleanup_verified, terminate_sent, kill_sent, cleanup_errors = _cleanup(
            process, terminate_timeout, kill_timeout
        )

    stdout_data, stdout_capped, stdout_error = _read_final_stream(stdout_path, output_cap, "stdout")
    stderr_data, stderr_capped, stderr_error = _read_final_stream(stderr_path, output_cap, "stderr")
    for error in (stdout_error, stderr_error):
        if error:
            if not primary_error and failure_kind is None:
                failure_kind = "diagnostic_read"
                primary_error = error
            else:
                secondary_errors.append(error)
    secondary_errors.extend(cleanup_errors)
    payload, ready_at_end = _payload_from_stdout(stdout_data)

    if timed_out:
        if stdout_capped or stderr_capped:
            secondary_errors.append("output_cap observed after timeout primary")
        failure_kind = "timeout"
    elif stdout_capped or stderr_capped:
        if failure_kind is None:
            failure_kind = "output_cap"
    returncode = _cached_returncode(process)
    try:
        returncode = process.poll()
    except Exception as exc:
        error = f"final process poll failed: {type(exc).__name__}: {exc}"
        if primary_error or failure_kind is not None:
            secondary_errors.append(error)
        else:
            primary_error = error
            failure_kind = "supervision"

    if not primary_error and failure_kind is None:
        if returncode != 0:
            failure_kind = "child_exit"
        elif not ready_at_end:
            failure_kind = "protocol"
        elif payload.get("status") != "PASS":
            failure_kind = "child_result"

    if not cleanup_verified and not timed_out:
        failure_kind = failure_kind or "cleanup_uncertain"
    if timed_out:
        status = "TIMEOUT"
    elif failure_kind is not None or not cleanup_verified:
        status = "FAIL"
    else:
        status = "SUCCESS"

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
        spawn_elapsed_s=spawn_elapsed,
        supervision_elapsed_s=time.monotonic() - started,
        readiness_deadline_s=readiness_timeout,
        execution_deadline_s=execution_timeout,
        stdout=_text(stdout_data),
        stderr=_text(stderr_data),
        child_payload=payload,
        primary_error=primary_error,
        secondary_errors=secondary_errors,
        detail=("cleanup uncertain" if not cleanup_verified else ""),
        **base,
    )
    _write_result_safely(result_path, result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--hwnd")
    parser.add_argument("--pid")
    parser.add_argument("--create-time")
    parser.add_argument("--exe")
    parser.add_argument("--readiness-timeout", type=float, default=10.0)
    parser.add_argument("--execution-timeout", type=float, default=60.0)
    parser.add_argument("--terminate-timeout", type=float, default=2.0)
    parser.add_argument("--kill-timeout", type=float, default=2.0)
    parser.add_argument("--output-cap", type=int, default=DEFAULT_OUTPUT_CAP)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    target_values = (args.hwnd, args.pid, args.create_time, args.exe)
    if any(value is None for value in target_values):
        print(json.dumps({"status": "FAIL", "failure_kind": "target_args"}))
        return 1
    worker_args = [
        "--hwnd", args.hwnd,
        "--pid", args.pid,
        "--create-time", args.create_time,
        "--exe", args.exe,
    ]
    try:
        result = run_supervised(
            output_dir=args.output_dir,
            worker_script=OWNED_WORKER,
            worker_args=worker_args,
            readiness_timeout=args.readiness_timeout,
            execution_timeout=args.execution_timeout,
            terminate_timeout=args.terminate_timeout,
            kill_timeout=args.kill_timeout,
            output_cap=args.output_cap,
        )
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "failure_kind": "argument", "detail": str(exc)}))
        return 1
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.status == "SUCCESS" else (2 if result.status == "TIMEOUT" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
