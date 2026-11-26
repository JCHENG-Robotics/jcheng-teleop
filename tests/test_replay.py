"""M4 offline replay and anomaly tests."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from jcheng_teleop.adapters.gateway.mock import MockGateway
from jcheng_teleop.adapters.input.virtual import VirtualInputSource
from jcheng_teleop.capture import CaptureMetadata, EpisodeRecorder
from jcheng_teleop.core.clock import ManualClock
from jcheng_teleop.core.model import InputSample, Mode
from jcheng_teleop.core.profile import load_binding, load_profile, resolve_profile
from jcheng_teleop.core.runner import TeleopRunner
from jcheng_teleop.core.session import SessionConfig, TeleopSession
from jcheng_teleop.replay import cli, read_capture, replay_capture, replay_streams, scan_streams

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "sha256:" + "0" * 64
HASH = "sha256:" + "1" * 64


def _resolved():
    return resolve_profile(
        load_profile(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
        load_binding(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
    )


def _samples(profile, ticks: int) -> VirtualInputSource:
    samples = []
    for index in range(ticks):
        values = [0.0] * profile.joint_count
        values[0] = 0.2 if index < ticks - 4 else 0.0
        samples.append(
            InputSample(
                schema=InputSample.SCHEMA,
                source_id="replay_test",
                source_class="virtual",
                seq=index,
                t_source_ns=index * 20_000_000,
                t_host_mono_ns=index * 20_000_000,
                mode=Mode.JOINT_VELOCITY,
                joint_velocities_rad_s=tuple(values),
                deadman=index < ticks - 2,
                profile_id=profile.profile_id,
            )
        )
    return VirtualInputSource(samples)


def _record(tmp_path: Path, *, ticks: int = 8) -> tuple[Path, str]:
    resolved = _resolved()
    clock = ManualClock(0)
    gateway = MockGateway(
        clock,
        contract_hash=CONTRACT,
        profile_hash=resolved.profile_hash,
        joint_count=resolved.joint_count,
    )
    session = TeleopSession(
        resolved,
        gateway,
        clock,
        config=SessionConfig(deadman_ms=300, tick_ms=20, max_rate_hz=50, contract_hash=CONTRACT),
    )
    session.start()
    metadata = CaptureMetadata(
        capture_id="replay-cap",
        created_at="2026-11-26T00:00:00+00:00",
        teleop_version="0.3.0",
        contract_hash=CONTRACT,
        profile_id=resolved.profile_id,
        profile_hash=resolved.profile_hash,
        binding_hash=resolved.binding.binding_hash,
        environment_class="mock",
        source_class="scripted",
        session_id="replay-cap",
        task_id="replay",
        task_description="replay test",
        joint_names=resolved.joint_names,
        generator_id="replay-test",
        generator_seed=0,
        generator_config_hash=HASH,
    )
    recorder = EpisodeRecorder(tmp_path, metadata)
    runner = TeleopRunner(
        session=session,
        source=_samples(resolved, ticks),
        clock=clock,
        observer=lambda result, sample, now: (
            recorder.observe(result, sample, now),
            not recorder.faulted,
        )[1],
    )
    runner.run_ticks(ticks)
    session.close()
    recorder.close(outcome="unknown", outcome_source="automatic")
    return tmp_path, "replay-cap"


def test_replay_reproduces_recorded_actions(tmp_path: Path) -> None:
    root, capture_id = _record(tmp_path)
    capture = read_capture(root, capture_id)
    report = replay_capture(capture, _resolved())
    assert report.ok, (report.defects, report.divergences)
    assert report.motion_compared > 0
    assert report.stop_skipped >= 1
    anomalies = scan_streams(capture.streams, capture.environment_class)
    assert anomalies.ok, anomalies.errors


def test_replay_detects_a_tampered_action(tmp_path: Path) -> None:
    root, capture_id = _record(tmp_path)
    capture = read_capture(root, capture_id)
    action = next(row for row in capture.streams["action"] if row["purpose"] == "motion")
    action["joint_velocities_rad_s"][0] = float(action["joint_velocities_rad_s"][0]) + 0.5
    report = replay_streams(capture.streams, _resolved(), capture_id=capture_id)
    assert not report.ok
    assert any(item.field == "joint_velocities_rad_s" for item in report.divergences)


def test_replay_detects_missing_input(tmp_path: Path) -> None:
    root, capture_id = _record(tmp_path)
    capture = read_capture(root, capture_id)
    action_tick = next(row["tick_id"] for row in capture.streams["action"] if row["purpose"] == "motion")
    capture.streams["input"] = [
        row for row in capture.streams["input"] if row["tick_id"] != action_tick
    ]
    report = replay_streams(capture.streams, _resolved(), capture_id=capture_id)
    assert report.missing_input >= 1
    assert report.defects


def _row(**overrides):
    base = {
        "schema": "jcheng.teleop.observation.v1",
        "tick_id": 1,
        "t_mono_ns": 0,
        "capture_id": "x",
        "clock_id": "host_mono",
        "truth": "commanded",
        "verification": "timed",
    }
    base.update(overrides)
    return base


def test_anomaly_rejects_bus_label_in_mock() -> None:
    report = scan_streams(
        {"observation": [_row(truth="measured", verification="bus")]}, "mock"
    )
    assert not report.ok
    assert any("bus label" in error for error in report.errors)


def test_anomaly_rejects_simulated_label_outside_simulation() -> None:
    report = scan_streams(
        {"observation": [_row(truth="measured", verification="simulated")]}, "mock"
    )
    assert not report.ok


def test_anomaly_detects_non_monotonic_time() -> None:
    report = scan_streams(
        {
            "input": [
                {"schema": "jcheng.teleop.input.v1", "tick_id": 1, "t_mono_ns": 10},
                {"schema": "jcheng.teleop.input.v1", "tick_id": 2, "t_mono_ns": 5},
            ]
        },
        "mock",
    )
    assert not report.ok
    assert any("regressed" in error for error in report.errors)


def test_anomaly_rejects_stop_with_deadman() -> None:
    report = scan_streams(
        {
            "action": [
                {
                    "schema": "jcheng.teleop.action.v1",
                    "tick_id": 1,
                    "t_mono_ns": 0,
                    "purpose": "stop",
                    "deadman": True,
                    "joint_positions_rad": [],
                    "joint_velocities_rad_s": [0.0],
                }
            ]
        },
        "mock",
    )
    assert not report.ok


def test_cli_replay_end_to_end(tmp_path: Path, capsys) -> None:
    root, capture_id = _record(tmp_path)
    code = cli.main(
        [
            "--capture-root",
            str(root),
            "--capture-id",
            capture_id,
            "--profile",
            str(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
            "--binding",
            str(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.out
    payload = json.loads(captured.out)
    assert payload["replay"]["status"] == "ok"
    assert payload["anomalies"]["status"] in {"ok", "warnings"}


def test_cli_rejects_a_profile_mismatch(tmp_path: Path, capsys) -> None:
    root, capture_id = _record(tmp_path)
    code = cli.main(
        [
            "--capture-root",
            str(root),
            "--capture-id",
            capture_id,
            "--profile",
            str(ROOT / "examples/piper_x_demo/profile.yaml"),
            "--binding",
            str(ROOT / "examples/piper_x_demo/binding.yaml"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "profile_hash" in captured.out


def test_replay_package_has_no_runtime_imports() -> None:
    import ast

    replay_dir = ROOT / "src/jcheng_teleop/replay"
    forbidden = ("rclpy", "jcheng_teleop.adapters.gateway", "socket", "subprocess", "requests")
    for path in replay_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        for module in modules:
            assert not any(
                module == item or module.startswith(item + ".") for item in forbidden
            ), f"{path.name} imports {module}"
