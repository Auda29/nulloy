"""Helpers built from the retained native Qt observation capture."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CAPTURE = json.loads((HERE / "fixtures" / "qt682-native-observation.json").read_text(encoding="utf-8"))
_CAPTURE_NONCE = CAPTURE["nonce"]


def _replace_nonce(value: Any, nonce: str) -> Any:
    if type(value) is str:
        return value.replace(_CAPTURE_NONCE, nonce)
    if isinstance(value, list):
        return [_replace_nonce(item, nonce) for item in value]
    if isinstance(value, dict):
        return {key: _replace_nonce(item, nonce) for key, item in value.items()}
    return value


def native_observations(*, nonce: str, pid: int, root_hwnd: int, dialog_hwnd: int) -> dict[str, Any]:
    """Return a typed observation snapshot derived only from the real capture."""
    observations = _replace_nonce(copy.deepcopy(CAPTURE["observations"]), nonce)
    for record in (observations["root"], observations["dialog"], observations["body"],
                   observations["buttons"]["Cancel"], observations["buttons"]["Yes"]):
        record["pid"] = pid
        record["process_id"] = pid
    observations["root"]["hwnd"] = root_hwnd
    observations["root"]["native_owner_pid"] = pid
    observations["dialog"]["hwnd"] = dialog_hwnd
    observations["dialog"]["native_owner_pid"] = pid
    return observations
