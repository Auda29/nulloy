# Windows Explorer/UIA desktop probe

## PR28 tooling-only rebuild — 2026-10-01

PR28 is rebuilt on integration `bcd9b63709d373bd932a1e419a299f04b8a44ae6`.
The former head, including PR24 ancestry, is preserved at
`archive/2026-10-01/windows-desktop-probe-before-rebuild`. No product sources,
PR24 policy or product-test fixtures are included in the rebuilt diff.

`desktop-probe.yml` runs mocked contracts on relevant PRs. Its explicit manual
dispatch builds the branch's own package and exercises cold/warm-empty Explorer
opens with 3 and 12 files, using enqueue=true/play-enqueued=false. This is a
tooling check on the existing append behavior, not acceptance of PR24's replacement
or first-enqueued playback behavior. The full PR24 preference matrix stays on its
separate acceptance branch. Qt5/Qt6 builds remain serial; packages are retained
for three days only on dispatch, desktop evidence for seven days.

The optional `monitor_probe.py` helper is retained as test tooling only. This
workflow does not run or claim physical-monitor, hotplug or mixed-DPI acceptance.
The historical sections below describe their original package sources and scope.

The first rebuilt dispatch, `36848055700` (source `47274d0`), passed both toolkit
builds and the 49 contracts. All four Explorer cases reached playlist observation
and verified cleanup, then failed the additional trace correlation: integration
does not contain the combined branch's `player-message` instrumentation. The
tooling-only dispatch therefore does not request `--trace-startup`. That option
remains a stricter, separate check requiring an appropriately instrumented package;
the failing correlation has not been relabeled as a passing trace test. PR28's
native scope is exact UI membership/multiplicity, process ownership and cleanup,
not player-message delivery order or PR24 policy acceptance.

## 2026-09-28 combined-candidate follow-up

Branch `test/windows-open-acceptance` combines current integration (`5b2c600`)
with PR #29 (`9d7de51`) and PR #24 (`21848c1`). The first diagnostic builds source
`17bc6455d5b787754ad0540ebca9b5f02b8920e0`. Product PRs have not been merged into
integration. The historical observations below still describe their original runs.

`open-matrix.yml` reuses an exact previously built Qt6 package, verifies its source
SHA and all manifest hashes, and runs all four EnqueueFiles/PlayEnqueued settings
on cold and warm-empty starts plus a 12-file cold selection. Preferences are set
only inside the freshly extracted portable package, including SettingsVersion so
the application does not discard them. Every case has its own package extraction,
fixtures and evidence directory. Unverified cleanup stops subsequent cases.

The follow-up probe refreshes process discovery during window polling and before
cleanup, retaining earlier process identities. Registry creation now checks the
Win32 new-key disposition; deletion requires the run's ownership marker and an
unchanged command. Menu discovery requires the exact fixture Explorer window in
the foreground and the same Explorer PID. Local regression checks cover late
primary discovery, foreign registry ownership and foreign-process menu labels.
These changes still require actual native results; passing mock contracts alone
does not close PR #28's review.

The matrix checks exact file membership, multiplicity and a single player window.
It does not yet assert received-message order, playing row/position, nonempty
playing/paused warm state, independent rapid opens or audible output. The hosted
Windows Server runner is not a Windows 11 or mixed-DPI hardware acceptance lab.

Example scenario (omit `--warm-start` for cold startup):

```text
python tools/desktop-probe/probe.py --package package.zip --source-sha <package-source-sha> --output evidence --headless-audio --enqueue false --play-enqueued true --warm-start
```

`tools/desktop-probe/probe.py` is a bounded feasibility probe for the Qt 6 Windows package. It is not the complete upstream `#211` acceptance matrix and does not cover `#255` or `#236`.

## Current acceptance limits

This probe is **not accepted for integration**. Native run [34477210965](https://github.com/Auda29/nulloy/actions/runs/34477210965) recorded three visible `NMainWindow` instances in three distinct processes, rather than one. Its package source is `e3371b2cf8b5c364bdba3aa0c142b9bd2d936e5f` (branch head `e2ea841bdfaa5e6c7e81eecb2f0a2cc3a917fa88`); this is a failure observation, not a passed Explorer acceptance.

The code now re-discovers the stored Explorer HWND/directory before closing instead of trusting a cached wrapper. That change has local regression coverage; native verification is still pending. Other independent-review findings remain open: process ownership is inferred from a best-effort snapshot, registry creation/deletion lacks a verified ownership marker, and menu lookup is not bound to the owned Explorer HWND. A reported `cleanup_verified=true` describes the checks implemented for that run, not proof that these remaining safety gaps are resolved.

`player-discovery.jsonl` records each discovery poll and distinguishes no main window, multiple main windows, one selected main window, and exceptions. The exact-one-main requirement must not be relaxed to bypass the observed multi-instance startup.

## Invocation

```text
python tools/desktop-probe/probe.py \
  --package path/to/NulloyFork-<version>-windows-x64.zip \
  --output desktop-probe-evidence \
  --source-sha <github.sha> [--headless-audio]
```

The package and probe jobs must use the same `github.sha` (the PR merge commit under the current workflow policy). `--source-sha` is checked against `package-manifest.json.source_commit`; it is not inferred from the ZIP. If the workflow also knows the PR head SHA, it may report that separately, but the package provenance assertion remains the exact `github.sha` used by checkout/build/package.

Exit codes are:

- `0` — `PASS`: all exact assertions passed and owned-resource cleanup was verified.
- `1` — `FAIL`: a package, provenance, shell, UIA, or playlist assertion failed.
- `2` — `BLOCKED`: a required prerequisite was unavailable or the cold-launch safety preflight could not run.

## What the first slice proves

1. The ZIP SHA-256 is calculated from the exact archive bytes. An adjacent `.zip.sha256` sidecar, when present, must agree.
2. The archive contains one safe package root and a manifest. Every manifest file is hash-checked after extraction, including the packaged `.exe`.
3. The manifest has the exact supplied `source_commit`, `tracked_changes: false`, `upstream_update_check: false`, and `qt_major: "6"` profile.
4. A desktop screenshot and UI Automation desktop enumeration succeed before any state change.
5. Three one-second generated WAV files (44100 mono frames at 44100 Hz) are created in a private temporary directory.
6. A unique HKCU `SystemFileAssociations\\.wav\\shell\\NulloyDesktopProbe-<run>` verb is installed with `MultiSelectModel=Document`. Its command contains one `%1` file placeholder, never `%*`, and starts the packaged app with `PATH=%SystemRoot%\\System32` so development/toolchain DLL paths are not used. With the explicit `--headless-audio` opt-in, the same Explorer-launched command also sets `GST_PLUGIN_FEATURE_RANK=directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0`; this reports `audio_mode=no-device-fallback` and excludes `audio_output_not_tested` from acceptance. It is not audio acceptance and does not alter the normal device-backed mode.
7. Explorer is opened on that private directory. The three files are selected in Explorer and the verb is invoked through the actual Explorer context menu; no multi-file CLI substitute is used. Only the exact `UIItemsView` file container and its direct `ListItem` rows are considered, and selection is re-read after any fallback before continuing.
8. UIA reads the cold-launched packaged player's playlist after a bounded stabilization wait. The control must match the observed Qt identity `class_name=NPlaylistWidget`, `automation_id=QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget`; every intermediate row snapshot is retained, and each generated basename must occur exactly once with exactly three rows.
9. The intended ownership scope is the private packaged player processes, exact Explorer window/path, unique registry verb and generated fixture directory. PID/creation-time/executable revalidation narrows process cleanup, but does not resolve all ownership gaps listed above. Explorer itself is never terminated as a process.

The probe writes evidence even when blocked or failed. Typical files are:

- `result.json`, `status.txt`
- `archive.sha256`, `executable.sha256`
- `desktop-preflight.png`
- `explorer-before.png`, `explorer-selection.png`, `explorer-selection-uia.jsonl`, `explorer-failure.png`, `explorer-uia.jsonl`
- `player.png`, `player-failure.png`, `player-uia.jsonl`, `player-uia-failure.jsonl`
- `explorer-selection.txt`, `playlist-rows.txt`, `playlist-row-observations.jsonl`

A primary probe failure is retained in `result.json.error` and `result.json.error_traceback`; cleanup failures are retained separately in `cleanup_errors` (and `cleanup_error_traceback` when evidence collection itself fails) and never converted to `cleanup_verified=true`. A cleanup failure prevents `PASS`. Registry deletion sends `SHChangeNotify(SHCNE_ASSOCCHANGED, ...)` and is read back. The exact owned Explorer window is closed and its disappearance is verified; the shared Explorer process is never killed. The exact packaged player PID is gracefully terminated only after identity revalidation, then narrowly force-terminated only if needed. Package extraction is outside the evidence directory; if an owned player process cannot be cleaned up, extraction is preserved rather than recursively deleting files that may still be loaded.

## Prerequisites and bounds

Run on an interactive Windows desktop with a usable input session. The build runner must have Python, `pywinauto`, Pillow, and `psutil` installed. The package must be a clean Qt 6 package produced by `tools/phase2/package-windows.py`; a currently running copy of that packaged executable blocks the cold-launch slice. Explorer, UIA, registry associations, and the package itself must be allowed by the runner policy. `--headless-audio` is only a narrowly scoped no-device fallback for the diagnosed runner condition; it does not suppress application dialogs or settings and does not claim audio-output acceptance.

The input-desktop WinSta0/foreground interaction ctypes preflight remains deferred. The existing screenshot and UIA checks prove that an interactive desktop is enumerable, but not that injected input reaches the active desktop; adding a typed-handle check without a Windows runner to validate its semantics would risk a false safety result. A blocked outcome remains distinct and expected when runner policy supplies no usable interactive desktop.

Pure contracts run on Linux or Windows without desktop dependencies:

```text
python -m unittest discover -s tools/desktop-probe -p 'test_*.py'
```

This initial proof intentionally covers only one cold launch, one three-file Explorer multi-selection, one `.wav` Document verb, and the playlist read-back. It does not claim the full upstream `#211` matrix, repeated launches, skins, scaling, private media, update behavior, or the separate `#255`/`#236` work.
