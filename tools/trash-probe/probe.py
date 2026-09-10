#!/usr/bin/env python3
"""Real Windows UI acceptance probe for Nulloy's Move To Trash action.

The probe deliberately has no Explorer or registry integration.  It launches the
validated portable executable directly, drives only its owned Qt UI, and leaves
successful generated fixtures in the Windows recycle bin for inspection.
"""

from __future__ import annotations

import argparse
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


SOURCE_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
FIXTURE_COUNT = 3
FIXTURE_SECONDS = 10
FIXTURE_RATE = 44100
PLAYLIST_CLASS = "NPlaylistWidget"
PLAYLIST_AUTOMATION_ID = (
    "QtSingleApplication.mainWindow.borderWidget.splitter.playlistWidget"
)


class ContractError(ValueError):
    """The supplied package or an exact acceptance contract is unsafe."""


class BlockedError(RuntimeError):
    """The runner cannot safely perform native acceptance."""


@dataclasses.dataclass(frozen=True)
class PackageContract:
    root: str
    executable: str
    source_commit: str
    portable: bool
    qt_major: str
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
class Fixture:
    path: Path
    payload_sha256: str
    payload_size: int


@dataclasses.dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float
    executable: str



def status_exit_code(status: str) -> int:
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}.get(status, 1)



def parse_source_sha(value: str) -> str:
    if not isinstance(value, str) or not SOURCE_SHA_RE.fullmatch(value):
        raise ContractError("--source-sha must be exactly 40 hexadecimal characters")
    return value



def _required_string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ContractError(f"manifest field {key!r} must be a non-empty string")
    return value



def _safe_relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    reserved = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
    unsafe_part = any(
        re.search(r'[<>:"|?*\x00-\x1f]', part)
        or part.endswith((".", " "))
        or reserved.fullmatch(part)
        for part in path.parts
    )
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or path.as_posix() != value
        or value == "."
        or unsafe_part
    ):
        raise ContractError(f"unsafe {field}: {value!r}")
    return path.as_posix()



def validate_manifest(manifest: dict[str, Any], source_sha: str) -> PackageContract:
    """Validate the package metadata before any executable is started."""
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

    root = _safe_relative_path(_required_string(manifest, "root"), "root")
    if "/" in root:
        raise ContractError("manifest root must be one archive directory")
    executable = _safe_relative_path(
        _required_string(manifest, "executable"), "executable"
    )
    if not executable.lower().endswith(".exe"):
        raise ContractError("manifest executable must be an .exe")
    if manifest.get("portable") is not True:
        raise ContractError("trash acceptance requires portable=true")
    if str(manifest.get("qt_major", "")) != "6":
        raise ContractError("trash acceptance requires qt_major=6")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ContractError("manifest files must be a non-empty object")
    normalized: dict[str, str] = {}
    for filename, expected in files.items():
        safe_name = _safe_relative_path(filename, "manifest file")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise ContractError(f"manifest hash for {safe_name!r} is not SHA-256")
        normalized[safe_name] = expected.lower()
    if executable not in normalized:
        raise ContractError("manifest files does not contain the executable")
    if "build-info.json" not in normalized:
        raise ContractError("manifest files does not contain build-info.json")
    return PackageContract(root, executable, actual_source, True, "6", normalized)



def validate_archive_members(members: Iterable[str], root: str) -> None:
    """Reject traversal, aliases, and members outside the single package root."""
    root = _safe_relative_path(root, "root")
    if "/" in root:
        raise ContractError("archive root must be one directory")
    seen: set[str] = set()
    for member in members:
        if not isinstance(member, str) or not member:
            raise ContractError(f"unsafe archive member: {member!r}")
        if member.startswith(("/", "\\")):
            raise ContractError(f"unsafe archive member: {member!r}")
        name = member.rstrip("/")
        _safe_relative_path(name, "archive member")
        path = PurePosixPath(name)
        if ".." in path.parts or "\\" in member:
            raise ContractError(f"unsafe archive member: {member!r}")
        normalized = path.as_posix().casefold()
        if normalized in seen:
            raise ContractError(f"duplicate archive member: {member!r}")
        seen.add(normalized)
        if normalized != root.casefold() and not normalized.startswith(root.casefold() + "/"):
            raise ContractError(f"archive member outside package root: {member!r}")
    if (root + "/package-manifest.json").casefold() not in seen:
        raise ContractError("archive does not contain package-manifest.json")



def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()



def _validate_build_info(path: Path, contract: PackageContract) -> None:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid build-info.json: {exc}") from exc
    if not isinstance(info, dict):
        raise ContractError("build-info.json must contain an object")
    if info.get("source_commit") != contract.source_commit:
        raise ContractError("build-info source_commit does not match package-manifest.json")
    if info.get("executable") != contract.executable:
        raise ContractError("build-info executable does not match package-manifest.json")
    if info.get("portable") is not True:
        raise ContractError("build-info portable must be true")
    if info.get("tracked_changes") is not False:
        raise ContractError("build-info tracked_changes must be false")
    if "qt_major" in info and str(info["qt_major"]) != "6":
        raise ContractError("build-info qt_major is not 6")



def validate_extracted_package(
    root: Path, manifest: dict[str, Any], source_sha: str
) -> ExtractedPackage:
    contract = validate_manifest(manifest, source_sha)
    if root.name != contract.root:
        raise ContractError(f"extracted root is {root.name!r}, expected {contract.root!r}")
    for filename, expected in contract.files.items():
        path = root / filename
        if not path.is_file() or path.is_symlink():
            raise ContractError(f"manifest file is missing or linked: {filename}")
        if _sha256(path) != expected:
            raise ContractError(f"manifest hash mismatch: {filename}")
    _validate_build_info(root / "build-info.json", contract)
    executable = root / contract.executable
    actual_executable_sha = _sha256(executable)
    return ExtractedPackage(
        archive_sha256="",
        executable_sha256=actual_executable_sha,
        file_hashes_verified=len(contract.files),
        root=root,
        executable=executable,
        contract=contract,
    )



def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000



def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    for info in archive.infolist():
        if _is_zip_symlink(info):
            raise ContractError(f"ZIP symlink is not allowed: {info.filename!r}")
        relative = Path(*PurePosixPath(info.filename).parts)
        target = (destination / relative).resolve()
        if os.path.commonpath((str(destination.resolve()), str(target))) != str(destination.resolve()):
            raise ContractError(f"ZIP member escapes extraction directory: {info.filename!r}")
        if info.is_dir() or info.filename.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info, "r") as source, target.open("wb") as sink:
            shutil.copyfileobj(source, sink)



def _manifest_from_archive(package: Path, source_sha: str) -> tuple[str, dict[str, Any]]:
    if not package.is_file():
        raise ContractError(f"package does not exist: {package}")
    archive_sha = _sha256(package)
    sidecar = package.with_suffix(package.suffix + ".sha256")
    if sidecar.is_file():
        tokens = sidecar.read_text(encoding="ascii").split()
        if not tokens or tokens[0].lower() != archive_sha:
            raise ContractError("ZIP SHA-256 does not match its .sha256 sidecar")
    try:
        with zipfile.ZipFile(package) as archive:
            candidates = [
                item.filename
                for item in archive.infolist()
                if item.filename.casefold().endswith("/package-manifest.json")
            ]
            if len(candidates) != 1:
                raise ContractError("ZIP must contain exactly one package-manifest.json")
            try:
                manifest = json.loads(archive.read(candidates[0]).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ContractError("package-manifest.json is not valid JSON") from exc
            if not isinstance(manifest, dict):
                raise ContractError("package-manifest.json must contain an object")
            contract = validate_manifest(manifest, source_sha)
            validate_archive_members((item.filename for item in archive.infolist()), contract.root)
    except zipfile.BadZipFile as exc:
        raise ContractError(f"invalid ZIP: {exc}") from exc
    return archive_sha, manifest



def extract_and_validate(
    package: Path, destination: Path, source_sha: str
) -> ExtractedPackage:
    archive_sha, manifest = _manifest_from_archive(package, source_sha)
    contract = validate_manifest(manifest, source_sha)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as archive:
        _safe_extract(archive, destination)
    result = validate_extracted_package(destination / contract.root, manifest, source_sha)
    return dataclasses.replace(result, archive_sha256=archive_sha)



def make_wav_fixtures(directory: Path, run_id: str) -> list[Path]:
    """Create three unique, silent, long-enough generated WAV fixtures."""
    fixture_dir = directory / run_id
    fixture_dir.mkdir(parents=True, exist_ok=False)
    frames = b"\x00\x00" * FIXTURE_RATE * FIXTURE_SECONDS
    paths: list[Path] = []
    for index in range(1, FIXTURE_COUNT + 1):
        path = fixture_dir / f"trash-probe-{run_id}-{index:02d}.wav"
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(FIXTURE_RATE)
            output.writeframes(frames)
        paths.append(path)
    return paths



def exact_rows(actual: Sequence[str], expected: Sequence[str]) -> bool:
    if list(actual) != list(expected):
        raise ContractError(
            f"playlist rows differ: expected={list(expected)!r}, actual={list(actual)!r}"
        )
    return True



def verdict(assertions: Sequence[bool], cleanup_verified: bool) -> str:
    return "PASS" if assertions and all(assertions) and cleanup_verified else "FAIL"



def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")



def _write_step(path: Path, name: str, **data: Any) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"step": name, **data}, sort_keys=True, default=str) + "\n")



def _wait_for(predicate: Any, timeout: float, description: str) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except BlockedError:
            raise
        except Exception as exc:
            last_error = exc
        time.sleep(0.2)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"timed out waiting for {description}{detail}")



def _same_executable(first: str, second: str) -> bool:
    if os.path.abspath(first).casefold() == os.path.abspath(second).casefold():
        return True
    try:
        return os.path.samefile(first, second)
    except (OSError, ValueError):
        return False



def process_identity_matches(process: Any, identity: ProcessIdentity) -> bool:
    try:
        return (
            process.pid == identity.pid
            and float(process.create_time()) == identity.create_time
            and _same_executable(process.exe(), identity.executable)
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def recycle_metadata_original_path(raw: bytes) -> str | None:
    """Decode the original path from a Vista+ $I recycle metadata record."""
    if len(raw) < 24:
        return None
    for offset in (24, 16):
        try:
            text = raw[offset:].decode("utf-16le", errors="strict").split("\0", 1)[0]
        except UnicodeDecodeError:
            continue
        if len(text) >= 3 and (text[1] == ":" or text.startswith("\\\\")):
            return text
    return None


def _window_pid(window: Any) -> int:
    return int(getattr(window.element_info, "process_id", 0))


def _window_class(window: Any) -> str:
    return str(getattr(window.element_info, "class_name", ""))


def _window_text(window: Any) -> str:
    try:
        return str(window.window_text())
    except Exception:
        return ""


class WindowsScenario:
    def __init__(self, package_zip: Path, source_sha: str, evidence: Path, name: str):
        self.package_zip = package_zip
        self.source_sha = source_sha
        self.evidence = evidence
        self.name = name
        self.temp_root: Path | None = None
        self.package: ExtractedPackage | None = None
        self.fixtures: list[Fixture] = []
        self.process: subprocess.Popen[bytes] | None = None
        self.identity: ProcessIdentity | None = None
        self.desktop: Any = None
        self.ImageGrab: Any = None
        self.psutil: Any = None
        self.main_window: Any = None
        self.steps = evidence / "steps.jsonl"
        self.cleanup_errors: list[str] = []
        self.process_cleanup_verified = False
        self.cleanup_verified = False
        self.recycle_entries: list[dict[str, Any]] = []

    def _verify_process(self) -> None:
        if self.process is None or self.identity is None or self.psutil is None:
            raise RuntimeError("owned player process identity is not established")
        process = self.psutil.Process(self.identity.pid)
        if not process_identity_matches(process, self.identity):
            raise RuntimeError("packaged player PID/create_time/executable identity changed")
        if self.process.poll() is not None:
            raise RuntimeError(f"packaged player exited with {self.process.returncode}")

    def _owned_windows(self) -> list[Any]:
        if self.identity is None:
            return []
        return [
            window
            for window in self.desktop.windows()
            if _window_pid(window) == self.identity.pid
        ]

    def _find_main_window(self) -> Any:
        self._verify_process()
        windows = [
            window for window in self._owned_windows()
            if _window_class(window) == "NMainWindow"
            and getattr(window, "is_visible", lambda: True)()
        ]
        if len(windows) != 1:
            raise RuntimeError(f"owned NMainWindow count is {len(windows)}, expected one")
        return windows[0]

    def _dump_uia(self, window: Any, filename: str) -> None:
        records: list[dict[str, Any]] = []
        try:
            for control in [window, *window.descendants()]:
                info = control.element_info
                records.append(
                    {
                        "control_type": getattr(info, "control_type", ""),
                        "name": getattr(info, "name", ""),
                        "automation_id": getattr(info, "automation_id", ""),
                        "class_name": getattr(info, "class_name", ""),
                        "process_id": getattr(info, "process_id", ""),
                        "text": _window_text(control),
                    }
                )
        except Exception as exc:
            records.append({"dump_error": repr(exc)})
        _write_json(self.evidence / filename, records)

    def _capture_failure_evidence(self) -> None:
        try:
            if self.main_window is not None:
                self.main_window.capture_as_image().save(self.evidence / "player-failure.png")
                self._dump_uia(self.main_window, "player-failure-uia.json")
        except Exception as exc:
            _write_json(self.evidence / "player-failure-capture-error.json", {"error": repr(exc)})
        try:
            if self.ImageGrab is not None:
                self.ImageGrab.grab(all_screens=True).save(self.evidence / "desktop-failure.png")
        except Exception as exc:
            _write_json(self.evidence / "desktop-failure-capture-error.json", {"error": repr(exc)})

    def _playlist(self) -> Any:
        self._verify_process()
        if self.main_window is None:
            self.main_window = self._find_main_window()
        matches = []
        for control in self.main_window.descendants(control_type="List"):
            info = control.element_info
            if (
                getattr(info, "class_name", "") == PLAYLIST_CLASS
                and getattr(info, "automation_id", "") == PLAYLIST_AUTOMATION_ID
            ):
                matches.append(control)
        if len(matches) != 1:
            raise RuntimeError(f"Qt playlist control count is {len(matches)}, expected one")
        return matches[0]

    def _playlist_rows(self) -> list[Any]:
        return list(self._playlist().descendants(control_type="ListItem"))

    def _label_mapping(self, rows: Sequence[Any]) -> dict[str, str]:
        names = [fixture.path.name for fixture in self.fixtures]
        mapping: dict[str, str] = {}
        for row in rows:
            label = _window_text(row)
            matches = [
                name
                for name in names
                if label == name or (label.startswith(name + " (") and label.endswith(")"))
            ]
            if len(matches) != 1:
                raise ContractError(f"unknown or ambiguous visible playlist row: {label!r}")
            if matches[0] in mapping:
                raise ContractError(f"duplicate visible playlist row: {label!r}")
            mapping[matches[0]] = label
        if set(mapping) != set(names):
            raise ContractError(f"playlist did not expose exactly the generated files: {mapping!r}")
        return mapping

    def _wait_initial_playlist(self) -> dict[str, str]:
        observations: list[list[str]] = []
        def ready() -> dict[str, str] | None:
            rows = self._playlist_rows()
            labels = [_window_text(row) for row in rows]
            observations.append(labels)
            if len(rows) != FIXTURE_COUNT:
                return None
            try:
                return self._label_mapping(rows)
            except ContractError:
                return None
        try:
            mapping = _wait_for(ready, 30, "exact generated WAV playlist")
        except Exception:
            _write_json(self.evidence / "playlist-observations.json", observations)
            raise
        _write_json(self.evidence / "playlist-initial.json", mapping)
        _write_step(self.steps, "playlist_initial", rows=mapping)
        return mapping

    def _selected_names(self, rows: Sequence[Any], mapping: dict[str, str]) -> list[str]:
        result = []
        for name, label in mapping.items():
            row = next(row for row in rows if _window_text(row) == label)
            if row.is_selected():
                result.append(name)
        return [name for name in (fixture.path.name for fixture in self.fixtures) if name in result]

    def _select(self, selected: Sequence[Path], mapping: dict[str, str]) -> None:
        self._verify_process()
        playlist = self._playlist()
        rows = self._playlist_rows()
        current = self._label_mapping(rows)
        selected_names = {path.name for path in selected}
        if not selected_names or not selected_names.issubset(current):
            raise ContractError("selection is not a subset of the exact generated playlist")
        ordered = [
            row for row in rows if _window_text(row) in {current[name] for name in selected_names}
        ]
        ordered.sort(key=lambda row: [current[name] for name in selected_names].index(_window_text(row)))
        ordered[0].click_input()
        for row in ordered[1:]:
            row.click_input(pressed="control")
        actual = self._selected_names(self._playlist_rows(), current)
        exact_rows(actual, [path.name for path in selected])
        _write_step(self.steps, "playlist_selected", rows=actual)

    def _dialog_candidates(self) -> list[Any]:
        self._verify_process()
        candidates = []
        for window in self._owned_windows():
            if window is self.main_window or _window_class(window) == "NMainWindow":
                continue
            try:
                if not window.is_visible():
                    continue
                buttons = [_window_text(button) for button in window.descendants(control_type="Button")]
                title = _window_text(window)
                if title in {"Confirmation", "Trash Error", "File Delete Error"} or {
                    "Yes", "Cancel"
                }.issubset(buttons):
                    candidates.append(window)
            except Exception:
                continue
        return candidates

    def _verify_confirmation(self, expected_name: str) -> Any:
        dialogs = self._dialog_candidates()
        if len(dialogs) != 1:
            raise RuntimeError(f"owned confirmation dialog count is {len(dialogs)}, expected one")
        dialog = dialogs[0]
        title = _window_text(dialog)
        texts = [_window_text(dialog)] + [
            _window_text(control) for control in dialog.descendants()
        ]
        joined = "\n".join(texts)
        if title != "Confirmation":
            if title == "Trash Error":
                self._cancel_owned_dialog(dialog)
                raise BlockedError("player offered permanent-delete fallback after recycle failure")
            raise RuntimeError(f"unexpected owned dialog: {title!r}")
        if expected_name not in joined or any(
            fixture.path.name in joined
            for fixture in self.fixtures
            if fixture.path.name != expected_name
        ):
            raise ContractError(f"confirmation text does not name only {expected_name!r}: {joined!r}")
        button_names = [_window_text(button) for button in dialog.descendants(control_type="Button")]
        if not {"Yes", "Cancel"}.issubset(button_names):
            raise ContractError(f"confirmation buttons are not Yes/Cancel: {button_names!r}")
        cancel = dialog.child_window(title="Cancel", control_type="Button").wrapper_object()
        if not self._button_is_default(cancel):
            raise ContractError("confirmation default button is not verifiably Cancel")
        self._dump_uia(dialog, f"dialog-{expected_name}.json")
        _write_step(self.steps, "confirmation_verified", fixture=expected_name, default="Cancel")
        return dialog

    @staticmethod
    def _button_is_default(button: Any) -> bool:
        try:
            properties = button.get_properties()
            for key in ("is_default", "default", "is_default_button"):
                if properties.get(key) is True:
                    return True
        except Exception:
            pass
        try:
            if button.has_focus():
                return True
        except Exception:
            pass
        try:
            import ctypes
            handle = int(getattr(button, "handle", 0))
            if handle:
                style = ctypes.windll.user32.GetWindowLongW(handle, -16)
                return bool(style & 0x1)  # BS_DEFPUSHBUTTON
        except Exception:
            pass
        return False

    def _cancel_owned_dialog(self, dialog: Any) -> None:
        self._verify_process()
        cancel = dialog.child_window(title="Cancel", control_type="Button").wrapper_object()
        cancel.click_input()
        _wait_for(lambda: not self._dialog_candidates(), 5, "owned dialog close")

    def _drive_confirmation(self, expected_name: str, answer: str) -> None:
        dialog = _wait_for(
            lambda: self._verify_confirmation(expected_name),
            15,
            f"confirmation for {expected_name}",
        )
        self._verify_process()
        # Re-find and revalidate the exact modal immediately before clicking.
        dialog = self._verify_confirmation(expected_name)
        dialog.child_window(title=answer, control_type="Button").wrapper_object().click_input()
        _wait_for(lambda: not self._dialog_candidates(), 15, "owned confirmation dialog close")
        _write_step(self.steps, "confirmation_answered", fixture=expected_name, answer=answer)

    def _stop_and_verify(self) -> None:
        """Use the real V shortcut and verify the exposed position is reset."""
        self._verify_process()
        stop_buttons = [
            control
            for control in self.main_window.descendants(control_type="Button")
            if getattr(control.element_info, "automation_id", "") == "stopButton"
        ]
        if len(stop_buttons) != 1:
            raise ContractError(f"owned stopButton count is {len(stop_buttons)}, expected one")
        sliders = [
            control
            for control in self.main_window.descendants()
            if getattr(control.element_info, "class_name", "") == "NWaveformSlider"
            and getattr(control.element_info, "automation_id", "") == "waveformSlider"
        ]
        if len(sliders) != 1:
            raise ContractError(f"owned waveformSlider count is {len(sliders)}, expected one")
        self.main_window.set_focus()
        from pywinauto.keyboard import send_keys
        send_keys("v")

        def position() -> float | None:
            slider = sliders[0]
            try:
                return float(slider.get_value())
            except (AttributeError, TypeError, ValueError):
                try:
                    value = slider.get_properties().get("value")
                    return None if value is None else float(value)
                except (AttributeError, TypeError, ValueError):
                    return None

        samples: list[float] = []
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self._verify_process()
            value = position()
            if value is not None:
                samples.append(value)
                if abs(value) <= 1e-6 and len(samples) >= 2:
                    _write_json(self.evidence / "player-stopped.json", {
                        "shortcut": "V",
                        "stop_button_automation_id": "stopButton",
                        "waveform_slider_automation_id": "waveformSlider",
                        "position_samples": samples,
                        "verified": True,
                    })
                    _write_step(self.steps, "player_stopped", shortcut="V", position=value)
                    return
            time.sleep(0.2)
        raise ContractError(f"V did not expose a stopped zero position: {samples!r}")

    def _send_move_to_trash(self) -> None:
        self._verify_process()
        playlist = self._playlist()
        playlist.set_focus()
        from pywinauto.keyboard import send_keys
        send_keys("^({DEL})")
        _write_step(self.steps, "shortcut_sent", shortcut="Ctrl+Delete")

    def _prepare_portable_config(self, root: Path) -> None:
        data = root / "Data"
        data.mkdir(parents=True, exist_ok=True)
        config_name = self.package.executable.stem + ".cfg"
        (data / config_name).write_text(
            "SettingsVersion=0.8\n"
            "StartPaused=true\n"
            "DisplayMoveToTrashConfirmDialog=true\n"
            "RestorePlaylist=false\n"
            "SingleInstance=false\n"
            "EnqueueFiles=false\n"
            "PlayEnqueued=false\n",
            encoding="utf-8",
        )
        _write_step(self.steps, "isolated_config_written", path=str(data / config_name))

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        system_root = Path(environment.get("SystemRoot", r"C:\\Windows"))
        environment["PATH"] = str(system_root / "System32")
        for key in list(environment):
            if key.startswith(("QT_", "QML", "GST_", "MSYS", "MINGW")):
                environment.pop(key, None)
        if getattr(self, "headless_audio", False):
            environment["GST_PLUGIN_FEATURE_RANK"] = (
                "directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0"
            )
        return environment

    def _recycle_root(self, source: Path) -> Path:
        anchor = Path(source.anchor)
        root = anchor / "$Recycle.Bin"
        if not root.is_dir():
            raise BlockedError(f"Windows recycle bin root is unavailable: {root}")
        try:
            next(os.walk(root))
        except OSError as exc:
            raise BlockedError(f"Windows recycle bin cannot be inspected: {exc}") from exc
        return root

    def _find_recycle_entry(self, fixture: Fixture) -> dict[str, Any]:
        root = self._recycle_root(fixture.path)
        expected = os.path.normcase(os.path.abspath(str(fixture.path)))
        scanned = 0
        for directory, _, filenames in os.walk(root):
            for filename in filenames:
                if not filename.startswith("$I"):
                    continue
                scanned += 1
                metadata = Path(directory) / filename
                try:
                    original = recycle_metadata_original_path(metadata.read_bytes())
                except OSError:
                    continue
                if original is None or os.path.normcase(os.path.abspath(original)) != expected:
                    continue
                payload = metadata.with_name("$R" + filename[2:])
                if not payload.is_file():
                    raise ContractError(f"recycle metadata has no matching payload: {metadata}")
                actual_sha = _sha256(payload)
                if actual_sha != fixture.payload_sha256 or payload.stat().st_size != fixture.payload_size:
                    raise ContractError(f"recycle payload mismatch for {fixture.path.name}")
                entry = {
                    "metadata": str(metadata),
                    "payload": str(payload),
                    "original_path": original,
                    "payload_sha256": actual_sha,
                    "payload_size": payload.stat().st_size,
                    "metadata_bytes": metadata.stat().st_size,
                    "metadata_scanned": scanned,
                }
                _write_json(self.evidence / f"recycle-{fixture.path.stem}.json", entry)
                return entry
        raise BlockedError(
            f"no recycle-bin metadata+payload match for {fixture.path}; "
            f"scanned {scanned} metadata files under {root}"
        )

    def _verify_filesystem(self, moved: Sequence[Fixture]) -> None:
        moved_paths = {fixture.path for fixture in moved}
        for fixture in self.fixtures:
            if fixture.path in moved_paths:
                if fixture.path.exists():
                    raise ContractError(f"recycled fixture still exists at source: {fixture.path}")
                self.recycle_entries.append(self._find_recycle_entry(fixture))
            else:
                if not fixture.path.is_file():
                    raise ContractError(f"cancelled/unattempted fixture disappeared: {fixture.path}")
                if fixture.path.stat().st_size != fixture.payload_size or _sha256(fixture.path) != fixture.payload_sha256:
                    raise ContractError(f"cancelled/unattempted fixture bytes changed: {fixture.path}")
        _write_step(
            self.steps,
            "filesystem_verified",
            recycled=[fixture.path.name for fixture in moved],
            preserved=[fixture.path.name for fixture in self.fixtures if fixture not in moved],
        )

    def _launch(self) -> dict[str, str]:
        self._prepare_portable_config(self.package.root)
        environment = self._environment()
        command = [str(self.package.executable), *[str(fixture.path) for fixture in self.fixtures]]
        self.process = subprocess.Popen(command, cwd=self.package.root, env=environment)
        self.identity = ProcessIdentity(
            self.process.pid,
            float(self.psutil.Process(self.process.pid).create_time()),
            str(self.psutil.Process(self.process.pid).exe()),
        )
        if not _same_executable(self.identity.executable, str(self.package.executable)):
            raise RuntimeError("Popen executable identity does not match packaged executable")
        _write_json(self.evidence / "process-identity.json", dataclasses.asdict(self.identity))
        self.main_window = _wait_for(self._find_main_window, 45, "owned packaged NMainWindow")
        self._dump_uia(self.main_window, "player-uia.json")
        if self.ImageGrab is not None:
            try:
                self.main_window.capture_as_image().save(self.evidence / "player-before.png")
            except Exception:
                pass
        _write_step(self.steps, "packaged_player_launched", command=command, path_environment=environment["PATH"])
        return {"path": environment["PATH"], "executable": str(self.package.executable)}

    def run(self, selected_indices: Sequence[int], answers: Sequence[str]) -> dict[str, Any]:
        self.evidence.mkdir(parents=True, exist_ok=True)
        try:
            import psutil
            from PIL import ImageGrab
            from pywinauto import Desktop
        except ImportError as exc:
            raise BlockedError(f"missing Windows probe dependency: {exc.name}") from exc
        self.psutil = psutil
        self.ImageGrab = ImageGrab
        self.desktop = Desktop(backend="uia", allow_magic_lookup=False)
        self.temp_root = Path(tempfile.mkdtemp(prefix=f"nulloy-trash-{self.name}-"))
        self.package = extract_and_validate(
            self.package_zip, self.temp_root / "package-extract", self.source_sha
        )
        paths = make_wav_fixtures(self.temp_root / "fixtures", self.name + "-" + uuid.uuid4().hex[:8])
        self.fixtures = [Fixture(path, _sha256(path), path.stat().st_size) for path in paths]
        _write_json(
            self.evidence / "fixtures.json",
            [dataclasses.asdict(fixture) for fixture in self.fixtures],
        )
        environment = self._launch()
        mapping = self._wait_initial_playlist()
        self._stop_and_verify()
        self._select([self.fixtures[index].path for index in selected_indices], mapping)
        self._send_move_to_trash()
        moved: list[Fixture] = []
        for index, answer in zip(selected_indices, answers):
            fixture = self.fixtures[index]
            self._drive_confirmation(fixture.path.name, answer)
            if answer == "Yes":
                moved.append(fixture)
        self._verify_filesystem(moved)
        expected_names = [fixture.path.name for fixture in self.fixtures if fixture not in moved]
        expected_labels = [mapping[name] for name in expected_names]
        observed: list[str] = []
        def rows_ready() -> bool:
            nonlocal observed
            observed = [_window_text(row) for row in self._playlist_rows()]
            return observed == expected_labels
        _wait_for(rows_ready, 20, "exact post-action playlist rows")
        exact_rows(observed, expected_labels)
        _write_json(self.evidence / "playlist-final.json", {"rows": observed})
        _write_step(self.steps, "playlist_final_verified", rows=observed)
        return {
            "status": "PASS",
            "archive_sha256": self.package.archive_sha256,
            "executable_sha256": self.package.executable_sha256,
            "manifest_executable_sha256": self.package.contract.files[self.package.contract.executable],
            "file_hashes_verified": self.package.file_hashes_verified,
            "assertions": {
                "generated_wav_count": len(self.fixtures) == FIXTURE_COUNT,
                "shortcut_is_ctrl_delete": True,
                "filesystem_and_payloads": True,
                "playlist_rows_exact": True,
                "confirmation_default_cancel": True,
            },
            "fixture_files": [fixture.path.name for fixture in self.fixtures],
            "recycled_files": [fixture.path.name for fixture in moved],
            "preserved_files": [fixture.path.name for fixture in self.fixtures if fixture not in moved],
            "recycle_entries": self.recycle_entries,
            "player": environment,
            "audio_exclusion": "audio output is not tested; headless rank is explicit only",
        }

    def _cleanup_player(self) -> bool:
        if self.process is None or self.identity is None:
            self.process_cleanup_verified = True
            return True
        try:
            if self.process.poll() is None:
                self._verify_process()
                if self.main_window is not None:
                    self.main_window.close()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._verify_process()
                    self.process.terminate()
                    self.process.wait(timeout=10)
            if self.process.poll() is not None:
                self.process_cleanup_verified = True
                return True
        except Exception as exc:
            self.cleanup_errors.append(f"player cleanup: {exc}")
        self.process_cleanup_verified = False
        return False

    def cleanup(self) -> dict[str, Any]:
        player_ok = self._cleanup_player()
        if not player_ok:
            self.cleanup_errors.append("generated package/fixtures preserved because player cleanup was not verified")
        elif self.temp_root is not None:
            try:
                shutil.rmtree(self.temp_root)
            except OSError as exc:
                self.cleanup_errors.append(f"generated package/fixtures cleanup: {exc}")
        self.cleanup_verified = player_ok and not self.cleanup_errors
        result = {
            "cleanup_verified": self.cleanup_verified,
            "process_cleanup_verified": self.process_cleanup_verified,
            "cleanup_errors": list(self.cleanup_errors),
            "preserved_temp_root": str(self.temp_root) if not self.cleanup_verified else None,
        }
        _write_json(self.evidence / "cleanup.json", result)
        return result


SCENARIOS = (
    ("ordinary-cancellation", (0,), ("Cancel",)),
    ("successful-recycling", (0,), ("Yes",)),
    ("partial-batch-cancellation", (0, 1, 2), ("Yes", "Cancel")),
)



def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True, help="packaged portable Windows ZIP")
    parser.add_argument("--source-sha", required=True, help="exact 40-character source SHA")
    parser.add_argument("--output", type=Path, required=True, help="evidence directory")
    parser.add_argument(
        "--headless-audio",
        action="store_true",
        help="explicitly rank device sinks below no-device fallback; audio is not accepted",
    )
    return parser.parse_args(argv)



def run_probe(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    result: dict[str, Any] = {
        "status": "BLOCKED",
        "run_id": run_id,
        "package": str(args.package.resolve()),
        "source_sha_argument": args.source_sha,
        "execution_started": False,
        "cleanup_verified": False,
        "audio_mode": "headless-no-device-fallback" if args.headless_audio else "normal",
        "scenarios": {},
    }
    if os.name != "nt":
        result["error"] = "Windows native acceptance requires Windows; execution was not started"
        _write_json(output / "result.json", result)
        (output / "status.txt").write_text("BLOCKED\n", encoding="utf-8")
        return 2, result

    try:
        source_sha = parse_source_sha(args.source_sha)
        archive_sha, manifest = _manifest_from_archive(args.package.resolve(), source_sha)
        contract = validate_manifest(manifest, source_sha)
        validation_root = Path(tempfile.mkdtemp(prefix=f"trash-package-{run_id}-"))
        try:
            validated_package = extract_and_validate(
                args.package.resolve(), validation_root, source_sha
            )
        finally:
            shutil.rmtree(validation_root, ignore_errors=True)
        result.update(
            {
                "archive_sha256": archive_sha,
                "executable_sha256": validated_package.executable_sha256,
                "source_commit": contract.source_commit,
                "tracked_changes": False,
                "root": contract.root,
                "executable": contract.executable,
                "portable": True,
                "qt_major": "6",
                "manifest_executable_sha256": contract.files[contract.executable],
                "file_hashes_expected": len(contract.files),
            }
        )
        scenario_data: dict[str, Any] = {}
        blocked = False
        failed = False
        for scenario_name, selected, answers in SCENARIOS:
            scenario = WindowsScenario(
                args.package.resolve(), source_sha, output / scenario_name, scenario_name
            )
            scenario.headless_audio = bool(args.headless_audio)
            primary_error: str | None = None
            try:
                data = scenario.run(selected, answers)
                scenario_data[scenario_name] = data
            except BlockedError as exc:
                blocked = True
                primary_error = str(exc)
                scenario_data[scenario_name] = {"status": "BLOCKED", "error": primary_error}
            except Exception as exc:
                failed = True
                primary_error = f"{type(exc).__name__}: {exc}"
                scenario._capture_failure_evidence()
                scenario_data[scenario_name] = {
                    "status": "FAIL",
                    "error": primary_error,
                    "traceback": traceback.format_exc(),
                }
            finally:
                cleanup = scenario.cleanup()
                scenario_data[scenario_name].update(cleanup)
                result["execution_started"] = bool(
                    result["execution_started"] or scenario.process is not None
                )
                if not cleanup["cleanup_verified"]:
                    failed = True
        result["scenarios"] = scenario_data
        result["cleanup_verified"] = all(
            bool(data.get("cleanup_verified")) for data in scenario_data.values()
        )
        if failed:
            result["status"] = "FAIL"
        elif blocked:
            result["status"] = "BLOCKED"
        else:
            assertions = [
                data.get("status") == "PASS"
                and all(data.get("assertions", {}).values())
                for data in scenario_data.values()
            ]
            result["status"] = verdict(assertions, result["cleanup_verified"])
    except BlockedError as exc:
        result["status"] = "BLOCKED"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
    except (ContractError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        result["status"] = "FAIL"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
    except Exception as exc:
        result["status"] = "FAIL"
        result["error"] = f"unexpected {type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
    result["cleanup_verified"] = bool(result.get("cleanup_verified", False))
    _write_json(output / "result.json", result)
    (output / "status.txt").write_text(result["status"] + "\n", encoding="utf-8")
    if result.get("archive_sha256"):
        (output / "archive.sha256").write_text(result["archive_sha256"] + "\n", encoding="ascii")
    if result.get("executable_sha256"):
        (output / "executable.sha256").write_text(result["executable_sha256"] + "\n", encoding="ascii")
    return status_exit_code(result["status"]), result



def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    code, result = run_probe(args)
    print(f"{result['status']}: {result.get('error', 'trash probe completed')}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
