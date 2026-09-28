# Single-instance startup regression test

This is a small component-level regression test for the production startup
role decision. It compiles the vendored `QtSingleApplication` and
`QtLocalPeer` sources, then launches the test executable as real primary and
secondary subprocesses.

It covers:

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
Only the separate successful delayed case asserts an exact-once delivery
contract. The test does not identify the Windows cause of the original startup
symptom, does not exercise native application wiring, and is not an Explorer
or Windows acceptance harness; those remain open.

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
