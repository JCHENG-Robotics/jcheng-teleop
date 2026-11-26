"""Gateway boundary and canonical result types.

The core depends on this narrow port. M1 ships only an in-process mock; a later
HTTP/DDS adapter implements the same semantics without changing the core.
"""

from __future__ import annotations

from typing import Protocol

from .model import (
    ActionIntent,
    Admission,
    GatewayResult,
    Lease,
    LeaseRequest,
    RobotStateView,
    StopResult,
)


class GatewayError(RuntimeError):
    code = "GATEWAY_ERROR"


class GatewayUnavailable(GatewayError):
    code = "GATEWAY_UNAVAILABLE"


class GatewayProtocolError(GatewayError):
    code = "GATEWAY_PROTOCOL_ERROR"


class GatewayUnauthorized(GatewayError):
    code = "UNAUTHORIZED"


class GatewayContractMismatch(GatewayError):
    code = "CONTRACT_MISMATCH"


class GatewayPort(Protocol):
    def admit(self) -> Admission: ...

    def acquire(self, request: LeaseRequest) -> Lease: ...

    def renew(self, lease_id: str, ttl_ms: int) -> Lease: ...

    def release(self, lease_id: str) -> None: ...

    def state(self) -> RobotStateView: ...

    def supports_mode(self, mode: str) -> bool: ...

    def submit(self, intent: ActionIntent) -> GatewayResult: ...

    def stop(self, reason: str) -> StopResult: ...
