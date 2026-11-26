"""Teleop capture package (M3).

`jcheng.teleop.capture.v1` is teleop-local; it is not the learning dataset
contract. The recorder never blocks the control loop or the stop path, and a
capture never relabels simulation or mock data as hardware.
"""

from .observation import VERIFICATIONS, ObservationSample
from .provenance import (
    ENVIRONMENT_CLASSES,
    OUTCOMES,
    SCHEMA,
    SOURCE_CLASSES,
    CaptureMetadata,
    ProvenanceError,
)
from .recorder import EpisodeRecorder, EpisodeSummary, lease_reference
from .verify import VerifyReport, verify_capture
from .writer import CapturePathError, CaptureWriter

__all__ = [
    "ENVIRONMENT_CLASSES",
    "OUTCOMES",
    "SCHEMA",
    "SOURCE_CLASSES",
    "VERIFICATIONS",
    "CaptureMetadata",
    "CapturePathError",
    "CaptureWriter",
    "EpisodeRecorder",
    "EpisodeSummary",
    "ObservationSample",
    "ProvenanceError",
    "VerifyReport",
    "lease_reference",
    "verify_capture",
]
