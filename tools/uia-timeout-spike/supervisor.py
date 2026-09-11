"""Bounded parent supervisor for the read-only Windows UIA worker spike.

The parent never imports UIA/COM. It starts the owned helper with the fixed
interpreter, captures both streams in files, and bounds readiness, execution,
and cleanup independently. ``worker_script`` is injectable only so Linux tests
can exercise real child-process behavior; the CLI defaults to worker.py.
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


def validate_deadline(value: float, name: str) -> float:
    """Return a finite, strictly positive timeout or reject it."""
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


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
    stdout_path: str = ""
    stderr_path: str = ""
    result_path: str = ""
    stdout: str = ""
    stderr: str = ""
    child_payload: dict[str, Any] = field(default_factory=dict)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    return process.poll() is not None


def _cleanup(
    process: subprocess.Popen[bytes],
    terminate_timeout: float,
    kill_timeout: float,
) -> tuple[bool, bool, bool]:
    """Use finite terminate/kill/wait stages and report their observations."""
    terminate_sent = False
    kill_sent = False
    if process.poll() is None:
        terminate_sent = True
        try:
            process.terminate()
        except OSError:
            pass
        _wait_for_exit(process, terminate_timeout)
    if process.poll() is None:
        kill_sent = True
        try:
            process.kill()
        except OSError:
            pass
        _wait_for_exit(process, kill_timeout)
    return process.poll() is not None, terminate_sent, kill_sent


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

    ``Popen`` creation is intentionally not claimed to be bounded: Python's
    timeout starts after spawn. The measured spawn duration is recorded.
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
        result = SupervisionResult(status="FAIL", failure_kind="spawn", detail=str(exc), **base)
        _write_result(result_path, result)
        return result
    spawn_elapsed = time.monotonic() - spawn_started

    timed_out = False
    timeout_phase: str | None = None
    failure_kind: str | None = None
    deadline = time.monotonic() + readiness_timeout
    ready = False
    while process.poll() is None and time.monotonic() < deadline:
        data, capped = _read_bytes_capped(stdout_path, output_cap)
        if capped:
            failure_kind = "output_cap"
            break
        _, ready = _payload_from_stdout(data)
        if ready:
            break
        time.sleep(min(0.01, max(0.001, deadline - time.monotonic())))
    if failure_kind is None and not ready and process.poll() is None:
        timed_out = True
        timeout_phase = "readiness"
    if failure_kind is None and not timed_out and ready and process.poll() is None:
        deadline = time.monotonic() + execution_timeout
        while process.poll() is None and time.monotonic() < deadline:
            data, capped = _read_bytes_capped(stdout_path, output_cap)
            if capped:
                failure_kind = "output_cap"
                break
            time.sleep(min(0.01, max(0.001, deadline - time.monotonic())))
        if failure_kind is None and process.poll() is None:
            timed_out = True
            timeout_phase = "execution"

    cleanup_verified = True
    terminate_sent = False
    kill_sent = False
    if process.poll() is None:
        cleanup_verified, terminate_sent, kill_sent = _cleanup(process, terminate_timeout, kill_timeout)
    else:
        cleanup_verified = process.poll() is not None
    returncode = process.poll()

    stdout_data, stdout_capped = _read_bytes_capped(stdout_path, output_cap)
    stderr_data, stderr_capped = _read_bytes_capped(stderr_path, output_cap)
    payload, ready_at_end = _payload_from_stdout(stdout_data)
    if stdout_capped or stderr_capped:
        failure_kind = "output_cap"
    if not timed_out and failure_kind is None:
        if returncode != 0:
            failure_kind = "child_exit"
        elif not ready_at_end:
            failure_kind = "protocol"
        elif payload.get("status") != "PASS":
            failure_kind = "child_result"

    if timed_out:
        status = "TIMEOUT"
    elif not cleanup_verified:
        status = "FAIL"
        failure_kind = failure_kind or "cleanup_uncertain"
    elif failure_kind is not None:
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
        stdout=_text(stdout_data),
        stderr=_text(stderr_data),
        child_payload=payload,
        detail=("cleanup uncertain" if not cleanup_verified else ""),
        **base,
    )
    _write_result(result_path, result)
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
    parser.add_argument("--worker-script", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    injected = args.worker_script is not None
    target_values = (args.hwnd, args.pid, args.create_time, args.exe)
    if not injected and any(value is None for value in target_values):
        print(json.dumps({"status": "FAIL", "failure_kind": "target_args"}))
        return 1
    worker_args: list[str] = []
    if not injected:
        worker_args = [
            "--hwnd", args.hwnd,
            "--pid", args.pid,
            "--create-time", args.create_time,
            "--exe", args.exe,
        ]
    try:
        result = run_supervised(
            output_dir=args.output_dir,
            worker_script=args.worker_script or OWNED_WORKER,
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
