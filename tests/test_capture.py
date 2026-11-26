"""M3 capture tests: provenance, non-blocking writer, seal/verify, CLI."""

from __future__ import annotations

from pathlib import Path
import json
import time

import pytest

from jcheng_teleop.capture import (
    SCHEMA,
    CaptureMetadata,
    CapturePathError,
    CaptureWriter,
    EpisodeRecorder,
    ObservationSample,
    ProvenanceError,
    verify_capture,
)
from jcheng_teleop.core.clock import ManualClock
from jcheng_teleop.core.profile import load_binding, load_profile, resolve_profile
from jcheng_teleop.core.runner import TeleopRunner
from jcheng_teleop.core.session import SessionConfig, TeleopSession
from jcheng_teleop.adapters.gateway.mock import MockGateway
from jcheng_teleop.adapters.input.virtual import VirtualInputSource
from jcheng_teleop.core.model import InputSample, Mode
from jcheng_teleop import cli

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "sha256:" + "0" * 64
HASH = "sha256:" + "1" * 64


def metadata(**overrides) -> CaptureMetadata:
    base = dict(
        capture_id="cap-test",
        created_at="2026-11-26T00:00:00+00:00",
        teleop_version="0.3.0",
        contract_hash=CONTRACT,
        profile_id="armpi_ultra_demo",
        profile_hash=HASH,
        binding_hash=HASH,
        environment_class="mock",
        source_class="scripted",
        session_id="session-1",
        task_id="task-1",
        task_description="capture test",
        joint_names=("joint1", "joint2"),
        generator_id="pytest",
        generator_seed=0,
        generator_config_hash=HASH,
        limitations=("test only",),
    )
    base.update(overrides)
    return CaptureMetadata(**base)


def _session():
    clock = ManualClock(0)
    profile = resolve_profile(
        load_profile(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
        load_binding(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
    )
    gateway = MockGateway(
        clock,
        contract_hash=CONTRACT,
        profile_hash=profile.profile_hash,
        joint_count=profile.joint_count,
    )
    session = TeleopSession(
        profile,
        gateway,
        clock,
        config=SessionConfig(
            deadman_ms=300, tick_ms=20, max_rate_hz=50, contract_hash=CONTRACT
        ),
    )
    session.start()
    return clock, profile, session


def _source(profile, ticks: int) -> VirtualInputSource:
    samples = []
    for index in range(ticks):
        values = [0.0] * profile.joint_count
        values[0] = 0.2
        samples.append(
            InputSample(
                schema=InputSample.SCHEMA,
                source_id="virtual_test",
                source_class="virtual",
                seq=index,
                t_source_ns=index * 20_000_000,
                t_host_mono_ns=index * 20_000_000,
                mode=Mode.JOINT_VELOCITY,
                joint_velocities_rad_s=tuple(values),
                deadman=True,
                profile_id=profile.profile_id,
            )
        )
    return VirtualInputSource(samples)


# ---- provenance ----


def test_mock_scripted_metadata_is_valid() -> None:
    assert metadata().validate() is not None


def test_simulation_requires_truth_label() -> None:
    with pytest.raises(ProvenanceError, match="sim_truth_label"):
        metadata(
            environment_class="simulation",
            source_class="human_teleop",
            profile_source="simulation",
        ).validate()


def test_simulation_cannot_claim_system_profile() -> None:
    with pytest.raises(ProvenanceError, match="system hardware profile"):
        metadata(
            environment_class="simulation",
            source_class="human_teleop",
            profile_source="system",
            sim_truth_label="/sim/truth/source=simulated",
            simulator_repo="jcheng-simulation",
            simulator_version="0.1.0",
        ).validate()


def test_hardware_requires_authorization_and_supervisor() -> None:
    with pytest.raises(ProvenanceError, match="operator_id|supervisor_id|authorization_ref"):
        metadata(environment_class="hardware", source_class="human_teleop").validate()


def test_hardware_valid_with_authorization() -> None:
    meta = metadata(
        environment_class="hardware",
        source_class="human_teleop",
        profile_source="system",
        operator_id="op-1",
        operator_role="teleoperator",
        supervisor_id="sup-1",
        authorization_ref="auth-20261126",
    )
    assert meta.validate() is not None


def test_replay_is_not_a_new_capture() -> None:
    with pytest.raises(ProvenanceError, match="replay"):
        metadata(source_class="replay").validate()


def test_policy_execution_requires_policy_id() -> None:
    with pytest.raises(ProvenanceError, match="policy_id"):
        metadata(source_class="policy_execution").validate()


def test_sim_truth_label_is_rejected_on_mock() -> None:
    with pytest.raises(ProvenanceError, match="only valid for simulation"):
        metadata(sim_truth_label="/sim/truth/source=simulated").validate()


# ---- writer ----


def test_capture_root_inside_worktree_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(CapturePathError, match="outside a git worktree"):
        CaptureWriter(repo / "captures", "cap-1")


def test_bounded_queue_drops_normal_rows_first(tmp_path: Path) -> None:
    writer = CaptureWriter(tmp_path, "cap-1", queue_limit=3, start_thread=False)
    try:
        assert writer.record("input", {"schema": "x", "tick_id": 0})
        assert writer.record("input", {"schema": "x", "tick_id": 1})
        assert writer.record("events", {"schema": "x", "tick_id": 2}, priority=True)
        # Full: a new normal row drops the oldest normal row, not the priority row.
        assert writer.record("input", {"schema": "x", "tick_id": 3})
        assert writer.dropped["input"] == 1
        assert writer.record("events", {"schema": "x", "tick_id": 4}, priority=True)
        assert writer.dropped_priority == 0
    finally:
        seal = writer.close()
    assert seal["fault"] is None


def test_record_never_raises_after_close(tmp_path: Path) -> None:
    writer = CaptureWriter(tmp_path, "cap-1", start_thread=False)
    writer.close()
    assert writer.record("input", {"tick_id": 0}) is False
    assert writer.dropped["input"] == 1


def test_storage_fault_marks_writer_and_never_propagates(tmp_path: Path, monkeypatch) -> None:
    writer = CaptureWriter(tmp_path, "cap-1", queue_limit=16)
    monkeypatch.setattr(
        writer, "_write_row", lambda stream, row: (_ for _ in ()).throw(OSError("disk full"))
    )
    assert writer.record("input", {"tick_id": 0}) is True
    deadline = time.monotonic() + 5.0
    while not writer.faulted and time.monotonic() < deadline:
        time.sleep(0.01)
    assert writer.faulted
    assert writer.record("input", {"tick_id": 1}) is False
    seal = writer.close()
    assert seal["fault"] is not None


# ---- recorder / runner ----


def _run_with_recorder(tmp_path: Path, ticks: int = 6, capture_id: str = "cap-1"):
    clock, profile, session = _session()
    meta = metadata(
        capture_id=capture_id,
        profile_id=profile.profile_id,
        profile_hash=profile.profile_hash,
        binding_hash=profile.binding.binding_hash,
        joint_names=profile.joint_names,
    )
    recorder = EpisodeRecorder(tmp_path, meta)
    runner = TeleopRunner(
        session=session,
        source=_source(profile, ticks),
        clock=clock,
        observer=lambda result, sample, now: (
            recorder.observe(result, sample, now),
            not recorder.faulted,
        )[1],
    )
    runner.run_ticks(ticks)
    session.close()
    seal = recorder.close(outcome="unknown", outcome_source="automatic")
    return recorder, seal


def test_seal_writes_manifest_hashes_and_verifies(tmp_path: Path) -> None:
    recorder, seal = _run_with_recorder(tmp_path)
    assert seal.fault is None
    capture = tmp_path / "cap-1"
    for name in ("input.jsonl", "action.jsonl", "command.jsonl", "observation.jsonl",
                 "events.jsonl", "manifest.json", "SHA256SUMS"):
        assert (capture / name).is_file(), name
    manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == SCHEMA
    assert manifest["environment"]["environment_class"] == "mock"
    assert manifest["environment"]["source_class"] == "scripted"
    assert manifest["task"]["outcome"] == "unknown"
    assert seal.written["input"] > 0
    assert seal.written["action"] > 0
    report = verify_capture(tmp_path, "cap-1")
    assert report.ok, report.errors
    assert report.status == "valid"
    assert report.row_counts["input"] > 0


def test_raw_lease_id_is_not_written(tmp_path: Path) -> None:
    recorder, seal = _run_with_recorder(tmp_path)
    text = (tmp_path / "cap-1" / "action.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    assert rows
    for row in rows:
        if row.get("lease_ref"):
            assert row["lease_ref"].startswith("sha256:")
    assert "lease-" not in text


def test_tampered_capture_fails_verification(tmp_path: Path) -> None:
    _recorder, seal = _run_with_recorder(tmp_path)
    path = tmp_path / "cap-1" / "input.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"tampered":true}\n', encoding="utf-8")
    report = verify_capture(tmp_path, "cap-1")
    assert report.status == "invalid"
    assert any("hash mismatch" in error or "SHA256SUMS" in error for error in report.errors)


def test_deterministic_streams_for_identical_runs(tmp_path: Path) -> None:
    _recorder_a, seal_a = _run_with_recorder(tmp_path / "a", capture_id="cap")
    _recorder_b, seal_b = _run_with_recorder(tmp_path / "b", capture_id="cap")
    for name in ("input.jsonl", "action.jsonl", "events.jsonl"):
        a = (tmp_path / "a" / "cap" / name).read_bytes()
        b = (tmp_path / "b" / "cap" / name).read_bytes()
        assert a == b, name


def _observation(**overrides) -> ObservationSample:
    base = dict(
        topic="/jcheng/telemetry/state",
        source="jcheng_runtime/mock",
        seq=1,
        fresh=True,
        joint_names=("joint1", "joint2"),
        positions=(0.0, 0.0),
        velocities=(0.0, 0.0),
        gripper_position=0.0,
        base_duty=(0.0, 0.0, 0.0, 0.0),
        battery_voltage=7.4,
        profile_hash=HASH,
        truth="commanded",
        verification="timed",
        stamp_ns=0,
        received_ns=0,
    )
    base.update(overrides)
    return ObservationSample(**base)


def _record_observations(tmp_path: Path, meta: CaptureMetadata, *observations) -> EpisodeRecorder:
    recorder = EpisodeRecorder(tmp_path, meta)
    for index, observation in enumerate(observations):
        recorder.record_observation(observation, index * 20_000_000)
    assert recorder.close().fault is None
    return recorder


def test_mock_capture_records_commanded_observations(tmp_path: Path) -> None:
    recorder = _record_observations(tmp_path, metadata(), _observation(), _observation(seq=2))
    rows = [
        json.loads(line)
        for line in (tmp_path / "cap-test" / "observation.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 2
    assert rows[0]["truth"] == "commanded"
    assert rows[0]["verification"] == "timed"
    assert rows[0]["joint_names"] == ["joint1", "joint2"]
    assert recorder.rejected_observations == 0
    assert verify_capture(tmp_path, "cap-test").ok


def test_mock_capture_rejects_a_bus_label_and_records_an_event(tmp_path: Path) -> None:
    recorder = _record_observations(
        tmp_path, metadata(), _observation(truth="measured", verification="bus")
    )
    assert recorder.rejected_observations == 1
    observation_rows = (tmp_path / "cap-test" / "observation.jsonl").read_text(encoding="utf-8")
    assert observation_rows.strip() == ""
    events = (tmp_path / "cap-test" / "events.jsonl").read_text(encoding="utf-8")
    assert "OBSERVATION_REJECTED" in events
    report = verify_capture(tmp_path, "cap-test")
    assert report.ok
    assert report.status == "degraded"


def test_simulation_capture_accepts_simulated_state(tmp_path: Path) -> None:
    meta = metadata(
        environment_class="simulation",
        source_class="human_teleop",
        profile_source="simulation",
        sim_truth_label="/sim/truth/source=simulated",
        simulator_repo="jcheng-simulation",
        simulator_version="0.1.0",
    )
    recorder = _record_observations(
        tmp_path,
        meta,
        _observation(truth="measured", verification="simulated", source="jcheng_runtime/sim_bridge"),
    )
    assert recorder.rejected_observations == 0
    report = verify_capture(tmp_path, "cap-test")
    assert report.ok, report.errors


def test_simulation_capture_rejects_a_bus_label(tmp_path: Path) -> None:
    meta = metadata(
        environment_class="simulation",
        source_class="human_teleop",
        profile_source="simulation",
        sim_truth_label="/sim/truth/source=simulated",
        simulator_repo="jcheng-simulation",
        simulator_version="0.1.0",
    )
    recorder = _record_observations(
        tmp_path, meta, _observation(truth="measured", verification="bus")
    )
    assert recorder.rejected_observations == 1


def test_hardware_capture_accepts_a_bus_measurement(tmp_path: Path) -> None:
    meta = metadata(
        environment_class="hardware",
        source_class="human_teleop",
        profile_source="system",
        operator_id="op-1",
        operator_role="teleoperator",
        supervisor_id="sup-1",
        authorization_ref="auth-20261126",
    )
    recorder = _record_observations(
        tmp_path, meta, _observation(truth="measured", verification="bus", source="jcheng_telemetry")
    )
    assert recorder.rejected_observations == 0


def test_observation_length_mismatch_is_rejected(tmp_path: Path) -> None:
    recorder = _record_observations(
        tmp_path, metadata(), _observation(positions=(0.0,))
    )
    assert recorder.rejected_observations == 1


# ---- runner observer contract ----


def test_observer_exception_is_counted_and_run_continues() -> None:
    clock, profile, session = _session()
    calls = {"count": 0}

    def observer(result, sample, now):
        calls["count"] += 1
        raise RuntimeError("recorder bug")

    runner = TeleopRunner(
        session=session, source=_source(profile, 5), clock=clock, observer=observer
    )
    results = runner.run_ticks(5)
    session.close()
    assert len(results) == 5
    assert runner.observer_errors == 5
    assert calls["count"] == 5


def test_observer_false_requests_system_stop() -> None:
    clock, profile, session = _session()
    calls = {"count": 0}

    def observer(result, sample, now):
        calls["count"] += 1
        return calls["count"] < 2

    runner = TeleopRunner(
        session=session, source=_source(profile, 10), clock=clock, observer=observer
    )
    results = runner.run_ticks(10)
    session.close()
    assert len(results) == 3  # 2 normal ticks + the stop tick
    assert results[-1].stop_sent is True
    assert any(event.code for event in results[-1].events)


# ---- CLI ----


def test_cli_records_a_valid_capture(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            "--profile",
            str(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
            "--binding",
            str(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
            "--ticks",
            "8",
            "--record",
            str(tmp_path),
            "--capture-id",
            "cli-cap",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    summary = json.loads(captured.out)
    assert summary["capture"]["verify"] == "valid"
    manifest = json.loads((tmp_path / "cli-cap" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["environment"]["environment_class"] == "mock"
    assert manifest["environment"]["source_class"] == "scripted"
    assert manifest["environment"]["sim_truth_label"] is None
    assert manifest["identity"]["profile_id"] == "armpi_ultra_demo"


def test_cli_refuses_a_capture_root_inside_the_repository(capsys) -> None:
    exit_code = cli.main(
        [
            "--profile",
            str(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
            "--binding",
            str(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
            "--ticks",
            "2",
            "--record",
            str(ROOT / "captures"),
        ]
    )
    assert exit_code == 3
    assert "outside a git worktree" in capsys.readouterr().err
    assert not (ROOT / "captures").exists()
