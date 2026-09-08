#!/usr/bin/env python3
"""Import an explicitly supplied profile copy into an unused portable profile."""
import argparse
import json
from pathlib import Path


def migrate(settings, playlist, destination, playlist_base=None):
    settings, destination = Path(settings).resolve(), Path(destination).resolve()
    info = json.loads((destination / "build-info.json").read_text(encoding="utf-8"))
    if not info.get("portable") or info.get("executable") != "NulloyFork.exe":
        raise ValueError("Destination must be an extracted NulloyFork portable package")
    data = destination / "Data"
    targets = [data / "NulloyFork.cfg", data / "NulloyFork.m3u"]
    if any(p.exists() for p in targets):
        raise ValueError("Destination already has a profile; use a fresh extraction")
    config = settings.read_bytes()
    converted = None
    if playlist:
        lines = Path(playlist).read_text(encoding="utf-8-sig").splitlines()
        converted = []
        for line in lines:
            if line.strip() and not line.startswith("#") and not Path(line).is_absolute():
                if not playlist_base:
                    raise ValueError("Relative playlist entries require --playlist-base pointing to the original playlist directory")
                line = str((Path(playlist_base).resolve() / line).resolve())
            converted.append(line)
    data.mkdir(exist_ok=True)
    # Exclusive creation prevents accidental replacement if another process starts.
    with targets[0].open("xb") as output:
        output.write(config)
    if converted is not None:
        with targets[1].open("x", encoding="utf-8") as output:
            output.write("\n".join(converted) + "\n")
    print(f"Imported profile copy into {data}; source files unchanged")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True, help="Copied .cfg file")
    parser.add_argument("--playlist", help="Copied .m3u file")
    parser.add_argument("--playlist-base", help="Original directory for relative playlist entries")
    parser.add_argument("--destination", required=True, help="Fresh extracted NulloyFork directory; player must be closed")
    args = parser.parse_args()
    migrate(args.settings, args.playlist, args.destination, args.playlist_base)
