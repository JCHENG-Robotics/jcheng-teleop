"""M6 supervised-session authorization and offline preflight."""

from .authorization import SCHEMA, SupervisedAuthorization, SupervisedError
from .preflight import HARDWARE_BLOCKERS, PreflightReport, run_preflight

__all__ = [
    "HARDWARE_BLOCKERS",
    "SCHEMA",
    "PreflightReport",
    "SupervisedAuthorization",
    "SupervisedError",
    "run_preflight",
]
