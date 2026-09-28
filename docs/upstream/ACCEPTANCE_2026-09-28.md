# Merge acceptance follow-up — 2026-09-28

## Verified integration baseline

Integration `5b2c600c68c475de9fa9176005d9620f0fcc92e4` passed:

- [Linux 36410316706](https://github.com/Auda29/nulloy/actions/runs/36410316706):
  all 14 discovered native issue harnesses passed. Downloaded `results.json`
  confirms issues 11, 121, 129, 132, 139, 141, 146, 176, 218, 238, 240, 241, 245, 261.
- [Windows 36410317010](https://github.com/Auda29/nulloy/actions/runs/36410317010):
  Qt5/Qt6 builds, component tests, package/format verification and applicable
  Qt6 startup/registry/skin checks passed. Package ZIP upload was intentionally off.

## PR #16 — native Windows geometry

The first Qt5 standalone build exposed missing `UNICODE` and `_UNICODE` definitions
in the harness (not in the player build). PR head
`46712208431dbad1a3300780a92720c185fcbaff` corrects those definitions only.

[Run 36412027745](https://github.com/Auda29/nulloy/actions/runs/36412027745)
checked that exact head. Both Qt 5.15.19 and Qt 6.11.2 passed 45 QtTest results
including init/cleanup, zero failures or skips, with `QT_QPA_PLATFORM=windows`.
Text/XML reports were downloaded and checked. Synthetic screen rectangles and
notifications ran alongside real native window-state/frame handling on the
Windows Server 2022 Hyper-V display.

Physical unplug/replug, mixed per-monitor DPI and final packaged-skin testing
remain open. This does not certify a multi-monitor Windows 11 installation.

## PR #15 — real recycle-bin adapter

The same run checked unchanged PR head
`774894c4eba7b646beafb38313fe0dc73cfb4671`. Each Qt version passed 26 shared-contract
and four native QtTest results, including init/cleanup, with no failures or skips.
The native test generated its own Unicode-named file on C:, verified matching
recycle-bin metadata and payload, and checked missing-file errors. No recycle-bin
configuration was changed. The reports were downloaded and checked.

This is not the final player-action matrix: cancellation/partial cancellation,
recycling-unavailable fallback, duplicate rows and current/next items during
Play/Pause/Stop still need player-level acceptance. The original macOS case is open.

## PR #24 + #29 — combined package, observed acceptance failure

Test branch `test/windows-open-acceptance` assembled integration `5b2c600`, PR #29
`9d7de5108f842269ffa2a99048d69577a123d1ac`, and PR #24
`21848c11d6ca4dc1e1c8552285ffc1b84946a029`. It also carries separate probe tooling.

[Run 36411154445](https://github.com/Auda29/nulloy/actions/runs/36411154445)
passed both Windows builds/package checks and the combined Linux harnesses.
The actual packaged source is `17bc6455d5b787754ad0540ebca9b5f02b8920e0`.

| Identity | SHA-256 |
| --- | --- |
| Qt6 package ZIP | `62cae150f145d8f2481e937e3a215b6bf3900e67e1e806a835c700745b015e90` |
| Packaged EXE | `51f6c08dc52168aec4aaad4ebdedf224940d99266684ef60623808ab2c495a06` |

The package was downloaded and all 497 manifest file hashes, ZIP and EXE hashes
were independently recomputed locally. The real Explorer diagnostic **failed**:
Explorer selection recorded files 01, 02 and 03, while 21 UIA playlist snapshots
contained only 03 and 02. The downloaded player screenshot also shows only two
rows. Cleanup reported success with no errors. This is a missing-playlist-entry
observation, not deletion of an input file and not yet a proven root cause.

The initial diagnostic used the historical probe at `17bc645`. A subsequent
matrix uses strengthened registry/menu checks and repeated process discovery,
with the same verified package bytes. Its verdict belongs to its own run;
this original failure must not be relabelled if a later run passes.

Matrix run `36412673752` stopped each case in probe setup because Python cannot
construct `winreg.PyHKEY` directly from the Win32 handle. Those nine setup errors
are **not player failures** and its cleanup booleans cannot certify registry
cleanup: creation had already occurred before the wrapper raised. The follow-up
uses an explicitly closed raw handle and adds a real Windows regression for
creation, collision refusal, retained foreign values and handle lifecycle.

## Merge decision

All five functional/test PRs remain drafts. No functional PR was merged into
integration, and integration was not promoted to master. Original-project PRs
were not changed. Native component success narrows the remaining work but does
not override the combined Explorer failure or the unexecuted acceptance cases.
