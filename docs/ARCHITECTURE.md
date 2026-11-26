# Architecture — jcheng-teleop

> Status: **Experimental** as of 2026-11-26. Version 0.1.0.
> v0.1.0 is documentation and admission only: no input adapter, no runtime
> node and no device access. The input plane is planned for M1 and the intent
> plane for M2.

## 1. Position in the ecosystem

`jcheng-teleop` is an L3 capability. It sits beside `jcheng-mobile`,
`jcheng-perception` and `jcheng-learning`, below the system layer in the
dependency direction:

```text
operator-side adapter (outside this repository)
        │  input samples (documented line protocol)
        ▼
  input plane    deadzone · scaling · limits · seq/stamp      (M1, ROS-free)
        │
        ▼
  intent plane   TeleopCommand stream, lease-gated, deadman  (M2, domain 42)
        │
        ▼
  jcheng-system  arbiter (priority 40) -> safety -> ExecuteMotion
```

Rules that come from the ecosystem and are not negotiable here:

- The system layer is the **only** origin of motion. This repository never
  calls `ExecuteMotion`, never publishes `/cmd_vel` and never writes a servo or
  motor device.
- Capabilities publish **intent**. The system layer decides whether intent
  becomes motion. The arbiter samples the teleoperation stream on a fixed
  period and converts it into the same internal intent path used by every
  other source; it does not forward the stream as a hardware command.
- The contract already exists: `TeleopCommand.msg` is defined and reserved in
  `jcheng-interfaces` v0.1.0. Enabling the stream requires a contract-first PR
  and does not change the other messages.
- Cross-repository contracts live only in `jcheng-interfaces`. This repository
  does not invent a topic or service that another repository consumes without
  adding the contract there first.
- `hardware_access: none` in `capability.yaml`. No robot device is opened. The
  physical operator input adapter is also outside the repository: a capability
  manifest cannot express device access, so a device-owning adapter would need
  an explicit boundary review before adoption.
- Base chassis intent (`/cmd_vel`) belongs to `jcheng-mobile`. Teleoperation
  publishes arm intent only; it does not become a second base-intent source.
- `/joint_states` from the vendor stack is a **command cache**, not a
  measurement. Teleoperation must never treat it as pose truth.

## 2. Input plane (M1, ROS-free)

The input plane turns operator samples into a bounded, ordered and
deadman-guarded stream. It is a pure-Python core so it can be tested without
ROS, without a device and without a robot:

1. an operator-side adapter samples the physical device and emits input
   samples in a documented format; the adapter is not part of this repository;
2. the core applies the deadzone, scaling, per-axis bounds, rate limit and
   `seq`/`stamp` rules from [INPUT.md](INPUT.md);
3. the core owns the deadman state machine and refuses to emit after a gap,
   a lease loss or a mode change until a fresh enable edge arrives.

The core does not open a device, does not join a DDS domain and does not
publish. The exact sample format is proposed in [INPUT.md](INPUT.md) and is
frozen when M1 accepts it.

## 3. Intent plane (M2, planned)

The intent node will be a thin ROS 2 Humble wrapper around the ROS-free core.
It will:

- subscribe to robot, safety and lease state owned by the system layer;
- publish `TeleopCommand` on the planned `/jcheng/intent/teleop` topic on
  domain 42;
- hold no lease of its own: the operator's lease is acquired through the
  system layer, and the node only presents it;
- command no hardware and publish no other topic.

Topic and service names are **not** claimed in v0.1.0. They enter
`capability.yaml` and this document in the same contract-first PR that enables
the reserved stream. The manifest then moves from `safety.class: offline` to
`motion_source` with explicit scopes, a bounded rate and a deadman.

`TeleopCommand.msg` v0.1.0 carries arm joint velocity or Cartesian velocity and
a deadman flag; it has no gripper field. Gripper teleoperation is therefore
not expressible in the current contract and is not claimed. Adding it is a
contract decision, not a repository-local field.

## 4. System plane (arbiter and safety)

The system layer applies, independently of this repository:

| Rule | Consequence for teleoperation |
|---|---|
| Priority 40 | A field-operator lease (100) or an application task (60) preempts teleoperation; teleoperation preempts learning (20) and diagnostics (10) |
| Preemption audit | The preempted stream receives `LEASE_PREEMPTED`; in-flight motion returns `ABORTED`; there is no silent switch |
| Lease scope | The lease must cover every commanded axis; an out-of-scope axis is rejected, not ignored |
| Deadman | The interval between commands above `deadman_ms` (300 ms planned) stops motion immediately |
| Replay rejection | `seq` must increase strictly; `stamp` outside the 200 ms window is rejected |
| Velocity profile | The system clips to the robot profile and returns `VELOCITY_LIMIT` with a counter; it does not truncate silently |
| Stop latch | A timeout or unknown outcome latches; teleoperation cannot clear it |

The node's obligation is to stop emitting on lease loss or input staleness and
to report the reason. The system's obligation is the actual stop.

## 5. Invariants

| Invariant | Enforcement |
|---|---|
| No device access, including operator input devices | `capability.yaml`; `tests/test_no_hardware.py` |
| No motion command or motion service call | static scan; review of the M2 contract |
| No fabricated state, TF or measurement | review; intent is labelled as intent |
| No recordings or model weights in git | `scripts/check_repo_gate.sh`; `.gitignore` |
| No vendor code copied | review; differences are recorded as documents |
| Fail closed | no intent on stale input, missing lease, invalid mode or internal error |
| Domain 42 only at M2, one RMW | deployment review; the repository ships no DDS configuration |
| No secrets in the tree | gate secret scan; operator storage only |

## 6. Failure semantics

| Condition | Required behavior |
|---|---|
| Input stream stale beyond `deadman_ms` | emit `deadman: false` and zero velocity immediately; require a fresh enable edge |
| No valid lease, or lease revoked | emit nothing; the system stops motion within its bound |
| `seq` rollback or duplicate | reject the sample; do not reorder or repair |
| `stamp` outside the 200 ms window | reject the sample; do not rebase silently |
| Requested velocity above the profile | bounded and counted; never silently truncated without a limit event |
| Internal error or exception | stop publishing; fail closed |
| Invalid mode or missing calibration for Cartesian intent | emit no Cartesian intent |
| Preempted by a higher-priority lease | stop emitting; report `LEASE_PREEMPTED` |

An operator deadman is **not** a safety function. The platform has no e-stop,
brake, encoder or self-collision model; the system layer's stop latch is a
software stop, not an e-stop.

## 7. Non-goals

- Owning or opening the operator input device; adapters are operator-side.
- Publishing `/cmd_vel`, base intent or any vendor topic.
- Rebuilding motion planning, perception or the system layer's safety policy.
- Remote internet control or cross-network real-time teleoperation.
- Acting as an e-stop or a safety-rated device.
- Any claim of hardware validation without a separate, supervised L5 session.

## 8. Related

- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces) — `TeleopCommand.msg` and the contract hash.
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system) — lease, arbitration, safety and the only motion origin.
- [`jcheng-mobile`](https://github.com/JCHENG-Robotics/jcheng-mobile) — base intent owner.
- [`INTEGRATION.md`](INTEGRATION.md) — admission, lease and failure semantics.
- [`INPUT.md`](INPUT.md) — input samples, conditioning and deadman rules.
- [README](../README.md) / [ROADMAP](../ROADMAP.md) / [ACCEPTANCE](../ACCEPTANCE.md).
