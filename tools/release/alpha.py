#!/usr/bin/env python3
"""Validate an alpha tag and publish only the package verified by the same run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / ".phase4/release-input"
OUTPUT = ROOT / ".phase4/release-output"


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version_from_tag(tag, presets):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+-alpha\.[1-9][0-9]*", tag):
        raise ValueError("Expected an alpha tag such as v0.10.0-alpha.1")
    preset = next(p for p in presets["configurePresets"] if p["name"] == "windows-portable-x64")
    version = preset["cacheVariables"]["NULLOY_VERSION"]
    if tag != "v" + version:
        raise ValueError(f"Tag {tag} does not match portable preset version {version}")
    return version


def validate():
    if os.environ.get("GITHUB_REF_TYPE") != "tag":
        raise ValueError("Release workflow requires a tag push")
    tag = os.environ["GITHUB_REF_NAME"]
    version = version_from_tag(tag, json.loads((ROOT / "CMakePresets.json").read_text()))
    commit = run("git", "rev-parse", "HEAD")
    if commit != os.environ["GITHUB_SHA"]:
        raise ValueError("Checkout does not match the triggering commit")
    if run("git", "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Release source contains tracked changes")
    return tag, version, commit


def verify_package(package, version, commit, evidence):
    digest = sha256(package)
    if package.with_suffix(".zip.sha256").read_text().split()[0] != digest:
        raise ValueError("Package checksum mismatch")
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("NulloyFork/package-manifest.json"))
        if (manifest["source_commit"] != commit or manifest["version"] != version
                or manifest["tracked_changes"] or not manifest["portable"]
                or manifest["upstream_update_check"] or manifest["qt_major"] != "6"):
            raise ValueError("Package provenance/version/options mismatch")
        for name, expected in manifest["files"].items():
            if hashlib.sha256(archive.read("NulloyFork/" + name)).hexdigest() != expected:
                raise ValueError(f"Package file checksum mismatch: {name}")
    checks = {}
    for folder in ("package-check", "format-check", "startup-check", "startup-check-missing",
                   "startup-check-corrupt", "startup-check-changed-plugin"):
        # Artifact upload roots also include the shared skin probe, so build paths
        # may be retained by upload-artifact's least common ancestor calculation.
        matches = list(evidence.rglob(folder + "/verified.json"))
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one successful {folder} report")
        report = json.loads(matches[0].read_text())
        if report["archive_sha256"] != digest or report["qt_major"] != "6":
            raise ValueError(f"{folder} was run against a different package")
        checks[folder] = report
    if set(checks["format-check"]["formats"]) != {"wav", "mp3", "flac", "ogg", "opus", "wv"}:
        raise ValueError("Incomplete audio format verification")
    if not checks["format-check"]["unicode_tag_roundtrip"]:
        raise ValueError("Unicode tag verification missing")
    for name in ("package-check", "startup-check"):
        report = checks[name]
        if len(report["skins"]) != 4 or not report["portable_process_isolation"]:
            raise ValueError(f"{name} lacks skin/process verification")
    return digest, manifest, checks


def prepare():
    tag, version, commit = validate()
    package = INPUT / "package" / f"NulloyFork-{version}-windows-x64.zip"
    digest, manifest, checks = verify_package(package, version, commit, INPUT / "evidence")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    shutil.copy2(package, OUTPUT)
    shutil.copy2(package.with_suffix(".zip.sha256"), OUTPUT)
    source = OUTPUT / f"NulloyFork-{version}-source.zip"
    subprocess.run(["git", "archive", "--format=zip", f"--prefix=NulloyFork-{version}/",
                    f"--output={source}", "HEAD"], cwd=ROOT, check=True)
    shutil.make_archive(str(OUTPUT / f"NulloyFork-{version}-test-evidence"), "zip", INPUT / "evidence")
    report = {"tag": tag, "version": version, "source_commit": commit,
              "workflow_url": os.environ["RELEASE_RUN_URL"], "archive_sha256": digest,
              "verified_files": len(manifest["files"]), "x64_binaries": len(manifest["binaries"]),
              "package_checks": checks,
              "limitations": ["Alpha Windows x64 build; no installer or automatic fork updates",
                              "CI audio tests use the no-device fallback",
                              "Separate Windows machine without development tools not yet confirmed",
                              "User acceptance covered the earlier local Phase 4 package, not this CI binary"]}
    (OUTPUT / "release-validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sums = "".join(f"{sha256(p)}  {p.name}\n" for p in sorted(OUTPUT.iterdir()))
    (OUTPUT / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    notes = f"""# NulloyFork {version}

Erste Alpha des Community-Forks für Windows x64 mit Qt 6. Die bisherigen Skins und
Bedienelemente bleiben erhalten. Das portable Paket nutzt einen eigenen `Data`-Ordner
und einen vorbereiteten GStreamer-Cache für schnellere Erststarts.

**Start:** `NulloyFork-{version}-windows-x64.zip` vollständig in einen beschreibbaren
Ordner entpacken und `NulloyFork.exe` starten. Eigene Tracks per Drag-and-drop hinzufügen.
Vorhandene Installationen und Profile werden nicht automatisch übernommen.

Qt-5-Vergleich und Qt-6-Build, vier Skins, sechs Audioformate, Unicode-Tags,
Instanztrennung und Cache-Wiederherstellung wurden im [Release-Workflow]({os.environ['RELEASE_RUN_URL']}) geprüft.
Quellstand: `{commit}`. Prüfsummen stehen in `SHA256SUMS.txt`;
`release-validation.json` ordnet die Prüfungen diesem Download zu.

Diese Alpha hat keinen Installer und keine automatischen Fork-Updates. Ein Test auf
einem separaten Windows-Rechner ohne Entwicklungswerkzeuge steht aus. Die manuelle
Phase-4-Abnahme betraf das lokale Vorgängerpaket; dieses Download-Paket wurde in CI gebaut.
Der enthaltene Phase-4-Bericht dokumentiert diese frühere lokale Prüfung. Fehlende,
veraltete oder beschädigte GStreamer-Caches können weiterhin einen längeren Start verursachen.

GPL- und Drittanbieter-Lizenztexte sind im Paket enthalten. Der Quellcode dieses
Tags liegt als Source-ZIP bei; MSYS2-Abhängigkeiten und Quellenhinweise stehen im Paket.
"""
    (ROOT / ".phase4/release-notes.md").write_text(notes, encoding="utf-8")


def publish():
    tag, version, _ = validate()
    assets = sorted(str(p) for p in OUTPUT.iterdir() if p.is_file())
    # Create as a draft so no partially uploaded asset set is published.
    subprocess.run(["gh", "release", "create", tag, *assets, "--verify-tag", "--draft",
                    "--prerelease", "--title", f"NulloyFork {version}",
                    "--notes-file", str(ROOT / ".phase4/release-notes.md")], cwd=ROOT, check=True)
    release = json.loads(run("gh", "release", "view", tag, "--json", "assets,isDraft,isPrerelease"))
    if not release["isDraft"] or not release["isPrerelease"]:
        raise ValueError("Expected an unpublished prerelease")
    if {a["name"] for a in release["assets"]} != {Path(p).name for p in assets}:
        raise ValueError("Uploaded asset set differs from verified files")
    subprocess.run(["gh", "release", "edit", tag, "--draft=false", "--prerelease", "--latest=false"],
                   cwd=ROOT, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "prepare", "publish"))
    globals()[parser.parse_args().command]()
