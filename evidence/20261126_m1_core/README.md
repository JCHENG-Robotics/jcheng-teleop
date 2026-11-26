# M1 core evidence — 2026-11-26

> Scope: ROS-free teleoperation core, device-free input adapters, profile
> mapping, safety state machine, in-process mock gateway and CLI.
> No ROS node, no DDS domain, no device, no robot, no recording and no hardware
> session. M1 is an L1 / in-process L2 result, not hardware evidence.
>
> Branch: `docs/m0-architecture` (working tree), version 0.3.0.
> Operator: JerichoCheng. Independent code review Round 1 returned REJECT;
> Round 2 returned APPROVE WITH CHANGES; all findings were fixed. M1 is
> accepted at L1/in-process L2; commit/tag is authorized. See `review.md`.
> M1 code/test snapshot: `sha256:21cf5e4c632194e86a16326b6b729289300e7aef53616b0f00d87ff997f7a3f0`;
> no commit/tag was created (operator action).

## Commands

```bash
python3 -m pytest tests
bash scripts/check_repo_gate.sh
PYTHONPATH=src python3 -m jcheng_teleop \
  --profile examples/armpi_ultra_demo/profile.yaml \
  --binding examples/armpi_ultra_demo/binding.yaml \
  --input virtual --ticks 20
```

## Results

| Check | Result | Evidence |
|---|---|---|
| Unit and in-process L2 tests | pass (111 tests) | `pytest.txt` |
| Repository gate (documents, links, manifest, no device/secret/weight) | pass | `gate.txt` |
| 2/5/6-DoF profile resolution and mapping | pass | `profiles.txt` |
| Deterministic replay of the same script | pass | `determinism.txt`; `cli_trace_sha256.txt` |
| CLI virtual run | 15 submitted, 1 stop, 0 faults, state IDLE (before close) | `cli_summary_1.txt` |
| Two CLI traces byte-identical | same SHA-256 | `cli_trace_sha256.txt` |

CLI trace hash:

```text
7d79cfbcd277ef0f7c9d87f790eb10feea477e6743d13bade2d8eecba1c0c9c2  cli_trace_1.jsonl
7d79cfbcd277ef0f7c9d87f790eb10feea477e6743d13bade2d8eecba1c0c9c2  cli_trace_2.jsonl
```

## What M1 proves

- The core is importable and testable without ROS, DDS, a device or a robot.
- No intent is emitted before a fresh enable edge and a valid lease/state.
- Deadman release and input timeout produce one mode-specific stop intent and
  stop the session; no auto-resume.
- Velocity conditioning clamps to profile limits and emits one limit event per
  continuous saturation episode.
- Joint position is a typed target and is refused when the mock gateway does
  not support the native mode; it is never emulated with a velocity loop.
- A profile/binding mismatch, duplicate/rollback sequence, stamp rollback and
  non-finite input are rejected, not repaired.
- The mock gateway exercises lease acquire/renew/release, submit, unknown,
  busy, unavailable and stop; the session never retries motion.
- The same script produces a byte-identical trace.

## What M1 does not prove

- No ROS 2 Humble node, DDS QoS, lease handshake against the system gateway or
  simulation plant.
- No measured-state path at the teleop rate; the mock state is synthetic.
- No recording, replay of a real capture, dataset or LeRobot export.
- No hardware, no bus read, no e-stop and no physical stop confirmation.
- The independent code review Round 1 rejected the artifact; fixes are applied
  and re-review is pending. The tree is not committed/tagged.

## Limitations

- The mock gateway is a semantic fake, not the system arbiter.
- The keyboard adapter consumes injected key events; a real terminal wrapper
  and a real gamepad driver remain operator-side.
- The demo profile is a fixture, not the canonical system profile; M2 must
  resolve the canonical profile and hash.
- The 50 Hz/300 ms values are local design bounds; they are not a hardware
  stop guarantee.
- No `LICENSE`; no third-party code was copied.

## Artifacts

- `review.md`, `pytest.txt`, `gate.txt`, `profiles.txt`, `determinism.txt`
- `cli_summary_1.txt`, `cli_summary_2.txt`, `cli_trace_1.jsonl`,
  `cli_trace_2.jsonl`, `cli_trace_sha256.txt`
- `src/jcheng_teleop/`, `tests/`, `examples/armpi_ultra_demo/`
