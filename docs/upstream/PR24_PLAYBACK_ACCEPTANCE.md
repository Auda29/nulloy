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

## Results

Pending native execution. No new player acceptance has been established by the
workflow and contract implementation alone.
