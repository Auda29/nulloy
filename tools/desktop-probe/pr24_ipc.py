#!/usr/bin/env python3
"""Exact-package IPC burst acceptance for the packaged Nulloy player.

This module deliberately does not use the package's wall-clock trace fields for
boundary decisions.  The controller brackets each secondary-process launch
with ``time.perf_counter()`` and closes a file bracket only after the primary
trace contains that file's policy and result records.  The seven native cases
are isolated workers, and a cleanup failure stops the following workers.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from typing import Any, Iterable, Sequence

import probe
import pr24_playback as playback


CASE_GROUP = "ipc"
RESULT_SCHEMA_VERSION = 1
IPC_CASES = (
    "ipc_short",
    "ipc_idle",
    "ipc_maximum",
    "ipc_command_next",
    "ipc_command_prev",
    "ipc_command_stop",
    "ipc_command_pause",
)
CASE_TIMEOUT_SECONDS = 120.0
IDLE_LIMIT_SECONDS = 0.250
MAXIMUM_BURST_SECONDS = 1.000
MAXIMUM_MESSAGE_COUNT = 13
MAXIMUM_SCHEDULE_STEP_SECONDS = 0.080
MAXIMUM_RESET_ANCHOR_SECONDS = 1.050


class ContractError(ValueError):
    """The exact-package observation does not prove its requested contract."""


class BlockedError(RuntimeError):
    """The evidence is insufficient to make a product verdict safely."""


@dataclasses.dataclass(frozen=True)
class ReceiptBracket:
    """A same-controller monotonic receipt bracket.

    ``lower`` is sampled immediately before ``Popen`` and ``upper`` is sampled
    only after the required primary-trace marker has been observed.  No trace
    wall clock is stored or compared here.
    """

    message: str
    lower: float
    upper: float
    kind: str
    policy_observed: bool
    result_observed: bool
    completion_basis: str = "policy-and-result"

    def __post_init__(self) -> None:
        if not isinstance(self.message, str) or not self.message:
            raise ContractError("receipt bracket message must be non-empty")
        if self.kind not in ("file", "command"):
            raise ContractError(f"unknown receipt bracket kind: {self.kind!r}")
        if not all(math.isfinite(float(value)) for value in (self.lower, self.upper)):
            raise BlockedError("receipt bracket has no finite perf_counter endpoint")
        if self.upper < self.lower:
            raise ContractError("receipt bracket upper endpoint precedes its lower endpoint")
        if not self.completion_basis:
            raise BlockedError("receipt bracket has no completion basis")

    @property
    def complete(self) -> bool:
        if self.kind == "command":
            return self.completion_basis == "command-message-entry-before-next-file"
        return bool(self.policy_observed and self.result_observed)

    @property
    def interval(self) -> tuple[float, float]:
        return (self.lower, self.upper)

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "kind": self.kind,
            "lower_perf_counter": self.lower,
            "upper_perf_counter": self.upper,
            "interval_seconds": self.upper - self.lower,
            "policy_observed": self.policy_observed,
            "result_observed": self.result_observed,
            "completion_basis": self.completion_basis,
            "clock": "perf_counter",
        }


@dataclasses.dataclass(frozen=True)
class BurstClassification:
    continuations: list[bool]
    intervals: list[dict[str, Any]]


@dataclasses.dataclass(frozen=True)
class _FileObservation:
    message: str
    policy: dict[str, Any]
    result: dict[str, Any]
    record_index: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "policy": self.policy,
            "result": self.result,
            "record_index": self.record_index,
            "complete": True,
        }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=("all", *IPC_CASES), default="all")
    parser.add_argument("--headless-audio", action="store_true")
    parser.add_argument("--case-timeout", type=float, default=CASE_TIMEOUT_SECONDS)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.case_timeout <= 0 or args.case_timeout > CASE_TIMEOUT_SECONDS:
        parser.error(f"--case-timeout must be > 0 and <= {CASE_TIMEOUT_SECONDS:g} seconds")
    return args


def selected_cases(args: argparse.Namespace) -> list[str]:
    return list(IPC_CASES) if args.case == "all" else [args.case]


def expected_file_results(messages: Sequence[str], continuations=None) -> list[dict[str, Any]]:
    """Compute replacement-mode results without consulting returned policy."""
    continuations = [False]*len(messages) if continuations is None else continuations
    if len(continuations) != len(messages) or not messages or continuations[0]:
        raise ContractError('invalid independent scenario expectations')
    rows = []
    results = []
    for message, continuation in zip(messages, continuations):
        rows = rows + [str(message)] if continuation else [str(message)]
        results.append(dict(rows=rows.copy(),playing_row=0))
    return results


def expected_final_state(messages: Sequence[str]) -> dict[str, Any]:
    if not messages:
        raise ContractError("final state requires at least one file")
    message = str(messages[-1])
    return {"rows": [message], "current_media": message, "playing_row": 0}


def validate_file_results(
    observations: Sequence[dict[str, Any]], messages: Sequence[str], continuations=None,
) -> list[dict[str, Any]]:
    """Require each result to be the independently expected replacement row."""
    expected = expected_file_results(messages, continuations)
    actual = [dict(rows=observation.get('result',{}).get('rows'), playing_row=observation.get('result',{}).get('playing_row')) for observation in observations]
    if len(actual) != len(expected) or any(a['playing_row'] != e['playing_row'] or not isinstance(a['rows'],list) or len(a['rows']) != len(e['rows']) or any(not _same_message(x,y) for x,y in zip(a['rows'],e['rows'])) for a,e in zip(actual,expected)):
        raise ContractError(f"player-open-result rows differ: {actual!r} != {expected!r}")
    return actual


def _message_parts(record: dict[str, Any]) -> list[str]:
    message = record.get("message")
    if not isinstance(message, str) or not message:
        return []
    return [part for part in message.split("<|>") if part]


def _message_rows(records: Sequence[dict[str, Any]]) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for index, record in enumerate(records):
        if record.get("event") != "player-message":
            continue
        parts = _message_parts(record)
        if not parts and record.get('message') == '':
            continue
        if len(parts) != 1:
            raise BlockedError("player-message record is not one exact IPC message")
        rows.append((index, parts[0]))
    return rows


def _followup(records: Sequence[dict[str, Any]], message_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    followups: list[dict[str, Any]] = []
    for record in records[message_index + 1 :]:
        if record.get("event") == "player-message":
            break
        if record.get("event") in ("player-open-policy", "player-open-result"):
            followups.append(record)
    if [row.get("event") for row in followups] != ["player-open-policy", "player-open-result"]:
        raise BlockedError("file IPC message lacks a complete policy/result pair")
    policy, result = followups
    if not isinstance(policy.get("continuation"), bool):
        raise BlockedError("file IPC policy continuation is not boolean")
    if not isinstance(result.get("rows"), list) or type(result.get("playing_row")) is not int:
        raise BlockedError("file IPC result lacks rows or integer playing_row")
    return policy, result


def _primary_records(traces: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    candidates = [
        records for records in traces.values()
        if any(record.get("event") == "player-connected" for record in records)
    ]
    if len(candidates) != 1:
        raise BlockedError(f"expected one primary IPC trace, observed {len(candidates)}")
    return candidates[0]


def _same_message(first: str, second: str) -> bool:
    return playback.same_message(first, second)


def extract_complete_file_observations(
    records: Sequence[dict[str, Any]], expected_messages: Sequence[str],
) -> list[dict[str, Any]]:
    """Extract exact file observations; incomplete proof is BLOCKED."""
    rows = [(index, message) for index, message in _message_rows(records)
            if not message.startswith("--")]
    expected = [str(message) for message in expected_messages]
    if len(rows) != len(expected) or any(not _same_message(actual, wanted)
                                         for (_, actual), wanted in zip(rows, expected)):
        raise ContractError(f"file message order differs: {[message for _, message in rows]!r} != {expected!r}")
    observations: list[dict[str, Any]] = []
    for index, message in rows:
        policy, result = _followup(records, index)
        observations.append(_FileObservation(message, policy, result, index).as_dict())
    return observations


def extract_command_observations(
    records: Sequence[dict[str, Any]], expected_sequence: Sequence[str],
) -> dict[str, Any]:
    """Check file-command-file FIFO and prove that command resets the burst.

    This function intentionally does not accept matching final UI state as a
    substitute for the command boundary or the two file policy records.
    """
    rows = _message_rows(records)
    actual = [message for _, message in rows]
    expected = [str(message) for message in expected_sequence]
    if len(actual) != len(expected) or any(not _same_message(a, e) for a, e in zip(actual, expected)):
        raise ContractError(f"command message order differs: {actual!r} != {expected!r}")
    command_positions = [index for index, message in enumerate(actual) if message.startswith("--")]
    if command_positions != [1] or len(actual) != 3:
        raise ContractError("command case must be exactly file, command, file")
    file_observations: list[_FileObservation] = []
    for position in (0, 2):
        record_index, message = rows[position]
        policy, result = _followup(records, record_index)
        file_observations.append(_FileObservation(message, policy, result, record_index))
    between = records[rows[1][0] + 1 : rows[2][0]]
    if any(row.get("event") in ("player-open-policy", "player-open-result") for row in between):
        raise ContractError("command produced a late file policy/result before file two")
    policies = [bool(item.policy.get("continuation")) for item in file_observations]
    if policies != [False, False]:
        raise ContractError("file two did not prove a command reset")
    return {
        "message_sequence": actual,
        "file_observations": [item.as_dict() for item in file_observations],
        "file_policies": policies,
        "command_reset_limited": True,
        "limitation": "command behavioral effects are not proved by this reset-only case",
    }


def classify_receipts(receipts: Sequence[ReceiptBracket]) -> BurstClassification:
    """Apply conservative receipt-bracket gates, failing closed on uncertainty."""
    if not receipts:
        raise BlockedError("receipt classification has no brackets")
    if any(receipt.kind != "file" or not receipt.complete for receipt in receipts):
        raise BlockedError("receipt classification requires complete file brackets")
    for previous, current in zip(receipts, receipts[1:]):
        if current.lower < previous.upper:
            raise BlockedError("receipt brackets overlap; boundary is uncertain")
    continuations = [False]
    intervals: list[dict[str, Any]] = [{
        "clock": "perf_counter",
        "message": receipts[0].message,
        "first": True,
        "continuation": False,
        "reset_reason": "initial",
    }]
    burst_start = receipts[0]
    for previous, current in zip(receipts, receipts[1:]):
        max_gap = current.upper - previous.lower
        min_gap = current.lower - previous.upper
        max_age = current.upper - burst_start.lower
        min_age = current.lower - burst_start.upper
        detail: dict[str, Any] = {
            "clock": "perf_counter",
            "message": current.message,
            "previous": previous.message,
            "max_gap": max_gap,
            "min_gap": min_gap,
            "max_age": max_age,
            "min_age": min_age,
        }
        if max_gap < IDLE_LIMIT_SECONDS and max_age < MAXIMUM_BURST_SECONDS:
            continuation = True
            detail.update(continuation=True, reset_reason=None)
        elif min_gap >= IDLE_LIMIT_SECONDS:
            continuation = False
            detail.update(continuation=False, reset_reason="idle")
            burst_start = current
        elif min_age >= MAXIMUM_BURST_SECONDS and max_gap < IDLE_LIMIT_SECONDS:
            continuation = False
            detail.update(continuation=False, reset_reason="cap")
            burst_start = current
        else:
            raise BlockedError(
                f"receipt boundary is uncertain for {current.message!r}: {detail!r}"
            )
        continuations.append(continuation)
        intervals.append(detail)
    return BurstClassification(continuations, intervals)


def validate_command_brackets(receipts: Sequence[ReceiptBracket]) -> dict[str, Any]:
    """Require a command triplet to be conservatively inside both gates."""
    if len(receipts) != 3 or receipts[1].kind != "command":
        raise ContractError("command timing requires file, command, file brackets")
    if any(not receipt.complete for receipt in receipts):
        raise BlockedError("command timing has an incomplete receipt bracket")
    if any(current.lower < previous.upper
           for previous, current in zip(receipts, receipts[1:])):
        raise BlockedError("command timing brackets overlap")
    maximum_gaps = [current.upper - previous.lower
                    for previous, current in zip(receipts, receipts[1:])]
    minimum_gaps = [current.lower - previous.upper
                    for previous, current in zip(receipts, receipts[1:])]
    maximum_gap = max(maximum_gaps)
    maximum_total = receipts[-1].upper - receipts[0].lower
    if maximum_gap >= IDLE_LIMIT_SECONDS or maximum_total >= IDLE_LIMIT_SECONDS:
        raise BlockedError(
            f"command timing is not proven inside gates: max_gap={maximum_gap}, "
            f"max_total={maximum_total}"
        )
    return {
        "clock": "perf_counter",
        "maximum_gap": maximum_gap,
        "minimum_gaps": minimum_gaps,
        "maximum_total": maximum_total,
        "gap_limit_seconds": IDLE_LIMIT_SECONDS,
        "total_limit_seconds": MAXIMUM_BURST_SECONDS,
    }


def expected_continuations(case: str, count: int) -> list[bool]:
    if case == "ipc_short":
        expected = [False, True, True]
    elif case == "ipc_idle":
        expected = [False, False, True]
    elif case == "ipc_maximum":
        expected = [False] + [True] * (count - 2) + [False]
    else:
        raise ContractError(f"no burst expectation for {case!r}")
    if len(expected) != count:
        raise ContractError(f"case {case} expected {len(expected)} messages, got {count}")
    return expected


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _case_result(case: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "case": case,
        "group": CASE_GROUP,
        "status": status,
        "cleanup_verified": False,
        **extra,
    }


def _write_summary(output: Path, cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for case in cases:
        status = str(case.get("status", "FAIL"))
        counts[status] = counts.get(status, 0) + 1
    status = "PASS" if cases and counts.get("PASS") == len(cases) else (
        "BLOCKED" if counts.get("BLOCKED") and not counts.get("FAIL") else "FAIL"
    )
    summary = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "group": CASE_GROUP,
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


class IPCPlaybackCaseRun(playback.PlaybackCaseRun):
    """PlaybackCaseRun specialization for exact-package IPC-only cases."""

    def _write_setup(self, settings: str, playlist: Sequence[Path]) -> None:
        if settings.count("EnqueueFiles=true") != 1:
            raise ContractError("IPC setup expected one true EnqueueFiles setting")
        settings = settings.replace("EnqueueFiles=true", "EnqueueFiles=false", 1)
        super()._write_setup(settings, playlist)

    def _send_secondary_arguments(self, arguments: Sequence[str]) -> tuple[Any, float]:
        environment = probe._app_environment()
        if self.trace_directory is not None:
            environment["NULLOY_STARTUP_TRACE_DIR"] = str(self.trace_directory)
        if self.headless_audio:
            environment["GST_PLUGIN_FEATURE_RANK"] = (
                "directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0"
            )
        lower = time.perf_counter()
        process = subprocess.Popen([str(self.package.executable), *arguments], env=environment)
        return process, lower

    def _complete_file_trace(self, expected: Sequence[str]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        deadline = time.monotonic() + 15.0
        last: dict[str, list[dict[str, Any]]] = {}
        while time.monotonic() < deadline:
            last = self._snapshot_traces()
            try:
                records = _primary_records(last)
                file_rows = [(index, message) for index, message in _message_rows(records)
                             if not message.startswith("--")]
                if len(file_rows) < len(expected):
                    time.sleep(0.002)
                    continue
                if len(file_rows) > len(expected):
                    raise ContractError("primary trace contains an unexpected extra file message")
                if len(file_rows) == len(expected) and any(
                    not _same_message(actual, wanted)
                    for (_, actual), wanted in zip(file_rows, expected)
                ):
                    raise ContractError("primary trace file message order differs")
                observations = extract_complete_file_observations(records, expected)
                return last, observations
            except ContractError:
                raise
            except BlockedError:
                pass
        raise BlockedError(f"primary trace did not complete file observation: {expected!r}")

    def _wait_command_entry(self, expected: str, prior_messages: int) -> dict[str, list[dict[str, Any]]]:
        deadline = time.monotonic() + 15.0
        last: dict[str, list[dict[str, Any]]] = {}
        while time.monotonic() < deadline:
            last = self._snapshot_traces()
            try:
                records = _primary_records(last)
                rows = _message_rows(records)
                if len(rows) == prior_messages + 1 and _same_message(rows[-1][1], expected):
                    return last
            except BlockedError:
                pass
            time.sleep(0.002)
        raise BlockedError(f"primary trace did not observe command entry: {expected!r}")

    @staticmethod
    def _wait_client(process: Any, message: str) -> dict[str, Any]:
        try:
            return_code = process.wait(timeout=10)
        except subprocess.TimeoutExpired as exc:
            raise ContractError(f"secondary IPC client timed out: {message!r}") from exc
        if return_code != 0:
            raise ContractError(f"secondary IPC client exit code {return_code}: {message!r}")
        return {"message": message, "exit_code": return_code, "acknowledged": True}

    def _dispatch_file(
        self, path: Path, prior_files: Sequence[str], brackets: list[ReceiptBracket], outcomes: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        process, lower = self._send_secondary_arguments((str(path),))
        expected = [*prior_files, str(path)]
        traces, observations = self._complete_file_trace(expected)
        upper = time.perf_counter()
        outcomes.append(self._wait_client(process, str(path)))
        observation = observations[-1]
        brackets.append(ReceiptBracket(
            str(path), lower, upper, "file", True, True, "policy-and-result",
        ))
        _write_json(self.evidence / 'ipc-brackets-progress.json', [b.as_dict() for b in brackets])
        _write_json(self.evidence / 'client-outcomes.json', outcomes)
        _write_json(self.evidence / "last-complete-file.json", observation)
        return traces

    def _dispatch_command(
        self, option: str, prior_messages: int, outcomes: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        process, lower = self._send_secondary_arguments((option,))
        traces = self._wait_command_entry(option, prior_messages)
        # Commands have no file policy/result pair.  The entry is the only
        # command-specific marker; file two is dispatched only after this client
        # is acknowledged, and the final trace proves the reset ordering.
        upper = time.perf_counter()
        outcomes.append(self._wait_client(process, option))
        return traces, ReceiptBracket(
            option, lower, upper, "command", False, False, "command-message-entry-before-next-file",
        )

    def _validate_client_outcomes(self, expected: Sequence[str], expected_clients: int) -> dict[str, Any]:
        traces = self._snapshot_traces()
        primary = _primary_records(traces)
        started = [records for records in traces.values()
                   if any(row.get("event") == "main-start" for row in records)]
        primaries = [records for records in started
                     if any(row.get("event") == "player-connected" for row in records)]
        if len(primaries) != 1 or len(started) != expected_clients + 1:
            raise ContractError("IPC traces do not identify one primary and every secondary launch")
        secondaries = [records for records in started if records is not primaries[0]]
        sent: list[str] = []
        for records in secondaries:
            exits = [row for row in records if row.get("event") == "main-exit"]
            sends = [row for row in records if row.get("event") == "send-begin"]
            acks = [row for row in records if row.get("event") == "send-end"]
            if len(exits) != 1 or exits[0].get("exit_code") != 0 or exits[0].get("role") != "client":
                raise ContractError("secondary IPC client did not exit 0 as a client")
            if len(sends) != 1 or len(acks) != 1 or acks[0].get("acknowledged") is not True:
                raise ContractError("secondary IPC client lacks one acknowledged send")
            sent.append(str(sends[0].get("message", "")))
        received = [str(row.get("message", "")) for row in primary if row.get("event") == "receive-frame"]
        dispatched = [str(row.get("message", "")) for row in primary if row.get("event") == "receive-dispatch"]
        if received != dispatched or len(received) != len(expected):
            raise ContractError("primary receive/dispatched IPC order is not exact")
        remaining = list(expected)
        for actual in sent:
            match = next((i for i,wanted in enumerate(remaining) if _same_message(actual,wanted)), None)
            if match is None:
                raise ContractError('unexpected or duplicate client send')
            remaining.pop(match)
        if remaining:
            raise ContractError(f"secondary send order differs: {sent!r} != {list(expected)!r}")
        delivered = [
            part for row in primary if row.get("event") == "player-message"
            for part in _message_parts(row)
        ]
        if len(delivered) != len(expected) or any(
            not _same_message(a, e) for a, e in zip(delivered, expected)
        ):
            raise ContractError(f"player-message receipt order differs: {delivered!r} != {list(expected)!r}")
        if len(sent) != len(expected_clients * [None]):
            raise ContractError("secondary launch count differs from expected")
        return {
            "primary_process_count": 1,
            "secondary_client_count": len(secondaries),
            "client_receipts_exact": True,
            "client_ack_exit_exact": True,
            "player_message_order_exact": True,
        }

    def _burst_files(self, case: str) -> list[Path]:
        if case == "ipc_short" or case == "ipc_idle":
            return list(self.incoming)
        if case == "ipc_maximum":
            return [self.incoming[index % len(self.incoming)] for index in range(MAXIMUM_MESSAGE_COUNT)]
        raise ContractError(f"not a burst case: {case!r}")

    def _result_burst(self, case: str) -> dict[str, Any]:
        files = self._burst_files(case)
        brackets: list[ReceiptBracket] = []
        outcomes: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        expected_messages: list[str] = []
        schedule_anchor: float | None = None
        for index, path in enumerate(files):
            if case == "ipc_idle" and index == 1:
                time.sleep(IDLE_LIMIT_SECONDS + 0.10)
            elif case == "ipc_maximum" and index:
                if schedule_anchor is None:
                    raise ContractError("maximum schedule anchor is missing")
                target = (schedule_anchor + MAXIMUM_RESET_ANCHOR_SECONDS
                          if index == MAXIMUM_MESSAGE_COUNT - 1
                          else schedule_anchor + index * MAXIMUM_SCHEDULE_STEP_SECONDS)
                delay = target - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            traces = self._dispatch_file(path, expected_messages, brackets, outcomes)
            expected_messages.append(str(path))
            records = _primary_records(traces)
            observations = extract_complete_file_observations(records, expected_messages)
            if schedule_anchor is None:
                schedule_anchor = brackets[0].upper
        classification = classify_receipts(brackets)
        expected_policy = expected_continuations(case, len(files))
        if classification.continuations != expected_policy:
            raise BlockedError(
                f"receipt boundary sequence differs: {classification.continuations!r} != {expected_policy!r}"
            )
        if [o['policy']['continuation'] for o in observations] != expected_policy:
            raise ContractError('actual grouping differs from independently proven boundary scenario')
        expected_results = expected_file_results(expected_messages, expected_policy)
        actual_results = validate_file_results(observations, expected_messages, expected_policy)
        expected_paths = [Path(path) for path in expected_results[-1]['rows']]
        rows = self._read_playlist_rows(expected_paths)
        after = self._observe_state("playing", [path.name for path in self.fixtures], expected_paths[0].name)
        final_expected = dict(rows=[path.name for path in expected_paths], current_media=expected_paths[0].name, playing_row=0)
        self._assert_one_settled_player()
        client_evidence = self._validate_client_outcomes(expected_messages, len(files))
        _write_json(self.evidence / "ipc-receipts.json", {
            "case": case,
            "clock": "perf_counter",
            "brackets": [bracket.as_dict() for bracket in brackets],
            "intervals": classification.intervals,
            "continuations": classification.continuations,
            "expected_continuations": expected_policy,
            "schedule": {
                "step_seconds": MAXIMUM_SCHEDULE_STEP_SECONDS if case == "ipc_maximum" else None,
                "reset_anchor_seconds": MAXIMUM_RESET_ANCHOR_SECONDS if case == "ipc_maximum" else None,
                "controller_only": True,
            },
        })
        _write_json(self.evidence / "client-outcomes.json", outcomes)
        _write_json(self.evidence / "ipc-observations.json", {
            "messages": expected_messages,
            "results": actual_results,
            "expected_results_independent_of_policy": expected_results,
            "final_visible_rows": rows,
            "final_expected_state": final_expected,
            "final_current_media": after.get("current_media"),
            "final_playing_row": 0,
        })
        return {
            "messages": expected_messages,
            "rows": rows,
            "after": after,
            "receipt_brackets": [bracket.as_dict() for bracket in brackets],
            "assertions": {
                "receipt_boundaries_proven_by_perf_counter_brackets": True,
                "receipt_policy_sequence_exact": True,
                "player_open_results_exact_independent_of_policy": True,
                "final_visible_indexed_playlist_exact": rows == final_expected["rows"],
                "final_current_playback_directly_observed": after.get("current_media") == final_expected["current_media"],
                **client_evidence,
            },
            "limitations": [
                "command behavioral effects are not part of these burst cases",
                "audio output is not an acceptance assertion",
                "exact 250ms and 1000ms edge values are not established; scenarios stay inside or outside the gates",
            ],
        }

    def _result_commands(self) -> dict[str, Any]:
        option = {
            "ipc_command_next": "--next",
            "ipc_command_prev": "--prev",
            "ipc_command_stop": "--stop",
            "ipc_command_pause": "--pause",
        }[self.spec.name]
        first, second = self.incoming[0], self.incoming[1]
        outcomes: list[dict[str, Any]] = []
        brackets: list[ReceiptBracket] = []
        expected_messages: list[str] = []
        file_observations: list[dict[str, Any]] = []
        traces = self._dispatch_file(first, [], brackets, outcomes)
        expected_messages.append(str(first))
        for _ in (option,):
            traces, command_bracket = self._dispatch_command(option, len(expected_messages), outcomes)
            brackets.append(command_bracket)
            expected_messages.append(option)
        traces = self._dispatch_file(second, [str(first)], brackets, outcomes)
        expected_messages.append(str(second))
        records = _primary_records(traces)
        _write_json(self.evidence / 'ipc-brackets-progress.json', [b.as_dict() for b in brackets])
        command_timing = validate_command_brackets(brackets)
        command_observation = extract_command_observations(
            records, [str(first), option, str(second)]
        )
        file_observations = command_observation["file_observations"]
        expected_results = expected_file_results([str(first), str(second)])
        actual_results = validate_file_results(file_observations, [str(first), str(second)])
        rows = self._read_playlist_rows([second])
        after = self._observe_state("playing", [path.name for path in self.fixtures], second.name)
        final_expected = expected_final_state([second.name])
        self._assert_one_settled_player()
        command_timing = validate_command_brackets(brackets)
        client_evidence = self._validate_client_outcomes(expected_messages, 3)
        _write_json(self.evidence / "command-trace.json", {
            "message_sequence": expected_messages,
            "file_policies": command_observation["file_policies"],
            "command_reset_limited": True,
            "limitation": command_observation["limitation"],
            "brackets": [bracket.as_dict() for bracket in brackets],
            "timing": command_timing,
            "clock": "perf_counter",
        })
        _write_json(self.evidence / "client-outcomes.json", outcomes)
        _write_json(self.evidence / "ipc-observations.json", {
            "messages": expected_messages,
            "results": actual_results,
            "expected_results_independent_of_policy": expected_results,
            "final_visible_rows": rows,
            "final_expected_state": final_expected,
            "final_current_media": after.get("current_media"),
            "final_playing_row": 0,
        })
        return {
            "messages": expected_messages,
            "rows": rows,
            "after": after,
            "command": option,
            "receipt_brackets": [bracket.as_dict() for bracket in brackets],
            "assertions": {
                "file_command_file_fifo_exact": True,
                "command_receipt_brackets_inside_gates": command_timing["maximum_gap"] < IDLE_LIMIT_SECONDS and command_timing["maximum_total"] < MAXIMUM_BURST_SECONDS,
                "command_reset_proven_without_final_ui_substitution": command_observation["command_reset_limited"],
                "file_two_policy_false_after_command": command_observation["file_policies"] == [False, False],
                "player_open_results_exact_independent_of_policy": True,
                "final_visible_indexed_playlist_exact": rows == final_expected["rows"],
                "final_current_playback_directly_observed": after.get("current_media") == final_expected["current_media"],
                **client_evidence,
            },
            "limitations": [
                "command behavioral effects are not proved by this reset-only case",
                "audio output is not an acceptance assertion",
                "exact 250ms and 1000ms edge values are not established",
            ],
        }

    def _result_command(self) -> dict[str, Any]:
        if self.spec.name in ("ipc_short", "ipc_idle", "ipc_maximum"):
            return self._result_burst(self.spec.name)
        return self._result_commands()


def _prepare_download_tmp(output: Path) -> Path:
    directory = output.resolve() / "download-tmp"
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(directory)
    tempfile.tempdir = None
    return directory


def run_case(args: argparse.Namespace, case: str) -> tuple[int, dict[str, Any]]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _prepare_download_tmp(output)
    run_id = uuid.uuid4().hex[:12]
    evidence = _case_result(case, "BLOCKED", package=str(args.package.resolve()), run_id=run_id)
    package_temp = Path(tempfile.mkdtemp(prefix=f"pr24-ipc-package-{run_id}-"))
    runtime: IPCPlaybackCaseRun | None = None
    try:
        source_sha = probe.parse_source_sha(args.source_sha)
        package = probe.extract_and_validate(args.package.resolve(), package_temp, source_sha)
        evidence.update({
            "archive_sha256": package.archive_sha256,
            "executable_sha256": package.executable_sha256,
            "manifest_executable_sha256": package.contract.files[package.contract.executable],
            "file_hashes_verified": package.file_hashes_verified,
            "source_commit": package.contract.source_commit,
            "tracked_changes": False,
            "upstream_update_check": package.contract.upstream_update_check,
            "qt_major": package.contract.qt_major,
            "portable": package.contract.portable,
            "root": package.contract.root,
            "executable": package.contract.executable,
            "audio_mode": "no-device-fallback" if args.headless_audio else "device",
            "download_tmp": str(_prepare_download_tmp(output)),
        })
        spec = playback.CaseSpec(case, "commands", enqueue=False)
        runtime = IPCPlaybackCaseRun(package, output, run_id, spec, args.headless_audio)
        result = runtime.execute()
        evidence.update(result)
        assertions = list(result.get("assertions", {}).values())
        evidence["cleanup_verified"] = bool(runtime.cleanup_verified)
        evidence["status"] = probe.verdict(assertions, runtime.cleanup_verified)
        if evidence["status"] != "PASS":
            evidence["error"] = "one or more exact-package IPC assertions failed"
    except (probe.BlockedError, BlockedError) as exc:
        evidence.update(status="BLOCKED", error=str(exc), error_traceback=traceback.format_exc())
    except Exception as exc:
        evidence.update(status="FAIL", error=str(exc), error_traceback=traceback.format_exc())
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
    return _case_result(case, "FAIL", error=f"case watchdog exceeded {seconds:g} seconds",
                        cleanup_errors=["child process was terminated by supervisor"])


def run_all(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _prepare_download_tmp(output)
    cases: list[dict[str, Any]] = []
    names = selected_cases(args)
    for index, case in enumerate(names):
        case_output = output / case
        command = [
            sys.executable, str(Path(__file__).resolve()),
            "--package", str(args.package.resolve()),
            "--source-sha", args.source_sha,
            "--output", str(case_output),
            "--case", case,
            "--case-timeout", str(args.case_timeout),
            "--_worker",
        ]
        if args.headless_audio:
            command.append("--headless-audio")
        try:
            completed = subprocess.run(command, timeout=args.case_timeout + 5,
                                       capture_output=True, text=True)
            case_output.mkdir(parents=True, exist_ok=True)
            _write_text(case_output / "worker.stdout.txt", completed.stdout)
            _write_text(case_output / "worker.stderr.txt", completed.stderr)
        except subprocess.TimeoutExpired as exc:
            record = _timeout_result(case, args.case_timeout)
            case_output.mkdir(parents=True, exist_ok=True)
            _write_text(case_output / "worker.stdout.txt", str(exc.stdout or ""))
            _write_text(case_output / "worker.stderr.txt", str(exc.stderr or ""))
        else:
            result_path = case_output / "result.json"
            if result_path.is_file():
                try:
                    record = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    record = _case_result(case, "FAIL", error=f"invalid child result: {exc}")
            else:
                record = _case_result(case, "FAIL", error=(
                    f"case child produced no result.json (exit {completed.returncode})"
                ))
        if not (case_output / "result.json").is_file():
            _write_json(case_output / "result.json", record)
        cases.append({
            "case": case,
            "status": record.get("status", "FAIL"),
            "cleanup_verified": bool(record.get("cleanup_verified")),
            "result": str((case_output / "result.json").relative_to(output)),
            "error": record.get("error"),
        })
        if record.get("cleanup_verified") is not True:
            for skipped in names[index + 1 :]:
                cases.append(_case_result(skipped, "SKIPPED",
                                           error="sequential safety stop after unverified cleanup"))
            break
    summary = _write_summary(output, cases)
    return (0 if summary["status"] == "PASS" else 2 if summary["status"] == "BLOCKED" else 1), summary


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args._worker:
        code, result = run_case(args, args.case)
    else:
        code, result = run_all(args)
    print(f"{result['status']}: {result.get('error', 'exact-package IPC acceptance completed')}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
