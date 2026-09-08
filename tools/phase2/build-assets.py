#!/usr/bin/env python3
"""Generate skin archives and deterministic audio fixtures outside the source tree."""
import math
from pathlib import Path
import shutil
import struct
import sys
import wave
import zipfile

mode, source, output = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
output.mkdir(parents=True, exist_ok=True)
if mode == "skins":
    for name in ("Slim", "Silver", "Metro"):
        with zipfile.ZipFile(output / f"{name}.nzs", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted((source / name.lower()).iterdir()):
                if path.is_file() and path.name != "design.svg":
                    info = zipfile.ZipInfo(path.name, date_time=(2024, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, path.read_bytes())
elif mode == "tests":
    # Same 10-second, 44.1 kHz input duration as the original gst-launch fixture.
    samples = b"".join(struct.pack("<h", int(1000 * math.sin(2 * math.pi * 440 * i / 44100))) for i in range(441000))
    with wave.open(str(output / "01.wav"), "wb") as audio:
        audio.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        audio.writeframes(samples)
    for i in range(2, 11):
        shutil.copyfile(output / "01.wav", output / f"{i:02}.wav")
    shutil.copyfile(source / "playlist.m3u", output / "playlist.m3u")
else:
    raise SystemExit(f"Unknown mode: {mode}")
