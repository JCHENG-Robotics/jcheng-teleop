"""In-process gateway mock for M1.

This is a semantic fake, not a system emulator. It implements admission,
lease, state, submit and stop behavior and can inject faults. It never opens a
socket or connects to a robot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core.clock import Clock
from ...core.gateway import (
    GatewayContractMismatch,
    GatewayError,
    GatewayUnavailable,
)
from ...core.model import (
    ActionIntent,
    Admission,
    GatewayResult,
    Lease,
    LeaseRequest,
    Mode,
    RobotStateView,
    StopResult,
)


class MockGateway:
    def __init__(
        self,
        clock: Clock,
        *,
        contract_hash: str,
        profile_hash: str,
        joint_count: int,
        supported_modes: set[str] | None = None,
    ) -> None:
        self.clock = clock
        self.contract_hash = contract_hash
        self.profile_hash = profile_hash
        self.joint_count = joint_count
        self.supported_modes = set(supported_modes or {Mode.JOINT_VELOCITY.value})
        self.positions = [0.0] * joint_count
        self.velocities = [0.0] * joint_count
        self.gripper = 0.0
        self.fresh = True
        self.truth = "mock"
        self.verification = "none"
        self.leases: dict[str, Lease] = {}
        self.revoked: set[str] = set()
        self.submitted: list[ActionIntent] = []
        self.stop_requests: list[str] = []
        self.acquire_requests: list[LeaseRequest] = []
        self.faults: set[str] = set()
        self._counter = 0
        self._last_seq: dict[str, int] = {}

    # ---- test controls ----

    def fail(self, *faults: str) -> None:
        self.faults.update(faults)

    def clear_faults(self) -> None:
        self.faults.clear()

    def revoke(self, lease_id: str) -> None:
        self.leases.pop(lease_id, None)
        self.revoked.add(lease_id)

    def set_stale(self, stale: bool = True) -> None:
        self.fresh = not stale

    def set_positions(self, positions: list[float]) -> None:
        if len(positions) != self.joint_count:
            raise ValueError("position length mismatch")
        self.positions = [float(value) for value in positions]

    # ---- port ----

    def admit(self) -> Admission:
        if "admit_unavailable" in self.faults:
            raise GatewayUnavailable("mock admission unavailable")
        if "contract_mismatch" in self.faults:
            raise GatewayContractMismatch("mock contract mismatch")
        return Admission(
            contract_hash=self.contract_hash,
            profile_hash=self.profile_hash,
            mock=True,
            capabilities=("mock",),
        )

    def acquire(self, request: LeaseRequest) -> Lease:
        if "lease_unavailable" in self.faults:
            raise GatewayUnavailable("mock lease unavailable")
        if request.contract_hash != self.contract_hash:
            raise GatewayContractMismatch("lease contract mismatch")
        if not request.holder.strip():
            raise GatewayError("holder is required")
        if request.scope not in {"arm", "gripper", "base", "full"}:
            raise GatewayError(f"unknown scope {request.scope}")
        if request.ttl_ms <= 0:
            raise GatewayError("ttl_ms must be positive")
        now = self.clock.now_ns()
        for lease in self.leases.values():
            if lease.active(now) and (lease.scope == "full" or request.scope == "full" or lease.scope == request.scope):
                if lease.priority >= request.priority:
                    raise GatewayError(f"LEASE_CONFLICT: held by {lease.holder}")
        self._counter += 1
        lease = Lease(
            lease_id=f"mock-lease-{self._counter:04d}",
            holder=request.holder,
            scope=request.scope,
            mode=request.mode,
            priority=request.priority,
            deadman_required=request.deadman_required,
            issued_at_ns=now,
            expires_at_ns=now + request.ttl_ms * 1_000_000,
            contract_hash=request.contract_hash,
        )
        self.leases[lease.lease_id] = lease
        self.acquire_requests.append(request)
        return lease

    def renew(self, lease_id: str, ttl_ms: int) -> Lease:
        if lease_id in self.revoked:
            raise GatewayError("LEASE_REVOKED")
        lease = self.leases.get(lease_id)
        if lease is None:
            raise GatewayError("NO_LEASE")
        now = self.clock.now_ns()
        if not lease.active(now):
            self.leases.pop(lease_id, None)
            raise GatewayError("LEASE_EXPIRED")
        if ttl_ms <= 0:
            raise GatewayError("ttl_ms must be positive")
        renewed = Lease(
            lease_id=lease.lease_id,
            holder=lease.holder,
            scope=lease.scope,
            mode=lease.mode,
            priority=lease.priority,
            deadman_required=lease.deadman_required,
            issued_at_ns=lease.issued_at_ns,
            expires_at_ns=now + ttl_ms * 1_000_000,
            contract_hash=lease.contract_hash,
        )
        self.leases[lease_id] = renewed
        return renewed

    def release(self, lease_id: str) -> None:
        self.leases.pop(lease_id, None)

    def state(self) -> RobotStateView:
        if "state_unavailable" in self.faults:
            raise GatewayUnavailable("mock state unavailable")
        return RobotStateView(
            positions=tuple(self.positions),
            velocities=tuple(self.velocities),
            gripper=self.gripper,
            fresh=self.fresh,
            truth=self.truth,
            verification=self.verification,
            profile_hash=self.profile_hash,
            stamp_ns=self.clock.now_ns(),
        )

    def supports_mode(self, mode: str) -> bool:
        return mode in self.supported_modes

    def submit(self, intent: ActionIntent) -> GatewayResult:
        if "submit_unavailable" in self.faults:
            raise GatewayUnavailable("mock submit unavailable")
        if "submit_unknown" in self.faults:
            return GatewayResult("UNKNOWN", "GATEWAY_UNKNOWN", "ambiguous mock result")
        if "motion_busy" in self.faults:
            return GatewayResult("REJECTED", "MOTION_BUSY", "mock motion busy")
        if intent.purpose == "motion":
            if not intent.deadman:
                return GatewayResult("REJECTED", "INVALID_COMMAND", "motion intent requires deadman=true")
            lease = self.leases.get(intent.lease_id)
            if lease is None or not lease.active(self.clock.now_ns()):
                return GatewayResult("REJECTED", "NO_LEASE", "mock lease is not active")
            previous = self._last_seq.get(intent.lease_id, -1)
            if intent.seq <= previous:
                return GatewayResult("REJECTED", "INVALID_COMMAND", "non-increasing intent seq")
            self._last_seq[intent.lease_id] = intent.seq
        elif intent.purpose != "stop":
            return GatewayResult("REJECTED", "INVALID_COMMAND", "unknown intent purpose")
        if intent.profile_hash != self.profile_hash:
            return GatewayResult("REJECTED", "PROFILE_HASH_MISMATCH", "profile hash mismatch")
        if not self.supports_mode(intent.mode.value):
            return GatewayResult("REJECTED", "UNKNOWN_KIND", f"mode {intent.mode.value} not supported")
        self.submitted.append(intent)
        if intent.mode is Mode.JOINT_POSITION and intent.joint_positions_rad:
            self.positions = list(intent.joint_positions_rad)
        if intent.mode is Mode.JOINT_VELOCITY and intent.joint_velocities_rad_s:
            self.velocities = list(intent.joint_velocities_rad_s)
        if intent.gripper_valid and intent.gripper_normalized is not None:
            self.gripper = float(intent.gripper_normalized)
        return GatewayResult("COMPLETED", "OK", "mock accepted", applied=intent.to_dict())

    def stop(self, reason: str) -> StopResult:
        if "stop_unavailable" in self.faults:
            raise GatewayUnavailable("mock stop unavailable")
        if "stop_rejected" in self.faults:
            return StopResult(accepted=False, reason=reason, confirmed=False)
        self.stop_requests.append(reason)
        return StopResult(accepted=True, reason=reason, confirmed=None)

    # ---- helpers ----

    def snapshot(self) -> dict[str, Any]:
        return {
            "submitted": [intent.to_dict() for intent in self.submitted],
            "stops": list(self.stop_requests),
            "leases": [lease.to_dict() for lease in self.leases.values()],
        }
