"""Harmless Qt modal fixture with an exact Cancel outcome contract.

The fixture owns only the newly-created root directory and writes benign state,
counters, and a sentinel payload. It never invokes a product, filesystem
operation, shell command, or destructive action.
"""
from __future__ import annotations

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
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

NONCE_RE = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
MAX_LIFETIME = 120.0
SENTINEL = b"modal-cancel-fixture-sentinel-v1\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--lifetime", type=float, default=60.0)
    return parser


def _validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Path:
    if not NONCE_RE.fullmatch(args.nonce):
        parser.error("nonce must contain 1-80 ASCII letters, digits, underscores or hyphens")
    if not math.isfinite(args.lifetime) or not 0 < args.lifetime <= MAX_LIFETIME:
        parser.error(f"lifetime must be finite, positive and at most {MAX_LIFETIME:g}")
    root = args.root.resolve()
    if not root.parent.is_dir():
        parser.error("root parent must already be an existing directory")
    if root.exists():
        parser.error("root must not already exist")
    return root


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = _validate(args, parser)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    (root / "sentinel.bin").write_bytes(SENTINEL)

    app = QApplication([sys.argv[0]])
    process = psutil.Process(os.getpid())
    nonce = args.nonce
    main_title = f"Modal Cancel Fixture Main {nonce}"
    dialog_title = f"Modal Cancel Fixture {nonce}"
    dialog_body = f"Benign modal cancellation test {nonce}"
    record: dict = {
        "nonce": nonce,
        "parent_pid": int(os.getppid()),
        "pid": int(process.pid),
        "create_time": float(process.create_time()),
        "executable": str(process.exe()),
        "hwnd": 0,
        "qt_version": qVersion(),
        "qt_platform": app.platformName(),
        "main_title": main_title,
        "dialog_title": dialog_title,
        "dialog_body": dialog_body,
        "heartbeat": 0,
        "phase": "starting",
        "dialog_open": False,
        "dialog_closed": False,
        "cancel_count": 0,
        "yes_count": 0,
    }
    counters = {"nonce": nonce, "cancel": 0, "yes": 0, "dialog_closed": False}
    dialog_holder: dict[str, QMessageBox | None] = {"dialog": None}
    callback_failed = False

    def publish() -> None:
        record["monotonic"] = time.monotonic()
        _atomic_json(root / "state.json", record)

    def publish_counters() -> None:
        _atomic_json(root / "counters.json", counters)

    def guarded(callback) -> None:
        nonlocal callback_failed
        if callback_failed:
            return
        try:
            callback()
        except Exception as exc:  # Qt callbacks otherwise can leave exec running.
            callback_failed = True
            record["phase"] = "failed"
            record["error"] = f"fixture callback failed: {type(exc).__name__}: {exc}"
            record["dialog_open"] = bool(dialog_holder["dialog"] and dialog_holder["dialog"].isVisible())
            try:
                publish()
                publish_counters()
            finally:
                print(record["error"], file=sys.stderr, flush=True)
                if dialog_holder["dialog"] is not None:
                    dialog_holder["dialog"].done(0)
                app.exit(1)

    window = QMainWindow()
    window.setObjectName(f"ModalCancelFixtureMain_{nonce}")
    window.setWindowTitle(main_title)
    window.resize(480, 160)
    action = QAction("Open Harmless Modal", window)
    action.setObjectName(f"OpenHarmlessModal_{nonce}")
    window.addAction(action)
    window.show()
    record["hwnd"] = int(window.winId())
    record["phase"] = "ready"
    publish()
    publish_counters()

    def open_modal() -> None:
        dialog = QMessageBox(QMessageBox.Question, dialog_title, dialog_body,
                             QMessageBox.Yes | QMessageBox.Cancel, window)
        dialog.setObjectName(f"ModalCancelDialog_{nonce}")
        dialog.setDefaultButton(QMessageBox.Cancel)
        dialog_holder["dialog"] = dialog
        record["phase"] = "dialog_open"
        record["dialog_open"] = True
        record["dialog_closed"] = False
        publish()
        if os.environ.get("MODAL_CANCEL_FIXTURE_TEST_SEAM") == "cancel":
            QTimer.singleShot(150, lambda: guarded(lambda: dialog.button(QMessageBox.Cancel).click()))
        result = dialog.exec()
        record["dialog_open"] = False
        record["dialog_closed"] = True
        counters["dialog_closed"] = True
        if result == QMessageBox.StandardButton.Cancel:
            record["cancel_count"] += 1
            counters["cancel"] += 1
            record["phase"] = "cancelled"
        elif result == QMessageBox.StandardButton.Yes:
            record["yes_count"] += 1
            counters["yes"] += 1
            record["phase"] = "yes"
        else:
            record["phase"] = "closed_without_choice"
        publish()
        publish_counters()
        # Keep the fixture alive after the choice. The owning parent performs
        # bounded cleanup; this prevents a post-invoke worker race.

    def expire() -> None:
        if record["phase"] == "complete":
            return
        record["phase"] = "expired"
        record["error"] = "fixture lifetime expired before a completed choice"
        if dialog_holder["dialog"] is not None and dialog_holder["dialog"].isVisible():
            dialog_holder["dialog"].done(0)
        record["dialog_open"] = False
        publish()
        publish_counters()
        app.exit(1)

    def tick() -> None:
        if os.environ.get("MODAL_CANCEL_FIXTURE_TEST_FAIL_CALLBACK") == "1":
            raise RuntimeError("test seam callback guard")
        record["heartbeat"] += 1
        publish()

    action.triggered.connect(lambda: guarded(open_modal))
    timer = QTimer()
    timer.timeout.connect(lambda: guarded(tick))
    timer.start(50)
    QTimer.singleShot(100, action.trigger)
    QTimer.singleShot(int(args.lifetime * 1000), lambda: guarded(expire))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
