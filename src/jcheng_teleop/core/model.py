"""Typed, ROS-free model for the M1 teleoperation core.

The model is deliberately small: it describes operator input, a bounded action
intent, a lease reference and the small set of gateway results the core needs.
It does not import ROS, open a device or publish anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Sequence


class Mode(str, Enum):
    JOINT_VELOCITY = "JOINT_VELOCITY"
    JOINT_POSITION = "JOINT_POSITION"
    CARTESIAN_TWIST = "CARTESIAN_TWIST"  # internal; wire string is CARTESIAN_VELOCITY

    @classmethod
    def parse(cls, value: str) -> "Mode":
        try:
            return cls(str(value))
        except ValueError as exc:
            raise ValueError(f"unsupported mode: {value!r}") from exc


class SessionState(str, Enum):
    BOOT = "BOOT"
    SELFTEST = "SELFTEST"
    IDLE = "IDLE"
    READY = "READY"
    ACTIVE = "ACTIVE"
    STOPPING = "STOPPING"
    FAULT = "FAULT"
    PREEMPTED = "PREEMPTED"
    CLOSED = "CLOSED"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    FAULT = "fault"


class RejectionCode(str, Enum):
    SAMPLE_INVALID = "SAMPLE_INVALID"
    MODE_UNSUPPORTED = "MODE_UNSUPPORTED"
    SEQ_GAP = "SEQ_GAP"
    SEQ_DUPLICATE = "SEQ_DUPLICATE"
    STAMP_ROLLBACK = "STAMP_ROLLBACK"
    INPUT_STALE = "INPUT_STALE"
    PROFILE_MISMATCH = "PROFILE_MISMATCH"
    LIMIT_INVALID = "LIMIT_INVALID"
    GATEWAY_UNAVAILABLE = "GATEWAY_UNAVAILABLE"
    GATEWAY_UNKNOWN = "GATEWAY_UNKNOWN"
    LEASE_INVALID = "LEASE_INVALID"
    STATE_STALE = "STATE_STALE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class RejectedSample(ValueError):
    def __init__(self, code: RejectionCode | str, message: str) -> None:
        super().__init__(message)
        self.code = str(code.value if isinstance(code, RejectionCode) else code)
        self.message = message


def _finite(values: Sequence[float]) -> bool:
    return all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values)


def _tuple(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


@dataclass(frozen=True)
class CartesianTwist:
    """Linear and angular velocity in one named frame."""

    linear_x: float = 0.0
    linear_y: float = 0.0
    linear_z: float = 0.0
    angular_x: float = 0.0
    angular_y: float = 0.0
    angular_z: float = 0.0
    frame_id: str = "base_link"

    def __post_init__(self) -> None:
        values = (
            self.linear_x,
            self.linear_y,
            self.linear_z,
            self.angular_x,
            self.angular_y,
            self.angular_z,
        )
        if not _finite(values):
            raise ValueError("cartesian twist contains a non-finite value")
        if not self.frame_id:
            raise ValueError("cartesian twist requires a frame_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "linear": [self.linear_x, self.linear_y, self.linear_z],
            "angular": [self.angular_x, self.angular_y, self.angular_z],
            "frame_id": self.frame_id,
        }


@dataclass(frozen=True)
class InputSample:
    """One normalized operator sample.

    The schema identifier is the transport contract. The core accepts only
    this schema; an adapter must normalize its device units before constructing
    the sample.
    """

    schema: str
    source_id: str
    source_class: str
    seq: int
    t_source_ns: int
    t_host_mono_ns: int
    mode: Mode
    joint_positions_rad: tuple[float, ...] = ()
    joint_velocities_rad_s: tuple[float, ...] = ()
    cartesian_twist: CartesianTwist | None = None
    gripper_normalized: float | None = None
    gripper_valid: bool = False
    deadman: bool = False
    calibration_id: str | None = None
    profile_id: str | None = None
    session_hint: str | None = None

    SCHEMA = "jcheng.teleop.input.v1"

    def __post_init__(self) -> None:
        if self.schema != self.SCHEMA:
            raise ValueError(f"unsupported input schema: {self.schema!r}")
        if not self.source_id:
            raise ValueError("source_id is required")
        if not self.source_class:
            raise ValueError("source_class is required")
        if self.seq < 0:
            raise ValueError("seq must be non-negative")
        if self.t_source_ns < 0 or self.t_host_mono_ns < 0:
            raise ValueError("timestamps must be non-negative")
        if not isinstance(self.mode, Mode):
            raise ValueError("mode must be a Mode")
        if not _finite(self.joint_positions_rad):
            raise ValueError("joint positions contain a non-finite value")
        if not _finite(self.joint_velocities_rad_s):
            raise ValueError("joint velocities contain a non-finite value")
        if self.gripper_valid:
            if self.gripper_normalized is None:
                raise ValueError("gripper_valid requires gripper_normalized")
            if not math.isfinite(self.gripper_normalized):
                raise ValueError("gripper_normalized must be finite")
            if not 0.0 <= self.gripper_normalized <= 1.0:
                raise ValueError("gripper_normalized must be in [0, 1]")
        elif self.gripper_normalized is not None:
            raise ValueError("gripper_normalized requires gripper_valid")

        position = bool(self.joint_positions_rad)
        velocity = bool(self.joint_velocities_rad_s)
        twist = self.cartesian_twist is not None
        if self.mode is Mode.JOINT_POSITION and not (position and not velocity and not twist):
            raise ValueError("JOINT_POSITION requires only joint_positions_rad")
        if self.mode is Mode.JOINT_VELOCITY and not (velocity and not position and not twist):
            raise ValueError("JOINT_VELOCITY requires only joint_velocities_rad_s")
        if self.mode is Mode.CARTESIAN_TWIST and not (twist and not position and not velocity):
            raise ValueError("CARTESIAN_TWIST requires only cartesian_twist")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InputSample":
        mode = Mode.parse(str(value["mode"]))
        twist_value = value.get("cartesian_twist")
        twist = None
        if twist_value is not None:
            twist = CartesianTwist(
                linear_x=float(twist_value["linear"][0]),
                linear_y=float(twist_value["linear"][1]),
                linear_z=float(twist_value["linear"][2]),
                angular_x=float(twist_value["angular"][0]),
                angular_y=float(twist_value["angular"][1]),
                angular_z=float(twist_value["angular"][2]),
                frame_id=str(twist_value.get("frame_id", "base_link")),
            )
        gripper = value.get("gripper_normalized")
        return cls(
            schema=str(value.get("schema", cls.SCHEMA)),
            source_id=str(value["source_id"]),
            source_class=str(value["source_class"]),
            seq=int(value["seq"]),
            t_source_ns=int(value["t_source_ns"]),
            t_host_mono_ns=int(value["t_host_mono_ns"]),
            mode=mode,
            joint_positions_rad=_tuple(value.get("joint_positions_rad", ())),
            joint_velocities_rad_s=_tuple(value.get("joint_velocities_rad_s", ())),
            cartesian_twist=twist,
            gripper_normalized=None if gripper is None else float(gripper),
            gripper_valid=bool(value.get("gripper_valid", False)),
            deadman=bool(value.get("deadman", False)),
            calibration_id=value.get("calibration_id"),
            profile_id=value.get("profile_id"),
            session_hint=value.get("session_hint"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_id": self.source_id,
            "source_class": self.source_class,
            "seq": self.seq,
            "t_source_ns": self.t_source_ns,
            "t_host_mono_ns": self.t_host_mono_ns,
            "mode": self.mode.value,
            "joint_positions_rad": list(self.joint_positions_rad),
            "joint_velocities_rad_s": list(self.joint_velocities_rad_s),
            "cartesian_twist": None if self.cartesian_twist is None else self.cartesian_twist.to_dict(),
            "gripper_normalized": self.gripper_normalized,
            "gripper_valid": self.gripper_valid,
            "deadman": self.deadman,
            "calibration_id": self.calibration_id,
            "profile_id": self.profile_id,
            "session_hint": self.session_hint,
        }


@dataclass(frozen=True)
class ActionIntent:
    """A bounded action proposal. It is not a hardware command."""

    mode: Mode
    profile_id: str
    profile_hash: str
    deadman: bool
    t_source_ns: int
    seq: int
    joint_positions_rad: tuple[float, ...] = ()
    joint_velocities_rad_s: tuple[float, ...] = ()
    cartesian_twist: CartesianTwist | None = None
    gripper_normalized: float | None = None
    gripper_valid: bool = False
    frame_id: str = ""
    lease_id: str = ""
    purpose: str = "motion"      # motion | stop

    def __post_init__(self) -> None:
        if not self.profile_id or not self.profile_hash:
            raise ValueError("profile_id and profile_hash are required")
        if self.purpose not in {"motion", "stop"}:
            raise ValueError("intent purpose must be motion or stop")
        if self.purpose == "stop" and self.deadman:
            raise ValueError("a stop intent must have deadman=false")
        if not _finite(self.joint_positions_rad) or not _finite(self.joint_velocities_rad_s):
            raise ValueError("action intent contains a non-finite value")
        if self.gripper_valid:
            if self.gripper_normalized is None or not math.isfinite(self.gripper_normalized):
                raise ValueError("valid gripper requires a finite normalized value")
        elif self.gripper_normalized is not None:
            raise ValueError("gripper value requires gripper_valid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "profile_id": self.profile_id,
            "profile_hash": self.profile_hash,
            "deadman": self.deadman,
            "t_source_ns": self.t_source_ns,
            "seq": self.seq,
            "joint_positions_rad": list(self.joint_positions_rad),
            "joint_velocities_rad_s": list(self.joint_velocities_rad_s),
            "cartesian_twist": None if self.cartesian_twist is None else self.cartesian_twist.to_dict(),
            "gripper_normalized": self.gripper_normalized,
            "gripper_valid": self.gripper_valid,
            "frame_id": self.frame_id,
            "lease_id": self.lease_id,
            "purpose": self.purpose,
        }


@dataclass(frozen=True)
class TeleopEvent:
    code: str
    severity: Severity
    at_ns: int
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "at_ns": self.at_ns,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class LeaseRequest:
    holder: str
    scope: str
    mode: str
    priority: int
    ttl_ms: int
    deadman_required: bool
    contract_hash: str


@dataclass(frozen=True)
class Lease:
    lease_id: str
    holder: str
    scope: str
    mode: str
    priority: int
    deadman_required: bool
    issued_at_ns: int
    expires_at_ns: int
    contract_hash: str

    def active(self, now_ns: int) -> bool:
        return now_ns < self.expires_at_ns

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "holder": self.holder,
            "scope": self.scope,
            "mode": self.mode,
            "priority": self.priority,
            "deadman_required": self.deadman_required,
            "issued_at_ns": self.issued_at_ns,
            "expires_at_ns": self.expires_at_ns,
            "contract_hash": self.contract_hash,
        }


@dataclass(frozen=True)
class Admission:
    contract_hash: str
    profile_hash: str
    mock: bool
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class RobotStateView:
    positions: tuple[float, ...]
    velocities: tuple[float, ...]
    gripper: float
    fresh: bool
    truth: str
    verification: str
    profile_hash: str
    stamp_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": list(self.positions),
            "velocities": list(self.velocities),
            "gripper": self.gripper,
            "fresh": self.fresh,
            "truth": self.truth,
            "verification": self.verification,
            "profile_hash": self.profile_hash,
            "stamp_ns": self.stamp_ns,
        }


@dataclass(frozen=True)
class GatewayResult:
    outcome: str
    reason_code: str = "OK"
    message: str = ""
    applied: dict[str, Any] = field(default_factory=dict)
    confirmed: bool | None = None

    @property
    def terminal(self) -> bool:
        return self.outcome in {"COMPLETED", "REJECTED", "ABORTED", "TIMEOUT", "UNKNOWN"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "message": self.message,
            "applied": dict(self.applied),
            "confirmed": self.confirmed,
        }


@dataclass(frozen=True)
class StopResult:
    accepted: bool
    reason: str
    confirmed: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "reason": self.reason, "confirmed": self.confirmed}


@dataclass(frozen=True)
class TickResult:
    state: SessionState
    intent: ActionIntent | None
    events: tuple[TeleopEvent, ...]
    submitted: bool
    gateway_result: GatewayResult | None
    stop_sent: bool
    # The mode-specific stop intent sent on this tick, if any. It is not part
    # of `to_dict()` (trace compatibility); the capture recorder reads it so a
    # stop is auditable instead of being inferred from an event code.
    stop_intent: ActionIntent | None = None
    # The intent handed to the gateway on this tick, when a submit happened.
    submitted_intent: ActionIntent | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "intent": None if self.intent is None else self.intent.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "submitted": self.submitted,
            "gateway_result": None if self.gateway_result is None else self.gateway_result.to_dict(),
            "stop_sent": self.stop_sent,
        }
