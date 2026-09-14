"""Behavioral regressions for the bounded context worker review findings."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


worker = _load("context_worker_review_worker", HERE / "uia_worker.py")
fixtures = _load("context_worker_review_fixtures", HERE / "test_bounded_context.py")
EXPECTED = fixtures.EXPECTED


class ContextIdentityReviewTests(unittest.TestCase):
    def test_generic_menu_root_is_rejected_by_validator_and_discovery(self):
        menu = fixtures._Menu(
            fixtures._valid_menu().children,
            control_type="Menu",
            class_name="UnrelatedMenu",
            automation_id="unrelated",
        )
        with self.assertRaises(worker._OwnershipError):
            worker._validate_context_menu(menu, 4242)

        class Desktop:
            def windows(self):
                return [fixtures._Root(fixtures._Playlist([])), menu]

        main = Desktop().windows()[0]
        with self.assertRaises(worker._OwnershipError):
            worker._owned_context_menus(Desktop(), main, 4242)

    def test_context_records_require_raw_positive_python_pid(self):
        item = fixtures._valid_menu().children[0]
        item.element_info.process_id = "4242"
        with self.assertRaises(worker._OwnershipError):
            worker._context_record(item, 4242)
        item.element_info.process_id = True
        with self.assertRaises(worker._OwnershipError):
            worker._context_record(item, 4242)
        item.element_info.process_id = 0
        with self.assertRaises(worker._OwnershipError):
            worker._context_record(item, 4242)

    def test_context_records_require_nonempty_signed_int_runtime_ids(self):
        menu = fixtures._valid_menu()
        menu.element_info.runtime_id = (-2147483648, -1, 0, 2147483647)
        observed = worker._validate_context_menu(menu, 4242)
        self.assertEqual(observed["root"]["runtimeID"], [-2147483648, -1, 0, 2147483647])

        for runtime_id in ((), [], ("not-native",), (2147483648,), (-2147483649,), (True,)):
            with self.subTest(runtime_id=runtime_id):
                bad = fixtures._valid_menu()
                bad.element_info.runtime_id = runtime_id
                with self.assertRaises(worker._OwnershipError):
                    worker._validate_context_menu(bad, 4242)

    def test_child_without_native_handle_is_allowed_but_root_handle_is_strict(self):
        observed = worker._validate_context_menu(fixtures._valid_menu(), 4242)
        self.assertEqual([item["nativehandle"] for item in observed["menu_items"]], [0, 0, 0, 0])
        for handle in (None, 0, False, "1002"):
            with self.subTest(handle=handle):
                bad = fixtures._valid_menu()
                bad.element_info.handle = handle
                with self.assertRaises(worker._OwnershipError):
                    worker._validate_context_menu(bad, 4242)


class ContextStageReviewTests(unittest.TestCase):
    def _fixture(self):
        actions = []
        rows = []
        rows.extend(fixtures._Row(name, rows, actions) for name in EXPECTED)
        playlist = fixtures._Playlist(rows)
        playlist.element_info.element = fixtures._NativeElement(actions)
        root = fixtures._Root(playlist)
        desktop = fixtures._Desktop(root)
        menu = fixtures._valid_menu()
        return actions, rows, playlist, root, desktop, menu

    def test_context_worker_emits_started_and_completed_events_in_order(self):
        actions, rows, playlist, root, desktop, menu = self._fixture()
        events = []

        def emit(value):
            events.append(value)

        def post(hwnd):
            desktop.windows_now.append(menu)

        with mock.patch.object(
            worker, "_native_window_info", return_value={"hwnd": 1001, "pid": 4242, "visible": True}
        ), mock.patch.object(worker, "_validate_main_root", return_value=root), mock.patch.object(
            worker, "_emit", side_effect=events.append
        ):
            worker._context_inspect_once(
                desktop, fixtures._PlayerProcess(), {"pid": 4242, "create_time": 12.5},
                "C:/Nulloy/Nulloy.exe", 1001, EXPECTED, emit,
                post_context=post, context_timeout=.2,
            )

        stage_events = [event for event in events if event.get("event") == "stage"]
        self.assertEqual(
            [(event["stage"], event["phase"]) for event in stage_events],
            [(stage, status) for stage in (
                "root/readiness", "focus-selection", "ownership", "postcontext",
                "menu-discovery", "finalselection",
            ) for status in ("started", "completed")],
        )

    def test_real_context_worker_timeout_retains_prior_stage_events(self):
        with tempfile.TemporaryDirectory(prefix="context-worker-stage-hang-") as raw:
            root = Path(raw)
            child = root / "actual_context_inspect_once.py"
            child.write_text(textwrap.dedent(f"""
                import importlib.util
                import sys
                import time
                from pathlib import Path
                HERE = Path({str(HERE)!r})
                spec = importlib.util.spec_from_file_location("actual_worker", HERE / "uia_worker.py")
                worker = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = worker
                spec.loader.exec_module(worker)
                fixtures_spec = importlib.util.spec_from_file_location("actual_fixtures", HERE / "test_bounded_context.py")
                fixtures = importlib.util.module_from_spec(fixtures_spec)
                sys.modules[fixtures_spec.name] = fixtures
                fixtures_spec.loader.exec_module(fixtures)
                print('{{"event":"ready"}}', flush=True)
                actions = []
                rows = []
                rows.extend(fixtures._Row(name, rows, actions) for name in fixtures.EXPECTED)
                playlist = fixtures._Playlist(rows)
                playlist.element_info.element = fixtures._NativeElement(actions)
                main = fixtures._Root(playlist)
                desktop = fixtures._Desktop(main)
                def hang_at_menu_wait(*args, **kwargs):
                    time.sleep(30)
                worker._wait_for_context_menu = hang_at_menu_wait
                worker._native_window_info = lambda *args, **kwargs: {{"hwnd": 1001, "pid": 4242, "visible": True}}
                worker._validate_main_root = lambda root, pid, hwnd: root
                def post(hwnd):
                    pass
                worker._context_inspect_once(
                    desktop, fixtures._PlayerProcess(), {{"pid": 4242, "create_time": 12.5}},
                    "C:/Nulloy/Nulloy.exe", 1001, fixtures.EXPECTED, lambda value: None,
                    post_context=post, context_timeout=.2,
                )
            """), encoding="utf-8")
            supervisor = _load("context_worker_review_supervisor", HERE / "uia_supervisor.py")
            result = supervisor.run_supervised(
                output_dir=root / "run",
                worker_script=child,
                readiness_timeout=.5,
                execution_timeout=.2,
                terminate_timeout=.2,
                kill_timeout=.2,
            )
            self.assertEqual(result.status, "TIMEOUT")
            self.assertTrue(result.cleanup_verified)
            self.assertEqual(result.timeout_phase, "execution")
            self.assertIsNotNone(result.returncode)
            lines = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
            stages = [(line.get("stage"), line.get("phase")) for line in lines if line.get("event") == "stage"]
            self.assertIn(("postcontext", "started"), stages)
            self.assertIn(("postcontext", "completed"), stages)
            self.assertIn(("menu-discovery", "started"), stages)
            self.assertNotIn(("menu-discovery", "completed"), stages)
            self.assertIn(("ownership", "completed"), stages)
            self.assertIn(("focus-selection", "completed"), stages)
            self.assertEqual(result.child_payload, {})
            self.assertNotEqual(result.child_payload.get("status"), "PASS")


if __name__ == "__main__":
    unittest.main()
