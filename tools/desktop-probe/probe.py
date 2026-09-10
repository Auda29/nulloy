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
import uuid
import wave
import zipfile
from typing import Any, Iterable, Sequence


SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SOURCE_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
EXPECTED_FIXTURE_COUNT = 3


class ContractError(ValueError):
    """The package, shell contract, or an exact assertion is invalid."""


class BlockedError(RuntimeError):
    """The runner cannot safely execute the desktop slice."""


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
    return parser.parse_args(argv)


def shell_command(executable: Path) -> str:
    """Return a one-file command with a hermetic app PATH, never %*."""
    executable = executable.resolve()
    # Explorer expands %1 before invoking this command.  cmd.exe sets the
    # child's PATH so an MSYS2/Qt toolchain PATH cannot satisfy app DLL loads.
    return f'cmd.exe /d /s /c "set "PATH=%SystemRoot%\\System32"&&"{executable}" "%1""'


def shell_verb_profile(run_id: str, executable: Path) -> ShellVerbProfile:
    if not re.fullmatch(r"[A-Za-z0-9-]+", run_id):
        raise ContractError("run id is not safe for a registry key")
    key_name = f"NulloyDesktopProbe-{run_id}"
    registry_path = rf"Software\Classes\SystemFileAssociations\.wav\shell\{key_name}"
    return ShellVerbProfile(
        key_name=key_name,
        registry_path=registry_path,
        label=f"Nulloy desktop probe ({run_id})",
        command=shell_command(executable),
    )


def exact_playlist_rows(actual: Sequence[str], expected: Sequence[str]) -> bool:
    """Require exactly the expected rows, with no duplicate or extra row."""
    if len(actual) != len(expected) or len(set(expected)) != len(expected):
        raise ContractError("playlist row count is not an exact unique match")
    if collections.Counter(actual) != collections.Counter(expected):
        raise ContractError(f"playlist rows differ: expected={list(expected)!r}, actual={list(actual)!r}")
    return True


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
    silence = b"\x00\x00" * 4410
    for index in range(1, EXPECTED_FIXTURE_COUNT + 1):
        path = directory / f"desktop-probe-{index:02d}.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(44100)
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


class WindowsDesktopRun:
    def __init__(self, package: ExtractedPackage, evidence: Path, run_id: str) -> None:
        self.package = package
        self.evidence = evidence
        self.run_id = run_id
        self.profile = shell_verb_profile(run_id, package.executable)
        self.registry_key_created = False
        self.explorer_window: Any = None
        self.player_window: Any = None
        self.fixture_directory: Path | None = None
        self.desktop: Any = None
        self.application: Any = None
        self.ImageGrab: Any = None

    def preflight(self) -> None:
        self.ImageGrab, Desktop, self.application = _windows_modules()
        self.desktop = Desktop(backend="uia", allow_magic_lookup=False)
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
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, self.profile.label)
            winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Document")
        self.registry_key_created = True
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
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, 0, 0)

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
        self.registry_key_created = False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.profile.registry_path):
                return False
        except FileNotFoundError:
            return True

    def _find_explorer(self) -> Any:
        name = self.fixture_directory.name if self.fixture_directory else ""
        for window in self.desktop.windows():
            try:
                info = window.element_info
                title = window.window_text()
                if info.class_name in ("CabinetWClass", "ExploreWClass") and name in title:
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

    def _select_all_fixture_files(self) -> None:
        expected_names = sorted(path.name for path in self.fixture_directory.iterdir() if path.is_file())
        controls = self.explorer_window.descendants(control_type="ListItem")
        mapped = explorer_row_names([item.window_text() for item in controls], expected_names)
        items = dict(zip(mapped, controls))
        ordered = [items[name] for name in expected_names]
        ordered[0].click_input()
        for item in ordered[1:]:
            item.click_input(pressed="CTRL")
        states: list[bool] = []
        for item in ordered:
            try:
                states.append(bool(item.is_selected()))
            except Exception:
                states = []
                break
        if states and not all(states):
            self.explorer_window.set_focus()
            self.explorer_window.type_keys("^a")
        self.evidence.joinpath("explorer-selection.txt").write_text(
            "\n".join(sorted(expected_names)) + "\n", encoding="utf-8"
        )

    def _read_playlist_rows(self, expected: Sequence[Path]) -> list[str]:
        expected_names = [path.name for path in expected]
        candidates: list[str] = []
        for control in self.player_window.descendants(control_type="List"):
            names = [item.window_text() for item in control.descendants(control_type="ListItem")]
            matches = [name for name in names if any(base in name for base in expected_names)]
            if matches:
                candidates = names
                break
        if not candidates:
            # Keep a useful artifact even when UIA exposes an unexpected control type.
            candidates = [item.window_text() for item in self.player_window.descendants(control_type="ListItem")]
        _write_text(self.evidence / "playlist-rows.txt", "\n".join(candidates) + "\n")
        normalized: list[str] = []
        for basename in expected_names:
            matches = [name for name in candidates if basename in name]
            if len(matches) != 1:
                raise ContractError(f"UIA playlist row for {basename!r}: found {len(matches)}")
            normalized.append(basename)
        if len(candidates) != len(expected_names):
            raise ContractError(
                f"UIA playlist has {len(candidates)} candidate rows, expected {len(expected_names)}"
            )
        return normalized

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
            del explorer_process  # Explorer is never killed by this probe.
            self.explorer_window = _wait_for(self._find_explorer, 20, "fixture Explorer window")
            self.explorer_window.set_focus()
            _capture_image(
                self.explorer_window.capture_as_image(), self.evidence / "explorer-before.png"
            )
            self._select_all_fixture_files()
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
            if self.player_window is not None:
                try:
                    self.player_window.close()
                    _wait_for(lambda: self._find_player() is None, 10, "owned player window close")
                except Exception:
                    cleanup_ok = False
            if self.explorer_window is not None:
                try:
                    self.explorer_window.close()
                except Exception:
                    cleanup_ok = False
            cleanup_ok = self._registry_cleanup() and cleanup_ok
            try:
                shutil.rmtree(temp_root)
                cleanup_ok = not temp_root.exists() and cleanup_ok
            except OSError:
                cleanup_ok = False
            self.cleanup_verified = cleanup_ok


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
    }
    runtime: WindowsDesktopRun | None = None
    try:
        source_sha = parse_source_sha(args.source_sha)
        with tempfile.TemporaryDirectory(prefix=f"package-{run_id}-", dir=output) as temporary:
            package = extract_and_validate(args.package.resolve(), Path(temporary), source_sha)
            evidence.update(
                {
                    "archive_sha256": package.archive_sha256,
                    "executable_sha256": package.executable_sha256,
                    "manifest_executable_sha256": package.contract.files[package.contract.executable],
                    "file_hashes_verified": package.file_hashes_verified,
                    "source_commit": package.contract.source_commit,
                    "tracked_changes": False,
                    "root": package.contract.root,
                    "executable": package.contract.executable,
                    "portable": package.contract.portable,
                    "upstream_update_check": package.contract.upstream_update_check,
                    "qt_major": package.contract.qt_major,
                }
            )
            runtime = WindowsDesktopRun(package, output, run_id)
            runtime_result = runtime.execute()
            evidence.update(runtime_result)
            evidence["cleanup_verified"] = bool(runtime.cleanup_verified)
            assertions = list(runtime_result["assertions"].values())
            evidence["status"] = verdict(assertions, runtime.cleanup_verified)
    except BlockedError as exc:
        evidence["status"] = "BLOCKED"
        evidence["error"] = str(exc)
    except (ContractError, AssertionError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        evidence["status"] = "FAIL"
        evidence["error"] = str(exc)
    except Exception as exc:  # keep evidence for unexpected Windows/UIA failures
        evidence["status"] = "FAIL"
        evidence["error"] = f"unexpected {type(exc).__name__}: {exc}"
    finally:
        if runtime is not None:
            evidence["cleanup_verified"] = bool(getattr(runtime, "cleanup_verified", False))
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
