"""Strict controller acceptance and explicit one-Cancel opt-in tests."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from test_controller_observations import native_observations


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("modal_controller_cancel", HERE / "controller.py")
controller = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(controller)


class ControllerCancelContractTests(unittest.TestCase):
    nonce = "modal-testnonce"
    expected = (1234, 1.0, "fixture")

    def state(self, *, phase="cancelled", dialog_open=False, dialog_closed=True,
              cancel_count=1, yes_count=0):
        return {
            "nonce": self.nonce,
            "parent_pid": controller.os.getpid(),
            "pid": 1234,
            "create_time": 1.0,
            "executable": "fixture",
            "hwnd": 222,
            "qt_version": "6.8.2",
            "qt_platform": "offscreen",
            "main_title": f"Modal Cancel Fixture Main {self.nonce}",
            "dialog_title": f"Modal Cancel Fixture {self.nonce}",
            "dialog_body": f"Benign modal cancellation test {self.nonce}",
            "heartbeat": 4,
            "monotonic": 4.0,
            "phase": phase,
            "dialog_open": dialog_open,
            "dialog_closed": dialog_closed,
            "cancel_count": cancel_count,
            "yes_count": yes_count,
        }

    def counters(self, *, cancel=1, yes=0, dialog_closed=True):
        return {"cancel": cancel, "yes": yes, "dialog_closed": dialog_closed, "nonce": self.nonce}

    def payload(self, *, status="PASS", action=None, captured_readonly=False,
                native_acceptance=True):
        action = action or {
            "cancel_attempted": 1,
            "cancel_completed": 1,
            "yes_attempted": 0,
            "outcome": "completed",
        }
        return {
            "status": status,
            "captured_readonly": captured_readonly,
            "native_acceptance": native_acceptance,
            "modal_absent": not captured_readonly,
            "post_identity_verified": not captured_readonly,
            "direct_cancel_invoke": True,
            "direct_cancel_invoke_count": 1,
            "yes_invoke_count": 0,
            "action": action,
            "observations": native_observations(
                nonce=self.nonce, pid=1234, root_hwnd=222, dialog_hwnd=333,
            ),
        }

    def result(self, payload):
        report = {
            "status": "SUCCESS",
            "success": True,
            "cleanup_verified": True,
            "secondary_errors": [],
            "child_payload": payload,
        }
        return SimpleNamespace(
            status="SUCCESS", success=True, cleanup_verified=True,
            secondary_errors=[], child_payload=payload,
            to_dict=lambda: report,
        )

    def test_valid_cancel_payload_is_accepted(self):
        state = self.state()
        payload = self.payload()
        self.assertTrue(controller._validate_native_acceptance(
            self.result(payload), state, self.counters(), self.nonce,
            fixture_postcheck_verified=True, cancel_once=True,
        ))

    def test_canonical_fields_do_not_require_provider_aliases(self):
        payload = self.payload()
        for observed in (
            payload["observations"]["root"], payload["observations"]["dialog"],
            payload["observations"]["body"], payload["observations"]["buttons"]["Cancel"],
            payload["observations"]["buttons"]["Yes"],
        ):
            for alias in ("pid", "class", "controltype", "auto_id", "raw_visibility", "runtime_ids"):
                observed.pop(alias, None)
        self.assertTrue(controller._validate_native_acceptance(
            self.result(payload), self.state(), self.counters(), self.nonce,
            fixture_postcheck_verified=True, cancel_once=True,
        ))

    def test_pass_shaped_payload_without_actual_action_is_rejected(self):
        payload = self.payload(action=None)
        payload.pop("action")
        self.assertFalse(controller._validate_native_acceptance(
            self.result(payload), self.state(), self.counters(), self.nonce,
            fixture_postcheck_verified=True, cancel_once=True,
        ))

    def test_complete_native_observation_mutations_are_rejected(self):
        def missing_body(observations):
            del observations["body"]

        def missing_buttons(observations):
            del observations["buttons"]

        def foreign_pid(observations):
            observations["body"]["process_id"] = 999

        def malformed_pid_alias(observations):
            observations["body"]["pid"] = True

        def wrong_observation_role(observations):
            observations["body"]["observation_role"] = "dialog"

        def malformed_visibility(observations):
            observations["body"]["visible"] = "true"

        def malformed_runtime(observations):
            observations["body"]["runtime_id"] = [True]

        def mismatched_runtime_alias(observations):
            observations["body"]["runtime_ids"] = []

        def wrong_class(observations):
            observations["body"]["class_name"] = "QPushButton"

        def wrong_automation_id(observations):
            observations["body"]["automation_id"] = "not-the-Qt-id"

        def missing_root_hwnd(observations):
            del observations["root"]["hwnd"]

        def child_has_hwnd(observations):
            observations["body"]["hwnd"] = 1

        def wrong_root_owner(observations):
            observations["root"]["native_owner_pid"] = 999

        def wrong_dialog_owner(observations):
            observations["dialog"]["native_owner_pid"] = 999

        def invisible_root(observations):
            observations["root"]["visible"] = False

        def duplicate_button_runtime(observations):
            observations["buttons"]["Yes"]["runtime_id"] = copy.deepcopy(
                observations["buttons"]["Cancel"]["runtime_id"]
            )

        def mislabeled_cancel(observations):
            observations["buttons"]["Cancel"]["name"] = "Yes"

        mutations = (
            ("missing body", missing_body),
            ("missing buttons", missing_buttons),
            ("foreign PID", foreign_pid),
            ("malformed PID alias", malformed_pid_alias),
            ("wrong observation role", wrong_observation_role),
            ("malformed visibility", malformed_visibility),
            ("malformed RuntimeId", malformed_runtime),
            ("mismatched RuntimeId alias", mismatched_runtime_alias),
            ("wrong class", wrong_class),
            ("wrong automation ID", wrong_automation_id),
            ("missing root HWND", missing_root_hwnd),
            ("child HWND", child_has_hwnd),
            ("wrong root owner PID", wrong_root_owner),
            ("wrong dialog owner PID", wrong_dialog_owner),
            ("invisible root", invisible_root),
            ("duplicate button RuntimeId", duplicate_button_runtime),
            ("mislabeled Cancel", mislabeled_cancel),
        )
        for label, mutate in mutations:
            with self.subTest(observation=label):
                payload = self.payload()
                mutate(payload["observations"])
                self.assertFalse(controller._validate_native_acceptance(
                    self.result(payload), self.state(), self.counters(), self.nonce,
                    fixture_postcheck_verified=True, cancel_once=True,
                ))

        mutations = (
            ("pid", True),
            ("hwnd", "222"),
            ("cancel_count", "1"),
            ("nonce", "wrong-nonce"),
            ("phase", "dialog_open"),
            ("dialog_closed", 1),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                state = self.state()
                state[field] = value
                self.assertFalse(controller._validate_native_acceptance(
                    self.result(self.payload()), state, self.counters(), self.nonce,
                    fixture_postcheck_verified=True, cancel_once=True,
                ))

    def test_each_action_mutation_is_rejected(self):
        mutations = (
            {"cancel_attempted": True, "cancel_completed": 1, "yes_attempted": 0, "outcome": "completed"},
            {"cancel_attempted": 1, "cancel_completed": "1", "yes_attempted": 0, "outcome": "completed"},
            {"cancel_attempted": 1, "cancel_completed": 1, "yes_attempted": 1, "outcome": "completed"},
            {"cancel_attempted": 1, "cancel_completed": 1, "yes_attempted": 0, "outcome": "unknown"},
        )
        for action in mutations:
            with self.subTest(action=action):
                self.assertFalse(controller._validate_native_acceptance(
                    self.result(self.payload(action=action)), self.state(), self.counters(), self.nonce,
                    fixture_postcheck_verified=True, cancel_once=True,
                ))

    def test_readonly_block_is_partial_only_with_exact_no_action(self):
        state = self.state(phase="dialog_open", dialog_open=True, dialog_closed=False,
                           cancel_count=0, yes_count=0)
        counters = self.counters(cancel=0, yes=0, dialog_closed=False)
        payload = self.payload(status="BLOCKED", captured_readonly=True, native_acceptance=False,
                               action={"cancel_attempted": 0, "cancel_completed": 0,
                                       "yes_attempted": 0, "outcome": "not_attempted"})
        payload["direct_cancel_invoke"] = False
        payload["direct_cancel_invoke_count"] = 0
        payload["modal_absent"] = False
        payload["post_identity_verified"] = False
        self.assertTrue(controller._validate_readonly_block(
            payload, state, counters, self.nonce,
        ))
        payload["action"]["cancel_attempted"] = 1
        self.assertFalse(controller._validate_readonly_block(payload, state, counters, self.nonce))

    def test_cancel_once_block_can_never_be_partial(self):
        payload = self.payload(status="BLOCKED", captured_readonly=True, native_acceptance=False,
                               action={"cancel_attempted": 0, "cancel_completed": 0,
                                       "yes_attempted": 0, "outcome": "not_attempted"})
        self.assertFalse(controller._validate_native_acceptance(
            self.result(payload), self.state(phase="dialog_open", dialog_open=True,
                                         dialog_closed=False, cancel_count=0, yes_count=0),
            self.counters(cancel=0, yes=0, dialog_closed=False), self.nonce,
            fixture_postcheck_verified=True, cancel_once=True,
        ))

    def test_cli_opt_in_is_forwarded_and_default_is_readonly(self):
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(
                controller, "os", SimpleNamespace(name="nt", getpid=__import__("os").getpid)), \
                mock.patch.object(controller, "run_native", return_value={"status": "FAIL"}) as run:
            controller.main(["--evidence-root", raw])
            controller.main(["--evidence-root", raw, "--cancel-once"])
        self.assertEqual(run.call_args_list[0].kwargs, {"cancel_once": False})
        self.assertEqual(run.call_args_list[1].kwargs, {"cancel_once": True})

    def test_worker_cancel_flag_is_added_only_for_explicit_opt_in(self):
        captured = []
        state = self.state(phase="dialog_open", dialog_open=True, dialog_closed=False,
                           cancel_count=0, yes_count=0)
        checks = {"state": state, "counters": self.counters(cancel=0, yes=0, dialog_closed=False)}
        process = mock.Mock(pid=1234)
        process.poll.return_value = None
        blocked_payload = self.payload(
            status="BLOCKED", captured_readonly=True, native_acceptance=False,
            action={"cancel_attempted": 0, "cancel_completed": 0,
                    "yes_attempted": 0, "outcome": "not_attempted"},
        )
        blocked_payload["direct_cancel_invoke"] = False
        blocked_payload["direct_cancel_invoke_count"] = 0
        blocked_payload["modal_absent"] = False
        blocked_payload["post_identity_verified"] = False
        result = SimpleNamespace(
            status="BLOCKED", success=False, cleanup_verified=True, secondary_errors=[],
            child_payload=blocked_payload, to_dict=lambda: {},
        )

        def run_supervised(**kwargs):
            captured.append(tuple(kwargs["worker_args"]))
            return result

        def invoke(cancel_once):
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw) / "fixture"
                root.mkdir()
                (root / "sentinel.bin").write_bytes(b"sentinel")
                with mock.patch.object(
                        controller, "os", SimpleNamespace(name="nt", getpid=__import__("os").getpid)), \
                        mock.patch.object(controller, "_nonce", return_value=self.nonce), \
                        mock.patch.object(controller, "_start_fixture", return_value=(process, root, self.expected)), \
                        mock.patch.object(controller, "_await_state", return_value=state), \
                        mock.patch.object(controller, "_common_fixture_checks", return_value=checks), \
                        mock.patch.object(controller, "_native_owner_pid", return_value=1234), \
                        mock.patch.object(controller, "_load_supervisor", return_value=SimpleNamespace(run_supervised=run_supervised)), \
                        mock.patch.object(controller, "_cleanup", return_value={"cleanup_verified": True, "errors": []}):
                    controller.run_native(Path(raw) / "output", cancel_once=cancel_once)

        invoke(False)
        invoke(True)
        self.assertNotIn("--cancel-once", captured[0])
        self.assertIn("--cancel-once", captured[1])


if __name__ == "__main__":
    unittest.main()
