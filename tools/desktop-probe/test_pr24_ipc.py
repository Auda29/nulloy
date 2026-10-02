import argparse
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pr24_ipc as ipc


SOURCE_SHA = "be5b1e88286c1ff0bbe7e298e3585bbfb248aba5"


class CaseAndCliContracts(unittest.TestCase):
    def test_cli_has_only_independent_ipc_cases_and_all(self):
        args = ipc.parse_args([
            "--package", "package.zip", "--output", "evidence",
            "--source-sha", SOURCE_SHA,
        ])
        self.assertEqual(args.case, "all")
        self.assertEqual(ipc.selected_cases(args), list(ipc.IPC_CASES))
        self.assertEqual(len(ipc.IPC_CASES), 7)
        for case in ipc.IPC_CASES:
            selected = ipc.parse_args([
                "--package", "package.zip", "--output", "evidence",
                "--source-sha", SOURCE_SHA, "--case", case,
            ])
            self.assertEqual(ipc.selected_cases(selected), [case])

    def test_cli_rejects_legacy_playback_cases(self):
        with self.assertRaises(SystemExit):
            ipc.parse_args([
                "--package", "package.zip", "--output", "evidence",
                "--source-sha", SOURCE_SHA, "--case", "command_next",
            ])


class ReceiptBracketContracts(unittest.TestCase):
    def test_bracket_is_monotonic_and_contains_processing_completion(self):
        bracket = ipc.ReceiptBracket(
            message="one.wav", lower=10.0, upper=10.2,
            kind="file", policy_observed=True, result_observed=True,
        )
        self.assertEqual(bracket.interval, (10.0, 10.2))
        self.assertTrue(bracket.complete)
        with self.assertRaises(ipc.ContractError):
            ipc.ReceiptBracket("bad", 2.0, 1.0, "file", True, True)
        with self.assertRaises(ipc.BlockedError):
            ipc.ReceiptBracket("bad", math.nan, 1.0, "file", True, True)

    def test_short_burst_uses_worst_case_max_gap_and_max_age(self):
        receipts = [
            ipc.ReceiptBracket("one.wav", 0.00, 0.04, "file", True, True),
            ipc.ReceiptBracket("two.wav", 0.10, 0.14, "file", True, True),
            ipc.ReceiptBracket("three.wav", 0.20, 0.24, "file", True, True),
        ]
        result = ipc.classify_receipts(receipts)
        self.assertEqual(result.continuations, [False, True, True])
        self.assertEqual(result.intervals[1]["max_gap"], 0.14)
        self.assertEqual(result.intervals[2]["max_age"], 0.24)
        self.assertTrue(all(item["clock"] == "perf_counter" for item in result.intervals))

    def test_idle_requires_minimum_gap_before_reset(self):
        receipts = [
            ipc.ReceiptBracket("one.wav", 0.00, 0.04, "file", True, True),
            ipc.ReceiptBracket("two.wav", 0.35, 0.39, "file", True, True),
            ipc.ReceiptBracket("three.wav", 0.45, 0.49, "file", True, True),
        ]
        result = ipc.classify_receipts(receipts)
        self.assertEqual(result.continuations, [False, False, True])
        self.assertEqual(result.intervals[1]["reset_reason"], "idle")

    def test_maximum_cap_requires_min_age_and_a_small_max_gap(self):
        receipts = [
            ipc.ReceiptBracket(f"{index}.wav", index / 10, index / 10 + 0.02,
                               "file", True, True)
            for index in range(10)
        ] + [ipc.ReceiptBracket("10.wav", 1.10, 1.12, "file", True, True)]
        result = ipc.classify_receipts(receipts)
        self.assertEqual(result.continuations, [False] + [True] * 9 + [False])
        self.assertEqual(result.intervals[-1]["reset_reason"], "cap")

    def test_command_receipts_are_well_inside_gap_and_total_gates(self):
        brackets = [
            ipc.ReceiptBracket("one.wav", 0.00, 0.04, "file", True, True),
            ipc.ReceiptBracket("--next", 0.10, 0.12, "command", False, False,
                               "command-message-entry-before-next-file"),
            ipc.ReceiptBracket("two.wav", 0.20, 0.24, "file", True, True),
        ]
        timing = ipc.validate_command_brackets(brackets)
        self.assertEqual(timing["clock"], "perf_counter")
        self.assertLess(timing["maximum_gap"], 0.250)
        self.assertLess(timing["maximum_total"], 1.000)

    def test_command_receipt_uncertainty_is_blocked(self):
        brackets = [
            ipc.ReceiptBracket("one.wav", 0.00, 0.20, "file", True, True),
            ipc.ReceiptBracket("--next", 0.10, 0.30, "command", True, True,
                               "command-message-entry-before-next-file"),
            ipc.ReceiptBracket("two.wav", 0.40, 0.60, "file", True, True),
        ]
        with self.assertRaises(ipc.BlockedError):
            ipc.validate_command_brackets(brackets)

    def test_complete_file_trace_requires_policy_and_result(self):
        records = [
            {"event": "player-message", "message": "one.wav"},
            {"event": "player-open-policy", "continuation": False, "enqueue": False},
            {"event": "player-open-result", "rows": ["one.wav"], "playing_row": 0},
        ]
        observed = ipc.extract_complete_file_observations(records, ["one.wav"])
        self.assertEqual(observed[0]["result"]["rows"], ["one.wav"])
        self.assertEqual(observed[0]["result"]["playing_row"], 0)
        self.assertTrue(observed[0]["complete"])

    def test_expected_results_are_independent_of_policy_continuation(self):
        expected = ipc.expected_file_results(["a.wav", "b.wav", "c.wav"])
        self.assertEqual(expected, [
            {"rows": ["a.wav"], "playing_row": 0},
            {"rows": ["b.wav"], "playing_row": 0},
            {"rows": ["c.wav"], "playing_row": 0},
        ])
        self.assertEqual(ipc.expected_final_state(["a.wav", "b.wav"]),
                         {"rows": ["b.wav"], "current_media": "b.wav", "playing_row": 0})

    def test_old_append_results_are_rejected_in_replacement_mode(self):
        observations = [
            {"result": {"rows": ["seed.wav", "one.wav"], "playing_row": 0}},
            {"result": {"rows": ["seed.wav", "one.wav", "two.wav"], "playing_row": 0}},
        ]
        with self.assertRaises(ipc.ContractError):
            ipc.validate_file_results(observations, ["one.wav", "two.wav"])

    def test_command_trace_requires_file_result_after_command_and_false_reset(self):
        records = [
            {"event": "player-message", "message": "one.wav"},
            {"event": "player-open-policy", "continuation": False, "enqueue": False},
            {"event": "player-open-result", "rows": ["one.wav"], "playing_row": 0},
            {"event": "player-message", "message": "--next"},
            {"event": "player-message", "message": "two.wav"},
            {"event": "player-open-policy", "continuation": False, "enqueue": False},
            {"event": "player-open-result", "rows": ["two.wav"], "playing_row": 0},
        ]
        observed = ipc.extract_command_observations(records, ["one.wav", "--next", "two.wav"])
        self.assertEqual(observed["message_sequence"], ["one.wav", "--next", "two.wav"])
        self.assertEqual(observed["file_policies"], [False, False])
        self.assertTrue(observed["command_reset_limited"])

    def test_trace_without_policy_or_result_is_blocked_not_fail(self):
        with self.assertRaises(ipc.BlockedError):
            ipc.extract_complete_file_observations(
                [{"event": "player-message", "message": "one.wav"}], ["one.wav"]
            )


class SetupAndRunnerContracts(unittest.TestCase):
    def test_setup_forces_enqueue_false_at_isolated_config_seam(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = object.__new__(ipc.IPCPlaybackCaseRun)
            runtime.package = SimpleNamespace(contract=SimpleNamespace(portable=True), root=root, executable=Path("Nulloy.exe"))
            runtime.evidence = root / "evidence"
            runtime.evidence.mkdir()
            runtime.spec = SimpleNamespace(name="ipc_short")
            settings = "[General]\nEnqueueFiles=true\nOther=true\n"
            with patch.object(ipc.playback, "_wav_playlist"):
                ipc.IPCPlaybackCaseRun._write_setup(runtime, settings, [])
            written = (runtime.evidence / "scenario-settings.cfg").read_text(encoding="utf-8")
            self.assertIn("EnqueueFiles=false", written)
            self.assertNotIn("EnqueueFiles=true", written)

    def test_runner_preserves_exact_package_provenance_and_case_name(self):
        self.assertIn("ipc_short", ipc.IPC_CASES)
        self.assertEqual(ipc.CASE_GROUP, "ipc")
        self.assertEqual(ipc.RESULT_SCHEMA_VERSION, 1)


class IndependentOracleReview(unittest.TestCase):
    def test_short_burst_keeps_all_rows_not_original_per_message_bug(self):
        expected=ipc.expected_file_results(['a','b','c'],[False,True,True])
        self.assertEqual(expected,[dict(rows=['a'],playing_row=0),dict(rows=['a','b'],playing_row=0),dict(rows=['a','b','c'],playing_row=0)])
        observations=[dict(result=dict(event='player-open-result',time_msec=1,**r)) for r in expected]
        ipc.validate_file_results(observations,['a','b','c'],[False,True,True])
        observations[1]['result']['rows']=['b']
        with self.assertRaises(ipc.ContractError):
            ipc.validate_file_results(observations,['a','b','c'],[False,True,True])

    def test_idle_and_cap_reset_only_once_independent_of_actual_policy(self):
        self.assertEqual(ipc.expected_file_results(['a','b','c'],[False,False,True])[-1]['rows'],['b','c'])
        self.assertEqual(ipc.expected_file_results(['a','b','c'],[False,True,False])[-1]['rows'],['c'])

    def test_command_entire_file_to_file_gap_must_be_within_idle(self):
        brackets=[ipc.ReceiptBracket('a',0,.02,'file',True,True),
                  ipc.ReceiptBracket('--stop',.15,.17,'command',False,False,'command-message-entry-before-next-file'),
                  ipc.ReceiptBracket('b',.3,.32,'file',True,True)]
        with self.assertRaises(ipc.BlockedError):
            ipc.validate_command_brackets(brackets)

    def test_empty_startup_activation_is_not_an_ipc_file(self):
        self.assertEqual(ipc._message_rows([dict(event='player-message',message='')]),[])

if __name__ == "__main__":
    unittest.main()
