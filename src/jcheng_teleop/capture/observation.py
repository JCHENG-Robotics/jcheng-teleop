"""Observation rows for capture: labelled state, never reinterpreted.

The recorder copies `truth` and `verification` from the system telemetry
message. It never upgrades a command cache to a measurement, and it refuses a
`bus` label outside a hardware capture so a mock/simulation run cannot be
relabelled as hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .provenance import ProvenanceError

TRUTHS = frozenset({"measured", "commanded", "simulated"})
VERIFICATIONS = frozenset({"bus", "timed", "open_loop", "simulated"})


@dataclass(frozen=True)
class ObservationSample:
    topic: str
    source: str
    seq: int
    fresh: bool
    joint_names: tuple[str, ...]
    positions: tuple[float, ...]
    velocities: tuple[float, ...]
    gripper_position: float
    base_duty: tuple[float, ...]
    battery_voltage: float
    profile_hash: str
    truth: str
    verification: str
    stamp_ns: int
    received_ns: int

    def validate(self, environment_class: str) -> "ObservationSample":
        if not self.topic or not self.source:
            raise ProvenanceError("observation topic and source are required")
        if self.truth not in TRUTHS:
            raise ProvenanceError(f"unsupported observation truth: {self.truth!r}")
        if self.verification not in VERIFICATIONS:
            raise ProvenanceError(
                f"unsupported observation verification: {self.verification!r}"
            )
        if len(self.joint_names) != len(self.positions) or len(self.positions) != len(
            self.velocities
        ):
            raise ProvenanceError("observation joint vector lengths do not match")
        if not self.joint_names:
            raise ProvenanceError("observation has no joints")
        if not all(
            math.isfinite(value)
            for value in (*self.positions, *self.velocities, self.gripper_position,
                          *self.base_duty, self.battery_voltage)
        ):
            raise ProvenanceError("observation contains a non-finite value")
        if self.stamp_ns < 0 or self.received_ns < 0:
            raise ProvenanceError("observation timestamps must be non-negative")
        if self.verification == "bus" and self.truth != "measured":
            raise ProvenanceError("verification=bus requires truth=measured")
        if self.verification == "simulated":
            if environment_class != "simulation":
                raise ProvenanceError(
                    "verification=simulated is only valid in a simulation capture"
                )
            if self.truth not in {"measured", "simulated"}:
                raise ProvenanceError(
                    "verification=simulated requires truth=measured or simulated"
                )
        if environment_class == "hardware" and self.verification == "simulated":
            raise ProvenanceError("a hardware capture cannot carry a simulated state")
        if environment_class != "hardware" and self.verification == "bus":
            raise ProvenanceError(
                f"{environment_class} capture must not record a bus measurement"
            )
        return self

    def to_row(self) -> dict[str, object]:
        return {
            "topic": self.topic,
            "source": self.source,
            "seq": int(self.seq),
            "fresh": bool(self.fresh),
            "joint_names": list(self.joint_names),
            "positions": list(self.positions),
            "velocities": list(self.velocities),
            "gripper_position": float(self.gripper_position),
            "base_duty": list(self.base_duty),
            "battery_voltage": float(self.battery_voltage),
            "profile_hash": self.profile_hash,
            "truth": self.truth,
            "verification": self.verification,
            "t_ros_ns": int(self.stamp_ns),
            "t_received_ns": int(self.received_ns),
        }
