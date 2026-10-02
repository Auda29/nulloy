# PR24 exact-package playback acceptance

## Scope

This isolated automation branch extends native Windows/Explorer observation of
PR24. It does not change the player, rebuild its package, approve/merge PR24, or
close upstream #211. The base remains `test/windows-open-acceptance`; the current
integration branch is untouched.

## Fixed package identity

- Repository: `Auda29/nulloy`
- Original package run: `36843804143`
- Artifact: `Nulloy-Qt6-windows-x64`
- Packaged source: `be5b1e88286c1ff0bbe7e298e3585bbfb248aba5`
- ZIP SHA-256: `039c21768668d69649ee6950b9039f16b6fde0ec0835e2f8f8278ba3a79fe9be`
- EXE SHA-256: `a231f27777954ced66ba349998863c59bc415f866bda727bd72e84368ec282f2`

The original artifact was downloaded locally and all 497 manifest file hashes
verified. CI must download this original artifact, check the fixed ZIP digest,
and independently validate the extracted manifest before execution. An expired
artifact is a blocker, not permission to silently rebuild or substitute a ZIP.

## Execution

`.github/workflows/pr24-playback-acceptance.yml` runs only on the dedicated
`test/pr24-playback-acceptance` branch or explicit dispatch. It has read-only
repository/Actions permissions, runs Linux contracts first, and then runs
separate `windows-2022` jobs for `populated`, `restored`, `rapid`, and `commands`.
The maximum parallelism is two. Native observation uses disposable portable
package copies, generated WAV fixtures and the existing ownership-checked
Explorer verb/process/registry cleanup.

The intended observations cover the four enqueue/play-enqueued combinations,
stopped/playing/paused populated playlists, restored startup, independent opens
and command boundaries. Results are bound to the probe commit and original
package digest. Preserve every case result and raw observations on failure.
Unknown UI state, incomplete delivery evidence, unobserved timing or uncertain
cleanup must never become a PASS.

## Acceptance boundaries

- A GitHub-hosted Windows Server 2022 desktop is not Windows 11.
- No-device GStreamer fallback is not a hardware/audio-output acceptance test.
- Explorer invocation uses an isolated Document-model test verb. It does not
  certify a user's actual default file association or Explorer Enter behavior.
- Trace receipt timing, not controller sleep duration, determines whether an
  opening was within the 250ms idle / 1000ms absolute grouping boundaries.
- `--pause` retains the existing product mapping to `play()`. Do not interpret
  that CLI command as a pause-state setup operation.
- Historical green tests do not count as results of this new matrix.
- The candidate is a bounded time-based policy, not arbitrary shell transaction
  detection. Automated behavior checks cannot make the user's policy decision.

## Recorded native results (original package)

[Run 36977902125](https://github.com/Auda29/nulloy/actions/runs/36977902125)
executed probe `049bb4453cbcdbc6f2d6edf578191de9dccafaf4` against the original
package above. All 31 downloaded case results were parsed, and each confirms
497 manifest file hashes, the fixed source/ZIP/EXE identities, and verified
cleanup. The reported verdicts were 28 PASS, one FAIL and two BLOCKED:

- Populated playlist: 12 PASS (four preferences x playing/paused/stopped).
- Settled restored playlist plus persistence readback: 12 PASS.
- Sequential CLI command behavior: four PASS.
- Separate Explorer timing: one menu-discovery timeout, two BLOCKED.

These are scoped observations, not a merge decision. Restored cases open files
only **after** startup has settled, not during the synchronous cold-start decision.
Command cases establish sequential delivery/visible effects and a fresh group
following a command; they do not prove that the command interrupted an otherwise
live sub-250ms burst. No-delay-restart behavior over an extended idle interval is
not established by an absence of file-policy records between two messages.

The rapid Explorer observations had delivery gaps measured in seconds. Their
wall-clock-only diagnostic timestamps cannot supply the missing tight monotonic
boundary proof. Repeating the same slow context-menu loop is not a remedy.
Historical failed runs `36976593005` and `36977166589` remain failed; corrected
fixture/observer errors do not relabel their results.

## Separate IPC boundary follow-up

`pr24-ipc-acceptance.yml` and `pr24_ipc.py` reuse the exact original ZIP, without
rebuilding or changing the executable. They are explicitly **not Explorer tests**.
The controller brackets actual primary processing between monotonic timestamps
before launching a secondary executable and after observing its complete trace
result. Conservative differences between those brackets can prove that a whole
interval lies on one side of the policy threshold without pretending the package
emits a monotonic clock. A bracket that straddles a threshold is BLOCKED.

Expected playlist contents and playing row must be derived independently from
the planned scenario, with EnqueueFiles=false to make incorrect continuation
visible as incorrect replacement/retention. Native UI rows, current media and
playback observation remain required in addition to diagnostic policy records.
A command-reset check must prove both file messages would otherwise have stayed
inside the same grouping window; sequential command behavior alone is insufficient.

## Recorded IPC boundary results (original package)

[Run 36985660394](https://github.com/Auda29/nulloy/actions/runs/36985660394)
executed probe `cc4e749d8eba86f78febb840d6c3f30e172bc7a8` on Windows Server
2022: **seven PASS**, verified by downloading and independently parsing all seven
case results, receipt brackets, intermediate row snapshots, final media/position
samples and cleanup records. Every case verifies the fixed ZIP/EXE/source
identities and all 497 manifest file hashes. Initial state was a populated,
playing playlist with `seed-02.wav` current, `EnqueueFiles=false`.

The following values are conservative bounds from the same controller's monotonic
clock, not exact player-receipt timestamps (displayed rounded to two decimals).

| Case | Measured bound | Observed result |
|---|---|---|
| Short burst, three launches | Whole burst upper bound 128.54 ms | Three ordered rows retained; first incoming file playing |
| Idle boundary | Gap lower bound 353.90 ms | Second file starts a fresh group; third appends; second file playing |
| Absolute cap, 13 launches | Age lower bound 1050.72 ms; final gap upper bound 217.68 ms | Final file replaces the preceding group and plays |
| File / `--next` / file | File-to-file upper bound 126.31 ms | Command resets group; second file alone and playing |
| File / `--prev` / file | File-to-file upper bound 127.17 ms | Command resets group; second file alone and playing |
| File / `--stop` / file | File-to-file upper bound 125.07 ms | Command resets group; second file alone and playing |
| File / `--pause` / file | File-to-file upper bound 123.89 ms | Command resets group; second file alone and playing |

All intermediate file-result rows are compared to independent scenario
expectations, not expectations derived from the returned policy. Immediate
`playing_row` may be -1 while asynchronous media loading is pending, or the
expected row zero; other rows fail. Final playback is a separate mandatory
observation: correct current-media label plus three UI position samples showing
progress, not a selected row or the immediate trace. These tests do **not** prove
settled playback after every individual message in the rapid burst.

The command cases establish reset of an otherwise live grouping window, not each
command's transient playback effect before the next file. CLI mapping is unchanged:
`--pause` calls `play()` in this package. Exact equality at the 250/1000 ms edges,
arbitrary shell grouping, audible output and Windows 11 are not established.

Historical IPC run `36984639975` remains failed: its observer incorrectly required
an already-set playing row in the immediate result trace. The corrected observer
was regression-tested locally and rerun natively; this is not a retroactive PASS.
Local contract suite at the passing probe: 96 tests run, three skipped on Linux.
The duplicate legacy playback run `36985660284` was cancelled intentionally; no
new populated/restored/Explorer result is attributed to that run.

Raw evidence is retained in the run's `pr24-ipc-evidence` artifact (seven-day CI
retention) and the local archive
`/home/hermes/workspace/nulloy-acceptance/pr24-be5b1e8/run-36985660394/`.
The local independent replay is `audit-ipc-evidence.py`, with machine-readable
output `ipc-audit-36985660394.json`, both in that archive's parent directory.

PR24 remains draft. Fast independent Explorer interaction, Windows 11, audible
output, and opening files during synchronous restored startup remain open. These
scoped IPC results do not constitute a full native acceptance or merge approval.
