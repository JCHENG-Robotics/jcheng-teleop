"""Supervised-session authorization record (M6).

A hardware teleoperation session is only admissible with a separate, explicit,
per-session authorization that names the operator, the supervisor, the
workspace checklist, the robot profile, the contract and the exact motion
scope. This module validates that record offline; it never grants motion.

The record is teleop-local (`jcheng.teleop.authorization.v1`). The system layer
still owns the lease, deadman, limits and stop latch; this record only gates
whether the operator may start a session at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import math
from typing import Any, Mapping

from ..core.profile import ResolvedProfile

SCHEMA = "jcheng.teleop.authorization.v1"
SHA256_PREFIX = "sha256:"


class SupervisedError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(problems))


def _sha256(value: Any, field: str, problems: list[str]) -> None:
    if not isinstance(value, str) or not value.startswith(SHA256_PREFIX) or len(value) != 71:
        problems.append(f"{field} must be a sha256:<64 hex> value")


def _text(value: Any, field: str, problems: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{field} is required")
        return ""
    return value.strip()


def _time(value: Any, field: str, problems: list[str]) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        problems.append(f"{field} must be ISO 8601 with a timezone")
        return datetime.min
    if parsed.tzinfo is None:
        problems.append(f"{field} must carry a timezone")
    return parsed


@dataclass(frozen=True)
class SupervisedAuthorization:
    schema: str
    session_id: str
    operator_id: str
    supervisor_id: str
    authorization_ref: str
    workspace_clear: bool
    checklist_hash: str
    profile_id: str
    profile_hash: str
    contract_hash: str
    joint_names: tuple[str, ...]
    motion_scope: tuple[str, ...]
    max_velocity_rad_s: float
    issued_at: str
    expires_at: str
    notes: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SupervisedAuthorization":
        if not isinstance(raw, Mapping):
            raise SupervisedError(["authorization must be a mapping"])
        joint_names = raw.get("joint_names")
        scope = raw.get("motion_scope")
        return cls(
            schema=str(raw.get("schema", "")),
            session_id=str(raw.get("session_id", "")),
            operator_id=str(raw.get("operator_id", "")),
            supervisor_id=str(raw.get("supervisor_id", "")),
            authorization_ref=str(raw.get("authorization_ref", "")),
            workspace_clear=bool(raw.get("workspace_clear", False)),
            checklist_hash=str(raw.get("checklist_hash", "")),
            profile_id=str(raw.get("profile_id", "")),
            profile_hash=str(raw.get("profile_hash", "")),
            contract_hash=str(raw.get("contract_hash", "")),
            joint_names=tuple(joint_names) if isinstance(joint_names, list) else (),
            motion_scope=tuple(scope) if isinstance(scope, list) else (),
            max_velocity_rad_s=float(raw.get("max_velocity_rad_s", 0.0)),
            issued_at=str(raw.get("issued_at", "")),
            expires_at=str(raw.get("expires_at", "")),
            notes=str(raw.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "session_id": self.session_id,
            "operator_id": self.operator_id,
            "supervisor_id": self.supervisor_id,
            "authorization_ref": self.authorization_ref,
            "workspace_clear": self.workspace_clear,
            "checklist_hash": self.checklist_hash,
            "profile_id": self.profile_id,
            "profile_hash": self.profile_hash,
            "contract_hash": self.contract_hash,
            "joint_names": list(self.joint_names),
            "motion_scope": list(self.motion_scope),
            "max_velocity_rad_s": self.max_velocity_rad_s,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "notes": self.notes,
        }

    def record_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return SHA256_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def validate(
        self,
        *,
        profile: ResolvedProfile,
        contract_hash: str,
        now: datetime,
    ) -> None:
        problems: list[str] = []
        if self.schema != SCHEMA:
            problems.append(f"schema must be {SCHEMA}")
        _text(self.session_id, "session_id", problems)
        _text(self.operator_id, "operator_id", problems)
        _text(self.supervisor_id, "supervisor_id", problems)
        _text(self.authorization_ref, "authorization_ref", problems)
        if self.operator_id and self.supervisor_id and self.operator_id == self.supervisor_id:
            problems.append("operator_id and supervisor_id must be different people")
        if not self.workspace_clear:
            problems.append("workspace_clear must be true")
        _sha256(self.checklist_hash, "checklist_hash", problems)
        _sha256(self.profile_hash, "profile_hash", problems)
        _sha256(self.contract_hash, "contract_hash", problems)
        if self.profile_id != profile.profile_id:
            problems.append(
                f"profile_id mismatch: authorization {self.profile_id!r} vs {profile.profile_id!r}"
            )
        if self.profile_hash != profile.profile_hash:
            problems.append("profile_hash does not match the supplied profile")
        if self.contract_hash != contract_hash:
            problems.append("contract_hash does not match the pinned contract")
        if self.joint_names != profile.joint_names:
            problems.append(
                "joint_names must match the profile joint order exactly "
                f"(authorization {list(self.joint_names)} vs profile {list(profile.joint_names)})"
            )
        if not self.motion_scope:
            problems.append("motion_scope must not be empty")
        unknown = sorted(set(self.motion_scope) - set(self.joint_names))
        if unknown:
            problems.append(f"motion_scope has unknown joints: {unknown}")
        if len(set(self.motion_scope)) != len(self.motion_scope):
            problems.append("motion_scope has duplicate joints")
        if not math.isfinite(self.max_velocity_rad_s) or self.max_velocity_rad_s <= 0:
            problems.append("max_velocity_rad_s must be finite and positive")
        else:
            known_scope = [j for j in self.motion_scope if j in profile.joint_names]
            if known_scope:
                limit = min(profile.joint(joint).max_velocity_rad_s for joint in known_scope)
                if self.max_velocity_rad_s > limit:
                    problems.append(
                        f"max_velocity_rad_s {self.max_velocity_rad_s} exceeds the profile "
                        f"limit {limit} for the authorized scope"
                    )
        issued = _time(self.issued_at, "issued_at", problems)
        expires = _time(self.expires_at, "expires_at", problems)
        if issued.tzinfo is not None and expires.tzinfo is not None:
            if expires <= issued:
                problems.append("expires_at must be after issued_at")
            if expires - issued > timedelta(hours=8):
                problems.append("authorization window must not exceed 8 hours")
            if now < issued:
                problems.append("authorization is not valid yet")
            if now >= expires:
                problems.append("authorization has expired")
        if problems:
            raise SupervisedError(problems)
