# M3 capture core and observation rows (slices 1–2)

> Status: **Partially verified (L1/L2 mock + simulation, 2026-11-26)**. No
> hardware. 30-episode acceptance and the disk-full drill are **not** met.
> This record covers the recorder core, provenance gate, seal/verify, labelled
> observation rows and the ROS demo harness capture.

## Implemented

`src/jcheng_teleop/capture/`:

- `provenance.py`: `jcheng.teleop.capture.v1` identity/environment/session/task
  metadata. Validation requires hardware authorization fields for
  `environment_class=hardware`, a truth label and simulator identity for
  `simulation`, generator identity/seed/config hash for `scripted`, and
  policy identity for `policy_execution`/`human_correction`. `replay` is
  rejected: a replay is a derived artifact, not a new capture.
- `writer.py`: append-only JSONL writer with a bounded queue and a background
  drain thread. `record()` does no storage I/O and never raises; a storage
  error marks the writer faulted and is reported at seal. Ordinary rows are
  dropped before priority rows (stop intent, gateway result, fault/threshold
  events). Sealing writes `manifest.json` and `SHA256SUMS`.
- `recorder.py`: maps `TickResult`/`InputSample` into `input`, `action`,
  `command` and `events` rows; lease ids are hashed (`lease_ref`), never raw.
  Public `record_input`/`record_action`/`record_event`/`record_observation`
  writers share one logical tick.
- `observation.py`: labelled state rows copied from `/jcheng/telemetry/state`;
  `bus` is accepted only in a hardware capture, `simulated` only in a
  simulation capture, and a rejected row becomes an `OBSERVATION_REJECTED`
  event instead of an exception.
- `verify.py`: read-only re-read and hash verification; a capture with dropped
  rows or a recorder fault is `degraded`, a failed check is `invalid`.
- `core/runner.py`: optional `observer` hook. An observer exception is counted
  and swallowed; a `False` return requests a system stop (`recorder_fault`).
- CLI: `--record DATA_ROOT`, `--capture-id`, `--task`. CLI captures are
  `environment_class=mock`, `source_class=scripted`.
- ROS harness (`jcheng_teleop_ros`): optional capture with `record_root`,
  `capture_id`, `task`, `environment_class`, simulation identity parameters
  and `state_topic`; records input/action/observation rows and a
  `SESSION_CLOSED` event, and stops the script with a neutral frame on a
  capture fault.

## Tests

`python3 -m pytest -q tests/test_capture.py` — **26 passed**. Full suite:
**137 passed**; gate OK.

Covered: provenance rules (mock/simulation/hardware/scripted/policy/replay),
capture root inside a git worktree rejected, bounded-queue drop order, no raise
after close, storage fault propagation, seal + manifest + SHA256SUMS + verify,
raw lease id absent, tamper detection, deterministic streams, observer
exception isolation, observer-requested stop, CLI end-to-end and CLI refusal
inside the repository; observation labels (mock `commanded`/`timed`,
simulation `measured`/`simulated`), rejection of `bus` outside hardware,
hardware acceptance of a bus measurement, and vector-length rejection.

## Demo capture (mock CLI, outside the repository)

```text
{"capture": {"dropped_priority": 0, "fault": null,
 "manifest_sha256": "sha256:822b6fe97c5723b56ac5e20f5ffae6a90cd6bac6082063ccfd59fd010716ac0a",
 "path": "/tmp/jcheng-m3-capture/demo-20261126", "rows_dropped": 0,
 "rows_written": {"action": 35, "command": 35, "events": 8, "input": 40, "observation": 0},
 "verify": "valid"}, "faults": 0, "state": "IDLE", "stop_sent": 1,
 "submitted": 35, "ticks": 40}
```

Manifest excerpt:

```json
{"environment_class": "mock", "source_class": "scripted",
 "sim_truth_label": null, "profile_source": "fixture"}
```

The files are `input.jsonl`, `action.jsonl`, `command.jsonl`,
`observation.jsonl` (empty), `events.jsonl`, `manifest.json`, `SHA256SUMS`.

## Observation rows (slice 2)

The ROS demo harness records `/jcheng/telemetry/state` (system runtime,
20 Hz) as observation rows and adds a `SESSION_CLOSED` event. Two integration
runs, both outside the repository under `/tmp/jcheng-m3-ros`:

| Capture | Runtime backend | Observation rows | Labels | Motion |
|---|---|---|---|---|
| `ros-mock-20261126` | mock stack | 252 | `commanded` / `timed` | none (not armed) |
| `ros-sim-motion-20261126` | domain-43 sim bridge | 188 | `measured` / `simulated` | joint1 0 → 0.1361 rad |

```text
mock:  status valid, env mock,       sim_truth_label null
sim:   status valid, env simulation, truth label /sim/truth/source=simulated,
       source jcheng_runtime/sim_bridge, simulator jcheng-simulation 54993cc
```

Both captures verify `valid`; the simulation manifest records the truth label
and the simulator identity, so the rows cannot be mistaken for hardware. The
label gate was also exercised negatively in tests: a `bus` row in a mock or
simulation capture is dropped and an `OBSERVATION_REJECTED` event is written.

## Limits

- The mock CLI still records no observation rows; only the ROS harness does.
- No media, no camera frames, no `README.txt`.
- No hardware capture session; the telemetry tap has only been exercised on
  `MockStack` and `RosSimHardwareBridge`.
- The CLI still does not record the session-close event; the ROS harness does.
- The mock capture was taken while the system was disarmed, so its observation
  positions are zero; it proves labels and plumbing, not tracking.
- Manifest policy/checkpoint/lease-reference fields are `null` where the mock
  path has no value; they are placeholders, not measurements.
- 30 episodes × 60 s valid-capture acceptance and a disk-full session-stop
  drill are still open.
