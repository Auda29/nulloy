"""In-memory opt-in Cancel worker contracts; no native UIA execution."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
WORKER = HERE / "worker.py"


def _load_worker():
    spec = importlib.util.spec_from_file_location("modal_cancel_worker_cancel", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


worker = _load_worker()
SUPERVISOR = HERE.parent / "player-inspection" / "uia_supervisor.py"


class Info:
    def __init__(self, *, name, pid, runtime, hwnd, class_name, control_type, automation_id):
        self.name = name
        self.process_id = pid
        self.runtime_id = runtime
        self.handle = hwnd
        self.class_name = class_name
        self.control_type = control_type
        self.automation_id = automation_id


class Wrapper:
    def __init__(self, info, children=(), visible=True, on_invoke=None):
        self.element_info = info
        self._children = list(children)
        self._visible = visible
        self.invoke_count = 0
        self.on_invoke = on_invoke

    def descendants(self):
        return list(self._children)

    def is_visible(self):
        return self._visible

    def invoke(self):
        self.invoke_count += 1
        if self.on_invoke is not None:
            self.on_invoke()


class Process:
    pid = 321

    def create_time(self):
        return 12.5

    def exe(self):
        return "/owned/player.exe"


class Psutil:
    Process = lambda self, pid: Process()


class Desktop:
    root_result = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def window(self, **kwargs):
        return types.SimpleNamespace(wrapper_object=lambda: self.root_result)

    def windows(self):
        return [self.root_result] if self.root_result is not None else []


def _args(output_dir: Path, **overrides):
    values = dict(
        pid="321", create_time="12.5", exe="/owned/player.exe", hwnd="100",
        nonce="nonce-1", root=str(output_dir), output_dir=str(output_dir),
        main_title="Modal Cancel Fixture Main nonce-1",
        dialog_title="Modal Cancel Fixture nonce-1",
        dialog_body="Benign modal cancellation test nonce-1",
        cancel_once=True,
    )
    values.update(overrides)
    return types.SimpleNamespace(**values)


def _qt_tree(*, on_invoke=None):
    nonce = "nonce-1"
    dialog_id = f"QApplication.ModalCancelDialog_{nonce}"
    body = Wrapper(Info(
        name=f"Benign modal cancellation test {nonce}", pid=321, runtime=[-7, 4], hwnd=0,
        class_name="QLabel", control_type="Text",
        automation_id=dialog_id + ".qt_msgbox_label",
    ))
    cancel = Wrapper(Info(
        name="Cancel", pid=321, runtime=[-8, 4], hwnd=0,
        class_name="QPushButton", control_type="Button",
        automation_id=dialog_id + ".qt_msgbox_buttonbox.QPushButton",
    ), on_invoke=on_invoke)
    yes = Wrapper(Info(
        name="Yes", pid=321, runtime=[-9, 4], hwnd=0,
        class_name="QPushButton", control_type="Button",
        automation_id=dialog_id + ".qt_msgbox_buttonbox.QPushButton",
    ))
    dialog = Wrapper(Info(
        name=f"Modal Cancel Fixture {nonce}", pid=321, runtime=[-6, 4], hwnd=200,
        class_name="QMessageBox", control_type="Window", automation_id=dialog_id,
    ), [body, cancel, yes])
    root = Wrapper(Info(
        name=f"Modal Cancel Fixture Main {nonce}", pid=321, runtime=[-5, 4], hwnd=100,
        class_name="QMainWindow", control_type="Window",
        automation_id=f"QApplication.ModalCancelFixtureMain_{nonce}",
    ), [dialog])
    return root, dialog, body, cancel, yes


class OptInCancelTests(unittest.TestCase):
    def _run(self, root, **overrides):
        Desktop.root_result = root
        output = Path(tempfile.mkdtemp())
        args = _args(output, **overrides)
        native_calls = []

        def native(hwnd):
            native_calls.append(hwnd)
            return 321

        with mock.patch.object(worker, "os", types.SimpleNamespace(name="nt")), \
             mock.patch.object(worker, "_load_dependencies", return_value=(Psutil(), Desktop)), \
             mock.patch.object(worker, "_native_window_pid", side_effect=native):
            result = worker.inspect_target(args)
        return result, native_calls

    def test_opt_in_exact_qt_shape_invokes_cancel_once_and_disappears(self):
        alive = {"value": True}

        def remove_modal():
            alive["value"] = False

        root, dialog, body, cancel, yes = _qt_tree(on_invoke=remove_modal)
        original = root.descendants
        root.descendants = lambda: original() if alive["value"] else []
        result, _ = self._run(root)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["action"], {
            "cancel_attempted": 1, "cancel_completed": 1,
            "yes_attempted": 0, "outcome": "completed",
        })
        self.assertTrue(result["modal_absent"])
        self.assertTrue(result["post_identity_verified"])
        self.assertTrue(result["direct_cancel_invoke"])
        self.assertEqual(result["direct_cancel_invoke_count"], 1)
        self.assertEqual(cancel.invoke_count, 1)
        self.assertEqual(yes.invoke_count, 0)

    def test_default_namespace_remains_read_only_with_explicit_reason(self):
        root, _dialog, _body, cancel, yes = _qt_tree()
        result, _ = self._run(root, cancel_once=False)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertEqual(result["reason"], "Cancel invocation is not enabled")
        self.assertTrue(result["captured_readonly"])
        self.assertEqual(result["action"], {
            "cancel_attempted": 0, "cancel_completed": 0,
            "yes_attempted": 0, "outcome": "not_attempted",
        })
        self.assertFalse(result["modal_absent"])
        self.assertFalse(result["post_identity_verified"])
        self.assertEqual(cancel.invoke_count + yes.invoke_count, 0)

    def test_wrong_nonce_derived_automation_id_blocks_before_cancel(self):
        root, _dialog, _body, cancel, yes = _qt_tree()
        root.element_info.automation_id = "wrong-root-id"
        result, _ = self._run(root)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertEqual(result["action"]["outcome"], "not_attempted")
        self.assertEqual(result["direct_cancel_invoke_count"], 0)
        self.assertEqual(cancel.invoke_count + yes.invoke_count, 0)

    def test_invoke_exception_is_unknown_and_is_not_retried(self):
        def explode():
            raise RuntimeError("invoke exploded")

        root, _dialog, _body, cancel, _yes = _qt_tree(on_invoke=explode)
        with self.assertRaises(worker._WorkerFailure) as caught:
            self._run(root)
        failure = caught.exception
        self.assertEqual(failure.action, {
            "cancel_attempted": 1, "cancel_completed": 0,
            "yes_attempted": 0, "outcome": "unknown",
        })
        self.assertEqual(cancel.invoke_count, 1)
        self.assertIn("cancel_invoke_started", [s["stage"] for s in failure.stages])
        self.assertNotIn("cancel_invoke_completed", [s["stage"] for s in failure.stages])

    def test_post_discovery_error_is_unknown_after_one_cancel(self):
        alive = {"value": True}

        def keep_modal():
            alive["value"] = True

        root, _dialog, _body, cancel, _yes = _qt_tree(on_invoke=keep_modal)
        original = root.descendants
        calls = {"count": 0}

        def descendants():
            calls["count"] += 1
            if calls["count"] >= 4:
                raise RuntimeError("post provider exploded")
            return original()

        root.descendants = descendants
        with self.assertRaises(worker._WorkerFailure) as caught:
            self._run(root)
        self.assertEqual(caught.exception.action, {
            "cancel_attempted": 1, "cancel_completed": 1,
            "yes_attempted": 0, "outcome": "unknown",
        })
        self.assertEqual(cancel.invoke_count, 1)

    def test_supervisor_bounds_cancel_hang_and_preserves_entered_action_stage(self):
        spec = importlib.util.spec_from_file_location("modal_cancel_cancel_supervisor", SUPERVISOR)
        supervisor = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        import sys
        sys.modules[spec.name] = supervisor
        spec.loader.exec_module(supervisor)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            child = root / "hanging_cancel_worker.py"
            child.write_text(
                "import json,time\n"
                "print(json.dumps({'event':'ready'}), flush=True)\n"
                "print(json.dumps({'event':'stage','stage':'cancel_invoke_started',"
                "'action':{'cancel_attempted':1,'cancel_completed':0,"
                "'yes_attempted':0,'outcome':'unknown'},'invoke_count':1}), flush=True)\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            result = supervisor.run_supervised(
                output_dir=root / "run", worker_script=child,
                readiness_timeout=.4, execution_timeout=.15,
                terminate_timeout=.2, kill_timeout=.5,
            )
            self.assertEqual(result.status, "TIMEOUT", result.to_dict())
            self.assertTrue(result.cleanup_verified)
            self.assertIn("cancel_invoke_started", result.stdout)
            self.assertIn("cancel_attempted", result.stdout)
            self.assertIn('"invoke_count": 1', result.stdout)


if __name__ == "__main__":
    unittest.main()
