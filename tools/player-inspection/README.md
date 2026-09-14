# Packaged player inspection

This is test automation, not player acceptance or a release gate by itself.
The existing default read-only inspector and the opt-in context-menu inspector
remain available. They still contain synchronous UIA operations in the controller;
the new bounded mode does not make those legacy paths bounded.

## Additional bounded read-only path

```powershell
python tools/player-inspection/inspect_player.py `
  --package PATH_TO_EXACT_PACKAGE.zip `
  --output evidence-bounded `
  --source-sha EXACT_PACKAGE_SOURCE_COMMIT `
  --archive-sha256 EXACT_ARCHIVE_SHA256 `
  --bounded-read-only
```

Use the package identity fixed in `player-inspection.yml`, not a newly built or
similarly named ZIP. The inspector validates the archive and package manifest
before launching only the extracted portable executable with generated WAV files.

The bounded mode uses a separate `uia_worker.py` process for UIA traversal.
`uia_supervisor.py` applies separate finite readiness, execution, terminate/wait,
and kill/wait stages and retains file-backed stdout/stderr plus a result report.
The operational CLI cannot substitute an arbitrary worker. The Python
`worker_script` seam exists only for trusted test fixtures; it is not a sandbox.
OS process creation itself is not claimed to have a hard deadline.

The supervisor reads at most `output_cap + 1` bytes per stream per capture. This
bounds diagnostic reading, not the total size a child can write between polls;
it is not a hard disk quota. Errors after process creation still require owned
worker cleanup. Incomplete diagnostics or cleanup cannot certify success.

The timeout design derives from the separate UIA timeout experiment, but these
player-specific files are a new adaptation and require their own review and
native execution. A green historical fixture run is not proof of this code.

## Scope and evidence

- Bounded mode returns primitive UIA and exact playlist-row observations.
- It performs no selection, mouse/keyboard input, menu invocation, or deletion.
- It cannot be combined with `--inspect-context-menu` or pointer input.
- It does not capture screenshots. Legacy runs provide their own separate
  screenshots; those are not screenshots of the bounded run.
- A contained worker timeout is a failed observation, not proof that Windows
  interrupted a COM call, and never a successful player acceptance result.
- Generated file integrity, owned process cleanup, and temporary-file retention
  on uncertain cleanup remain separate evidence obligations.
- Native Windows execution and independent final review are still required.
  Linux tests do not establish Windows UIA behavior or any trash/Explorer case.

## Local contracts

```bash
TMPDIR=/tmp python -m unittest discover -s tools/player-inspection -p 'test_*.py' -v
```

On Windows, run the same Python command without the POSIX `TMPDIR` prefix.
Only the test of ignoring POSIX `SIGTERM` is skipped there. A separate portable
test runs a real child with a trusted no-op `terminate` seam and exercises the
real kill/wait fallback on either platform; this is transport containment, not
native UIA acceptance. The missing-package CLI test expects `FAIL` on Windows
and the explicit platform `BLOCKED` result elsewhere.

## Bounded context-menu observation

The context slice is opt-in and uses a separate supervised worker:

```powershell
python tools/player-inspection/inspect_player.py `
  --package PATH_TO_EXACT_PACKAGE.zip `
  --output evidence-context-bounded `
  --source-sha EXACT_PACKAGE_SOURCE_COMMIT `
  --archive-sha256 EXACT_ARCHIVE_SHA256 `
  --bounded-context-menu
```

This mode validates the pinned `NMainWindow`/playlist, focuses the first exact
row, and uses only UIA `SelectionItem.Select` followed by
`AddToSelection` to establish `[True, True, False]`. It then posts one
keyboard-reason `WM_CONTEXTMENU` (`LPARAM=-1`) to the already-owned root HWND.
The worker observes one fresh owned `QMenu`/`Pane` and exactly four visible
menu items, including the exact `Move To Trash` and `Remove From Playlist`
labels and automation IDs with distinct runtime IDs. It records
`menu_items_invoked=false` and performs no menu invocation, trash action,
pointer input, global input, or modal handling.

`--bounded-context-menu` is incompatible with `--bounded-read-only`,
`--inspect-context-menu`, and `--allow-owned-pointer-input`. The mode is not
passive read-only because it changes focus and selection and posts a context
request. It emits primitive JSON only, does not claim screenshot evidence, and
does not prove that a particular Qt build routes the keyboard-reason request;
native Windows execution and independent review remain required.
