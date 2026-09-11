# Read-only UIA timeout supervisor spike

This is a disposable, standalone feasibility spike for bounding a Windows UIA
read-only query. It is **not** production Nulloy code and it does not perform
player acceptance.

## Scope and safety boundary

- `supervisor.py` starts the exact owned `worker.py` with the current
  `sys.executable`, `shell=False`, `stdin=DEVNULL`, and no inherited output
  pipes. It records stdout and stderr in `stdout.txt` and `stderr.txt`.
  `run_supervised(worker_script=...)` remains a trusted test-only API seam for
  real child-process fixtures; it is not a security sandbox. The operational
  CLI has no worker replacement option and always launches the owned helper.
- Readiness, execution, terminate, and kill/wait stages all have finite,
  independently validated deadlines. `TIMEOUT` and `FAIL` remain distinct;
  success is impossible when cleanup cannot be verified. Post-spawn diagnostic,
  wait, final-capture, and result-write failures are serialized as structured
  failures when possible; the primary error is retained separately from
  secondary cleanup/evidence errors.
- Both stdout and stderr are polled while the child is live. Crossing
  `output_cap` fails promptly and retained diagnostics are capped. This is a
  polling containment limit, not a hard disk quota: a child can overshoot
  between polls, and it does not bound a synchronous UIA/COM call.
- The worker accepts one positive exact `HWND`, `PID`, process `create_time`,
  and executable path. It validates the native HWND owner PID using typed,
  pointer-sized Win64 API declarations both before and after the UIA
  traversal, then validates the exact psutil identity before and after the
  UIA query. The post-query HWND check is a race detector, not atomic HWND
  ownership proof.
- The worker sets `sys.coinit_flags = 0` before importing pywinauto/comtypes,
  as recommended for a windowless MTA UIA client. COM wrappers never leave the
  worker; the result is JSON primitives only.
- The worker performs only an exact-handle, own-PID UIA snapshot. It has no
  application-level child-process spawning and exposes no input, invoke,
  selection, menu, deletion, or other UI action. This does not claim that
  Windows UIAutomationCore cannot create a system helper process.
- UIA traversal is intentionally unbounded inside the worker: that is the
  operation the parent must contain. The 64-record snapshot limit is an
  output/diagnostic cap and is not a call timeout.
- The parent timeout begins after `Popen` returns. Python subprocess timeout
  arguments do not bound OS process creation; `spawn_elapsed_s` is recorded
  explicitly instead of claiming an absolute wall-clock bound.

## Linux test result (partial by design)

Run from this directory:

```text
python -m unittest -v test_spike.py
```

Observed on the Linux development environment:

```text
Ran 12 tests in 1.2s
OK
```

These are real subprocess tests covering a successful worker protocol, missing
child result, child exception/nonzero exit, stall before readiness, stall after
readiness and finite cleanup, live stdout/stderr output-cap failure distinct
from timeout, timeout-primary preservation, diagnostic/wait/result-write
failure containment, deadline validation, owned-worker CLI JSON serialization,
and rejection of script replacement. The worker identity regression uses a
synthetic native-PID change around a fake traversal: it validates the race
detector, not Windows ABI or native HWND behavior.

For the later disposable Windows experiment, install the pinned compatible
runtime (`pywinauto==0.6.9` and `psutil`), start a harmless owned Qt fixture,
obtain its exact HWND/PID/create-time/exe identity, and run for example:

```text
python supervisor.py --output-dir run \
  --hwnd 0x123456 --pid 1234 \
  --create-time 1700000000.0 --exe 'C:\\path\\fixture.exe'
```

That native run must remain read-only and independently verify process cleanup;
this spike intentionally does not perform it.
