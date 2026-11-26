"""Map conditioned input to a typed action intent."""

from __future__ import annotations

from .conditioning import ConditionedSample
from .model import ActionIntent, Mode, RejectedSample, RejectionCode
from .profile import ResolvedProfile


class ActionMapper:
    def __init__(self, profile: ResolvedProfile) -> None:
        self.profile = profile

    def map(self, conditioned: ConditionedSample) -> ActionIntent:
        sample = conditioned.sample
        mode = conditioned.mode
        if mode is Mode.JOINT_VELOCITY:
            return ActionIntent(
                mode=mode,
                profile_id=self.profile.profile_id,
                profile_hash=self.profile.profile_hash,
                deadman=sample.deadman,
                t_source_ns=sample.t_source_ns,
                seq=sample.seq,
                joint_velocities_rad_s=conditioned.values,
                gripper_normalized=conditioned.gripper_normalized,
                gripper_valid=conditioned.gripper_normalized is not None,
            )
        if mode is Mode.JOINT_POSITION:
            return ActionIntent(
                mode=mode,
                profile_id=self.profile.profile_id,
                profile_hash=self.profile.profile_hash,
                deadman=sample.deadman,
                t_source_ns=sample.t_source_ns,
                seq=sample.seq,
                joint_positions_rad=conditioned.values,
                gripper_normalized=conditioned.gripper_normalized,
                gripper_valid=conditioned.gripper_normalized is not None,
            )
        if mode is Mode.CARTESIAN_TWIST:
            if sample.cartesian_twist is None:
                raise RejectedSample(RejectionCode.SAMPLE_INVALID, "Cartesian sample has no twist")
            return ActionIntent(
                mode=mode,
                profile_id=self.profile.profile_id,
                profile_hash=self.profile.profile_hash,
                deadman=sample.deadman,
                t_source_ns=sample.t_source_ns,
                seq=sample.seq,
                cartesian_twist=sample.cartesian_twist,
                gripper_normalized=conditioned.gripper_normalized,
                gripper_valid=conditioned.gripper_normalized is not None,
                frame_id=sample.cartesian_twist.frame_id,
            )
        raise RejectedSample(RejectionCode.MODE_UNSUPPORTED, f"unsupported mode {mode.value}")
