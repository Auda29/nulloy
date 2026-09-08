# #141 — short-file engine/output-clock characterization

Issue: https://github.com/nulloy/nulloy/issues/141

Read the live thread (including the maintainer's 0.9.7 rework note), fork analysis,
and related PR #263 comments. Number/waveform/short duplicate searches found no
separate fix. The original Windows 10 WAV/MP3 report says the waveform reaches the
end about two seconds before audio. The linked video was not reviewed here.

## What was measured

This independent branch adds only a standalone real-engine harness. It replaces
playbin's output sink with synchronized F32LE appsink instrumentation; production
engine methods, Qt timers and bus processing remain real. Only application
argument initialization is adapted. Fixtures are generated automatically: mono
48 kHz square-wave WAVs lasting 50, 250, 800 and 2,000 ms.

Each test checks every decoded frame arrived, compares emitted engine positions
with monotonic elapsed time since the first clocked PCM buffer, and checks final
EOS did not precede the last buffer's estimated render end. The latter includes
the **last buffer duration**, not merely its callback time (which is its start).
The position skew tolerance is 60 ms; EOS tolerance is 20 ms. For files at least
250 ms long, progress beyond halfway is required. A 50 ms file can finish before
the initial 100 ms status timer; intermediate visible animation is not claimed.

```sh
cmake -S tests/upstream/141 -B /tmp/nulloy-141 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/nulloy-141 -j1
ctest --test-dir /tmp/nulloy-141 --no-tests=error --output-on-failure --timeout 180
```

## Results / limits

Linux Qt 6.8.2, GStreamer 1.26.2, GCC 14.2, tests serialized under the shared lock:

- Baseline **6 QtTest passes**. Exact PCM sample counts 2,400 / 12,000 / 38,400 /
  96,000. Maximum position/output-clock skew approximately 43.10 / 0.15 / 21.88 /
  0.20 ms, respectively. This did not reproduce a two-second engine lead.
- Deliberately advancing emitted position by 250 ms failed the 800 ms row:
  measured skew **250.136 ms**, beyond the 60 ms tolerance. This sensitivity check
  is not evidence of an existing application bug.
- Mutation reverted; final CTest **1/1 passed in 3.38 s**, engine diff empty.
- Shared logs: `evidence/audio/141-baseline.txt`, `141-sabotage.txt`, `141-green.txt`.

This characterizes the **engine signal supplied to the waveform**, not the actual
painted widget, display latency, audio driver/DAC latency or audible output. WAV
only; no MP3, real Windows/macOS device, Qt 5 execution or original-video replay.
No amplitude claim from frame counting; #238 separately measures PCM amplitudes.
No production fix or issue closure claimed. Actual UI/sink-clock/DAC correlation
on the reported platform remains necessary; parent independent review and package
compatibility checks remain pending. No top-level build restriction was weakened.
