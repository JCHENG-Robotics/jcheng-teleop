"""Episode recorder: turns tick results and state telemetry into stream rows.

The recorder is an observer, not a control component. Every `record_*` method
builds a plain dict and hands it to the non-blocking writer; none of them raises
into a tick loop or a ROS callback. Stop intents, gateway results, rejected
observations and safety/fault events are queued as priority rows so a full
queue drops ordinary input/action rows first.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from ..core.model import ActionIntent, GatewayResult, InputSample, Severity, TeleopEvent, TickResult
from .observation import ObservationSample
from .provenance import SCHEMA, CaptureMetadata, ProvenanceError
from .writer import CaptureWriter, utc_now

INPUT_SCHEMA = "jcheng.teleop.input.v1"
ACTION_SCHEMA = "jcheng.teleop.action.v1"
COMMAND_SCHEMA = "jcheng.teleop.command.v1"
OBSERVATION_SCHEMA = "jcheng.teleop.observation.v1"
EVENT_SCHEMA = "jcheng.teleop.event.v1"

_PRIORITY_EVENT_CODES = frozenset(
    {
        "SESSION_STOP",
        "STOP_SENT",
        "STOP_REJECTED",
        "DEADMAN_RELEASE",
        "DEADMAN_TIMEOUT",
        "LOOP_WATCHDOG",
        "LOOP_OVERRUN",
        "OBSERVATION_REJECTED",
    }
)


def lease_reference(lease_id: str) -> str | None:
    """Hash a lease id; a raw lease id is never written to a capture."""
    if not lease_id:
        return None
    return "sha256:" + hashlib.sha256(lease_id.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EpisodeSummary:
    capture_path: Path
    manifest_sha256: str | None
    accepted: dict[str, int]
    written: dict[str, int]
    dropped: dict[str, int]
    dropped_priority: int
    rejected_observations: int
    fault: str | None


class EpisodeRecorder:
    def __init__(
        self,
        root: str | Path,
        metadata: CaptureMetadata,
        *,
        queue_limit: int = 4096,
        start_thread: bool = True,
        drain_delay_s: float = 0.0,
    ) -> None:
        metadata.validate()
        self.metadata = metadata
        self.writer = CaptureWriter(
            root,
            metadata.capture_id,
            queue_limit=queue_limit,
            start_thread=start_thread,
            drain_delay_s=drain_delay_s,
        )
        self.tick_id = 0
        self._last_input_seq: int | None = None
        self._fault_events = 0
        self.rejected_observations = 0

    @property
    def faulted(self) -> bool:
        return self.writer.faulted

    @property
    def fault(self) -> str | None:
        return self.writer.fault

    def begin_tick(self, now_ns: int) -> int:
        """Start one logical tick; rows written for it share the tick id."""
        self.tick_id += 1
        return self.tick_id

    def _base(self, schema: str, now_ns: int, tick_id: int) -> dict[str, Any]:
        return {
            "schema": schema,
            "capture_id": self.metadata.capture_id,
            "tick_id": int(tick_id),
            "t_mono_ns": int(now_ns),
            "clock_id": self.metadata.clock_id,
        }

    # ---- public row writers (never raise) ----

    def record_input(
        self, sample: InputSample, now_ns: int, *, tick_id: int | None = None
    ) -> bool:
        if self.writer.faulted:
            return False
        tick = self.begin_tick(now_ns) if tick_id is None else tick_id
        if sample.seq == self._last_input_seq:
            return True
        self._last_input_seq = sample.seq
        return self.writer.record("input", self._input_row(sample, now_ns, tick))

    def record_action(
        self, intent: ActionIntent, now_ns: int, *, tick_id: int | None = None
    ) -> bool:
        if self.writer.faulted:
            return False
        tick = self.begin_tick(now_ns) if tick_id is None else tick_id
        return self.writer.record(
            "action",
            self._action_row(intent, now_ns, tick),
            priority=intent.purpose == "stop",
        )

    def record_event(
        self,
        code: str,
        severity: Severity,
        now_ns: int,
        *,
        detail: dict[str, Any] | None = None,
        tick_id: int | None = None,
    ) -> bool:
        if self.writer.faulted:
            return False
        tick = self.begin_tick(now_ns) if tick_id is None else tick_id
        event = TeleopEvent(code=code, severity=severity, at_ns=int(now_ns), detail=detail or {})
        if severity is Severity.FAULT:
            self._fault_events += 1
        return self.writer.record(
            "events",
            self._event_row(event, now_ns, tick),
            priority=severity is Severity.FAULT or code in _PRIORITY_EVENT_CODES,
        )

    def record_observation(
        self,
        observation: ObservationSample,
        now_ns: int,
        *,
        tick_id: int | None = None,
    ) -> bool:
        if self.writer.faulted:
            return False
        tick = self.begin_tick(now_ns) if tick_id is None else tick_id
        try:
            observation.validate(self.metadata.environment_class)
        except ProvenanceError as exc:
            self.rejected_observations += 1
            self.record_event(
                "OBSERVATION_REJECTED",
                Severity.WARNING,
                now_ns,
                detail={
                    "reason": str(exc),
                    "topic": observation.topic,
                    "truth": observation.truth,
                    "verification": observation.verification,
                },
                tick_id=tick,
            )
            return False
        row = self._base(OBSERVATION_SCHEMA, now_ns, tick)
        row.update(observation.to_row())
        row["environment_class"] = self.metadata.environment_class
        return self.writer.record("observation", row)

    # ---- runner path ----

    def observe(
        self,
        result: TickResult,
        sample: InputSample | None,
        now_ns: int,
    ) -> None:
        if self.writer.faulted:
            return
        tick = self.begin_tick(now_ns)
        if sample is not None:
            self.record_input(sample, now_ns, tick_id=tick)
        if result.intent is not None:
            self.record_action(result.intent, now_ns, tick_id=tick)
        if result.gateway_result is not None:
            self.writer.record(
                "command",
                self._command_row(result.gateway_result, now_ns, tick),
                priority=True,
            )
        for event in result.events:
            if event.severity.value == "fault":
                self._fault_events += 1
            priority = event.severity.value == "fault" or event.code in _PRIORITY_EVENT_CODES
            self.writer.record("events", self._event_row(event, now_ns, tick), priority=priority)

    def _input_row(self, sample: InputSample, now_ns: int, tick_id: int) -> dict[str, Any]:
        row = self._base(INPUT_SCHEMA, now_ns, tick_id)
        row.update(
            {
                "source_id": sample.source_id,
                "source_class": sample.source_class,
                "seq": sample.seq,
                "mode": sample.mode.value,
                "joint_positions_rad": list(sample.joint_positions_rad),
                "joint_velocities_rad_s": list(sample.joint_velocities_rad_s),
                "gripper_normalized": sample.gripper_normalized,
                "gripper_valid": bool(sample.gripper_valid),
                "deadman": bool(sample.deadman),
                "profile_id": sample.profile_id,
                "t_source_ns": int(sample.t_source_ns),
                "t_host_mono_ns": int(sample.t_host_mono_ns),
                "calibration_id": sample.calibration_id,
                "environment_class": self.metadata.environment_class,
            }
        )
        return row

    def _action_row(self, intent: ActionIntent, now_ns: int, tick_id: int) -> dict[str, Any]:
        row = self._base(ACTION_SCHEMA, now_ns, tick_id)
        row.update(
            {
                "mode": intent.mode.value,
                "purpose": intent.purpose,
                "deadman": bool(intent.deadman),
                "seq": intent.seq,
                "t_source_ns": int(intent.t_source_ns),
                "joint_positions_rad": list(intent.joint_positions_rad),
                "joint_velocities_rad_s": list(intent.joint_velocities_rad_s),
                "gripper_normalized": intent.gripper_normalized,
                "gripper_valid": bool(intent.gripper_valid),
                "frame_id": intent.frame_id,
                "profile_id": intent.profile_id,
                "profile_hash": intent.profile_hash,
                "lease_ref": lease_reference(intent.lease_id),
            }
        )
        return row

    def _command_row(self, result: GatewayResult, now_ns: int, tick_id: int) -> dict[str, Any]:
        row = self._base(COMMAND_SCHEMA, now_ns, tick_id)
        row.update(
            {
                "transport": "mock_gateway",
                "outcome": result.outcome,
                "reason_code": result.reason_code,
                "message": result.message,
                "applied": dict(result.applied),
                "confirmed": result.confirmed,
            }
        )
        return row

    def _event_row(self, event: TeleopEvent, now_ns: int, tick_id: int) -> dict[str, Any]:
        row = self._base(EVENT_SCHEMA, now_ns, tick_id)
        row.update(
            {
                "code": event.code,
                "severity": event.severity.value,
                "at_ns": int(event.at_ns),
                "detail": dict(event.detail),
            }
        )
        return row

    def close(
        self,
        *,
        outcome: str = "unknown",
        outcome_source: str = "automatic",
        ended_at: str | None = None,
    ) -> EpisodeSummary:
        flags: list[str] = []
        if self._fault_events:
            flags.append("fault_events")
        if self.rejected_observations:
            flags.append("rejected_observations")
        if self.writer.dropped_priority or any(self.writer.dropped.values()):
            flags.append("dropped_rows")
        manifest = self.metadata.to_manifest(
            ended_at=ended_at or utc_now(),
            files=[],
            stream_counts={},
            outcome=outcome,
            outcome_source=outcome_source,
            quality_flags=flags,
            dropped_priority=self.writer.dropped_priority,
            recorder_fault=self.writer.fault,
        )
        seal = self.writer.close(manifest)
        return EpisodeSummary(
            capture_path=Path(seal["capture_path"]),
            manifest_sha256=seal.get("manifest_sha256"),
            accepted=seal["accepted"],
            written=seal["written"],
            dropped=seal["dropped"],
            dropped_priority=seal["dropped_priority"],
            rejected_observations=self.rejected_observations,
            fault=seal["fault"],
        )
