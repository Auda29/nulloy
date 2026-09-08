#!/usr/bin/env python3
"""Inventory QtScript and Qt-internal dependencies, including bundled sources."""
import json
from pathlib import Path
import re
import sys

root, destination = map(Path, sys.argv[1:])
patterns = {
    "QtScript": re.compile(r"QScript\w*|QScriptable|qscript\w*|qScript\w*|QT\s*\+=.*\bscript\b"),
    "Qt internals": re.compile(r"Qt\w+/private/|<qpa/|QAbstractFileEngine\w*|\b(?:core|gui)-private\b|staticQtMetaObject|QPlatformNativeInterface|platformNativeInterface\("),
    "platform migration": re.compile(r"QX11Info|QDesktopWidget|nativeEvent(?:Filter)?\(|QRegExp|setIniCodec|setCodec\(|\bq[rs]rand\(|QtWin|winextras"),
}
rows = []
for folder in ("src", "3rdParty"):
    for path in sorted((root / folder).rglob("*")):
        if not path.is_file() or path.suffix not in (".h", ".cpp", ".pri", ".pro", ".js", ".patch"):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for category, pattern in patterns.items():
                if pattern.search(line):
                    rows.append(dict(category=category, file=path.relative_to(root).as_posix(), line=number, text=line.strip()))
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"{len(rows)} source locations written to {destination}")
