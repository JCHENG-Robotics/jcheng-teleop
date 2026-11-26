"""Shared fixtures for the M1 test suite."""

from __future__ import annotations

from pathlib import Path

import yaml

from jcheng_teleop.adapters.gateway.mock import MockGateway
from jcheng_teleop.core.clock import ManualClock
from jcheng_teleop.core.model import InputSample, Mode
from jcheng_teleop.core.profile import (
    load_binding,
    load_profile,
    resolve_profile,
)
from jcheng_teleop.core.session import SessionConfig, TeleopSession

CONTRACT = "sha256:" + "1" * 64


def write_resolved(
    tmp_path: Path,
    *,
    joints: int = 5,
    modes: tuple[str, ...] = ("JOINT_VELOCITY",),
    gripper: bool = True,
    deadzone: float = 0.05,
    hysteresis: float = 0.02,
):
    profile_path = tmp_path / f"profile_{joints}_{len(modes)}.yaml"
    profile_data = {
        "schema": "jcheng.teleop.profile.v1",
        "profile_id": f"fixture_{joints}dof",
        "joints": [
            {
                "name": f"joint{index + 1}",
                "lower_rad": -1.8,
                "upper_rad": 1.8,
                "max_velocity_rad_s": 1.2,
                "max_acceleration_rad_s2": 0.5,
            }
            for index in range(joints)
        ],
        "workspace_frame": "base_link",
        "tip_link": "tool0",
        "modes": list(modes),
    }
    if gripper:
        profile_data["gripper"] = {
            "min_normalized": 0.0,
            "max_normalized": 1.0,
            "closed": 0.0,
            "open": 1.0,
        }
    profile_path.write_text(yaml.safe_dump(profile_data, sort_keys=False), encoding="utf-8")
    profile = load_profile(profile_path)

    binding_path = tmp_path / f"binding_{joints}_{len(modes)}.yaml"
    binding_data = {
        "schema": "jcheng.teleop.binding.v1",
        "profile_id": profile.profile_id,
        "profile_hash": profile.profile_hash,
        "source_id": "test_source",
        "joints": [
            {
                "input": index,
                "joint": f"joint{index + 1}",
                "sign": 1,
                "offset_rad": 0.0,
                "deadzone": deadzone,
                "hysteresis": hysteresis,
            }
            for index in range(joints)
        ],
        "modes": list(modes),
    }
    if gripper:
        binding_data["gripper"] = {"input": joints, "closed": 0.0, "open": 1.0}
    binding_path.write_text(yaml.safe_dump(binding_data, sort_keys=False), encoding="utf-8")
    binding = load_binding(binding_path)
    return resolve_profile(profile, binding)


def make_sample(
    resolved,
    seq: int,
    *,
    values: tuple[float, ...] | None = None,
    mode: Mode = Mode.JOINT_VELOCITY,
    deadman: bool = True,
    t_ns: int | None = None,
    gripper: float | None = None,
    profile_id: str | None = None,
) -> InputSample:
    count = resolved.joint_count
    if values is None:
        values = (0.0,) * count
    t = seq * 20_000_000 if t_ns is None else t_ns
    kwargs = dict(
        schema=InputSample.SCHEMA,
        source_id="test_source",
        source_class="virtual",
        seq=seq,
        t_source_ns=t,
        t_host_mono_ns=t,
        mode=mode,
        deadman=deadman,
        profile_id=resolved.profile_id if profile_id is None else profile_id,
    )
    if mode is Mode.JOINT_VELOCITY:
        kwargs["joint_velocities_rad_s"] = values
    elif mode is Mode.JOINT_POSITION:
        kwargs["joint_positions_rad"] = values
    if gripper is not None:
        kwargs["gripper_normalized"] = gripper
        kwargs["gripper_valid"] = True
    return InputSample(**kwargs)


def make_session(
    resolved,
    *,
    clock: ManualClock | None = None,
    supported_modes: set[str] | None = None,
    contract_hash: str = CONTRACT,
):
    clock = clock or ManualClock(0)
    gateway = MockGateway(
        clock,
        contract_hash=contract_hash,
        profile_hash=resolved.profile_hash,
        joint_count=resolved.joint_count,
        supported_modes=supported_modes or {Mode.JOINT_VELOCITY.value},
    )
    session = TeleopSession(
        resolved,
        gateway,
        clock,
        config=SessionConfig(
            deadman_ms=300,
            tick_ms=20,
            max_rate_hz=50,
            lease_ttl_ms=1000,
            contract_hash=contract_hash,
        ),
    )
    session.start()
    assert session.state is not session.state.FAULT
    return session, gateway, clock
