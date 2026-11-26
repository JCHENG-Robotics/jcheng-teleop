"""Quality metrics over a capture, for replay reports.

Metrics are descriptive, not a safety certification. They never change a
capture and never replace a failed bound with a more favourable statistic.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Any


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def _summary(values: list[float], *, unit_scale: float = 1.0) -> dict[str, float]:
    scaled = [value * unit_scale for value in values]
    return {
        "count": len(scaled),
        "p50": round(_percentile(scaled, 0.50), 3),
        "p95": round(_percentile(scaled, 0.95), 3),
        "p99": round(_percentile(scaled, 0.99), 3),
        "max": round(max(scaled), 3) if scaled else 0.0,
    }


def compute_metrics(
    streams: dict[str, list[dict[str, Any]]], manifest: dict[str, Any]
) -> dict[str, Any]:
    tick_ms = float(manifest.get("time", {}).get("tick_ms", 20))
    tick_ns = int(tick_ms * 1_000_000)
    actions = streams.get("action", [])
    observations = streams.get("observation", [])
    events = streams.get("events", [])

    jitter_ms: list[float] = []
    times = [row["t_mono_ns"] for row in actions if isinstance(row.get("t_mono_ns"), int)]
    for before, after in zip(times, times[1:]):
        delta = after - before
        jitter_ms.append(abs(delta - tick_ns) / 1_000_000.0)

    obs_times = sorted(
        row["t_received_ns"]
        for row in observations
        if isinstance(row.get("t_received_ns"), int)
    )
    skew_ms: list[float] = []
    if obs_times and times:
        for received in obs_times:
            position = bisect_left(times, received)
            candidates = []
            if position < len(times):
                candidates.append(times[position])
            if position > 0:
                candidates.append(times[position - 1])
            nearest = min(candidates, key=lambda value: abs(value - received))
            skew_ms.append(abs(received - nearest) / 1_000_000.0)

    limit_events = sum(1 for row in events if "LIMIT" in str(row.get("code", "")))
    deadman_releases = sum(
        1
        for row in events
        if str(row.get("code", "")).startswith("DEADMAN_RELEASE")
    )
    stop_intents = sum(1 for row in actions if row.get("purpose") == "stop")
    motion = [row for row in actions if row.get("purpose") != "stop"]
    zero_motion = 0
    for row in motion:
        values = list(row.get("joint_positions_rad", [])) + list(
            row.get("joint_velocities_rad_s", [])
        )
        if values and all(float(value) == 0.0 for value in values):
            zero_motion += 1
    duration_s = (times[-1] - times[0]) / 1e9 if len(times) > 1 else 0.0
    return {
        "tick_ms": tick_ms,
        "duration_s": round(duration_s, 3),
        "rows": {name: len(rows) for name, rows in streams.items()},
        "jitter_ms": _summary(jitter_ms),
        "observation_skew_ms": _summary(skew_ms),
        "limit_events": limit_events,
        "limit_events_per_min": round(limit_events / duration_s * 60.0, 3)
        if duration_s > 0
        else 0.0,
        "deadman_releases": deadman_releases,
        "stop_intents": stop_intents,
        "motion_actions": len(motion),
        "zero_motion_ratio": round(zero_motion / len(motion), 4) if motion else 0.0,
    }
