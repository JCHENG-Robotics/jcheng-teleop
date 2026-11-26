# Architecture — jcheng-teleop

> Status: **Experimental** as of 2026-11-26. Version 0.3.0.
> M0 design is approved; the M1 ROS-free core and CLI are implemented. M2 adds a
> test-only ROS intent publisher and simulation L3; there is still no input
> device access, no lease adapter, no production gateway client and no motion.
> The M2+ sections remain a design plan beyond that transport.

## 1. Position in the ecosystem

`jcheng-teleop` is an L3 capability. The repository was admitted at v0.1.0 as
an offline scaffold; v0.2.0 added the M0 design and v0.3.0 adds the M1 local
core without changing the runtime surface. It sits below the system layer and above the operator's input
surface:

```text
operator-side adapter (outside this repository)
  keyboard · gamepad · JSONL bridge · leader arm · studio bridge
        │  normalized input samples (versioned contract)
        ▼
┌────────────────────────── jcheng-teleop (L3) ──────────────────────────┐
│ input adapter → teleop core → action mapper → safety guard             │
│                      │             │                 │                 │
│                 robot profile  session/lease    gateway adapter        │
│                      │             │                 │                 │
│                 episode recorder  replay engine   dataset adapter       │
└────────────────────────────────────────────────────────────────────────┘
        │  teleoperation intent only                │  capture/dataset (outside git)
        ▼                                           ▼
jcheng-system (L2): gateway · lease · motion arbiter · safety supervisor
        │
        ▼
privileged motion plane / simulation plant (never addressed by teleop)
```

The system layer is the only origin of motion. Teleoperation publishes
**intent**; the system decides whether intent becomes motion. The repository
never calls `ExecuteMotion`, never publishes `/cmd_vel` or a vendor topic and
never writes a servo or motor device.

## 2. Trust and transport boundaries

| Boundary | Owner | Teleop may | Teleop must not |
|---|---|---|---|
| Operator input device | Operator workstation, outside this repo | Consume normalized samples over a documented local transport | Open `/dev/input`, `evdev`, `hidapi`, SDL, a vendor SDK or a serial port |
| Capability plane, domain 42 | System contract | Publish `TeleopCommand` (M2 onward) and read state/safety | Join domain 0/41/43 at runtime; publish vendor topics |
| System gateway HTTP/WS | `jcheng-system` | Read state/safety/contract; acquire/renew/release a lease; request stop (M2) | Submit motion outside the gateway/arbiter; mint a lease; clear a latch |
| Privileged motion plane, domain 41 | `jcheng-system` | Nothing | Publish, subscribe or proxy commands |
| Simulation plant, domain 43 | `jcheng-simulation` | Nothing at runtime | Publish `/sim/*` commands from the teleop process; treat simulation truth as hardware |
| Dataset and capture storage | Operator data root, outside git | Write immutable capture packages | Commit data, weights, recordings or personal data |

The capability manifest schema fixes `hardware_access: none` and restricts
runtime domains to 42. A device-owning adapter is therefore not admissible in
this repository; the operator-side process owns the device and the teleop
repository owns only the sample contract.

**"Gateway Adapter" means the system boundary, not only HTTP.** Lease, state
and stop are HTTP/WS; the canonical high-rate intent is the approved
`TeleopCommand` DDS stream consumed by the system-side intake. The test-only
HTTP step fallback uses `/v1/motion/execute` and is not the canonical
streaming transport. Neither path bypasses the lease, arbiter or safety
supervisor.

## 3. Modules

| Module | Responsibility | Inputs | Outputs | Lifecycle | Depends on |
|---|---|---|---|---|---|
| **Input Adapter** | Turn a normalized source into ordered `InputSample` values; detect silence and focus loss | Virtual script, keyboard events, JSONL, gamepad frames, future leader/studio frames | `InputSample` stream | `CLOSED → OPENING → READY → STREAMING → STALE → CLOSED/FAULT` | Clock, sample schema |
| **Teleop Core** | Own the control loop, session state, mode selection and event fan-out | Samples, profile, gateway state | `ActionIntent`, session events | `BOOT → SELFTEST → IDLE → READY → ACTIVE → STOPPING → FAULT/PREEMPTED` | Input, profile, safety, gateway port |
| **Robot Profile** | Resolve one canonical robot description plus a teleop binding; validate joint order, signs, units and modes | Profile document, binding, gateway `profile_hash` | Immutable `ResolvedProfile` | Loaded once per session; mismatch fails closed | `jcheng-interfaces` schema; system/simulation profile as deployment input |
| **Action Mapper** | Convert conditioned input into a typed `ActionIntent`; enforce units, frames, per-axis limits and rate | `ConditionedSample`, profile | `JointPositionIntent`, `JointVelocityIntent`, reserved `CartesianTwistIntent` | Stateless per tick; mode fixed per armed session | Profile, conditioning |
| **Safety Guard** | Local deadman, watchdog, limits, mode-change protection, fault latch and stop request | `ActionIntent`, session state, timestamps | Bounded intent, `SafetyEvent`, stop decision | Coupled to core state machine | Clock, profile, policy |
| **Gateway Adapter** | Submit intent/lease/stop through the system boundary; parse strict responses | Intent, lease id, gateway config | Wire command, `GatewayResult`, canonical errors | `DISCONNECTED → ADMITTED → LEASED → ACTIVE → STOPPING` | System HTTP/WS or DDS intake contract |
| **Episode Recorder** | Append observations, raw input, action intent, wire command, state, events, task and provenance to a capture package | Taps from core/gateway, measured state, clock | Immutable `jcheng.teleop.capture.v1` package | `IDLE → OPEN → RECORDING → FINALIZING → SEALED/FAULT` | Storage outside git, clock, provenance |
| **Replay Engine** | Re-run a capture through the same core with a fake clock; compare and flag anomalies | Capture, profile, mode | Replay report, anomaly list, benchmark JSONL | Offline one-shot | Core, profile, no gateway |
| **Dataset Adapter** | Convert capture packages into the learning-owned `jcheng.dataset.v1` and LeRobot v3.0 exports | Sealed capture, learning contract | Dataset package, quality report | Offline, idempotent by capture hash | `jcheng-learning` contract/writer; no runtime dependency in the core |

The modules are logical boundaries, not necessarily packages. M1 keeps them as
ROS-free Python modules; M2 adds a thin ROS node wrapper around the same core.

## 4. Core data flow

```text
raw source
  └─ InputSample(seq, t_source_ns, mode, positions/velocities/twist,
                 deadman, source_id, calibration_id)
       └─ conditioning: validate → deadzone/hysteresis → scale once →
                        per-axis bound → rate limit → ordering
            └─ ActionIntent(mode, values, frame, profile_id, profile_hash)
                 └─ Safety Guard: deadman, watchdog, mode, limits, fault latch
                      └─ Gateway Adapter: lease check + wire command
                           └─ system gateway/arbiter/safety (external)
                                └─ result: COMPLETED / REJECTED / ABORTED /
                                           TIMEOUT / UNKNOWN
```

Recording taps each stage without changing it:

```text
input.jsonl   action.jsonl   command.jsonl   observation.jsonl   events.jsonl
                              └─ joined by tick_id and monotonic time
```

`command.jsonl` records what was sent; `observation.jsonl` records what was
measured or simulated, with `truth` and `verification` explicit. `/joint_states`
is a command cache and is never used as measured pose truth.

## 5. Session and process lifecycle

```text
process start
  → load config and teleop binding
  → resolve canonical robot profile (hash check)
  → open input source (no device in this repo)
  → admit gateway (contract hash + profile hash + health)
  → SELFTEST (schema, units, profile, clock, storage)
  → IDLE (no lease)
  → READY (lease valid, state fresh, deadman released)
  → ACTIVE (fresh enable edge; commands emitted)
  → STOPPING (release/timeout/fault/preemption; one mode-specific stop intent)
  → IDLE or FAULT/PREEMPTED (explicit reset and fresh enable edge)
  → release lease, seal capture, close input
```

The process does not acquire a lease by itself during boot. The operator
authorizes the session and the lease is acquired through the system boundary:
by the operator console (`external`, the hardware default) or by teleop on the
operator's behalf with an operator identity (`managed`, used by the mock).
The teleop process may renew the lease while the session is active; it never
re-acquires after loss or preemption.

## 6. Deployment topologies

### 6.1 M1 — offline core (no ROS)

```text
virtual/keyboard/JSONL → core → in-process mock gateway → assertions
```

No DDS, no network, no device. Used for deterministic tests and the M1 CLI.

### 6.2 M2 — system mock and simulation

```text
operator adapter → teleop core → gateway adapter
                                   │ HTTP /v1 (mock)          [test-only step path]
                                   │ or DDS TeleopCommand      [canonical, needs system intake]
                                   ▼
                            jcheng-system mock
                                   │
                                   ▼
                    mock hardware or simulation bridge
                                   │
                                   ▼
                    jcheng-simulation domain 43 (test-owned)
```

The canonical path requires a system-side `TeleopIntake` and a streaming servo
session in the arbiter. The current system has neither; the HTTP step path is
a bounded, test-only fallback that uses the existing `POST /v1/motion/execute`
with multi-joint `JOINT_STEP`/`pose` requests at ≤10 Hz. It is not used for
hardware and is not reported as completion of the canonical path.

### 6.3 M6 — supervised hardware

```text
leader arm / pendant (operator side)
        │ normalized absolute positions + enable
        ▼
teleop process (operator laptop) ── domain 42 intent ──► system TeleopIntake
                                                              │
                                                              ▼
                                                   privileged plane domain 41
                                                              │
                                                              ▼
                                                   vendor executor domain 0
```

This topology is **blocked today**: the vendor executor accepts one
`JOINT_STEP` for one joint at about 5 commands/s with a 0.4 s settle, and the
system has no streaming servo session. A 5-joint 50 Hz leader-follower loop
cannot be built from the existing path without a new privileged-plane design
and safety review.

### 6.4 M5 — studio

Studio runs on the operator workstation and uses gateway HTTP/WS only. It may
display teleop status and send a stop request through the system boundary; it
does not publish intent, join DDS or open the input device. A browser gamepad,
if used, is an operator-side input source behind the same sample contract, not
a studio motion API.

## 7. Timing and control rates

| Stage | Target | Notes |
|---|---|---|
| Input sampling | 50–100 Hz | Device-dependent; the adapter timestamps at the source |
| Core tick / publish | 50 Hz (20 ms) | Configurable 20–100 Hz; fixed period, no burst catch-up |
| System intake | 20 Hz proposed | The arbiter samples the latest intent; no per-sample action call |
| Gateway HTTP fallback | ≤10 Hz | Test-only; gateway and arbiter both cap at 20/s |
| Deadman / input timeout | 300 ms proposed | Schema maximum is 500 ms; the manifest and teleop use 300 ms. 300 ms is the input-timeout threshold, not an end-to-end stop guarantee |
| Lease TTL / renewal | 1 s / 10 Hz proposed | Must be reconciled with the system's 100 ms–300 s TTL |
| Stop budget | Split: detection + transport + intake + actuation | Deadman release emits within one tick; input timeout adds 300 ms detection. Report each part; do not claim one 300 ms end-to-end number. Not an e-stop claim |

The 200 ms cross-host stamp window in earlier design notes is **withdrawn**.
The platform has no PTP guarantee. Liveness and safety use the operator host
monotonic arrival time, `seq` and the deadman; `header.stamp` is for latency
and provenance, and a skew check is enabled only when a measured sync bound
exists. The current system has no command timestamp or teleop window; it only
checks state freshness at 0.5 s. The system-side intake must enforce its own
command window.

## 8. Robot profiles and multi-robot compatibility

One core, one profile resolver, no per-robot forks.

- The canonical robot description remains owned by the ecosystem: the system
  `profile.yaml` for the deployed ArmPi, the simulation `robots/<id>/robot.yaml`
  for simulation, and a future `robot-profile.v2` for CAN arms such as PiPER X.
  The environment selects the canonical source: **hardware → system profile;
  simulation → simulation catalog**. The session records `profile_source` and
  the hash. If both sources are present, the resolver cross-checks joint
  names/order/limits and fails closed on a mismatch; there is no silent
  precedence.
- `jcheng-teleop` adds only a **teleop binding**: input channel to joint index,
  sign, offset/scale, deadzone, per-mode enablement, gripper mapping and
  mode-switch policy. It must not copy limits, joint order or servo IDs.
- The resolver validates joint count, names, order, signs, units and the
  gateway `profile_hash`; any mismatch refuses the session.
- A 2-DoF Gate-2 arm, a 5-DoF ArmPi and a 6-DoF PiPER X use the same code with
  different profiles. Bimanual and mobile manipulation are profile extensions,
  not new cores.
- `robot-profile.v1` is bus-servo specific (servo IDs, pulse arrays, mandatory
  gripper/workspace/base) and cannot express a CAN arm. The PiPER X proposal is
  currently untracked; M6 depends on a v2 schema or an approved overlay.

## 9. Action semantics

| Mode | Internal intent | Units / frame | Wire status |
|---|---|---|---|
| `JOINT_VELOCITY` | Per-joint velocity | rad/s, profile joint order | `TeleopCommand` v0.1; can be used with the system after intake |
| `JOINT_POSITION` | Per-joint absolute target | rad for revolute joints; profile order | Not in `TeleopCommand` v0.1; proposed for v0.2 |
| `CARTESIAN_TWIST` | Linear + angular velocity | m/s and rad/s in `base_link` | Reserved; no FK/IK in teleop, no vendor path |
| `CARTESIAN_POSE` | Absolute pose | m and quaternion in `base_link` | Reserved; not planned before M6 |

Gripper is an **orthogonal field**, not a mode: `gripper_normalized` (0 closed
.. 1 open) plus `gripper_valid`. The profile maps it to radians (ArmPi) or
metres (PiPER X); a blind open/close is never used as a stop.

Rules:

- The adapter normalizes raw device units to SI exactly once; the conversion
  is recorded with the adapter identity.
- Joint order and sign come from the resolved profile; no core code contains
  robot-specific names.
- A mode change requires the deadman to be released, a neutral state and a new
  enable edge. A stale Cartesian target can never be replayed as joint motion.
- Cartesian intent is not solved in teleop. If the system cannot accept a
  twist or pose, the mode is refused; teleop does not add IK or a vendor path.

## 10. Failure containment

| Failure | Containment |
|---|---|
| Input silence, focus loss, adapter crash | Watchdog stops within one tick; one mode-specific stop intent; fault latch; no auto-resume |
| Sequence rollback, duplicate, non-monotonic stamp | Reject the sample; count the event; no reorder or repair |
| Non-finite value | Reject immediately; latch after the configured repeat bound |
| Lease loss, expiry, preemption | Stop emitting; session abort (release lease; no system latch); no re-acquisition; explicit system stop only if the outcome is unknown |
| Gateway unavailable or ambiguous | Stop; mark outcome unknown; no retry of motion |
| Profile/hash mismatch | Refuse the session before any command |
| Recorder backpressure or disk failure | Stop path is independent; required-recording session fails closed |
| Simulation/real confusion | Environment class is explicit; teleop never connects to a real gateway by default; replay has no gateway port |
| Internal exception | Stop publishing; latch; preserve the last evidence |

## 11. Architecture decisions (proposed)

The table is the M0 decision log. Accepted decisions become individual ADR
files under `docs/adr/` when M1 starts; proposed decisions stay in this table
until the owning repository approves them.

| ID | Decision | Rationale | Status |
|---|---|---|---|
| ADR-001 | The only motion path is lease-gated intent through the system boundary; teleop never calls `ExecuteMotion` or a hardware API | Preserves the single motion authority and the stop latch | Accepted for M0 |
| ADR-002 | Operator input devices stay outside the repository; teleop consumes a normalized sample contract | `capability-manifest.v1` fixes `hardware_access: none`; avoids device fragmentation | Accepted for M0 |
| ADR-003 | One core plus a teleop binding; profiles reference canonical descriptions and never duplicate limits | Multi-robot without forks; profile mismatch is detectable | Accepted for M0 |
| ADR-004 | Joint-space first; Cartesian is a pass-through intent, never local IK | The system has no Cartesian execution path and teleop must not become a kinematics authority | Accepted for M0 |
| ADR-005 | Capture is teleop-owned; the dataset contract and LeRobot export are learning-owned | Avoids a second dataset schema and duplicated training pipeline | Proposed; depends on learning contract freeze |
| ADR-006 | M2 canonical transport is a system-side intake; a test-only HTTP step adapter is not M2 completion | The reserved `TeleopCommand` has no consumer; a per-sample HTTP loop cannot meet the rate/latency budget | Proposed; system review required |
| ADR-007 | No heavy runtime dependency in the core; ROS only in the thin M2 wrapper | Determinism, testability on the host and a small supply chain | Accepted for M0 |
| ADR-008 | The operator deadman is not a safety function; the platform has no e-stop | The stop latch is a software stop, not a certified safety device | Accepted for M0 |

## 12. Non-goals

- Owning or opening the operator input device.
- Publishing `/cmd_vel`, base intent or vendor topics.
- Rebuilding motion planning, perception, the system safety policy, the
  simulation catalog or the benchmark harness.
- Remote internet control, cross-network real-time teleoperation or unattended
  motion.
- Acting as an e-stop or a safety-rated device.
- Any hardware claim without a separately authorized, supervised L5 session.

## 13. Related

- [Teleop core](TELEOP_CORE.md)
- [Safety model](SAFETY_MODEL.md)
- [Data collection](DATA_COLLECTION.md)
- [Integration contract](INTEGRATION_CONTRACT.md)
- [Dependency review](DEPENDENCY_REVIEW.md)
- [M1 plan](M1_PLAN.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-simulation`](https://github.com/JCHENG-Robotics/jcheng-simulation)
- [`.github` taxonomy](https://github.com/JCHENG-Robotics/.github/blob/main/docs/repo-taxonomy.md)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
