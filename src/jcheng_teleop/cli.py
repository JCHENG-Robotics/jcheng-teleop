"""M1/M3 command-line entry point.

Runs the ROS-free core against a virtual or JSONL input and the in-process
mock gateway. It never opens a socket, device or ROS graph. With `--record` it
also writes a `jcheng.teleop.capture.v1` package outside the repository; the
recorder is an observer and cannot block the tick loop or the stop path.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from . import __version__
from .adapters.gateway.mock import MockGateway
from .adapters.input.jsonl import JsonlInputSource
from .adapters.input.keyboard import KeyboardInputSource, ScriptedKeySource
from .adapters.input.virtual import VirtualInputSource
from .capture import CaptureMetadata, EpisodeRecorder, verify_capture
from .core.clock import ManualClock
from .core.model import InputSample, Mode, SessionState
from .core.profile import load_binding, load_profile, resolve_profile
from .core.runner import TeleopRunner
from .core.session import SessionConfig, TeleopSession

DEMO_CONTRACT = "sha256:" + "0" * 64


def _demo_samples(profile, *, ticks: int, tick_ns: int) -> list[InputSample]:
    samples: list[InputSample] = []
    for index in range(ticks):
        values = [0.0] * profile.joint_count
        if profile.joint_count:
            values[0] = 0.2 if index < max(1, ticks // 2) else 0.0
        samples.append(
            InputSample(
                schema=InputSample.SCHEMA,
                source_id="virtual_demo",
                source_class="virtual",
                seq=index,
                t_source_ns=index * tick_ns,
                t_host_mono_ns=index * tick_ns,
                mode=Mode.JOINT_VELOCITY,
                joint_velocities_rad_s=tuple(values),
                deadman=index < max(1, ticks - 5),
                profile_id=profile.profile_id,
            )
        )
    return samples


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jcheng-teleop",
        description="ROS-free M1 teleoperation core (mock gateway only)",
    )
    parser.add_argument("--profile", required=True, help="teleop profile YAML")
    parser.add_argument("--binding", required=True, help="teleop binding YAML")
    parser.add_argument("--input", choices=("virtual", "jsonl", "keyboard"), default="virtual")
    parser.add_argument("--jsonl", help="input JSONL path (required for --input jsonl)")
    parser.add_argument("--key-script", default="space_down,w_down,w_down,w_up,space_up")
    parser.add_argument("--ticks", type=int, default=30)
    parser.add_argument("--duration", type=float, help="run duration in seconds (overrides --ticks)")
    parser.add_argument("--tick-ms", type=int, default=20)
    parser.add_argument("--stop-file", help="request a system stop when this file appears")
    parser.add_argument("--trace", help="write one JSON result per line")
    parser.add_argument(
        "--record",
        metavar="DATA_ROOT",
        help="write a capture package under this root (outside any git worktree)",
    )
    parser.add_argument("--capture-id", help="capture directory name (default: timestamped)")
    parser.add_argument("--task", default="cli-demo", help="task id recorded in the manifest")
    parser.add_argument("--mock", action="store_true", default=True, help="mock gateway only (M1)")
    parser.add_argument("--contract-hash", default=DEMO_CONTRACT)
    return parser


def _capture_metadata(args, resolved, *, ticks: int) -> CaptureMetadata:
    capture_id = args.capture_id or (
        "capture-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    generator_config = {
        "input": args.input,
        "ticks": ticks,
        "tick_ms": args.tick_ms,
        "duration": args.duration,
        "stop_file": bool(args.stop_file),
        "profile_hash": resolved.profile_hash,
        "binding_hash": resolved.binding.binding_hash,
    }
    return CaptureMetadata(
        capture_id=capture_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        teleop_version=__version__,
        contract_hash=args.contract_hash,
        profile_id=resolved.profile_id,
        profile_hash=resolved.profile_hash,
        binding_hash=resolved.binding.binding_hash,
        environment_class="mock",
        source_class="scripted",
        session_id=capture_id,
        task_id=args.task,
        task_description=f"CLI {args.input} mock teleoperation ({args.task})",
        joint_names=resolved.joint_names,
        profile_source="fixture",
        has_gripper=resolved.profile.gripper is not None,
        generator_id="jcheng-teleop-cli",
        generator_seed=0,
        generator_config_hash="sha256:"
        + hashlib.sha256(
            json.dumps(generator_config, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        tick_ms=args.tick_ms,
        nominal_hz=1000.0 / args.tick_ms,
        deadman_ms=300,
        limitations=(
            "mock gateway only; no RobotState observation stream",
            "joint frames are not measured or bus-verified",
            "session close event is not recorded",
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ticks = args.ticks
    if args.duration is not None:
        ticks = max(0, int(args.duration * 1000 / args.tick_ms))
    if ticks < 0:
        parser.error("--ticks must be non-negative")
    if args.tick_ms <= 0:
        parser.error("--tick-ms must be positive")
    if args.input == "jsonl" and not args.jsonl:
        parser.error("--jsonl is required for --input jsonl")

    try:
        profile = load_profile(Path(args.profile))
        binding = load_binding(Path(args.binding))
        resolved = resolve_profile(profile, binding)
    except (OSError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 3

    clock = ManualClock(0)
    tick_ns = args.tick_ms * 1_000_000
    gateway = MockGateway(
        clock,
        contract_hash=args.contract_hash,
        profile_hash=resolved.profile_hash,
        joint_count=resolved.joint_count,
    )
    session = TeleopSession(
        resolved,
        gateway,
        clock,
        config=SessionConfig(
            deadman_ms=300,
            tick_ms=args.tick_ms,
            max_rate_hz=max(1, 1000 // args.tick_ms),
            contract_hash=args.contract_hash,
        ),
    )
    started = session.start()
    if session.state is SessionState.FAULT:
        for event in started:
            print(json.dumps(event.to_dict(), sort_keys=True), file=sys.stderr)
        return 4

    if args.input == "virtual":
        source = VirtualInputSource(_demo_samples(resolved, ticks=ticks, tick_ns=tick_ns))
    elif args.input == "jsonl":
        source = JsonlInputSource(Path(args.jsonl))
    else:
        events = [event.strip() for event in args.key_script.split(",") if event.strip()]
        source = KeyboardInputSource(
            ScriptedKeySource(events),
            joint_count=resolved.joint_count,
            profile_id=resolved.profile_id,
        )

    runner = TeleopRunner(
        session=session,
        source=source,
        clock=clock,
        tick_ns=tick_ns,
        stop_file=args.stop_file,
    )
    recorder: EpisodeRecorder | None = None
    if args.record:
        try:
            recorder = EpisodeRecorder(
                Path(args.record), _capture_metadata(args, resolved, ticks=ticks)
            )
        except (OSError, ValueError) as exc:
            session.close()
            print(f"record error: {exc}", file=sys.stderr)
            return 3

        def _observe(result, sample, now_ns) -> bool:
            recorder.observe(result, sample, now_ns)
            return not recorder.faulted

        runner.observer = _observe
    try:
        results = runner.run_ticks(ticks)
    except (OSError, ValueError) as exc:
        session.close()
        if recorder is not None:
            recorder.close(outcome="aborted", outcome_source="automatic")
        print(f"input error: {exc}", file=sys.stderr)
        return 3
    final_state = session.state
    session.close()

    lines = [json.dumps(result.to_dict(), sort_keys=True) for result in results]
    if args.trace:
        Path(args.trace).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    faults = sum(
        1
        for result in results
        for event in result.events
        if event.severity.value == "fault"
    )
    summary = {
        "state": final_state.value,
        "ticks": len(results),
        "submitted": sum(1 for result in results if result.submitted),
        "stop_sent": sum(1 for result in results if result.stop_sent),
        "faults": faults,
    }
    capture_invalid = False
    if recorder is not None:
        if recorder.faulted:
            outcome, outcome_source = "aborted", "automatic"
        elif faults:
            outcome, outcome_source = "failure", "automatic"
        else:
            outcome, outcome_source = "unknown", "automatic"
        seal = recorder.close(outcome=outcome, outcome_source=outcome_source)
        report = verify_capture(seal.capture_path.parent, seal.capture_path.name)
        capture_invalid = bool(seal.fault) or not report.ok
        summary["capture"] = {
            "path": str(seal.capture_path),
            "manifest_sha256": seal.manifest_sha256,
            "verify": report.status,
            "rows_written": seal.written,
            "rows_dropped": sum(seal.dropped.values()),
            "dropped_priority": seal.dropped_priority,
            "fault": seal.fault,
        }
        for message in report.errors:
            print(f"capture verify: {message}", file=sys.stderr)
    print(json.dumps(summary, sort_keys=True))
    if capture_invalid:
        return 5
    return 0 if final_state is not SessionState.FAULT else 1
