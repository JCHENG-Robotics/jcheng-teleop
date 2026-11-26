from __future__ import annotations

import pytest
import yaml

from jcheng_teleop.core.model import Mode
from jcheng_teleop.core.profile import (
    ProfileError,
    load_binding,
    load_profile,
    resolve_profile,
)
from conftest import write_resolved


def test_profile_and_binding_resolve(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    assert resolved.joint_count == 5
    assert resolved.profile_id == "fixture_5dof"
    assert resolved.profile_hash.startswith("sha256:")
    assert resolved.modes == {Mode.JOINT_VELOCITY}


def test_profile_hash_is_stable(tmp_path):
    path = tmp_path / "p.yaml"
    path.write_text(
        "schema: jcheng.teleop.profile.v1\n"
        "profile_id: p\n"
        "joints:\n"
        "  - {name: j1, lower_rad: -1, upper_rad: 1, max_velocity_rad_s: 1, max_acceleration_rad_s2: 1}\n"
        "workspace_frame: base_link\n"
        "tip_link: t\n"
        "modes: [JOINT_VELOCITY]\n",
        encoding="utf-8",
    )
    first = load_profile(path)
    second = load_profile(path)
    assert first.profile_hash == second.profile_hash


def test_hash_mismatch(tmp_path):
    resolved = write_resolved(tmp_path, joints=2)
    binding_path = tmp_path / "binding_2_1.yaml"
    data = yaml.safe_load(binding_path.read_text(encoding="utf-8"))
    data["profile_hash"] = "sha256:" + "0" * 64
    binding_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ProfileError):
        resolve_profile(resolved.profile, load_binding(binding_path))


def test_binding_must_cover_every_joint(tmp_path):
    resolved = write_resolved(tmp_path, joints=3)
    binding_path = tmp_path / "binding_3_1.yaml"
    data = yaml.safe_load(binding_path.read_text(encoding="utf-8"))
    data["joints"] = data["joints"][:2]
    binding_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ProfileError):
        resolve_profile(resolved.profile, load_binding(binding_path))


def test_binding_profile_id_mismatch(tmp_path):
    resolved = write_resolved(tmp_path, joints=2)
    binding_path = tmp_path / "binding_2_1.yaml"
    data = yaml.safe_load(binding_path.read_text(encoding="utf-8"))
    data["profile_id"] = "other"
    binding_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ProfileError):
        resolve_profile(resolved.profile, load_binding(binding_path))


def test_unenabled_mode(tmp_path):
    resolved = write_resolved(tmp_path, joints=2, modes=("JOINT_VELOCITY",))
    binding_path = tmp_path / "binding_2_1.yaml"
    data = yaml.safe_load(binding_path.read_text(encoding="utf-8"))
    data["modes"] = ["JOINT_VELOCITY", "JOINT_POSITION"]
    binding_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ProfileError):
        resolve_profile(resolved.profile, load_binding(binding_path))


def test_map_arm_values_applies_sign_and_offset(tmp_path):
    resolved = write_resolved(tmp_path, joints=2)
    # The helper uses +1 signs and zero offsets; mutate a copy in memory.
    from jcheng_teleop.core.profile import JointBinding, TeleopBinding

    bindings = list(resolved.binding.joints)
    bindings[0] = JointBinding(input_index=0, joint="joint1", sign=-1, offset_rad=0.1, scale=2.0)
    changed = TeleopBinding(
        profile_id=resolved.profile_id,
        profile_hash=resolved.profile_hash,
        source_id=resolved.binding.source_id,
        joints=tuple(bindings),
        modes=resolved.binding.modes,
        gripper=resolved.binding.gripper,
    )
    changed_resolved = resolve_profile(resolved.profile, changed)
    assert changed_resolved.map_arm_values([0.5, 0.2]) == (-0.9, 0.2)


def test_2_5_6_dof_profiles_resolve(tmp_path):
    for joints in (2, 5, 6):
        resolved = write_resolved(tmp_path, joints=joints, modes=("JOINT_VELOCITY",))
        assert resolved.joint_count == joints
        assert len(resolved.map_arm_values([0.0] * joints)) == joints


def test_declared_profile_hash_must_match_content(tmp_path):
    path = tmp_path / "p.yaml"
    path.write_text(
        "schema: jcheng.teleop.profile.v1\n"
        "profile_id: p\n"
        "profile_hash: sha256:" + "0" * 64 + "\n"
        "joints:\n"
        "  - {name: j1, lower_rad: -1, upper_rad: 1, max_velocity_rad_s: 1, max_acceleration_rad_s2: 1}\n"
        "workspace_frame: base_link\n"
        "tip_link: t\n"
        "modes: [JOINT_VELOCITY]\n",
        encoding="utf-8",
    )
    with pytest.raises(ProfileError):
        load_profile(path)


def test_nan_binding_deadzone_is_rejected(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    from jcheng_teleop.core.profile import JointBinding

    with pytest.raises(ProfileError):
        JointBinding(input_index=0, joint="joint1", deadzone=float("nan"))
