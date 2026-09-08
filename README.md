# NulloyFork

A community-maintained fork of [Nulloy](https://github.com/nulloy/nulloy), the
music player with a waveform progress bar, originally created by Sergey Vlasov.
This is an independent project. Releases from this repository are fork builds,
not official Nulloy releases.

The aim is to modernize the player while keeping its familiar interface,
playlist workflow and skins. Adding one or several tracks by drag-and-drop,
responsive startup and shutdown, and quick waveform loading remain priorities.

[Download the Windows x64 alpha](https://github.com/Auda29/nulloy/releases/tag/v0.10.0-alpha.2)
| [All fork releases](https://github.com/Auda29/nulloy/releases)
| [Report a fork issue](https://github.com/Auda29/nulloy/issues)
| [Build and test workflow](https://github.com/Auda29/nulloy/actions/workflows/windows-cmake.yml)

## What is different in this fork?

The following changes are included in **v0.10.0-alpha.2**:

| Area | Changes in the fork |
|---|---|
| Qt 6 | The player runs on Qt 6 with Qt Widgets. QJSEngine replaces QtScript, and the skin loader uses public Qt APIs. |
| Existing interface | Slim, Silver, Metro and Native skins are retained. The control layout and playlist workflow are preserved. |
| Windows x64 | CMake and Ninja build the player and plugins as 64-bit binaries. The old Windows 32-bit/qmake instructions are no longer the main build path. |
| Portable profile | `NulloyFork.exe` stores settings, playlist and caches in its own `Data` directory. Separate portable copies can run independently. |
| Startup | Packages include a relocatable GStreamer plugin cache to reduce first-start scanning. Missing, invalid or outdated caches are rebuilt. |
| Compatibility fixes | The migration includes Unicode tag read/write fixes, persistent skin settings, and Windows taskbar minimize/restore handling. |
| Automated validation | GitHub Actions builds Qt 5 and Qt 6 variants and checks skins, drag-and-drop, playback, waveform generation, Unicode tags, profile compatibility and extracted packages. |
| Releases | Alpha tags trigger a workflow that builds, tests and publishes portable packages with SHA-256 checksums and build metadata. Upstream automatic update checks are disabled in the portable fork. |

Playback and waveform generation still use GStreamer, with TagLib for metadata
and cover art. The portable build does not enable the VLC backend.

![Original Nulloy interface](https://nulloy.com/files/screen.png)

The image above is an upstream Nulloy screenshot, shown as a reference for the
interface this fork preserves. [More upstream screenshots](https://nulloy.com/screenshots/).

## Download and run

The current release is **v0.10.0-alpha.2**, a Windows x64 prerelease.

1. Download `NulloyFork-0.10.0-alpha.2-windows-x64.zip` from the
   [fork release page](https://github.com/Auda29/nulloy/releases/tag/v0.10.0-alpha.2).
2. Extract the entire ZIP into a writable folder and start `NulloyFork.exe`.
3. Drag one or multiple audio files into the playlist.

Settings, the saved playlist and caches live in `Data` next to the executable.
The original Nulloy profile is not imported automatically. To move the portable
copy, close the player and copy its entire folder; external music files must
still be accessible. Back up `Data` before replacing a build.

Updates are downloaded manually from this fork's releases. There is no automatic
fork update channel yet. See the [portable usage and profile import guide](docs/phase4/PORTABLE.md)
for importing copies of existing settings and playlists.

Windows x64 is the current release target. Linux and macOS source code remains
in the repository, but this fork does not yet provide validated packages for
those platforms. Test results and remaining validation limits are recorded in
the [portable migration report](PHASE4_REPORT.md).

## Development status

The Qt 6, CMake, Windows x64 and portable-profile migration has been completed.
The [migration plan](MIGRATION_PLAN.md) describes the staged approach and later work.

[Merged fork PR #6](https://github.com/Auda29/nulloy/pull/6) contains the adapted port of
[upstream PR #263](https://github.com/nulloy/nulloy/pull/263): seek/gapless fixes,
GStreamer resource handling, shared TagLib file validation and AIFF file filters.
These changes are included in **v0.10.0-alpha.2**. See the [release notes](docs/releases/0.10.0-alpha.2.md) for the changes and remaining validation limits.

A limited Rust component pilot is planned for a later phase. The current player
is C++/Qt; a complete Rust rewrite has not been adopted as the project goal.

## Building the fork

Use MSYS2 MINGW64 with Qt 6.8 or newer, CMake, Ninja, GStreamer and TagLib.
The [Qt 6 build guide](docs/phase3/BUILD_WINDOWS_QT6.md) lists the required packages.
For the portable fork build, run these commands from the repository root in the
MINGW64 shell:

```bash
cmake --preset windows-portable-x64 -DCMAKE_PREFIX_PATH="$(cygpath -m /mingw64)"
cmake --build --preset windows-portable-x64
ctest --preset windows-portable-x64
python tools/phase2/package-windows.py --prefix "$(cygpath -m /mingw64)" --build .phase4/build --source .
python tools/phase2/verify-package.py --prefix "$(cygpath -m /mingw64)" --build .phase4/build --headless-audio
```

The package is written to `.phase4/build/`. The final command checks an extracted
copy without the development toolchain on `PATH`; `--headless-audio` allows it
to run without an audio device and is not a listening test.

The `windows-x64` preset remains available for Qt 5 compatibility checks.
Historical upstream qmake instructions are retained in
[the legacy build reference](docs/LEGACY_BUILD.md).

## Project records

- [Phase 0: Baseline](PHASE0_REPORT.md)
- [Phase 1: Skin compatibility prototype](PHASE1_REPORT.md)
- [Phase 2: CMake and Windows x64](PHASE2_REPORT.md)
- [Phase 3: Qt 6 integration](PHASE3_REPORT.md)
- [Phase 4: Portable player and alpha release](PHASE4_REPORT.md)

## Upstream and license

NulloyFork builds on the work of Sergey Vlasov and the Nulloy contributors.
The original project is available at [nulloy/nulloy](https://github.com/nulloy/nulloy)
and [nulloy.com](https://nulloy.com/). Please use
[this fork's issue tracker](https://github.com/Auda29/nulloy/issues) for problems
with its builds.

The fork retains the original copyright notices and the
[GNU General Public License version 3](LICENSE.GPL3). Third-party components
retain their respective licenses.
