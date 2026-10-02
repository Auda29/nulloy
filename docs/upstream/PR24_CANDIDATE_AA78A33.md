# PR24 updated candidate: observer preflight

Historical preflight report, preserved during 2 October 2026 cleanup. Its failed/
blocked results remain unchanged. Later accepted candidate and merge status are
recorded in `PR24_CANDIDATE_7B29285.md`; this older package is not the merged one.

## Exact candidate and package

- PR head: `aa78a3352497ca7ba431e9aa0ff50e820e95048a`.
- Successful package build: https://github.com/Auda29/nulloy/actions/runs/36991823896
- Artifact: `Nulloy-Qt6-windows-x64`.
- ZIP SHA-256: `e9f94e6045333b111b492079df0584fc0a3f5834fa884fab3d261a005f15164e`.
- EXE SHA-256: `84c33a989f0e5bdbe818acf0d17c8a541c6c6810c4d4960fe069d54e0e1f4c74`.
- All 497 manifest file hashes independently verified; source matches and tracked_changes is false.
- Local archive: `/home/hermes/workspace/nulloy-acceptance/pr24-aa78a33/`.

The old original-package tests remain tied to their old source and hashes. They
are not evidence of native playback/IPC acceptance of this candidate.

## Native preflight result

Run: https://github.com/Auda29/nulloy/actions/runs/36993149897

Probe commit: `7d9fae52433b90d8f32c7a99e775a5654f8d0167`.

Two cases executed on Windows Server 2022 using the unmodified candidate package:

| Case | Raw verdict | Error |
|---|---|---|
| `ipc_short` | BLOCKED | Primary trace did not complete file observation |
| `populated_enqueue_false_play_false_playing` | FAIL | Player message delivery is not exact-once for selected files |

Both result files confirm the fixed source/ZIP/EXE identities, 497 verified files,
cleanup_verified=true and no cleanup errors. No complete playback/IPC matrix was
run and neither preflight case is a PASS.

## Root cause and limits

The previous package included additional `NPlayer::readMessage` instrumentation:
`player-message`, `player-open-policy`, and `player-open-result`. That diagnostic
instrumentation is absent from this PR head. The existing observers require it.
This was established by source comparison and then confirmed by the actual native
trace files; there were zero such events in both cases.

The IPC case's transport log contains one received and dispatched file message.
The playback case contains three received and dispatched file messages. Those
transport records cannot replace proof of completed GUI/player processing or
policy/result snapshots. In particular, receipt/dispatch by the transport thread
must not be treated as a post-handler completion barrier.

The playback FAIL is an observer prerequisite failure, not evidence that the
player lost files. Its raw status remains FAIL; no result is retroactively
relabeled PASS. The full acceptance is blocked on observation compatibility.

Possible next paths require an explicit scope decision: add opt-in player
instrumentation to the actual PR candidate, then rebuild and retest that new
candidate; or redesign the black-box observer with equivalent proof strength.
A separate instrumented diagnostic build alone cannot certify the unmodified
candidate. No product source, draft status, or integration branch was changed by
this preflight.

The maintainer's recorded acceptance of manual Explorer/startup/Windows-11/audio
risks remains separate; it does not waive this automated observer prerequisite.
