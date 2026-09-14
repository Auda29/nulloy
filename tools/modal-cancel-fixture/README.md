# Harmless modal-Cancel fixture

This directory is an isolated vertical slice. It does not start Nulloy, call
player inspection, invoke a product action, touch the registry, trash files,
or delete arbitrary paths.

## Files

- `fixture.py` — real `PySide6==6.8.2` `QMainWindow` and `QAction`. The action
  opens a fixed-nonce `QMessageBox.exec()` with benign `Yes` and `Cancel`
  buttons; Cancel is the only intended outcome. Atomic `state.json` and an
  independent `counters.json` record heartbeat, identity, modal state, and
  exact outcomes. `sentinel.bin` is a benign immutable payload used by the
  controller to detect accidental mutation.
- `worker.py` — Windows-only child. It validates PID, process creation time,
  executable, owned HWND, main title, exact modal title/body, button identities,
  and UIA runtime-ID deduplication. It performs all UIA work in the child. It
  persists a stage immediately before the one allowed `Cancel.invoke()`; it
  never invokes `Yes` and never retries after the action. Read-only observation
  remains the default. `--cancel-once` explicitly opts into the harmless fixture
  only, using the native-observed Qt 6.8.2 `QMessageBox`/`Window` shape and exact
  nonce-derived `QApplication.` automation IDs. Unknown outcomes cannot pass.
- `controller.py` — fixed-path controller. The Windows CLI launches only the
  fixed fixture and this fixed worker through the reviewed existing
  `tools/player-inspection/uia_supervisor.py`; it has no arbitrary worker/script
  option. It pins the live owned process and validates independent counters,
  dialog closure, sentinel SHA-256, worker cleanup, and finite fixture cleanup.
  `run_internal_cancel()` is a Linux-only trusted test seam that causes the
  fixture itself to click its real Qt Cancel button; it is explicitly marked
  non-native and is not UIA acceptance.
- `test_modal_cancel.py` — fixed-path tests using real subprocesses and the
  existing supervisor.

## Pinned environment

Use an isolated Python 3.11 environment with pinned dependencies; no global
install is required:

```text
PySide6==6.8.2
psutil==7.0.0
```

The fixture is not the player environment (the player archive may use another
Qt version). On Linux the tests set `QT_QPA_PLATFORM=offscreen`; this proves
real Qt subprocess/modal behavior only, not Windows UIA behavior.

## Tests

Run only this fixed slice with output outside the repository:

```bash
python -m unittest discover -v -s tools/modal-cancel-fixture -p 'test_*.py'
```

Set `TMPDIR` to an existing external directory with free space if the system
temporary filesystem is full. Do not delete historical evidence to make room.

The test run exercises invalid nonce, invalid lifetime, existing-root guard,
real guarded callback failure, real Qt modal Cancel, independent counters and
sentinel preservation, the real bounded supervisor timeout/reap path, the
worker's no-opt-in block, and the Linux CLI block. Native read-only evidence
from run `34868391499` is replayed as a committed schema fixture. It does not
prove native Invoke; the opt-in branch needs its own reviewed Windows run.

## Windows gate

Run from an isolated disposable Windows runner with a reviewed Python
containing `PySide6==6.8.2`, `psutil==7.0.0`, `pywinauto==0.6.9`, and the
matching COM dependencies:

```powershell
python tools/modal-cancel-fixture/controller.py `
  --evidence-root C:\path\outside\checkout\modal-cancel-fixture
```

A native pass still requires fresh evidence for the modal UIA `ControlType`.
Until `PINNED_MODAL_CONTROL_TYPES` is populated from that evidence, the worker
must remain `BLOCKED`/partial; Linux or an offscreen run must not be upgraded
into native acceptance.

The isolated `modal-fixture-observe.yml` workflow runs the Linux regression
suite first. Pushes and default manual runs only observe. Only a manual
`workflow_dispatch` with Boolean `cancel_once: true` adds `--cancel-once`;
use this only after independent review of the exact source.
It preserves the controller exit code: a BLOCKED/partial result is not painted
green. The Windows evidence upload runs even on failure with seven-day retention;
no player packages are downloaded or uploaded by this workflow. Raw runtime
source hashes, worker diagnostics, state/counters, sentinel checks and cleanup
are retained separately from any future Cancel verdict. Native findings must
be read back and independently assessed before enabling Cancel.
