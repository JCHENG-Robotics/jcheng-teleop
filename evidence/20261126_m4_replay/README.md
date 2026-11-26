# M4 offline replay (slice 1)

> Status: **Partially verified (L1, recorded mock + simulation, 2026-11-26)**.
> Input replay and anomaly scan only; no command replay, benchmark export or
> LeRobot adapter yet. No hardware.

## Scope

`src/jcheng_teleop/replay/`:

- `capture_reader.py`: verifies a sealed capture (hashes and schemas) and
  parses the five streams. An unverified capture is not replayed.
- `replay.py`: re-derives action intents from `input.jsonl` with a fresh
  `Conditioner`/`ActionMapper` and compares them field by field to
  `action.jsonl`. Stop intents are skipped (the session, not the mapper,
  generates them).
- `anomaly.py`: pure scan for schema, tick/time ordering, stop/deadman
  consistency, command/action coverage and observation label violations.
- `cli.py`: `jcheng-teleop-replay`; exit 0 clean, 1 divergence/anomaly error,
  2 verification or profile mismatch. It imports no rclpy, gateway, socket or
  subprocess module (static test).

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

`python3 -m pytest -q tests/test_replay.py` — **10 passed**. Full suite:
**147 passed**.

Covered: replay reproduces recorded actions; a tampered action is detected;
missing input is a defect; a `bus` label in a mock capture and a `simulated`
label outside simulation are errors; non-monotonic time and a stop with
`deadman=true` are errors; CLI end-to-end and profile-hash mismatch; the replay
package imports no runtime/network module.

## Limits

- Input replay only. `command.jsonl` does not record the submitted payload, so
  command replay (recorded action vs re-derived wire command) is not
  implemented.
- Stop intents are skipped by replay; they are checked by the anomaly scan
  (deadman/ordering) and are now recorded.
- The 30-episode set in `evidence/20261126_m3_capture/drills.txt` was not
  replayed one by one; the two ROS captures above are the replay evidence.
- No benchmark JSONL export and no LeRobot adapter (later M4 slices).
- Mock/simulation only; no hardware replay and no bus measurement.
