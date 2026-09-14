"""Bounded Windows UIA worker for discovery and opt-in one-Cancel action.

All pywinauto/UIA imports and calls stay in this child. Discovery is read-only
by default; the explicit ``--cancel-once`` path is bound to the reviewed Qt
identity and never retries an entered Invoke.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Callable

# Select the windowless MTA before importing pywinauto/comtypes on Windows.
sys.coinit_flags = 0

PINNED_MODAL_CONTROL_TYPES: frozenset[str] = frozenset({"Window"})
PINNED_MODAL_CLASS_NAME = "QMessageBox"
PINNED_MODAL_CONTROL_TYPE = "Window"
KNOWN_TRANSIENT_HRESULT = 0x80040201
MAX_DISCOVERY_ATTEMPTS = 2
DISCOVERY_RETRY_DELAY = 0.05
DISAPPEARANCE_TIMEOUT = 5.0
DISAPPEARANCE_POLL_DELAY = 0.05
_MISSING = object()


class _BlockedObservation(ValueError):
    """A known safety/identity observation that must not become native action."""


class _WorkerFailure(RuntimeError):
    """Fatal failure carrying the partial read-only evidence for main()."""

    def __init__(self, message: str, *, observations: dict[str, Any],
                 stages: list[dict[str, Any]], output_dir: Path,
                 action: dict[str, Any] | None = None):
        super().__init__(message)
        self.observations = observations
        self.stages = stages
        self.output_dir = output_dir
        self.action = copy.deepcopy(action) if action is not None else _new_action()


def _new_action() -> dict[str, Any]:
    return {"cancel_attempted": 0, "cancel_completed": 0,
            "yes_attempted": 0, "outcome": "not_attempted"}


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


def _expected_shape(nonce: str) -> dict[str, dict[str, Any]]:
    dialog_id = f"QApplication.ModalCancelDialog_{nonce}"
    return {
        "root": {"name": f"Modal Cancel Fixture Main {nonce}",
                 "class_name": "QMainWindow", "control_type": "Window",
                 "automation_id": f"QApplication.ModalCancelFixtureMain_{nonce}"},
        "dialog": {"name": f"Modal Cancel Fixture {nonce}",
                    "class_name": "QMessageBox", "control_type": "Window",
                    "automation_id": dialog_id},
        "body": {"name": f"Benign modal cancellation test {nonce}",
                  "class_name": "QLabel", "control_type": "Text",
                  "automation_id": dialog_id + ".qt_msgbox_label"},
        "button": {"name": None, "class_name": "QPushButton",
                    "control_type": "Button",
                    "automation_id": dialog_id + ".qt_msgbox_buttonbox.QPushButton"},
    }


def _identity_fields(observed: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(observed[key] for key in (
        "name", "process_id", "class_name", "control_type", "automation_id",
        "visible", "runtime_id", "hwnd",
    ))


def _strict_shape(root: Any, match: tuple[Any, dict[str, Any]], nonce: str,
                  pid: int, hwnd: int) -> dict[str, Any]:
    expected = _expected_shape(nonce)
    dialog, details = match
    root_observation = _observed(root, "root", require_hwnd=True)
    if root_observation["hwnd"] != hwnd or root_observation["process_id"] != pid:
        raise _BlockedObservation("strict root ownership identity mismatch")
    for key, value in expected["root"].items():
        if root_observation[key] != value:
            raise _BlockedObservation(f"root {key} is not the nonce-derived Qt identity")
    dialog_observation = _observed(dialog, "dialog", require_hwnd=True)
    if dialog_observation["process_id"] != pid:
        raise _BlockedObservation("strict dialog ownership identity mismatch")
    for key, value in expected["dialog"].items():
        if dialog_observation[key] != value:
            raise _BlockedObservation(f"dialog {key} is not the pinned Qt identity")
    body = details["body"]
    body_observation = _observed(body, "body", require_hwnd=False)
    if body_observation["process_id"] != pid:
        raise _BlockedObservation("fresh body PID differs from the owned fixture")
    for key, value in expected["body"].items():
        if body_observation[key] != value:
            raise _BlockedObservation(f"body {key} is not the pinned Qt identity")
    if body_observation["hwnd"] is not None:
        raise _BlockedObservation("Qt modal body unexpectedly exposes a native HWND")
    button_observations: dict[str, dict[str, Any]] = {}
    runtime_ids: set[tuple[int, ...]] = set()
    for button_name in ("Cancel", "Yes"):
        button_observation = _observed(details["buttons"][button_name],
                                       f"button.{button_name}", require_hwnd=False)
        if button_observation["process_id"] != pid:
            raise _BlockedObservation(f"fresh {button_name} PID differs from the owned fixture")
        for key, value in expected["button"].items():
            if key == "name":
                value = button_name
            if button_observation[key] != value:
                raise _BlockedObservation(f"{button_name} {key} is not the pinned Qt identity")
        if button_observation["hwnd"] is not None:
            raise _BlockedObservation(f"Qt {button_name} button unexpectedly exposes a native HWND")
        runtime = tuple(button_observation["runtime_id"])
        if runtime in runtime_ids:
            raise _BlockedObservation("pinned Cancel and Yes RuntimeIds are not distinct")
        runtime_ids.add(runtime)
        button_observations[button_name] = button_observation
    return {"root": root_observation, "dialog": dialog_observation,
            "body": body_observation, "buttons": button_observations,
            "dialog_wrapper": dialog, "body_wrapper": body,
            "button_wrappers": details["buttons"]}


def _fresh_snapshot(desktop: Any, psutil: Any, pid: int, hwnd: int,
                    title: str, body: str, nonce: str) -> dict[str, Any]:
    absent_reason = "exact owned modal is absent during identity snapshot"
    transient_seen = False
    for attempt in range(1, MAX_DISCOVERY_ATTEMPTS + 1):
        try:
            fresh_root = desktop.window(handle=hwnd).wrapper_object()
            local_observations: dict[str, Any] = {}
            match = _find_modal(fresh_root, pid, title, body, desktop,
                                local_observations, lambda: None)
            if match is None:
                raise _BlockedObservation(absent_reason)
            snapshot = _strict_shape(fresh_root, match, nonce, pid, hwnd)
            snapshot["process"] = _identity(psutil.Process(pid))
            snapshot["root"]["native_owner_pid"] = _native_bind(
                "main", snapshot["root"]["hwnd"], pid)
            snapshot["dialog"]["native_owner_pid"] = _native_bind(
                "dialog", snapshot["dialog"]["hwnd"], pid)
            return snapshot
        except _BlockedObservation as exc:
            if str(exc) != absent_reason and not transient_seen:
                raise
            if attempt == MAX_DISCOVERY_ATTEMPTS:
                raise
        except Exception as exc:
            if not _is_known_transient(exc) or attempt == MAX_DISCOVERY_ATTEMPTS:
                raise
            transient_seen = True
        time.sleep(DISCOVERY_RETRY_DELAY)
    raise _BlockedObservation(absent_reason)


def _verify_post_owner(desktop: Any, psutil: Any, pid: int, hwnd: int,
                       pinned: dict[str, Any]) -> None:
    root = desktop.window(handle=hwnd).wrapper_object()
    root_observation = _observed(root, "post.root", require_hwnd=True)
    if _identity_fields(root_observation) != _identity_fields(pinned["root"]):
        raise RuntimeError("root identity changed after Cancel Invoke")
    _native_bind("post.main", root_observation["hwnd"], pid)
    if _identity(psutil.Process(pid)) != pinned["process"]:
        raise RuntimeError("owned process identity changed after Cancel Invoke")


def _owned_replacement_modal(root: Any, pid: int, desktop: Any) -> bool:
    candidates = [root, *_children(root), *list(desktop.windows())]
    for child in candidates:
        info = _info(child)
        if _raw(info, "process_id") != pid:
            continue
        if _raw(info, "class_name") == PINNED_MODAL_CLASS_NAME and \
                _raw(info, "control_type") == PINNED_MODAL_CONTROL_TYPE and \
                _raw(info, "name") is not None and \
                str(_raw(info, "name")).startswith("Modal Cancel Fixture ") and _visible(child):
            return True
    return False


def _modal_absent(desktop: Any, psutil: Any, pid: int, hwnd: int,
                  title: str, body: str, nonce: str,
                  pinned: dict[str, Any]) -> bool:
    root = desktop.window(handle=hwnd).wrapper_object()
    root_observation = _observed(root, "post.root", require_hwnd=True)
    if _identity_fields(root_observation) != _identity_fields(pinned["root"]):
        raise RuntimeError("root identity changed while checking modal disappearance")
    _native_bind("post.main", root_observation["hwnd"], pid)
    if _identity(psutil.Process(pid)) != pinned["process"]:
        raise RuntimeError("owned process identity changed while checking modal disappearance")
    local: dict[str, Any] = {}
    match = _find_modal(root, pid, title, body, desktop, local, lambda: None)
    if match is not None or _owned_replacement_modal(root, pid, desktop):
        return False
    return True


def _wait_for_modal_absence(desktop: Any, psutil: Any, pid: int, hwnd: int,
                            title: str, body: str, nonce: str,
                            pinned: dict[str, Any]) -> None:
    deadline = time.monotonic() + DISAPPEARANCE_TIMEOUT
    while time.monotonic() < deadline:
        try:
            if _modal_absent(desktop, psutil, pid, hwnd, title, body, nonce, pinned):
                return
        except Exception as exc:
            if not _is_known_transient(exc):
                raise
        time.sleep(DISAPPEARANCE_POLL_DELAY)
    raise RuntimeError("exact nonce modal did not disappear before the bounded deadline")


def _identity(process: Any) -> tuple[int, float, str]:
    pid = _strict_int(process.pid, "process.pid", positive=True)
    return pid, float(process.create_time()), str(process.exe())


def _blocked(reason: str, *, observations: dict[str, Any], stages: list[dict[str, Any]],
             stages_path: Path, output_dir: Path,
             action: dict[str, Any] | None = None) -> dict[str, Any]:
    action = copy.deepcopy(action) if action is not None else _new_action()
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
        "action": action,
        "modal_absent": False,
        "post_identity_verified": False,
        "direct_cancel_invoke": False,
        "direct_cancel_invoke_count": action["cancel_attempted"],
        "yes_invoke_count": action["yes_attempted"],
        "observations": observations,
        "stages": stages,
        "output_dir": str(output_dir),
    }
    if "dialog" in observations:
        result["dialog_control_type"] = observations["dialog"].get("control_type")
        result["dialog_class_name"] = observations["dialog"].get("class_name")
    _stage(stages_path, stages, "blocked", reason=reason,
           captured_readonly=True, native_acceptance=False,
           direct_cancel_invoke_count=action["cancel_attempted"],
           action=action)
    result["stages"] = stages
    return result


def inspect_target(args: argparse.Namespace) -> dict[str, Any]:
    action = _new_action()
    if os.name != "nt":
        return {
            "status": "BLOCKED",
            "reason": "native UIA worker requires Windows; modal control type is unpinned",
            "captured_readonly": False,
            "native_acceptance": False,
            "action": action,
            "modal_absent": False,
            "post_identity_verified": False,
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
        if not getattr(args, "cancel_once", False):
            return _blocked("Cancel invocation is not enabled", observations=observations,
                            stages=stages, stages_path=stages_path,
                            output_dir=output_dir, action=action)
        if observations["dialog"]["control_type"] not in PINNED_MODAL_CONTROL_TYPES:
            raise _BlockedObservation("modal control type is not pinned by native evidence")

        # The action gate is deliberately separate from the descriptive
        # discovery records.  Pinned values are never overwritten by a later
        # provider query; every action-boundary query starts at a fresh root.
        pinned = _fresh_snapshot(desktop, psutil, pid, hwnd,
                                 args.dialog_title, args.dialog_body, args.nonce)
        for role in ("root", "dialog", "body"):
            if _identity_fields(observations[role]) != _identity_fields(pinned[role]):
                raise _BlockedObservation(f"{role} identity changed after discovery")
        for name in ("Cancel", "Yes"):
            if _identity_fields(observations["buttons"][name]) != \
                    _identity_fields(pinned["buttons"][name]):
                raise _BlockedObservation(f"{name} identity changed after discovery")
        if before != pinned["process"]:
            raise _BlockedObservation("owned process identity changed after discovery snapshot")
        for role in ("root", "dialog"):
            if observations[role].get("native_owner_pid") != pinned[role]["native_owner_pid"]:
                raise _BlockedObservation(f"{role} native owner changed after discovery")
        before_action = _fresh_snapshot(desktop, psutil, pid, hwnd,
                                        args.dialog_title, args.dialog_body, args.nonce)
        for role in ("root", "dialog", "body"):
            if _identity_fields(before_action[role]) != _identity_fields(pinned[role]):
                raise _BlockedObservation(f"{role} identity changed before Cancel Invoke")
        if before_action["buttons"].keys() != pinned["buttons"].keys():
            raise _BlockedObservation("button identity set changed before Cancel Invoke")
        for name in ("Cancel", "Yes"):
            if _identity_fields(before_action["buttons"][name]) != \
                    _identity_fields(pinned["buttons"][name]):
                raise _BlockedObservation(f"{name} identity changed before Cancel Invoke")
        if before_action["process"] != pinned["process"]:
            raise _BlockedObservation("owned process identity changed before Cancel Invoke")
        for role in ("root", "dialog"):
            if before_action[role]["native_owner_pid"] != pinned[role]["native_owner_pid"]:
                raise _BlockedObservation(f"{role} native owner changed before Cancel Invoke")
        observations["action_snapshot"] = {
            role: copy.deepcopy(pinned[role]) for role in ("root", "dialog", "body", "buttons")
        }
        observations["action_snapshot"]["process"] = pinned["process"]
        _write_observations(output_dir, observations)

        # Flush the audit marker before entering the one syntactic Invoke.
        # If that write fails, this remains a planned but unentered action.
        action["cancel_attempted"] = 1
        action["outcome"] = "unknown"
        try:
            _stage(stages_path, stages, "cancel_invoke_started",
                   cancel_invoke_count=1, action=copy.deepcopy(action))
        except Exception:
            action = _new_action()
            if stages and stages[-1].get("stage") == "cancel_invoke_started":
                stages[-1].update(stage="cancel_invoke_not_entered", cancel_invoke_count=0,
                                  action=copy.deepcopy(action), audit_write_failed=True)
            raise
        try:
            before_action["button_wrappers"]["Cancel"].invoke()
        except Exception as exc:
            action["outcome"] = "unknown"
            try:
                _stage(stages_path, stages, "cancel_invoke_failed",
                       cancel_invoke_count=1, yes_invoke_count=0,
                       action=copy.deepcopy(action))
            except Exception:
                pass
            raise _WorkerFailure("Cancel Invoke failed", observations=observations,
                                 stages=stages, output_dir=output_dir,
                                 action=action) from exc
        action["cancel_completed"] = 1
        action["outcome"] = "completed"
        try:
            _stage(stages_path, stages, "cancel_invoke_completed",
                   cancel_invoke_count=1, yes_invoke_count=0,
                   action=copy.deepcopy(action))
            _verify_post_owner(desktop, psutil, pid, hwnd, pinned)
            _wait_for_modal_absence(desktop, psutil, pid, hwnd,
                                    args.dialog_title, args.dialog_body,
                                    args.nonce, pinned)
        except Exception as exc:
            action["outcome"] = "unknown"
            raise _WorkerFailure("post-Cancel identity/disappearance validation failed",
                                 observations=observations, stages=stages,
                                 output_dir=output_dir, action=action) from exc
        try:
            _stage(stages_path, stages, "post_validated", cancel_invoke_count=1,
                   yes_invoke_count=0, action=copy.deepcopy(action),
                   modal_absent=True, post_identity_verified=True)
        except Exception as exc:
            action["outcome"] = "unknown"
            raise _WorkerFailure("post-Cancel audit stage failed", observations=observations,
                                 stages=stages, output_dir=output_dir,
                                 action=action) from exc
        return {"status": "PASS", "action": action, "modal_absent": True,
                "post_identity_verified": True, "direct_cancel_invoke": True,
                "direct_cancel_invoke_count": action["cancel_attempted"],
                "yes_invoke_count": action["yes_attempted"],
                "captured_readonly": False, "native_acceptance": True,
                "observations": observations, "stages": stages,
                "output_dir": str(output_dir)}
    except _WorkerFailure:
        raise
    except _BlockedObservation as exc:
        # Even a blocked/partial discovery gets an independent post-query
        # ownership check. Preserve the discovery reason if the recheck also
        # fails; neither error is evidence of a native acceptance.
        if action["cancel_attempted"]:
            action["outcome"] = "unknown"
            raise _WorkerFailure(str(exc), observations=observations,
                                 stages=stages, output_dir=output_dir,
                                 action=action) from exc
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
                        stages_path=stages_path, output_dir=output_dir,
                        action=action)
    except Exception as exc:
        # Attach the exact partial evidence without replacing the causal error;
        # main() prints the full chained traceback to stderr.
        if action["cancel_attempted"]:
            action["outcome"] = "unknown"
        raise _WorkerFailure(str(exc), observations=observations, stages=stages,
                             output_dir=output_dir, action=action) from exc


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
    parser.add_argument("--cancel-once", action="store_true",
                        help="explicitly opt in to exactly one native Cancel Invoke")
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
        action = getattr(exc, "action", _new_action())
        output_dir = getattr(exc, "output_dir", None)
        if output_dir is not None:
            try:
                _write_observations(output_dir, observations)
                _atomic_json(output_dir / "worker-stages.json", stages)
                _atomic_json(output_dir / "worker-failure.json", {
                    "error_type": type(primary_exc).__name__, "error": str(primary_exc),
                    "traceback": traceback.format_exc(), "observations": observations,
                    "stages": stages, "action": action,
                })
            except Exception as evidence_exc:
                print(f"evidence preservation failed: {type(evidence_exc).__name__}: {evidence_exc}",
                      file=sys.stderr, flush=True)
        result = {
            "status": "FAIL", "error_type": type(primary_exc).__name__, "error": str(primary_exc),
            "traceback": traceback.format_exc(), "observations": observations, "stages": stages,
            "captured_readonly": bool(observations) and action["cancel_attempted"] == 0,
            "native_acceptance": False,
            "action": action, "modal_absent": False,
            "post_identity_verified": False,
            "direct_cancel_invoke": bool(action["cancel_attempted"]),
            "direct_cancel_invoke_count": action["cancel_attempted"],
            "yes_invoke_count": action["yes_attempted"],
        }
        traceback.print_exc(file=sys.stderr)
        _emit(result)
        return 1
    _emit(result)
    return 0 if result["status"] == "PASS" else (2 if result["status"] == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
