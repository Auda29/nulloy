# #240 — clocked repeat/end-marker characterization

Issue: https://github.com/nulloy/nulloy/issues/240

The complete live thread clarifies that **the end is cut off**, not merely the
known startup speed-adjustment delay. Read the fork analysis and PR #263 with its
full comment thread; number/speed/repeat searches found no other implementation.
PR #263's transition port is already present in the starting commit `027d81a`.

## Scope and test

This branch is independent of #238 (same integration base). It contains no engine
change and does **not** claim to fix or close the original report, which was not
reproduced in the tested configuration.

The standalone CMake project compiles the real engine with Qt 5/6-selectable
metaobjects and GStreamer. Test-only private access attaches a synchronized
appsink, without replacing playback, seeking, timers, bus processing or handoffs.
The application argument adapter is the only stub. No Windows target restriction
or top-level build file changes.

A generated two-second, 48 kHz mono WAV has a uniquely higher-amplitude final
250 ms (12,000 frames). Real `about-to-finish` callbacks prepare three repeats;
one final EOS and three stream starts are required, without a fake EOS controller.
F32LE output is inspected for sample counts, the entire tail marker, per-buffer
GStreamer segment rate and elapsed clocked playback time at **0.5x, 1x and 2x**.

The test allows up to 125 ms of aggregate media loss/duplication and 250 ms of
render-duration error per cycle because the current engine applies rate changes
with a deferred flushing seek. This is not a sample-perfect/gapless-start claim.
Every one of the 12,000 end-marker samples must nevertheless arrive on every loop.
The wall-time tolerance is one second over three loops; run on an adequately
provisioned host rather than alongside memory-saturating compilers.

```sh
cmake -S tests/upstream/240 -B /tmp/nulloy-240 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/nulloy-240 -j1
ctest --test-dir /tmp/nulloy-240 --no-tests=error --output-on-failure --timeout 180
```

## Runtime evidence

Linux x86-64, Qt 6.8.2, GStreamer 1.26.2, GCC 14.2:

- Baseline: 5 QtTest passes. All three rates delivered all 12,000 tail frames on
  each loop. Total elapsed playback was 11,905 / 6,050 / 3,151 ms respectively.
- Sensitivity mutation 1: forcing seek rate 1.0 made the half-speed row fail its
  decoded-segment duration assertion (about 2 s per loop instead of 4 s).
- Sensitivity mutation 2: setting seek stop 250 ms before duration made the
  half-speed row fail its delivered-frame assertion, with **zero tail frames**.
- Both mutations reverted; final CTest **1/1 passed in 21.38 s**, no engine diff.
- An intervening run failed wall-time tolerance under concurrent compiler load:
  its 1x output segments still totaled approximately 6 s but wall time was
  22,496 ms. An unchanged rerun passed, as did the final run. The failing evidence
  is retained; no production fix or weakened assertion was used to hide it.

Shared evidence: `evidence/audio/240-baseline.txt`, `240-sabotage.txt`,
`240-sabotage-tail.txt`, `240-green.txt` (wall-time failure),
`240-green-rerun.txt`, `240-final-green.txt`.

## Limits / follow-up

These are intentionally characterized current behaviors with mutation-sensitive
checks, not TDD reds reproducing an existing defect. WAV only, software sink only;
no hardware/DAC, system mixer, audible continuity, native skins, macOS or Windows
validation. Qt 5 CMake compatibility is offered but was not executed. Extremely
short files, rate changes during an in-flight handoff, compressed codecs, UI
repeat wiring and displayed position/time synchronization are not covered. In
particular `tick` scales a queried media position by speed; that separate display
concern is not fixed or equated with the reported audio endpoint defect here.
Parent independent review, Windows package tests and actual-device checks remain.
