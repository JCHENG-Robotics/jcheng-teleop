"""M7 mixed-source dataset index and correction provenance tests."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from jcheng_teleop.adapters.gateway.mock import MockGateway
from jcheng_teleop.adapters.input.virtual import VirtualInputSource
from jcheng_teleop.capture import CaptureMetadata, EpisodeRecorder, ProvenanceError
from jcheng_teleop.core.clock import ManualClock
from jcheng_teleop.core.model import InputSample, Mode
from jcheng_teleop.core.profile import load_binding, load_profile, resolve_profile
from jcheng_teleop.core.runner import TeleopRunner
from jcheng_teleop.core.session import SessionConfig, TeleopSession
from jcheng_teleop.export import CaptureEntry, DatasetError, build_index, capture_entry, write_index

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "sha256:" + "0" * 64
HASH = "sha256:" + "1" * 64


def _manifest(capture_id: str, source: str, *, env: str = "mock", correction=None, policy=None):
    manifest = {
        "schema": "jcheng.teleop.capture.v1",
        "capture_id": capture_id,
        "environment": {"environment_class": env, "source_class": source},
        "identity": {"profile_id": "armpi_ultra_demo", "profile_hash": HASH},
        "contract_hash": CONTRACT,
        "task": {"task_id": "task-1", "outcome": "unknown"},
    }
    if policy is not None:
        manifest["policy"] = policy
    if correction is not None:
        manifest["correction"] = correction
    return manifest


def _entry(capture_id: str, source: str, **kwargs) -> CaptureEntry:
    return CaptureEntry(capture_id=capture_id, manifest=_manifest(capture_id, source, **kwargs),
                        manifest_sha256=HASH)


def test_index_groups_by_source_class_and_keeps_environment() -> None:
    index = build_index(
        [
            _entry("policy-1", "policy_execution", policy={"policy_id": "p", "policy_version": "1"}),
            _entry(
                "correction-1",
                "human_correction",
                policy={"policy_id": "p", "policy_version": "1"},
                correction={
                    "corrected_from_capture_id": "policy-1",
                    "corrected_from_tick_id": 12,
                    "policy_action_seq": 7,
                },
            ),
            _entry("demo-1", "human_teleop"),
        ]
    )
    assert index["schema"] == "jcheng.teleop.dataset.v1"
    assert index["counts"]["episodes"] == 3
    assert index["groups"]["human_correction"] == ["correction-1"]
    assert index["mixed_source_classes"] is True
    assert index["mixed_environments"] is False
    assert all(ep["environment_class"] == "mock" for ep in index["episodes"])


def test_duplicate_capture_is_refused() -> None:
    with pytest.raises(DatasetError, match="duplicate capture_id"):
        build_index([_entry("dup", "human_teleop"), _entry("dup", "human_teleop")])


def test_unsupported_source_class_is_refused() -> None:
    with pytest.raises(DatasetError, match="unsupported source class"):
        build_index([_entry("x", "replay")])


def test_correction_reference_must_exist() -> None:
    with pytest.raises(DatasetError, match="is not in the index"):
        build_index(
            [
                _entry(
                    "correction-1",
                    "human_correction",
                    policy={"policy_id": "p", "policy_version": "1"},
                    correction={
                        "corrected_from_capture_id": "missing",
                        "policy_action_seq": 1,
                    },
                )
            ]
        )


def test_external_correction_can_be_allowed() -> None:
    index = build_index(
        [
            _entry(
                "correction-1",
                "human_correction",
                policy={"policy_id": "p", "policy_version": "1"},
                correction={
                    "corrected_from_capture_id": "external-policy",
                    "policy_action_seq": 1,
                },
            )
        ],
        allow_external_corrections=True,
    )
    assert index["allow_external_corrections"] is True


def test_correction_cannot_reference_itself() -> None:
    with pytest.raises(DatasetError, match="cannot reference itself"):
        build_index(
            [
                _entry(
                    "correction-1",
                    "human_correction",
                    policy={"policy_id": "p", "policy_version": "1"},
                    correction={
                        "corrected_from_capture_id": "correction-1",
                        "policy_action_seq": 1,
                    },
                )
            ]
        )


def test_correction_reference_without_correction_source_is_refused() -> None:
    with pytest.raises(DatasetError, match="without human_correction"):
        build_index(
            [
                _entry(
                    "demo-1",
                    "human_teleop",
                    correction={"corrected_from_capture_id": "other"},
                )
            ]
        )


def test_correction_metadata_requires_a_prior_policy_action() -> None:
    base = dict(
        capture_id="corr",
        created_at="2026-11-26T00:00:00+00:00",
        teleop_version="0.3.0",
        contract_hash=CONTRACT,
        profile_id="armpi_ultra_demo",
        profile_hash=HASH,
        binding_hash=HASH,
        environment_class="hardware",
        source_class="human_correction",
        session_id="s",
        task_id="t",
        task_description="correction",
        joint_names=("joint1",),
        profile_source="system",
        operator_id="op",
        operator_role="teleoperator",
        supervisor_id="sup",
        authorization_ref="auth",
        policy_id="p",
        policy_version="1",
    )
    with pytest.raises(ProvenanceError, match="corrected_from_capture_id"):
        CaptureMetadata(**base).validate()
    CaptureMetadata(
        **base,
        corrected_from_capture_id="policy-cap",
        policy_action_seq=3,
    ).validate()


def test_scripted_capture_cannot_carry_a_correction_reference() -> None:
    with pytest.raises(ProvenanceError, match="only valid for human_correction"):
        CaptureMetadata(
            capture_id="s",
            created_at="2026-11-26T00:00:00+00:00",
            teleop_version="0.3.0",
            contract_hash=CONTRACT,
            profile_id="armpi_ultra_demo",
            profile_hash=HASH,
            binding_hash=HASH,
            environment_class="mock",
            source_class="scripted",
            session_id="s",
            task_id="t",
            task_description="x",
            joint_names=("joint1",),
            generator_id="g",
            generator_seed=0,
            generator_config_hash=HASH,
            corrected_from_capture_id="policy-cap",
        ).validate()


def _record(tmp_path: Path, capture_id: str = "index-cap") -> Path:
    resolved = resolve_profile(
        load_profile(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
        load_binding(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
    )
    clock = ManualClock(0)
    gateway = MockGateway(
        clock, contract_hash=CONTRACT, profile_hash=resolved.profile_hash,
        joint_count=resolved.joint_count,
    )
    session = TeleopSession(
        resolved, gateway, clock,
        config=SessionConfig(deadman_ms=300, tick_ms=20, max_rate_hz=50, contract_hash=CONTRACT),
    )
    session.start()
    metadata = CaptureMetadata(
        capture_id=capture_id,
        created_at="2026-11-26T00:00:00+00:00",
        teleop_version="0.3.0",
        contract_hash=CONTRACT,
        profile_id=resolved.profile_id,
        profile_hash=resolved.profile_hash,
        binding_hash=resolved.binding.binding_hash,
        environment_class="mock",
        source_class="scripted",
        session_id=capture_id,
        task_id="index",
        task_description="index test",
        joint_names=resolved.joint_names,
        generator_id="index-test",
        generator_seed=0,
        generator_config_hash=HASH,
    )
    recorder = EpisodeRecorder(tmp_path, metadata)
    samples = [
        InputSample(
            schema=InputSample.SCHEMA, source_id="virtual", source_class="virtual", seq=i,
            t_source_ns=i * 20_000_000, t_host_mono_ns=i * 20_000_000,
            mode=Mode.JOINT_VELOCITY,
            joint_velocities_rad_s=(0.2,) + (0.0,) * (resolved.joint_count - 1),
            deadman=True, profile_id=resolved.profile_id,
        )
        for i in range(6)
    ]
    runner = TeleopRunner(
        session=session, source=VirtualInputSource(samples), clock=clock,
        observer=lambda result, sample, now: (recorder.observe(result, sample, now), not recorder.faulted)[1],
    )
    runner.run_ticks(6)
    session.close()
    recorder.close(outcome="unknown", outcome_source="automatic")
    return tmp_path


def test_capture_entry_and_index_file(tmp_path: Path) -> None:
    root = _record(tmp_path)
    entry = capture_entry(root, "index-cap")
    index = build_index([entry])
    assert index["counts"]["episodes"] == 1
    written = write_index(tmp_path / "dataset-index.json", index)
    assert written["bytes"] > 0
    saved = json.loads((tmp_path / "dataset-index.json").read_text())
    assert saved["episodes"][0]["capture_id"] == "index-cap"
    assert saved["episodes"][0]["manifest_sha256"] == entry.manifest_sha256


def test_index_write_refuses_the_repository() -> None:
    with pytest.raises(ValueError, match="outside a git worktree"):
        write_index(ROOT / "dataset-index.json", {"schema": "jcheng.teleop.dataset.v1"})


def test_cli_builds_an_index(tmp_path: Path, capsys) -> None:
    from jcheng_teleop.export import cli

    root = _record(tmp_path)
    output = tmp_path / "cli-index.json"
    code = cli.main(
        [
            "--capture-root",
            str(root),
            "--capture-id",
            "index-cap",
            "--out",
            str(output),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.out
    payload = json.loads(captured.out)
    assert payload["index"]["episodes"] == 1
    assert output.is_file()
