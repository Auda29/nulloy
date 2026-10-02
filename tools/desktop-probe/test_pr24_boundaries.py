import unittest

import pr24_playback as probe



def trace_record(event, time_msec, **fields):
    return {"event": event, "time_msec": time_msec, **fields}


class PlayerTraceBoundaryContracts(unittest.TestCase):
    def test_rapid_analysis_uses_player_receipt_trace_and_marks_wall_clock_blocked(self):
        traces = {
            "primary": [
                trace_record("player-message", 1000, message="one.wav"),
                trace_record("player-open-policy", 1001, enqueue=True, play_enqueued=False,
                             continuation=False),
                trace_record("player-open-result", 1002, rows=["one.wav"], playing_row=0),
                trace_record("player-message", 1180, message="two.wav"),
                trace_record("player-open-policy", 1181, enqueue=True, play_enqueued=False,
                             continuation=True),
                # Deliberately keep the result identical to a different grouping.
                trace_record("player-open-result", 1182, rows=["one.wav", "two.wav"], playing_row=0),
            ]
        }

        observation = probe.analyze_player_trace(traces, ["one.wav", "two.wav"])

        self.assertEqual(observation["receipt_source"], "player-trace:time_msec")
        self.assertEqual(observation["continuations"], [False, True])
        self.assertFalse(observation["boundary_supported"])
        self.assertEqual(observation["results"][-1]["rows"], ["one.wav", "two.wav"])

    def test_absolute_cap_fixture_has_eight_receipts_at_about_180ms(self):
        records = []
        for index in range(8):
            when = 1000 + index * 180
            records.extend([
                trace_record("player-message", when, message=f"{index}.wav"),
                trace_record("player-open-policy", when + 1, enqueue=True,
                             play_enqueued=False, continuation=(index not in (0, 6))),
                trace_record("player-open-result", when + 2,
                             rows=[f"{item}.wav" for item in range(index + 1)], playing_row=0),
            ])

        observation = probe.analyze_player_trace(
            {"primary": records}, [f"{index}.wav" for index in range(8)]
        )

        self.assertEqual(len(observation["messages"]), 8)
        self.assertEqual(observation["continuations"],
                         [False, True, True, True, True, True, False, True])
        self.assertFalse(observation["boundary_supported"])
        self.assertEqual(observation["receipt_intervals_msec"], [180] * 7)

    def test_grouping_is_not_inferred_from_enqueue_playlist_result(self):
        traces = {
            "primary": [
                trace_record("player-message", 1000, message="one.wav"),
                trace_record("player-open-policy", 1001, enqueue=True,
                             play_enqueued=False, continuation=False),
                trace_record("player-open-result", 1002, rows=["one.wav"], playing_row=0),
                trace_record("player-message", 1100, message="two.wav"),
                trace_record("player-open-policy", 1101, enqueue=True,
                             play_enqueued=False, continuation=False),
                trace_record("player-open-result", 1102,
                             rows=["one.wav", "two.wav"], playing_row=0),
            ]
        }

        observation = probe.analyze_player_trace(traces, ["one.wav", "two.wav"])

        self.assertEqual(observation["continuations"], [False, False])
        self.assertEqual(observation["results"][0]["rows"] + ["two.wav"],
                         observation["results"][1]["rows"])
        self.assertNotEqual(observation["continuations"], [False, True])


class CommandTraceContracts(unittest.TestCase):
    def test_file_option_file_is_immediate_and_command_resets_burst(self):
        traces = {
            "primary": [
                trace_record("player-message", 1000, message="one.wav"),
                trace_record("player-open-policy", 1001, enqueue=True,
                             play_enqueued=False, continuation=False),
                trace_record("player-open-result", 1002, rows=["seed.wav", "one.wav"], playing_row=0),
                trace_record("player-message", 1100, message="--next"),
                trace_record("player-message", 1200, message="two.wav"),
                trace_record("player-open-policy", 1201, enqueue=True,
                             play_enqueued=False, continuation=False),
                trace_record("player-open-result", 1202,
                             rows=["seed.wav", "one.wav", "two.wav"], playing_row=0),
            ]
        }

        observation = probe.analyze_command_trace(
            traces, ["one.wav", "--next", "two.wav"]
        )

        self.assertEqual(observation["message_sequence"], ["one.wav", "--next", "two.wav"])
        self.assertEqual(observation["file_continuations"], [False, False])
        self.assertTrue(observation["command_immediate"])
        self.assertTrue(observation["no_late_open_before_new_file"])

    def test_missing_player_trace_is_blocked_not_a_product_failure(self):
        with self.assertRaises(probe.BlockedError):
            probe.analyze_player_trace({}, ["one.wav"])


if __name__ == "__main__":
    unittest.main()
