#!/usr/bin/env python3
"""M3 acceptance drill: N episodes x duration_s, valid capture, label scan.

Each episode runs the ROS-free core with a scripted input, records a capture
package outside the repository, seals it and re-reads it. The drill fails if a
capture is not `valid` or if any row claims a `bus` measurement / a
hardware-only label.

    PYTHONPATH=src python3 tools/capture_acceptance_drill.py \
        --episodes 30 --seconds 60 --root /tmp/jcheng-m3-acceptance

Capture data is never written into the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
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


def _samples(profile, *, ticks: int, tick_ns: int, episode: int) -> list[InputSample]:
    joint = episode % profile.joint_count
    velocity = 0.2 if episode % 2 == 0 else -0.2
    samples = []
    for index in range(ticks):
        values = [0.0] * profile.joint_count
        values[joint] = velocity if index < ticks - 5 else 0.0
        samples.append(
            InputSample(
                schema=InputSample.SCHEMA,
                source_id=f"drill_{episode:02d}",
                source_class="virtual",
                seq=index,
                t_source_ns=index * tick_ns,
                t_host_mono_ns=index * tick_ns,
                mode=Mode.JOINT_VELOCITY,
                joint_velocities_rad_s=tuple(values),
                deadman=index < ticks - 3,
                profile_id=profile.profile_id,
            )
        )
    return samples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--rate-hz", type=float, default=50.0)
    parser.add_argument("--root", default="")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)
    if args.episodes <= 0 or args.seconds <= 0 or args.rate_hz <= 0:
        raise SystemExit("episodes, seconds and rate must be positive")

    root = Path(args.root).expanduser() if args.root else Path(
        tempfile.mkdtemp(prefix="jcheng-m3-acceptance-")
    )
    root.mkdir(parents=True, exist_ok=True)
    profile = resolve_profile(
        load_profile(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
        load_binding(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
    )
    tick_ns = int(1_000_000_000 / args.rate_hz)
    ticks = int(args.seconds * args.rate_hz)
    started = time.perf_counter()
    episodes = []
    total_rows = 0
    violations = 0

    for episode in range(args.episodes):
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
            config=SessionConfig(
                deadman_ms=300,
                tick_ms=max(1, round(1000.0 / args.rate_hz)),
                max_rate_hz=max(1, round(args.rate_hz)),
                contract_hash=CONTRACT,
            ),
        )
        session.start()
        capture_id = f"ep-{episode:02d}-mock"
        metadata = CaptureMetadata(
            capture_id=capture_id,
            created_at="2026-11-26T00:00:00+00:00",
            teleop_version="0.3.0",
            contract_hash=CONTRACT,
            profile_id=profile.profile_id,
            profile_hash=profile.profile_hash,
            binding_hash=profile.binding.binding_hash,
            environment_class="mock",
            source_class="scripted",
            session_id=capture_id,
            task_id=f"drill-{episode:02d}",
            task_description=f"acceptance drill episode {episode}",
            joint_names=profile.joint_names,
            generator_id="capture-acceptance-drill",
            generator_seed=episode,
            generator_config_hash="sha256:"
            + hashlib.sha256(
                json.dumps(
                    {"episode": episode, "ticks": ticks, "rate_hz": args.rate_hz},
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            nominal_hz=args.rate_hz,
            tick_ms=max(1, round(1000.0 / args.rate_hz)),
            limitations=("acceptance drill; mock gateway, no observations",),
        )
        recorder = EpisodeRecorder(root, metadata, queue_limit=65536)
        runner = TeleopRunner(
            session=session,
            source=VirtualInputSource(
                _samples(profile, ticks=ticks, tick_ns=tick_ns, episode=episode)
            ),
            clock=clock,
            observer=lambda result, sample, now: (
                recorder.observe(result, sample, now),
                not recorder.faulted,
            )[1],
        )
        results = runner.run_ticks(ticks)
        final_state = session.state
        session.close()
        summary = recorder.close(outcome="unknown", outcome_source="automatic")
        report = verify_capture(root, capture_id)
        rows = sum(report.row_counts.values())
        total_rows += rows
        if report.status != "valid" or summary.fault is not None:
            violations += 1
        manifest = json.loads(
            (root / capture_id / "manifest.json").read_text(encoding="utf-8")
        )
        if (
            manifest["environment"]["environment_class"] != "mock"
            or manifest["environment"]["sim_truth_label"] is not None
        ):
            violations += 1
        for name in ("input.jsonl", "action.jsonl", "command.jsonl",
                     "observation.jsonl", "events.jsonl"):
            text = (root / capture_id / name).read_text(encoding="utf-8")
            if '"verification":"bus"' in text or '"truth":"measured"' in text:
                violations += 1
        episodes.append(
            {
                "capture_id": capture_id,
                "ticks": len(results),
                "state": final_state.value,
                "rows": rows,
                "verify": report.status,
                "quality_flags": manifest["capture"]["quality_flags"],
                "manifest_sha256": summary.manifest_sha256,
            }
        )

    elapsed = time.perf_counter() - started
    total_bytes = sum(
        path.stat().st_size for path in root.rglob("*") if path.is_file()
    )
    summary = {
        "episodes": len(episodes),
        "seconds_per_episode": args.seconds,
        "rate_hz": args.rate_hz,
        "ticks_per_episode": ticks,
        "total_rows": total_rows,
        "total_bytes": total_bytes,
        "violations": violations,
        "elapsed_s": round(elapsed, 3),
        "root": str(root),
        "sample": episodes[0] if episodes else None,
        "last": episodes[-1] if episodes else None,
    }
    print(json.dumps(summary, sort_keys=True))
    ok = violations == 0 and all(item["verify"] == "valid" for item in episodes)
    if not args.keep:
        shutil.rmtree(root, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
