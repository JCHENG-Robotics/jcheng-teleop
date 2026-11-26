from __future__ import annotations

import json

from jcheng_teleop.adapters.input.gamepad import GamepadInputSource, JoyFrame, VirtualJoySource
from jcheng_teleop.adapters.input.jsonl import JsonlInputSource
from jcheng_teleop.adapters.input.keyboard import KeyboardInputSource, ScriptedKeySource
from jcheng_teleop.adapters.input.virtual import VirtualInputSource
from conftest import make_sample, write_resolved


def test_virtual_source_respects_time(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    source = VirtualInputSource([make_sample(resolved, 0, t_ns=20)])
    source.open()
    assert source.poll(0) is None
    assert source.poll(20) is not None
    assert source.poll(40) is None
    source.close()


def test_jsonl_source_parses_contract(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    sample = make_sample(resolved, 0, values=(0.1,), gripper=0.5)
    path = tmp_path / "input.jsonl"
    path.write_text(json.dumps(sample.to_dict()) + "\n", encoding="utf-8")
    source = JsonlInputSource(path)
    source.open()
    parsed = source.poll(0)
    assert parsed is not None
    assert parsed.seq == 0
    assert parsed.gripper_normalized == 0.5
    source.close()


def test_keyboard_mapping_and_deadman(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    keys = ScriptedKeySource(["space_down", "w_down", "w_up"])
    source = KeyboardInputSource(keys, joint_count=resolved.joint_count, profile_id=resolved.profile_id)
    source.open()
    sample = source.poll(0)
    assert sample is not None
    assert sample.deadman is True
    assert sample.joint_velocities_rad_s[0] == 0.0
    sample2 = source.poll(20)
    assert sample2 is not None
    assert sample2.joint_velocities_rad_s[0] == 1.0
    sample3 = source.poll(40)
    assert sample3 is not None
    assert sample3.joint_velocities_rad_s[0] == 0.0
    source.close()


def test_keyboard_stop_key_zeroes_and_disables(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    keys = ScriptedKeySource(["space_down", "w_down", "esc_down"])
    source = KeyboardInputSource(keys, joint_count=resolved.joint_count, profile_id=resolved.profile_id)
    source.open()
    sample = source.poll(0)
    assert sample is not None
    assert sample.deadman is True
    sample2 = source.poll(20)
    assert sample2 is not None
    assert sample2.joint_velocities_rad_s[0] == 1.0
    sample3 = source.poll(40)
    assert sample3 is not None
    assert sample3.deadman is False
    assert sample3.joint_velocities_rad_s == (0.0,) * 5
    source.close()


def test_gamepad_maps_axes_and_deadman(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    joy = VirtualJoySource([JoyFrame(axes=(0.5, -0.2, 0.0, 0.0, 0.0, 0.5), buttons=(True, False))])
    source = GamepadInputSource(joy, joint_count=resolved.joint_count, profile_id=resolved.profile_id)
    source.open()
    sample = source.poll(0)
    assert sample is not None
    assert sample.deadman is True
    assert sample.joint_velocities_rad_s[0] == 0.5
    assert sample.joint_velocities_rad_s[1] == -0.2
    assert sample.gripper_normalized == 0.75
    source.close()


def test_gamepad_stop_button(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    joy = VirtualJoySource([JoyFrame(axes=(0.5, 0, 0, 0, 0), buttons=(True, True))])
    source = GamepadInputSource(joy, joint_count=resolved.joint_count, profile_id=resolved.profile_id)
    source.open()
    sample = source.poll(0)
    assert sample is not None
    assert sample.deadman is False
    assert sample.joint_velocities_rad_s == (0.0,) * 5
    source.close()
