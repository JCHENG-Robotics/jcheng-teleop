# M3 capture core (slice 1)

> Status: **Partially verified (L1/L2, mock only, 2026-11-26)**. No hardware, no
> simulation session, no observation stream. 30-episode acceptance is **not**
> met; this record covers the recorder core, provenance gate and seal/verify.

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
- `verify.py`: read-only re-read and hash verification; a capture with dropped
  rows or a recorder fault is `degraded`, a failed check is `invalid`.
- `core/runner.py`: optional `observer` hook. An observer exception is counted
  and swallowed; a `False` return requests a system stop (`recorder_fault`).
- CLI: `--record DATA_ROOT`, `--capture-id`, `--task`. CLI captures are
  `environment_class=mock`, `source_class=scripted`.

## Tests

`python3 -m pytest -q tests/test_capture.py` — **20 passed**. Full suite:
**131 passed**; gate OK.

Covered: provenance rules (mock/simulation/hardware/scripted/policy/replay),
capture root inside a git worktree rejected, bounded-queue drop order, no raise
after close, storage fault propagation, seal + manifest + SHA256SUMS + verify,
raw lease id absent, tamper detection, deterministic streams, observer
exception isolation, observer-requested stop, CLI end-to-end and CLI refusal
inside the repository.

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

## Limits

- `observation.jsonl` is empty: the M1/mock path has no `RobotState` stream.
  Measured/simulated rows require the M2 simulation bridge or a system bus
  read; neither is recorded here.
- No media, no camera frames, no `README.txt`.
- No hardware or simulation capture session; only the mock CLI.
- The session-close event is not recorded; the final state is only in the CLI
  summary.
- Manifest policy/checkpoint/lease-reference fields are `null` where the mock
  path has no value; they are placeholders, not measurements.
- 30 episodes × 60 s valid-capture acceptance and a disk-full session-stop
  drill are still open.
