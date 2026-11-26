"""Base teleoperation intent and its local guard (M9, offline).

The base intent is **not** the mobile velocity topic. `jcheng-mobile` owns that
topic; this module only defines the bounded operator intent that the mobile
layer will later consume through a contract. It opens no device and publishes
nothing.

Limits mirror `jcheng-mobile/docs/INTEGRATION.md` (the mobile layer re-applies
them; this guard is early feedback, not authority).
"""

from __future__ import annotations

from dataclasses import dataclass
import math

MAX_FORWARD_M_S = 0.25
MAX_LATERAL_M_S = 0.20
MAX_YAW_RAD_S = 0.60
MAX_RATE_HZ = 20.0
DEADMAN_MS = 500


class BaseIntentError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class BaseIntent:
    schema: str
    session_id: str
    source: str
    lease_id: str
    seq: int
    t_source_ns: int
    vx_m_s: float
    vy_m_s: float
    wz_rad_s: float
    deadman: bool
    frame: str = "base_link"

    SCHEMA = "jcheng.teleop.base_intent.v1"

    def is_stop(self) -> bool:
        return self.vx_m_s == 0.0 and self.vy_m_s == 0.0 and self.wz_rad_s == 0.0


@dataclass
class BaseIntentState:
    last_seq: int = -1
    last_accepted_ns: int | None = None


def validate_base_intent(
    intent: BaseIntent,
    *,
    now_ns: int,
    state: BaseIntentState,
    deadman_ms: int = DEADMAN_MS,
) -> None:
    problems: list[str] = []
    if intent.schema != BaseIntent.SCHEMA:
        problems.append(f"schema must be {BaseIntent.SCHEMA}")
    if not intent.session_id or not intent.source or not intent.lease_id:
        problems.append("session_id, source and lease_id are required")
    if intent.frame != "base_link":
        problems.append("frame must be base_link")
    if not all(
        math.isfinite(value)
        for value in (intent.vx_m_s, intent.vy_m_s, intent.wz_rad_s)
    ):
        problems.append("base velocity must be finite")
    if abs(intent.vx_m_s) > MAX_FORWARD_M_S:
        problems.append(f"vx_m_s exceeds {MAX_FORWARD_M_S}")
    if abs(intent.vy_m_s) > MAX_LATERAL_M_S:
        problems.append(f"vy_m_s exceeds {MAX_LATERAL_M_S}")
    if abs(intent.wz_rad_s) > MAX_YAW_RAD_S:
        problems.append(f"wz_rad_s exceeds {MAX_YAW_RAD_S}")
    if intent.seq <= state.last_seq:
        problems.append(
            f"seq must increase: {intent.seq} <= {state.last_seq}"
        )
    age_ns = now_ns - intent.t_source_ns
    if age_ns < 0:
        problems.append("t_source_ns is in the future")
    elif age_ns > deadman_ms * 1_000_000:
        problems.append(f"input older than {deadman_ms} ms")
    if not intent.is_stop() and not intent.deadman:
        problems.append("non-zero base motion requires deadman=true")
    if state.last_accepted_ns is not None:
        minimum_ns = int(1_000_000_000 / MAX_RATE_HZ)
        if now_ns - state.last_accepted_ns < minimum_ns:
            problems.append("base intent exceeds the 20 Hz bound")
    if problems:
        raise BaseIntentError(problems)


def accept_base_intent(
    intent: BaseIntent,
    *,
    now_ns: int,
    state: BaseIntentState,
    deadman_ms: int = DEADMAN_MS,
) -> BaseIntent:
    """Validate and update the sequence/rate state; no publishing."""
    validate_base_intent(
        intent, now_ns=now_ns, state=state, deadman_ms=deadman_ms
    )
    state.last_seq = intent.seq
    state.last_accepted_ns = now_ns
    return intent
