# Single-instance startup regression test

This is a small component-level regression test for the production startup
role decision. It compiles the vendored `QtSingleApplication` and
`QtLocalPeer` sources, then launches the test executable as real primary and
secondary subprocesses.

It covers:

- a fast primary that acknowledges one forwarded message;
- a primary that starts processing late, making the secondary's bounded
  acknowledgement wait ambiguous: the secondary exits nonzero, does not start
a player, and the primary receives the message exactly once;
- first launch becoming primary; and
- `SingleInstance` disabled, where a second process still starts.

The test proves the startup policy and QtLocalPeer interaction only. It does
not identify the Windows cause of the original startup symptom and is not an
Explorer or Windows acceptance harness.

## Run

```sh
flock /home/hermes/workspace/nulloy-swarm/build.lock \
  cmake -S tests/single-instance-startup \
  -B tests/single-instance-startup/build -DCMAKE_BUILD_TYPE=RelWithDebInfo
flock /home/hermes/workspace/nulloy-swarm/build.lock \
  cmake --build tests/single-instance-startup/build -j1
QT_QPA_PLATFORM=offscreen \
  tests/single-instance-startup/build/testSingleInstanceStartup
```
