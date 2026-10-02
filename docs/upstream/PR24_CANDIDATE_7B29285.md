# PR24 updated-candidate acceptance: 7b29285

## Exact identity

- PR head: `7b292852a85bd6a40a99cd7d7813660250ed5b3d`.
- Reviewed opt-in post-action diagnostics are part of this actual candidate, not a separately instrumented substitute.
- Package build: https://github.com/Auda29/nulloy/actions/runs/36995053598
- Artifact: `Nulloy-Qt6-windows-x64`.
- ZIP SHA-256: `2327a4a5e5599e7788f595c4babb83595aef37939d2375b8c72cca1edf53614f`.
- EXE SHA-256: `dd981e98a0a70f1a90843961615c7f9a7d8923bfa05d2a5b8b73b198977cb10a`.
- All 497 manifest file hashes independently verified before native execution and in each case.
- Probe commit: `f74eff44aeaa3d6d6ca8a3efc94220e99634c23c`.

## Executed native results

Acceptance run: https://github.com/Auda29/nulloy/actions/runs/36996164364

| Group | Executed | PASS | FAIL/BLOCKED |
|---|---:|---:|---:|
| Populated playlist: four preferences x playing/paused/stopped | 12 | 12 | 0 |
| Settled restored playlist, including persisted settings readback | 12 | 12 | 0 |
| Sequential CLI commands | 4 | 4 | 0 |
| IPC short burst, idle, absolute cap, four command resets | 7 | 7 | 0 |
| Total | 35 | 35 | 0 |

All 35 unique downloaded result files and four group summaries were parsed and
checked for expected case coverage, candidate/ZIP/EXE identity, manifest count,
assertions, process cleanup and absence of cleanup errors. Direct current-media,
state and position samples and visible ordered rows were checked against the
scenario's preferences; selected rows were not interpreted as current playback.
The IPC audit independently recomputed conservative timing bounds and expected
replacement/retention rows rather than trusting the reported policy flags.

Conservative monotonic bounds, rounded to two decimals:

- Short three-message burst: total upper bound 108.98 ms.
- Idle reset: gap lower bound 352.61 ms.
- Absolute cap across 13 launches: age lower bound 1050.22 ms while final gap upper bound 210.49 ms.
- File/command/file upper bounds: next 152.97 ms, prev 108.18 ms, stop 107.88 ms, pause 108.65 ms. Each resets an otherwise live grouping window.

These are controller receipt brackets, not exact player timestamps. Handler
records are emitted after processing; the wall-clock time_msec field is not used
to prove the policy thresholds. Immediate playing_row=-1 is allowed during
asynchronous loading, but separate settled UI playback remains mandatory.

## Other gates

- Local real-player regression: 37 passed, zero failed/skipped, including tracing enabled/disabled/unavailable and post-action write ordering.
- Independent code re-review passed after moving diagnostic I/O after actions.
- Native Linux PR CI passed: https://github.com/Auda29/nulloy/actions/runs/36995057457
- Windows Qt5 and Qt6 PR CI passed: https://github.com/Auda29/nulloy/actions/runs/36995057581
- Package workflow passed for both Qt versions. The separate 35-case matrix above is specifically Qt6.

## Scope and accepted risks

Windows Server 2022 with no-device audio fallback is not Windows 11 or audible
hardware testing. Explorer activation uses the disposable test verb, not a user's
real default association/Enter path. Fast separate Explorer opens and opens during
startup restoration remain unverified; restored cases execute after startup has
settled. CLI reset cases do not prove every transient intermediate command state.
The existing --pause mapping to play() is unchanged. Time-based grouping remains
a heuristic, not arbitrary shell transaction detection.

The maintainer explicitly accepted the listed remaining manual gaps for an
integration-branch merge: https://github.com/Auda29/nulloy/pull/24#issuecomment-5949127763
These gaps are not relabeled as passed. Opt-in synchronous diagnostic I/O can add
overhead to later messages; the native matrix proves the actual candidate with
tracing enabled, not zero tracing overhead or exact equality at timing edges.

This evidence satisfies the agreed automated candidate checks. PR24 remains draft
and unmerged until the maintainer authorizes the merge. Integration is unchanged.
The earlier aa78a33 preflight remains failed/blocked, not retroactively green.

## Evidence retention

Four `pr24-candidate-*` artifacts on the acceptance run retain raw UIA, screenshots,
traces, results and cleanup records for seven days. The package artifact retains
three days. Both package and acceptance artifacts are archived locally under
`/home/hermes/workspace/nulloy-acceptance/pr24-7b29285/`.
Local replays: `audit-candidate.py` -> `candidate-audit.json` (35 cases),
`audit-ipc.py` -> `ipc-audit.json` (seven IPC cases). Preserve the local archive
before GitHub artifact expiration; do not rebuild and silently substitute hashes.
