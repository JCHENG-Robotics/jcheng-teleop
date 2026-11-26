"""Offline anomaly scan over capture streams.

The scan is pure: it takes parsed rows and reports findings. It never repairs,
rewrites or drops data. Provenance violations are errors; timing and coverage
gaps are warnings with metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

EXPECTED_SCHEMA = {
    "input": "jcheng.teleop.input.v1",
    "action": "jcheng.teleop.action.v1",
    "command": "jcheng.teleop.command.v1",
    "observation": "jcheng.teleop.observation.v1",
    "events": "jcheng.teleop.event.v1",
}
VERIFICATIONS = {"bus", "timed", "open_loop", "simulated"}
TRUTHS = {"measured", "commanded", "simulated"}
OUTCOMES = {"COMPLETED", "REJECTED", "ABORTED", "TIMEOUT", "UNKNOWN", "BUSY", "UNAVAILABLE"}
MAX_TICK_GAP_WARN = 50


@dataclass
class AnomalyReport:
    status: str = "ok"                  # ok | warnings | errors
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status != "errors"


def _finite(values) -> bool:
    return all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values)


def scan_streams(
    streams: dict[str, list[dict[str, Any]]], environment_class: str
) -> AnomalyReport:
    report = AnomalyReport()
    for name, rows in streams.items():
        expected = EXPECTED_SCHEMA[name]
        last_t: int | None = None
        last_tick: int | None = None
        seen: set[int] = set()
        for index, row in enumerate(rows):
            where = f"{name}[{index}]"
            if row.get("schema") != expected:
                report.errors.append(f"{where}: unexpected schema {row.get('schema')!r}")
            tick = row.get("tick_id")
            if not isinstance(tick, int):
                report.errors.append(f"{where}: tick_id missing")
                continue
            if name != "events":
                # Several events legitimately share one tick; the other streams
                # have one row per tick and are checked as keys.
                if tick in seen:
                    report.errors.append(f"{where}: duplicate tick_id {tick}")
                if last_tick is not None and tick < last_tick:
                    report.errors.append(f"{where}: tick_id regressed {last_tick} -> {tick}")
            seen.add(tick)
            last_tick = tick
            t_mono = row.get("t_mono_ns")
            if not isinstance(t_mono, int) or t_mono < 0:
                report.errors.append(f"{where}: invalid t_mono_ns")
            elif last_t is not None and t_mono < last_t:
                report.errors.append(f"{where}: t_mono_ns regressed")
            if isinstance(t_mono, int):
                last_t = t_mono

    inputs = {row.get("tick_id"): row for row in streams.get("input", [])}
    actions = streams.get("action", [])
    action_ticks = {row.get("tick_id") for row in actions}
    for index, row in enumerate(actions):
        where = f"action[{index}]"
        if row.get("purpose") == "stop":
            if row.get("deadman") is not False:
                report.errors.append(f"{where}: stop intent must have deadman=false")
        else:
            values = list(row.get("joint_positions_rad", [])) + list(
                row.get("joint_velocities_rad_s", [])
            )
            if not _finite(values):
                report.errors.append(f"{where}: non-finite action value")
        tick = row.get("tick_id")
        if tick not in inputs:
            report.warnings.append(f"{where}: no input row at tick {tick}")
        else:
            input_row = inputs[tick]
            if row.get("t_mono_ns") != input_row.get("t_mono_ns"):
                report.warnings.append(f"{where}: action/input t_mono mismatch at tick {tick}")
            if row.get("t_source_ns") != input_row.get("t_source_ns"):
                report.warnings.append(f"{where}: action/input t_source mismatch at tick {tick}")

    for index, row in enumerate(streams.get("command", [])):
        where = f"command[{index}]"
        if row.get("outcome") not in OUTCOMES:
            report.errors.append(f"{where}: unsupported outcome {row.get('outcome')!r}")
        if row.get("tick_id") not in action_ticks:
            report.warnings.append(f"{where}: command without an action at tick {row.get('tick_id')}")

    for index, row in enumerate(streams.get("observation", [])):
        where = f"observation[{index}]"
        truth = row.get("truth")
        verification = row.get("verification")
        if truth not in TRUTHS:
            report.errors.append(f"{where}: unsupported truth {truth!r}")
        if verification not in VERIFICATIONS:
            report.errors.append(f"{where}: unsupported verification {verification!r}")
        if verification == "bus" and environment_class != "hardware":
            report.errors.append(f"{where}: bus label in a {environment_class} capture")
        if verification == "simulated" and environment_class != "simulation":
            report.errors.append(f"{where}: simulated label in a {environment_class} capture")
        if verification == "simulated" and truth not in {"measured", "simulated"}:
            report.errors.append(f"{where}: simulated label with truth {truth!r}")

    gaps = []
    for name in ("input", "action", "command"):
        ticks = sorted(
            row["tick_id"] for row in streams.get(name, []) if isinstance(row.get("tick_id"), int)
        )
        for before, after in zip(ticks, ticks[1:]):
            gaps.append(after - before)
    max_gap = max(gaps) if gaps else 0
    report.metrics = {
        "rows": {name: len(rows) for name, rows in streams.items()},
        "max_tick_gap": max_gap,
        "environment_class": environment_class,
    }
    if max_gap > MAX_TICK_GAP_WARN:
        report.warnings.append(f"tick gap {max_gap} exceeds {MAX_TICK_GAP_WARN}")
    if report.errors:
        report.status = "errors"
    elif report.warnings:
        report.status = "warnings"
    return report
