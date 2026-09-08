#!/usr/bin/env python3
"""Encode generated sine-wave fixtures using the installed GStreamer encoders."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--prefix", required=True)
parser.add_argument("--build", required=True)
args = parser.parse_args()
prefix, build = Path(args.prefix).resolve(), Path(args.build).resolve()
output = build / "format-fixtures"
output.mkdir(exist_ok=True)
source = build / "test-run/tests/01.wav"
pipelines = {
    # Include a duration/seek header so VBR duration is known before decoding EOF.
    "mp3": ["lamemp3enc", "!", "xingmux"], "flac": ["flacenc"],
    "ogg": ["vorbisenc", "!", "oggmux"],
    "opus": ["opusenc", "!", "oggmux"], "wv": ["wavpackenc"],
}
formats = ["wav", *pipelines]
for suffix in formats:
    first = output / f"01.{suffix}"
    if suffix == "wav":
        shutil.copy2(source, first)
    else:
        pipeline = [str(prefix / "bin/gst-launch-1.0.exe"), "-q", "-e",
                    "filesrc", f"location={source.as_posix()}", "!", "wavparse", "!",
                    "audioconvert", "!", "audioresample", "!", *pipelines[suffix],
                    "!", "filesink", f"location={first.as_posix()}"]
        subprocess.run(pipeline, check=True, timeout=60)
    shutil.copy2(first, output / f"02.{suffix}")
(output / "formats.json").write_text(json.dumps(formats) + "\n")
print("Generated fixtures:", ", ".join(formats))
