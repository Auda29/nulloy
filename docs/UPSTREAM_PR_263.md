# Port of upstream PR 263

Source: [nulloy/nulloy#263](https://github.com/nulloy/nulloy/pull/263), by
the3asic, reviewed at `a859095c8ea3e4d92177236240fac29d4b6b0f71`.

The upstream commits are `a85067f2be90638fe44b6c7c8bc23035e43ccd40`
for playback, `9c3068c9d3c619509af0d671e3a00786ba074a3b` for resources,
and `a859095c8ea3e4d92177236240fac29d4b6b0f71` for AIFF filters.
This is an adapted port onto the fork's Qt Widgets player. It does not import
the upstream QML controller or change the skins.

## Playback changes

The GStreamer streaming callback consumes a mutex-protected successor URI.
It no longer makes a blocking request to the GUI thread. Current-track metadata
is updated on the GUI thread when the corresponding stream starts.
Bus messages and the bus reference obtained by the polling timer are released.

The Widgets playlist refreshes its successor after insertion, removal, reordering,
shuffle, repeat and loop changes. Model notifications are coalesced so a multi-file
drop does not schedule a refresh for every inserted row. Clearing the playlist
also clears its item map. Removal by filename no longer leaves dangling pointers.
Shuffle collects the original item count before removing items.

The normal EOS fallback now selects the immediate successor or repeats the same
item. This fallback also handles short tracks that finish before a successor is
prepared. A prepared successor is consumed once, avoiding duplicate handoffs
before the GUI has processed the next stream-start message.

Additional handling beyond upstream:

- Stop and manual track changes disable handoffs before resetting the pipeline.
  The mutex is never held across a pipeline state change or seek.
- A seek back into the current track or removal of an already prepared successor
  revokes the queued URI by restarting the current track at its saved position.
  This path preserves the requested play/pause state and does not count the
  restart as another played track.
- A flushing seek can discard the restart's stream-start notification. The next
  real track transition must still update the visible track.
- Zero or unknown durations are rejected before calculating relative positions.

## Resources and file filters

Waveform processing releases negotiated caps and checks for missing caps,
invalid channel counts and unmappable buffers. Tag reads and writes validate the
actual shared TagLib file reference, including after the cover reader releases it.
Releasing an empty cover source leaves a null reference.

The default file filters include `.aif` and `.aifc`. Existing profiles receive
these extensions only if their filter list still matches the previous default.
Custom lists are preserved.

## Regression coverage

- Gapless handoff without an EOS fallback, including appended multi-file drops,
  successor deletion, deletion during a prepared handoff, reorder, shuffle,
  repeat and playlist looping.
- Forced EOS fallback with and without repeat.
- Repeated seeks near track end, seek back, pause/resume, stop and manual selection.
- Ordered playback and final stop for 50 ms, 250 ms and 800 ms tracks.
- Shared tag/cover file release, missing and unsupported files, and Unicode tags.
- Repeated waveform builds and cancellation.
- New/default filter migration with preservation of custom settings.

These tests exercise real GStreamer and TagLib plugins. Playlist tests use
synchronized fake audio sinks, so they do not measure audible gap length.
The resource fixes follow the API ownership contracts; these tests are not a
long-running heap or leak measurement.

## Manual check before merging

Local validation on Windows 11, 2026-09-08:

- Qt 6.11.2 portable build: all five CTest targets passed.
- Qt 5.15.19 compatibility build: all five CTest targets passed.
- Seek-back and removal-during-handoff regressions: five consecutive additional
  runs passed with Qt 6.
- Extracted portable package: Slim, Silver, Metro and Native workflows passed,
  including native taskbar minimize/restore and shutdown during waveform work.
- WAV, MP3, FLAC, Ogg, Opus and WavPack package checks passed, including Unicode
  tag write/reopen and cold/cached waveform generation.

The first extracted-package Slim run took 11.934 s to expose its window; 10.544 s
had elapsed before discovery of the GStreamer plugin. Subsequent skin runs took
0.563 to 0.772 s. This first-load outlier is recorded rather than attributed to
the patch without evidence. The real-file manual check remains necessary.

Use a test package built from the PR, with its own portable `Data` directory.
Play several real music files, add multiple tracks by drag-and-drop, and remove
or reorder the next track during playback. Seek close to the end and back into
the current track several times. Check that pause/resume, repeat and the next
track behave as expected. Listen to adjacent tracks for unwanted gaps and check
opening, closing and cold/cached waveform loading with your usual files.

No release tag or existing release is changed by this PR.
