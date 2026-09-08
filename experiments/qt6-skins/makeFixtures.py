#!/usr/bin/env python3
"""Build disposable ZIP fixtures with Python's independent standard ZIP writer."""
import io
from pathlib import Path
import shutil
import sys
import zipfile
import wave

source, output, font = map(Path, sys.argv[1:])
output.mkdir(parents=True, exist_ok=True)
for skin in ("slim", "native", "silver", "metro"):
    for method, label in ((zipfile.ZIP_STORED, "stored"), (zipfile.ZIP_DEFLATED, "deflated")):
        with zipfile.ZipFile(output / f"{skin}-{label}.nzs", "w", compression=method) as archive:
            for path in sorted((source / skin).rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(source / skin).as_posix())

# Nonseekable output makes zipfile produce local data descriptors.
class Nonseekable(io.BytesIO):
    def seek(self, *args):
        raise io.UnsupportedOperation()

stream = Nonseekable()
with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name in ("form.ui", "script.js", "id.txt"):
        archive.write(source / "slim" / name, name)
(output / "descriptor.nzs").write_bytes(stream.getvalue())
with zipfile.ZipFile(output / "traversal.nzs", "w") as archive:
    archive.writestr("../escaped.txt", "must never escape")
with zipfile.ZipFile(output / "duplicate.nzs", "w") as archive:
    archive.writestr("test.txt", "one")
    archive.writestr("TEST.txt", "two")
with zipfile.ZipFile(output / "nested.nzs", "w") as archive:
    for name in ("form.ui", "script.js", "id.txt"):
        archive.write(source / "slim" / name, name)
    archive.writestr("images/nested.txt", "nested resource ä")
corrupt = bytearray((output / "slim-stored.nzs").read_bytes())
corrupt[100] ^= 0x42
(output / "corrupt.nzs").write_bytes(corrupt)
shutil.copyfile(font, output / "fixture.ttf")
tracks = output.parent / "tests"
tracks.mkdir(exist_ok=True)
with wave.open(str(tracks / "01.wav"), "wb") as audio:
    audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
    audio.writeframes(b"\0\0" * 8000)
