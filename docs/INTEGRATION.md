# Integration — jcheng-teleop

> Status: **Experimental** as of 2026-11-26. v0.1.0 has no runtime surface:
> no node is started, no intent is published and no lease is acquired.
> The M2 contract below is planned, not implemented.

## 1. Discovery and admission

The system reads `capability.yaml` and checks the admission fields. For
v0.1.0 it finds:

| Field | Value | Meaning |
|---|---|---|
| `name` | `jcheng-teleop` | capability identity |
| `version` | `0.1.0` | must match `VERSION` |
| `contract.interfaces` | `>=0.1,<0.2` | pinned contract range |
| `contract.contract_hash` | `sha256:0b8d72…24b42` | must match the interfaces manifest |
| `safety.class` | `offline` | no intent source yet |
| `safety.scopes` | `[]` | no motion scope |
| `safety.requires_lease` | `true` | required by the schema; vacuous while there is no runtime |
| `hardware_access` | `none` | hard boundary |
| `runtime` | empty | no domain, no topics |

Because the runtime surface is empty, admission means "no runtime object to
discover". A future M2 adds the node, the topics and a contract change in the
same PR. Until then, the system must not assume a teleoperation node exists.

## 2. Inputs owned by other layers

| Input | Owner | Used at | Note |
|---|---|---|---|
| Operator input samples | operator-side adapter (outside this repository) | M1 | never a device owned here |
| Robot, safety and lease state | system | M2 | read-only context; the node never writes it |
| Perception targets | perception | not required | advisory only; teleoperation does not wait for perception |
| Calibration identifiers | system / perception | M2 | required for Cartesian intent |

## 3. Planned M2 intent surface

The contract exists but the stream is reserved. `TeleopCommand.msg` is defined
in `jcheng-interfaces` v0.1.0 and carries `header`, `seq`, `lease_id`,
`source`, `contract`, `mode`, `joint_velocity_rad_s`, `cartesian_velocity` and
`deadman`. The planned topic is `/jcheng/intent/teleop` on domain 42. Neither
the topic nor a rate is claimed in v0.1.0.

Rules from the ecosystem design record:

- the stream is accepted only while the node holds a `motion_source` lease;
- the lease scope must cover every commanded axis;
- `seq` is strictly increasing and `header.stamp` must be inside the 200 ms
  window;
- a gap above `deadman_ms` stops motion immediately;
- the arbiter samples the stream on a fixed period (recommended 20–50 Hz) and
  converts it to the same internal intent path; it never publishes a hardware
  command;
- the robot profile clips velocity and reports `VELOCITY_LIMIT` with a counter
  instead of truncating silently.

Contract-first checklist for M2:

1. Confirm or extend the reserved teleoperation contract in
   `jcheng-interfaces`; regenerate the manifest and bump the contract hash if
   the message or its semantics change.
2. Update `capability.yaml` to `safety.class: motion_source` with explicit
   scopes, `max_rate_hz`, `deadman_ms` and a non-empty `runtime` (domain 42,
   publishes `/jcheng/intent/teleop`, subscribes the state and lease streams).
3. Update this document, [ARCHITECTURE.md](ARCHITECTURE.md) and
   [INPUT.md](INPUT.md) in the same PR.
4. Prove the mock path (L2/L3): intent is rejected without a lease, dropped on
   stale input, rejected on `seq` rollback or stale `stamp`, and stopped on
   preemption and deadman expiry.
5. Only then request a supervised hardware session (L5), separately
   authorized.

What the system layer must do with teleoperation intent:

- treat it as a proposal, never as a trajectory or a servo command;
- apply the lease, deadman, joint limits and the stop latch;
- reject intent produced from stale, out-of-window or out-of-scope input;
- log the lease, source and contract hash that produced the intent;
- never treat an operator deadman as a safety function.

## 4. Lease, priority and preemption

| Priority | Subject | Preemption |
|---|---|---|
| 100 | field operator | preempts every lease; motion stops within the system's bound after revocation |
| 60 | application task | preempts 40/20/10 |
| 40 | teleoperation | preempts 20/10 |
| 20 | learning / automatic policy | cannot preempt a higher priority |
| 10 | diagnostics / calibration | only in `DISARMED` with no other lease |

- A preemption produces an audit event. The teleoperation stream receives
  `LEASE_PREEMPTED`; in-flight motion returns `ABORTED`; there is no silent
  switch.
- A revoked or expired lease stops the node from emitting. It does not acquire
  a replacement lease on its own.
- The node holds no lease of its own; the operator acquires it through the
  system layer.

## 5. Failure semantics

| Condition | Required behavior |
|---|---|
| No valid lease | emit nothing; the system rejects intent without a lease |
| Lease revoked, expired or preempted | stop emitting immediately; report the reason |
| Input stale beyond `deadman_ms` | emit `deadman: false` with zero velocity; require a fresh enable edge |
| `seq` rollback or duplicate | reject the sample; never reorder or repair |
| `stamp` outside the 200 ms window | reject the sample; never rebase silently |
| Requested velocity above the profile | bounded and counted; the system returns `VELOCITY_LIMIT` |
| Invalid mode or missing calibration | emit no intent that depends on them |
| Internal error, exception or failed load | stop publishing; fail closed |
| Unknown outcome after an in-flight command | the system latches; teleoperation cannot clear it |

## 6. Security and operations

- No network listener, no gateway token and no SSH material in this repository
  or its runtime node.
- No device is opened, here or at M2. The operator adapter is outside the
  repository.
- The node joins only domain 42 at M2, with the system's RMW. It ships no DDS
  configuration of its own.
- Startup, restart and stop are the system layer's decision; this repository
  provides no systemd unit for the robot.
- Teleoperation never runs unattended. An operator is present for every
  session, and every session is separately authorized.
- No remote internet control and no cross-network real-time teleoperation.

## 7. Verification

| Stage | Evidence |
|---|---|
| v0.1.0 admission | `python3 -m pytest -q tests`; `bash scripts/check_repo_gate.sh` |
| M1 intent core | deterministic unit tests for conditioning and the deadman state machine |
| M2 mock integration | rejection, stale-input, ordering, preemption and deadman scenarios |
| M3 hardware | separately authorized L5 session with system limits and the stop latch active |

No hardware claim is valid before M3. Synthetic or mock results are never
reported as hardware validation.

## 8. Related

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — input, intent and system planes.
- [`INPUT.md`](INPUT.md) — input samples, conditioning and deadman rules.
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces) — `TeleopCommand.msg` and the contract hash.
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system) — gateway, lease, arbiter and safety.
- [README](../README.md) / [ROADMAP](../ROADMAP.md) / [ACCEPTANCE](../ACCEPTANCE.md).
