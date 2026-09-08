#!/usr/bin/env python3
"""Aggregate measured JSONL from a successful full testWaveform139 run."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def summarize(rows):
    expected = {"environment": 1, "complete": 12, "cache-save": 100,
                "cache-load": 3, "cancel": 50, "close": 50, "rename": 1, "unlink": 1}
    actual = Counter(row["kind"] for row in rows)
    if dict(actual) != expected:
        raise ValueError(f"Incomplete full run: expected {expected}, got {dict(actual)}")
    result = {"rows": len(rows), "counts": dict(actual), "environment": rows[0]}
    result["completion"] = [row for row in rows if row["kind"] == "complete"]
    result["cache_checkpoints"] = [row for row in rows
                                   if row["kind"] in ("cache-save", "cache-load")
                                   and row["entries"] in (1, 10, 100)]
    for kind, field in (("cancel", "stop_ms"), ("close", "close_ms")):
        values = [row[field] for row in rows if row["kind"] == kind]
        result[kind] = {"count": len(values), "min_ms": min(values),
                        "median_ms": statistics.median(values), "max_ms": max(values)}
    result["filesystem"] = [row for row in rows if row["kind"] in ("rename", "unlink")]
    hwm = [row["process_hwm_kib"] for row in rows if "process_hwm_kib" in row]
    if hwm:
        result["process_hwm_kib"] = max(hwm)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.metrics.read_text().splitlines() if line.strip()]
    print(json.dumps(summarize(records), indent=2))
