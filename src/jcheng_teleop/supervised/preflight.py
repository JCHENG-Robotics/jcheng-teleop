"""Offline M6 preflight: validate an authorization and report hardware blockers.

Preflight never contacts the system, the robot or a device. A passing
authorization means "the paperwork and profile are consistent", not "motion is
allowed": every M6 hardware blocker is reported explicitly and
`hardware_ready` stays false until the system streaming path and stop
confirmation exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.profile import ResolvedProfile
from .authorization import SupervisedAuthorization, SupervisedError

HARDWARE_BLOCKERS = (
    "system streaming executor missing: jcheng_vendor serializes one joint per "
    "JOINT_STEP; the vendor ServosPosition vector exists, but no privileged "
    "bridge and no measured rate/interpolation (B2)",
    "TeleopCommand v0.2 (joint position, gripper, session/provenance) is not "
    "approved (P-001/B3)",
    "stop confirmation is open: StopResult has no confirmation field (R5/B9)",
    "the platform has no e-stop, brake, encoder or self-collision model",
    "PiPER X canonical profile v2 is not approved; only ArmPi's bus-servo "
    "profile is expressible (B4)",
)


@dataclass(frozen=True)
class PreflightReport:
    status: str                  # "authorized" | "refused"
    errors: tuple[str, ...]
    blockers: tuple[str, ...]
    hardware_ready: bool
    authorization_hash: str
    session: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "jcheng.teleop.preflight.v1",
            "status": self.status,
            "errors": list(self.errors),
            "blockers": list(self.blockers),
            "hardware_ready": self.hardware_ready,
            "authorization_hash": self.authorization_hash,
            "session": self.session,
        }


def run_preflight(
    authorization: SupervisedAuthorization,
    profile: ResolvedProfile,
    *,
    contract_hash: str,
    now: datetime,
) -> PreflightReport:
    errors: tuple[str, ...] = ()
    try:
        authorization.validate(
            profile=profile, contract_hash=contract_hash, now=now
        )
    except SupervisedError as exc:
        errors = exc.problems
    session = {
        "session_id": authorization.session_id,
        "operator_id": authorization.operator_id,
        "supervisor_id": authorization.supervisor_id,
        "authorization_ref": authorization.authorization_ref,
        "profile_id": authorization.profile_id,
        "profile_hash": authorization.profile_hash,
        "contract_hash": authorization.contract_hash,
        "motion_scope": list(authorization.motion_scope),
        "max_velocity_rad_s": authorization.max_velocity_rad_s,
        "issued_at": authorization.issued_at,
        "expires_at": authorization.expires_at,
    }
    return PreflightReport(
        status="refused" if errors else "authorized",
        errors=errors,
        blockers=HARDWARE_BLOCKERS,
        hardware_ready=False,
        authorization_hash=authorization.record_hash(),
        session=session,
    )
