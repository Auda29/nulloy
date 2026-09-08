# #261 — rapid playback-operation stress characterization

Issue: https://github.com/nulloy/nulloy/issues/261

Read the live issue (no comments), fork issue analysis and all comments on related
PR #263. The report concerns rapid selection/seeking on a MacBook Pro M3, Tahoe
26.2, and links a Drive recording. The recording itself was not reviewed here.
Number/seek/crash PR searches found PR #263, already ported in this fork at
`33388d1`, and no additional relevant fix. That port removes a streaming-thread /
GUI blocking-lock inversion; this test is not a reproduction of the original Mac
crash and does not justify closing #261.

## Executable scope

The standalone harness compiles the **real engine**, not a playback mock. It uses
its existing `_TESTS_` clock-synchronized fakesink, with a handoff callback counting
nonempty decoded output buffers. Test-only private access attaches that observer;
only `NCore::cArgs` is adapted. Generated 48 kHz mono WAV files are 2 and 3 seconds.

Each of 100 iterations selects alternating files, waits for actual position
progress, seeks to 98%, allows the real status timer / about-to-finish callback to
race, seeks back to 15%, pauses and resumes. Every fifth iteration also stops.
Each iteration must resume decoded output without an engine error. The successor
cache is populated through the production `nextMediaRespond` API on stream starts.
After stress, successors are disconnected and a fresh file must reach final EOS,
emit more output, retain its identity and report Stopped. CTest's external timeout
bounds a deadlock that would also block the Qt event loop.

```sh
cmake -S tests/upstream/261 -B /tmp/nulloy-261 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/nulloy-261 -j1
ctest --test-dir /tmp/nulloy-261 --no-tests=error --output-on-failure --timeout 180
```

## Evidence

Linux x86-64, Qt 6.8.2, GStreamer 1.26.2, GCC 14.2:

- Unmodified baseline: 3 QtTest passes. 100 iterations, **699 nonempty output
  buffers**, **109 stream starts**, 20,845 ms stress plus final recovery playback.
- Deliberate sensitivity mutation made `play()` request PAUSED instead of PLAYING;
  the test failed its position-progress condition, rather than accepting a live
  event loop with stalled audio. This is not a reproduction of a Mac deadlock.
- Mutation restored, engine diff empty. Final CTest repeated three times:
  **23.01 / 22.98 / 23.00 s**, all passing, each executing 100 iterations.
- Early compilation failed because shared `/tmp` filled, then a compiler was
  killed under memory pressure. The parent subsequently identified a 2 GiB / 1 CPU
  cgroup and introduced a global build lock. Build and all final runs succeeded
  under that lock; temporary compiler files were redirected to disk-backed storage.

Shared evidence: `evidence/audio/261-baseline.txt`, `261-sabotage.txt`,
`261-green.txt`. No production change; this branch is independent of #238/#240.

## Limits

This test asserts engine progress, output-buffer delivery and recovery, **not
signal amplitude or audible continuity** (see the separate #238 appsink harness).
It does not drive a playlist widget, waveform worker, file additions, skin, native
macOS audio sink, actual hardware or the reporter's exact files. No thread/heap
sanitizer or overnight endurance run. Qt 5 CMake selection is available but not
executed here. Mac crash logs, sample/spindump during a hang and the linked
recording still need comparison with this fork. Parent independent review and
Windows package compatibility remain pending. No source fix was invented from
passing characterization, and no UI/Windows build restriction was changed.
