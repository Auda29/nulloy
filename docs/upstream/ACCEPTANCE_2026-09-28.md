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
Run `36424862530` established delivery with the fix and zero delivered messages
with the previous receiver. Its overall result was still red because the identity
regression was skipped on the checkout volume. Candidate `a8639e1` also passed
one real Explorer run (`36423121033`), but this was not full package acceptance.

The instrumented matrix `36422795897` confirms a second defect: all four warm
cases end with two native main windows. The warm process hashes an 8.3 executable
path (`C:/Users/RUNNER~1/...`), whereas Explorer's children hash its long form
(`C:/Users/runneradmin/...`), producing distinct IPC channel/lock identities for
the same executable. `QFileInfo::canonicalFilePath()` alone did **not** expand 8.3
names: `36425677590` reproduced the unequal identities with that first candidate.
Candidate `6f245e0` additionally calls `GetLongPathNameW`. Run `36426203490` passed
all ten Qt6 startup results without skips; both the lost-listen-notification and
8.3-identity cases fail against the original receiver. Its subprocess regression compares
long/short launch identities and checks that a separate executable copy still
has a distinct identity. The matrix also contains cold missing-frame/timeout
failures; no burst-timing limits have been relaxed.

The next packaged run `36423455014` passed Linux/Qt5/Qt6 builds but still failed
Explorer. The primary took **6524 ms** to construct its player. Both clients
exited after their 5000 ms send budget; the now-connected receiver subsequently
observed empty disconnected sockets. This is a separate GUI-blocked-reception
failure, not evidence that the listen-notification fix regressed.

Candidate `fd7e416` moves only the primary socket receiver to a dedicated thread,
retaining the election mutex on its acquiring thread. Complete frames are
acknowledged independently of GUI initialization, then delivered on the GUI
thread. Main buffers startup notifications until its own initial arguments have
been applied. The client deadline and file-open-burst limits are unchanged.
Tests compare clients with/without background reception while the GUI is blocked,
and check that GUI message dispatch occurs on the original thread. Frames remain
in memory, so this does not promise delivery across a primary-process crash.
Regression `36426673584` passed all 12 results (no skips), including both
blocked-GUI reception cases; the old-code identity/listen regressions failed as
expected. Package run `36426674095` passed Linux, Windows Qt5/Qt6 and real Explorer
acceptance. The primary took 5671ms to construct the player while both clients
received acknowledgements immediately and exited with code 0. All three files
arrived exactly once, one settled player remained, and cleanup passed.
ZIP SHA-256: `e668066d1e82fc72dc4edef67270323a0d09b3194541da48e7b277349fd61c2a`;
EXE SHA-256: `ce6d54bed8dddf773cd0cca9714f1737668fd5c0a16910c1bace485e5d37f08b`.
Probe `51326ac` also correlates
client success/acknowledgements, received frames, player-message exact-once
delivery and actual UI row order; 47 local probe tests passed. Matrix `36429597491`
used this stronger probe against the same `fd7e416` package, exposing a probe-only
short/long fixture-path mismatch. `afd5676` resolves actual file paths before
comparing them. The next run `36430105997` exposed another probe defect: its
playlist reader returned expected fixture order rather than the observed UI order.
All nine saved raw UI orders matched player delivery. `e7c86b7` returns actual
observations and requires two consecutive snapshots with the same order; 49
local contracts passed.

Final run **`36430784792`: 9/9 PASS**, all nine cleanup checks passed. It verifies
all four enqueue/play-enqueued combinations for cold and warm-empty launches,
plus a cold 12-file selection, using the unchanged `fd7e416` package. Every
scenario passed acknowledgement/received-frame correlation, exact-once player
delivery, UI row order and the settled single-window invariant. This establishes
the startup/IPC acceptance slice, not the remaining #24 nonempty playback-state,
position and independent-rapid-open semantics.

The verified startup implementation and regression files were transplanted
byte-for-byte to PR29 head `6170dbe`. Windows Qt5/Qt6 `36431623652` passed.
Linux `36431623867` failed the #146 metadata harness: the final fixture already
had duration 30 instead of the assumed unread value -1. That harness does not
link the changed IPC/startup sources. Its setup populated the playlist before
showing/sizing the layout, although `setFiles()` immediately preloads visible
and prefetched rows. PR29 follow-up `9d8b352` moves population after the bounded
viewport is established, retaining the offscreen-row/unread-metadata assertions.
Head `9d8b352` passed Windows `36433117685` but Linux `36433117692` still failed
all four unread-final-row assumptions. Moving population after layout alone did
not solve that assumption: `processVisibleItems()` can prefetch the full list.

Follow-up on 1 October 2026, head `be7a766`, explicitly marks the target metadata
unread immediately before each activation, without an intervening event-loop
wait, and retains the real-file metadata checks inside the activation signal.
Reverse traversal still seeds a stale cached title. This tests refresh rather
than assuming which rows startup painting did/did not cache. New full-head
checks `36839437749` (Linux) and `36839437766` (Windows) are pending. A separate
pinned-head workflow repeats the metadata test three times offscreen and once
under XCB, then requires the stale-title check to fail with forced refresh
disabled. Initial setup run `36839704026` stopped at Git's container ownership
check before compilation; the provenance command now scopes `safe.directory`
to the checkout path for that invocation only. No desktop-probe workflow or
#24 playlist policy was transplanted into PR29.

Pinned-head fixture verification `36839972967` passed: three offscreen runs and
one XCB/Xvfb run each report **7 passed / 0 failed / 0 skipped**. Disabling
forced metadata refresh then fails on the seeded stale cached title, as required
by the sensitivity check. The corrected fixture therefore retains its ability
to detect broken activation-time refresh. Full-head CI remains the merge gate.

PR15 player-action tests run separately on `test/windows-trash-player-acceptance`
at `bdc812e`: generated disposable WAV files, real player action and Windows
adapter, ordinary/partial cancellation, duplicate rows, current/next removal,
and a handle-denied recycle followed by declined permanent deletion. The matrix
covers playing/paused/stopped and package skins. Run `36421958897` passed the
15 non-current-track cases on Qt5/Qt6 Slim, but all three current-track cases
reached the explicit permanent-delete fallback, which the harness cancelled.
Releasing the cached metadata handle did not resolve this (`36423610588`) and
that speculative product change was reverted at `0eea361`.

Handle diagnosis `36425057304` checks Windows DELETE access without deleting:
before loading it succeeds; during playback it fails with ERROR_SHARING_VIOLATION
(32). Releasing tags and stopping waveform generation still leaves it blocked;
stopping playback afterwards releases it. All four package skins on both Qt
versions continue to fail the successful-current-track-recycling expectation.
This establishes an open-handle obstacle; it does not yet establish safe state/
position restoration after cancellation or successful current-track deletion.

Follow-up `36427409143` at `fad2702` verifies retained file bytes, current media,
playback state and paused/stopped position *before* reporting the current-track
recycling failure, and adds ordinary-prompt cancellation for the current track.
Qt6 Slim: 21 passed / 3 failed / no skips (includes init/cleanup/handle diagnosis).
The three failures remain the expected-success current-track recycle cases;
their fallback cancellation passes the byte/state checks. No successful
current-track recycling acceptance is claimed.

Read-only local display discovery found two 2560x1440 monitors, both 96 DPI.
Mixed-DPI and physical hotplug are not represented by this current setup.
PR16 package `2fd31b9` from `36426857899` combines current integration with the
PR16 head. Locally verified all 497 manifest hashes. ZIP SHA-256:
`61626accfe31831a1f927ddba8adefc64fe823216738fa90a45150b6df33a175`;
EXE SHA-256: `26a55aece2c1ea3ea84d8597bc1178107a27f94ff1bfac2b137a4f60307eb03a`.

The local native monitor probe (`tools/desktop-probe/monitor_probe.py`, `bee0ca5`)
checks only its own disposable portable processes. Slim, Metro and Silver pass
offscreen/oversized startup recovery, moving to each real monitor, minimizing/
restoring on both, and a persisted restart: six case phases passed. The Native
skin **fails** oversized startup: its outer rectangle `[-8, 0, 2568, 1431]`
extends below primary work area `[0, 0, 2560, 1392]`. All seven started processes
were cleaned up. The probe allows only a 16px invisible resize-border margin,
not a titlebar-height overflow. Evidence is retained locally under
`nulloy-acceptance-20260928/geometry-local`.

Candidate `5f82eee` on the geometry test branch includes native frame dimensions
in fallback fitting, retaining normal-state frame dimensions during minimized/
maximized transitions. A new actual native-window regression checks complete
frame containment. Run `36428998249` passed **46 native results each on Qt5 and
Qt6**; both old-code comparisons failed the new frame-containment case. Its Qt5
package build also passed. The Qt6 package job failed during MSYS installation
with HTTP 500 and has been rerun; no source/test failure was reported in that job.
The failed-job rerun passed. The resulting Qt6 package passed **all eight local
skin/phase checks**, including Native, on the two physical 96-DPI monitors. All
eight owned processes were cleaned up; all 497 package hashes were verified.
ZIP SHA-256: `2b1629f35d4230c37531990fc241b22f7868758c6a904b5a2dabcbd143213f47`;
EXE SHA-256: `d1d5bc9dc69a8c41f5495c400e7f556bfaaa320d3267c9ee3f90523fa8895ab2`.
Local evidence: `nulloy-acceptance-20260928/geometry-frame-local`.

The verified geometry source/regression files were transplanted byte-for-byte to
PR16 head `c7ce989`, with acceptance references in `docs/upstream/236.md`.
PR-head checks passed: Linux `36431008436` and Windows Qt5/Qt6 `36431008472`.
Mixed-DPI and physical hotplug remain outstanding.

## Current merge decision

All five functional/test PRs remain drafts. No functional PR was merged into
integration, and integration was not promoted to master. Original-project PRs
were not changed. Native component success narrows the remaining work but does
not override the unexecuted acceptance cases or the player-trash recycling gap.
