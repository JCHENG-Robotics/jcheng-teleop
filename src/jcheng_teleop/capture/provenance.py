"""Capture identity and provenance for M3.

The capture package is teleop-local (`jcheng.teleop.capture.v1`). It is not the
learning dataset contract; an adapter converts it through the learning-owned
writer. Environment and source classes are immutable and are never relabelled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any

SCHEMA = "jcheng.teleop.capture.v1"
ENVIRONMENT_CLASSES = frozenset({"mock", "simulation", "hardware"})
SOURCE_CLASSES = frozenset(
    {
        "human_teleop",
        "human_correction",
        "autonomous_grasp",
        "policy_execution",
        "scripted",
    }
)
OUTCOMES = frozenset({"success", "failure", "unknown", "aborted"})
OUTCOME_SOURCES = frozenset({"operator", "automatic", "policy"})
OPERATOR_ROLES = frozenset({"teleoperator", "supervisor", "annotator"})
PROFILE_SOURCES = frozenset({"system", "simulation", "fixture"})
_CAPTURE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class ProvenanceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProvenanceError(message)


def _required(value: str | None, field_name: str) -> str:
    _require(bool(value and str(value).strip()), f"{field_name} is required")
    return str(value)


@dataclass(frozen=True)
class CaptureMetadata:
    """Identity, environment and session provenance of one capture."""

    capture_id: str
    created_at: str
    teleop_version: str
    contract_hash: str
    profile_id: str
    profile_hash: str
    binding_hash: str
    environment_class: str
    source_class: str
    session_id: str
    task_id: str
    task_description: str
    joint_names: tuple[str, ...]
    operator_id: str | None = None
    operator_role: str | None = None
    supervisor_id: str | None = None
    authorization_ref: str | None = None
    sim_truth_label: str | None = None
    simulator_repo: str | None = None
    simulator_version: str | None = None
    generator_id: str | None = None
    generator_seed: int | None = None
    generator_config_hash: str | None = None
    policy_id: str | None = None
    policy_version: str | None = None
    profile_source: str = "fixture"
    has_gripper: bool = False
    clock_id: str = "host_mono"
    clock_source: str = "operator_host_monotonic"
    offset_uncertainty_ns: int | None = None
    nominal_hz: float = 50.0
    deadman_ms: int = 300
    tick_ms: int = 20
    git_commit: str | None = None
    calibration_id: str | None = None
    limitations: tuple[str, ...] = ()

    def validate(self) -> "CaptureMetadata":
        _require(bool(_CAPTURE_ID.match(self.capture_id)), "capture_id must be a safe path segment")
        _require(".." not in self.capture_id, "capture_id must not contain '..'")
        try:
            created = datetime.fromisoformat(self.created_at)
        except ValueError as exc:
            raise ProvenanceError("created_at must be ISO 8601") from exc
        _require(created.tzinfo is not None, "created_at must carry a timezone")
        for name in ("teleop_version", "profile_id", "session_id", "task_id"):
            _required(getattr(self, name), name)
        for name in ("contract_hash", "profile_hash", "binding_hash"):
            _require(
                bool(_SHA256.match(str(getattr(self, name)))),
                f"{name} must be a sha256:<64 hex> value",
            )
        if self.generator_config_hash is not None:
            _require(
                bool(_SHA256.match(self.generator_config_hash)),
                "generator_config_hash must be a sha256:<64 hex> value",
            )
        _require(
            self.environment_class in ENVIRONMENT_CLASSES,
            f"unsupported environment_class: {self.environment_class!r}",
        )
        _require(
            self.source_class in SOURCE_CLASSES,
            f"unsupported source_class: {self.source_class!r} "
            "(replay is a derived artifact, not a new capture)",
        )
        _require(self.profile_source in PROFILE_SOURCES, "unsupported profile_source")
        _require(bool(self.joint_names), "joint_names must not be empty")
        _require(len(set(self.joint_names)) == len(self.joint_names), "duplicate joint name")
        _require(self.nominal_hz > 0, "nominal_hz must be positive")
        _require(self.tick_ms > 0, "tick_ms must be positive")
        _require(self.deadman_ms >= 0, "deadman_ms must be non-negative")

        if self.environment_class == "hardware":
            _required(self.operator_id, "operator_id (hardware)")
            _required(self.supervisor_id, "supervisor_id (hardware)")
            _required(self.authorization_ref, "authorization_ref (hardware)")
            _require(
                self.operator_role in OPERATOR_ROLES,
                "operator_role must be teleoperator, supervisor or annotator (hardware)",
            )
            _require(
                self.profile_source == "system",
                "hardware requires profile_source=system",
            )
            _require(
                self.sim_truth_label is None,
                "hardware must not carry a sim_truth_label",
            )
        else:
            _require(
                self.operator_role in (None,) + tuple(OPERATOR_ROLES),
                "unsupported operator_role",
            )
            _require(
                self.profile_source != "system",
                f"{self.environment_class} must not claim the system hardware profile",
            )

        if self.environment_class == "simulation":
            _required(self.sim_truth_label, "sim_truth_label (simulation)")
            _required(self.simulator_repo, "simulator_repo (simulation)")
            _required(self.simulator_version, "simulator_version (simulation)")
        elif self.sim_truth_label is not None:
            raise ProvenanceError("sim_truth_label is only valid for simulation")

        if self.source_class == "scripted":
            _required(self.generator_id, "generator_id (scripted)")
            _require(self.generator_seed is not None, "generator_seed (scripted)")
            _required(self.generator_config_hash, "generator_config_hash (scripted)")
        if self.source_class in {"policy_execution", "human_correction"}:
            _required(self.policy_id, "policy_id (policy execution/correction)")
            _required(self.policy_version, "policy_version (policy execution/correction)")
        return self

    def to_manifest(
        self,
        *,
        ended_at: str,
        files: list[dict[str, Any]],
        stream_counts: dict[str, dict[str, int]],
        outcome: str,
        outcome_source: str,
        quality_flags: list[str],
        dropped_priority: int,
        recorder_fault: str | None,
    ) -> dict[str, Any]:
        _require(outcome in OUTCOMES, f"unsupported outcome: {outcome!r}")
        _require(outcome_source in OUTCOME_SOURCES, f"unsupported outcome_source: {outcome_source!r}")
        _require(
            not (self.environment_class == "hardware" and self.source_class == "scripted")
            or self.authorization_ref is not None,
            "hardware scripted capture requires an authorization_ref",
        )
        limitations = list(self.limitations)
        if recorder_fault:
            limitations.append(f"recorder fault: {recorder_fault}")
        if dropped_priority:
            limitations.append(f"{dropped_priority} priority rows dropped")
        return {
            "schema": SCHEMA,
            "capture_id": self.capture_id,
            "created_at": self.created_at,
            "ended_at": ended_at,
            "teleop_version": self.teleop_version,
            "git_commit": self.git_commit,
            "contract_hash": self.contract_hash,
            "identity": {
                "profile_id": self.profile_id,
                "profile_hash": self.profile_hash,
                "binding_hash": self.binding_hash,
                "profile_source": self.profile_source,
                "joint_names": list(self.joint_names),
                "dof": len(self.joint_names),
                "has_gripper": self.has_gripper,
                "calibration_id": self.calibration_id,
            },
            "environment": {
                "environment_class": self.environment_class,
                "source_class": self.source_class,
                "sim_truth_label": self.sim_truth_label,
                "simulator_repo": self.simulator_repo,
                "simulator_version": self.simulator_version,
                "generator_id": self.generator_id,
                "generator_seed": self.generator_seed,
                "generator_config_hash": self.generator_config_hash,
                "profile_source": self.profile_source,
            },
            "session": {
                "session_id": self.session_id,
                "operator_id": self.operator_id,
                "operator_role": self.operator_role,
                "supervisor_id": self.supervisor_id,
                "authorization_ref": self.authorization_ref,
                "lease_ref_hash": None,
            },
            "task": {
                "task_id": self.task_id,
                "task_description": self.task_description,
                "outcome": outcome,
                "outcome_source": outcome_source,
            },
            "policy": {
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "checkpoint_hash": None,
                "action_chunk": None,
            },
            "time": {
                "clock_source": self.clock_source,
                "clock_id": self.clock_id,
                "offset_ns": 0,
                "offset_uncertainty_ns": self.offset_uncertainty_ns,
                "nominal_fps": self.nominal_hz,
                "deadman_ms": self.deadman_ms,
                "tick_ms": self.tick_ms,
            },
            "capture": {
                "files": files,
                "frame_count": 0,
                "episode_count": 1,
                "rows": stream_counts,
                "quality_flags": quality_flags,
                "limitations": limitations,
            },
            "consent": {
                "human_present": self.operator_id is not None,
                "consent_ref": None,
                "redaction": "not_applicable",
            },
        }
