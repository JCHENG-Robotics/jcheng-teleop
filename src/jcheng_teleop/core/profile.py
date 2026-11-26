"""Canonical robot profile plus a teleop binding.

The profile fixture format is teleop-local for M1. It carries the canonical
joint order, limits and mode set by reference; the binding adds only teleop
semantics (input index, sign, offset, deadzone). M2 will resolve a canonical
system/simulation profile and require its hash to match.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .model import Mode


class ProfileError(ValueError):
    pass


def _hash_payload(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_sha256(value: str, field: str) -> str:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ProfileError(f"{field} must be a sha256:<64 hex> value")
    try:
        int(value.split(":", 1)[1], 16)
    except ValueError as exc:
        raise ProfileError(f"{field} must be a sha256:<64 hex> value") from exc
    return value


@dataclass(frozen=True)
class JointSpec:
    name: str
    lower_rad: float
    upper_rad: float
    max_velocity_rad_s: float
    max_acceleration_rad_s2: float

    def __post_init__(self) -> None:
        if not self.name:
            raise ProfileError("joint name is required")
        if not all(math.isfinite(value) for value in (self.lower_rad, self.upper_rad, self.max_velocity_rad_s, self.max_acceleration_rad_s2)):
            raise ProfileError(f"{self.name}: joint values must be finite")
        if not self.lower_rad < self.upper_rad:
            raise ProfileError(f"{self.name}: lower_rad must be < upper_rad")
        if self.max_velocity_rad_s <= 0:
            raise ProfileError(f"{self.name}: max_velocity_rad_s must be > 0")
        if self.max_acceleration_rad_s2 <= 0:
            raise ProfileError(f"{self.name}: max_acceleration_rad_s2 must be > 0")


@dataclass(frozen=True)
class GripperSpec:
    min_normalized: float = 0.0
    max_normalized: float = 1.0
    closed: float = 0.0
    open: float = 1.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.min_normalized, self.max_normalized, self.closed, self.open)):
            raise ProfileError("gripper values must be finite")
        if not self.min_normalized < self.max_normalized:
            raise ProfileError("gripper min_normalized must be < max_normalized")
        if not (self.min_normalized <= self.closed <= self.max_normalized):
            raise ProfileError("gripper closed value outside range")
        if not (self.min_normalized <= self.open <= self.max_normalized):
            raise ProfileError("gripper open value outside range")


@dataclass(frozen=True)
class JointBinding:
    input_index: int
    joint: str
    sign: int = 1
    offset_rad: float = 0.0
    scale: float = 1.0
    deadzone: float = 0.0
    hysteresis: float = 0.0

    def __post_init__(self) -> None:
        if self.input_index < 0:
            raise ProfileError("binding input index must be non-negative")
        if self.sign not in (-1, 1):
            raise ProfileError("binding sign must be +1 or -1")
        if not all(math.isfinite(value) for value in (self.deadzone, self.hysteresis)):
            raise ProfileError("deadzone and hysteresis must be finite")
        if self.deadzone < 0 or self.hysteresis < 0:
            raise ProfileError("deadzone and hysteresis must be non-negative")
        if self.deadzone + self.hysteresis > 1.0:
            raise ProfileError("deadzone + hysteresis must be <= 1")
        if self.scale <= 0 or self.scale != self.scale or abs(self.scale) == float("inf"):
            raise ProfileError("binding scale must be finite and > 0")
        if self.offset_rad != self.offset_rad or abs(self.offset_rad) == float("inf"):
            raise ProfileError("binding offset_rad must be finite")


@dataclass(frozen=True)
class GripperBinding:
    input_index: int
    closed: float = 0.0
    open: float = 1.0
    deadzone: float = 0.0
    hysteresis: float = 0.0

    def __post_init__(self) -> None:
        if self.input_index < 0:
            raise ProfileError("gripper input index must be non-negative")
        if not (0.0 <= self.closed <= 1.0 and 0.0 <= self.open <= 1.0):
            raise ProfileError("gripper binding endpoints must be in [0, 1]")
        if not all(math.isfinite(value) for value in (self.deadzone, self.hysteresis)):
            raise ProfileError("gripper deadzone/hysteresis must be finite")
        if self.deadzone < 0 or self.hysteresis < 0:
            raise ProfileError("gripper deadzone/hysteresis must be non-negative")


@dataclass(frozen=True)
class TeleopProfile:
    profile_id: str
    profile_hash: str
    joints: tuple[JointSpec, ...]
    modes: frozenset[Mode]
    gripper: GripperSpec | None
    workspace_frame: str
    tip_link: str
    schema: str = "jcheng.teleop.profile.v1"
    source: str = ""

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ProfileError("profile_id is required")
        _require_sha256(self.profile_hash, "profile_hash")
        names = [joint.name for joint in self.joints]
        if not names:
            raise ProfileError("at least one joint is required")
        if len(names) != len(set(names)):
            raise ProfileError("joint names must be unique")

    @property
    def joint_names(self) -> tuple[str, ...]:
        return tuple(joint.name for joint in self.joints)

    def joint(self, name: str) -> JointSpec:
        for joint in self.joints:
            if joint.name == name:
                return joint
        raise ProfileError(f"unknown joint: {name}")


@dataclass(frozen=True)
class TeleopBinding:
    profile_id: str
    profile_hash: str
    source_id: str
    joints: tuple[JointBinding, ...]
    modes: frozenset[Mode]
    gripper: GripperBinding | None = None
    schema: str = "jcheng.teleop.binding.v1"
    source: str = ""

    def __post_init__(self) -> None:
        if not self.profile_id or not self.source_id:
            raise ProfileError("binding profile_id and source_id are required")
        _require_sha256(self.profile_hash, "binding profile_hash")
        inputs = [binding.input_index for binding in self.joints]
        if len(inputs) != len(set(inputs)):
            raise ProfileError("binding input indices must be unique")
        joints = [binding.joint for binding in self.joints]
        if len(joints) != len(set(joints)):
            raise ProfileError("binding joints must be unique")


@dataclass(frozen=True)
class ResolvedProfile:
    profile: TeleopProfile
    binding: TeleopBinding
    source: str

    @property
    def profile_id(self) -> str:
        return self.profile.profile_id

    @property
    def profile_hash(self) -> str:
        return self.profile.profile_hash

    @property
    def joint_names(self) -> tuple[str, ...]:
        return self.profile.joint_names

    @property
    def joint_count(self) -> int:
        return len(self.profile.joints)

    @property
    def modes(self) -> frozenset[Mode]:
        return self.binding.modes & self.profile.modes

    @property
    def workspace_frame(self) -> str:
        return self.profile.workspace_frame

    @property
    def tip_link(self) -> str:
        return self.profile.tip_link

    @property
    def gripper(self) -> GripperSpec | None:
        return self.profile.gripper

    def joint(self, name: str) -> JointSpec:
        return self.profile.joint(name)

    def map_arm_values(self, raw: Sequence[float], *, include_offset: bool = True) -> tuple[float, ...]:
        """Map raw input indices to canonical joint order, applying sign/offset/scale.

        Offsets are a position-mode concept; a velocity mapping must not add a
        constant offset (that would create a bias).
        """
        if len(raw) <= max((binding.input_index for binding in self.binding.joints), default=-1):
            raise ProfileError("input vector does not cover every binding index")
        by_joint = {binding.joint: binding for binding in self.binding.joints}
        mapped: list[float] = []
        for joint in self.profile.joints:
            binding = by_joint[joint.name]
            value = float(raw[binding.input_index]) * binding.scale
            if binding.sign < 0:
                value = -value
            if include_offset:
                value += float(binding.offset_rad)
            mapped.append(value)
        return tuple(mapped)

    def gripper_value(self, raw: Sequence[float]) -> float | None:
        binding = self.binding.gripper
        if binding is None:
            return None
        if len(raw) <= binding.input_index:
            raise ProfileError("input vector does not cover the gripper binding")
        value = float(raw[binding.input_index])
        if value <= binding.closed:
            return 0.0
        if value >= binding.open:
            return 1.0
        span = binding.open - binding.closed
        if span == 0:
            return 0.0
        return max(0.0, min(1.0, (value - binding.closed) / span))


def _load_yaml(path: str | Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProfileError(f"{path}: top-level YAML must be a mapping")
    return raw


def _profile_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    payload.pop("profile_hash", None)
    return payload


def load_profile(path: str | Path) -> TeleopProfile:
    raw = _load_yaml(path)
    if raw.get("schema") != "jcheng.teleop.profile.v1":
        raise ProfileError("profile schema must be jcheng.teleop.profile.v1")
    computed_hash = _hash_payload(_profile_payload(raw))
    declared_hash = raw.get("profile_hash")
    if declared_hash is not None and str(declared_hash) != computed_hash:
        raise ProfileError("declared profile_hash does not match the profile content")
    profile_hash = computed_hash
    _require_sha256(str(profile_hash), "profile_hash")
    joints_raw = raw.get("joints")
    if not isinstance(joints_raw, list):
        raise ProfileError("profile joints must be a list")
    joints = tuple(
        JointSpec(
            name=str(item["name"]),
            lower_rad=float(item["lower_rad"]),
            upper_rad=float(item["upper_rad"]),
            max_velocity_rad_s=float(item["max_velocity_rad_s"]),
            max_acceleration_rad_s2=float(item["max_acceleration_rad_s2"]),
        )
        for item in joints_raw
    )
    modes_raw = raw.get("modes")
    if not isinstance(modes_raw, list) or not modes_raw:
        raise ProfileError("profile modes must be a non-empty list")
    modes = frozenset(Mode.parse(str(item)) for item in modes_raw)
    gripper_raw = raw.get("gripper")
    gripper = None
    if gripper_raw is not None:
        gripper = GripperSpec(
            min_normalized=float(gripper_raw.get("min_normalized", 0.0)),
            max_normalized=float(gripper_raw.get("max_normalized", 1.0)),
            closed=float(gripper_raw.get("closed", 0.0)),
            open=float(gripper_raw.get("open", 1.0)),
        )
    return TeleopProfile(
        profile_id=str(raw["profile_id"]),
        profile_hash=str(profile_hash),
        joints=joints,
        modes=modes,
        gripper=gripper,
        workspace_frame=str(raw.get("workspace_frame", "base_link")),
        tip_link=str(raw.get("tip_link", "")),
        source=str(path),
    )


def load_binding(path: str | Path) -> TeleopBinding:
    raw = _load_yaml(path)
    if raw.get("schema") != "jcheng.teleop.binding.v1":
        raise ProfileError("binding schema must be jcheng.teleop.binding.v1")
    joints_raw = raw.get("joints")
    if not isinstance(joints_raw, list) or not joints_raw:
        raise ProfileError("binding joints must be a non-empty list")
    joints = tuple(
        JointBinding(
            input_index=int(item["input"]),
            joint=str(item["joint"]),
            sign=int(item.get("sign", 1)),
            offset_rad=float(item.get("offset_rad", 0.0)),
            scale=float(item.get("scale", 1.0)),
            deadzone=float(item.get("deadzone", 0.0)),
            hysteresis=float(item.get("hysteresis", 0.0)),
        )
        for item in joints_raw
    )
    modes_raw = raw.get("modes")
    if not isinstance(modes_raw, list) or not modes_raw:
        raise ProfileError("binding modes must be a non-empty list")
    modes = frozenset(Mode.parse(str(item)) for item in modes_raw)
    gripper_raw = raw.get("gripper")
    gripper = None
    if gripper_raw is not None:
        gripper = GripperBinding(
            input_index=int(gripper_raw["input"]),
            closed=float(gripper_raw.get("closed", 0.0)),
            open=float(gripper_raw.get("open", 1.0)),
            deadzone=float(gripper_raw.get("deadzone", 0.0)),
            hysteresis=float(gripper_raw.get("hysteresis", 0.0)),
        )
    return TeleopBinding(
        profile_id=str(raw["profile_id"]),
        profile_hash=str(raw["profile_hash"]),
        source_id=str(raw["source_id"]),
        joints=joints,
        modes=modes,
        gripper=gripper,
        source=str(path),
    )


def resolve_profile(profile: TeleopProfile, binding: TeleopBinding) -> ResolvedProfile:
    if profile.profile_id != binding.profile_id:
        raise ProfileError(
            f"profile_id mismatch: profile {profile.profile_id!r} vs binding {binding.profile_id!r}"
        )
    if profile.profile_hash != binding.profile_hash:
        raise ProfileError("profile_hash mismatch between profile and binding")
    profile_joints = set(profile.joint_names)
    binding_joints = {joint.joint for joint in binding.joints}
    if profile_joints != binding_joints:
        missing = sorted(profile_joints - binding_joints)
        extra = sorted(binding_joints - profile_joints)
        raise ProfileError(f"binding joints must match profile; missing={missing}, extra={extra}")
    if len(binding.joints) != len(profile.joints):
        raise ProfileError("binding must cover each profile joint exactly once")
    unknown_modes = binding.modes - profile.modes
    if unknown_modes:
        raise ProfileError(f"binding modes not supported by profile: {sorted(mode.value for mode in unknown_modes)}")
    return ResolvedProfile(profile=profile, binding=binding, source=f"{profile.source} + {binding.source}")
