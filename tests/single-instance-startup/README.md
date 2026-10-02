# Single-instance startup regression test

This is a small component-level regression test for the production startup
role decision. It compiles the vendored `QtSingleApplication` and
`QtLocalPeer` sources, then launches the test executable as real primary and
secondary subprocesses.

It covers:

- background reception while the GUI thread is blocked: secondary processes
  finish successfully before GUI event processing, and notifications are later
  dispatched exactly once on the GUI thread; disabling the background receiver
  in the same test demonstrates the original timeout;
- Windows 8.3/long executable aliases sharing an IPC identity, while a separate
  executable copy retains a different identity;
- a real Windows connection accepted inside `QLocalServer::listen()`: the
  receiver must subscribe before listening and defer application dispatch;
- a client that disconnects without sending a frame header: the primary must return to its event loop and exit normally without emitting a message;
- a fast primary that acknowledges one forwarded message;
- a deterministic delayed-acknowledgement failure: a primary is held outside
  its event loop behind a unique `QTemporaryDir` release file until the
  secondary has exited, so the secondary must report `IPC_FAILED` and must not
  start a player; after release, the primary must exit normally and may have
  received zero or one copy of the message;
- a separate delayed-but-within-budget forward: a test-only `newConnection`
  observer is registered before the production receiver. It peeks at the full
  expected frame without consuming it, then holds the production receiver until
  the parent releases a unique file barrier. The parent checks that the sender
  stays running for at least 150 ms after the frame is observed; the receiver
  also reports the measured hold. Only then may the unchanged receiver consume
  the frame and acknowledge it. Exactly one message, successful forwarding and
  no second player are required. This observes a queued frame, not merely the
  earlier `SENDING` log marker;
- first launch becoming primary; and
- `SingleInstance` disabled, where a second process still starts.

The zero-or-one assertion in the failure case is intentional. A secondary
that timed out waiting for an acknowledgement cannot establish lossless file
open delivery, even if the primary later receives the already-written frame.
Successful cases assert exact-once delivery. The component suite does not itself
exercise Explorer or the complete player; see the separate package evidence below.

## Windows package evidence, 28 September 2026

Traces reproduced three distinct causes: notification emitted before receiver
registration, unequal identities for short/long executable paths, and player
construction taking longer than the existing client timeout. Production now
receives complete frames on a dedicated socket thread while retaining the
native election mutex on its acquiring thread. Startup messages are buffered
until initial player arguments are applied. GUI delivery stays on the GUI thread.
Acknowledgement is in-memory acceptance, not crash-persistent storage.

Opt-in `NULLOY_STARTUP_TRACE_DIR` writes per-PID JSONL into a pre-existing
directory. With it unset, no diagnostic files are created.

- `36426673584`: all 12 Qt6 startup results passed; the listen/identity
  regressions failed against the old implementation.
- `36426674095`: Linux and Windows Qt5/Qt6 builds and real Explorer acceptance
  passed. Player construction took 5671ms; both clients were acknowledged before
  construction completed, and all three files reached one player.
- `36430784792`: **9/9 real Explorer scenarios passed**, covering cold/warm-empty
  starts, all enqueue/play-enqueued combinations and a 12-file selection. Checks
  correlate successful client acknowledgements, complete received frames,
  exact-once player delivery, actual playlist order and one settled main window.
  All nine cleanup checks passed. Probe-only path/order defects from preceding
  runs were corrected with regressions before this final run.

These package runs use combined source `fd7e416` (including the separate #24
playlist-burst candidate); the startup source and regression files transplanted
here are byte-identical to that candidate. ZIP SHA-256:
`e668066d1e82fc72dc4edef67270323a0d09b3194541da48e7b277349fd61c2a`.
This does not certify #24 playback-position/nonempty-state or independent-rapid-
open semantics. PR-head CI must also pass before merging the startup changes.

The subprocesses use RAII cleanup and bounded waits so a failed assertion does
not leave a running `QProcess` behind. The release files are unique per test,
are passed as arguments, and are removed by `QTemporaryDir` cleanup; no global
environment or shared control state is used.

## Run

```sh
flock /home/hermes/workspace/nulloy-swarm/build.lock \
  cmake -S tests/single-instance-startup \
  -B tests/single-instance-startup/build -DCMAKE_BUILD_TYPE=RelWithDebInfo
flock /home/hermes/workspace/nulloy-swarm/build.lock \
  cmake --build tests/single-instance-startup/build -j1
QT_QPA_PLATFORM=offscreen \
  tests/single-instance-startup/build/testSingleInstanceStartup \
  -o tests/single-instance-startup/build/testSingleInstanceStartup-results.txt,txt
```

CTest uses the same `-o` report path and the test target retains the Windows
`UNICODE`/`_UNICODE` definitions used by the production build.
