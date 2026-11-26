"""Read-only teleop status payload (jcheng.teleop.status.v1).

The payload is a presentation contract for the studio operator console and the
capture UI. It reports state; it carries no lease, no intent and no motion
authority. A missing or stale sample is reported as stale, never as ready.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "jcheng.teleop.status.v1"
STALE_AFTER_MS = 1000


def status_payload(
    *,
    teleop_version: str,
    contract_hash: str,
    profile_id: str,
    profile_hash: str,
    lease_ref: str | None,
    phase: str,
    last_wire_seq: int,
    mode: str | None,
    source_id: str | None,
    sample_seq: int | None,
    sample_t_source_ns: int | None,
    deadman: bool | None,
    input_age_ms: float | None,
    capture: dict[str, Any],
    now_mono_ns: int,
    stale_after_ms: int = STALE_AFTER_MS,
) -> dict[str, Any]:
    if phase not in {"starting", "running", "completed", "faulted"}:
        raise ValueError(f"unsupported phase: {phase!r}")
    stale = input_age_ms is None or input_age_ms > stale_after_ms
    return {
        "schema": SCHEMA,
        "teleop_version": teleop_version,
        "contract_hash": contract_hash,
        "profile_id": profile_id,
        "profile_hash": profile_hash,
        "lease_ref": lease_ref,
        "phase": phase,
        "generated_at_ns": int(now_mono_ns),
        "stale_after_ms": int(stale_after_ms),
        "input": {
            "present": sample_seq is not None,
            "age_ms": None if input_age_ms is None else round(float(input_age_ms), 3),
            "stale": stale,
            "deadman": deadman,
            "mode": mode,
            "source_id": source_id,
            "seq": sample_seq,
            "t_source_ns": sample_t_source_ns,
        },
        "last_wire_seq": int(last_wire_seq),
        "capture": capture,
        "limitations": [
            "read-only status; no lease, intent or motion authority",
            "demo script input; the operator input adapter is out of scope",
        ],
    }
