"""Fixed-path controller for the harmless modal Cancel fixture.

The public CLI is Windows-only and launches only this fixture plus the fixed
worker through the reviewed existing supervisor. Linux uses only the explicit
internal Qt test seam; it never claims native UIA acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Any, Callable

import psutil

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture.py"
WORKER = HERE / "worker.py"
SUPERVISOR = HERE.parent / "player-inspection" / "uia_supervisor.py"


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _nonce() -> str:
    return "modal-" + secrets.token_hex(10)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} is not an object")
    return value


def _await_state(process: subprocess.Popen[bytes], path: Path, predicate: Callable[[dict[str, Any]], bool], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last = "state condition not met"
    while time.monotonic() < deadline:
        if path.exists():
            try:
                state = _read_json(path)
                if predicate(state):
                    return state
                last = f"phase={state.get('phase')!r}, heartbeat={state.get('heartbeat')!r}"
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                last = f"state read failed: {type(exc).__name__}: {exc}"
        returncode = process.poll()
        if returncode is not None:
            raise RuntimeError(f"fixture exited before state condition ({returncode}): {last}")
        time.sleep(0.025)
    raise TimeoutError(last)


def _owned_identity(process: subprocess.Popen[bytes]) -> tuple[int, float, str]:
    live = psutil.Process(process.pid)
    return int(live.pid), float(live.create_time()), str(live.exe())


def _cleanup(process: subprocess.Popen[bytes], terminate_timeout: float = 1.0, kill_timeout: float = 1.0) -> dict[str, Any]:
    errors: list[str] = []
    terminate_sent = kill_sent = False
    try:
        exited = process.poll() is not None
    except Exception as exc:
        exited = False
        errors.append(f"initial poll failed: {type(exc).__name__}: {exc}")
    if not exited:
        terminate_sent = True
        try:
            process.terminate()
            process.wait(timeout=terminate_timeout)
            exited = True
        except subprocess.TimeoutExpired:
            pass
        except Exception as exc:
            errors.append(f"terminate cleanup failed: {type(exc).__name__}: {exc}")
        if not exited:
            kill_sent = True
            try:
                process.kill()
                process.wait(timeout=kill_timeout)
                exited = True
            except Exception as exc:
                errors.append(f"kill cleanup failed: {type(exc).__name__}: {exc}")
    try:
        exited = process.poll() is not None
    except Exception as exc:
        errors.append(f"cleanup verification failed: {type(exc).__name__}: {exc}")
        exited = False
    return {"cleanup_verified": exited and not errors, "terminate_sent": terminate_sent,
            "kill_sent": kill_sent, "errors": errors}


def _start_fixture(run_dir: Path, nonce: str, *, test_seam: bool) -> tuple[subprocess.Popen[bytes], Path, tuple[int, float, str]]:
    root = (run_dir / "fixture-root").resolve()
    stdout = (run_dir / "fixture-stdout.txt").open("wb")
    stderr = (run_dir / "fixture-stderr.txt").open("wb")
    process: subprocess.Popen[bytes] | None = None
    try:
        env = os.environ.copy()
        if os.name == "nt":
            for key in ('MODAL_CANCEL_FIXTURE_TEST_SEAM', 'MODAL_CANCEL_FIXTURE_TEST_FAIL_CALLBACK', 'QT_QPA_PLATFORM'):
                env.pop(key, None)
            if test_seam:
                raise RuntimeError("internal Qt cancellation seam is Linux-only")
        if os.name != "nt":
            env["QT_QPA_PLATFORM"] = "offscreen"
        if test_seam:
            env["MODAL_CANCEL_FIXTURE_TEST_SEAM"] = "cancel"
        process = subprocess.Popen(
            [sys.executable, str(FIXTURE), "--root", str(root), "--nonce", nonce, "--lifetime", "60"],
            cwd=str(HERE), env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            shell=False, close_fds=True,
        )
        # Handle closure and launch identity are post-spawn work and therefore
        # must remain inside the owned-child cleanup boundary.
        stdout.close()
        stderr.close()
        launch_identity = _owned_identity(process)
        return process, root, launch_identity
    except Exception:
        if process is not None:
            _cleanup(process)
        raise
    finally:
        for stream in (stdout, stderr):
            try:
                if not stream.closed:
                    stream.close()
            except Exception:
                # Preserve the primary spawn/identity/close exception. The
                # child was already handled above when it exists.
                pass


def _load_supervisor() -> Any:
    if not SUPERVISOR.is_file():
        raise RuntimeError(f"reviewed supervisor is missing: {SUPERVISOR}")
    name = f"modal_cancel_uia_supervisor_{secrets.token_hex(8)}"
    spec = importlib.util.spec_from_file_location(name, SUPERVISOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load reviewed UIA supervisor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _native_owner_pid(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_owner = user32.GetWindowThreadProcessId
    get_owner.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    get_owner.restype = wintypes.DWORD
    owner = wintypes.DWORD()
    if not get_owner(wintypes.HWND(hwnd), ctypes.byref(owner)) or not owner.value:
        raise RuntimeError(f"HWND has no live owner: {hwnd}")
    return int(owner.value)


def _common_fixture_checks(root: Path, expected: tuple[int, float, str], process: subprocess.Popen[bytes], nonce: str) -> dict[str, Any]:
    state = _read_json(root / "state.json")
    counters = _read_json(root / "counters.json")
    if process.poll() is not None:
        raise RuntimeError("fixture is not live during identity verification")
    live = _owned_identity(process)
    if live != expected:
        raise RuntimeError("fixture live identity changed")
    expected_state = {"parent_pid": os.getpid(), "pid": expected[0], "create_time": expected[1], "executable": expected[2], "nonce": nonce}
    for key, value in expected_state.items():
        if state.get(key) != value:
            raise RuntimeError(f"fixture state identity mismatch for {key}")
    if state.get("qt_version") != "6.8.2":
        raise RuntimeError(f"unexpected Qt version: {state.get('qt_version')!r}")
    if os.name != "nt" and state.get("qt_platform") != "offscreen":
        raise RuntimeError(f"unexpected Linux Qt platform: {state.get('qt_platform')!r}")
    return {"state": state, "counters": counters}


def run_internal_cancel(output_dir: Path) -> dict[str, Any]:
    """Trusted Linux-only seam that clicks the real Qt Cancel button internally."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / ("run-" + _nonce())
    run_dir.mkdir()
    stages: list[dict[str, Any]] = []
    _atomic_json(run_dir / "controller-stages.json", stages)
    nonce = _nonce()
    process: subprocess.Popen[bytes] | None = None
    report: dict[str, Any] = {"status": "FAIL", "native_acceptance": False, "direct_cancel_invoke_count": 0,
                              "run_dir": str(run_dir), "fixture": {},
                              "sentinel": {"before_sha256": None, "after_sha256": None, "unchanged": False},
                              "cleanup_verified": False}
    cleanup: dict[str, Any] = {"cleanup_verified": False, "errors": []}
    try:
        process, root, expected = _start_fixture(run_dir, nonce, test_seam=True)
        _await_state(process, root / "state.json", lambda value: value.get("phase") == "dialog_open", 4.0)
        sentinel = (root / "sentinel.bin").read_bytes()
        before_hash = hashlib.sha256(sentinel).hexdigest()
        _atomic_json(run_dir / "controller-stages.json", stages + [{"stage": "target_validated", "nonce": nonce}])
        state = _await_state(process, root / "state.json", lambda value: value.get("phase") == "cancelled", 4.0)
        checks = _common_fixture_checks(root, expected, process, nonce)
        state = checks["state"]
        counters = checks["counters"]
        after_bytes = (root / "sentinel.bin").read_bytes()
        after_hash = hashlib.sha256(after_bytes).hexdigest()
        passed = (state.get("dialog_closed") is True and state.get("cancel_count") == 1 and
                  state.get("yes_count") == 0 and counters == {"cancel": 1, "dialog_closed": True, "nonce": nonce, "yes": 0} and
                  before_hash == after_hash and sentinel == after_bytes)
        report.update({"status": "PASS" if passed else "FAIL", "native_acceptance": False,
                       "direct_cancel_invoke_count": 0,
                       "fixture": {"root": str(root), "pid": expected[0], "returncode": process.poll(),
                                   "phase": state.get("phase"), "cancel_count": state.get("cancel_count"),
                                   "yes_count": state.get("yes_count"), "dialog_closed": state.get("dialog_closed")},
                       "sentinel": {"before_sha256": before_hash, "after_sha256": after_hash, "unchanged": before_hash == after_hash and sentinel == after_bytes}})
    except Exception as exc:
        report.update({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        if process is not None:
            cleanup = _cleanup(process)
        report["cleanup_verified"] = cleanup["cleanup_verified"]
        report["cleanup"] = cleanup
        if not cleanup["cleanup_verified"]:
            report["status"] = "FAIL"
            report["native_acceptance"] = False
        _atomic_json(run_dir / "final-report.json", report)
    return report


def run_native(output_root: Path) -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "BLOCKED", "native_acceptance": False, "reason": "controller is Windows-only"}
    source_sha256 = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (Path(__file__), FIXTURE, WORKER, Path(__file__).resolve().parents[1] / 'player-inspection/uia_supervisor.py')}
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = output_root / ("run-" + _nonce())
    run_dir.mkdir()
    nonce = _nonce()
    process: subprocess.Popen[bytes] | None = None
    report: dict[str, Any] = {"status": "FAIL", "native_acceptance": False, "run_dir": str(run_dir),
                              "source_sha256": source_sha256,
                              "direct_cancel_invoke_count": 0,
                              "sentinel": {"before_sha256": None, "after_sha256": None, "unchanged": False}}
    cleanup: dict[str, Any] = {"cleanup_verified": False, "errors": []}
    sentinel: bytes | None = None
    root: Path | None = None
    try:
        process, root, expected = _start_fixture(run_dir, nonce, test_seam=False)
        _await_state(process, root / "state.json", lambda value: value.get("phase") == "dialog_open", 15.0)
        checks = _common_fixture_checks(root, expected, process, nonce)
        state = checks["state"]
        if _native_owner_pid(int(state["hwnd"])) != expected[0]:
            raise RuntimeError("fixture HWND owner mismatch before supervisor")
        sentinel = (root / "sentinel.bin").read_bytes()
        before_hash = hashlib.sha256(sentinel).hexdigest()
        report["sentinel"]["before_sha256"] = before_hash
        supervisor = _load_supervisor()
        supervisor_error = None
        try:
            result = supervisor.run_supervised(
                output_dir=run_dir / "uia-supervisor", worker_script=WORKER,
                worker_args=("--pid", str(expected[0]), "--create-time", str(expected[1]), "--exe", expected[2],
                             "--hwnd", str(state["hwnd"]), "--nonce", nonce, "--root", str(root),
                             "--output-dir", str(run_dir / "uia-worker"), "--main-title", state["main_title"],
                             "--dialog-title", state["dialog_title"], "--dialog-body", state["dialog_body"]),
                readiness_timeout=15.0, execution_timeout=30.0, terminate_timeout=2.0, kill_timeout=2.0,
            )
            # Freeze the child result before any identity/counter validation.
            report["supervisor"] = result.to_dict()
            _atomic_json(run_dir / "supervisor-result.json", report["supervisor"])
        except Exception as exc:
            supervisor_error = exc
            raise
        finally:
            try:
                # Never substitute the launch identity or kill before this check.
                checks = _common_fixture_checks(root, expected, process, nonce)
                if _native_owner_pid(int(state["hwnd"])) != expected[0]:
                    raise RuntimeError("fixture HWND owner mismatch after supervisor")
                report["fixture_postcheck_verified"] = True
            except Exception as exc:
                report["fixture_postcheck_verified"] = False
                report.setdefault("secondary_errors", []).append(f"fixture postcheck: {type(exc).__name__}: {exc}")
                if supervisor_error is None:
                    raise
        state = checks["state"]
        counters = checks["counters"]
        after = (root / "sentinel.bin").read_bytes()
        after_hash = hashlib.sha256(after).hexdigest()
        payload = result.child_payload if isinstance(result.child_payload, dict) else {}
        native_pass = (result.success and payload.get("status") == "PASS" and result.cleanup_verified and
                       state.get("dialog_closed") is True and counters.get("cancel") == 1 and counters.get("yes") == 0 and
                       before_hash == after_hash and after == sentinel)
        if not result.cleanup_verified:
            outcome = "FAIL"
        elif native_pass:
            outcome = "PASS"
        elif payload.get("status") == "BLOCKED":
            outcome = "PARTIAL"
        else:
            outcome = "FAIL"
        report.update({"status": outcome,
                       "native_acceptance": native_pass, "supervisor": result.to_dict(),
                       "direct_cancel_invoke_count": payload.get("direct_cancel_invoke_count", 0),
                       "sentinel": {"before_sha256": before_hash, "after_sha256": after_hash, "unchanged": before_hash == after_hash and after == sentinel},
                       "fixture": {"root": str(root), "cancel_count": counters.get("cancel"), "yes_count": counters.get("yes"), "dialog_closed": state.get("dialog_closed")}})
    except Exception as exc:
        report.update({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        if sentinel is not None and root is not None:
            try:
                with (root / "sentinel.bin").open("rb") as stream:
                    final_bytes = stream.read(len(sentinel) + 1)
                report["sentinel"]["after_sha256"] = hashlib.sha256(final_bytes).hexdigest()
                report["sentinel"]["unchanged"] = final_bytes == sentinel
                if final_bytes != sentinel:
                    raise RuntimeError("sentinel bytes changed")
            except Exception as exc:
                report.setdefault("secondary_errors", []).append(f"sentinel postcheck: {type(exc).__name__}: {exc}")
                report["status"] = "FAIL"
                report["native_acceptance"] = False
        if process is not None:
            cleanup = _cleanup(process)
        report["cleanup"] = cleanup
        report["cleanup_verified"] = cleanup["cleanup_verified"]
        if not cleanup["cleanup_verified"]:
            report["status"] = "FAIL"
            report["native_acceptance"] = False
        _atomic_json(run_dir / "final-report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if os.name != "nt":
        args.evidence_root.mkdir(parents=True, exist_ok=True)
        run_dir = args.evidence_root.resolve() / ("blocked-" + _nonce())
        run_dir.mkdir()
        report = {"status": "BLOCKED", "native_acceptance": False, "reason": "controller is Windows-only", "run_dir": str(run_dir)}
        _atomic_json(run_dir / "final-report.json", report)
        print(json.dumps(report, sort_keys=True))
        return 2
    report = run_native(args.evidence_root)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS" else (2 if report["status"] == "PARTIAL" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
