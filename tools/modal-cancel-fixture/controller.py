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
import math
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


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a strict bool")
    return value


def _strict_int(value: Any, name: str, *, maximum: int, positive: bool = False) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be a raw Python int")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if value < 0 or value > maximum:
        raise ValueError(f"{name} is outside its accepted range")
    return value


def _strict_float(value: Any, name: str, *, positive: bool = False) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite raw Python float")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _validate_fixture_snapshot(
    state: dict[str, Any], counters: dict[str, Any], expected: tuple[int, float, str], nonce: str,
    *, expected_phase: str | None = None, expected_dialog_open: bool | None = None,
    expected_dialog_closed: bool | None = None, expected_cancel_count: int | None = None,
    expected_yes_count: int | None = None, expected_parent_pid: int | None = None,
) -> None:
    """Validate one complete, typed fixture snapshot before using its values."""
    required = {
        "nonce", "parent_pid", "pid", "create_time", "executable", "hwnd", "qt_version",
        "qt_platform", "main_title", "dialog_title", "dialog_body", "heartbeat", "phase",
        "dialog_open", "dialog_closed", "cancel_count", "yes_count", "monotonic",
    }
    missing = required.difference(state)
    if missing:
        raise ValueError(f"fixture state is missing fields: {sorted(missing)}")
    if set(counters) != {"cancel", "yes", "dialog_closed", "nonce"}:
        raise ValueError("fixture counters have an unexpected schema")

    pid = _strict_int(state["pid"], "state.pid", maximum=2**32 - 1, positive=True)
    parent_pid = _strict_int(state["parent_pid"], "state.parent_pid", maximum=2**32 - 1, positive=True)
    hwnd = _strict_int(state["hwnd"], "state.hwnd", maximum=2**64 - 1, positive=True)
    parent_expected = os.getpid() if expected_parent_pid is None else expected_parent_pid
    if pid != expected[0] or parent_pid != parent_expected or state["executable"] != expected[2]:
        raise ValueError("fixture state process identity does not match the owned launch")
    create_time = _strict_float(state["create_time"], "state.create_time", positive=True)
    if create_time != expected[1]:
        raise ValueError("fixture state create time does not match the owned launch")
    _strict_float(state["monotonic"], "state.monotonic", positive=True)
    _strict_int(state["heartbeat"], "state.heartbeat", maximum=2**64 - 1)
    if type(state["nonce"]) is not str or state["nonce"] != nonce:
        raise ValueError("fixture state nonce mismatch")
    if state["qt_version"] != "6.8.2":
        raise ValueError(f"unexpected Qt version: {state['qt_version']!r}")
    expected_platform = "windows" if os.name == "nt" else "offscreen"
    if state["qt_platform"] != expected_platform:
        raise ValueError(f"unexpected Qt platform: {state['qt_platform']!r}")
    if state["main_title"] != f"Modal Cancel Fixture Main {nonce}":
        raise ValueError("fixture main title nonce mismatch")
    if state["dialog_title"] != f"Modal Cancel Fixture {nonce}":
        raise ValueError("fixture dialog title nonce mismatch")
    if state["dialog_body"] != f"Benign modal cancellation test {nonce}":
        raise ValueError("fixture dialog body nonce mismatch")
    if type(state["phase"]) is not str or not state["phase"]:
        raise ValueError("fixture phase must be a non-empty string")
    if expected_phase is not None and state["phase"] != expected_phase:
        raise ValueError(f"fixture phase is not {expected_phase!r}")

    dialog_open = _strict_bool(state["dialog_open"], "state.dialog_open")
    dialog_closed = _strict_bool(state["dialog_closed"], "state.dialog_closed")
    cancel_count = _strict_int(state["cancel_count"], "state.cancel_count", maximum=1)
    yes_count = _strict_int(state["yes_count"], "state.yes_count", maximum=1)
    counter_cancel = _strict_int(counters["cancel"], "counters.cancel", maximum=1)
    counter_yes = _strict_int(counters["yes"], "counters.yes", maximum=1)
    counter_closed = _strict_bool(counters["dialog_closed"], "counters.dialog_closed")
    if counters["nonce"] != nonce or (cancel_count, yes_count) != (counter_cancel, counter_yes):
        raise ValueError("fixture state and counters disagree")
    if counter_closed != dialog_closed:
        raise ValueError("fixture closure fields disagree")
    if expected_dialog_open is not None and dialog_open != expected_dialog_open:
        raise ValueError("fixture dialog_open value is unexpected")
    if expected_dialog_closed is not None and dialog_closed != expected_dialog_closed:
        raise ValueError("fixture dialog_closed value is unexpected")
    if expected_cancel_count is not None and cancel_count != expected_cancel_count:
        raise ValueError("fixture cancel count is unexpected")
    if expected_yes_count is not None and yes_count != expected_yes_count:
        raise ValueError("fixture Yes count is unexpected")


def _validate_worker_action(payload: dict[str, Any], *, cancel_once: bool) -> None:
    action = payload["action"]
    if not isinstance(action, dict) or set(action) != {
        "cancel_attempted", "cancel_completed", "yes_attempted", "outcome",
    }:
        raise ValueError("worker action evidence has an unexpected schema")
    attempted = _strict_int(action["cancel_attempted"], "action.cancel_attempted", maximum=1)
    completed = _strict_int(action["cancel_completed"], "action.cancel_completed", maximum=1)
    yes_attempted = _strict_int(action["yes_attempted"], "action.yes_attempted", maximum=1)
    outcome = action["outcome"]
    if type(outcome) is not str or outcome not in {"not_attempted", "completed", "unknown"}:
        raise ValueError("worker action outcome is not explicit")
    direct = _strict_bool(payload["direct_cancel_invoke"], "direct_cancel_invoke")
    direct_count = _strict_int(payload["direct_cancel_invoke_count"], "direct_cancel_invoke_count", maximum=1)
    yes_count = _strict_int(payload["yes_invoke_count"], "yes_invoke_count", maximum=1)
    if direct != bool(attempted) or direct_count != attempted or yes_count != 0 or yes_attempted != 0:
        raise ValueError("worker direct action counters disagree")
    expected = (1, 1, "completed") if cancel_once else (0, 0, "not_attempted")
    if (attempted, completed, outcome) != expected:
        raise ValueError("worker action evidence does not match the requested mode")


def _validate_worker_observations(payload: dict[str, Any], state: dict[str, Any], nonce: str) -> None:
    observations = payload["observations"]
    if not isinstance(observations, dict):
        raise ValueError("worker observations are not an object")
    if not {"root", "dialog", "body", "buttons"}.issubset(observations):
        raise ValueError("worker observations are incomplete")
    buttons = observations["buttons"]
    if not isinstance(buttons, dict) or set(buttons) != {"Cancel", "Yes"}:
        raise ValueError("worker modal buttons are incomplete")

    dialog_id = f"QApplication.ModalCancelDialog_{nonce}"
    expected = {
        "root": (state["main_title"], "QMainWindow", "Window",
                 f"QApplication.ModalCancelFixtureMain_{nonce}"),
        "dialog": (state["dialog_title"], "QMessageBox", "Window", dialog_id),
        "body": (state.get("dialog_body", f"Benign modal cancellation test {nonce}"),
                 "QLabel", "Text", dialog_id + ".qt_msgbox_label"),
        "Cancel": ("Cancel", "QPushButton", "Button",
                    dialog_id + ".qt_msgbox_buttonbox.QPushButton"),
        "Yes": ("Yes", "QPushButton", "Button",
                 dialog_id + ".qt_msgbox_buttonbox.QPushButton"),
    }
    records = {
        "root": observations["root"], "dialog": observations["dialog"],
        "body": observations["body"], "Cancel": buttons["Cancel"], "Yes": buttons["Yes"],
    }
    aliases = (("process_id", "pid"), ("class_name", "class"),
               ("control_type", "controltype"), ("automation_id", "auto_id"),
               ("visible", "raw_visibility"), ("runtime_id", "runtime_ids"))
    for role, observed in records.items():
        if not isinstance(observed, dict):
            raise ValueError(f"worker {role} observation is not an object")
        expected_role = role if role in {"root", "dialog", "body"} else f"button.{role}"
        if "observation_role" in observed and observed["observation_role"] != expected_role:
            raise ValueError(f"worker {role} observation role mismatch")
        required = {"name", "process_id", "class_name", "control_type", "automation_id",
                    "visible", "runtime_id", "hwnd"}
        missing = required.difference(observed)
        if missing:
            raise ValueError(f"worker {role} observation is missing fields: {sorted(missing)}")
        if type(observed["name"]) is not str:
            raise ValueError(f"worker {role}.name must be a raw string")
        pid = _strict_int(observed["process_id"], f"worker {role}.process_id",
                          maximum=2**32 - 1, positive=True)
        for field in ("class_name", "control_type", "automation_id"):
            if type(observed[field]) is not str:
                raise ValueError(f"worker {role}.{field} must be a raw string")
        visibility = observed["visible"]
        if not (type(visibility) is bool or (type(visibility) is int and visibility in (0, 1))):
            raise ValueError(f"worker {role}.visible is not canonical")
        if visibility is not True and visibility != 1:
            raise ValueError(f"worker {role} is not visible")
        runtime = observed["runtime_id"]
        if type(runtime) is not list or not runtime:
            raise ValueError(f"worker {role}.runtime_id is not a non-empty list")
        if any(type(component) is not int or not -(2**31) <= component <= 2**31 - 1
               for component in runtime):
            raise ValueError(f"worker {role}.runtime_id is not signed 32-bit")
        if role in {"root", "dialog"}:
            hwnd = _strict_int(observed["hwnd"], f"worker {role}.hwnd",
                               maximum=2**64 - 1, positive=True)
            owner = _strict_int(observed.get("native_owner_pid"),
                                f"worker {role}.native_owner_pid",
                                maximum=2**32 - 1, positive=True)
            if owner != state["pid"]:
                raise ValueError(f"worker {role} native owner PID mismatch")
        elif observed["hwnd"] is not None:
            raise ValueError(f"worker {role} HWND must be absent for a Qt alien control")
        elif "native_owner_pid" in observed:
            raise ValueError(f"worker {role} must not report a native owner PID")
        if (observed["name"], observed["class_name"], observed["control_type"],
                observed["automation_id"]) != expected[role]:
            raise ValueError(f"worker {role} is not the pinned Qt identity")
        if pid != state["pid"]:
            raise ValueError(f"worker {role} PID mismatch")
        for canonical, alias in aliases:
            if alias not in observed:
                continue
            alias_value = observed[alias]
            if canonical in {"process_id"}:
                _strict_int(alias_value, f"worker {role}.{alias}",
                            maximum=2**32 - 1, positive=True)
            elif canonical == "visible":
                if not (type(alias_value) is bool or
                        (type(alias_value) is int and alias_value in (0, 1))):
                    raise ValueError(f"worker {role}.{alias} is not canonical")
            elif canonical == "runtime_id":
                if type(alias_value) is not list or not alias_value:
                    raise ValueError(f"worker {role}.{alias} is not a non-empty list")
                if any(type(component) is not int or not -(2**31) <= component <= 2**31 - 1
                       for component in alias_value):
                    raise ValueError(f"worker {role}.{alias} is not signed 32-bit")
            elif type(alias_value) is not str:
                raise ValueError(f"worker {role}.{alias} must be a raw string")
            if alias_value != observed[canonical]:
                raise ValueError(f"worker {role}.{alias} disagrees with {canonical}")
    if len({tuple(records[name]["runtime_id"]) for name in ("Cancel", "Yes")}) != 2:
        raise ValueError("modal buttons do not have distinct RuntimeIds")
    if records["root"]["hwnd"] != state["hwnd"]:
        raise ValueError("worker root HWND does not match fixture state")


def _validate_native_acceptance(
    result: Any, state: dict[str, Any], counters: dict[str, Any], nonce: str,
    *, fixture_postcheck_verified: bool, cancel_once: bool,
) -> bool:
    """Return true only for a complete, explicitly opted-in one-Cancel result."""
    try:
        if not cancel_once or fixture_postcheck_verified is not True:
            return False
        if result.status != "SUCCESS" or result.success is not True or result.cleanup_verified is not True:
            return False
        if type(result.secondary_errors) is not list or result.secondary_errors:
            return False
        payload = result.child_payload
        if not isinstance(payload, dict) or payload.get("status") != "PASS":
            return False
        if payload.get("captured_readonly") is not False or payload.get("native_acceptance") is not True:
            return False
        if _strict_bool(payload["modal_absent"], "modal_absent") is not True:
            return False
        if _strict_bool(payload["post_identity_verified"], "post_identity_verified") is not True:
            return False
        _validate_fixture_snapshot(
            state, counters, (state["pid"], state["create_time"], state["executable"]), nonce,
            expected_phase="cancelled", expected_dialog_open=False, expected_dialog_closed=True,
            expected_cancel_count=1, expected_yes_count=0,
        )
        _validate_worker_action(payload, cancel_once=True)
        _validate_worker_observations(payload, state, nonce)
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _validate_readonly_block(payload: dict[str, Any], state: dict[str, Any], counters: dict[str, Any], nonce: str) -> bool:
    try:
        if payload.get("status") != "BLOCKED":
            return False
        if payload.get("captured_readonly") is not True or payload.get("native_acceptance") is not False:
            return False
        if _strict_bool(payload["modal_absent"], "modal_absent") is not False:
            return False
        if _strict_bool(payload["post_identity_verified"], "post_identity_verified") is not False:
            return False
        _validate_fixture_snapshot(
            state, counters, (state["pid"], state["create_time"], state["executable"]), nonce,
            expected_phase="dialog_open", expected_dialog_open=True, expected_dialog_closed=False,
            expected_cancel_count=0, expected_yes_count=0,
        )
        _validate_worker_action(payload, cancel_once=False)
        _validate_worker_observations(payload, state, nonce)
        return True
    except (KeyError, TypeError, ValueError):
        return False


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


def _common_fixture_checks(
    root: Path, expected: tuple[int, float, str], process: subprocess.Popen[bytes], nonce: str,
    *, expected_phase: str | None = None, expected_dialog_open: bool | None = None,
    expected_dialog_closed: bool | None = None, expected_cancel_count: int | None = None,
    expected_yes_count: int | None = None,
) -> dict[str, Any]:
    state = _read_json(root / "state.json")
    counters = _read_json(root / "counters.json")
    if process.poll() is not None:
        raise RuntimeError("fixture is not live during identity verification")
    live = _owned_identity(process)
    if live != expected:
        raise RuntimeError("fixture live identity changed")
    try:
        _validate_fixture_snapshot(
            state, counters, expected, nonce, expected_phase=expected_phase,
            expected_dialog_open=expected_dialog_open, expected_dialog_closed=expected_dialog_closed,
            expected_cancel_count=expected_cancel_count, expected_yes_count=expected_yes_count,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"fixture snapshot validation failed: {exc}") from exc
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


def run_native(output_root: Path, *, cancel_once: bool = False) -> dict[str, Any]:
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
        checks = _common_fixture_checks(
            root, expected, process, nonce, expected_phase="dialog_open",
            expected_dialog_open=True, expected_dialog_closed=False,
            expected_cancel_count=0, expected_yes_count=0,
        )
        state = checks["state"]
        if _native_owner_pid(int(state["hwnd"])) != expected[0]:
            raise RuntimeError("fixture HWND owner mismatch before supervisor")
        sentinel = (root / "sentinel.bin").read_bytes()
        before_hash = hashlib.sha256(sentinel).hexdigest()
        report["sentinel"]["before_sha256"] = before_hash
        supervisor = _load_supervisor()
        supervisor_error = None
        try:
            worker_args = [
                "--pid", str(expected[0]), "--create-time", str(expected[1]), "--exe", expected[2],
                "--hwnd", str(state["hwnd"]), "--nonce", nonce, "--root", str(root),
                "--output-dir", str(run_dir / "uia-worker"), "--main-title", state["main_title"],
                "--dialog-title", state["dialog_title"], "--dialog-body", state["dialog_body"],
            ]
            if cancel_once:
                worker_args.append("--cancel-once")
            result = supervisor.run_supervised(
                output_dir=run_dir / "uia-supervisor", worker_script=WORKER,
                worker_args=tuple(worker_args),
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
                checks = _common_fixture_checks(
                    root, expected, process, nonce,
                    expected_phase="cancelled" if cancel_once else "dialog_open",
                    expected_dialog_open=not cancel_once, expected_dialog_closed=cancel_once,
                    expected_cancel_count=1 if cancel_once else 0, expected_yes_count=0,
                )
                if checks["state"]["hwnd"] != state["hwnd"]:
                    raise RuntimeError("fixture main HWND changed after supervisor")
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
        sentinel_unchanged = before_hash == after_hash and after == sentinel
        native_pass = (sentinel_unchanged and _validate_native_acceptance(
            result, state, counters, nonce,
            fixture_postcheck_verified=report.get("fixture_postcheck_verified") is True,
            cancel_once=cancel_once,
        ))
        readonly_partial = (
            not cancel_once and sentinel_unchanged and result.cleanup_verified is True and
            report.get("fixture_postcheck_verified") is True and
            type(result.secondary_errors) is list and not result.secondary_errors and
            _validate_readonly_block(payload, state, counters, nonce)
        )
        if result.cleanup_verified is not True:
            outcome = "FAIL"
        elif native_pass:
            outcome = "PASS"
        elif readonly_partial:
            outcome = "PARTIAL"
        else:
            outcome = "FAIL"
        report.update({"status": outcome,
                       "native_acceptance": native_pass, "supervisor": result.to_dict(),
                       "cancel_once": cancel_once,
                       "direct_cancel_invoke": payload.get("direct_cancel_invoke"),
                       "direct_cancel_invoke_count": payload.get("direct_cancel_invoke_count"),
                       "yes_invoke_count": payload.get("yes_invoke_count"),
                       "action": payload.get("action"),
                       "sentinel": {"before_sha256": before_hash, "after_sha256": after_hash, "unchanged": sentinel_unchanged},
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
    parser.add_argument("--cancel-once", action="store_true",
                        help="explicitly opt in to one native Cancel Invoke")
    args = parser.parse_args(argv)
    if os.name != "nt":
        args.evidence_root.mkdir(parents=True, exist_ok=True)
        run_dir = args.evidence_root.resolve() / ("blocked-" + _nonce())
        run_dir.mkdir()
        report = {"status": "BLOCKED", "native_acceptance": False, "reason": "controller is Windows-only", "run_dir": str(run_dir)}
        _atomic_json(run_dir / "final-report.json", report)
        print(json.dumps(report, sort_keys=True))
        return 2
    report = run_native(args.evidence_root, cancel_once=args.cancel_once)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS" else (2 if report["status"] == "PARTIAL" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
