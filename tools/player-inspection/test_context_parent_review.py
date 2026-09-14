"""Parent regressions from the independent bounded-context review."""
import copy
from pathlib import Path
import unittest
from unittest import mock
import test_bounded_context as fixtures

inspector = fixtures.inspector
EXPECTED = fixtures.EXPECTED


def valid_payload():
    observed = fixtures.worker._validate_context_menu(fixtures._valid_menu(), 4242)
    return {"pid": 4242, "context_menu": {
        "menu_items_invoked": False,
        "stage_diagnostics": {name: True for name in (
            "root_playlist_rows_validated", "focus_and_selection_validated",
            "ownership_before_validated", "keyboard_context_posted_once",
            "fresh_menu_validated", "selection_retained_after_menu")},
        "selected_rows": EXPECTED[:2],
        "selection_state": [True, True, False],
        "selection_after_menu": [True, True, False],
        "menu_items_count": 4,
        "menu_items": observed["menu_items"],
        "menu_root": observed["root"],
        "recognized_items": observed["recognized_items"],
        "ownership_before": {"owned_popup_count": 0, "owned_context_menu_count": 0},
        "ownership_after": {"owned_popup_count": 1, "owned_context_menu_count": 1},
    }}


class ContextParentReviewTests(unittest.TestCase):
    def test_pinned_postcheck_never_substitutes_popup_for_lost_main(self):
        import test_uia_worker_regressions as native
        for changed_owner in (None, 9999):
            owners = {1002: 4242}
            if changed_owner is not None:
                owners[1001] = changed_owner
            api = native._FakeUser32(list(owners), owners)
            processes = native._FakePsutil({4242: native._FakeNativeProcess(4242)})
            with mock.patch.object(inspector, "is_windows_native", return_value=True), mock.patch.object(
                inspector.ctypes, "WinDLL", return_value=api, create=True
            ), self.subTest(owner=changed_owner), self.assertRaises(TimeoutError):
                inspector._discover_owned_main_hwnd(
                    native._FakeProcess(), processes, native.IDENTITY, native.EXE,
                    timeout=.001, poll_interval=0, pinned_hwnd=1001)

    def test_context_postcheck_retains_pinned_main_when_owned_menu_opens(self):
        import test_uia_worker_regressions as native
        api = native._FakeUser32([1001], {1001: 4242}, classes={1001: "Qt6112QWindowIcon"})
        processes = native._FakePsutil({4242: native._FakeNativeProcess(4242)})

        def execute_worker(**kwargs):
            api.windows.append(1002)
            api.owners[1002] = 4242
            api.visible[1002] = True
            api.classes[1002] = "Qt6112QWindowPopup"
            return native._FakeResult(status="SUCCESS", failure_kind=None)

        with mock.patch.object(inspector, "is_windows_native", return_value=True), mock.patch.object(inspector.ctypes, "WinDLL", return_value=api, create=True), mock.patch.object(
            inspector.uia_supervisor, "run_supervised", side_effect=execute_worker
        ):
            try:
                result = inspector._bounded_read_only_snapshot(
                    output=Path("evidence"), process=native._FakeProcess(), psutil=processes,
                    identity=native.IDENTITY, executable=native.EXE, expected_rows=EXPECTED,
                    worker_mode_args=("--context-menu",))
            except Exception as exc:
                self.fail(f"owned popup must not invalidate pinned main postcheck: {exc}")
        self.assertEqual(result["result"]["parent_target_after"]["hwnd"], 1001)

    def test_parent_rejects_bool_pids_and_malformed_runtime_ids(self):
        baseline = valid_payload()
        inspector._validate_bounded_context_payload(baseline, EXPECTED)
        for mutation in ("bool_pid", "string_runtime", "bool_runtime", "empty_runtime", "bool_handle"):
            payload = copy.deepcopy(baseline)
            context = payload["context_menu"]
            if mutation == "bool_pid":
                payload["pid"] = True
                for record in [context["menu_root"], *context["menu_items"],
                               *(entry["record"] for entry in context["recognized_items"])]:
                    record["process_id"] = True
            elif mutation == "bool_handle":
                context["menu_root"]["nativehandle"] = True
            else:
                context["recognized_items"][0]["record"]["runtimeID"] = {
                    "string_runtime": ["not-native"], "bool_runtime": [True], "empty_runtime": []}[mutation]
            with self.subTest(mutation=mutation), self.assertRaises(inspector.ContractError):
                inspector._validate_bounded_context_payload(payload, EXPECTED)

    def test_parent_rejects_generic_menu_outside_observed_qt_identity(self):
        payload = valid_payload()
        inspector._validate_bounded_context_payload(payload, EXPECTED)
        root = payload["context_menu"]["menu_root"]
        root.update(control_type="Menu", class_name="UnrelatedMenu", automation_id="unrelated")
        with self.assertRaises(inspector.ContractError):
            inspector._validate_bounded_context_payload(payload, EXPECTED)

    def test_invalid_payload_preserves_supervisor_diagnostics(self):
        payload = valid_payload()
        inspector._validate_bounded_context_payload(payload, EXPECTED)
        del payload["context_menu"]
        result = {"status": "SUCCESS", "cleanup_verified": True,
                  "stdout": "actual captured worker output", "child_payload": payload}
        with mock.patch.object(inspector, "_bounded_read_only_snapshot", return_value={"result": result}):
            with self.assertRaises(inspector.ContractError) as raised:
                inspector._bounded_context_menu_snapshot(
                    output=Path("evidence"), process=None, psutil=None,
                    identity={"pid": 4242}, executable=Path("player.exe"), expected_rows=EXPECTED)
        self.assertIs(getattr(raised.exception, "supervisor_result", None), result)


if __name__ == "__main__":
    unittest.main()
