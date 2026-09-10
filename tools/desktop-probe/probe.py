#!/usr/bin/env python3
"""Windows Explorer/UIA feasibility probe for a packaged Qt 6 Nulloy build.

The Linux-runnable portion of this module owns the package/provenance and verdict
contracts.  The desktop slice is deliberately small: three generated WAV files,
one cold player launch, and one Explorer context-menu invocation.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import wave
import zipfile
from typing import Any, Iterable, Sequence


SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SOURCE_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
EXPECTED_FIXTURE_COUNT = 3
FIXTURE_SAMPLE_RATE = 44100
FIXTURE_FRAMES = 44100
PLAYLIST_STABILIZATION_TIMEOUT = 5.0
PLAYLIST_STABLE_SNAPSHOTS = 2
PLAYLIST_CONTROL_CLASS = "NPlaylistWidget"
PLAYLIST_CONTROL_AUTOMATION_ID = "QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget"


class ContractError(ValueError):
    """The package, shell contract, or an exact assertion is invalid."""


class BlockedError(RuntimeError):
    """The runner cannot safely execute the desktop slice."""


@dataclasses.dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float
    executable: str


@dataclasses.dataclass(frozen=True)
class PackageContract:
    source_commit: str
    root: str
    executable: str
    portable: bool
    qt_major: str
    upstream_update_check: bool
    files: dict[str, str]


@dataclasses.dataclass(frozen=True)
class ExtractedPackage:
    archive_sha256: str
    executable_sha256: str
    file_hashes_verified: int
    root: Path
    executable: Path
    contract: PackageContract


@dataclasses.dataclass(frozen=True)
class ShellVerbProfile:
    key_name: str
    registry_path: str
    label: str
    command: str
    multi_select_model: str = "Document"
    audio_mode: str = "device"


def parse_source_sha(value: str) -> str:
    if not SOURCE_SHA_RE.fullmatch(value):
        raise ContractError("--source-sha must be exactly 40 hexadecimal characters")
    return value


def _required_string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ContractError(f"manifest field {key!r} must be a non-empty string")
    return value


def _relative_manifest_path(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    reserved = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
    if (path.is_absolute() or ".." in path.parts or "\\" in value
            or path.as_posix() != value or value == "."
            or any(re.search(r'[<>:"|?*\x00-\x1f]', part)
                   or part.endswith((".", " ")) or reserved.match(part)
                   for part in path.parts)):
        raise ContractError(f"unsafe {field}: {value!r}")
    return path.as_posix()


def validate_manifest(manifest: dict[str, Any], source_sha: str) -> PackageContract:
    """Validate the package-windows.py manifest/profile contract."""
    source_sha = parse_source_sha(source_sha)
    actual_source = _required_string(manifest, "source_commit")
    if actual_source != source_sha:
        raise ContractError(
            f"package source_commit {actual_source!r} does not match --source-sha {source_sha!r}"
        )
    if manifest.get("tracked_changes") is not False:
        raise ContractError("package must have tracked_changes=false")
    if manifest.get("upstream_update_check") is not False:
        raise ContractError("package must have upstream_update_check=false")
    root = _relative_manifest_path(_required_string(manifest, "root"), "root")
    if "/" in root:
        raise ContractError("manifest root must be one archive directory")
    executable = _relative_manifest_path(_required_string(manifest, "executable"), "executable")
    if executable.lower().endswith(".exe") is False:
        raise ContractError("manifest executable must be an .exe")
    qt_major = str(manifest.get("qt_major", ""))
    if qt_major != "6":
        raise ContractError(f"desktop probe requires Qt 6 package, got {qt_major!r}")
    portable = manifest.get("portable")
    if not isinstance(portable, bool):
        raise ContractError("manifest portable flag must be boolean")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ContractError("manifest files must be a non-empty object")
    normalized: dict[str, str] = {}
    for filename, expected in files.items():
        filename = _relative_manifest_path(filename, "manifest file")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise ContractError(f"manifest hash for {filename!r} is not SHA-256")
        normalized[filename] = expected
    if executable not in normalized:
        raise ContractError("manifest files does not contain the executable")
    return PackageContract(
        source_commit=actual_source,
        root=root,
        executable=executable,
        portable=portable,
        qt_major=qt_major,
        upstream_update_check=False,
        files=normalized,
    )


def validate_archive_members(members: Iterable[str], root: str) -> None:
    """Reject ZIP paths that could extract outside the package root."""
    root = _relative_manifest_path(root, "root")
    seen: set[str] = set()
    for member in members:
        if not isinstance(member, str) or not member or member.startswith(("/", "\\")):
            raise ContractError(f"unsafe archive member: {member!r}")
        _relative_manifest_path(member.rstrip("/"), "archive member")
        path = PurePosixPath(member)
        if ".." in path.parts or "\\" in member:
            raise ContractError(f"unsafe archive member: {member!r}")
        normalized = path.as_posix()
        if normalized.endswith("/"):
            normalized = normalized.rstrip("/")
        if normalized.casefold() in seen:
            raise ContractError(f"duplicate archive member: {member!r}")
        seen.add(normalized.casefold())
        if not (normalized == root or normalized.startswith(root + "/")):
            raise ContractError(f"archive member outside package root: {member!r}")
    manifest_name = root + "/package-manifest.json"
    if manifest_name.casefold() not in seen:
        raise ContractError("archive does not contain package-manifest.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_extracted_package(
    root: Path, manifest: dict[str, Any], source_sha: str
) -> ExtractedPackage:
    """Validate every manifest file and return the exact executable digest."""
    contract = validate_manifest(manifest, source_sha)
    package_root = root
    if package_root.name != contract.root:
        raise ContractError(f"extracted root is {package_root.name!r}, expected {contract.root!r}")
    for filename, expected in contract.files.items():
        path = package_root / filename
        if not path.is_file():
            raise ContractError(f"manifest file is missing: {filename}")
        actual = _sha256(path)
        if actual != expected:
            raise ContractError(f"manifest hash mismatch: {filename}")
    executable = package_root / contract.executable
    return ExtractedPackage(
        archive_sha256="",
        executable_sha256=_sha256(executable),
        file_hashes_verified=len(contract.files),
        root=package_root,
        executable=executable,
        contract=contract,
    )


def _manifest_from_archive(package: Path, source_sha: str) -> tuple[str, dict[str, Any]]:
    if not package.is_file():
        raise ContractError(f"package does not exist: {package}")
    archive_sha = _sha256(package)
    sidecar = package.with_suffix(package.suffix + ".sha256")
    if sidecar.is_file():
        tokens = sidecar.read_text(encoding="ascii").split()
        if not tokens or tokens[0] != archive_sha:
            raise ContractError("ZIP SHA-256 does not match its .sha256 sidecar")
    with zipfile.ZipFile(package) as archive:
        candidates = [
            item.filename
            for item in archive.infolist()
            if item.filename.endswith("/package-manifest.json")
        ]
        if len(candidates) != 1:
            raise ContractError("ZIP must contain exactly one package-manifest.json")
        with archive.open(candidates[0]) as stream:
            try:
                manifest = json.load(stream)
            except json.JSONDecodeError as exc:
                raise ContractError("package-manifest.json is not valid JSON") from exc
        if not isinstance(manifest, dict):
            raise ContractError("package-manifest.json must contain an object")
        contract = validate_manifest(manifest, source_sha)
        validate_archive_members((item.filename for item in archive.infolist()), contract.root)
    return archive_sha, manifest


def extract_and_validate(package: Path, destination: Path, source_sha: str) -> ExtractedPackage:
    archive_sha, manifest = _manifest_from_archive(package, source_sha)
    contract = validate_manifest(manifest, source_sha)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as archive:
        archive.extractall(destination)
    result = validate_extracted_package(destination / contract.root, manifest, source_sha)
    return dataclasses.replace(result, archive_sha256=archive_sha)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True, help="packaged Windows ZIP")
    parser.add_argument("--output", type=Path, required=True, help="evidence directory")
    parser.add_argument("--source-sha", required=True, help="exact 40-character source SHA")
    parser.add_argument(
        "--headless-audio",
        action="store_true",
        help="opt into no-device GStreamer ranks for the Explorer-launched app",
    )
    return parser.parse_args(argv)


def shell_command(executable: Path, headless_audio: bool = False) -> str:
    """Return a one-file command with a hermetic app PATH, never %*."""
    executable = executable.resolve()
    # Explorer expands %1 before invoking this command. cmd.exe sets the
    # child's environment, which also works when Explorer is a singleton and
    # ignores environment changes made only to the Explorer Popen request.
    assignments = ['set "PATH=%SystemRoot%\\System32"']
    if headless_audio:
        assignments.append(
            'set "GST_PLUGIN_FEATURE_RANK=directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0"'
        )
    prefix = "&&".join(assignments)
    return f'cmd.exe /d /s /c "{prefix}&&"{executable}" "%1""'


def shell_verb_profile(run_id: str, executable: Path, headless_audio: bool = False) -> ShellVerbProfile:
    if not re.fullmatch(r"[A-Za-z0-9-]+", run_id):
        raise ContractError("run id is not safe for a registry key")
    key_name = f"NulloyDesktopProbe-{run_id}"
    registry_path = rf"Software\Classes\SystemFileAssociations\.wav\shell\{key_name}"
    return ShellVerbProfile(
        key_name=key_name,
        registry_path=registry_path,
        label=f"Nulloy desktop probe ({run_id})",
        command=shell_command(executable, headless_audio=headless_audio),
        audio_mode="no-device-fallback" if headless_audio else "device",
    )


def exact_playlist_rows(actual: Sequence[str], expected: Sequence[str]) -> bool:
    """Require exactly the expected rows, with no duplicate or extra row."""
    if len(actual) != len(expected) or len(set(expected)) != len(expected):
        raise ContractError("playlist row count is not an exact unique match")
    if collections.Counter(actual) != collections.Counter(expected):
        raise ContractError(f"playlist rows differ: expected={list(expected)!r}, actual={list(actual)!r}")
    return True


def _normalized_executable(value: str) -> str:
    return os.path.abspath(value).casefold()


def process_identity_matches(process: Any, identity: ProcessIdentity) -> bool:
    """Match a live process without risking PID reuse or a different executable."""
    try:
        return (
            process.pid == identity.pid
            and float(process.create_time()) == identity.create_time
            and _normalized_executable(process.exe()) == _normalized_executable(identity.executable)
        )
    except (OSError, AttributeError, TypeError, ValueError):
        return False


def explorer_row_names(display_names: Sequence[str], expected: Sequence[str]) -> list[str]:
    """Map exact fixture names or hidden-extension labels, never substrings."""
    mapped = []
    for name in display_names:
        matches = [base for base in expected if name in (base, Path(base).stem)]
        if len(matches) != 1:
            raise ContractError(f"ambiguous or unknown Explorer row: {name!r}")
        mapped.append(matches[0])
    exact_playlist_rows(mapped, expected)
    return mapped


def verdict(assertions: Sequence[bool], cleanup_verified: bool) -> str:
    return "PASS" if bool(assertions) and all(assertions) and cleanup_verified else "FAIL"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _capture_image(image: Any, path: Path) -> None:
    try:
        image.save(path)
    except Exception as exc:  # pragma: no cover - Windows evidence fallback
        _write_text(path.with_suffix(path.suffix + ".error.txt"), repr(exc))


def _dump_uia(window: Any, path: Path) -> None:
    lines: list[str] = []
    try:
        controls = [window, *window.descendants()]
        for control in controls:
            info = control.element_info
            lines.append(
                json.dumps(
                    {
                        "control_type": getattr(info, "control_type", ""),
                        "name": getattr(info, "name", ""),
                        "automation_id": getattr(info, "automation_id", ""),
                        "class_name": getattr(info, "class_name", ""),
                        "process_id": getattr(info, "process_id", ""),
                    },
                    ensure_ascii=False,
                )
            )
    except Exception as exc:
        lines.append(json.dumps({"dump_error": repr(exc)}))
    _write_text(path, "\n".join(lines) + "\n")


def _wait_for(predicate: Any, timeout: float, description: str) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except Exception as exc:  # UIA can race window destruction.
            last_error = exc
        time.sleep(0.25)
    suffix = f": {last_error}" if last_error else ""
    raise RuntimeError(f"timed out waiting for {description}{suffix}")


def _windows_modules() -> tuple[Any, Any, Any]:
    if os.name != "nt":
        raise BlockedError("desktop probe requires Windows")
    try:
        from PIL import ImageGrab
        from pywinauto import Desktop
        from pywinauto.application import Application
    except ImportError as exc:
        raise BlockedError(f"missing Windows probe dependency: {exc.name}") from exc
    return ImageGrab, Desktop, Application


def _make_fixtures(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=False)
    fixtures: list[Path] = []
    silence = b"\x00\x00" * FIXTURE_FRAMES
    for index in range(1, EXPECTED_FIXTURE_COUNT + 1):
        path = directory / f"desktop-probe-{index:02d}.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(FIXTURE_SAMPLE_RATE)
            output.writeframes(silence)
        fixtures.append(path)
    return fixtures


def _app_environment() -> dict[str, str]:
    if os.name != "nt":
        raise BlockedError("desktop probe requires Windows")
    environment = os.environ.copy()
    system_root = Path(environment.get("SystemRoot", r"C:\Windows"))
    environment["PATH"] = str(system_root / "System32")
    for key in list(environment):
        if key.startswith(("QT_", "QML", "GST_", "MSYS", "MINGW")):
            environment.pop(key, None)
    return environment


def _notify_association_changed() -> None:
    import ctypes

    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, 0, 0)


class WindowsDesktopRun:
    def __init__(self, package: ExtractedPackage, evidence: Path, run_id: str,
                 headless_audio: bool = False) -> None:
        self.package = package
        self.evidence = evidence
        self.run_id = run_id
        self.headless_audio = headless_audio
        self.profile = shell_verb_profile(run_id, package.executable, headless_audio=headless_audio)
        self.registry_key_created = False
        self.explorer_window: Any = None
        self.player_window: Any = None
        self.fixture_directory: Path | None = None
        self.desktop: Any = None
        self.application: Any = None
        self.ImageGrab: Any = None
        self.psutil: Any = None
        self.player_process_baseline: tuple[ProcessIdentity, ...] = ()
        self.owned_player_processes: list[ProcessIdentity] = []
        self.process_cleanup_verified = False
        self.cleanup_errors: list[str] = []
        self.explorer_launch_started = False
        self.explorer_identity: tuple[int | None, str] | None = None
        self.cleanup_verified = False
        self.playlist_control_identity: dict[str, str] | None = None

    def _process_snapshot(self) -> list[tuple[Any, ProcessIdentity]]:
        records = []
        for process in self.psutil.process_iter(["pid", "create_time", "exe"]):
            try:
                info = process.info
                executable = info.get("exe")
                if executable and _normalized_executable(executable) == _normalized_executable(str(self.package.executable)):
                    records.append((process, ProcessIdentity(
                        int(info["pid"]), float(info["create_time"]), executable
                    )))
            except (OSError, KeyError, TypeError, ValueError):
                continue
        return records

    def _capture_new_player_processes(self) -> bool:
        baseline = set(self.player_process_baseline)
        current = [identity for _, identity in self._process_snapshot()]
        self.owned_player_processes = [identity for identity in current if identity not in baseline]
        return bool(self.owned_player_processes)

    def _player_processes_alive(self) -> list[ProcessIdentity]:
        current = {identity for _, identity in self._process_snapshot()}
        return [identity for identity in self.owned_player_processes if identity in current]

    def _terminate_owned_player_processes(self) -> bool:
        if not self.owned_player_processes and self.psutil is not None:
            self._capture_new_player_processes()
        if not self.owned_player_processes:
            self.process_cleanup_verified = True
            return True
        failures = []
        for identity in self.owned_player_processes:
            try:
                process = self.psutil.Process(identity.pid)
                if process_identity_matches(process, identity):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except self.psutil.TimeoutExpired:
                        if process_identity_matches(process, identity):
                            process.kill()
                            process.wait(timeout=5)
                else:
                    failures.append(f"PID {identity.pid} identity changed before termination")
            except self.psutil.NoSuchProcess:
                pass
            except Exception as exc:
                failures.append(f"PID {identity.pid}: {exc}")
        alive = self._player_processes_alive()
        if alive:
            failures.append(f"owned package processes remain: {alive!r}")
        self.cleanup_errors.extend(failures)
        self.process_cleanup_verified = not failures and not alive
        return self.process_cleanup_verified

    def preflight(self) -> None:
        try:
            import psutil
        except ImportError as exc:
            raise BlockedError(f"missing Windows process-tracking dependency: {exc.name}") from exc
        self.psutil = psutil
        self.ImageGrab, Desktop, self.application = _windows_modules()
        self.desktop = Desktop(backend="uia", allow_magic_lookup=False)
        self.player_process_baseline = tuple(identity for _, identity in self._process_snapshot())
        if self.player_process_baseline:
            raise BlockedError("packaged player already has a running process; cold launch is unsafe")
        try:
            image = self.ImageGrab.grab(all_screens=True)
        except TypeError:
            image = self.ImageGrab.grab()
        except Exception as exc:
            raise BlockedError(f"input desktop screenshot unavailable: {exc}") from exc
        screenshot = self.evidence / "desktop-preflight.png"
        _capture_image(image, screenshot)
        if not screenshot.is_file():
            raise BlockedError("input desktop screenshot could not be saved")
        try:
            windows = self.desktop.windows()
        except Exception as exc:
            raise BlockedError(f"UIA desktop is not usable: {exc}") from exc
        if not windows:
            raise BlockedError("UIA desktop returned no windows")
        try:
            self.application(backend="uia").connect(path=str(self.package.executable), timeout=1)
        except Exception:
            return
        raise BlockedError("packaged player already has a running process; cold launch is unsafe")

    def _registry_install(self) -> None:
        import winreg

        key_path = self.profile.registry_path
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
        # CreateKeyEx creates the owned parent even if entering or writing it fails.
        self.registry_key_created = True
        with key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, self.profile.label)
            winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Document")
        command_path = key_path + r"\command"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, command_path, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, self.profile.command)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            model, _ = winreg.QueryValueEx(key, "MultiSelectModel")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, command_path) as key:
            command, _ = winreg.QueryValueEx(key, "")
        if model != "Document" or command != self.profile.command:
            raise ContractError("registry shell verb read-back did not match the requested profile")
        # Tell already-running Explorer windows to refresh their association cache.
        _notify_association_changed()

    def _registry_cleanup(self) -> bool:
        if not self.registry_key_created:
            return True
        import winreg

        command_deleted = False
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self.profile.registry_path + r"\command")
            command_deleted = True
        except FileNotFoundError:
            command_deleted = True
        except OSError:
            pass
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self.profile.registry_path)
            root_deleted = True
        except FileNotFoundError:
            root_deleted = True
        except OSError:
            root_deleted = False
        if not (command_deleted and root_deleted):
            return False
        try:
            _notify_association_changed()
        except Exception:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.profile.registry_path):
                return False
        except FileNotFoundError:
            self.registry_key_created = False
            return True

    def _explorer_address_path(self, window: Any) -> str | None:
        for control in window.descendants(control_type="ToolBar"):
            name = control.window_text()
            if name.startswith("Address: "):
                return name.removeprefix("Address: ").strip().casefold()
        return None

    def _find_explorer(self) -> Any:
        name = self.fixture_directory.name if self.fixture_directory else ""
        expected_path = str(self.fixture_directory).casefold() if self.fixture_directory else ""
        for window in self.desktop.windows():
            try:
                info = window.element_info
                title = window.window_text()
                if info.class_name not in ("CabinetWClass", "ExploreWClass") or name not in title:
                    continue
                actual_path = self._explorer_address_path(window)
                if getattr(self, "evidence", None) is not None:
                    _write_json(self.evidence / "explorer-discovery.json", {
                        "expected_path": expected_path, "actual_path": actual_path,
                        "title": title, "handle": getattr(window, "handle", None),
                    })
                    _dump_uia(window, self.evidence / "explorer-discovery-uia.jsonl")
                if actual_path is None or (
                    actual_path != expected_path
                    and not os.path.samefile(actual_path, expected_path)
                ):
                    continue
                handle = getattr(window, "handle", None)
                if self.explorer_identity is not None and (
                    handle != self.explorer_identity[0]
                    or expected_path != self.explorer_identity[1]
                ):
                    continue
                if self.explorer_identity is None:
                    self.explorer_identity = (handle, expected_path)
                return window
            except Exception:
                continue
        return None

    def _find_player(self) -> Any:
        try:
            application = self.application(backend="uia").connect(
                path=str(self.package.executable), timeout=1
            )
            visible = [window for window in application.windows() if window.is_visible()]
            return visible[0] if visible else None
        except Exception:
            return None

    def _find_explorer_items_view(self) -> Any:
        matches = []
        for control in self.explorer_window.descendants(control_type="List"):
            info = control.element_info
            if (
                getattr(info, "class_name", "") == "UIItemsView"
                and getattr(info, "control_type", "List") == "List"
                and control.window_text() == "Items View"
            ):
                matches.append(control)
        if len(matches) != 1:
            raise ContractError(f"Explorer Items View count is {len(matches)}, expected one")
        return matches[0]

    def _explorer_file_rows(self, items_view: Any) -> list[Any]:
        rows = list(items_view.children(control_type="ListItem"))
        if not rows:
            raise ContractError("Explorer Items View exposed no direct file rows")
        return rows

    def _select_all_fixture_files(self) -> None:
        expected_names = sorted(path.name for path in self.fixture_directory.iterdir() if path.is_file())
        items_view = self._find_explorer_items_view()
        controls = self._explorer_file_rows(items_view)
        mapped = explorer_row_names([item.window_text() for item in controls], expected_names)
        items = dict(zip(mapped, controls))
        ordered = [items[name] for name in expected_names]
        ordered[0].click_input()
        for item in ordered[1:]:
            item.click_input(pressed="CTRL")

        def selected_names() -> list[str]:
            try:
                return [item.window_text() for item in controls if item.is_selected()]
            except Exception as exc:
                raise ContractError(f"Explorer selection state is unavailable: {exc}") from exc

        actual = selected_names()
        if len(actual) != len(controls):
            self.explorer_window.set_focus()
            self.explorer_window.type_keys("^a")
            actual = selected_names()
        if len(actual) != len(controls):
            raise ContractError(f"Explorer did not select every fixture row: {actual!r}")
        explorer_row_names(actual, expected_names)
        self.evidence.joinpath("explorer-selection.txt").write_text(
            "\n".join(sorted(actual)) + "\n", encoding="utf-8"
        )

    def _find_playlist_control(self) -> Any:
        matches = []
        for control in self.player_window.descendants(control_type="List"):
            info = control.element_info
            if (
                getattr(info, "class_name", "") == PLAYLIST_CONTROL_CLASS
                and getattr(info, "automation_id", "") == PLAYLIST_CONTROL_AUTOMATION_ID
            ):
                matches.append(control)
        if len(matches) != 1:
            raise ContractError(f"Qt playlist control count is {len(matches)}, expected one")
        self.playlist_control_identity = {
            "class_name": PLAYLIST_CONTROL_CLASS,
            "automation_id": PLAYLIST_CONTROL_AUTOMATION_ID,
        }
        return matches[0]

    def _playlist_snapshot(self) -> list[str]:
        control = self._find_playlist_control()
        return [item.window_text() for item in control.descendants(control_type="ListItem")]

    def _read_playlist_rows(self, expected: Sequence[Path]) -> list[str]:
        expected_names = [path.name for path in expected]
        observations: list[list[str]] = []
        stable_exact = 0
        deadline = time.monotonic() + PLAYLIST_STABILIZATION_TIMEOUT
        last_error: Exception | None = None
        while True:
            try:
                names = self._playlist_snapshot()
                observations.append(names)
                _write_text(
                    self.evidence / "playlist-row-observations.jsonl",
                    "".join(json.dumps(observation) + "\n" for observation in observations),
                )
                _write_text(self.evidence / "playlist-rows.txt", "\n".join(names) + "\n")
                try:
                    exact_playlist_rows(names, expected_names)
                    stable_exact += 1
                    if stable_exact >= PLAYLIST_STABLE_SNAPSHOTS:
                        return list(expected_names)
                except ContractError as exc:
                    stable_exact = 0
                    last_error = exc
            except Exception as exc:
                stable_exact = 0
                last_error = exc
            if time.monotonic() >= deadline:
                raise ContractError(
                    f"UIA playlist did not stabilize to exact rows; observations={observations!r}: {last_error}"
                ) from last_error
            time.sleep(0.25)

    def _cleanup_explorer(self) -> bool:
        if not self.explorer_launch_started:
            return True
        window = self.explorer_window or self._find_explorer()
        if window is None:
            raise RuntimeError("owned fixture Explorer window was not found for cleanup")
        window.close()
        _wait_for(lambda: self._find_explorer() is None, 10, "owned fixture Explorer window close")
        return True

    def _owned_player_windows(self) -> list[Any]:
        """Return visible windows for a currently revalidated owned player PID."""
        if not self.owned_player_processes or self.psutil is None:
            return []
        owned_pids: set[int] = set()
        for identity in self.owned_player_processes:
            try:
                process = self.psutil.Process(identity.pid)
                if process_identity_matches(process, identity):
                    owned_pids.add(identity.pid)
            except (self.psutil.NoSuchProcess, OSError, ValueError):
                continue
        if not owned_pids:
            return []

        candidates: list[Any] = []
        if self.player_window is not None:
            candidates.append(self.player_window)
        if self.desktop is None:
            raise RuntimeError("UIA desktop is unavailable while closing owned player windows")
        candidates.extend(self.desktop.windows())
        windows: list[Any] = []
        seen: set[int] = set()
        for window in candidates:
            try:
                process_id = int(getattr(window.element_info, "process_id", 0))
                if process_id not in owned_pids:
                    continue
                if hasattr(window, "is_visible") and not window.is_visible():
                    continue
                marker = getattr(window, "handle", None) or id(window)
                if marker not in seen:
                    seen.add(marker)
                    windows.append(window)
            except (AttributeError, TypeError, ValueError, OSError):
                continue
        if self.player_window in windows:
            windows.remove(self.player_window)
            windows.append(self.player_window)
        return windows

    def _cleanup_player(self) -> bool:
        cleanup_ok = True
        try:
            windows = self._owned_player_windows()
            for window in windows:
                try:
                    window.close()
                except Exception as exc:
                    self._cleanup_error("owned player window cleanup", exc)
                    cleanup_ok = False
            if windows:
                _wait_for(
                    lambda: not self._owned_player_windows(),
                    10,
                    "owned player windows close",
                )
        except Exception as exc:
            self._cleanup_error("player window cleanup", exc)
            cleanup_ok = False
        return self._terminate_owned_player_processes() and cleanup_ok

    def _cleanup_error(self, description: str, exc: Exception) -> None:
        self.cleanup_errors.append(f"{description}: {exc}")

    def _cleanup_evidence(self) -> dict[str, Any]:
        return {
            "cleanup_errors": list(self.cleanup_errors),
            "owned_player_processes": [dataclasses.asdict(identity) for identity in self.owned_player_processes],
            "preexisting_player_processes": [dataclasses.asdict(identity) for identity in self.player_process_baseline],
            "process_cleanup_verified": self.process_cleanup_verified,
            "explorer_identity": {
                "handle": self.explorer_identity[0],
                "fixture_directory": self.explorer_identity[1],
            } if self.explorer_identity else None,
            "preserved_fixture_directory": str(self.fixture_directory.parent)
            if self.fixture_directory is not None and not self.process_cleanup_verified else None,
        }

    def execute(self) -> dict[str, Any]:
        self.preflight()
        environment = _app_environment()
        temp_root = Path(tempfile.mkdtemp(prefix=f"nulloy-desktop-probe-{self.run_id}-"))
        self.fixture_directory = temp_root / f"fixtures-{self.run_id}"
        fixtures: list[Path] = []
        try:
            fixtures = _make_fixtures(self.fixture_directory)
            self._registry_install()
            explorer_process = subprocess.Popen(
                ["explorer.exe", "/n", f"/root,{self.fixture_directory}"],
                env=environment,
            )
            self.explorer_launch_started = True
            del explorer_process  # Explorer is shared and is never killed by this probe.
            self.explorer_window = _wait_for(self._find_explorer, 20, "fixture Explorer window")
            self.explorer_window.set_focus()
            _capture_image(
                self.explorer_window.capture_as_image(), self.evidence / "explorer-before.png"
            )
            self._select_all_fixture_files()
            _capture_image(
                self.explorer_window.capture_as_image(), self.evidence / "explorer-selection.png"
            )
            _dump_uia(self.explorer_window, self.evidence / "explorer-selection-uia.jsonl")
            self.explorer_window.type_keys("+{F10}")
            menu_item = _wait_for(
                lambda: next(
                    (
                        item
                        for item in self.desktop.windows()
                        for item in item.descendants(control_type="MenuItem")
                        if item.window_text() == self.profile.label
                    ),
                    None,
                ),
                10,
                "probe shell verb in Explorer context menu",
            )
            menu_item.click_input()
            _wait_for(self._capture_new_player_processes, 45, "owned packaged player process")
            self.player_window = _wait_for(self._find_player, 45, "cold packaged player window")
            _capture_image(self.player_window.capture_as_image(), self.evidence / "player.png")
            _dump_uia(self.player_window, self.evidence / "player-uia.jsonl")
            rows = self._read_playlist_rows(fixtures)
            exact_playlist_rows(rows, [path.name for path in fixtures])
            return {
                "fixture_files": [path.name for path in fixtures],
                "assertions": {
                    "three_generated_wav_files": len(fixtures) == EXPECTED_FIXTURE_COUNT,
                    "explorer_context_menu": True,
                    "playlist_rows_exact_once": True,
                },
                "app_path_environment": environment["PATH"],
                "audio_mode": self.profile.audio_mode,
                "exclusion": "audio_output_not_tested" if self.headless_audio else None,
                "playlist_control": self.playlist_control_identity,
                "shell_verb": dataclasses.asdict(self.profile),
            }
        except Exception:
            if self.explorer_window is not None:
                try:
                    _capture_image(
                        self.explorer_window.capture_as_image(), self.evidence / "explorer-failure.png"
                    )
                    _dump_uia(self.explorer_window, self.evidence / "explorer-uia.jsonl")
                except Exception:
                    pass
            if self.player_window is not None:
                try:
                    _capture_image(
                        self.player_window.capture_as_image(), self.evidence / "player-failure.png"
                    )
                    _dump_uia(self.player_window, self.evidence / "player-uia-failure.jsonl")
                except Exception:
                    pass
            raise
        finally:
            cleanup_ok = True
            try:
                cleanup_ok = self._cleanup_player() and cleanup_ok
            except Exception as exc:
                self._cleanup_error("player cleanup", exc)
                cleanup_ok = False
            try:
                cleanup_ok = self._cleanup_explorer() and cleanup_ok
            except Exception as exc:
                self._cleanup_error("Explorer cleanup", exc)
                cleanup_ok = False
            try:
                registry_ok = self._registry_cleanup()
                if not registry_ok:
                    self._cleanup_error("registry cleanup", RuntimeError("registry ownership remains"))
                cleanup_ok = registry_ok and cleanup_ok
            except Exception as exc:
                self._cleanup_error("registry cleanup", exc)
                cleanup_ok = False
            if self.process_cleanup_verified:
                try:
                    shutil.rmtree(temp_root)
                    cleanup_ok = not temp_root.exists() and cleanup_ok
                except OSError as exc:
                    self._cleanup_error("fixture directory cleanup", exc)
                    cleanup_ok = False
            else:
                self._cleanup_error("fixture directory cleanup", RuntimeError(
                    "package process cleanup was not verified; fixtures preserved"
                ))
                cleanup_ok = False
            self.cleanup_verified = cleanup_ok and self.process_cleanup_verified and not self.cleanup_errors


def run_probe(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    evidence: dict[str, Any] = {
        "status": "BLOCKED",
        "run_id": run_id,
        "package": str(args.package.resolve()),
        "source_sha_argument": args.source_sha,
        "assertions": {},
        "cleanup_verified": False,
        "audio_mode": "no-device-fallback" if args.headless_audio else "device",
        "exclusion": "audio_output_not_tested" if args.headless_audio else None,
    }
    runtime: WindowsDesktopRun | None = None
    package_temp = Path(tempfile.mkdtemp(prefix=f"package-{run_id}-"))
    try:
        source_sha = parse_source_sha(args.source_sha)
        package = extract_and_validate(args.package.resolve(), package_temp, source_sha)
        evidence.update(
            {
                "archive_sha256": package.archive_sha256,
                "executable_sha256": getattr(
                    package,
                    "executable_sha256",
                    package.contract.files[package.contract.executable],
                ),
                "manifest_executable_sha256": package.contract.files[package.contract.executable],
                "file_hashes_verified": getattr(package, "file_hashes_verified", len(package.contract.files)),
                "source_commit": package.contract.source_commit,
                "tracked_changes": False,
                "root": package.contract.root,
                "executable": package.contract.executable,
                "portable": package.contract.portable,
                "upstream_update_check": package.contract.upstream_update_check,
                "qt_major": package.contract.qt_major,
            }
        )
        runtime = WindowsDesktopRun(package, output, run_id, headless_audio=args.headless_audio)
        runtime_result = runtime.execute()
        evidence.update(runtime_result)
        evidence["cleanup_verified"] = bool(runtime.cleanup_verified)
        assertions = list(runtime_result["assertions"].values())
        evidence["status"] = verdict(assertions, runtime.cleanup_verified)
    except BlockedError as exc:
        evidence["status"] = "BLOCKED"
        evidence["error"] = str(exc)
        evidence["error_traceback"] = traceback.format_exc()
    except (ContractError, AssertionError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        evidence["status"] = "FAIL"
        evidence["error"] = str(exc)
        evidence["error_traceback"] = traceback.format_exc()
    except Exception as exc:  # keep evidence for unexpected Windows/UIA failures
        evidence["status"] = "FAIL"
        evidence["error"] = f"unexpected {type(exc).__name__}: {exc}"
        evidence["error_traceback"] = traceback.format_exc()
    finally:
        if runtime is not None:
            cleanup_evidence_failed = False
            try:
                evidence.update(runtime._cleanup_evidence())
            except Exception as exc:
                cleanup_evidence_failed = True
                evidence.setdefault("cleanup_errors", []).append(
                    f"cleanup evidence: {exc}"
                )
                evidence["cleanup_error_traceback"] = traceback.format_exc()
                evidence["status"] = "FAIL"
            evidence["cleanup_verified"] = (
                False if cleanup_evidence_failed
                else bool(getattr(runtime, "cleanup_verified", False))
            )
        preserve_package = bool(
            runtime is not None
            and runtime.owned_player_processes
            and not runtime.process_cleanup_verified
        )
        if preserve_package:
            evidence["preserved_package_path"] = str(package_temp)
        else:
            try:
                shutil.rmtree(package_temp)
            except OSError as exc:
                evidence.setdefault("cleanup_errors", []).append(
                    f"package extraction cleanup: {exc}"
                )
                evidence["cleanup_verified"] = False
                evidence["status"] = "FAIL"
                if "error" not in evidence:
                    evidence["error"] = f"package extraction cleanup failed: {exc}"
        _write_json(output / "result.json", evidence)
        _write_text(output / "status.txt", evidence["status"] + "\n")
        if "archive_sha256" in evidence:
            _write_text(output / "archive.sha256", evidence["archive_sha256"] + "\n")
        if "executable_sha256" in evidence:
            _write_text(output / "executable.sha256", evidence["executable_sha256"] + "\n")
    return (0 if evidence["status"] == "PASS" else 2 if evidence["status"] == "BLOCKED" else 1), evidence


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    code, evidence = run_probe(args)
    print(f"{evidence['status']}: {evidence.get('error', 'desktop probe completed')}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
