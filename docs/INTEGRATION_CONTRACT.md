# Integration contract — jcheng-teleop

> Status: **Proposed** as of 2026-11-26. No interface, schema, gateway or
> system file is changed by this document. The contracts below are the current
> facts plus proposals; the proposals are not approvals.

## 1. Ecosystem audit summary (2026-11-26)

| Repository | Version / state | What exists | Teleop reuse | Gap or decision |
|---|---|---|---|---|
| `jcheng-interfaces` | 0.1.0, tag `33f1293` | 25 IDL files, JSON schemas, error registry, contract hash; `TeleopCommand` reserved | Contracts, hashes, error vocabulary | No position/gripper, no dataset/episode schema, no teleop error codes |
| `jcheng-system` | `0.3.0-dev0` | Gateway HTTP/WS, leases, discrete arbiter, safety, mock stack, vendor executor | Lease/arbiter/safety authority | No teleop consumer; no streaming session; vendor one-joint step; no domain bridge |
| `jcheng-simulation` | 0.1.0 Experimental | Multi-robot catalog, mock and Gazebo plants, `/sim/*`, domain 43, truth label | Robot profiles, plant for M2 | No system bridge, no testkit sim scenario, one plant per domain |
| `jcheng-learning` | `0.1.0` committed; working tree `0.2.0` with untracked `docs/m1/` and `src/` writer | Dataset contract proposal and an uncommitted writer; no merged runtime | Dataset contract, LeRobot export ownership | Contract/writer not merged or frozen; M1 action kind is absolute position only |
| `jcheng-studio` | 0.7.0 Experimental | React console, gateway `/v1` and `/v1/ws/state` client, session/auth UI | Operator UI, status presentation | No teleop panel or input code; M5 work |
| `jcheng-applications` | 0.1.0 Experimental | Offline recipe/plan/runner, read-only transport, M3 write path uncommitted | Gateway port/strict parser/no-retry patterns | Synchronous step runner is not a teleop transport |
| `jcheng-benchmark` | 0.1.0 Experimental | JSONL suite runner, metrics/thresholds, report schema | Offline scoring and report format | No replay/alignment; teleop exports JSONL |
| `jcheng-mobile` | Experimental | ICP/SLAM/Nav2, `/cmd_vel` base intent | M9 base intent owner | Teleop must not publish `/cmd_vel` |
| `jcheng-ops` | Deployed | Health probes, watchdogs, systemd | Operator-side health visibility | Never joins DDS; not a teleop component |
| `jcheng-research` | Private | Investigation protocol and reports | Prior-art/experiment discipline | No runtime dependency |

The audit did not modify any repository. The only writes are in
`jcheng-teleop`.

## 2. Contract matrix

| Peer | Version | Current fact | Teleop dependency |
|---|---|---|---|
| `jcheng-interfaces` | 0.1.0, tag `33f1293`, hash `sha256:0b8d72…24b42` | `TeleopCommand.msg` reserved; no dataset/episode schema; no teleop error codes | Read-only for M1; v0.2 proposal for position/gripper (M2/M6) |
| `jcheng-system` | `0.3.0-dev0` | Mock `TeleopIntake` + `/jcheng/intent/teleop` ROS subscriber on branch `feat/teleop-intake`; teleop ROS publisher in this repo; sim bridge/merge missing; vendor executor still single-joint step | M2 sim bridge/L3, merge, and M6 prerequisite |
| `jcheng-simulation` | 0.1.0 | Domain 43; mock `JointState` or Gazebo JTC; no system bridge | M2 test bridge |
| `jcheng-learning` | 0.1.0 committed; 0.2.0 only in the working tree | `jcheng.dataset.v1` and a writer are untracked; not merged or frozen | M3/M4 contract freeze and merge |
| `jcheng-studio` | 0.7.0 | Gateway `/v1` client and `/v1/ws/state`; no teleop UI | M5 status/stop surface |
| `jcheng-applications` | 0.1.0 | Gateway port/transport patterns; M3 write path uncommitted | Reuse patterns only |
| `jcheng-benchmark` | 0.1.0 | JSONL suite runner; no replay execution | M4 scoring |

The `capability.yaml` declares `system_api: ">=0.1,<0.2"` while the system
repository is `0.3.0-dev0`. This range has not been revalidated; M2 must
reconcile it before a runtime claim.

## 3. Current system reality

The M0 audit found no `TeleopCommand` subscriber in `jcheng-system`. A mock
`TeleopIntake` and a `/jcheng/intent/teleop` subscriber now exist on branch
`feat/teleop-intake`; they are not merged and the simulation bridge is absent.
The implemented discrete motion path is:

```text
HTTP POST /v1/motion/execute ─┐
ROS action /jcheng/motion/execute ─┴─► MotionArbiter (one active motion)
                                          ├─ LeaseManager
                                          ├─ SafetySupervisor
                                          └─ hardware bridge / vendor executor
```

Relevant facts:

- The gateway and arbiter rate-limit at **20 commands/s per source**.
- The arbiter accepts **one active motion**; a second command returns
  `MOTION_BUSY`.
- `MotionCommand` is discrete: `JOINT_TRAJECTORY`, `JOINT_STEP`, `POSE`,
  `HOME`, `BASE_PULSE`, `GRIPPER`.
- The vendor executor accepts only one-joint `JOINT_STEP` and `GRIPPER`; it
  waits for `duration + 0.4 s`, allows about 5 commands/s and rejects `POSE`,
  `JOINT_TRAJECTORY`, `HOME` and `BASE_PULSE`.
- There is no deadman enforcement, no `seq` validation, no command timestamp
  window and no velocity clipping with a counter in the system today.
- `deadman_required` is stored on the lease but not enforced.
- Preemption currently surfaces as `LEASE_EXPIRED`, not `LEASE_PREEMPTED`;
  lease events are not exposed over HTTP or ROS.
- A safety latch or bus-unknown does not revoke an active lease; the lease
  check can still return OK, while `safety.validate` rejects motion.
- The capability plane (domain 42) cannot see vendor domain-0 telemetry; the
  planned domain bridge is not implemented.
- There is no `GET /v1/leases`, no teleop state stream and no stop
  confirmation field.

These are not teleop bugs; they are system-side gaps that M2/M6 must resolve
or explicitly bound.

## 4. Current gateway surface

The mock gateway is the only implemented HTTP surface. It binds
`127.0.0.1:8766` by default, requires a bearer token (health is unauth), and
uses a shared token with no roles.

| Method/path | Use for teleop | Notes |
|---|---|---|
| `GET /v1/health` | Admission probe | Unauthenticated; includes contract and safety |
| `GET /v1/contract` | Contract/profile hash pin | `profile_hash` is the ArmPi profile hash |
| `GET /v1/state` | Read-only state | `truth`/`verification` are explicit |
| `GET /v1/safety` | Stop latch / armed state | Authoritative safety snapshot |
| `POST /v1/safety/arm` | Operator arms the system | Requires checklist hash, exact phrase, contract, profile hash |
| `POST /v1/safety/reset` | Operator clears a latch | Requires exact phrase and bus check on unknown |
| `POST /v1/leases` | Acquire the teleop lease | Scope `arm`, `gripper` or `full`; priority 40; TTL 100 ms–300 s |
| `POST /v1/leases/{id}/renew` | Renew | Teleop renews at TTL/3 |
| `DELETE /v1/leases/{id}` | Release | Idempotent from the client |
| `POST /v1/motion/validate` | Optional preflight | Diagnostic; execution revalidates |
| `POST /v1/motion/execute` | Test-only step fallback | Requires `Idempotency-Key`; returns 200 with `REJECTED` for validation failures |
| `POST /v1/motion/stop` | Stop request | Requires operator id; latches the system stop |
| `GET /v1/events` | Evidence page | Does not include lease events |
| `GET /v1/ws/state` | Read-only state/safety | 10 Hz hello/state/safety; no lease/intent write |

Lease acquisition is explicit: `managed` means teleop acquires/renews on the
operator's behalf with an operator identity in the holder string; `external`
means the operator console acquires and teleop only presents the lease.
Hardware defaults to `external`; the in-process mock may use `managed`. In
both cases the lease comes from the system, never from teleop itself.

Teleop never uses `/v1/motion/execute` in the canonical path. The test-only
fallback is described in §6.2.

## 5. Canonical target path

```text
operator adapter
   │ InputSample (local, versioned)
   ▼
teleop core ── ActionIntent ──► gateway adapter
                                   │
                                   │ TeleopCommand (domain 42, 50 Hz)
                                   ▼
                        system TeleopIntake (L2, new)
                          ├─ contract/lease/profile/seq/stamp/deadman checks
                          ├─ TeleopSession in the arbiter (streaming, one owner)
                          ├─ limits + safety supervisor
                          └─ 20 Hz bounded multi-joint step to the hardware port
                                   │
                                   ▼
                     mock hardware / simulation bridge / vendor executor
```

The system-side intake is the missing piece. `TeleopCommand.msg` says
"consumed by the motion arbiter only"; the arbiter does not consume it today.
A teleop-only publication would be inert.

### 5.1 Proposed stream

| Property | Proposal |
|---|---|
| Topic | `/jcheng/intent/teleop` |
| Domain | 42 only |
| Type | `jcheng_interfaces/msg/TeleopCommand` (v0.1 now, v0.2 for position/gripper) |
| QoS | Best effort, depth 1, volatile; the newest sample wins; a lost sample is a gap, not a queue |
| Rate | 50 Hz nominal; 20–100 Hz allowed; the intake samples the latest value at 20 Hz |
| Lease | `arm` + `gripper` or `full`, priority 40, exclusive, TTL 1 s, renewal 10 Hz |
| Deadman | `deadman=true` required while moving; release or gap > 300 ms stops |
| Stamp | `header.stamp` is the sample source time; use it for latency/provenance. Liveness uses host arrival monotonic time + `seq` + deadman; enforce a clock-sync bound only when one is measured |
| Sequence | `seq` strictly increasing per session; rollback/duplicate rejected |
| Profile | `expected_profile_hash` or an equivalent check; mismatch rejects |
| Stop | Mode-specific stop intent (zero velocity / hold position / hold gripper) with `deadman=false` once, then silence; session abort is non-latching; system stop is independent and latching |

### 5.2 Proposed intake behavior

1. Admit the capability by contract hash and `capability.yaml`; unknown or
   mismatch → reject.
2. Acquire/validate the lease; scope must cover every commanded axis; no
   silent scope widening.
3. Validate mode, payload shape, joint count/order, finite values, profile
   hash, seq, stamp and deadman.
4. Open one `TeleopSession` in the arbiter. While active, updates replace the
   previous target; they do not create a second motion. The session is the
   only active motion in the arm scope.
5. At 20 Hz, convert the latest intent into a bounded multi-joint step using
   fresh measured state and the profile limits. The system, not teleop,
   computes the applied step and records limit events. The law is fixed:
   `step_max = max_velocity * dt`; velocity mode
   `q_cmd = q_measured + clamp(v*dt, ±step_max)`; position mode
   `q_cmd = q_measured + clamp(q_target-q_measured, ±step_max)`. State older
   than `state_age_max` (target 100 ms) is rejected; there is no integrator,
   catch-up or all-zero position stop.
6. On deadman release, input gap, lease loss, preemption, stop latch, invalid
   sample or internal error: stop the session, apply the hold/zero path, emit
   one terminal result and latch where required.
7. Publish `TeleopState` (session, seq, mode, lease, deadman, last sample,
   limit counters, stop reason) for studio/recorder; this is a proposal, not
   an existing message.
8. Never auto-resume. A new session requires a fresh lease and a fresh enable
   edge.

### 5.3 Required system changes

- A `TeleopIntake` node/process on domain 42.
- A streaming `TeleopSession` mode in the arbiter, reusing lease, safety,
  limits and evidence; not a bypass around them.
- A multi-joint `TELEOP` kind/profile or an approved equivalent (the existing
  `JOINT_STEP`/`step` is one joint; the vendor path is one joint).
- Deadman, seq, arrival-liveness/sync-bound and clipping/counter semantics.
- A non-latching teleop session abort (deadman release, input timeout, lease
  loss, normal hand-back) distinct from the latching system stop.
- Publisher/capability binding on domain 42 (registration or DDS Security) so a
  self-declared `source` cannot reuse a lease; at minimum an explicit trusted-
  bus assumption with an owner.
- Preemption code/event correction (`LEASE_PREEMPTED`), or a documented
  decision to treat `LEASE_EXPIRED` as preemption.
- Lease invalidation on stop latch/bus unknown, per `docs/SAFETY.md`.
- A teleop state/event surface for studio and capture.
- A privileged-plane multi-joint streaming executor for real hardware; the
  current vendor executor is not sufficient.
- A domain 0→41/42 telemetry bridge or an HTTP read path for fresh measured
  state.

These changes belong to `jcheng-system` and require its own design, safety and
test review. They are proposed in
[docs/proposals/SYSTEM_TELEOP_INTAKE.md](proposals/SYSTEM_TELEOP_INTAKE.md).

## 6. Session sequence

### 6.1 Start

```text
Operator        Teleop        System gateway/arbiter
   │ authorize     │                    │
   │──────────────►│                    │
   │               │ GET /v1/health     │
   │               │───────────────────►│
   │               │ GET /v1/contract   │
   │               │───────────────────►│
   │               │ GET /v1/state      │
   │               │───────────────────►│
   │               │ GET /v1/safety     │
   │               │───────────────────►│
   │               │ POST /v1/leases    │
   │               │ priority 40, ttl 1s│
   │               │───────────────────►│
   │               │◄──── lease ────────│
   │               │ READY              │
   │ enable edge   │                    │
   │──────────────►│ ACTIVE             │
   │               │ TeleopCommand 50Hz │
   │               │───────────────────►│ intake/arbiter
```

### 6.2 Active

- Teleop renews at TTL/3; a failed renewal means the lease is lost.
- The intake checks the deadline on every sample; a gap > 300 ms is a stop.
- The system may preempt at any time; teleop stops on the next check/event.
- Every command/result is recorded with the session and profile hash.

### 6.3 Stop

```text
deadman release / input timeout / lease loss
   │
   ├─ teleop: STOPPING; one mode-specific stop intent + deadman=false; silence
   ├─ teleop: release lease (if still held); no system stop-latch call
   ├─ system intake: abort the teleop session without latching
   └─ evidence: reason, abort result, confirmation (or unknown)

explicit operator stop / observed safety fault / unknown outcome
   │
   ├─ teleop: one mode-specific stop intent + deadman=false
   ├─ teleop: POST /v1/motion/stop once
   ├─ system: hold/zero the hardware path; latch if required
   └─ evidence: stop result, confirmation (or unknown), reason
```

The **session abort** class must not latch the whole system; otherwise a 300 ms
network gap would force a reset/re-arm and encourage operators to bypass the
stop. The system today only exposes a latching `/v1/motion/stop`; a
non-latching teleop session abort is a required S-M2 change. Until it exists,
the test-only HTTP path must not pretend a normal deadman release is a system
stop, and it must not be used for hardware.

The stop is cooperative and independent: the system must stop on its own
deadman/lease/latch path even if teleop is wedged.

## 7. M2 paths

### 7.1 Canonical path

System `TeleopIntake` + arbiter `TeleopSession` + simulation bridge. This is
the only path that counts as M2 completion. It requires the system work in
§4.3.

### 7.2 Test-only HTTP step fallback

To exercise the core before the intake exists, a test adapter may submit
multi-joint `JOINT_STEP` with profile `pose` at ≤10 Hz through
`POST /v1/motion/execute`, holding an `arm`+`gripper` or `full` lease at
priority 40. It must:

- be enabled only by an explicit `--test-gateway` flag and a loopback URL;
- require `GET /v1/health` to return `capabilities` containing `"mock"`;
  refuse any gateway that does not identify as mock, even on loopback (an SSH
  tunnel to the Pi would otherwise pass a URL-only check);
- record `environment_class=mock` and the health capability list in every log;
- never be used with a real robot;
- wait for the terminal result before the next step; `MOTION_BUSY` means skip,
  not queue;
- send `GRIPPER` separately with the gripper scope;
- not call the latching `/v1/motion/stop` for a normal deadman release; it
  stops output and releases the lease, and reports that a non-latching abort
  is unavailable in the current system;
- label every report "test-only gateway step path, not streaming teleop".

It is a development harness, not a deployed capability and not M2 evidence.
The gateway/arbiter 20/s limit and the one-active motion rule make it
unsuitable for hardware.

### 7.3 Simulation bridge

`jcheng-simulation` exposes `/sim/joint_command` (mock, position setpoints) or
`/sim/<controller>/follow_joint_trajectory` (Gazebo). It does not consume
system intents. A test bridge must translate a system mock hardware port to
these surfaces:

```text
system mock hardware port → test bridge → /sim/joint_command (mock)
                                      → JTC action (Gazebo, domain 43)
```

The bridge is test infrastructure, owned by the system testkit or a joint
test package. Teleop never publishes `/sim/*`; simulation never joins 42/41/0.
One plant at a time; the catalog robots are tested sequentially. The mock
plant holds the last target after 500 ms (it does not stop), and Gazebo does
not enforce controller-level limits; the system/teleop guards remain
responsible.

## 8. Failure semantics

| Condition | Teleop behavior | System behavior required | Code |
|---|---|---|---|
| No lease | No intent; `IDLE`/`FAULT` | Reject intent | `NO_LEASE` |
| Lease expired | Stop; no auto-renew after loss; session abort | Abort the session without latching | `LEASE_EXPIRED` |
| Lease revoked | Stop; no auto re-acquire; session abort | Abort the session without latching | `LEASE_REVOKED` |
| Preempted | Stop; `PREEMPTED`; operator re-arms; session abort | Abort the session; emit preemption event | `LEASE_PREEMPTED` (code exists; system emission is the gap) |
| Input stale | One mode-specific stop intent + false; `STOPPING`; session abort | Abort the session without latching | `STATE_STALE`/local `INPUT_STALE` |
| Deadman release | One mode-specific stop intent + false; silence; session abort | Abort the session without latching | `DEADMAN_RELEASED` local |
| Seq rollback/duplicate | Reject sample; no reorder | Reject intent | local `SEQ_GAP`; proposed `TELEOP_SEQ` |
| Arrival stale / stamp outside a measured sync bound | Reject sample | Reject intent | local `STAMP_STALE`; proposed `TELEOP_STALE` |
| Profile mismatch | Refuse session | Reject intent | `PROFILE_HASH_MISMATCH` |
| Contract mismatch | Refuse session | Reject intent | `CONTRACT_HASH_MISMATCH` |
| Over-limit | Clamp + count; no silent truncation | Validate; `VELOCITY_LIMIT`/`JOINT_LIMIT` | canonical |
| Gateway unavailable | Stop; `UNKNOWN`; no retry | Hold/stop; evidence | `HARDWARE_UNAVAILABLE`/`TIMEOUT` |
| Motion outcome unknown | Stop; no retry | Latch; bus check before reset | `MOTION_OUTCOME_UNKNOWN` |
| Stop latch active | No intent; `FAULT` | Reject; reset by operator | `SAFETY_STOP_LATCHED` |
| Recorder failure | Stop if required; `FAULT` | No change | local `RECORDER_FAULT` |
| Cartesian unsupported | Refuse mode; no fallback | Reject kind/mode | `UNKNOWN_KIND`/`INVALID_COMMAND` |

## 9. Learning integration

`jcheng-learning` owns the dataset contract. Its current `jcheng.dataset.v1`
proposal is untracked and not frozen; its M1 action kind is
`joint_position_absolute`. Teleop's capture is intentionally separate:

```text
teleop capture (teleop-local, immutable)
        │  adapter (M4)
        ▼
jcheng.dataset.v1 writer/validator (learning-owned)
        │
        ▼
LeRobot v3.0 export / SmolVLA training (learning-owned)
```

Rules:

- Teleop does not implement a second dataset schema or a training pipeline.
- Teleop writing `jcheng.dataset.v1` across repositories requires an
  interfaces proposal and a new contract hash; until then, the converter runs
  in the learning repository or is explicitly labelled a local adapter.
- Velocity-only episodes are not silently converted to absolute-position
  actions. They are capture-only until the contract supports the action kind.
- Provenance is immutable; a derived dataset keeps the original environment
  and source class.

## 10. Studio integration

- Studio stays HTTP/WS only; it does not join DDS, open devices or publish
  intent.
- M5 needs a teleop status surface (session, lease, deadman, input age,
  profile/contract hash, capture state) and a stop control that reaches the
  system stop path.
- The browser never calls the gateway directly; studio's backend proxies with
  the token.
- A browser gamepad is an operator-side input source behind the sample
  contract; it is not a motion API.
- A UI session is not a lease; the panel must show the lease holder and
  priority, not a green "connected" state alone.

## 11. Benchmark integration

- `jcheng-benchmark` scores JSONL; it does not replay or align time.
- Teleop exports one row per evaluation sample with `sample_id`, optional
  `trial`, `measured_m`/`reference_m` for position error, precomputed scalars
  and `success`.
- Use `level: L4`, `data_source: recorded` only for genuine capture replay;
  mock/simulation exports use `mock`/`synthetic` and are never called
  hardware.
- Do not put ROS code or replay players under the benchmark tree; it rejects
  `rclpy`/`ros2` tokens.

## 12. Contract proposals

| ID | Proposal | Owner | Status |
|---|---|---|---|
| P-001 | `TeleopCommand` v0.2: joint position, gripper, session/episode, profile hash, source class, mode-conditional payload | `jcheng-interfaces` | Proposed; no file changed |
| P-002 | System teleop intake, streaming session, deadman/seq/stamp/clipping, `TeleopState` | `jcheng-system` (+ interfaces for codes/state) | Proposed; no file changed |
| P-003 | Robot profile v2 or an approved overlay for CAN/prismatic arms; teleop binding | `jcheng-interfaces` | Proposed; PiPER X v2 proposal is untracked |
| P-004 | Dataset/episode contract `jcheng.dataset.v1` and teleop producer rules | `jcheng-learning` → interfaces | Proposed; learning M1 package untracked |
| P-005 | Studio teleop status/stop surface | `jcheng-studio` + teleop local | Proposed; M5 |

Links:

- [TeleopCommand v0.2 proposal](proposals/TELEOP_COMMAND_V0.2.md)
- [System teleop intake proposal](proposals/SYSTEM_TELEOP_INTAKE.md)

## 13. Blockers

| ID | Blocker | Impact | Resolution |
|---|---|---|---|
| B0 | `.github` teleop admission is on an unmerged branch; `origin/main` still says "planned" | Governance admission not final | Merge the admission branch before M1 |
| B1 | System intake/ROS subscriber and teleop ROS publisher exist only on branches; simulation bridge and end-to-end L3 missing | M2 canonical path still incomplete | Merge both branches and implement the sim bridge/L3 evidence |
| B2 | Vendor executor is single-joint step at ~5/s | M6 hardware streaming impossible | New privileged servo/executor design |
| B3 | `TeleopCommand` lacks position/gripper/session/provenance | Leader-follower and dataset actions blocked | P-001 |
| B4 | `robot-profile.v1` cannot express CAN/prismatic arms; PiPER X proposal untracked | Multi-robot profile blocked | P-003 |
| B5 | No system-simulation bridge; no testkit sim scenario | M2 simulation/L3 blocked | SIM-M2 |
| B6 | Learning's `jcheng.dataset.v1` and writer are untracked in a 0.2.0 working tree, not merged/frozen | M3/M4 export blocked | P-004 + merge/freeze the learning contract |
| B7 | No measured state at teleop rate; `/joint_states` is a command cache | Capture truth and position mapping limited | Domain bridge or bus-read telemetry |
| B8 | Preemption returns `LEASE_EXPIRED`; lease events not exposed | Operator cannot distinguish preemption | System fix or documented mapping |
| B9 | No stop confirmation (`StopResult` has no field) | Cannot claim physical stop | R5 system work |
| B10 | License review open; no `LICENSE` | Third-party code adoption blocked | Ecosystem review |
| B11 | Capability `system_api` range (`>=0.1,<0.2`) does not match system `0.3.0-dev0` | Admission/contract handshake ambiguity | Reconcile at M2 |
| B12 | Real hardware has no e-stop/brake/encoder | Residual risk cannot be eliminated | Supervised, low-speed scope only |
| B13 | Domain 42 has no publisher authentication or DDS Security; `source` is self-declared and a lease id is bearer authority | A malicious/misconfigured L3 node could reuse a lease | Bind lease holder to a registered capability or add DDS Security; until then treat domain 42 as a trusted, isolated bus with an owner and no untrusted nodes |
| B14 | Learning's dataset `source_class` is dataset-level and currently forbids mixing; teleop M7 wants multiple source classes | Mixed-source export is not implementable as written | Split datasets per source_class or add per-episode provenance to learning's contract |
| B15 | Velocity-only episodes cannot satisfy learning's `joint_position_absolute` action kind | M4 LeRobot round-trip is untestable for velocity teleop | Use v0.2 position mode or add a velocity action kind; mark M4 partial until then |

## 14. Related

- [Architecture](ARCHITECTURE.md)
- [Teleop core](TELEOP_CORE.md)
- [Safety model](SAFETY_MODEL.md)
- [Data collection](DATA_COLLECTION.md)
- [Dependency review](DEPENDENCY_REVIEW.md)
- [M1 plan](M1_PLAN.md)
- [`jcheng-system` gateway](https://github.com/JCHENG-Robotics/jcheng-system/blob/main/ros2_ws/src/jcheng_system_core/jcheng_system_core/gateway.py)
- [`jcheng-simulation` multi-robot](https://github.com/JCHENG-Robotics/jcheng-simulation/blob/main/docs/MULTI_ROBOT.md)
- [`jcheng-learning`](https://github.com/JCHENG-Robotics/jcheng-learning) — dataset contract and training ownership; `docs/m1/` is not yet on `main`.
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
