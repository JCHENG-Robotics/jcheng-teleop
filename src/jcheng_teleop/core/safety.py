"""Local safety guard: defence-in-depth checks and mode-specific stop intent."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .model import ActionIntent, CartesianTwist, Mode, RejectedSample, RejectionCode
from .profile import ResolvedProfile


@dataclass(frozen=True)
class SafetyLimits:
    deadman_ms: int = 300
    tick_ms: int = 20
    max_rate_hz: int = 50
    state_age_max_ms: int = 100

    def __post_init__(self) -> None:
        if self.deadman_ms <= 0 or self.tick_ms <= 0 or self.max_rate_hz <= 0:
            raise ValueError("safety limits must be positive")
        if self.state_age_max_ms <= 0:
            raise ValueError("state_age_max_ms must be positive")

    @property
    def deadman_ns(self) -> int:
        return self.deadman_ms * 1_000_000

    @property
    def tick_ns(self) -> int:
        return self.tick_ms * 1_000_000

    @property
    def state_age_max_ns(self) -> int:
        return self.state_age_max_ms * 1_000_000


class SafetyGuard:
    def __init__(self, profile: ResolvedProfile, limits: SafetyLimits | None = None) -> None:
        self.profile = profile
        self.limits = limits or SafetyLimits()

    def validate(self, intent: ActionIntent) -> None:
        if intent.profile_id != self.profile.profile_id:
            raise RejectedSample(RejectionCode.PROFILE_MISMATCH, "intent profile_id mismatch")
        if intent.profile_hash != self.profile.profile_hash:
            raise RejectedSample(RejectionCode.PROFILE_MISMATCH, "intent profile_hash mismatch")
        if intent.mode is Mode.JOINT_VELOCITY:
            if len(intent.joint_velocities_rad_s) != self.profile.joint_count:
                raise RejectedSample(RejectionCode.SAMPLE_INVALID, "velocity vector length mismatch")
            for joint, value in zip(self.profile.profile.joints, intent.joint_velocities_rad_s):
                if not math.isfinite(value):
                    raise RejectedSample(RejectionCode.SAMPLE_INVALID, f"{joint.name}: non-finite velocity")
                if abs(value) > joint.max_velocity_rad_s + 1e-9:
                    raise RejectedSample(
                        RejectionCode.LIMIT_INVALID,
                        f"{joint.name}: {value} exceeds {joint.max_velocity_rad_s}",
                    )
        elif intent.mode is Mode.JOINT_POSITION:
            if len(intent.joint_positions_rad) != self.profile.joint_count:
                raise RejectedSample(RejectionCode.SAMPLE_INVALID, "position vector length mismatch")
            for joint, value in zip(self.profile.profile.joints, intent.joint_positions_rad):
                if not math.isfinite(value):
                    raise RejectedSample(RejectionCode.SAMPLE_INVALID, f"{joint.name}: non-finite position")
                if value < joint.lower_rad - 1e-9 or value > joint.upper_rad + 1e-9:
                    raise RejectedSample(
                        RejectionCode.LIMIT_INVALID,
                        f"{joint.name}: {value} outside [{joint.lower_rad}, {joint.upper_rad}]",
                    )
        elif intent.mode is Mode.CARTESIAN_TWIST:
            if intent.cartesian_twist is None:
                raise RejectedSample(RejectionCode.SAMPLE_INVALID, "Cartesian intent has no twist")
            if intent.cartesian_twist.frame_id != self.profile.workspace_frame:
                raise RejectedSample(RejectionCode.SAMPLE_INVALID, "Cartesian frame mismatch")
        else:  # pragma: no cover
            raise RejectedSample(RejectionCode.MODE_UNSUPPORTED, f"unsupported mode {intent.mode}")
        if intent.gripper_valid:
            if intent.gripper_normalized is None or not 0.0 <= intent.gripper_normalized <= 1.0:
                raise RejectedSample(RejectionCode.SAMPLE_INVALID, "gripper value outside [0, 1]")

    def stop_intent(
        self,
        last_intent: ActionIntent | None,
        mode: Mode,
        *,
        seq: int,
        t_source_ns: int,
    ) -> ActionIntent | None:
        """Return one mode-specific stop intent.

        Position mode holds the last accepted target; an all-zero position is
        never used as a stop. Without a last position target there is no safe
        synthetic target, so the caller emits no command and relies on the
        system hold.
        """
        if mode is Mode.JOINT_VELOCITY:
            return ActionIntent(
                mode=mode,
                profile_id=self.profile.profile_id,
                profile_hash=self.profile.profile_hash,
                deadman=False,
                t_source_ns=t_source_ns,
                seq=seq,
                joint_velocities_rad_s=(0.0,) * self.profile.joint_count,
                gripper_normalized=(last_intent.gripper_normalized if last_intent and last_intent.gripper_valid else None),
                gripper_valid=bool(last_intent and last_intent.gripper_valid),
                lease_id=(last_intent.lease_id if last_intent else ""),
                purpose="stop",
            )
        if mode is Mode.JOINT_POSITION:
            if last_intent is None or not last_intent.joint_positions_rad:
                return None
            return ActionIntent(
                mode=mode,
                profile_id=self.profile.profile_id,
                profile_hash=self.profile.profile_hash,
                deadman=False,
                t_source_ns=t_source_ns,
                seq=seq,
                joint_positions_rad=last_intent.joint_positions_rad,
                gripper_normalized=(last_intent.gripper_normalized if last_intent.gripper_valid else None),
                gripper_valid=bool(last_intent and last_intent.gripper_valid),
                lease_id=last_intent.lease_id,
                purpose="stop",
            )
        if mode is Mode.CARTESIAN_TWIST:
            return ActionIntent(
                mode=mode,
                profile_id=self.profile.profile_id,
                profile_hash=self.profile.profile_hash,
                deadman=False,
                t_source_ns=t_source_ns,
                seq=seq,
                cartesian_twist=CartesianTwist(frame_id=self.profile.workspace_frame),
                gripper_normalized=(last_intent.gripper_normalized if last_intent and last_intent.gripper_valid else None),
                gripper_valid=bool(last_intent and last_intent.gripper_valid),
                frame_id=self.profile.workspace_frame,
                lease_id=(last_intent.lease_id if last_intent else ""),
                purpose="stop",
            )
        return None
