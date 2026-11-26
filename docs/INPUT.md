# Input model and conditioning — jcheng-teleop

> Status: **Proposed** as of 2026-11-26; to be frozen at M1.
> Nothing here is implemented and no input device is opened by this
> repository.

## 1. Boundary

The physical device is owned by an operator-side adapter, not by this
repository:

```text
physical device  ->  operator-side adapter  ->  input samples  ->  this core
   (gamepad,           (outside the repo,       (documented        (M1, ROS-free)
    wheel,              reads the device)        line protocol)
    pendant)
```

Rules:

- The adapter samples the device, normalizes units once and emits input
  samples. It never publishes robot intent and never talks to the robot.
- This repository's core is device-agnostic. It does not open `/dev/input`,
  does not use `evdev`, `hidapi`, SDL or a vendor SDK, and ships no adapter.
- An adapter failure is surfaced as sample loss, never hidden with a synthetic
  sample. The deadman handles the gap.
- If a device-owning adapter is ever proposed for this repository,
  `capability-manifest.v1` cannot express device access; the boundary must be
  reviewed in `.github` before adoption.

## 2. Sample fields (draft)

| Field | Meaning |
|---|---|
| `source` | stable adapter identity and device class, for the audit record |
| `seq` | strictly increasing integer per session; never reused or reordered |
| `stamp` | sample time from the adapter clock, with the host offset when available |
| `mode` | `JOINT_VELOCITY` or `CARTESIAN_VELOCITY` |
| `joint_velocity_rad_s` | per-joint velocity for `JOINT_VELOCITY`; empty otherwise |
| `cartesian_velocity` | linear and angular velocity for `CARTESIAN_VELOCITY`; empty otherwise |
| `deadman` | the operator enable input, held for as long as motion is requested |
| `calibration_id` | identifier of the calibration in force for Cartesian intent, when required |

The sample is a proposal to the intent plane, not a robot command. Units are
SI: rad/s for joints, m/s and rad/s for the Cartesian twist.

## 3. Conditioning rules

1. **Deadzone.** Each axis has a deadzone with hysteresis. A value inside the
   deadzone becomes exactly zero; no residual drift is forwarded.
2. **Scaling.** The adapter or the core normalizes raw device units to SI
   exactly once, and the conversion is documented with the adapter identity.
3. **Per-axis bound.** Every axis is bounded by the robot profile before it is
   published. An over-limit request produces a counted limit event; it is
   never silently truncated without a record.
4. **Rate limit.** The core emits at a fixed period at or below the manifest's
   `max_rate_hz` (planned 50 Hz). It does not emit bursts to catch up.
5. **Ordering.** `seq` increases strictly. `stamp` must be monotonic; a sample
   outside the system's 200 ms acceptance window is rejected, not rebased.
6. **Neutral on release.** Releasing the deadman emits one zero-velocity
   sample with `deadman: false`, then silence. The last command is never
   latched.
7. **Mode changes.** A mode change requires the deadman to be released and
   re-engaged, so a stale Cartesian target cannot be replayed as joint motion.

## 4. Deadman state machine (M1 proposal)

| State | Entry | Output |
|---|---|---|
| `DISABLED` | start; no lease; lease lost; internal error | nothing |
| `ARMED` | valid lease and a fresh enable edge | bounded samples |
| `EXPIRED` | no sample for longer than `deadman_ms` (planned 300 ms) | zero-velocity sample with `deadman: false`, then silence |

Transitions out of `EXPIRED` or `DISABLED` require a **new** enable edge after
the condition clears. Returning input alone does not resume motion. The state
machine is unit-tested at M1; the system layer's deadman remains an independent
second line of defense.

## 5. Mapping to `TeleopCommand` (M2)

| `TeleopCommand` field | Source |
|---|---|
| `header.stamp` | sample `stamp`; never the publish time |
| `seq` | sample `seq`, strictly increasing |
| `lease_id` | the lease granted by the system layer |
| `source` | adapter identity |
| `contract` | the `jcheng-interfaces` contract version in force |
| `mode` | `JOINT_VELOCITY` or `CARTESIAN_VELOCITY` |
| `joint_velocity_rad_s` | conditioned joint velocities |
| `cartesian_velocity` | conditioned Cartesian twist |
| `deadman` | the enable input |

The reserved message has no gripper field. Gripper teleoperation is not
expressible in the v0.1.0 contract and is not claimed; adding it is a contract
change.

## 6. Recording and provenance

- No recording is stored in this repository.
- If a supervised session is recorded, commanded intent and measured robot
  state are stored separately, outside the repository.
- `/joint_states` is a command cache, not a measurement. A session record that
  needs pose truth must carry an independent bus read.
- Recorded sessions are labelled with the adapter identity, the contract hash
  and the calibration identifiers in force.

## 7. M1 exit criteria

- The sample format and conditioning rules above are frozen in this document.
- A ROS-free core and its tests cover deadzone, bounds, rate limit, ordering
  and the deadman state machine.
- Tests prove that no sample is emitted without a valid enable edge and that
  an over-limit request produces a counted limit event.
- No device is opened, no DDS domain is joined and no robot is used.

## 8. Related

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — input, intent and system planes.
- [`INTEGRATION.md`](INTEGRATION.md) — lease, preemption and failure semantics.
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces) — `TeleopCommand.msg`.
- [README](../README.md) / [ROADMAP](../ROADMAP.md) / [ACCEPTANCE](../ACCEPTANCE.md).
