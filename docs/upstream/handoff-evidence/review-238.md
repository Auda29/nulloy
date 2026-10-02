# PR8 independent review — gain characterization

**Reviewed immutable SHA:** `7aa429c5c09d34f7b6c22a8f9f5887c3e6337847`  
**Source:** `/home/hermes/workspace/nulloy-swarm/issue-238`  
**Verdict:** No confirmed blocking correctness finding in this limited characterization PR. The prior intermittent timeout remains unresolved; these passes are not evidence that the harness is flake-free, nor that issue #238 is fixed.

## Findings / qualifications

- **Medium, unresolved reliability observation, not a proven code defect:** `tests/upstream/238/CMakeLists.txt:19` sets a hard 90-second CTest timeout. The README/runner's `--timeout 180` does not override that per-test property. `tests/upstream/238/testGain.cpp:134,143,157` also depend on Qt event-loop progress and 3/9-second polling deadlines. The real-clock fixture and successor publication from the GUI-thread `mediaChanged` callback (`149–153`) require scheduling headroom. The historical `evidence/audio/238-green.txt:24–27` reaches all four unity single-play captures and then times out before its gapless result. No stack trace identifies whether it stalled inside GStreamer/teardown or suffered scheduler starvation. Do not attribute that historical failure conclusively to load, and do not silently discard it. If it recurs under serialized resource-aware execution, capture thread stacks before termination and investigate before treating it as a dependable required CI gate.
- **Low, coverage wording:** The retained-file path at `testGain.cpp:140–144` calls `play()` after EOS; it does not explicitly invoke a mid-track user `stop()`. This does exercise real `stop()` because production EOS calls it (`playbackEngineGstreamer.cpp:432–435`), but it should be understood as EOS-stop/replay, not active user-stop/replay. This does not undermine the measured reset coverage.

## Correctness inspection

- CMake compiles the actual engine, header/metaobject and Qt/GStreamer dependencies. `_TESTS_` changes sinks, not volume or lifecycle logic. No production file changed in the reviewed commit.
- The generated S16 mono square wave has 96,000 frames, fixed magnitude 0.25, and a 48 kHz sample rate. F32LE output RMS and absolute peak are compared independently against requested gain at `testGain.cpp:75–87`. Unity provides a non-muted reference. Exact counts are checked before RMS division, avoiding a silent empty-capture pass. A loud isolated sample cannot be averaged away by the peak assertion. Counts are aggregate completeness checks, not sample-identity/ordering checks, and tiny deviations below the stated tolerance are intentionally permitted.
- Every delivered buffer is examined, without a startup discard window. Preroll is not separately counted; normal appsink sample delivery supplies it on playback. Actual runs returned exactly 96,000 samples per single and 288,000 per repeat sequence.
- Capture state is mutex-protected in callback, reset and assertions (`testGain.cpp:22–62,77`). Capture is declared before the engine (`118–119`) and therefore outlives engine shutdown. Assertions acquire the capture lock after EOS has synchronously stopped the pipeline, not while initiating a state change. I found no introduced capture-data race or capture/engine lock inversion. The repeat counter is touched through the engine's main-thread bus processing, not directly by its streaming callback.
- Three `mediaChanged` notifications plus exactly one additional final `mediaFinished` are asserted for gapless playback. The lambda publishes successors through the real production API; it does not fake EOS/restart. This covers three total plays, not three additional repeats.
- `#define private public` (`testGain.cpp:7–10`) is test-local and dependencies are pre-included. Only the sink is accessed through it. It remains brittle against header changes and formally changes the class definition between translation units, but no layout-sensitive behavior or production access-control change is introduced here. This is a bounded instrumentation tradeoff, not evidence of a runtime failure.
- Qt helper assertions return from `checkCapture`, not its caller, but QtTest still records the failure; they cannot turn a bad PCM result into a pass.

## Independent real execution

Native build used GCC 14.2, Qt 6.8.2, GStreamer 1.26.2, Linux x86-64, Release, Ninja, build parallelism 1.

1. Ran:
   ```sh
   python3 /home/hermes/workspace/nulloy-swarm/ci/tools/upstream/run-native.py \
     --source /home/hermes/workspace/nulloy-swarm/issue-238 --issue 238 \
     --output /home/hermes/workspace/nulloy-swarm/evidence/reviewer-238
   ```
   Configure/build/test exited 0. CTest passed in **43.88 s**; QtTest reported **5 passed, 0 failed**. Captures were gain 0: RMS/peak 0; gain 0.2: 0.05; gain 1: 0.25, with the exact sample counts above.
2. Repeated the unchanged native CTest with `--repeat until-fail:3 --timeout 180`: **three passes**, **44.08 s, 43.20 s, 44.15 s** (131.44 s total). Thus this reviewer observed four complete baseline passes, not just a successful configure/build.
3. Archived the exact commit into `evidence/reviewer-238/sensitivity-source`, changed only that throwaway copy's production `setVolume` to send unity, and ran the twenty-percent row with a 45-second process bound. After the resource incident below, the final build/run was serialized using `flock /home/hermes/workspace/nulloy-swarm/build.lock`. Native test exited **1**, reporting actual PCM **RMS 0.25 / peak 0.25** and failing the PCM assertion at line 83 (and later the volume getter assertion). QtTest: **2 passed, 1 failed**, 2.091 s. This independently verifies sensitivity to wrong decoded gain; it is not a reproduction of #238.

Primary evidence: `evidence/reviewer-238/results.json`, `238/step-0.log`, `238/step-1.log`, `238/step-2.log`, `238/Testing/Temporary/LastTest.log`, and `forced-unity.txt`. Repetition timings above are also retained here from tool execution output.

## Resource incident and timeout interpretation

The initial sensitivity build exceeded this reviewer's 140-second tool bound. Retrying before establishing that descendant compilers were gone caused overlapping builds in the same throwaway build directory. Parent identified and terminated those trees. One compile reported `Killed signal terminated program cc1plus`; its retry returned 143. This was a review execution error, not a source test failure. The final lock-serialized build and mutation test completed.

Live cgroup reads show `memory.max=2147483648`, `cpu.max=100000 100000`, and cumulative `memory.events` values `oom=186`, `oom_kill=20`. Host `free` output (~3.7 GiB) is not the effective container limit. These establish real resource pressure during this review, but cumulative counters do not date or explain the earlier documented 90-second test timeout. Four baseline successes, including during observed concurrent compilation, do not rule out scheduling sensitivity or an intermittent engine/GStreamer wait. No deliberate additional load was imposed and no scheduler-delay mutation was run.

## Scope / integrity

Initial and final `git status --short --untracked-files=all` were empty; final HEAD remained the exact SHA above. `git diff --check HEAD^ HEAD` passed. No immutable-source edits or GitHub writes were made. Created this report and reviewer evidence/build/throwaway source files only; the deliberate gain mutation remains confined to the clearly named sensitivity-source directory.

Accept only as Linux decoded software-output characterization. No Windows mixer/DAC, persisted UI, active-track replacement, rapid volume changes, active user-stop, pause/resume, other codecs or Qt 5 validation is claimed. The README correctly leaves the original issue open and unproven.
