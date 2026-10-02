# #238 — decoded gain characterization (not a claimed fix)

Issue: https://github.com/nulloy/nulloy/issues/238

Read the full live thread, linked #228 and PR #263 (including its comments),
plus this fork's `docs/UPSTREAM_ISSUES_ANALYSIS.md`. The report is intermittent
100% audio with a 20% slider, including Windows 11 reopen/repeat; #228's earlier
closure is not proof that #238 is resolved. Number, volume and gain PR searches
found no separate implementation. PR #263 is already ported at `33388d1`.

## Executable evidence

The standalone harness compiles the **real** playback engine and its Qt metaobject.
The only application adapter supplies `NCore::cArgs`; test-only private access
replaces playbin's sink with a clock-synchronized appsink. It does not replace
volume, reset, bus handling or transition code. Production files are unchanged.
No top-level Windows build restriction is relaxed.

A generated 48 kHz mono S16 square-wave WAV has exactly 96,000 frames and peak/RMS
0.25. The sink negotiates F32LE. Every delivered sample contributes to RMS and peak;
full sample counts must match, so a startup or transition gain spike is not hidden
by averaging or a muted test. Rows request 0, 0.2 and 1 gain, each through three
open/play/EOS resets, stop/play of the retained file and three gapless repeats.
The latter asserts three real stream starts and one final EOS, not an EOS-loop stub.

Run from the repository root:

```sh
cmake -S tests/upstream/238 -B /tmp/nulloy-238 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/nulloy-238 -j1
ctest --test-dir /tmp/nulloy-238 --no-tests=error --output-on-failure --timeout 180
```

On Linux x86-64, Qt 6.8.2, GStreamer 1.26.2, GCC 14.2:

- Unmodified baseline: 5 QtTest passes (3 data rows plus setup/cleanup).
  Gain 0.2 produced RMS **0.05**, peak **0.05** on all paths; mute and unity
  produced 0 and 0.25 respectively. Singles had 96,000 samples, repeats 288,000.
- Sensitivity check: temporarily forcing production `setVolume` to send 1.0 made
  the 0.2 row fail its actual PCM RMS assertion, reporting **0.25**, not 0.05.
  This deliberate mutation is **not** a reproduction of the original bug.
- Mutation reverted; CTest passed in 43.40 s. `git diff` confirms no engine change.
- One intervening rerun hit the 90 s test timeout during concurrent compilation
  load after two rows passed; retained as evidence, not silently discarded.
  The subsequent rerun passed without code changes. Its cause was not established.

Logs are in the shared agent evidence directory `evidence/audio/`:
`238-baseline.txt`, `238-sabotage.txt`, `238-green.txt` (timeout), and
`238-green-rerun.txt`. Initial harness adjustments (float tolerance and using a
2 s track that permits a queued successor) were test setup corrections, not reds
proving an application defect.

## Limits / next checks

This is characterization and a regression guard, **not a fix or closure of #238**.
It measures decoded software output, not DAC, Windows system mixer, hardware,
Bluetooth, or an audible listening test. Actual Windows 11 skins, persisted UI
slider feedback, opening a file in an already-running app, active-track manual
replacement, rapid volume changes, pause/resume, codecs other than WAV and macOS
remain unverified. Qt 5 is selectable by CMake but was not run here. The repository's
Windows package suite and independent parent review remain required before release.
