# Native UIA timeout controller

`run_probe.py` is a narrowly scoped Windows controller for the reviewed,
harmless Qt fixture. It launches only the fixed fixture with
`sys.executable`, keeps the fixture process and file-backed logs independently
owned, and invokes only the fixed `uia-timeout-spike/supervisor.py` and
`worker.py` pair. The worker performs a read-only UIA snapshot; this controller
has no menu, input, Invoke, selection, registry, or Nulloy operation.

## Safety and verdict boundaries

- The CLI refuses to run unless `os.name == "nt"`. It has no worker-script or
  query replacement option.
- Each run gets a unique evidence directory and a unique owned temporary
  parent. Evidence is never overwritten. Fixture state copies, stdout,
  stderr, raw supervisor reports, runtime SHA-256 hashes, and the final JSON
  report are retained in the evidence directory.
- Fixture identity is checked against the live `Popen` PID and `psutil`
  create-time/executable, not the state record alone. The HWND, Qt 6.8.2,
  Windows platform, nonce, and snapshot PID/label are checked as well.
- Cleanup uses finite terminate/wait and kill/wait stages on the owned child
  only. Unknown cleanup retains the temporary parent and forces `FAIL`.
- A blocked-stage execution timeout can be `PASS` only when the responsive
  query was verified, the fixture heartbeat independently stopped, the
  fixture was still blocked at capture, the timeout was inside the configured
  10/5/2/2-second stage budget, the worker exit/cleanup were verified, and
  fixture cleanup was verified. The label is deliberately
  `execution_timeout_worker_containment_only`; it is not proof that a COM call
  itself was interrupted.
- A worker return, worker error, or readiness timeout during the blocked stage
  is `PARTIAL`, not a fabricated timeout pass. A resumed fixture is recorded
  and never claimed to have been continuously blocked.
- Exit codes are `0` for `PASS`, `2` for `PARTIAL`, and `1` for `FAIL`.

## Windows run

Use the reviewed environment and an isolated disposable Windows runner:

```powershell
python tools/uia-timeout-native/run_probe.py --evidence-root uia-timeout-native-evidence
```

The command prints the complete report JSON. The printed report contains the
path to `final-report.json`; the files under that unique directory are the
external evidence artifact. `github_workflow_sha` is populated only when
`GITHUB_SHA` is a valid 40-hex value; local runs record `None` explicitly.

## Linux tests

The test suite runs the real PySide6 fixture with `QT_QPA_PLATFORM=offscreen`
and uses an explicit, trusted Python query seam. This exercises real fixture
heartbeat blocking, atomic request handling, identity checks, report
serialization, and owned cleanup, but it is **not native UIA acceptance** and
reports `native_acceptance_false: true`.

```bash
/home/hermes/workspace/nulloy-status-current/uia-fixture-venv/bin/python \
  -m unittest -v tools/uia-timeout-native/test_probe.py
```

No native Windows UIA query was performed in the Linux implementation run.
The pre-existing `tools/uia-timeout-spike/` and
`tools/uia-timeout-fixture/` directories are inputs and are not modified.
