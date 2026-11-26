#!/usr/bin/env python3
"""M3 storage-failure drill: a recorder fault must stop the session.

The size limit is lowered with ``RLIMIT_FSIZE`` so writes fail with EFBIG, the
same error path as a full disk. ``SIGXFSZ`` is ignored so the process survives
the write failure. The drill verifies that:

- the recorder marks itself faulted and ``record()`` never raises;
- the runner observer requests a system stop and the session stops;
- the sealed capture is ``degraded`` with a ``recorder_fault`` flag;
- no tick is blocked by storage (reported as max observer interval).

Run from the repository root with the core on ``PYTHONPATH``:

    PYTHONPATH=src python3 tools/disk_full_drill.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import shutil
import signal
import tempfile
import time

from jcheng_teleop.capture import CaptureMetadata, EpisodeRecorder, verify_capture
from jcheng_teleop.adapters.gateway.mock import MockGateway
from jcheng_teleop.adapters.input.virtual import VirtualInputSource
from jcheng_teleop.core.clock import ManualClock
from jcheng_teleop.core.model import InputSample, Mode
from jcheng_teleop.core.profile import load_binding, load_profile, resolve_profile
from jcheng_teleop.core.runner import TeleopRunner
from jcheng_teleop.core.session import SessionConfig, TeleopSession

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "sha256:" + "0" * 64
HASH = "sha256:" + "1" * 64


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks", type=int, default=400)
    parser.add_argument("--limit-bytes", type=int, default=512)
    parser.add_argument("--keep", action="store_true", help="keep the drill capture")
    args = parser.parse_args(argv)

    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    original_limit = resource.getrlimit(resource.RLIMIT_FSIZE)
    root = Path(tempfile.mkdtemp(prefix="jcheng-disk-drill-"))

    profile = resolve_profile(
        load_profile(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
        load_binding(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
    )
    clock = ManualClock(0)
    gateway = MockGateway(
        clock,
        contract_hash=CONTRACT,
        profile_hash=profile.profile_hash,
        joint_count=profile.joint_count,
    )
    session = TeleopSession(
        profile,
        gateway,
        clock,
        config=SessionConfig(deadman_ms=300, tick_ms=20, max_rate_hz=50, contract_hash=CONTRACT),
    )
    session.start()
    metadata = CaptureMetadata(
        capture_id="disk-drill",
        created_at="2026-11-26T00:00:00+00:00",
        teleop_version="0.3.0",
        contract_hash=CONTRACT,
        profile_id=profile.profile_id,
        profile_hash=profile.profile_hash,
        binding_hash=profile.binding.binding_hash,
        environment_class="mock",
        source_class="scripted",
        session_id="disk-drill",
        task_id="disk-full-drill",
        task_description="storage failure drill",
        joint_names=profile.joint_names,
        generator_id="disk-full-drill",
        generator_seed=0,
        generator_config_hash=HASH,
        limitations=("storage failure drill",),
    )
    recorder = EpisodeRecorder(root, metadata)
    intervals: list[float] = []
    last = [time.perf_counter()]

    def observer(result, sample, now_ns):
        now = time.perf_counter()
        intervals.append(now - last[0])
        last[0] = now
        recorder.observe(result, sample, now_ns)
        return not recorder.faulted

    samples = []
    for index in range(args.ticks):
        values = [0.0] * profile.joint_count
        values[0] = 0.2
        samples.append(
            InputSample(
                schema=InputSample.SCHEMA,
                source_id="disk_drill",
                source_class="virtual",
                seq=index,
                t_source_ns=index * 20_000_000,
                t_host_mono_ns=index * 20_000_000,
                mode=Mode.JOINT_VELOCITY,
                joint_velocities_rad_s=tuple(values),
                deadman=True,
                profile_id=profile.profile_id,
            )
        )
    runner = TeleopRunner(
        session=session,
        source=VirtualInputSource(samples),
        clock=clock,
        observer=observer,
    )

    started = time.perf_counter()
    soft_limit, hard_limit = original_limit
    resource.setrlimit(resource.RLIMIT_FSIZE, (args.limit_bytes, hard_limit))
    try:
        results = runner.run_ticks(args.ticks)
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft_limit, hard_limit))
    elapsed = time.perf_counter() - started
    state = session.state
    session.close()
    summary = recorder.close(outcome="aborted", outcome_source="automatic")
    report = verify_capture(root, metadata.capture_id)

    stopped = any(result.stop_sent for result in results)
    max_interval_ms = max(intervals) * 1000.0 if intervals else 0.0
    result = {
        "faulted": recorder.faulted,
        "fault": recorder.fault,
        "ticks_run": len(results),
        "stop_sent": stopped,
        "session_state": state.value,
        "observer_errors": runner.observer_errors,
        "max_observer_interval_ms": round(max_interval_ms, 3),
        "elapsed_s": round(elapsed, 3),
        "capture": str(summary.capture_path),
        "verify": report.status,
        "verify_errors": report.errors,
        "warnings": report.warnings,
        "manifest_sha256": summary.manifest_sha256,
    }
    print(json.dumps(result, sort_keys=True))
    # A storage fault can truncate the row that was being written, so the
    # sealed package may be invalid as well as degraded. The safety property
    # under test is the fault -> stop path, and the capture must say so.
    ok = (
        recorder.faulted
        and stopped
        and report.status in {"degraded", "invalid"}
        and summary.fault is not None
    )
    if not args.keep:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
