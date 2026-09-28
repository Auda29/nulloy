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

The updated PR also passed its complete Linux CI (`36411979841`) and Windows
Qt5/Qt6 CI (`36411979847`) against the current integration base.

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

Run `36412991184` exposed a second setup bug: `_registry_install` passed the
context manager instead of its yielded raw handle to `SetValueEx`. This was
reproduced locally with a real, disposable HKCU test key; the full
install/readback/cleanup regression failed before correction and passed after it.
These two failed automation runs are not product verdicts.

### Completed preference matrix

[Run 36413203120](https://github.com/Auda29/nulloy/actions/runs/36413203120),
probe source `3218973`, executed all nine scenarios against the same package ZIP
above. The Windows probe suite passed 44 tests before the native matrix.
All nine result files agree on the ZIP hash and report verified cleanup with no
cleanup errors. Exact Explorer selections and playlist snapshots were downloaded.

| Startup | EnqueueFiles | PlayEnqueued | Selected files | Observed playlist rows | Verdict |
| --- | --- | --- | ---: | ---: | --- |
| Cold | false | false | 3 | 1 | FAIL |
| Cold | false | true | 3 | 2 | FAIL |
| Cold | true | false | 3 | 3 | PASS |
| Cold | true | true | 3 | 1 | FAIL |
| Warm, initially empty | false | false | 3 | 0 | FAIL |
| Warm, initially empty | false | true | 3 | 0 | FAIL |
| Warm, initially empty | true | false | 3 | 0 | FAIL |
| Warm, initially empty | true | true | 3 | 0 | FAIL |
| Cold, larger selection | false | true | 12 | 12 | PASS |

The two PASS results cover this probe's exact membership/multiplicity checks,
not a full PR acceptance. It does not yet establish delivery order, playing row,
position, rapid independent opens or a final single-window invariant after all
secondary processes have settled. Warm observation may select the existing main
window before later launches settle; do not infer that no additional window
existed solely from its early single-window discovery.

The missing playlist rows are confirmed under multiple scenarios, but attribution
to transport, startup wiring or burst handling needs further diagnostics. The
next product investigation must capture per-launch exit codes and IPC receipt
timing, re-enumerate all package windows after clients settle, and compare delivered
messages with playlist changes. Increasing the batching timeout without this
evidence would not establish a correct fix. No failed scenario has been waived.

## Instrumented follow-up

Diagnostic source `13bae8bb241b93360787fa925acd4b1007e1a8ef`, built in
[36421225045](https://github.com/Auda29/nulloy/actions/runs/36421225045), adds
opt-in per-PID JSONL records for application arguments, peer/lock identity,
connection/acknowledgement, player construction, message dispatch and playlist
results. The probe now waits for all expected launch outcomes and re-enumerates
package windows before reading the playlist. Local probe tests: 46 passed.

That run passed Linux and Windows builds but failed Explorer acceptance. Its
downloaded trace shows primary PID 5860 and clients 768/3040 using the same
socket and lock path. Both clients connected before `listen()` returned, then
exited with code 1 after approximately five seconds without acknowledgement.
The primary constructed the player in 4932 ms, but never logged a receive callback
even during the following six seconds of its event loop. Its own file 01 was the
only playlist row. Cleanup passed. ZIP SHA-256:
`10820e2c18e39bfc9c58c519143a85314c35c19bce34e98bc2e4737d15cce1ad`.

Qt's Windows implementation calls `_q_onNewConnection()` inside `listen()`;
this can emit `newConnection` before the vendored code subscribes to it. Candidate
`a8639e1` subscribes before listening and queues the receiver invocation until
startup wiring is complete. A Windows/Qt6 regression uses a larger actual
named-pipe backlog to exercise acceptance *inside* `listen()`, then connects
the application message receiver after the primary claim, matching main.cpp.
CI must establish success with the fix and missing delivery with the previous
receiver. This candidate is not yet a completed package acceptance.

The instrumented matrix `36422795897` confirms a second defect: all four warm
cases end with two native main windows. The warm process hashes an 8.3 executable
path (`C:/Users/RUNNER~1/...`), whereas Explorer's children hash its long form
(`C:/Users/runneradmin/...`), producing distinct IPC channel/lock identities for
the same executable. Canonicalizing the executable path before hashing addresses
this independently of the listen-time race. Its subprocess regression compares
long/short launch identities and checks that a separate executable copy still
has a distinct identity. The matrix also contains cold missing-frame/timeout
failures; no burst-timing limits have been relaxed.

PR15 player-action tests run separately on `test/windows-trash-player-acceptance`
at `bdc812e`: generated disposable WAV files, real player action and Windows
adapter, ordinary/partial cancellation, duplicate rows, current/next removal,
and a handle-denied recycle followed by declined permanent deletion. The matrix
covers playing/paused/stopped and package skins; results are pending.

Read-only local display discovery found two 2560x1440 monitors, both 96 DPI.
Mixed-DPI and physical hotplug are not represented by this current setup.

## Current merge decision

All five functional/test PRs remain drafts. No functional PR was merged into
integration, and integration was not promoted to master. Original-project PRs
were not changed. Native component success narrows the remaining work but does
not override the combined Explorer failure or the unexecuted acceptance cases.
