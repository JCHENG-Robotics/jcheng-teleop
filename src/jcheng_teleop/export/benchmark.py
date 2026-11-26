"""Export a capture to the benchmark JSONL dataset shape (jcheng-benchmark).

The exporter writes one row per motion action. It maps the capture environment
to the benchmark's data-source vocabulary and never upgrades mock or simulation
data: only a hardware capture becomes `recorded`.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ..capture.writer import assert_outside_git

DATA_SOURCE = {"hardware": "recorded", "simulation": "synthetic", "mock": "mock"}
_LEVEL = {"hardware": "L4", "simulation": "L3", "mock": "L2"}


def benchmark_rows(streams: dict[str, list[dict[str, Any]]], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    environment = str(manifest.get("environment", {}).get("environment_class", ""))
    if environment not in DATA_SOURCE:
        raise ValueError(f"unsupported environment_class: {environment!r}")
    source = DATA_SOURCE[environment]
    capture_id = str(manifest.get("capture_id", ""))
    limit_ticks = {
        row.get("tick_id")
        for row in streams.get("events", [])
        if "LIMIT" in str(row.get("code", ""))
    }
    rows: list[dict[str, Any]] = []
    for action in streams.get("action", []):
        if action.get("purpose") == "stop":
            continue
        tick = action.get("tick_id")
        velocities = [float(item) for item in action.get("joint_velocities_rad_s", [])]
        positions = [float(item) for item in action.get("joint_positions_rad", [])]
        speed = math.sqrt(sum(value * value for value in velocities)) if velocities else 0.0
        zero = bool(velocities or positions) and all(
            value == 0.0 for value in (*velocities, *positions)
        )
        rows.append(
            {
                "sample_id": f"{capture_id}:{tick}",
                "trial": capture_id,
                "speed_rad_s": round(speed, 6),
                "deadman": bool(action.get("deadman", False)),
                "limit_event": tick in limit_ticks,
                "zero_command": zero,
                "mode": action.get("mode"),
                "environment_class": environment,
                "data_source": source,
                "capture_id": capture_id,
            }
        )
    return rows


def write_benchmark(
    streams: dict[str, list[dict[str, Any]]],
    manifest: dict[str, Any],
    path: str | Path,
) -> dict[str, Any]:
    output = Path(path).expanduser().resolve()
    assert_outside_git(output)
    rows = benchmark_rows(streams, manifest)
    text = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return {
        "path": str(output),
        "rows": len(rows),
        "bytes": len(text.encode("utf-8")),
        "sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "data_source": rows[0]["data_source"] if rows else None,
        "level": _LEVEL.get(str(manifest.get("environment", {}).get("environment_class", ""))),
    }
