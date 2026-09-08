#!/usr/bin/env python3
"""Run the actual player components from the ZIP without development DLL paths."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("--build", required=True)
parser.add_argument("--prefix", required=True)
args = parser.parse_args()
build, prefix = Path(args.build).resolve(), Path(args.prefix).resolve()
evidence = build / "package-check"
evidence.mkdir(exist_ok=True)
archive = build / "Nulloy-windows-x64.zip"
actual_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
assert actual_hash == archive.with_suffix(".zip.sha256").read_text().split()[0]
with tempfile.TemporaryDirectory(prefix="package check ä ", dir=build) as temp:
    with zipfile.ZipFile(archive) as package:
        package.extractall(temp)
    root = Path(temp) / "Nulloy"
    manifest = json.loads((root / "package-manifest.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["files"].items():
        assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == expected, filename
    shutil.copy2(build / "test-run/testPlayerPackage.exe", root)
    shutil.copy2(prefix / "bin/Qt5Test.dll", root)
    shutil.copytree(build / "test-run/tests", root / "tests")
    env = os.environ.copy()
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    for name in list(env):
        if name.startswith(("QT_", "QML", "GST_")):
            del env[name]
    env["QT_QPA_PLATFORM"] = "windows"
    env["GST_DEBUG"] = "2"
    for skin in ("Slim/0.9", "Silver/0.9", "Metro/0.9", "Native/0.9"):
        name = skin.split("/")[0].lower()
        env["NULLOY_TEST_SKIN"] = skin
        result = evidence / f"{name}-results.txt"
        cache = root / "testPlayerPackage.peaks"
        if cache.exists():
            cache.unlink()
        completed = subprocess.run([str(root / "testPlayerPackage.exe"), "-o", f"{result},txt"],
                                   cwd=temp, env=env, timeout=90, capture_output=True)
        (evidence / f"{name}-stderr.txt").write_bytes(completed.stderr)
        if (root / "render.png").exists():
            shutil.copy2(root / "render.png", evidence / f"{name}.png")
        if result.exists():
            print(result.read_text(encoding="utf-8"))
        if completed.returncode:
            raise RuntimeError(f"{skin} package workflow failed: {completed.returncode}")
    (evidence / "verified.json").write_text(json.dumps({
        "archive_sha256": actual_hash, "file_hashes_verified": len(manifest["files"]),
        "x64_binaries": len(manifest["binaries"]), "path": "Windows System32 only",
        "extraction_path": "temporary directory with spaces and umlaut",
        "skins": ["Slim/0.9", "Silver/0.9", "Metro/0.9", "Native/0.9"]
    }, indent=2) + "\n", encoding="utf-8")
