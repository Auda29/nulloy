#!/usr/bin/env python3
"""Native Windows PR24 playback acceptance for the exact packaged player.

The Linux part of this module validates the CLI, case matrix, fixture/settings
contracts, and fail-closed observation helpers.  Native cases run in a fresh
supervised child process.  Each child uses the existing ``probe.py`` package,
Explorer, registry, UIA, and identity-safe cleanup helpers; no product source
or installed user profile is changed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import wave
from typing import Any, Iterable, Sequence

import probe


GROUPS = ("populated", "restored", "rapid", "commands", "all")
FIXTURE_SAMPLE_RATE = 44100
FIXTURE_SECONDS = 125
IDLE_BOUNDARY_SECONDS = 0.250
MAXIMUM_BURST_SECONDS = 1.000
CASE_TIMEOUT_SECONDS = 75
TIME_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")


class ContractError(ValueError):
    """Evidence or input does not prove the requested acceptance invariant."""


class BlockedError(RuntimeError):
    """The native acceptance cannot safely run in this environment."""


@dataclasses.dataclass(frozen=True)
class CaseSpec:
    name: str
    group: str
    enqueue: bool = True
    play_enqueued: bool = False
    initial_state: str | None = None
    restored: bool = False
    rapid_mode: str | None = None
    command: str | None = None



def _make_cases() -> tuple[dict[str, list[str]], dict[str, CaseSpec]]:
    groups: dict[str, list[str]] = {group: [] for group in GROUPS}
    specs: dict[str, CaseSpec] = {}
    for enqueue in (False, True):
        for play_enqueued in (False, True):
            for state in ("playing", "paused", "stopped"):
                name = (
                    f"populated_enqueue_{str(enqueue).lower()}_"
                    f"play_{str(play_enqueued).lower()}_{state}"
                )
                spec = CaseSpec(name, "populated", enqueue, play_enqueued, state)
                groups["populated"].append(name)
                specs[name] = spec
    for enqueue in (False, True):
        for play_enqueued in (False, True):
            for state in ("playing", "paused", "stopped"):
                name = f"restored_enqueue_{str(enqueue).lower()}_play_{str(play_enqueued).lower()}_{state}"
                groups['restored'].append(name)
                specs[name] = CaseSpec(name, 'restored', enqueue, play_enqueued, state, restored=True)
    rapid = (
        ("rapid_open_boundary", "burst"),
        ("rapid_idle_boundary", "idle"),
        ("rapid_total_boundary", "total"),
    )
    for name, mode in rapid:
        groups["rapid"].append(name)
        specs[name] = CaseSpec(name, "rapid", enqueue=True, rapid_mode=mode)
    for name, option in (
        ("command_next", "--next"),
        ("command_prev", "--prev"),
        ("command_stop", "--stop"),
        ("command_pause", "--pause"),
    ):
        groups["commands"].append(name)
        specs[name] = CaseSpec(name, "commands", command=option)
    groups["all"] = [name for group in GROUPS[:-1] for name in groups[group]]
    return groups, specs


CASES_BY_GROUP, CASE_SPECS = _make_cases()


def all_case_names() -> list[str]:
    return list(CASES_BY_GROUP["all"])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--case", choices=("all", *all_case_names()), default="all")
    parser.add_argument("--group", choices=GROUPS, default="all")
    parser.add_argument("--case-timeout", type=float, default=CASE_TIMEOUT_SECONDS)
    parser.add_argument("--headless-audio", action="store_true")
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.case != "all" and args.group != "all":
        parser.error("--case and --group cannot both select a non-default shard")
    if args.case_timeout <= 0 or args.case_timeout > 300:
        parser.error("--case-timeout must be > 0 and <= 300 seconds")
    return args


def selected_cases(args: argparse.Namespace) -> list[str]:
    if args.case != "all":
        return [args.case]
    return list(CASES_BY_GROUP[args.group])


def command_option(case: str) -> str:
    spec = CASE_SPECS.get(case)
    if spec is None or spec.command is None:
        raise ContractError(f"case {case!r} is not a command case")
    return spec.command


def make_long_fixtures(directory: Path, count: int, prefix: str = "desktop-probe") -> list[Path]:
    """Create real uncompressed PCM WAVs long enough to expose state/position."""
    if count < 1:
        raise ContractError("fixture count must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    frames = FIXTURE_SAMPLE_RATE * FIXTURE_SECONDS
    chunk = b"\x00\x00" * (FIXTURE_SAMPLE_RATE * 4)
    fixtures: list[Path] = []
    for index in range(1, count + 1):
        path = directory / f"{prefix}-{index:02d}.wav"
        if path.exists():
            raise FileExistsError(str(path))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(FIXTURE_SAMPLE_RATE)
            remaining = frames
            while remaining:
                amount = min(remaining, FIXTURE_SAMPLE_RATE * 4)
                output.writeframes(chunk[: amount * 2])
                remaining -= amount
        fixtures.append(path)
    return fixtures


def playback_settings(
    *, enqueue: bool, play_enqueued: bool, restore: bool,
    start_paused: bool, row: int | None = None, position: float | None = None,
) -> str:
    lines = [
        "[General]",
        "SettingsVersion=0.8",
        "SingleInstance=true",
        f"RestorePlaylist={str(restore).lower()}",
        f"StartPaused={str(start_paused).lower()}",
        f"EnqueueFiles={str(enqueue).lower()}",
        f"PlayEnqueued={str(play_enqueued).lower()}",
        "Language=en",
        "AutoCheckUpdates=false",
        "TrayIcon=false",
        "MinimizeToTray=false",
        "QuitOnClose=true",
        "PlaylistTrackInfo=%i - %F",
        "WindowTitleTrackInfo=%F",

    ]
    if row is not None or position is not None:
        if row is None or position is None:
            raise ContractError("PlaylistRow requires both row and position")
        if row < 0 or not math.isfinite(position) or not 0 <= position <= 1:
            raise ContractError("invalid persisted playlist row")
        lines.append(f"PlaylistRow={row},{position:g}")
    lines.extend(["[TrackInfo]", "MiddleCenter=%F", "MiddleRight=%T", "BottomRight="])
    return "\n".join(lines) + "\n"


def indexed_rows(labels: Sequence[str]) -> list[str]:
    rows = []
    for index, label in enumerate(labels, 1):
        match = re.fullmatch(r"(\d+) - (.+)", label.strip())
        if not match or int(match.group(1)) != index:
            raise ContractError(f"incorrect visible playlist index: {label!r}, expected {index}")
        rows.append(match.group(2))
    return rows


def validate_preserved_position(before: float, after: float, state: str, elapsed: float) -> None:
    if not all(math.isfinite(x) for x in (before, after, elapsed)):
        raise ContractError("nonfinite position")
    if state == "paused":
        valid = abs(after - before) <= 1
    else:
        valid = before - 1 <= after <= before + elapsed + 2
    if not valid:
        raise ContractError(f"preserved {state} position changed unexpectedly: {before} -> {after} seconds")


def read_persisted_row(settings: str) -> tuple[int, float]:
    match = re.search(r"(?m)^PlaylistRow=([^\r\n]+)$", settings)
    if not match:
        raise ContractError("persisted settings have no PlaylistRow")
    parts = match.group(1).split(",")
    if len(parts) != 2:
        raise ContractError("persisted PlaylistRow shape is not row,position")
    try:
        row = int(parts[0])
        position = float(parts[1])
    except ValueError as exc:
        raise ContractError("persisted PlaylistRow is not numeric") from exc
    if row < -1 or not math.isfinite(position) or not 0 <= position <= 1:
        raise ContractError("persisted PlaylistRow is outside the accepted range")
    if row == -1 and position != 0:
        raise ContractError("stopped persisted PlaylistRow must have zero position")
    return row, position
def parse_position_text(value: str) -> int:
    value = str(value).strip()
    match = TIME_RE.fullmatch(value)
    if not match:
        raise ContractError(f"position text is not a time: {value!r}")
    hours, minutes, seconds = match.groups()
    minutes_i, seconds_i = int(minutes), int(seconds)
    if seconds_i >= 60 or (hours is not None and minutes_i >= 60):
        raise ContractError(f"position text has invalid fields: {value!r}")
    return (int(hours or 0) * 60 + minutes_i) * 60 + seconds_i


def choose_position_text(values: Iterable[str]) -> int:
    observed = list(values)
    candidates: list[int] = []
    for value in observed:
        try:
            candidates.append(parse_position_text(value))
        except ContractError:
            continue
    unique = sorted(set(candidates))
    if len(unique) != 1:
        raise ContractError(f"UIA position observation is missing or ambiguous: {observed!r}")
    return unique[0]


def classify_state(positions: Sequence[float]) -> str:
    if len(positions) < 3 or any(not math.isfinite(value) for value in positions):
        raise ContractError("at least three finite position observations are required")
    if all(abs(value) <= 0.01 for value in positions):
        return "stopped"
    if all(positions[index + 1] > positions[index] + 0.001 for index in range(len(positions) - 1)):
        return "playing"
    if max(positions) - min(positions) <= 0.01:
        return "paused"
    raise ContractError(f"position observations do not prove one state: {list(positions)!r}")


def require_current_media(title: str, expected_names: Sequence[str]) -> str:
    matches = [name for name in expected_names if name and name in str(title)]
    if len(matches) != 1:
        raise ContractError(f"window title does not identify exactly one current media file: {title!r}")
    return matches[0]


def within_boundary_window(idle_elapsed: float, burst_elapsed: float) -> bool:
    return idle_elapsed < IDLE_BOUNDARY_SECONDS and burst_elapsed < MAXIMUM_BURST_SECONDS


def rapid_continuations(timestamps: Sequence[float]) -> list[bool]:
    if not timestamps:
        raise ContractError("rapid timing requires at least one timestamp")
    if any(not math.isfinite(value) for value in timestamps):
        raise ContractError("rapid timing contains a non-finite timestamp")
    if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        raise ContractError("rapid timing timestamps are not strictly increasing")
    burst_start = timestamps[0]
    result = [False]
    for previous, current in zip(timestamps, timestamps[1:]):
        continuation = within_boundary_window(current - previous, current - burst_start)
        result.append(continuation)
        if not continuation:
            burst_start = current
    return result


def _primary_player_trace(traces: dict[str, list[dict[str, Any]]]) -> tuple[str, list[dict[str, Any]]]:
    candidates = [
        (name, records)
        for name, records in traces.items()
        if any(record.get("event") == "player-message" for record in records)
    ]
    if not candidates:
        raise BlockedError("primary player trace has no player-message records")
    if len(candidates) != 1:
        raise BlockedError(f"primary player trace is ambiguous: {[name for name, _ in candidates]!r}")
    return candidates[0]


def _trace_message_parts(record: dict[str, Any]) -> list[str]:
    message = record.get("message")
    if not isinstance(message, str) or not message:
        return []
    return [part for part in message.split("<|>") if part]


def _trace_clock_value(record: dict[str, Any]) -> tuple[str, float]:
    # qtlocalpeertrace.h in the pinned package emits time_msec from
    # QDateTime::currentMSecsSinceEpoch().  It does not emit a monotonic field.
    # Keep the source explicit so wall-clock observations cannot become a timing
    # acceptance by accident.
    if isinstance(record.get("monotonic"), (int, float)) and math.isfinite(float(record["monotonic"])):
        return "monotonic", float(record["monotonic"])
    value = record.get("time_msec")
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return "time_msec", float(value)
    raise BlockedError("player trace record has no finite receipt clock")


def _trace_clock(records: Sequence[dict[str, Any]]) -> tuple[str, list[float]]:
    sources: list[str] = []
    values: list[float] = []
    for record in records:
        source, value = _trace_clock_value(record)
        sources.append(source)
        values.append(value)
    if not sources or len(set(sources)) != 1:
        raise BlockedError("player trace mixes or omits receipt clock fields")
    if any(current < previous for previous, current in zip(values, values[1:])):
        raise ContractError("player trace receipt clock is not ordered")
    return sources[0], values


def _trace_message_rows(records: Sequence[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    return [
        (index, record)
        for index, record in enumerate(records)
        if record.get("event") == "player-message" and _trace_message_parts(record)
    ]


def _trace_followup(records: Sequence[dict[str, Any]], message_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    followups: list[dict[str, Any]] = []
    for record in records[message_index + 1:]:
        if record.get("event") == "player-message":
            break
        if record.get("event") in ("player-open-policy", "player-open-result"):
            followups.append(record)
    if [record.get("event") for record in followups] != ["player-open-policy", "player-open-result"]:
        raise ContractError("player file message lacks one immediate policy/result pair")
    policy, result = followups
    if not isinstance(policy.get("continuation"), bool):
        raise ContractError("player-open-policy lacks a boolean continuation field")
    if not isinstance(result.get("rows"), list):
        raise ContractError("player-open-result lacks a playlist rows array")
    return policy, result


def _trace_text(value: str) -> str:
    return str(value).replace("\\", "/").casefold()


def same_message(first: str, second: str) -> bool:
    if first.startswith('--') or second.startswith('--'):
        return first == second
    if _trace_text(first) == _trace_text(second):
        return True
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def analyze_player_trace(
    traces: dict[str, list[dict[str, Any]]], expected_messages: Sequence[str]
) -> dict[str, Any]:
    primary_name, records = _primary_player_trace(traces)
    messages = _trace_message_rows(records)
    actual = [_trace_message_parts(record) for _, record in messages]
    expected = [[str(message)] for message in expected_messages]
    if len(actual) != len(expected) or any(
        len(parts) != len(wanted) or any(not same_message(a, w) for a, w in zip(parts, wanted))
        for parts, wanted in zip(actual, expected)
    ):
        raise ContractError(f"player-message order differs: {actual!r} != {expected!r}")
    message_records = [record for _, record in messages]
    source, receipt_times = _trace_clock(message_records)
    policies: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for message_index, _ in messages:
        policy, result = _trace_followup(records, message_index)
        policies.append(policy)
        results.append(result)
    return {
        "primary_process": primary_name,
        "messages": message_records,
        "policies": policies,
        "results": results,
        "continuations": [bool(policy.get("continuation")) for policy in policies],
        "receipt_times": receipt_times,
        "receipt_intervals_msec": [int(round(current - previous))
                                   for previous, current in zip(receipt_times, receipt_times[1:])],
        "receipt_source": f"player-trace:{source}",
        # A wall-clock trace is useful for ordering/evidence, but does not prove
        # the strict 250ms/1000ms policy. The pinned header has no monotonic field.
        "boundary_supported": source == "monotonic",
        "trace_order_exact": True,
    }


def analyze_command_trace(
    traces: dict[str, list[dict[str, Any]]], expected_sequence: Sequence[str]
) -> dict[str, Any]:
    primary_name, records = _primary_player_trace(traces)
    messages = _trace_message_rows(records)
    actual = [_trace_message_parts(record)[0] for _, record in messages]
    expected = [str(value) for value in expected_sequence]
    if len(actual) != len(expected) or any(not same_message(a, e) for a, e in zip(actual, expected)):
        raise ContractError(f"command player-message order differs: {actual!r} != {expected!r}")
    policies: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    command_positions = [index for index, value in enumerate(expected) if value.startswith("--")]
    if len(command_positions) != 1:
        raise ContractError("command trace must contain exactly one command message")
    command_position = command_positions[0]
    command_index = messages[command_position][0]
    next_message_index = messages[command_position + 1][0] if command_position + 1 < len(messages) else len(records)
    command_followups = [record for record in records[command_index + 1:next_message_index]
                         if record.get("event") in ("player-open-policy", "player-open-result")]
    for position, (message_index, _) in enumerate(messages):
        if position == command_position:
            continue
        policy, result = _trace_followup(records, message_index)
        policies.append(policy)
        results.append(result)
    source, receipt_times = _trace_clock([record for _, record in messages])
    return {
        "primary_process": primary_name,
        "message_sequence": actual,
        "policies": policies,
        "results": results,
        "file_continuations": [bool(policy.get("continuation")) for policy in policies],
        "receipt_times": receipt_times,
        "receipt_source": f"player-trace:{source}",
        "command_immediate": not command_followups,
        "no_late_open_before_new_file": not command_followups,
        "boundary_supported": source == "monotonic",
    }


def validate_command_observation(observation: Any) -> None:
    if not getattr(observation, "current_media", ""):
        raise ContractError("command observation has no direct current-media evidence")
    if getattr(observation, "position", None) is None:
        raise ContractError("command observation has no direct position evidence")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_summary(output: Path, cases: Sequence[dict[str, Any]], group: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for case in cases:
        status = str(case.get("status", "FAIL"))
        counts[status] = counts.get(status, 0) + 1
    if counts.get("FAIL", 0):
        status = "FAIL"
    elif counts.get("BLOCKED", 0):
        status = "BLOCKED"
    elif counts.get("SKIPPED", 0):
        status = "FAIL"
    elif counts.get("PASS", 0) and counts["PASS"] == len(cases):
        status = "PASS"
    else:
        status = "FAIL"
    summary = {
        "group": group,
        "status": status,
        "cases": list(cases),
        "counts": counts,
        "cleanup_verified": bool(cases) and all(
            case.get("status") == "PASS" and case.get("cleanup_verified") is True
            for case in cases
        ),
    }
    _write_json(output / "summary.json", summary)
    _write_text(output / "status.txt", status + "\n")
    return summary


def _wav_playlist(path: Path, files: Sequence[Path]) -> None:
    lines = ["#EXTM3U"]
    for file in files:
        lines.append(str(file))
    _write_text(path, "\n".join(lines) + "\n")


def _option_profile(profile: probe.ShellVerbProfile, option: str) -> probe.ShellVerbProfile:
    if not option:
        return profile
    command = profile.command.replace(' "%1"', f' {option} "%1"', 1)
    if command == profile.command:
        raise ContractError("could not construct command-boundary shell command")
    return dataclasses.replace(profile, command=command)


class PlaybackCaseRun(probe.WindowsDesktopRun):
    """One disposable native case; all UIA side effects are owned by this object."""

    def __init__(self, package: probe.ExtractedPackage, evidence: Path, run_id: str,
                 spec: CaseSpec, headless_audio: bool = False) -> None:
        super().__init__(package, evidence, run_id, headless_audio=headless_audio,
                         scenario=None, trace_startup=True)
        self.spec = spec
        self.temp_root: Path | None = None
        self.fixtures: list[Path] = []
        self.seed: list[Path] = []
        self.incoming: list[Path] = []
        self.trigger: Path | None = None
        self.initial_observation: dict[str, Any] | None = None
        self.open_timestamps: list[float] = []
        self.open_continuations: list[bool] = []
        self._selection_expected: list[str] = []
        if spec.command:
            self.profile = _option_profile(self.profile, spec.command)

    def _write_setup(self, settings: str, playlist: Sequence[Path]) -> None:
        if not self.package.contract.portable:
            raise BlockedError("PR24 playback cases require an isolated portable package")
        data = self.package.root / "Data"
        data.mkdir(exist_ok=True)
        config = data / f"{self.package.executable.stem}.cfg"
        config.write_text(settings, encoding="utf-8")
        _write_text(self.evidence / "scenario-settings.cfg", settings)
        if playlist:
            _wav_playlist(data / f"{self.package.executable.stem}.m3u", playlist)
        _write_json(self.evidence / "scenario-input.json", {
            "case": self.spec.name,
            "playlist": [str(path) for path in playlist],
            "settings": settings,
        })

    def _launch_player(self) -> None:
        environment = probe._app_environment()
        environment["NULLOY_STARTUP_TRACE_DIR"] = str(self.trace_directory)
        if self.headless_audio:
            environment["GST_PLUGIN_FEATURE_RANK"] = (
                "directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0"
            )
        self.player_launch_started = True
        subprocess.Popen([str(self.package.executable)], env=environment)
        probe._wait_for(self._capture_new_player_processes, 45, "owned packaged player process")
        self.player_window = probe._wait_for(self._find_player, 45, "packaged player window")
        self._capture_player("startup")

    def _capture_player(self, label: str) -> None:
        if self.player_window is None:
            raise ContractError("cannot capture player evidence before UIA discovery")
        probe._capture_image(self.player_window.capture_as_image(), self.evidence / f"player-{label}.png")
        probe._dump_uia(self.player_window, self.evidence / f"player-{label}-uia.jsonl")

    def _snapshot_traces(self) -> dict[str, list[dict[str, Any]]]:
        processes: dict[str, list[dict[str, Any]]] = {}
        if self.trace_directory is not None and self.trace_directory.exists():
            for path in sorted(self.trace_directory.glob("*.jsonl")):
                records: list[dict[str, Any]] = []
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        records.append(value)
                processes[path.stem] = records
        _write_json(self.evidence / "startup-processes.json", processes)
        return processes

    def _uia_texts(self) -> list[str]:
        if self.player_window is None:
            raise ContractError("player UIA window is unavailable")
        values: list[str] = []
        for control in [self.player_window, *self.player_window.descendants()]:
            for getter in ("window_text",):
                try:
                    text = str(getattr(control, getter)()).strip()
                except Exception:
                    continue
                if text:
                    values.append(text)
            try:
                name = str(getattr(control.element_info, "name", "")).strip()
            except Exception:
                name = ""
            if name:
                values.append(name)
        return values

    def _window_title(self) -> str:
        try:
            return str(self.player_window.window_text())
        except Exception as exc:
            raise ContractError(f"player window title is unavailable: {exc}") from exc

    def _position(self) -> int | float:
        if self.player_window is None:
            raise ContractError("player UIA window is unavailable")
        if self.spec.initial_state == 'stopped':
            for slider in self.player_window.descendants(control_type='Slider'):
                if str(getattr(slider.element_info, 'automation_id', '')).endswith('.waveformSlider'):
                    try:
                        interface = slider.iface_range_value
                        minimum, maximum, value = (float(interface.CurrentMinimum), float(interface.CurrentMaximum), float(interface.CurrentValue))
                        _write_json(self.evidence / 'waveform-range.json', dict(minimum=minimum,maximum=maximum,value=value))
                        if maximum > minimum and minimum <= value <= maximum:
                            return (value-minimum)/(maximum-minimum)*FIXTURE_SECONDS
                    except Exception as exc:
                        _write_text(self.evidence / 'waveform-range-error.txt', repr(exc))
        # Always seconds, never mix a normalized slider fraction with seconds.
        texts = []
        for control in self.player_window.descendants():
            identifier = str(getattr(control.element_info, 'automation_id', ''))
            if identifier.endswith('MiddleRight'):
                texts.append(control.window_text())
        return float(choose_position_text(texts))

    def _current_media_from_ui(self, expected_names: Sequence[str]) -> str | None:
        matches: list[str] = []
        for control in self.player_window.descendants():
            info = control.element_info
            marker = " ".join((
                str(getattr(info, "automation_id", "")),
                str(getattr(info, "name", "")),
                str(getattr(info, "class_name", "")),
            ))
            if "MiddleCenter" not in marker:
                continue
            try:
                text = str(control.window_text())
            except Exception:
                continue
            matches.extend(name for name in expected_names if name in text)
        matches = sorted(set(matches))
        if len(matches) > 1:
            raise ContractError(f"UIA current-media label identifies multiple files: {matches!r}")
        return matches[0] if matches else None

    def _direct_observation(self, expected_names: Sequence[str]) -> dict[str, Any]:
        title = self._window_title()
        title_matches = [name for name in expected_names if name in title]
        if len(title_matches) > 1:
            raise ContractError(f"player title identifies multiple media files: {title!r}")
        current = title_matches[0] if title_matches else self._current_media_from_ui(expected_names)
        try:
            position = self._position()
        except ContractError:
            position = None
        return {"title": title, "current_media": current, "position": position,
                "monotonic": time.monotonic()}

    def _observe_state(self, expected: str, expected_names: Sequence[str],
                       current_required: str | None = None) -> dict[str, Any]:
        observations: list[dict[str, Any]] = []
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            observation = self._direct_observation(expected_names)
            observations.append(observation)
            if current_required is not None and observation["current_media"] != current_required:
                time.sleep(0.25)
                continue
            if expected == "stopped" and observation["current_media"] is None:
                state = "stopped"
            elif len(observations) >= 3 and all(item["position"] is not None for item in observations[-3:]):
                try:
                    state = classify_state([float(item["position"]) for item in observations[-3:]])
                except ContractError:
                    time.sleep(1.1)
                    continue
            else:
                time.sleep(1.1)
                continue
            if state == expected:
                result = {"state": state, "samples": observations[-3:],
                          "current_media": observation["current_media"],
                          "position": observation["position"]}
                return result
            time.sleep(1.1)
        raise ContractError(
            f"UIA did not prove expected {expected} state; observations={observations!r}"
        )

    def _find_items(self) -> tuple[Any, dict[str, Any]]:
        self.explorer_window = probe._wait_for(self._find_explorer, 20, "fixture Explorer window")
        view = self._find_explorer_items_view()
        controls = self._explorer_file_rows(view)
        names = sorted(path.name for path in self.fixture_directory.iterdir() if path.is_file())
        mapped = probe.explorer_row_names([item.window_text() for item in controls], names)
        return controls, dict(zip(mapped, controls))

    def _find_explorer_items_view(self) -> Any:
        matches = []
        for control in self.explorer_window.descendants(control_type="List"):
            info = control.element_info
            if (getattr(info, "class_name", "") == "UIItemsView"
                    and control.window_text() == "Items View"):
                matches.append(control)
        if len(matches) != 1:
            raise ContractError(f"Explorer Items View count is {len(matches)}, expected one")
        return matches[0]

    def _explorer_file_rows(self, items_view: Any) -> list[Any]:
        rows = list(items_view.children(control_type="ListItem"))
        if not rows:
            raise ContractError("Explorer Items View exposed no file rows")
        return rows

    def _select_files(self, wanted: Sequence[Path]) -> None:
        controls, items = self._find_items()
        expected = [path.name for path in wanted]
        for index, name in enumerate(expected):
            if name not in items:
                raise ContractError(f"requested Explorer file row is missing: {name}")
            if index:
                items[name].click_input(pressed="control")
            else:
                items[name].click_input()
        selected = [item.window_text() for item in controls if item.is_selected()]
        mapped = probe.explorer_row_names(selected, expected)
        if mapped != expected:
            raise ContractError(f"Explorer selected order differs: {mapped!r} != {expected!r}")
        self._selection_expected = expected
        _write_json(self.evidence / "explorer-selection.json", {
            "selected": selected, "expected": expected,
        })

    def _activate_selection(self) -> float:
        self.explorer_window.set_focus()
        self.explorer_window.type_keys("+{F10}")
        item = probe._wait_for(self._find_probe_menu_item, 10, "probe shell verb in Explorer context menu")
        started = time.monotonic()
        item.click_input()
        self.open_timestamps.append(started)
        return started

    def _open_files(self, files: Sequence[Path], separate: bool = False) -> None:
        for index, file in enumerate(files):
            if separate and self.spec.rapid_mode == "idle" and index == 1:
                time.sleep(IDLE_BOUNDARY_SECONDS + 0.05)
            if separate and self.spec.rapid_mode == "total":
                # Pace the controller near 180ms so the primary trace can
                # characterize the absolute-cap component. These are only
                # dispatch timestamps; they are never the acceptance clock.
                target = self.open_timestamps[0] + index * 0.18 if self.open_timestamps else time.monotonic()
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            self._select_files([file])
            self._activate_selection()
        if not separate:
            return
        _write_json(self.evidence / "rapid-timing.json", {
            "transport": "Explorer separate context-menu activations",
            "controller_timestamps": self.open_timestamps,
            "controller_relative": ([stamp - self.open_timestamps[0] for stamp in self.open_timestamps]
                                     if self.open_timestamps else []),
            "controller_clock": "time.monotonic; diagnostic dispatch timing only",
            "idle_limit_seconds": IDLE_BOUNDARY_SECONDS,
            "maximum_burst_seconds": MAXIMUM_BURST_SECONDS,
            "boundary_source": "pending primary player trace",
        })

    def _wait_for_player_trace(self, expected_messages: int) -> dict[str, list[dict[str, Any]]]:
        deadline = time.monotonic() + 10
        last: dict[str, list[dict[str, Any]]] = {}
        while time.monotonic() < deadline:
            last = self._snapshot_traces()
            try:
                _, records = _primary_player_trace(last)
            except BlockedError:
                time.sleep(0.05)
                continue
            if len(_trace_message_rows(records)) >= expected_messages:
                return last
            time.sleep(0.05)
        raise BlockedError(
            f"primary player trace did not receive {expected_messages} file messages; "
            f"observed={len(_trace_message_rows(_primary_player_trace(last)[1])) if last else 0}"
        )

    def _send_secondary_arguments(self, arguments: Sequence[str]) -> tuple[Any, float]:
        environment = probe._app_environment()
        if self.trace_directory is not None:
            environment["NULLOY_STARTUP_TRACE_DIR"] = str(self.trace_directory)
        if self.headless_audio:
            environment["GST_PLUGIN_FEATURE_RANK"] = (
                "directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0"
            )
        started = time.monotonic()
        process = subprocess.Popen([str(self.package.executable), *arguments], env=environment)
        return process, started

    def _prepare(self) -> dict[str, Any]:
        self.temp_root = Path(tempfile.mkdtemp(prefix=f"nulloy-pr24-{self.run_id}-"))
        self.fixture_directory = self.temp_root / "fixtures"
        if self.spec.group in ("populated", "restored", "rapid", "commands"):
            self.seed = make_long_fixtures(self.fixture_directory, 3, "seed")
            self.incoming = make_long_fixtures(self.fixture_directory, 3, "open")
            self.fixtures = self.seed + self.incoming
            if self.spec.group == "commands":
                settings = playback_settings(
                    enqueue=True, play_enqueued=False, restore=True,
                    start_paused=False, row=1, position=0.37,
                )
                self._write_setup(settings, self.seed)
            elif self.spec.group == "rapid":
                settings = playback_settings(
                    enqueue=True, play_enqueued=False, restore=True,
                    start_paused=False, row=1, position=0.37,
                )
                self._write_setup(settings, self.seed)
            else:
                settings = playback_settings(
                    enqueue=self.spec.enqueue, play_enqueued=self.spec.play_enqueued,
                    restore=True, start_paused=False,
                    row=1,
                    position=0.37,
                )
                self._write_setup(settings, self.seed)
        else:
            raise ContractError(f"unhandled case group: {self.spec.group}")
        self.trace_directory.mkdir(parents=True, exist_ok=True)
        self._registry_install()
        self._launch_player()
        expected = [path.name for path in self.seed]
        initial = self._read_playlist_rows(self.seed)
        if initial != expected:
            raise ContractError(f"initial playlist order mismatch: {initial!r} != {expected!r}")
        if self.spec.initial_state is not None:
            current = self.seed[1].name if self.spec.initial_state != "stopped" else None
            if self.spec.initial_state == 'stopped':
                self._observe_state('playing', [path.name for path in self.fixtures], self.seed[1].name)
                self.player_window.set_focus()
                self.player_window.type_keys('v')  # actual native Stop action, no setup IPC trace
            if self.spec.initial_state == 'paused':
                # StartPaused merely loads media without calling engine.pause().
                # Exercise a genuinely paused engine, not a stopped restored UI.
                self._observe_state('playing', [path.name for path in self.fixtures], current)
                buttons = [control for control in self.player_window.descendants(control_type='Button')
                           if str(getattr(control.element_info, 'automation_id', '')).endswith('.playButton')]
                if len(buttons) != 1:
                    raise ContractError('unique owned play/pause button not found')
                buttons[0].click_input()
            self.initial_observation = self._observe_state(
                self.spec.initial_state,
                [path.name for path in self.fixtures],
                current_required=current,
            )
        else:
            self.initial_observation = self._observe_state("playing", [path.name for path in self.fixtures],
                                                           current_required=self.seed[1].name)
        return {"initial": self.initial_observation, "initial_rows": initial}

    def _read_playlist_rows(self, expected: Sequence[Path]) -> list[str]:
        names = [path.name for path in expected]
        deadline = time.monotonic() + 8
        last: list[str] = []
        while time.monotonic() < deadline:
            control = self._find_playlist_control()
            raw = [item.window_text() for item in control.descendants(control_type="ListItem")]
            rows = indexed_rows(raw)
            last = rows
            if len(rows) == len(names) and rows == names:
                _write_json(self.evidence / "playlist-observation.json", {
                    "raw": raw, "rows": rows, "expected": names,
                })
                return rows
            time.sleep(0.25)
        raise ContractError(f"playlist rows did not stabilize exactly: {last!r} != {names!r}")

    def _result_populated(self) -> dict[str, Any]:
        self._select_files(self.incoming)
        self._activate_selection()
        probe._wait_for(lambda: self._startup_settled(4), 25, 'three acknowledged Explorer clients')
        self._assert_one_settled_player()
        processes = self._snapshot_traces()
        primary = next(records for records in processes.values()
                       if any(row.get('event') == 'player-connected' for row in records))
        delivered = [part for row in primary if row.get('event') == 'player-message'
                     for part in row['message'].split('<|>') if part]
        order = [Path(path).name for path in delivered]
        delivery = probe.startup_delivery(processes, self.incoming, order, 4)
        _write_json(self.evidence / 'delivery.json', delivery)
        by_name = {path.name: path for path in self.incoming}
        incoming_order = [by_name[name] for name in order]
        expected_rows = order
        if self.spec.enqueue:
            expected_rows = [path.name for path in self.seed] + expected_rows
        rows = self._read_playlist_rows(incoming_order if not self.spec.enqueue else self.seed + incoming_order)
        if rows != expected_rows:
            raise ContractError(f"open policy playlist order mismatch: {rows!r} != {expected_rows!r}")
        if not self.spec.enqueue or self.spec.play_enqueued or self.spec.initial_state == "stopped":
            current = incoming_order[0].name
            state = "playing"
        else:
            current = self.seed[1].name
            state = self.spec.initial_state or "playing"
        after = self._observe_state(state, [path.name for path in self.fixtures], current_required=current)
        if current == self.seed[1].name:
            before_position = self.initial_observation.get("position") if self.initial_observation else None
            after_position = after.get("position")
            if before_position is None or after_position is None:
                raise ContractError("preserved playback position not observed")
            elapsed = after['samples'][-1]['monotonic'] - self.initial_observation['samples'][-1]['monotonic']
            validate_preserved_position(before_position, after_position, state, elapsed)
        self._capture_player("after-open")
        return {"rows": rows, "after": after, "assertions": {
            "playlist_order_exact": True,
            "current_media_directly_observed": True,
            "state_directly_observed": True,
            "position_directly_observed": after.get("position") is not None,
        }}

    def _result_restored(self) -> dict[str, Any]:
        result = self._result_populated()
        result['restore_scope'] = 'external open after restored startup has settled; synchronous cold-start engine-state decision not observed'
        return result

    def _result_rapid(self) -> dict[str, Any]:
        files = list(self.incoming)
        if self.spec.rapid_mode == "total":
            # Reuse real fixture paths intentionally: schedule eight messages
            # near 180ms apart to isolate the one-second cap. The primary
            # player trace, not this controller schedule, decides acceptance.
            files = (files * ((8 + len(files) - 1) // len(files)))[:8]
        self._open_files(files, separate=True)
        traces = self._wait_for_player_trace(len(files))
        try:
            observation = analyze_player_trace(traces, [str(path) for path in files])
        except ContractError as exc:
            raise BlockedError(f"rapid player-trace characterization is incomplete: {exc}") from exc
        _write_json(self.evidence / "rapid-timing.json", {
            "transport": "Explorer separate context-menu activations",
            "controller_timestamps": self.open_timestamps,
            "controller_clock": "time.monotonic; diagnostic dispatch timing only",
            "trace_receipt_times": observation["receipt_times"],
            "trace_receipt_intervals_msec": observation["receipt_intervals_msec"],
            "trace_receipt_source": observation["receipt_source"],
            "trace_continuations": observation["continuations"],
            "boundary_supported": observation["boundary_supported"],
            "idle_limit_seconds": IDLE_BOUNDARY_SECONDS,
            "maximum_burst_seconds": MAXIMUM_BURST_SECONDS,
        })
        if not observation["boundary_supported"]:
            raise BlockedError(
                "rapid boundary is BLOCKED: qtlocalpeertrace.h records wall-clock "
                "time_msec only; controller timing cannot substitute for a monotonic player receipt clock"
            )
        expected = {
            "burst": [False] + [True] * (len(files) - 1),
            "idle": [False, False, True],
            "total": rapid_continuations([index * 0.18 for index in range(len(files))]),
        }[self.spec.rapid_mode or ""]
        if observation["continuations"] != expected:
            raise ContractError(
                f"player trace boundary sequence differs: {observation['continuations']!r} != {expected!r}"
            )
        expected_rows = [path.name for path in self.seed + files]
        rows = self._read_playlist_rows(self.seed + files)
        after = self._observe_state("playing", [path.name for path in self.fixtures], current_required=self.seed[1].name)
        return {"rows": rows, "after": after, "assertions": {
            "separate_explorer_activations": len(self.open_timestamps) == len(files),
            "boundary_observed_from_player_trace": True,
            "player_trace_order_exact": observation["trace_order_exact"],
            "grouping_observed_in_policy_trace": len(observation["policies"]) == len(files),
            "playlist_order_exact": rows == expected_rows,
        }}

    def _result_command(self) -> dict[str, Any]:
        first = self.trigger or self.incoming[0]
        second = self.incoming[1] if len(self.incoming) > 1 else self.incoming[0]
        option = self.spec.command or ""
        processes: list[Any] = []
        self.open_timestamps = []
        for arguments in ((str(first),), (option,), (str(second),)):
            process, started = self._send_secondary_arguments(arguments)
            processes.append(process)
            self.open_timestamps.append(started)
            if process.wait(timeout=10) != 0:
                raise ContractError('secondary IPC client did not acknowledge its frame')
            self._wait_for_player_trace(len(processes))
        for process in processes:
            return_code = process.wait(timeout=10)
            if return_code != 0:
                raise ContractError(f"secondary IPC client failed with exit code {return_code}")
        traces = self._wait_for_player_trace(3)
        observation = analyze_command_trace(
            traces, [str(first), option, str(second)]
        )
        _write_json(self.evidence / "command-trace.json", {
            "transport": "QtSingleApplication IPC via secondary processes",
            "controller_timestamps": self.open_timestamps,
            "controller_clock": "time.monotonic; dispatch diagnostic only",
            "trace_receipt_times": observation["receipt_times"],
            "trace_receipt_source": observation["receipt_source"],
            "message_sequence": observation["message_sequence"],
            "file_continuations": observation["file_continuations"],
            "command_immediate": observation["command_immediate"],
            "no_late_open_before_new_file": observation["no_late_open_before_new_file"],
            "boundary_supported": observation["boundary_supported"],
            "limitation": "This is an IPC characterization; it does not prove Explorer shell timing boundaries.",
        })
        if not observation["command_immediate"] or not observation["no_late_open_before_new_file"]:
            raise ContractError("command trace contains a late file-open policy/result before the new file")
        expected_current = second.name if option == "--stop" else {
            "--next": self.seed[2].name,
            "--prev": self.seed[0].name,
            "--pause": self.seed[1].name,
        }[option]
        state = "playing"
        after = self._observe_state(state, [path.name for path in self.fixtures], current_required=expected_current)
        rows = self._read_playlist_rows(self.seed + [first, second])
        return {"rows": rows, "after": after, "assertions": {
            "command_sequence_delivered_in_trace": all(same_message(a,b) for a,b in zip(observation["message_sequence"], [str(first), option, str(second)])),
            "post_command_open_starts_new_group": observation["file_continuations"] == [False, False],
            "no_file_policy_between_command_and_followup": observation["command_immediate"],
            "command_current_media_directly_observed": True,
            "command_state_directly_observed": True,
            "explorer_shell_boundary_not_claimed": observation["receipt_source"] == "player-trace:time_msec",
        }}

    def execute(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        self.preflight()
        try:
            result.update(self._prepare())
            if self.spec.group in ("populated", "restored", "rapid"):
                environment = probe._app_environment()
                self.explorer_launch_started = True
                subprocess.Popen(["explorer.exe", "/n", f"/root,{self.fixture_directory}"], env=environment)
            if self.spec.group == "populated":
                result.update(self._result_populated())
            elif self.spec.group == "restored":
                result.update(self._result_restored())
            elif self.spec.group == "rapid":
                # One Explorer instance is used, but every file is selected and
                # invoked through its own real context-menu activation.
                self.explorer_window = None
                result.update(self._result_rapid())
            elif self.spec.group == "commands":
                self.explorer_window = None
                result.update(self._result_command())
            else:
                raise ContractError(f"unsupported case group {self.spec.group!r}")
            traces = self._snapshot_traces()
            if not traces:
                raise ContractError("packaged startup trace is absent; launch/delivery is not observable")
            result["startup_trace_observed"] = True
            result["limitations"] = [
                "audio output hardware is not an acceptance assertion",
                "current media, state, and position come from direct UIA/title/time observations; selected rows are never used as playback state",
            ]
            return result
        except Exception:
            if self.explorer_window is not None:
                try:
                    probe._capture_image(self.explorer_window.capture_as_image(), self.evidence / "explorer-failure.png")
                    probe._dump_uia(self.explorer_window, self.evidence / "explorer-failure-uia.jsonl")
                except Exception:
                    pass
            if self.player_window is not None:
                try:
                    self._capture_player("failure")
                except Exception:
                    pass
            raise
        finally:
            cleanup_ok = True
            try:
                cleanup_ok = self._cleanup_player() and cleanup_ok
            except Exception as exc:
                self._cleanup_error("player cleanup", exc)
                cleanup_ok = False
            if self.spec.restored and self.package.root.exists():
                config = self.package.root / "Data" / f"{self.package.executable.stem}.cfg"
                try:
                    persisted = config.read_text(encoding="utf-8")
                    persisted_row = read_persisted_row(persisted)
                    after = result.get('after', {})
                    if after.get('current_media'):
                        expected_row = result['rows'].index(after['current_media'])
                        if persisted_row[0] != expected_row:
                            raise ContractError('persisted playing row differs from observed current media')
                        saved_seconds = persisted_row[1] * FIXTURE_SECONDS
                        elapsed = time.monotonic() - after['samples'][-1]['monotonic']
                        validate_preserved_position(after['position'], saved_seconds, after['state'], elapsed)
                    _write_json(self.evidence / "persisted-after-close.json", {
                        "row": persisted_row[0], "position": persisted_row[1],
                        "source": "portable settings read after owned player close",
                    })
                    result.setdefault("assertions", {})["persisted_settings_readback"] = True
                except Exception as exc:
                    self._cleanup_error("persisted settings readback", exc)
                    result.setdefault("assertions", {})["persisted_settings_readback"] = False
            try:
                cleanup_ok = self._cleanup_explorer() and cleanup_ok
            except Exception as exc:
                self._cleanup_error("Explorer cleanup", exc)
                cleanup_ok = False
            try:
                registry_ok = self._registry_cleanup()
                if not registry_ok:
                    self._cleanup_error("registry cleanup", RuntimeError("registry ownership remains"))
                cleanup_ok = cleanup_ok and registry_ok
            except Exception as exc:
                self._cleanup_error("registry cleanup", exc)
                cleanup_ok = False
            if self.process_cleanup_verified and self.temp_root is not None:
                try:
                    shutil.rmtree(self.temp_root)
                    cleanup_ok = cleanup_ok and not self.temp_root.exists()
                except OSError as exc:
                    self._cleanup_error("fixture directory cleanup", exc)
                    cleanup_ok = False
            elif self.temp_root is not None:
                self._cleanup_error("fixture directory cleanup", RuntimeError(
                    "package process cleanup was not verified; fixtures preserved"
                ))
                cleanup_ok = False
            self.cleanup_verified = cleanup_ok and self.process_cleanup_verified and not self.cleanup_errors
            _write_json(self.evidence / "cleanup.json", self._cleanup_evidence())


def _case_result_base(case: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"case": case, "status": status, "cleanup_verified": False, **extra}


def run_case(args: argparse.Namespace, case: str, *, runtime_factory=None) -> tuple[int, dict[str, Any]]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = _case_result_base(case, "BLOCKED", group=CASE_SPECS[case].group)
    run_id = uuid.uuid4().hex[:12]
    package_temp = Path(tempfile.mkdtemp(prefix=f"pr24-package-{run_id}-"))
    runtime: PlaybackCaseRun | None = None
    try:
        source_sha = probe.parse_source_sha(args.source_sha)
        package = probe.extract_and_validate(args.package.resolve(), package_temp, source_sha)
        evidence.update({
            "run_id": run_id,
            "package": str(args.package.resolve()),
            "archive_sha256": package.archive_sha256,
            "executable_sha256": package.executable_sha256,
            "manifest_executable_sha256": package.contract.files[package.contract.executable],
            "file_hashes_verified": package.file_hashes_verified,
            "source_commit": package.contract.source_commit,
            "portable": package.contract.portable,
            "root": package.contract.root,
            "executable": package.contract.executable,
            "audio_mode": "no-device-fallback" if args.headless_audio else "device",
        })
        factory = PlaybackCaseRun if runtime_factory is None else runtime_factory
        runtime = factory(package, output, run_id, CASE_SPECS[case], args.headless_audio)
        result = runtime.execute()
        evidence.update(result)
        assertions = list(result.get("assertions", {}).values())
        evidence["status"] = probe.verdict(assertions, runtime.cleanup_verified)
        if evidence["status"] != "PASS":
            evidence.setdefault("error", "one or more direct acceptance assertions failed")
    except probe.BlockedError as exc:
        evidence.update({"status": "BLOCKED", "error": str(exc),
                         "error_traceback": traceback.format_exc()})
    except (BlockedError,) as exc:
        evidence.update({"status": "BLOCKED", "error": str(exc),
                         "error_traceback": traceback.format_exc()})
    except Exception as exc:
        evidence.update({"status": "FAIL", "error": str(exc),
                         "error_traceback": traceback.format_exc()})
    finally:
        if runtime is not None:
            try:
                evidence.update(runtime._cleanup_evidence())
            except Exception as exc:
                evidence.setdefault("cleanup_errors", []).append(f"cleanup evidence: {exc}")
                evidence["status"] = "FAIL"
            evidence["cleanup_verified"] = bool(getattr(runtime, "cleanup_verified", False))
        preserve = bool(runtime is not None and runtime.owned_player_processes
                        and not runtime.process_cleanup_verified)
        if preserve:
            evidence["preserved_package_path"] = str(package_temp)
        else:
            try:
                shutil.rmtree(package_temp)
            except OSError as exc:
                evidence.setdefault("cleanup_errors", []).append(f"package extraction cleanup: {exc}")
                evidence["cleanup_verified"] = False
                evidence["status"] = "FAIL"
        _write_json(output / "result.json", evidence)
        _write_text(output / "status.txt", evidence["status"] + "\n")
        if evidence.get("archive_sha256"):
            _write_text(output / "archive.sha256", evidence["archive_sha256"] + "\n")
        if evidence.get("executable_sha256"):
            _write_text(output / "executable.sha256", evidence["executable_sha256"] + "\n")
    return (0 if evidence["status"] == "PASS" else 2 if evidence["status"] == "BLOCKED" else 1), evidence


def _timeout_result(case: str, seconds: float) -> dict[str, Any]:
    return _case_result_base(case, "FAIL", error=f"case watchdog exceeded {seconds:g} seconds",
                             cleanup_errors=["child process was terminated by supervisor"])


def run_group(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    names = selected_cases(args)
    for index, case in enumerate(names):
        case_output = output / case
        command = [
            sys.executable, str(Path(__file__).resolve()),
            "--package", str(args.package.resolve()),
            "--output", str(case_output),
            "--source-sha", args.source_sha,
            "--case", case,
            "--case-timeout", str(args.case_timeout),
            "--_worker",
        ]
        if args.headless_audio:
            command.append("--headless-audio")
        try:
            completed = subprocess.run(command, timeout=args.case_timeout + 5,
                                       capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            record = _timeout_result(case, args.case_timeout)
        else:
            result_path = case_output / "result.json"
            if result_path.is_file():
                try:
                    record = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    record = _case_result_base(case, "FAIL", error=f"invalid child result: {exc}")
            else:
                record = _case_result_base(case, "FAIL", error=(
                    f"case child produced no result.json (exit {completed.returncode}): "
                    f"{completed.stderr[-1000:]}"
                ))
        if not (case_output / "result.json").is_file():
            _write_json(case_output / "result.json", record)
        cases.append({
            "case": case,
            "status": record.get("status", "FAIL"),
            "cleanup_verified": bool(record.get("cleanup_verified")),
            "result": str((case_output / "result.json").relative_to(output))
            if (case_output / "result.json").is_file() else None,
            "error": record.get("error"),
        })
        if record.get("cleanup_verified") is not True:
            for skipped in names[index + 1:]:
                cases.append(_case_result_base(skipped, "SKIPPED",
                                               error="sequential safety stop after unverified cleanup"))
            break
    summary = write_summary(output, cases, args.group)
    return (0 if summary["status"] == "PASS" else 2 if summary["status"] == "BLOCKED" else 1), summary


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args._worker:
        code, evidence = run_case(args, args.case)
    else:
        code, evidence = run_group(args)
    print(f"{evidence['status']}: {evidence.get('error', 'PR24 playback acceptance completed')}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
