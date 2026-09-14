"""Read-only modal worker regression contracts; no native UIA or Invoke."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
WORKER = HERE / "worker.py"
SUPERVISOR = HERE.parent / "player-inspection" / "uia_supervisor.py"


def _load_worker():
    spec = importlib.util.spec_from_file_location("modal_cancel_worker_review", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


worker = _load_worker()


class Info:
    def __init__(self, *, name, pid, runtime, hwnd, class_name="ObservedClass",
                 control_type="Pane", automation_id="observed-id"):
        self.name = name
        self.process_id = pid
        self.runtime_id = runtime
        self.handle = hwnd
        self.class_name = class_name
        self.control_type = control_type
        self.automation_id = automation_id


class Wrapper:
    def __init__(self, info, children=(), visible=True):
        self.element_info = info
        self._children = list(children)
        self._visible = visible
        self.invoke_count = 0

    def descendants(self):
        return list(self._children)

    def is_visible(self):
        return self._visible

    def invoke(self):
        self.invoke_count += 1


class Process:
    pid = 321

    def create_time(self):
        return 12.5

    def exe(self):
        return "/owned/player.exe"


class Psutil:
    Process = lambda self, pid: Process()


class Desktop:
    windows_result = []
    root_result = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def window(self, **kwargs):
        return types.SimpleNamespace(wrapper_object=lambda: self.root_result)

    def windows(self):
        return list(self.windows_result)


def _args(output_dir: Path, **overrides):
    values = dict(
        pid="321", create_time="12.5", exe="/owned/player.exe", hwnd="100",
        nonce="nonce-1", root=str(output_dir), output_dir=str(output_dir),
        main_title="Main nonce-1", dialog_title="Dialog nonce-1",
        dialog_body="Body nonce-1",
    )
    values.update(overrides)
    return types.SimpleNamespace(**values)


def _owned_tree(*, dialog_class="ObservedClass", dialog_type="Pane", dialog_hwnd=200,
                dialog_pid=321, body_pid=321, root_pid=321):
    body = Wrapper(Info(name="Body nonce-1", pid=body_pid, runtime=[-7, 4], hwnd=202,
                        class_name="BodyClass", control_type="Text", automation_id="body-id"))
    cancel = Wrapper(Info(name="Cancel", pid=321, runtime=[-8, 4], hwnd=203,
                          class_name="ButtonClass", control_type="Button", automation_id="cancel-id"))
    yes = Wrapper(Info(name="Yes", pid=321, runtime=[-9, 4], hwnd=204,
                       class_name="ButtonClass", control_type="Button", automation_id="yes-id"))
    dialog = Wrapper(Info(name="Dialog nonce-1", pid=dialog_pid, runtime=[-6, 4], hwnd=dialog_hwnd,
                          class_name=dialog_class, control_type=dialog_type,
                          automation_id="dialog-id"), [body, cancel, yes])
    root = Wrapper(Info(name="Main nonce-1", pid=root_pid, runtime=[-5, 4], hwnd=100,
                        class_name="MainClass", control_type="Window", automation_id="root-id"),
                   [dialog])
    return root, dialog, body, cancel, yes


class WorkerObservationTests(unittest.TestCase):
    def setUp(self):
        Desktop.windows_result = []
        Desktop.root_result = None
        self.native_calls = []

    def _run(self, root, **kwargs):
        Desktop.root_result = root
        output = Path(kwargs.pop("output", tempfile.mkdtemp()))
        output.mkdir(parents=True, exist_ok=True)
        def native(hwnd):
            self.native_calls.append(hwnd)
            return 321
        with mock.patch.object(worker, "os", types.SimpleNamespace(name="nt")), \
             mock.patch.object(worker, "_load_dependencies", return_value=(Psutil(), Desktop)), \
             mock.patch.object(worker, "_native_window_pid", side_effect=native):
            return worker.inspect_target(_args(output, **kwargs))

    def test_unexpected_class_is_characterized_read_only_and_never_invoked(self):
        root, dialog, body, cancel, yes = _owned_tree(dialog_class="UnexpectedQtClass", dialog_type="CustomDialog")
        result = self._run(root)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(result["captured_readonly"])
        self.assertFalse(result["native_acceptance"])
        self.assertEqual(result["direct_cancel_invoke_count"], 0)
        observed = result["observations"]
        self.assertEqual(observed["dialog"]["class_name"], "UnexpectedQtClass")
        self.assertEqual(observed["dialog"]["control_type"], "CustomDialog")
        self.assertEqual(observed["body"]["process_id"], 321)
        self.assertEqual(observed["dialog"]["runtime_id"], [-6, 4])
        self.assertEqual(observed["root"]["hwnd"], 100)
        self.assertEqual(observed["dialog"]["hwnd"], 200)
        self.assertEqual(observed["root"]["native_owner_pid"], 321)
        self.assertEqual(observed["dialog"]["native_owner_pid"], 321)
        self.assertEqual(cancel.invoke_count + yes.invoke_count, 0)
        self.assertGreaterEqual(self.native_calls.count(100), 2)
        self.assertGreaterEqual(self.native_calls.count(200), 2)
        stages = json.loads((Path(result["output_dir"]) / "worker-stages.json").read_text())
        self.assertEqual([item["stage"] for item in stages][-2:], ["discovery_completed", "blocked"])

    def test_foreign_dialog_hwnd_blocks_before_any_action(self):
        root, dialog, *_ = _owned_tree(dialog_hwnd=999)
        Desktop.root_result = root
        calls = []
        def native(hwnd):
            calls.append(hwnd)
            return 999 if hwnd == 999 else 321
        output = Path(tempfile.mkdtemp())
        with mock.patch.object(worker, "os", types.SimpleNamespace(name="nt")), \
             mock.patch.object(worker, "_load_dependencies", return_value=(Psutil(), Desktop)), \
             mock.patch.object(worker, "_native_window_pid", side_effect=native):
            result = worker.inspect_target(_args(output))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["observations"]["dialog"]["hwnd"], 999)
        self.assertFalse(result["native_acceptance"])
        self.assertEqual(result["direct_cancel_invoke_count"], 0)
        self.assertIn(999, calls)

    def test_dialog_without_hwnd_is_blocked_with_raw_dialog_record(self):
        root, *_ = _owned_tree(dialog_hwnd=None)
        result = self._run(root)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertIsNone(result["observations"]["dialog"]["hwnd"])
        self.assertFalse(result["native_acceptance"])
        self.assertEqual(result["direct_cancel_invoke_count"], 0)

    def test_root_without_provider_hwnd_is_blocked_with_raw_root_record(self):
        root, *_ = _owned_tree()
        root.element_info.handle = None
        result = self._run(root)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertIsNone(result["observations"]["root"]["hwnd"])
        self.assertFalse(result["native_acceptance"])

    def test_malformed_provider_pid_blocks_instead_of_coercing(self):
        root, dialog, body, *_ = _owned_tree(body_pid="321")
        result = self._run(root)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertFalse(result["native_acceptance"])
        self.assertEqual(result["direct_cancel_invoke_count"], 0)
        self.assertIn("process_id", result["reason"])

    def test_malformed_runtime_and_visibility_are_not_accepted(self):
        root, dialog, body, *_ = _owned_tree()
        dialog.element_info.runtime_id = [-6, "4"]
        result = self._run(root)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertFalse(result["native_acceptance"])
        body._visible = "truthy"
        dialog.element_info.runtime_id = [-6, 4]
        result = self._run(root)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertIn("visibility", result["reason"])

    def test_duplicate_exact_nonce_modal_is_fatal_without_first_match(self):
        root, dialog, body, cancel, yes = _owned_tree()
        other_root, other_dialog, *_ = _owned_tree()
        other_dialog.element_info.runtime_id = [-60, 4]
        root._children.append(other_dialog)
        with self.assertRaises(RuntimeError):
            self._run(root)
        self.assertEqual(cancel.invoke_count + yes.invoke_count, 0)

    def test_known_transient_discovery_error_retries_before_action(self):
        root, *_ = _owned_tree()
        original = root.descendants
        class UIAElementNotAvailableError(RuntimeError):
            pass
        root.descendants = mock.Mock(side_effect=[UIAElementNotAvailableError("stale"), original()])
        result = self._run(root)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertEqual(root.descendants.call_count, 2)
        self.assertEqual(result["direct_cancel_invoke_count"], 0)

    def test_existing_button_identity_helper_keeps_callable_api_and_strict_fields(self):
        root, dialog, body, cancel, yes = _owned_tree()
        values = worker._button_identity({"Cancel": cancel, "Yes": yes}, 321)
        self.assertEqual(set(values), {"Cancel", "Yes"})
        self.assertEqual(values["Cancel"]["runtime_id"], [-8, 4])
        self.assertEqual(values["Yes"]["process_id"], 321)

    def test_unknown_provider_error_is_fatal_not_absent_modal(self):
        root, *_ = _owned_tree()
        root.descendants = mock.Mock(side_effect=RuntimeError("provider exploded"))
        with self.assertRaisesRegex(RuntimeError, "provider exploded"):
            self._run(root)


class WorkerSupervisorContainmentTests(unittest.TestCase):
    def test_discovery_hang_keeps_stage_evidence_and_reaps_child(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            child = root / "hanging_discovery.py"
            child.write_text(
                "import json,time\n"
                "print(json.dumps({'event':'ready'}), flush=True)\n"
                "print(json.dumps({'event':'stage','stage':'discovery_started'}), flush=True)\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            spec = importlib.util.spec_from_file_location("worker_review_supervisor", SUPERVISOR)
            supervisor = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            sys.modules[spec.name] = supervisor
            spec.loader.exec_module(supervisor)
            result = supervisor.run_supervised(
                output_dir=root / "run", worker_script=child,
                readiness_timeout=1, execution_timeout=.15,
                terminate_timeout=.2, kill_timeout=.5,
            )
            self.assertEqual(result.status, "TIMEOUT", result.to_dict())
            self.assertEqual(result.timeout_phase, "execution")
            self.assertTrue(result.cleanup_verified)
            self.assertIn("discovery_started", result.stdout)
            self.assertIsNotNone(result.returncode)


if __name__ == "__main__":
    unittest.main()
