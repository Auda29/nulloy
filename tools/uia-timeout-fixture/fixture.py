"""Harmless, independently observable Qt target. No input or menu actions."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import time

import psutil
from PySide6.QtCore import QTimer, qVersion
from PySide6.QtWidgets import QApplication, QLabel


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--lifetime", type=float, default=60)
    parser.add_argument("--block-seconds", type=float, default=1)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.nonce):
        parser.error("nonce must contain 1-80 ASCII letters, digits, underscores or hyphens")
    for name, maximum in (("lifetime", 120), ("block_seconds", 90)):
        value = getattr(args, name)
        if not math.isfinite(value) or not 0 < value <= maximum:
            parser.error(f"{name} must be finite, positive and at most {maximum}")
    args.root = args.root.resolve()
    args.root.mkdir(mode=0o700, parents=False, exist_ok=False)
    app = QApplication([sys.argv[0]])
    window = QLabel(f"Harmless UIA heartbeat {args.nonce}")
    window.setObjectName(f"UIATimeoutFixture_{args.nonce}")
    window.setWindowTitle(f"UIA Timeout Fixture {args.nonce}")
    window.resize(400, 100)
    window.show()
    process = psutil.Process(os.getpid())
    record = {
        "nonce": args.nonce, "pid": process.pid,
        "create_time": process.create_time(), "executable": process.exe(),
        "hwnd": int(window.winId()), "qt_version": qVersion(),
        "qt_platform": app.platformName(), "heartbeat": 0,
        "phase": "responsive",
    }

    def publish():
        record["monotonic"] = time.monotonic()
        temporary = args.root / "state.tmp"
        temporary.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        temporary.replace(args.root / "state.json")

    def tick():
        record["heartbeat"] += 1
        publish()
        request = args.root / "block-request.json"
        if request.exists() and not record.get("block_count"):
            value = json.loads(request.read_text(encoding="utf-8"))
            if value != {"nonce": args.nonce}:
                raise ValueError("request nonce/shape mismatch")
            record["block_count"] = 1
            record["phase"] = "blocked"
            publish()
            started = time.monotonic()
            time.sleep(args.block_seconds)  # Blocks THIS fixture's GUI thread only.
            record["block_elapsed"] = time.monotonic() - started
            record["phase"] = "responsive"
            publish()

    def finish():
        record["phase"] = "complete"
        publish()
        app.quit()

    def guarded(callback):
        try:
            callback()
        except Exception as exc:
            record["phase"] = "failed"
            record["error"] = f"fixture callback/request failed: {type(exc).__name__}: {exc}"
            print(record["error"], file=sys.stderr, flush=True)
            try:
                publish()
            except Exception as diagnostic_error:
                print(f"diagnostic write failed: {diagnostic_error}", file=sys.stderr, flush=True)
            app.exit(1)

    timer = QTimer()
    timer.timeout.connect(lambda: guarded(tick))
    timer.start(50)
    QTimer.singleShot(int(args.lifetime * 1000), lambda: guarded(finish))
    publish()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
