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
parser.add_argument("--media", nargs=2, help="Optional private media copies for a Slim reference run")
parser.add_argument("--headless-audio", action="store_true", help="Use GStreamer's no-device fallback on CI")
parser.add_argument("--repeat", type=int, choices=range(1, 11), default=1,
                    help="Repeat each skin in the same extraction to distinguish cold and warm starts")
parser.add_argument("--scale", type=float, choices=(1, 1.5, 2), help="Explicit Qt scale factor for UI comparison")
args = parser.parse_args()
build, prefix = Path(args.build).resolve(), Path(args.prefix).resolve()
evidence = build / ("private-media-check" if args.media else "package-check")
if args.scale:
    evidence = evidence.with_name(evidence.name + f"-scale-{args.scale:g}")
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
    qt_major = manifest.get("qt_major", "5")
    shutil.copy2(prefix / f"bin/Qt{qt_major}Test.dll", root)
    shutil.copytree(build / "test-run/tests", root / "tests")
    env = os.environ.copy()
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    for name in list(env):
        if name.startswith(("QT_", "QML", "GST_")):
            del env[name]
    env["QT_QPA_PLATFORM"] = "windows"
    if args.scale:
        env["QT_SCALE_FACTOR"] = str(args.scale)
    env["GST_DEBUG"] = "2"
    if args.headless_audio:
        env["GST_PLUGIN_FEATURE_RANK"] = "directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0"
    version = subprocess.run([str(root / "Nulloy.exe"), "--version"], cwd=temp, env=env,
                             timeout=30, capture_output=True, check=True)
    assert version.stdout.strip(), "The packaged executable did not report its version"
    (evidence / "version.txt").write_bytes(version.stdout)
    skins = ("Slim/0.9",) if args.media else ("Slim/0.9", "Silver/0.9", "Metro/0.9", "Native/0.9")
    if args.media:
        media = []
        for index, filename in enumerate(args.media):
            destination = root / "tests" / f"reference-{index + 1}{Path(filename).suffix}"
            shutil.copy2(filename, destination)
            media.append(destination.as_posix())
        env["NULLOY_TEST_MEDIA"] = "|".join(media)
    else:
        env.pop("NULLOY_TEST_MEDIA", None)
    for skin, attempt in ((skin, attempt) for skin in skins for attempt in range(args.repeat)):
        name = skin.split("/")[0].lower() + (f"-{attempt + 1}" if args.repeat > 1 else "")
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
            log = result.read_text(encoding="utf-8")
            print(log)
            for marker in ("QtScript:", "unknown user type with name QJSValue", "save a non-trivial QJSValue"):
                if marker in log:
                    raise RuntimeError(f"{skin} script or persistence error: {marker}")
        if completed.returncode:
            raise RuntimeError(f"{skin} package workflow failed: {completed.returncode}")
    (evidence / "verified.json").write_text(json.dumps({
        "archive_sha256": actual_hash, "file_hashes_verified": len(manifest["files"]),
        "x64_binaries": len(manifest["binaries"]), "path": "Windows System32 only",
        "extraction_path": "temporary directory with spaces and umlaut",
        "audio": "GStreamer no-device fallback" if args.headless_audio else "normal device selection, muted",
        "skins": skins, "repetitions_per_skin": args.repeat, "qt_major": qt_major,
        "explicit_scale_factor": args.scale
    }, indent=2) + "\n", encoding="utf-8")
