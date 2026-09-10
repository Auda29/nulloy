# Windows Explorer/UIA desktop probe

`tools/desktop-probe/probe.py` is a bounded feasibility probe for the Qt 6 Windows package. It is not the complete upstream `#211` acceptance matrix and does not cover `#255` or `#236`.

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
9. Only the probe's player process (matched by exact package path, PID, and creation time), player window, exact Explorer window/path, registry key, and temporary fixture directory are owned. The probe never kills Explorer or arbitrary player processes and never removes user files.

The probe writes evidence even when blocked or failed. Typical files are:

- `result.json`, `status.txt`
- `archive.sha256`, `executable.sha256`
- `desktop-preflight.png`
- `explorer-before.png`, `explorer-failure.png`, `explorer-uia.jsonl`
- `player.png`, `player-failure.png`, `player-uia.jsonl`, `player-uia-failure.jsonl`
- `explorer-selection.txt`, `playlist-rows.txt`, `playlist-row-observations.jsonl`

A cleanup failure prevents `PASS`. Registry deletion sends `SHChangeNotify(SHCNE_ASSOCCHANGED, ...)` and is read back. The exact owned Explorer window is closed and its disappearance is verified; the shared Explorer process is never killed. The exact packaged player PID is gracefully terminated only after identity revalidation, then narrowly force-terminated only if needed. Cleanup errors are retained in `result.json` and never converted to `cleanup_verified=true`. Package extraction is outside the evidence directory; if an owned player process cannot be cleaned up, extraction is preserved rather than recursively deleting files that may still be loaded.

## Prerequisites and bounds

Run on an interactive Windows desktop with a usable input session. The build runner must have Python, `pywinauto`, Pillow, and `psutil` installed. The package must be a clean Qt 6 package produced by `tools/phase2/package-windows.py`; a currently running copy of that packaged executable blocks the cold-launch slice. Explorer, UIA, registry associations, and the package itself must be allowed by the runner policy. `--headless-audio` is only a narrowly scoped no-device fallback for the diagnosed runner condition; it does not suppress application dialogs or settings and does not claim audio-output acceptance.

The input-desktop WinSta0/foreground interaction ctypes preflight remains deferred. The existing screenshot and UIA checks prove that an interactive desktop is enumerable, but not that injected input reaches the active desktop; adding a typed-handle check without a Windows runner to validate its semantics would risk a false safety result. A blocked outcome remains distinct and expected when runner policy supplies no usable interactive desktop.

Pure contracts run on Linux or Windows without desktop dependencies:

```text
python -m unittest discover -s tools/desktop-probe -p 'test_*.py'
```

This initial proof intentionally covers only one cold launch, one three-file Explorer multi-selection, one `.wav` Document verb, and the playlist read-back. It does not claim the full upstream `#211` matrix, repeated launches, skins, scaling, private media, update behavior, or the separate `#255`/`#236` work.
