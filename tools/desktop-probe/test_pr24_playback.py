import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pr24_playback as probe


SOURCE_SHA = "be5b1e88286c1ff0bbe7e298e3585bbfb248aba5"


class CliAndMatrixContracts(unittest.TestCase):
    def test_cli_defaults_to_all_and_accepts_ci_groups(self):
        args = probe.parse_args([
            "--package", "package.zip", "--output", "evidence",
            "--source-sha", SOURCE_SHA,
        ])
        self.assertEqual(args.case, "all")
        self.assertEqual(args.group, "all")
        self.assertEqual(
            [probe.CASES_BY_GROUP[group] for group in probe.GROUPS if group != "all"],
            [probe.CASES_BY_GROUP[group] for group in ("populated", "restored", "rapid", "commands")],
        )

    def test_group_selects_only_its_cases_and_case_is_exact(self):
        args = probe.parse_args([
            "--package", "package.zip", "--output", "evidence",
            "--source-sha", SOURCE_SHA, "--group", "rapid",
        ])
        self.assertEqual(args.group, "rapid")
        self.assertEqual(probe.selected_cases(args), probe.CASES_BY_GROUP["rapid"])
        one = probe.parse_args([
            "--package", "package.zip", "--output", "evidence",
            "--source-sha", SOURCE_SHA, "--case", "rapid_open_boundary",
        ])
        self.assertEqual(probe.selected_cases(one), ["rapid_open_boundary"])

    def test_case_and_group_conflict_is_rejected(self):
        with self.assertRaises(SystemExit):
            probe.parse_args([
                "--package", "package.zip", "--output", "evidence",
                "--source-sha", SOURCE_SHA, "--group", "rapid", "--case", "command_next",
            ])

    def test_matrix_is_twelve_populated_state_policy_cases_plus_restored_rapid_commands(self):
        self.assertEqual(len(probe.CASES_BY_GROUP["populated"]), 12)
        self.assertEqual(len(probe.CASES_BY_GROUP["restored"]), 12)
        self.assertGreaterEqual(len(probe.CASES_BY_GROUP["rapid"]), 3)
        self.assertGreaterEqual(len(probe.CASES_BY_GROUP["commands"]), 4)
        self.assertEqual(set(probe.all_case_names()), set(sum(
            (probe.CASES_BY_GROUP[group] for group in probe.GROUPS if group != "all"), []
        )))


class ObservationContracts(unittest.TestCase):
    def test_playback_state_requires_direct_position_observations(self):
        self.assertEqual(probe.classify_state([0.10, 0.11, 0.12]), "playing")
        self.assertEqual(probe.classify_state([0.42, 0.42, 0.42]), "paused")
        self.assertEqual(probe.classify_state([0.0, 0.0, 0.0]), "stopped")
        with self.assertRaises(probe.ContractError):
            probe.classify_state([])
        with self.assertRaises(probe.ContractError):
            probe.classify_state([0.2, 0.2, 0.3])

    def test_current_row_is_not_derived_from_selected_row(self):
        with self.assertRaises(probe.ContractError):
            probe.require_current_media("", ["desktop-probe-01.wav"])
        self.assertEqual(
            probe.require_current_media("desktop-probe-02.wav", ["desktop-probe-01.wav", "desktop-probe-02.wav"]),
            "desktop-probe-02.wav",
        )

    def test_position_observation_rejects_missing_or_ambiguous_text(self):
        self.assertEqual(probe.parse_position_text("1:23"), 83)
        with self.assertRaises(probe.ContractError):
            probe.parse_position_text("")
        with self.assertRaises(probe.ContractError):
            probe.parse_position_text("not-a-time")
        with self.assertRaises(probe.ContractError):
            probe.choose_position_text(["0:01", "0:02"])

    def test_boundary_window_is_strict_and_non_sliding(self):
        self.assertTrue(probe.within_boundary_window(0.249, 0.999))
        self.assertFalse(probe.within_boundary_window(0.250, 0.999))
        self.assertFalse(probe.within_boundary_window(0.251, 0.999))
        self.assertFalse(probe.within_boundary_window(0.249, 1.000))
        self.assertTrue(probe.within_boundary_window(0.100, 0.050))
        self.assertEqual(probe.rapid_continuations([0.0, 0.1, 0.4]), [False, True, False])
        with self.assertRaises(probe.ContractError):
            probe.rapid_continuations([0.0, float("nan")])


class FixtureAndPersistenceContracts(unittest.TestCase):
    def test_fixtures_are_pcm_and_at_least_two_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixtures = probe.make_long_fixtures(Path(tmp) / "fixtures", 2)
            self.assertEqual(len(fixtures), 2)
            for fixture in fixtures:
                with wave.open(str(fixture), "rb") as source:
                    self.assertEqual(source.getcomptype(), "NONE")
                    self.assertGreaterEqual(source.getnframes() / source.getframerate(), 120.0)

    def test_settings_round_trip_has_per_row_display_and_restore_state(self):
        settings = probe.playback_settings(
            enqueue=False, play_enqueued=True, restore=True,
            start_paused=True, row=1, position=0.37,
        )
        self.assertIn("PlaylistTrackInfo=%i - %F", settings)
        self.assertIn("[TrackInfo]\n", settings)
        self.assertIn("MiddleRight=%T", settings)
        self.assertIn("PlaylistRow=1,0.37", settings)
        self.assertEqual(probe.read_persisted_row(settings), (1, 0.37))
        with self.assertRaises(probe.ContractError):
            probe.read_persisted_row(settings.replace("PlaylistRow=1,0.37", "PlaylistRow=bad"))

    def test_summary_is_fail_closed_for_blocked_or_failed_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = probe.write_summary(Path(tmp), [
                {"case": "one", "status": "PASS", "cleanup_verified": True},
                {"case": "two", "status": "BLOCKED", "cleanup_verified": True},
            ], group="rapid")
            self.assertEqual(summary["status"], "BLOCKED")
            self.assertEqual(summary["counts"], {"PASS": 1, "BLOCKED": 1})
            self.assertFalse(summary["cleanup_verified"])
            self.assertEqual(json.loads((Path(tmp) / "summary.json").read_text())["cases"][1]["status"], "BLOCKED")


class CommandContracts(unittest.TestCase):
    def test_command_case_names_and_option_mapping_are_explicit(self):
        for name, option in {
            "command_next": "--next",
            "command_prev": "--prev",
            "command_stop": "--stop",
            "command_pause": "--pause",
        }.items():
            self.assertIn(name, probe.CASES_BY_GROUP["commands"])
            self.assertEqual(probe.command_option(name), option)
        self.assertEqual(probe.command_option("command_pause"), "--pause")

    def test_command_observation_does_not_accept_selected_row_as_state(self):
        observation = SimpleNamespace(current_media="", selected_row="desktop-probe-01.wav", position=None)
        with self.assertRaises(probe.ContractError):
            probe.validate_command_observation(observation)


if __name__ == "__main__":
    unittest.main()
