# Harmless Qt timeout target

**Verdict: PARTIAL — real Linux Qt tested; Windows UIA untested.**

This standalone fixture provides an independently observable GUI target for a future supervised, read-only UIA experiment. It does not start Nulloy, invoke actions, inject input, change the registry or trash files. No existing player or inspector code is changed.

## Run

Dependencies: Python with `PySide6==6.8.2` and `psutil==7.0.0`.

```text
python tools/uia-timeout-fixture/fixture.py --root <new-directory-under-owned-temp-parent> --nonce <unique-ASCII-token> --lifetime 60 --block-seconds 30
```

The supplied root must not exist; its parent must exist. The fixture creates that root exclusively and retains evidence there. The launching controller owns the process handle and is responsible for bounded termination, exit verification and eventual removal of its own temporary directory. Do not launch using global process-name discovery or kill by an externally supplied PID.

`state.json` is atomically replaced and contains the nonce, PID, process creation time, actual executable, `winId()`, Qt version/platform, heartbeat, phase and monotonic sample time. On native Windows the ID is intended to identify the owned window; Linux offscreen IDs are **not validated Windows HWNDs**.

A 50 ms Qt timer increments the heartbeat. To request one deliberate GUI-thread stall, the controller atomically writes `block-request.json` containing exactly `{"nonce":"<same-token>"}` into this owned root. The matching nonce is an identity check, not an authentication boundary against another process running as the same user. Publish the request via a temporary file plus replace; a partial/invalid request deliberately fails closed. The fixture records `phase=blocked` before sleeping on its own GUI thread. The heartbeat stops, then resumes; `block_count=1` prevents repeat execution, and `block_elapsed` records the measured sleep. A wrong nonce or malformed request yields a failed record and exit code 1, not a silently successful Qt event-loop exit.

Lifetime is finite and at most 120 seconds; block duration is finite and at most 90 seconds. **The lifetime Qt timer is not an independent watchdog:** it cannot fire while the GUI thread is sleeping. A controller must enforce its own process deadline. A blocked GUI thread also does not prove a UIA call blocks: a provider may return cached data or an error. Record the actual native outcome.

## Tests

```text
python -m unittest discover -s tools/uia-timeout-fixture -v
```

Tests use real subprocesses and real Qt; on non-Windows they set `QT_QPA_PLATFORM=offscreen`. Four test methods cover responsive heartbeat/exact live process identity and graceful exit; controlled stall, stopped heartbeat, measured recovery and single execution; invalid duration/nonce rejection before filesystem changes (12 subcases); and malformed/foreign-nonce requests failing without a stall (two subcases). Cleanup targets only the owned `Popen` handle and waits with finite timeouts.

Tests-first development observed missing fixture failure, missing stall behavior failure, missing configurable duration failure, invalid NaN creating a root failure, and swallowed Qt callback exception falsely exiting zero. Each was followed by a real passing execution after the corresponding implementation.

## Remaining native experiment

After independent review, run contracts on disposable GitHub-hosted windows-2022, then combine with the separately developed read-only worker. First inspect the responsive exact owned target, then request a stall and repeat the same UIA query with the supervisor deadline. Verify fixture identity, output, worker exit and fixture cleanup separately. No menu, player, recycling or final-package acceptance is implied.
