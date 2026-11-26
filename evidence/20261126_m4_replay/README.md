# M4 offline replay (slices 1–2)

> Status: **Partially verified (L1, recorded mock + simulation, 2026-11-26)**.
> Input replay, command-payload capture and wire-projection replay, quality
> metrics, anomaly scan and benchmark JSONL export are implemented. The
> LeRobot adapter is blocked on the learning dataset contract. No hardware.

## Scope

`src/jcheng_teleop/replay/`:

- `capture_reader.py`: verifies a sealed capture (hashes and schemas) and
  parses the five streams. An unverified capture is not replayed.
- `replay.py`: re-derives action intents from `input.jsonl` with a fresh
  `Conditioner`/`ActionMapper` and compares them field by field to
  `action.jsonl`; stop intents are skipped (the session, not the mapper,
  generates them). Also compares each recorded `command.payload` with its
  action row (wire projection: the session may assign a seq and lease id, but
  must not change the payload).
- `metrics.py`: jitter, action/observation skew, limit events, deadman
  releases, stop intents and zero-motion ratio.
- `anomaly.py`: pure scan for schema, tick/time ordering, stop/deadman
  consistency, command/action coverage and observation label violations.
- `../export/benchmark.py`: one benchmark row per motion action, with
  `environment_class` mapped to the benchmark vocabulary (`hardware` →
  `recorded`, `simulation` → `synthetic`, `mock` → `mock`).
- `cli.py`: `jcheng-teleop-replay`; exit 0 clean, 1 divergence/anomaly error,
  2 verification or profile mismatch; `--benchmark-out` writes the dataset.
  It imports no rclpy, gateway, socket or subprocess module (static test).

## Command payload and command replay

`TickResult.submitted_intent` exposes the intent handed to the gateway, and
`command.jsonl` now records a `payload` (mode, purpose, seq, deadman,
velocities/positions, gripper, profile hashes, hashed lease ref). A capture
recorded before this change has command rows without a payload; replay counts
them in `commands_without_payload` instead of inventing a comparison.

```text
cli-cmd-20261126: rows action=96, command=95, input=100, events=8
replay: commands_recorded=95, commands_compared=95,
        commands_without_payload=0, divergences=[]
metrics: jitter p50/p95/max 0.0/0.0/0.0 ms (ManualClock),
         duration 1.9 s, stop_intents 1, deadman_releases 2,
         zero_motion_ratio 0.4737, limit_events 0
```

## Benchmark export

The CLI capture above was exported and scored by `jcheng-benchmark`:

```text
export: 95 rows, 22,841 bytes, sha256:628aefb7c31e7f57..., data_source=mock, level=L2
suite:  teleop-replay-smoke, L2/mock, 95 samples, speed p95 0.2 rad/s,
        result=pass ("all 1 threshold(s) passed with 95 samples")
```

The report adds the benchmark's own limitation that a mock run is not a
hardware or recorded-data result. `read_dataset` accepted every row and
reported the same dataset hash as the exporter.

## Recorded captures

Both were recorded through the ROS demo harness with the teleop demo profile
and replayed with the same profile:

| Capture | Environment | Observation rows | Replay | Anomalies |
|---|---|---|---|---|
| `mock-mono-20261126` | mock | 285 | 101/101 actions, 0 divergences | none |
| `sim-mono-20261126` | simulation | 246 | 101/101 actions, 0 divergences | none |

```text
mock: {"replay": {"actions_recorded": 101, "motion_compared": 101,
       "divergences": [], "status": "ok"},
       "anomalies": {"status": "ok", "errors": []}}
sim:  {"replay": {"actions_recorded": 101, "motion_compared": 101,
       "divergences": [], "status": "ok"},
       "anomalies": {"status": "ok", "errors": []}}
```

Commands:

```bash
PYTHONPATH=src python3 -m jcheng_teleop.replay.cli \
  --capture-root /tmp/jcheng-m4-ros --capture-id mock-mono-20261126 \
  --profile examples/armpi_ultra_demo/profile.yaml \
  --binding examples/armpi_ultra_demo/binding.yaml
```

## Findings from the first replay

1. **Priority rows reordered a stream.** The writer drained priority rows
   first, so a stop action recorded at tick 7 appeared before ticks 1–6 and
   `verify_capture` rejected the capture (`tick_id regressed`). Fixed: one FIFO
   queue; `priority` only decides who is dropped under pressure.
2. **Stop intents were not captured.** `TickResult.intent` is the submitted
   motion intent; the mode-specific stop intent was only visible as an event.
   Added `TickResult.stop_intent`, set by the session on the tick that sends a
   stop and recorded as an `action` row (priority). Old captures lack it;
   new CLI runs have one stop row per stop.
3. **ROS wall clock is not monotonic.** The first mock capture had
   `observation[49]: t_mono_ns regressed` because the harness used the ROS
   wall clock for `t_mono_ns`. Fixed: host `time.monotonic_ns()` for capture
   ordering, ROS stamp preserved as `t_ros_ns`. The old capture remains an
   example of the detector firing.

## Tests

`python3 -m pytest -q tests/test_replay.py` — **16 passed**. Full suite:
**153 passed**.

Covered: replay reproduces recorded actions; a tampered action is detected;
missing input is a defect; a `bus` label in a mock capture and a `simulated`
label outside simulation are errors; non-monotonic time and a stop with
`deadman=true` are errors; command payloads match their actions, a tampered
payload is detected, and a payload-less capture is counted not invented;
metrics; benchmark export row count/uniqueness/data-source mapping and the
in-repo path refusal; CLI end-to-end and profile-hash mismatch; the replay
package imports no runtime/network module.

## Limits

- Command replay is a wire-projection check (recorded command payload vs its
  action). It does not re-run a gateway, so gateway outcomes are not
  re-derived.
- Stop intents are skipped by input replay; they are checked by the anomaly
  scan (deadman/ordering) and are recorded as action rows.
- Quality metrics are descriptive: jitter uses capture timestamps (ManualClock
  is exactly 0), and observation skew needs observation rows on the same
  monotonic clock. No safety bound is claimed.
- Benchmark export is a dataset writer; suite selection, thresholds and the
  report are benchmark-owned. Mock rows are `data_source: mock` and can never
  be reported as recorded or hardware.
- The LeRobot adapter is blocked on the learning `jcheng.dataset.v1` contract
  and the absolute-position action gap; not implemented.
- The 30-episode set in `evidence/20261126_m3_capture/drills.txt` was not
  replayed one by one; the two ROS captures above are the replay evidence.
- No benchmark JSONL export and no LeRobot adapter (later M4 slices).
- Mock/simulation only; no hardware replay and no bus measurement.
