# Proposal — system teleoperation intake and streaming session

> Status: **Proposal only**, 2026-11-26. No `jcheng-system` file, interface,
> gateway route or safety behavior is changed by this document. This is a
> cross-repository design proposal for the system owner and safety review.

## 1. Context

`jcheng-teleop` is an L3 capability. Its contract says the reserved
`TeleopCommand` stream is "consumed by the motion arbiter only". The M0 audit
found that `jcheng-system` has **no teleop consumer**:

- no `TeleopCommand` subscription or `/jcheng/intent/teleop` topic;
- no deadman, `seq`, command-timestamp or velocity-clipping enforcement;
- `MotionArbiter` accepts one discrete motion at a time and caps at 20
  commands/s/source;
- the gateway is a discrete HTTP surface with a 20 request/s limit;
- the vendor executor accepts exactly one-joint `JOINT_STEP` at about 5
  commands/s with a 0.4 s settle and rejects `POSE`, `JOINT_TRAJECTORY`,
  `HOME` and `BASE_PULSE`;
- leases are not revoked on a safety latch or bus-unknown;
- preemption surfaces as `LEASE_EXPIRED`, not `LEASE_PREEMPTED`;
- the capability plane (domain 42) cannot see vendor domain-0 telemetry.

Publishing the reserved stream without this work would be inert. Executing one
`ExecuteMotion` per 50 Hz sample is not viable and would turn a stream into a
queue of discrete motions.

## 2. Decision requested

Add a **system-side teleoperation intake** that samples `TeleopCommand` on
domain 42 and runs a long-lived streaming session through the existing lease,
safety, limit and evidence path. The arbiter remains the only motion entry; the
intake does not bypass it.

The work splits into:

- **S-M2 (mock/simulation):** intake, streaming session, mock backend,
  simulation bridge, tests. No hardware.
- **S-M6 (hardware):** a privileged-plane multi-joint streaming executor or a
  vendor bridge capable of bounded multi-joint updates at the teleop rate.
  Supervised hardware only.

## 3. Proposed components

```text
domain 42
  TeleopCommand (best effort, depth 1)
        │
        ▼
  TeleopIntake (new L2 node/process)
    ├─ contract/capability admission
    ├─ lease/scope/profile checks
    ├─ seq/stamp/deadman/mode/rate checks
    └─ TeleopSession handle
        │
        ▼
  MotionArbiter (extended)
    ├─ one teleop session per arm/gripper scope
    ├─ latest-setpoint sampling at 20 Hz
    ├─ limits via SafetySupervisor + profile
    ├─ bounded multi-joint step / velocity to the hardware port
    └─ stop/latch/evidence
        │
        ▼
  mock hardware / simulation bridge / vendor executor
```

### 3.1 TeleopIntake

- Subscribes only `/jcheng/intent/teleop`; QoS best effort, depth 1, volatile.
- Admits the capability by contract hash and manifest/registration; a mismatch
  rejects the stream.
- Validates: `lease_id`, scope covering every commanded axis, `seq` strictly
  increasing, host-arrival liveness, `deadman`, mode/payload shape, joint
  count/order, finite values, `profile_hash`. `header.stamp` is recorded for
  latency/provenance; a clock-sync bound is enforced only when one has been
  measured.
- Rejects stale/duplicate/out-of-order samples with a canonical error and a
  counter; it does not repair or reorder.
- Samples the latest accepted setpoint at 20 Hz; it does not call
  `ExecuteMotion` per sample.
- Stops on deadman release, gap > 300 ms, lease loss, preemption, stop latch,
  invalid input, profile mismatch or internal error.
- Emits `TeleopState` (new message proposal) with session, seq, mode, lease,
  deadman, last sample, limit counters and stop reason.

### 3.2 Streaming session in the arbiter

- `begin_teleop(session, lease, profile)` opens one session in the arm/gripper
  scope; `update_teleop(setpoint)` replaces the latest target; `end_teleop()`
  stops and writes one terminal result.
- The session is the only active motion in its scope; a second session gets
  `MOTION_BUSY`/`LEASE_CONFLICT`, not a silent switch.
- The existing stop latch, safety validation, publisher guard and evidence
  path remain authoritative. The session does not create a second queue of
  motions.
- At 20 Hz, compute the bounded target from the latest setpoint and fresh
  measured state. The system, not teleop, applies limits and records
  `VELOCITY_LIMIT`/`JOINT_LIMIT` counters.
- The conversion law is fixed before implementation:
  `dt = clamp(now - last_tick, 1/max_rate, tick_period)`;
  `step_max = profile.max_velocity * dt` (or the profile step bound);
  velocity mode: `q_cmd = q_measured + clamp(v_cmd * dt, ±step_max)`;
  position mode: `q_cmd = q_measured + clamp(q_target - q_measured, ±step_max)`.
  Reject if measured state is older than a configured `state_age_max` (target
  100 ms). There is no integrator and no catch-up; saturation is counted.
  On stop, hold the last accepted target or measured position; never command
  an all-zero position.
- On any stop condition, hold the hardware path (or zero base), write
  `ABORTED` or `REJECTED`, and latch only for a system stop, not a session
  abort.

### 3.3 New kind/profile and messages

The current `JOINT_STEP`/`step` profile is one joint; `JOINT_STEP`/`pose` can
carry multiple joints in the mock but the vendor path rejects it. A dedicated
`TELEOP` kind/profile (or an approved equivalent) is needed to express a
multi-joint bounded step with teleop-specific validation.

Proposed interface additions (subject to `jcheng-interfaces` review):

- `TeleopState.msg`: session id, seq, mode, lease id, deadman, last sample
  stamp/age, limit counters, stop reason, active.
- Error codes: `TELEOP_INPUT_STALE`, `TELEOP_DEADMAN`, `TELEOP_SEQ`,
  `TELEOP_RATE`, `TELEOP_MODE_UNSUPPORTED`, `TELEOP_SESSION_CONFLICT`.
- `MotionCommand.kind`/`profile` allowlist extension only if the arbiter's
  internal command model is exposed; otherwise keep `TELEOP` internal and do
  not change the public motion contract.

## 4. Sequence

```text
teleop                      intake/arbiter                   hardware
  │ acquire lease (HTTP)          │                              │
  │──────────────────────────────►│                              │
  │ TeleopCommand seq=1 deadman=1 │                              │
  │──────────────────────────────►│ validate; begin session      │
  │                               │ 20 Hz bounded step ─────────►│
  │ TeleopCommand seq=2 ...       │                              │
  │──────────────────────────────►│ update latest target         │
  │                               │ 20 Hz bounded step ─────────►│
  │ deadman=0 or gap/lease loss   │                              │
  │──────────────────────────────►│ stop; hold/zero; terminal    │
  │◄──── TeleopState/stop result ─│                              │
```

## 5. Safety requirements

- The intake must not accept a stream without a lease whose scope covers every
  commanded axis.
- Domain 42 currently has no publisher authentication: `source` is
  self-declared and a lease id is bearer authority. The intake must bind the
  lease holder to a registered capability (or DDS Security must be enabled);
  until then domain 42 is a trusted, isolated bus with an explicit owner and no
  untrusted nodes.
- The deadman is enforced at the intake and independently by the system stop
  path; a lost stream is a stop, not a hold.
- The system stop latch, publisher guard and bus verification remain
  authoritative; teleop cannot clear a latch.
- A lease must become invalid immediately on a stop latch, disarm or
  bus-unknown (this is currently a documented gap).
- Preemption must be distinguishable from expiry (`LEASE_PREEMPTED` or an
  event); the victim must stop, not silently continue.
- A session must never produce two terminal results for one intent; the
  existing `_complete_once` discipline is the model.
- No auto-resume; a new session requires a fresh lease and a fresh enable edge.
- The intake must fail closed on an unknown mode, malformed payload, non-finite
  value, wrong joint count/order or profile mismatch.

## 6. Impact

| Repository | Change |
|---|---|
| `jcheng-system` | New intake node/package; arbiter streaming session; `TELEOP` kind/profile; error/lease fixes; sim bridge test path; tests |
| `jcheng-interfaces` | `TeleopState`, teleop error codes, `TeleopCommand` v0.2; new contract hash/tag |
| `jcheng-teleop` | DDS adapter and node; capability manifest moves to `motion_source`; M2 evidence |
| `jcheng-simulation` | Test bridge to `/sim/joint_command` or JTC; no runtime join to 42 |
| `jcheng-learning` | Dataset mapping for position/gripper and teleop provenance |
| `jcheng-studio` | Optional status/stop panel using `TeleopState` |

This is a large change. It must be split: S-M2 for mock/simulation first, then
S-M6 for hardware. S-M2 does not authorize hardware.

## 7. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| One `ExecuteMotion` per 50 Hz sample | 20/s gateway/arbiter limits, one-active motion, HTTP overhead and queueing; not a stream |
| Teleop calls the gateway directly at 10 Hz for hardware | Step latency, `MOTION_BUSY`, no continuous deadman; acceptable only as a test fallback |
| Teleop drives the simulation plant directly | Bypasses the system gateway/lease/arbiter and mixes capability with plant control |
| MoveIt Servo inside teleop | Duplicates motion control and kinematics in L3; bypasses the JCHENG authority model |
| A separate teleop motion service outside the arbiter | Creates a second motion origin and a second stop path |
| Reuse the one-joint vendor executor for 5 joints | It cannot stream; 5 joints at 50 Hz would exceed its 5 commands/s and 0.4 s settle |

## 8. Verification plan

S-M2 (mock/simulation):

- L2 intake tests: contract, capability, lease/scope, seq, stamp, deadman,
  mode, joint count/order, profile hash, finite values.
- L2/L3 fault injection: lease revoke, expiry, preemption, stop latch, busy,
  gateway loss, stale input, duplicate sequence.
- L3 simulation: 2-DoF Gate-2, 5-DoF ArmPi, 6-DoF PiPER X, sequentially; one
  plant at a time; truth label `simulated`.
- Stop latency and no-auto-resume evidence.

S-M6 (hardware):

- Separate supervised authorization per session.
- Bus-verified stop and tracking evidence; no e-stop claim.
- Vendor streaming executor characterized before any motion.

## 9. Open questions

- Is the intake a new package or part of `jcheng_motion`? A new package keeps
  the intake testable but adds a process; the owner must decide.
- Should the streaming session live in `MotionArbiter` or a sibling
  `TeleopArbiter` that shares the same safety/lease/evidence objects? The
  sibling avoids complicating the discrete path, but must not become a second
  motion origin.
- Is `TELEOP` a public `MotionCommand.kind`, or internal to the intake? Public
  keeps one vocabulary but expands the contract; internal keeps the interface
  smaller.
- How is `TeleopState` exposed: DDS topic, gateway WS, or both? Studio prefers
  HTTP/WS; the recorder prefers DDS/local.
- What is the exact stop confirmation field (R5), and can teleop claim
  `stop_confirmed`?
- How is the domain 0→41/42 telemetry bridge implemented, and does it add
  latency beyond the 300 ms deadman?
- Should the intake accept `CARTESIAN_TWIST` and reject it explicitly until
  FK/IK exists, or omit the mode?

## 10. Related

- [Integration contract](../INTEGRATION_CONTRACT.md)
- [Safety model](../SAFETY_MODEL.md)
- [Teleop core](../TELEOP_CORE.md)
- [TeleopCommand v0.2 proposal](TELEOP_COMMAND_V0.2.md)
- [`jcheng-system` safety](https://github.com/JCHENG-Robotics/jcheng-system/blob/main/docs/SAFETY.md)
- [`jcheng-system` execution model](https://github.com/JCHENG-Robotics/jcheng-system/blob/main/docs/EXECUTION-MODEL-REVISION.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
