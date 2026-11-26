# Safety model — jcheng-teleop

> Status: **Implemented for M1** as of 2026-11-26. This is a local design and
> implementation model, not a certification or a safety-rated function. The
> platform has no e-stop, brake, encoder or self-collision model. The system
> layer's stop latch is a software stop, not an e-stop.

## 1. Scope and non-claims

This document defines the local safety behavior of the teleoperation
capability and its interaction with the system layer. It does not define the
system's safety policy, the robot's physical limits, or a certified safety
function.

Non-claims:

- The operator deadman is not an e-stop, a safety-rated device or a substitute
  for a risk assessment.
- A stop intent, a released lease or a latched stop proves only that the
  software path was asked to stop. It does not prove physical standstill until
  a bus read or other independent measurement confirms it.
- The platform has no e-stop, brake, encoder, force sensing or self-collision
  model. Collision avoidance is not claimed.
- Simulation and mock behavior are not hardware evidence.

## 2. Defense layers

| Layer | Owner | Responsibility | Cannot |
|---|---|---|---|
| Input adapter | Operator side | Produce fresh samples; report disconnect/focus loss | Grant authority, synthesize samples |
| Teleop core | This repo | Validate, condition, deadman, watchdog, local bounds, mode protection | Authorize motion, clear a system latch |
| Gateway adapter | This repo | Present the lease, submit bounded intent, request stop | Mint a lease, bypass the gateway/arbiter |
| System gateway/arbiter | `jcheng-system` | Lease, scope, arbitration, limits, stop latch, evidence | Guarantee physical stop without a bus read |
| Robot/plant | Vendor / simulation | Execute bounded commands; report state | Provide an e-stop or certified safety |

The layers are independent on purpose: a teleop bug must not be the only thing
between an operator and motion, and a system fault must not require teleop to
recover motion.

## 3. Local state machine

```text
                 config/profile/storage valid
BOOT ──► SELFTEST ─────────────────────────────► IDLE
  │         │ invalid                              │ lease valid + state fresh
  │         ▼                                      │ + deadman released
  │       FAULT                                    ▼
  │         ▲                                    READY
  │         │ fault                              │ fresh enable edge
  │         │                                    ▼
  │      STOPPING ◄──────── stop/fault ─────── ACTIVE
  │         │                                    │
  │         ├── clean ──► IDLE                   │ lease preempted
  │         └── fault ──► FAULT                  ▼
  │                                           PREEMPTED
  └──────────────────────────────────────────────┘
```

### 3.1 States

| State | Entry guard | Allowed output | Exit |
|---|---|---|---|
| `BOOT` | Process start | None | Config loaded → `SELFTEST` |
| `SELFTEST` | Profile, binding, contract, clock, storage checks | None | Pass → `IDLE`; fail → `FAULT` |
| `IDLE` | No active lease, or not yet ready | None | Lease + fresh state + deadman released → `READY` |
| `READY` | Valid lease, fresh state, neutral input, deadman released | None | Fresh enable edge → `ACTIVE`; lease loss → `PREEMPTED` |
| `ACTIVE` | Enable edge, fresh sample, valid mode | Bounded intent | Any stop condition → `STOPPING` |
| `STOPPING` | Stop condition | Exactly one mode-specific stop intent + `deadman=false`, then silence (see §5.1) | Clean stop → `IDLE`; fault → `FAULT` |

M1 treats `STOPPING` as an atomic internal phase: a synchronous `stop()` enters it, emits at most one stop intent and returns the final `IDLE`/`PREEMPTED`/`FAULT` state. A caller observes the final state, not an intermediate `STOPPING` tick; M2 may expose the phase explicitly.
| `FAULT` | Local fault or system latch observed | None | Local `reset()` (M1) + fresh state + new lease + new enable edge → `READY`; a system latch requires the system reset, not teleop |
| `PREEMPTED` | Lease lost to a higher-priority holder | None | New operator lease + fresh enable edge → `READY` |

### 3.2 Forbidden transitions

- `FAULT → ACTIVE` without an explicit operator reset and a new enable edge.
- `PREEMPTED → ACTIVE` automatically; the operator must re-acquire authority.
- `READY → ACTIVE` on a held deadman from before the stop; a **new** edge is
  required.
- Any state → `ACTIVE` while the system reports `stop_latched`, `FAULT`,
  `STATE_STALE`, a contract mismatch or a profile mismatch.

## 4. Deadman and watchdog

| Timer | Value | Source | Behavior on expiry |
|---|---|---|---|
| Input staleness | 300 ms proposed | Last accepted sample at the injected session clock | `STOPPING`; one mode-specific stop intent + `deadman=false`; `INPUT_STALE`; session abort, no auto-resume |
| Enable edge timeout | 300 ms proposed | Last `deadman=true` sample | Same as input staleness |
| Loop watchdog | 2 × tick (40 ms at 50 Hz) | Injected monotonic clock | `STOPPING`; `LOOP_WATCHDOG`/`LOOP_OVERRUN`; no catch-up |
| Lease renewal | TTL/3 (≈333 ms at 1 s TTL) | Gateway result | `LEASE_LOST`; stop; no auto re-acquire |
| Gateway state freshness | 500 ms system bound | `RobotState.fresh`/stamp | No new intent; `STATE_STALE` |
| Stop confirmation | System-defined | Bus read / system result | Report `UNKNOWN` if unconfirmed; never assert physical stop |

Rules:

- A released deadman emits one mode-specific stop intent with `deadman=false`,
  then silence. The last command is never latched as a new motion.
- Returning input after a timeout does not resume motion. A new enable edge is
  required.
- The system has its own deadman/timeout obligation. Teleop's 300 ms is a
  local bound, not a substitute for the system's independent stop.
- The system's current `state_timeout_s` is 0.5 s; teleop is stricter. The
  system-side teleoperation intake must enforce its own command window.

### 4.1 Stop budget is not one 300 ms end-to-end number

The 300 ms value is the **input-timeout detection threshold**, not an
end-to-end stop guarantee. The budget is reported in parts:

| Path | Detection | Local action | Transport + intake | Actuation |
|---|---|---|---|---|
| Deadman release | next tick (≤20 ms at 50 Hz) | one stop intent | ≤50 ms target | measured separately |
| Input timeout | 300 ms + next tick | one stop intent | ≤50 ms target | measured separately |
| Loop watchdog | 2 ticks (40 ms) | one stop intent | ≤50 ms target | measured separately |
| Lease loss | next gateway check | stop output; release | measured | measured separately |

Acceptance wording:

- **Deadman release:** the stop intent is emitted within one tick; the system
  must accept the abort/stop within 300 ms, measured.
- **Input timeout:** detection occurs at 300 ms, then the stop intent is
  emitted within one tick; the end-to-end time is
  `300 ms + transport + intake + actuation` and is reported as a distribution.
  It is **not** claimed to be ≤300 ms end-to-end.
- **Actuation:** the bus read or system confirmation is a separate measurement;
  without it, the stop is `unknown`.

This split prevents a design that spends the whole budget on detection and
then labels the result a 300 ms stop.

## 5. Stop paths

Two stop classes are distinct:

- **Session abort** stops intent output and releases the lease; it must not
  latch the whole system. Deadman release, input timeout, lease loss and
  normal operator hand-back use this class.
- **System stop** is an explicit operator/safety stop; it may latch. It is
  reserved for an operator stop, an observed safety fault or an unknown
  outcome that requires a bus check.

| Path | Class | Action | Evidence |
|---|---|---|---|
| Operator deadman release | Session abort | One mode-specific stop intent; `STOPPING`; release lease | `DEADMAN_RELEASED`, command log |
| Input timeout | Session abort | One mode-specific stop intent; `STOPPING`; release lease | `INPUT_STALE`, command log |
| Operator stop | System stop | One mode-specific stop intent; request system stop once; `STOPPING` | `STOP_REQUESTED`, stop result |
| Lease loss/expiry/preemption | Session abort | Stop output; release if still held; `PREEMPTED`; no re-acquire | `LEASE_*` |
| Gateway ambiguity | Session abort then system stop if outcome unknown | Stop output; release lease; request system stop only when the outcome is unknown or the intake cannot abort | `GATEWAY_UNKNOWN` |
| Local limit/fault | Session abort or system stop if repeated | Stop output; `FAULT`; no retry | `FAULT_LATCHED` |
| System stop latch | System stop | No output; `FAULT` until operator reset | `SYSTEM_LATCH` |
| Recorder failure | Session abort | Stop output; `FAULT`; recording failure never blocks stop | `RECORDER_FAULT` |
| Process crash | Session abort | No output; system lease TTL expires | System evidence |

The stop path:

1. is not rate-limited, smoothed or queued behind recording;
2. sends at most one mode-specific stop intent, then stops publishing;
3. calls the system **stop** at most once per system-stop episode, not on every
   session abort;
4. never retries motion;
5. records whether the stop was confirmed, unconfirmed or unknown.

### 5.1 Mode-specific stop intent

An all-zero joint vector is a valid **velocity** stop but a dangerous
**position** command: it means "move to 0 rad". The stop intent is therefore
mode-specific, and an all-zero position vector is forbidden as a stop.

| Mode | Stop intent |
|---|---|
| `JOINT_VELOCITY` | zero velocity vector, `deadman=false` |
| `JOINT_POSITION` | hold the last accepted target, `deadman=false`; if no prior target, emit no command and rely on the system hold; never all-zero |
| `CARTESIAN_VELOCITY`/twist | zero linear and angular velocity, `deadman=false` |
| Gripper (orthogonal field) | hold the last accepted normalized value or set `gripper_valid=false`; never a blind open/close |
| No active mode | no command; silence |

The system's hold/latch path remains the independent backstop. The teleop stop
intent is cooperative; it is not proof of physical standstill.

A stop request is not proof of physical standstill. Where the system returns
`StopResult` without confirmation, teleop reports `stop_confirmed: unknown`.

## 6. Limits and bounds

| Bound | Source | Behavior |
|---|---|---|
| Joint position | Canonical profile | Clamp at the local mapper; system validates again |
| Joint velocity | Canonical profile × session scale | Clamp; count `LIMIT_CLAMPED` once per saturation episode |
| Joint acceleration | Profile where available | The M1 core may pass through; the system remains authoritative |
| Step per tick | `max_velocity × tick` | Clamp; no accumulated catch-up |
| Gripper | Profile range | Normalize 0..1; map to actuator units; never exceed profile range |
| Cartesian workspace | Profile workspace | Reserved; no Cartesian claim before the system supports it |
| Clock offset | Session/config | Refuse or degrade; never rebase silently |

The local clamp is a convenience and a first line of defense. It does not
replace the system's validation. A system `VELOCITY_LIMIT` or `JOINT_LIMIT`
rejection is recorded and must stop the session if it repeats.

## 7. Mode changes

A mode change is a session-level operation, not a per-tick switch.

- Only allowed from `READY` or `IDLE`, with the deadman released.
- Requires a neutral sample and a fresh enable edge after the change.
- The old mode's payload is discarded; it is never reinterpreted in the new
  mode.
- A Cartesian target cannot be replayed as joint motion.
- A mode change while `ACTIVE` first triggers `STOPPING`; the new mode is
  selected only after the stop completes and the operator re-arms.
- The active mode, binding hash and profile hash are recorded in every capture.

## 8. Hazard analysis

Severity: S1 negligible, S2 minor, S3 serious, S4 critical. Likelihood: L1
remote, L2 unlikely, L3 possible, L4 likely. This is a design aid, not a
certified risk assessment.

| ID | Hazard | Cause | Severity | Likelihood | Controls | Residual risk |
|---|---|---|---|---|---|---|
| H1 | Runaway motion from stale command | Input/adapter/gateway stalls | S4 | L2 | Deadman, watchdog, system lease/TTL, system stop latch, one mode-specific stop intent then silence | Actuator/bus latency; no e-stop |
| H2 | Wrong robot profile | Wrong file, stale hash, copy/paste | S4 | L2 | Profile hash check, joint count/order/sign validation, refuse session | Human misconfiguration if hashes are bypassed |
| H3 | Mode confusion | Operator thinks velocity but position active | S3 | L3 | Mode displayed, re-arm on change, one payload per sample | UI/operator error |
| H4 | Lease conflict/preemption race | Two operators, priority change | S3 | L2 | Priority 40, exclusive lease, preemption stop, no auto re-acquire | Preemption surfaces as `LEASE_EXPIRED` today |
| H5 | Gateway partition | Wi-Fi/USB/process loss | S3 | L3 | Lease TTL, local stop, no retry | System stop bound unknown |
| H6 | Clock skew | Host/robot clocks drift | S3 | L2 | Source monotonic time, offset/uncertainty recorded, stale rejection | No PTP on the platform |
| H7 | Profile/unit error (rad vs m, sign) | Mixed units, wrong binding | S4 | L2 | Typed units, profile validation, sign/offset tests | Prismatic joints not yet in the arm profile |
| H8 | Dataset contamination | Simulation recorded as hardware | S3 | L3 | Immutable environment/source class, validator, no auto-relabel | Human mislabel at capture time |
| H9 | Recorder blocks stop | Disk stall, lock contention | S3 | L2 | Off-control-path writer, bounded queue, independent stop | Storage exhaustion |
| H10 | Duplicate command after reconnect | Replay/queue | S3 | L2 | Strict seq/stamp, no auto reconnect, no retry | Transport may duplicate; system rejects/idempotency |
| H11 | Operator input device failure | Unplug, focus loss, battery | S3 | L3 | Sample timeout, deadman, explicit stale event | OS driver may hang |
| H12 | System stop latch bypass | Teleop clears or ignores latch | S4 | L1 | Teleop cannot clear; reset is operator/system only | None if contract enforced |
| H13 | Simulation connected to real gateway | Wrong URL/profile | S4 | L1 | Environment guard, explicit `--environment`, no default real | Operator overrides |
| H14 | Gripper force/over-travel | No force sensing | S3 | L2 | Range clamp, profile limit, supervised session | No force feedback |
| H15 | Cartesian frame/units error | Wrong frame or twist | S3 | L2 | Frame check, reserved until system support | Not applicable before M6 |

## 9. Sim/real isolation

- The default environment is `mock`; the default gateway is in-process.
- A test-only HTTP gateway path is allowed only when `GET /v1/health` reports
  `capabilities` containing `"mock"`; a loopback URL alone is not proof (an SSH
  tunnel to the robot gateway is also loopback). The path records
  `environment_class=mock` and refuses a gateway that does not identify as
  mock.
- A `simulation` environment may only use a simulation-labeled profile and a
  simulation gateway/bridge; it must not accept a real robot URL.
- A `hardware` environment requires an explicit operator authorization, a
  real profile hash, a fresh bus measurement and a supervised session. It is
  not implemented before M6.
- Replay has no gateway port at all. It cannot connect to a live system.
- Every capture and report carries `environment_class`
  (`mock|simulation|hardware`) and `source_class`
  (`human_teleop|human_correction|autonomous_grasp|policy_execution|scripted|replay`).
  The environment class is immutable; a derived dataset preserves lineage.
- A simulation truth label (`/sim/truth/source=simulated`) is recorded as
  simulation evidence, never as hardware.

## 10. Verification matrix

| Claim | Level | Method |
|---|---|---|
| No device/motion token | L0 | Static scan; review |
| No command without enable edge | L1 | Table tests; sequence oracle |
| Deadman timeout ≤ one tick | L1 | Manual clock; boundary tests |
| No burst catch-up | L1 | Late-clock test |
| Over-limit clamp + one event | L1 | Boundary and saturation tests |
| Profile mismatch refused | L1 | Hash/order/sign fixtures |
| No auto-resume after fault | L1 | State-machine tests |
| Lease loss stops output | L2 | Mock gateway fault injection |
| Stop sent once, no retry | L2 | Recording mock transport |
| System lease/preemption/stop | L3 | System mock + simulation (M2) |
| Physical stop confirmation | L5 | Supervised session, bus read (M6) |

## 11. Residual risks and open issues

- No e-stop, brake, encoder, force sensing or self-collision model.
- The system's vendor executor is single-joint step-based at about 5 commands/s;
  a high-rate multi-joint teleoperation loop has no approved path yet.
- Preemption currently surfaces as `LEASE_EXPIRED` in the system; teleop must
  distinguish by event if available and otherwise treat both as stop.
- The system does not revoke leases on a safety latch or bus-unknown today;
  teleop must stop on the observed latch, not rely on lease invalidation.
- The system has no command timestamp/seq window or deadman enforcement; the
  proposed intake must add them.
- Stop confirmation is not implemented in the system (`StopResult` has no
  confirmation field); teleop reports unknown.
- Clock synchronization is host/robot dependent; there is no PTP guarantee.
- Operator input device drivers are outside the repository; their failure
  behavior is only as good as the sample timeout.

## 12. Related

- [Architecture](ARCHITECTURE.md)
- [Teleop core](TELEOP_CORE.md)
- [Integration contract](INTEGRATION_CONTRACT.md)
- [Data collection](DATA_COLLECTION.md)
- [M1 plan](M1_PLAN.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system` safety](https://github.com/JCHENG-Robotics/jcheng-system/blob/main/docs/SAFETY.md)
- [`.github` hardware workflow](https://github.com/JCHENG-Robotics/.github/blob/main/docs/hardware-workflow.md)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
