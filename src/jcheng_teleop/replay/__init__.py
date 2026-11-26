"""Offline capture replay and anomaly scan (M4).

Replay has no gateway, DDS, device or wall-clock dependency: it re-derives
actions from the recorded input with the same core and reports divergences.
"""

from .anomaly import AnomalyReport, scan_streams
from .capture_reader import CaptureData, ReplayError, read_capture
from .replay import Divergence, ReplayReport, replay_capture, replay_streams

__all__ = [
    "AnomalyReport",
    "CaptureData",
    "Divergence",
    "ReplayError",
    "ReplayReport",
    "read_capture",
    "replay_capture",
    "replay_streams",
    "scan_streams",
]
