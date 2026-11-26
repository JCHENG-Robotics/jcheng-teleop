"""Input validation, deadzone/scale, bounds and limit accounting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import InputSample, Mode, RejectedSample, RejectionCode, Severity, TeleopEvent
from .profile import ProfileError, ResolvedProfile


@dataclass(frozen=True)
class ConditionedSample:
    sample: InputSample
    mode: Mode
    values: tuple[float, ...]
    gripper_normalized: float | None
    events: tuple[TeleopEvent, ...]


class Conditioner:
    """Stateful, deterministic conditioning pipeline.

    One instance is used per session. It rejects ordering errors rather than
    repairing or reordering them.
    """

    def __init__(self, profile: ResolvedProfile, *, max_seq_gap: int = 1000) -> None:
        if max_seq_gap < 1:
            raise ValueError("max_seq_gap must be positive")
        self.profile = profile
        self.max_seq_gap = max_seq_gap
        self._last_seq: int | None = None
        self._last_source_ns: int | None = None
        self._last_host_ns: int | None = None
        self._last_output: dict[int, float] = {}
        self._limit_active: dict[str, bool] = {joint.name: False for joint in profile.profile.joints}

    @property
    def last_seq(self) -> int | None:
        return self._last_seq

    def _check_order(self, sample: InputSample) -> None:
        if self._last_seq is not None:
            if sample.seq == self._last_seq:
                raise RejectedSample(RejectionCode.SEQ_DUPLICATE, f"duplicate seq {sample.seq}")
            if sample.seq < self._last_seq:
                raise RejectedSample(RejectionCode.SEQ_GAP, f"seq rollback {sample.seq} < {self._last_seq}")
            if sample.seq - self._last_seq > self.max_seq_gap:
                raise RejectedSample(
                    RejectionCode.SEQ_GAP,
                    f"seq gap {sample.seq - self._last_seq} exceeds {self.max_seq_gap}",
                )
        if self._last_source_ns is not None and sample.t_source_ns < self._last_source_ns:
            raise RejectedSample(RejectionCode.STAMP_ROLLBACK, "source timestamp moved backwards")
        if self._last_host_ns is not None and sample.t_host_mono_ns < self._last_host_ns:
            raise RejectedSample(RejectionCode.STAMP_ROLLBACK, "host timestamp moved backwards")

    def _accept_order(self, sample: InputSample) -> None:
        self._last_seq = sample.seq
        self._last_source_ns = sample.t_source_ns
        self._last_host_ns = sample.t_host_mono_ns

    def _deadzone(self, index: int, value: float, deadzone: float, hysteresis: float) -> float:
        last = self._last_output.get(index, 0.0)
        magnitude = abs(value)
        if last == 0.0:
            out = 0.0 if magnitude <= deadzone + hysteresis else value
        else:
            out = value if magnitude > deadzone else 0.0
        self._last_output[index] = out
        return out

    def process(self, sample: InputSample) -> ConditionedSample:
        if not isinstance(sample, InputSample):
            raise RejectedSample(RejectionCode.SAMPLE_INVALID, "not an InputSample")
        if sample.profile_id is not None and sample.profile_id != self.profile.profile_id:
            raise RejectedSample(
                RejectionCode.PROFILE_MISMATCH,
                f"sample profile {sample.profile_id!r} != {self.profile.profile_id!r}",
            )
        if sample.mode not in self.profile.modes:
            raise RejectedSample(
                RejectionCode.MODE_UNSUPPORTED,
                f"mode {sample.mode.value} is not enabled by the binding/profile",
            )
        self._check_order(sample)

        events: list[TeleopEvent] = []
        if sample.mode is Mode.JOINT_VELOCITY:
            raw = list(sample.joint_velocities_rad_s)
            values = self._map_and_bound(sample, raw, Mode.JOINT_VELOCITY, events)
        elif sample.mode is Mode.JOINT_POSITION:
            raw = list(sample.joint_positions_rad)
            values = self._map_and_bound(sample, raw, Mode.JOINT_POSITION, events)
        elif sample.mode is Mode.CARTESIAN_TWIST:
            values = ()
            if sample.cartesian_twist is not None and sample.cartesian_twist.frame_id != self.profile.workspace_frame:
                raise RejectedSample(
                    RejectionCode.SAMPLE_INVALID,
                    f"Cartesian frame {sample.cartesian_twist.frame_id!r} != {self.profile.workspace_frame!r}",
                )
        else:  # pragma: no cover - exhaustive by Mode
            raise RejectedSample(RejectionCode.MODE_UNSUPPORTED, "unsupported mode")

        gripper = sample.gripper_normalized if sample.gripper_valid else None
        if gripper is not None:
            if self.profile.profile.gripper is None or self.profile.binding.gripper is None:
                raise RejectedSample(RejectionCode.SAMPLE_INVALID, "profile has no gripper binding")
            gripper = max(0.0, min(1.0, float(gripper)))

        self._accept_order(sample)
        return ConditionedSample(
            sample=sample,
            mode=sample.mode,
            values=values,
            gripper_normalized=gripper,
            events=tuple(events),
        )

    def _map_and_bound(
        self,
        sample: InputSample,
        raw: list[float],
        mode: Mode,
        events: list[TeleopEvent],
    ) -> tuple[float, ...]:
        if len(raw) != self.profile.joint_count:
            raise RejectedSample(
                RejectionCode.SAMPLE_INVALID,
                f"joint vector width {len(raw)} != profile width {self.profile.joint_count}",
            )
        max_index = max((binding.input_index for binding in self.profile.binding.joints), default=-1)
        if len(raw) <= max_index:
            raise RejectedSample(
                RejectionCode.SAMPLE_INVALID,
                f"joint vector length {len(raw)} does not cover binding index {max_index}",
            )
        adjusted = list(raw)
        if mode is Mode.JOINT_VELOCITY:
            for binding in self.profile.binding.joints:
                adjusted[binding.input_index] = self._deadzone(
                    binding.input_index,
                    float(raw[binding.input_index]),
                    binding.deadzone,
                    binding.hysteresis,
                )
        try:
            mapped = self.profile.map_arm_values(adjusted, include_offset=(mode is Mode.JOINT_POSITION))
        except ProfileError as exc:
            raise RejectedSample(RejectionCode.SAMPLE_INVALID, str(exc)) from exc

        out: list[float] = []
        for joint, value in zip(self.profile.profile.joints, mapped):
            if mode is Mode.JOINT_VELOCITY:
                applied = max(-joint.max_velocity_rad_s, min(joint.max_velocity_rad_s, value))
                limit = joint.max_velocity_rad_s
                saturated = abs(value) > limit
            else:
                applied = max(joint.lower_rad, min(joint.upper_rad, value))
                limit = joint.upper_rad if value >= 0 else joint.lower_rad
                saturated = value < joint.lower_rad or value > joint.upper_rad
            if saturated and not self._limit_active[joint.name]:
                self._limit_active[joint.name] = True
                events.append(
                    TeleopEvent(
                        code="LIMIT_CLAMPED",
                        severity=Severity.WARNING,
                        at_ns=sample.t_host_mono_ns,
                        detail={
                            "joint": joint.name,
                            "requested": value,
                            "applied": applied,
                            "limit": limit,
                            "mode": mode.value,
                        },
                    )
                )
            elif not saturated:
                self._limit_active[joint.name] = False
            out.append(applied)
        return tuple(out)
