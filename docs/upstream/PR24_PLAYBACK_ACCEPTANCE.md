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

IPC native results are pending. PR24 remains draft; fast independent Explorer
interaction, Windows 11, audible output and synchronous restored startup are not
certified by this follow-up.
