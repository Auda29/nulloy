"""Bounded Windows UIA worker for read-only discovery of one owned modal.

All pywinauto/UIA imports and calls stay in this child. Discovery records the
provider's observed identity without claiming native acceptance. Cancel Invoke
remains fail-closed until a separately reviewed native ControlType pin exists.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Callable

# Select the windowless MTA before importing pywinauto/comtypes on Windows.
sys.coinit_flags = 0

# Intentionally empty: no native action is reachable at this review stage.
PINNED_MODAL_CONTROL_TYPES: frozenset[str] = frozenset()
PINNED_MODAL_CLASS_NAME = "QMessageBox"
PINNED_MODAL_CONTROL_TYPE = "Window"
KNOWN_TRANSIENT_HRESULT = 0x80040201
MAX_DISCOVERY_ATTEMPTS = 2
DISCOVERY_RETRY_DELAY = 0.05
_MISSING = object()


class _BlockedObservation(ValueError):
    """A known safety/identity observation that must not become native action."""


class _WorkerFailure(RuntimeError):
    """Fatal failure carrying the partial read-only evidence for main()."""

    def __init__(self, message: str, *, observations: dict[str, Any], stages: list[dict[str, Any]],
                 output_dir: Path):
        super().__init__(message)
        self.observations = observations
        self.stages = stages
        self.output_dir = output_dir


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True), flush=True)


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _stage(path: Path, stages: list[dict[str, Any]], name: str, **details: Any) -> None:
    record = {"stage": name, "monotonic": time.monotonic(), **details}
    stages.append(record)
    _atomic_json(path, stages)
    _emit({"event": "stage", **record})


def _write_observations(output_dir: Path, observations: dict[str, Any]) -> None:
    _atomic_json(output_dir / "worker-observations.json", observations)


def _load_dependencies() -> tuple[Any, Any]:
    """Import and initialize the two native dependencies before ready."""
    import psutil
    from pywinauto import Desktop
    return psutil, Desktop


def _strict_int(value: Any, name: str, *, positive: bool = False) -> int:
    if type(value) is not int:  # bool and numeric strings are not identities.
        raise _BlockedObservation(f"{name} must be a raw Python int, not {type(value).__name__}")
    if positive and value <= 0:
        raise _BlockedObservation(f"{name} must be a positive raw Python int")
    return value


def _positive_raw_int(value: str, name: str) -> int:
    """Parse a command-line integer; provider fields use _strict_int instead."""
    if type(value) is not str:
        raise ValueError(f"{name} must be supplied as a raw integer string")
    try:
        parsed = int(value, 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive raw integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive raw integer")
    return parsed


def _raw(info: Any, field: str) -> Any:
    return getattr(info, field, _MISSING)


def _text(value: Any, name: str) -> str:
    if type(value) is not str:
        raise _BlockedObservation(f"{name} must be a raw string, not {type(value).__name__}")
    return value


def _canonical_visibility(value: Any) -> bool | int:
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return value
    raise _BlockedObservation("visibility must be canonical bool or integer 0/1")


def _info(wrapper: Any) -> Any:
    return wrapper.element_info


def _runtime_values(info: Any) -> tuple[int, ...]:
    runtime = _raw(info, "runtime_id")
    if not isinstance(runtime, (tuple, list)) or not runtime:
        raise _BlockedObservation("RuntimeId must be a non-empty tuple/list")
    values: list[int] = []
    for component in runtime:
        if type(component) is not int or not -(2**31) <= component <= 2**31 - 1:
            raise _BlockedObservation("RuntimeId components must be signed 32-bit Python ints")
        values.append(component)
    return tuple(values)


def _runtime_key(wrapper: Any) -> tuple[str, tuple[int, ...]]:
    return "runtime", _runtime_values(_info(wrapper))


def _visible(wrapper: Any) -> bool:
    value = _canonical_visibility(wrapper.is_visible())
    return value is True or value == 1


def _children(wrapper: Any) -> list[Any]:
    return list(wrapper.descendants())


def _optional_hwnd(value: Any, name: str) -> int | None:
    # Child controls need not expose a native HWND; zero is the provider's
    # conventional no-handle value. Root and dialog callers require positive.
    if value is _MISSING or value is None:
        return None
    if type(value) is int and value == 0:
        return None
    return _strict_int(value, name, positive=True)


def _observed(wrapper: Any, role: str, *, require_hwnd: bool) -> dict[str, Any]:
    info = _info(wrapper)
    raw_pid = _raw(info, "process_id")
    pid = _strict_int(raw_pid, f"{role}.process_id", positive=True)
    name = _text(_raw(info, "name"), f"{role}.name")
    class_name = _text(_raw(info, "class_name"), f"{role}.class_name")
    control_type = _text(_raw(info, "control_type"), f"{role}.control_type")
    automation_id = _text(_raw(info, "automation_id"), f"{role}.automation_id")
    visibility = _canonical_visibility(wrapper.is_visible())
    runtime = list(_runtime_values(info))
    hwnd_value = _raw(info, "handle")
    hwnd = _optional_hwnd(hwnd_value, f"{role}.hwnd")
    if require_hwnd and hwnd is None:
        raise _BlockedObservation(f"{role} has no positive native HWND for ownership binding")
    # Keep the provider vocabulary stable and include raw visibility verbatim.
    return {
        "name": name,
        "process_id": pid,
        "pid": pid,
        "class_name": class_name,
        "class": class_name,
        "control_type": control_type,
        "controltype": control_type,
        "automation_id": automation_id,
        "auto_id": automation_id,
        "visible": visibility,
        "raw_visibility": visibility,
        "runtime_id": runtime,
        "runtime_ids": runtime,
        "hwnd": hwnd,
    }


def _json_safe(value: Any) -> Any:
    if value is _MISSING:
        return None
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return repr(value)


def _raw_observed(wrapper: Any, role: str) -> dict[str, Any]:
    """Capture provider values before strict validation can reject a record."""
    info = _info(wrapper)
    visibility = wrapper.is_visible()
    runtime = _raw(info, "runtime_id")
    return {
        "name": _json_safe(_raw(info, "name")),
        "process_id": _json_safe(_raw(info, "process_id")),
        "pid": _json_safe(_raw(info, "process_id")),
        "class_name": _json_safe(_raw(info, "class_name")),
        "class": _json_safe(_raw(info, "class_name")),
        "control_type": _json_safe(_raw(info, "control_type")),
        "controltype": _json_safe(_raw(info, "control_type")),
        "automation_id": _json_safe(_raw(info, "automation_id")),
        "auto_id": _json_safe(_raw(info, "automation_id")),
        "visible": _json_safe(visibility),
        "raw_visibility": _json_safe(visibility),
        "runtime_id": _json_safe(runtime),
        "runtime_ids": _json_safe(runtime),
        "hwnd": _json_safe(_raw(info, "handle")),
        "observation_role": role,
    }


def _native_window_pid(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes

    hwnd = _strict_int(hwnd, "HWND", positive=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    is_window = user32.IsWindow
    is_window.argtypes = [wintypes.HWND]
    is_window.restype = wintypes.BOOL
    owner = user32.GetWindowThreadProcessId
    owner.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    owner.restype = wintypes.DWORD
    native = wintypes.DWORD()
    native_hwnd = wintypes.HWND(hwnd)
    if not is_window(native_hwnd):
        raise RuntimeError(f"HWND is not a live window: {hwnd}")
    if not owner(native_hwnd, ctypes.byref(native)) or not native.value:
        raise RuntimeError(f"HWND has no owner PID: {hwnd}")
    return _strict_int(int(native.value), "native owner PID", positive=True)


def _native_bind(label: str, hwnd: int | None, pid: int) -> int:
    if hwnd is None:
        raise _BlockedObservation(f"{label} cannot native-bind without a positive HWND")
    try:
        owner = _native_window_pid(hwnd)
    except RuntimeError as exc:
        raise _BlockedObservation(f"{label} native HWND validation failed: {exc}") from exc
    if owner != pid:
        raise _BlockedObservation(f"{label} HWND owner PID {owner} differs from owned PID {pid}")
    return owner


def _provider_pid(wrapper: Any) -> Any:
    return _raw(_info(wrapper), "process_id")


def _provider_name(wrapper: Any) -> Any:
    return _raw(_info(wrapper), "name")


def _is_known_transient(exc: BaseException) -> bool:
    if type(exc).__name__ == "UIAElementNotAvailableError":
        return True
    for attribute in ("HRESULT", "hresult", "winerror"):
        if getattr(exc, attribute, None) == KNOWN_TRANSIENT_HRESULT:
            return True
    return any(KNOWN_TRANSIENT_HRESULT == value for value in getattr(exc, "args", ()))


def _candidate_wrappers(root: Any, pid: int, desktop: Any) -> list[Any]:
    """Return only root-owned descendants and owned desktop top-level wrappers."""
    root_descendants = _children(root)
    top_level = list(desktop.windows())
    candidates: list[Any] = [root, *root_descendants]
    candidates.extend(top_level)
    owned: list[Any] = []
    for wrapper in candidates:
        raw_pid = _provider_pid(wrapper)
        # This PID filter intentionally precedes RuntimeId access. A foreign
        # provider can never make us query or deduplicate its RuntimeId.
        if type(raw_pid) is not int or raw_pid <= 0:
            if _provider_name(wrapper) in (None, _MISSING):
                continue
            if _provider_name(wrapper) in ("",):
                continue
            # An exact-title malformed candidate is handled as blocked by the
            # caller; unrelated foreign windows are merely not owned.
            owned.append((wrapper, False))
            continue
        if raw_pid == pid:
            owned.append((wrapper, True))
    return owned  # type: ignore[return-value]


def _button_identity(buttons: dict[str, Any], pid: int) -> dict[str, Any]:
    """Retain the original helper API while applying strict observations."""
    if set(buttons) != {"Cancel", "Yes"}:
        raise _BlockedObservation("modal button identity set is not exactly Cancel and Yes")
    values: dict[str, Any] = {}
    runtime_ids: set[tuple[str, tuple[int, ...]]] = set()
    for name, button in buttons.items():
        observed = _observed(button, f"button.{name}", require_hwnd=False)
        if observed["process_id"] != pid or observed["name"] != name:
            raise _BlockedObservation(f"button identity mismatch for {name}")
        if not (observed["visible"] is True or observed["visible"] == 1):
            raise _BlockedObservation(f"{name} button is not visible")
        if observed["control_type"] != "Button":
            raise _BlockedObservation(f"{name} is not observed as a Button control")
        key = _runtime_key(button)
        if key in runtime_ids:
            raise _BlockedObservation("modal buttons do not have unique RuntimeIds")
        runtime_ids.add(key)
        values[name] = observed
    return values


def _find_modal(root: Any, pid: int, title: str, body: str, desktop: Any | None = None,
                observations: dict[str, Any] | None = None,
                persist: Callable[[], None] | None = None) -> tuple[Any, dict[str, Any]] | None:
    if desktop is None:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
    if observations is None:
        observations = {}
    if persist is None:
        persist = lambda: None
    unique: dict[tuple[str, tuple[int, ...]], tuple[Any, bool]] = {}
    for wrapper, owned in _candidate_wrappers(root, pid, desktop):
        name = _provider_name(wrapper)
        if name != title:
            continue
        if not owned:
            raise _BlockedObservation("modal title matched a provider record without strict owned PID")
        observations["dialog"] = _raw_observed(wrapper, "dialog")
        persist()
        # RuntimeId is queried only after the PID filter above.
        key = _runtime_key(wrapper)
        unique.setdefault(key, (wrapper, owned))

    if len(unique) > 1:
        raise RuntimeError("multiple exact owned modal dialogs found; refusing first match")

    matches: list[tuple[Any, dict[str, Any]]] = []
    for wrapper, _owned in unique.values():
        dialog = _observed(wrapper, "dialog", require_hwnd=True)
        if dialog["name"] != title:
            continue
        observations["dialog"] = dialog
        persist()
        if not (dialog["visible"] is True or dialog["visible"] == 1):
            continue
        _native_bind("dialog", dialog["hwnd"], pid)
        children = _children(wrapper)
        body_candidates: list[Any] = []
        button_candidates: dict[str, list[Any]] = {"Cancel": [], "Yes": []}
        for child in children:
            child_name = _provider_name(child)
            if child_name == body or child_name in button_candidates:
                child_role = "body" if child_name == body else f"button.{child_name}"
                raw_child = _raw_observed(child, child_role)
                if child_name == body:
                    observations["body"] = raw_child
                else:
                    observations.setdefault("buttons", {})[child_name] = raw_child
                persist()
                raw_pid = _provider_pid(child)
                if type(raw_pid) is not int or raw_pid <= 0:
                    raise _BlockedObservation("modal child has a malformed process_id")
                if raw_pid != pid:
                    raise _BlockedObservation("modal child has a foreign process_id")
                if child_name == body:
                    body_candidates.append(child)
                else:
                    button_candidates[child_name].append(child)
        if len(body_candidates) != 1:
            raise _BlockedObservation("exactly one owned visible modal body was not observed")
        if any(len(items) != 1 for items in button_candidates.values()):
            raise _BlockedObservation("exactly one owned Cancel and Yes button was not observed")
        body_observation = _observed(body_candidates[0], "body", require_hwnd=False)
        if not (body_observation["visible"] is True or body_observation["visible"] == 1):
            raise _BlockedObservation("modal body is not visibly owned")
        button_observations: dict[str, dict[str, Any]] = {}
        button_wrappers: dict[str, Any] = {}
        button_runtime_ids: set[tuple[str, tuple[int, ...]]] = set()
        for button_name, items in button_candidates.items():
            button = items[0]
            try:
                observed = _observed(button, f"button.{button_name}", require_hwnd=False)
            except _BlockedObservation:
                # The raw record was persisted while matching the exact label.
                raise
            if not (observed["visible"] is True or observed["visible"] == 1):
                raise _BlockedObservation(f"{button_name} button is not visible")
            if observed["control_type"] != "Button":
                raise _BlockedObservation(f"{button_name} is not observed as a Button control")
            button_key = _runtime_key(button)
            if button_key in button_runtime_ids:
                raise _BlockedObservation("Cancel and Yes buttons share a RuntimeId")
            button_runtime_ids.add(button_key)
            button_observations[button_name] = observed
            button_wrappers[button_name] = button
        observations["body"] = body_observation
        observations["buttons"] = button_observations
        persist()
        matches.append((wrapper, {"body": body_candidates[0], "buttons": button_wrappers,
                                  "observed": dialog}))
    return matches[0] if matches else None


def _identity(process: Any) -> tuple[int, float, str]:
    pid = _strict_int(process.pid, "process.pid", positive=True)
    return pid, float(process.create_time()), str(process.exe())


def _blocked(reason: str, *, observations: dict[str, Any], stages: list[dict[str, Any]],
             stages_path: Path, output_dir: Path) -> dict[str, Any]:
    _write_observations(output_dir, observations)
    if not any(item.get("stage") == "discovery_completed" for item in stages):
        complete = all(key in observations for key in ("root", "dialog", "body", "buttons"))
        _stage(stages_path, stages, "discovery_completed", complete=complete,
               observations=observations)
    result = {
        "status": "BLOCKED",
        "reason": reason,
        "captured_readonly": True,
        "native_acceptance": False,
        "direct_cancel_invoke": False,
        "direct_cancel_invoke_count": 0,
        "yes_invoke_count": 0,
        "observations": observations,
        "stages": stages,
        "output_dir": str(output_dir),
    }
    if "dialog" in observations:
        result["dialog_control_type"] = observations["dialog"].get("control_type")
        result["dialog_class_name"] = observations["dialog"].get("class_name")
    _stage(stages_path, stages, "blocked", reason=reason,
           captured_readonly=True, native_acceptance=False, direct_cancel_invoke_count=0)
    result["stages"] = stages
    return result


def inspect_target(args: argparse.Namespace) -> dict[str, Any]:
    if os.name != "nt":
        return {
            "status": "BLOCKED",
            "reason": "native UIA worker requires Windows; modal control type is unpinned",
            "captured_readonly": False,
            "native_acceptance": False,
            "direct_cancel_invoke": False,
            "direct_cancel_invoke_count": 0,
            "yes_invoke_count": 0,
        }

    pid = _positive_raw_int(args.pid, "pid")
    hwnd = _positive_raw_int(args.hwnd, "hwnd")
    expected = (pid, float(args.create_time), str(args.exe))
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stages_path = output_dir / "worker-stages.json"
    stages: list[dict[str, Any]] = []
    observations: dict[str, Any] = {}
    _stage(stages_path, stages, "started")
    try:
        psutil, Desktop = _load_dependencies()
        desktop = Desktop(backend="uia")
        # ready means imports and backend initialization completed; no UIA
        # target query occurs before this event.
        _emit({"event": "ready", "pid": pid, "hwnd": hwnd})
        _native_bind("main", hwnd, pid)
        process = psutil.Process(pid)
        before = _identity(process)
        if before != expected:
            raise _BlockedObservation(f"owned identity mismatch before UIA: expected={expected!r}, actual={before!r}")
        root_spec = desktop.window(handle=hwnd)
        root = root_spec.wrapper_object()
        observations["root"] = _raw_observed(root, "root")
        _write_observations(output_dir, observations)
        root_observation = _observed(root, "root", require_hwnd=True)
        if root_observation["process_id"] != pid or root_observation["hwnd"] != hwnd:
            raise _BlockedObservation("main UIA root identity/HWND mismatch")
        if root_observation["name"] != args.main_title:
            raise _BlockedObservation("main UIA root title mismatch")
        observations["root"] = root_observation
        _write_observations(output_dir, observations)
        _stage(stages_path, stages, "target_validated", pid=pid, hwnd=hwnd,
               observation=root_observation)
        _stage(stages_path, stages, "discovery_started", attempt=1)

        match: tuple[Any, dict[str, Any]] | None = None
        last_reason = "exact owned modal title/body/buttons were not found"
        for attempt in range(1, MAX_DISCOVERY_ATTEMPTS + 1):
            try:
                match = _find_modal(root, pid, args.dialog_title, args.dialog_body,
                                    desktop, observations,
                                    lambda: _write_observations(output_dir, observations))
                if match is not None:
                    break
                last_reason = "exact owned modal title/body/buttons were not found"
            except Exception as exc:
                if not _is_known_transient(exc):
                    raise
                last_reason = f"known transient UIA observation error: {exc}"
            if attempt < MAX_DISCOVERY_ATTEMPTS:
                time.sleep(DISCOVERY_RETRY_DELAY)
        if match is None:
            raise _BlockedObservation(last_reason)
        dialog, details = match
        observations["dialog"]["native_owner_pid"] = _native_bind(
            "dialog", observations["dialog"]["hwnd"], pid)
        observations["root"]["native_owner_pid"] = _native_bind("main", hwnd, pid)
        _stage(stages_path, stages, "modal_validated", observation=observations["dialog"])
        _stage(stages_path, stages, "buttons_validated", buttons=observations["buttons"])
        _stage(stages_path, stages, "discovery_completed", complete=True,
               observations=observations)
        after_discovery = _identity(psutil.Process(pid))
        if after_discovery != before:
            raise _BlockedObservation("owned process identity changed after read-only discovery")
        if not observations["dialog"]["control_type"] in PINNED_MODAL_CONTROL_TYPES:
            return _blocked("modal control type is not pinned by native evidence",
                            observations=observations, stages=stages,
                            stages_path=stages_path, output_dir=output_dir)

        # Future-only action gate: expected native identity is checked again
        # after the pin. With the current empty pin this block is unreachable.
        if observations["dialog"]["class_name"] != PINNED_MODAL_CLASS_NAME:
            raise RuntimeError("pinned modal has unexpected native/UIA class")
        if observations["dialog"]["control_type"] != PINNED_MODAL_CONTROL_TYPE:
            raise RuntimeError("pinned modal has unexpected Window control type")
        pinned_button_runtime_ids = {
            name: tuple(value["runtime_id"])
            for name, value in observations["buttons"].items()
        }
        latest = _find_modal(root, pid, args.dialog_title, args.dialog_body, desktop,
                             observations,
                             lambda: _write_observations(output_dir, observations))
        if latest is None or _runtime_key(latest[0]) != _runtime_key(dialog):
            raise RuntimeError("modal identity changed before Cancel Invoke")
        latest_button_runtime_ids = {
            name: tuple(value["runtime_id"])
            for name, value in observations["buttons"].items()
        }
        if latest_button_runtime_ids != pinned_button_runtime_ids:
            raise RuntimeError("modal button identity changed before Cancel Invoke")
        observations["dialog"]["native_owner_pid"] = _native_bind(
            "dialog", observations["dialog"]["hwnd"], pid)
        observations["root"]["native_owner_pid"] = _native_bind("main", hwnd, pid)
        process_before_invoke = _identity(psutil.Process(pid))
        if process_before_invoke != before:
            raise RuntimeError("owned identity changed before Cancel Invoke")
        _stage(stages_path, stages, "cancel_invoke_started", cancel_invoke_count=1)
        latest[1]["buttons"]["Cancel"].invoke()
        _stage(stages_path, stages, "cancel_invoke_completed", cancel_invoke_count=1, yes_invoke_count=0)
        after = _identity(psutil.Process(pid))
        observations["dialog"]["native_owner_pid"] = _native_bind(
            "dialog", observations["dialog"]["hwnd"], pid)
        observations["root"]["native_owner_pid"] = _native_bind("main", hwnd, pid)
        if after != before:
            raise RuntimeError("owned identity changed after Cancel Invoke")
        _stage(stages_path, stages, "post_validated", cancel_invoke_count=1, yes_invoke_count=0)
        return {"status": "PASS", "direct_cancel_invoke": True, "direct_cancel_invoke_count": 1,
                "yes_invoke_count": 0, "captured_readonly": False, "native_acceptance": True,
                "observations": observations, "stages": stages, "output_dir": str(output_dir)}
    except _BlockedObservation as exc:
        # Even a blocked/partial discovery gets an independent post-query
        # ownership check. Preserve the discovery reason if the recheck also
        # fails; neither error is evidence of a native acceptance.
        reason = str(exc)
        for label, observed_hwnd in (("main", hwnd),
                                     ("dialog", observations.get("dialog", {}).get("hwnd"))):
            if label == "dialog" and "dialog" not in observations:
                continue
            try:
                _native_bind(label, observed_hwnd, pid)
            except _BlockedObservation as post_exc:
                reason += f"; post-query {label} ownership check: {post_exc}"
        return _blocked(reason, observations=observations, stages=stages,
                        stages_path=stages_path, output_dir=output_dir)
    except Exception as exc:
        # Attach the exact partial evidence without replacing the causal error;
        # main() prints the full chained traceback to stderr.
        raise _WorkerFailure(str(exc), observations=observations, stages=stages,
                             output_dir=output_dir) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True)
    parser.add_argument("--create-time", required=True)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--hwnd", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--main-title", required=False)
    parser.add_argument("--dialog-title", required=False)
    parser.add_argument("--dialog-body", required=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.main_title = args.main_title or f"Modal Cancel Fixture Main {args.nonce}"
    args.dialog_title = args.dialog_title or f"Modal Cancel Fixture {args.nonce}"
    args.dialog_body = args.dialog_body or f"Benign modal cancellation test {args.nonce}"
    try:
        result = inspect_target(args)
    except Exception as exc:
        primary_exc = exc.__cause__ if isinstance(exc, _WorkerFailure) and exc.__cause__ is not None else exc
        observations = getattr(exc, "observations", {})
        stages = getattr(exc, "stages", [])
        output_dir = getattr(exc, "output_dir", None)
        if output_dir is not None:
            try:
                _write_observations(output_dir, observations)
                _atomic_json(output_dir / "worker-failure.json", {
                    "error_type": type(primary_exc).__name__, "error": str(primary_exc),
                    "traceback": traceback.format_exc(), "observations": observations,
                    "stages": stages,
                })
            except Exception as evidence_exc:
                print(f"evidence preservation failed: {type(evidence_exc).__name__}: {evidence_exc}",
                      file=sys.stderr, flush=True)
        result = {
            "status": "FAIL", "error_type": type(primary_exc).__name__, "error": str(primary_exc),
            "traceback": traceback.format_exc(), "observations": observations, "stages": stages,
            "captured_readonly": bool(observations), "native_acceptance": False,
            "direct_cancel_invoke": False, "direct_cancel_invoke_count": 0,
            "yes_invoke_count": 0,
        }
        traceback.print_exc(file=sys.stderr)
        _emit(result)
        return 1
    _emit(result)
    return 0 if result["status"] == "PASS" else (2 if result["status"] == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
