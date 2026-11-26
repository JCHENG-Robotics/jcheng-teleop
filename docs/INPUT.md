# Input model and adapter boundary — jcheng-teleop

> Status: **Frozen for M1** as of 2026-11-26. The sample contract and
> device-free adapters are implemented; no input device is opened by this
> repository. A physical adapter is operator-side.

## 1. Boundary

```text
physical device            operator-side adapter            this repository
(gamepad, keyboard,   →    reads the device, normalizes →  InputSource
 wheel, pendant,           units once, emits samples        (core, no device)
 leader arm)               over a local transport
```

Rules:

- The adapter owns the device. This repository owns the sample contract and
  the conditioning/core semantics.
- The adapter never publishes robot intent, never talks to the robot and never
  knows the lease.
- A device failure is a sample gap, never a synthetic sample. The deadman and
  watchdog handle the gap.
- `capability-manifest.v1` fixes `hardware_access: none`; a device-owning
  adapter in this repository is not admissible. If one is ever proposed, it
  needs a governance boundary review before adoption.
- The repository does not import `evdev`, `hidapi`, `pygame.joystick`, SDL, a
  vendor SDK or a serial library. `pyserial`/serial paths are forbidden.

## 2. Adapters

| Adapter | Device in this repo | Transport | Milestone |
|---|---|---|---|
| Virtual | none | In-process scripted samples | M1 |
| Keyboard | none; consumes injected key events | `KeySource`; a terminal wrapper is operator-side | M1 mapping |
| JSONL | none | Newline JSON over stdin or a local Unix socket | M1 |
| Gamepad | none; consumes a `JoyFrame` | Injected `JoySource`; real source operator-side | M1 semantics |
| Leader arm | none | JSONL absolute positions + enable | M6 |
| Studio | none | Local studio bridge (browser/HTTP) | M5 |
| Replay | none | Sealed capture | M4 |

A real gamepad can be provided by an operator-side ROS 2 `joy` node or an
SDL/evdev process that emits the JSONL contract. The ROS `joy` package is a
BSD-licensed operator-side dependency; it is not a dependency of this
repository.

## 3. Sample contract

One JSON object per line for the JSONL transport; the in-process model uses
the same fields.

```json
{
  "schema": "jcheng.teleop.input.v1",
  "source_id": "operator_gamepad_01",
  "source_class": "gamepad",
  "seq": 120,
  "t_source_ns": 1234567890123,
  "t_host_mono_ns": 1234567890456,
  "mode": "JOINT_VELOCITY",
  "joint_positions_rad": [],
  "joint_velocities_rad_s": [0.10, 0.00, 0.00, 0.00, 0.00],
  "cartesian_twist": null,
  "gripper_normalized": 0.40,
  "deadman": true,
  "calibration_id": null,
  "profile_id": "armpi_ultra",
  "session_hint": "sess-01"
}
```

| Field | Meaning |
|---|---|
| `source_id` | Stable adapter identity; recorded in every capture |
| `source_class` | `keyboard|gamepad|leader_arm|jsonl|virtual|studio` |
| `seq` | Strictly increasing per session; never reused or reordered |
| `t_source_ns` | Adapter clock at capture; monotonic |
| `t_host_mono_ns` | Host monotonic clock at receipt; used for watchdog |
| `mode` | `JOINT_POSITION`, `JOINT_VELOCITY`, `CARTESIAN_TWIST` (reserved); gripper is an orthogonal field |
| `joint_positions_rad` | Absolute joint targets for `JOINT_POSITION`, profile order |
| `joint_velocities_rad_s` | Per-joint velocity for `JOINT_VELOCITY`, profile order |
| `cartesian_twist` | Linear/angular velocity and frame for the reserved Cartesian mode |
| `gripper_normalized` | 0.0 closed .. 1.0 open; profile maps to actuator units |
| `deadman` | Operator held enable; not a safety-rated signal |
| `calibration_id` | Calibration in force for Cartesian or leader mapping |
| `profile_id` | Expected canonical profile; mismatch is rejected |
| `session_hint` | Optional session identity; the system lease remains authoritative |

Units are SI where applicable: rad, rad/s, m/s. The adapter normalizes raw
units exactly once and documents the conversion with `source_id`.

## 4. Conditioning rules

1. **Validate.** Schema, finite floats, vector length, one arm mode payload
   (gripper is orthogonal), known mode, profile match. Invalid → reject, count,
   no intent.
2. **Order.** `seq` strictly increasing; `t_source_ns` non-decreasing. A
   rollback or duplicate is rejected, never repaired.
3. **Deadzone.** Per-axis deadzone with hysteresis. Inside the deadzone the
   output is exactly zero; hysteresis prevents chatter.
4. **Scale once.** The adapter or the profile applies the raw-to-SI scale; the
   core does not apply a second factor.
5. **Bound.** Per-axis clamp to the profile/session limit. An over-limit
   request produces exactly one `LIMIT_CLAMPED` event per continuous
   saturation episode, with requested and applied values.
6. **Rate.** Emit at a fixed period at or below `max_rate_hz` (50 Hz planned).
   No burst catch-up. A late tick emits at most one sample and records
   `LOOP_OVERRUN`.
7. **Neutral on release.** Releasing the deadman emits one mode-specific stop
   intent with `deadman=false` (zero velocity, hold position, or hold gripper),
   then silence. An all-zero position vector is never a stop. The last command
   is never latched as a new motion.
8. **Mode changes.** Only with the deadman released and a neutral state; a new
   enable edge is required. A Cartesian target is never replayed as joint
   motion.

## 5. Keyboard mapping (M1)

The keyboard adapter reads terminal key events, not `/dev/input`. A suggested
default (the binding is configurable and recorded):

| Key | Action |
|---|---|
| `Space` hold | Deadman enable |
| `W`/`S` | Joint 1 +/− |
| `A`/`D` | Joint 2 +/− |
| `Q`/`E` | Joint 3 +/− |
| `R`/`F` | Joint 4 +/− |
| `T`/`G` | Joint 5 +/− |
| `O`/`C` | Gripper open/close |
| `1`/`2` | Select joint-velocity / joint-position mode (neutral only) |
| `Esc` | Stop and release |

Rules:

- Key release is an event; the adapter does not rely on OS auto-repeat.
- Focus loss or terminal detach is a sample gap; the deadman/watchdog stops motion. An explicit adapter-health event is M2.
- The keyboard is a development and fallback input, not a precision
  teleoperation device.

## 6. Gamepad mapping (M1 semantics)

The adapter consumes a normalized `JoyFrame`:

```text
axes:    [left_x, left_y, right_x, right_y, trigger_l, trigger_r, ...]
buttons: [deadman, mode, gripper_open, gripper_close, stop, ...]
```

Rules:

- The deadman is a held button (default: right trigger or a shoulder button).
- A mode button changes mode only in neutral and with the deadman released.
- A stop button triggers the stop path and requires a new enable edge.
- Axes are normalized to `[-1, 1]`; the adapter applies the deadzone and
  documents the mapping.
- No turbo mode, no hidden scaling, no auto-repeat.
- A disconnect or focus loss is a sample gap; the deadman/watchdog stops motion.

A real gamepad driver is operator-side. The repository tests the mapping with
a `VirtualJoySource`; it does not open a device.

## 7. Leader arm (M6, reserved)

The leader arm adapter is operator-side and emits absolute joint positions,
gripper state and a deadman signal over the JSONL contract. Requirements:

- A kinematically equivalent leader is preferred; the binding maps leader
  joints to follower joints with sign/offset/scale.
- Calibration is recorded (`calibration_id`) and validated; a missing or stale
  calibration refuses position mode.
- The leader's joint limits and the follower's limits are separate; the
  follower profile remains authoritative.
- A leader disconnect is a sample gap; the deadman/watchdog stops motion and there is no synthetic hold.

## 8. Studio (M5, reserved)

Studio may display teleop state and send a stop request through the system
boundary. If a browser gamepad is used, it is an operator-side input source
behind the same sample contract; studio does not publish intent and the browser
does not call the gateway directly.

## 9. Mapping to the wire

| Wire field (v0.1) | Source | v0.2 proposal |
|---|---|---|
| `header.stamp` | `t_source_ns` | Same; the intake records it for latency/provenance and checks a sync bound only when one is measured |
| `seq` | Sample `seq` for ordering | Session assigns a strictly increasing wire seq per submit |
| `lease_id` | Session lease from the system | Same |
| `source` | `source_id` | Same |
| `contract` | Pinned contract version/hash | Same |
| `mode` | `JOINT_VELOCITY`/`CARTESIAN_VELOCITY` | Adds `JOINT_POSITION`; gripper is a separate `gripper_normalized`/`gripper_valid` field |
| `joint_velocity_rad_s` | Conditioned velocity | Same |
| `cartesian_velocity` | Reserved | Same, mode-conditional |
| `deadman` | Enable input | Same |
| — | — | `joint_positions_rad`, `gripper_normalized`, `gripper_valid`, `session_id`, `episode_id`, `profile_hash`, `source_class` |

v0.1 has no gripper field and no position field. Continuous gripper and
leader-position teleoperation are not claimed until v0.2 is accepted.

## 10. M1 exit criteria

- The sample contract and conditioning rules are frozen in this document.
- A ROS-free core and tests cover deadzone, bounds, rate, ordering and the
  deadman state machine.
- Tests prove no sample is emitted without a valid enable edge and every
  over-limit request produces one counted limit event.
- No device is opened, no DDS domain is joined and no robot is used.
- A real gamepad/leader adapter remains operator-side and outside the
  capability boundary.

## 11. Related

- [Architecture](ARCHITECTURE.md)
- [Teleop core](TELEOP_CORE.md)
- [Safety model](SAFETY_MODEL.md)
- [M1 plan](M1_PLAN.md)
- [Integration contract](INTEGRATION_CONTRACT.md)
- [`jcheng-interfaces` `TeleopCommand`](https://github.com/JCHENG-Robotics/jcheng-interfaces/blob/main/ros2_ws/src/jcheng_interfaces/msg/TeleopCommand.msg)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
