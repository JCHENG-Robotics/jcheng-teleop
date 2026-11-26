# jcheng-teleop roadmap

> Status: **v0.3.0** as of 2026-11-26. M0 design is approved. The M1 ROS-free
> core and CLI are accepted at L1/in-process L2. M2 is In progress; the system
> teleop intake, ROS runtime subscriber, teleop ROS publisher and test-only
> simulation bridge exist. M3 has started: the capture core (provenance,
> non-blocking writer, seal/verify) records mock CLI runs, and the ROS harness
> records labelled observation rows from the system telemetry tap. M4 has
> input replay, command replay, metrics and benchmark export. M5 has the
> read-only status API; the studio panel and system stop proxy are on the
> studio side. M6 is In progress at the offline authorization/preflight stage;
> hardware streaming and stop confirmation are still missing. No
> device or hardware path exists in this repository. The full M0–M9 path is
> recorded here so that later milestones are not redesigned around today's
> mock-only system.

## Current state

| Item | State | Evidence |
|---|---|---|
| Repository admission (`capability.yaml`, L3) | Complete (2026-11-26); the `.github` taxonomy merge is pending (B0) | `capability.yaml`; `tests/test_contract.py` |
| M0 ecosystem audit, architecture, contract proposals | Complete (delivery/approved, 2026-11-26); Round 2 APPROVE WITH CHANGES; operator approved | `evidence/20261126_m0_design/`; [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Research and dependency review | Complete (2026-11-26) | [docs/DEPENDENCY_REVIEW.md](docs/DEPENDENCY_REVIEW.md) |
| ROS-free teleop core, virtual/keyboard/JSONL/gamepad mapping, CLI | Complete (2026-11-26); L1/in-process L2 accepted | `evidence/20261126_m1_core/`; `tests/` |
| System teleoperation intake and simulation teleoperation | In progress (M2); system intake/ROS subscriber merged; teleop ROS publisher landed; system test-only sim bridge + ArmPi/Gate-2/PiPER X mock L3 (canonical domain 42 + domain-43 bridge) landed on `feat/teleop-sim-bridge`; PiPER X canonical profile pending | `jcheng-system` `tests/test_teleop.py`; `docs/TELEOP-INTAKE.md` |
| Episode capture, provenance and time sync | In progress (M3): capture core, provenance gate, non-blocking writer, seal/verify, CLI and ROS-harness recording, labelled observation rows and the session-close event landed. Mock acceptance met: 30 × 60 s valid captures and a storage-fault stop drill. Media, a simulation/hardware episode set and cross-stream time sync remain open | `evidence/20261126_m3_capture/`; `docs/DATA_COLLECTION.md` |
| Offline replay, quality evaluation and LeRobot export | In progress (M4): input replay, command-payload capture + wire-projection replay, anomalies, basic quality metrics and benchmark JSONL export landed. LeRobot v3 export is blocked on the learning dataset contract and the absolute-position action gap | `evidence/20261126_m4_replay/` |
| Studio teleoperation panel | In progress (M5); read-only teleop status API (`jcheng.teleop.status.v1`, loopback-only) landed in the ROS harness; studio panel and stop wiring next | [docs/STATUS_API.md](docs/STATUS_API.md) |
| Leader-arm and supervised hardware teleoperation | In progress (M6, offline prerequisites); `jcheng.teleop.authorization.v1` + `jcheng-teleop-preflight` implemented and tested; hardware blocked by the system streaming executor (B2), wire v0.2 (B3), stop confirmation (B9) and no e-stop | [docs/M6_PLAN.md](docs/M6_PLAN.md); `evidence/20261126_m6_preflight/` |
| Hybrid demonstration/policy data and SmolVLA loop | Planned (M7) | — |
| Shared autonomy and human-in-the-loop correction | Planned (M8) | — |
| Mobile manipulation teleoperation | Planned (M9) | — |

## Milestones

| Milestone | Scope | State | Exit criterion | Evidence |
|---|---|---|---|---|
| M0 | Admission, architecture, contract and dependency review, M1 plan | Complete (approved 2026-11-26) | Document set, research record, proposals, gate and review pass; operator approved; commit/tag remains an explicit request | `evidence/20261126_m0_design/` |
| M1 | ROS-free deterministic core, virtual/keyboard/JSONL/gamepad mapping, profile mapping, safety state machine, in-process mock gateway | Complete (2026-11-26); L1/in-process L2 accepted | 111 tests pass; no DDS, device, recording or hardware | `evidence/20261126_m1_core/` |
| M2 | System mock + simulation teleoperation across robot profiles | In progress (system intake + ROS subscriber + teleop publisher + ArmPi/Gate-2/PiPER X mock L3 on canonical domain 42 + Humble build; PiPER X canonical profile pending) | Lease/deadman/preemption/stop proven end-to-end in mock and simulation; no hardware | `jcheng-system` `tests/test_teleop.py`; `docs/TELEOP-INTAKE.md` |
| M3 | Episode capture, time synchronization, provenance and quality gate | In progress; the recorder, provenance gate, non-blocking writer, seal/verify, observation rows and the mock 30-episode/storage-fault drills are done. Media, a simulation/hardware capture set and action/observation time-sync validation remain | 30 complete episodes, 0 simulation-as-hardware labels, recorder cannot block stop | `evidence/20261126_m3_capture/`; `docs/DATA_COLLECTION.md` |
| M4 | Offline replay, anomaly detection and LeRobot v3 export | In progress; input replay, command-payload/wire-projection replay, anomalies, basic metrics and benchmark JSONL export are implemented. LeRobot v3 export is blocked on the learning contract and the absolute-position action gap | Byte-identical replay; benchmark scores; LeRobot round-trip equality | `evidence/20261126_m4_replay/` |
| M5 | Studio teleoperation panel and session UX | In progress; the read-only status contract and loopback server are implemented; the studio panel, stale-state UX and stop wiring remain | Operator can observe input/lease/deadman state and stop; studio remains HTTP/WS only | [docs/STATUS_API.md](docs/STATUS_API.md) |
| M6 | Leader-arm and supervised hardware teleoperation | In progress; offline authorization and preflight are implemented. Hardware is blocked: streaming executor, position/gripper wire, stop confirmation, no e-stop, PiPER X canonical profile | Authorized L5 session with bus-verified stop and no unattended motion | [docs/M6_PLAN.md](docs/M6_PLAN.md); `evidence/20261126_m6_preflight/` |
| M7 | Hybrid autonomous grasp + human demonstration + SmolVLA loop | Planned | Mixed-source dataset, policy evaluation and human takeover evidence | — |
| M8 | Shared autonomy, policy takeover and correction demonstrations | Planned | Authority handover is explicit, bounded and auditable | — |
| M9 | Mobile manipulation teleoperation and industrial extension | Planned | Coordinated base/arm intent with separate base authority and stop evidence | — |

## M0 — admission, architecture and contract review

**Scope.** Audit the ecosystem governance, interfaces, system gateway/arbiter,
simulation catalog, learning dataset contract, studio, applications and
benchmark. Record what exists, what is reusable, what is missing and which
cross-repository changes are prerequisites. Produce the M1 execution plan.

**Depends on.** The admitted v0.1.0 scaffold and the operator's decision to
start the subsystem.

**Non-goals.** No runtime code, no DDS node, no device adapter, no recording,
no hardware session, no interface change.

**Acceptance (quantified).**

- All required M0 documents exist and every relative link resolves.
- The audit names the exact contract and runtime gaps with file paths.
- Two contract-first proposals exist: teleoperation command v0.2 and the
  system teleoperation intake. Neither modifies `jcheng-interfaces`.
- The research record covers LeRobot, `teleop_twist_joy`, MoveIt Servo, ALOHA,
  Mobile ALOHA, Open-TeleVision, GELLO, UMI and SmolVLA with licenses and an
  explicit adopt/reject decision.
- M1 work packages, module tree, test matrix, cross-repository dependencies and
  blockers are written down.
- Independent design review finds no unresolved contradiction with governance.

**Test plan.** Repository gate, unit tests, Markdown link check, static
no-device scan, manual traceability review from every claim to an audit path.

**Safety risks.** Overclaiming a runtime that does not exist; designing a path
that bypasses the arbiter; treating an interface reservation as an implemented
consumer; treating simulation data as hardware evidence.

**Exit criteria.** The operator approved the M0 design on 2026-11-26 and
authorized M1. Commit/tag remains an explicit operator request.

## M1 — deterministic ROS-free teleop core

**Scope.** Build the hardware-independent core: typed input samples, input
conditioning, per-profile joint mapping, joint-position and joint-velocity
action intents, session state machine, deadman/watchdog, local limits, a
loopback mock gateway adapter, virtual/keyboard/JSONL input sources and a
deterministic CLI. The core stays importable without ROS.

**Depends on.** M0 approval. Read-only use of `TeleopCommand` v0.1.0 semantics;
no interface change is required for M1.

**Non-goals.** DDS, domain 42, real gateway, lease acquisition, ROS node,
recording, replay, Cartesian motion, device access, hardware.

**Acceptance (quantified).**

- A 50 Hz deterministic run produces identical output for identical input,
  clock and profile fixtures (byte-identical action stream).
- No action is emitted without a fresh enable edge and a valid session state;
  the stop path emits one mode-specific stop intent with `deadman=false`
  (zero velocity, hold position, or hold gripper), then silence.
- Input staleness is detected within one tick after `deadman_ms`; a stale
  sample never produces a non-zero action.
- Every over-limit request produces exactly one counted limit event and a
  bounded output; no silent truncation.
- Profile mismatch, non-finite values, sequence rollback, duplicate sequence
  and non-monotonic stamps are rejected, not repaired.
- `grep`-based static scan proves no device, vendor topic, `ExecuteMotion`,
  `/cmd_vel` or model/recording artifact exists.
- Test suite covers at least the matrix in [docs/M1_PLAN.md](docs/M1_PLAN.md).

**Test plan.** L1 unit tests for conditioning, mapping, state machine, profile
resolution and determinism; L2 in-process mock gateway tests for lease,
deadman, stop and fault injection; CLI golden tests; static boundary tests.

**Safety risks.** Mode confusion, stale input, profile/order mismatch, hidden
saturation, recorder coupling, a mock path that is mistaken for a system path.

**Exit criteria.** L1 and in-process L2 evidence is recorded; an independent
review confirms no motion authority and no device access; M2 is authorized
separately.

**Implementation state (2026-11-26).** W1-W12 delivered in `src/jcheng_teleop`
with 111 tests: conditioning, deadman, profile resolution, mapper, safety guard,
session, mock gateway, virtual/JSONL/keyboard/gamepad adapters, deterministic
runner and CLI. Evidence: `evidence/20261126_m1_core/`. No DDS, ROS node,
device, recording or hardware was added. Independent code review
Round 1 returned REJECT; Round 2 returned APPROVE WITH CHANGES; all findings
were fixed. M1 is accepted at L1/in-process L2; commit/tag is authorized.

## M2 — system mock and simulation teleoperation

**Scope.** Add a thin intent node and gateway adapter that submit teleoperation
intent through the system layer. Run against the system mock stack and the
`jcheng-simulation` plant for `armpi_ultra`, `gate2_arm` and `piper_x`,
sequentially, one plant at a time. The canonical path is a system-side
teleoperation intake that samples `TeleopCommand` on domain 42 and feeds the
existing arbiter/safety path. Until that intake exists, a **test-only** HTTP
step adapter against the current gateway may be used to exercise the core, but
it is not reported as M2 completion.

**Depends on.** M1 accepted. System-side work package S-M2 (teleoperation
intake, streaming servo session, teleop error semantics). Simulation-side work
package SIM-M2 (test bridge from the system mock hardware port to
`/sim/joint_command` or the JTC action). A contract decision on
`TeleopCommand` position/gripper support if leader-style position teleoperation
is enabled.

**Non-goals.** Real hardware, real vendor controller, Cartesian execution,
recording, dataset export, unattended operation.

**Acceptance (quantified).**

- A command without a valid lease is rejected with a canonical lease error;
  the teleop process emits no further motion.
- Lease revocation, expiry and preemption stop output within one control tick;
  the process does not re-acquire a lease automatically.
- Deadman release emits the stop intent within one control tick and the system
  accepts the abort/stop within 300 ms, measured. Input timeout is detected at
  300 ms, then the stop intent is emitted within one tick; the end-to-end
  timeout stop is reported as `300 ms + transport + intake + actuation`, not
  claimed as 300 ms end-to-end. The next motion requires a fresh enable edge.
- Sequence rollback, duplicate sequence and stale arrival are rejected and
  counted; a clock-sync bound is enforced only when one is measured.
- The three catalog robots run sequentially with their own profiles; no joint
  order, sign or limit is hard-coded in the core.
- The simulation truth label is `simulated`; no report calls it hardware.
- Zero commands reach a real device; the process joins only domain 42 (and the
  test bridge joins 43 as test infrastructure).
- L3 evidence exists for lease, deadman, preemption and stop behavior.

**Test plan.** L2 system mock integration; L3 system mock + simulation plant;
fault injection for lease loss, stale input, gateway error, duplicate command,
preemption and stop; profile matrix for 2-DoF, 5-DoF and 6-DoF robots; QoS and
timing checks.

**Safety risks.** The gateway is discrete and rate-limited, so a naive
per-sample HTTP loop creates latency and `MOTION_BUSY`; the system consumer may
not exist; the simulation plant is not the real robot; one plant per domain;
the mock holds the last target after its command timeout instead of stopping.

**Exit criteria.** The system mock + simulation path passes at L3 with the
canonical or explicitly labelled test-only transport; the system intake
proposal is accepted or M2 is recorded as partially verified with the blocker
named. No hardware session is requested at M2.

## M3 — episode capture, time synchronization and provenance

**Scope.** Record observations, raw operator input, mapped action intent, wire
command, system result, measured/commanded robot state, timestamps, task
description, outcome and provenance into an immutable capture package outside
git. Keep command cache, bus measurement and simulation truth separate.

**Depends on.** M2 path available for at least mock/simulation. The
`jcheng.dataset.v1` contract must be frozen (with a `jcheng-interfaces`
proposal if teleop is a cross-repository producer). A measured-state source
must exist; `/joint_states` is not accepted as pose truth.

**Non-goals.** LeRobot export, training, policy inference, hardware capture,
dataset storage in git.

**Acceptance (quantified).**

- 30 consecutive episodes of at least 60 s each pass the capture validator.
- Every episode records `source_class`, `environment_class`, operator/session,
  profile hash, contract hash, calibration id (if any), clock source and
  outcome; 0 episodes are labelled hardware when produced in simulation.
- Command, action intent, measured state and simulation truth are separate
  streams and cannot be silently merged.
- Time-sync offset and uncertainty are recorded; a skew above the threshold
  marks the episode degraded instead of rebasing it.
- Completeness is at least 99.9% of expected 50 Hz ticks over the acceptance
  run, excluding declared deadman gaps; every gap is explained by an event.
- Recorder backpressure, disk failure or validation failure never blocks the
  stop path; a required-recording session fails closed.
- A capture can be re-read and hash-verified without the teleop runtime.

**Test plan.** L2/L3 synthetic and simulation captures; clock-skew injection;
dropped-sample injection; disk-full and permission failures; corrupted package
tests; provenance matrix; schema validation; independent re-read.

**Safety risks.** Simulation data entering training as real data; command cache
presented as measurement; recorder blocking control; clock rebasing; missing
authorization for real-human data.

**Exit criteria.** Capture validator and evidence exist; learning accepts the
capture-to-dataset mapping in principle; no training or model artifact is
produced yet.

## M4 — offline replay, quality evaluation and LeRobot adapter

**Scope.** Deterministic replay of captured input through the same core with a
fake clock; anomaly detection; quality metrics; JSONL export for
`jcheng-benchmark`; LeRobot v3.0 dataset export through the learning-owned
contract. No live gateway and no robot.

**Depends on.** M3 capture format accepted. Learning's `jcheng.dataset.v1`
writer/validator is merged or a converter is agreed. A position-mode capture
path (v0.2 native position or a learning-approved velocity action) exists for
the LeRobot round-trip; otherwise M4 is replay/capture-only. Benchmark suite
format is stable enough for the exported JSONL.

**Non-goals.** Policy training, model selection, live inference, hardware.

**Acceptance (quantified).**

- Replaying the same capture with the same profile and clock produces
  byte-identical action intent; the replayed command is compared with the
  recorded command (there is no live gateway).
- All 30 M3 episodes (at least 90,000 frames at 50 Hz × 60 s) are evaluated;
  every anomaly has a machine-readable code and a trace to a tick.
- Benchmark reports use `data_source: recorded` only for genuine captures;
  mock/simulation exports use `mock`/`synthetic` and never `hardware`.
- LeRobot export round-trips on position-mode episodes: frame count,
  action/state dimensions, task text, timestamps and provenance sidecar match
  the capture. Velocity-only episodes remain capture-only until learning
  accepts a velocity action kind.
- No gateway connection, device or DDS domain is opened during replay.

**Test plan.** L4 replay golden tests; property tests for deterministic
ordering; anomaly fixtures; benchmark suite with pre-registered thresholds;
LeRobot round-trip; provenance negative tests.

**Safety risks.** Replay being mistaken for a live session; a replay process
connecting to a real gateway; dataset lineage loss; quality thresholds chosen
after seeing results.

**Exit criteria.** Reproducible replay and quality report exist; the dataset
adapter is accepted by learning; no model training is claimed.

## M5 — studio teleoperation panel

**Scope.** Add a studio panel for teleoperation session state, input health,
lease holder, deadman state, mapping/profile identity, stop control and
capture status. Studio continues to use gateway HTTP/WS only; the teleop
process remains the only capability that produces intent.

**Depends on.** M2/M3 surfaces; studio's `/v1` client and session model; a
studio–teleop status contract (HTTP or WS) that does not give studio motion
authority. A browser gamepad is optional and remains an operator-side input
source; it is not wired directly to motion.

**Non-goals.** Studio publishing intent directly, studio joining DDS, studio
opening devices, remote internet teleoperation.

**Acceptance (quantified).**

- The panel shows lease, deadman, input age, profile hash, contract hash and
  capture state with explicit `commanded`/`measured` labels.
- A status sample older than 1 s, or a missing teleop status, is displayed as
  degraded; it never shows a green "ready" state.
- Stop from the panel goes through the system stop path, not a studio-local
  motion call; the stop request is visible within 500 ms.
- E2E tests prove the browser cannot submit `ExecuteMotion` directly.
- No DDS, device or vendor topic appears in the studio diff.

**Test plan.** Studio backend tests, Playwright mock E2E, stale-state and
authorization negative tests, contract checks.

**Safety risks.** UI session mistaken for a lease; stale display; two operators
believing they hold control; stop control not reaching the system.

**Exit criteria.** L2/L3 studio evidence exists; operator can see and stop a
mock session; no hardware.

## M6 — leader-arm and supervised hardware teleoperation

**Scope.** Adapt an operator-side leader arm (or equivalent absolute input) to
the teleop input contract; enable joint-position intent and gripper intent;
run a supervised hardware session on ArmPi Ultra, with PiPER X as a later
profile. Characterize latency, tracking, sign/order mapping and stop.

**Depends on.** M5; contract v0.2 with joint position and gripper; profile v2
or a teleop overlay that can express non-bus-servo arms; a system-side
privileged servo/executor path that can stream multi-joint targets; and either
a system stop-confirmation field (R5) or an explicit `stop_confirmed: unknown`
report. The current vendor executor accepts one `JOINT_STEP` for one joint at
about 5 commands/s and cannot stream a 5-joint teleoperation loop; M6 is
blocked until that path is designed, reviewed and implemented.

**Non-goals.** Unattended motion, e-stop claims, Cartesian teleoperation,
force feedback, self-collision avoidance, industrial certification.

**Acceptance (quantified).**

- A separately authorized L5 session records operator, supervisor, workspace
  checklist, contract/profile hashes and the exact motion scope.
- Deadman release emits the stop intent within one tick and the system accepts
  the abort within 300 ms; input timeout is detected at 300 ms and the
  end-to-end time is reported as a distribution. The bus read confirms the stop
  when the system's confirmation path exists; until then it is `unknown`.
- No motion occurs before a fresh enable edge, after lease loss or after a
  stop latch.
- Joint order, sign and limits are validated against the active profile; a
  mismatch refuses the session.
- Tracking and latency are reported with distributions, not a single best
  sample; the operator records numeric bounds before the session and a failed
  bound stays failed.
- The report states that the platform has no e-stop and that the software stop
  is not an e-stop.

**Test plan.** Bench tests without motion; supervised low-speed session;
fault injection for lease revoke, input unplug, gateway loss and stop; bus-read
verification; operator workload/feedback review.

**Safety risks.** Runaway motion, wrong profile, leader/follower sign error,
vendor executor serialization, bus-read latency, operator fatigue, no e-stop.

**Exit criteria.** L5 evidence is accepted for a defined, low-speed scope; the
scope is not generalized to other robots without separate evidence.

## M7 — hybrid demonstration and SmolVLA loop

**Scope.** Collect mixed-source episodes: human teleoperation, autonomous
grasp, policy execution and human correction. Keep immutable provenance,
train a SmolVLA/ACT policy offline, deploy under a lease and evaluate with a
pre-registered protocol.

**Depends on.** M6; learning M2/M3 (training and policy intent); applications
task execution; a policy artifact store outside git; benchmark evaluation.

**Non-goals.** Fully autonomous operation, safety certification, model
weights in git, mixing simulation and hardware without labels.

**Acceptance (quantified).**

- At least two source classes are collected in separate learning datasets, or
  in one learning-approved mixed dataset with per-episode provenance; there are
  at least 30 episodes and no episode has an ambiguous environment class.
- Policy rollouts run under a non-teleop lease and can be preempted by the
  operator; takeover stops the policy before teleop intent is accepted.
- Evaluation uses at least three pre-registered tasks, fixed seeds, at least
  10 trials per hardware task and thresholds fixed before the run;
  synthetic/mock results are reported separately from hardware.
- Model artifacts are hash-pinned and stored outside the repository.

**Test plan.** Offline training reproducibility, held-out evaluation, mock
rollout, supervised hardware rollout, takeover and correction scenarios.

**Safety risks.** Policy motion without a valid lease, dataset contamination,
overfitting to the evaluation set, operator takeover race.

**Exit criteria.** A policy can be trained, evaluated and deployed in a
supervised loop with complete provenance; no autonomy claim beyond evidence.

## M8 — shared autonomy and human-in-the-loop correction

**Scope.** Blend operator and policy authority with explicit modes, confidence
gating, takeover and correction capture. Record who held authority at every
tick.

**Depends on.** M7; a policy intent contract; a shared-authority state machine;
studio indicators for authority source.

**Non-goals.** Implicit blending without an audit trail, silent policy
takeover, unbounded correction authority.

**Acceptance (quantified).**

- Every tick has exactly one authority source or an explicit blend with
  weights; 100% authority coverage, with no gaps.
- Operator takeover is accepted within 100 ms and the policy stops within
  150 ms, measured over at least 20 takeover trials.
- A policy fault or low-confidence condition yields a defined stop/handover,
  not a silent switch.
- Correction episodes are labelled `human_correction` and retain the policy
  action that preceded them.

The 100 ms / 150 ms takeover targets are initial design bounds; M7 latency
evidence may revise them before the M8 gate, but the bound is fixed before the
run and a failed bound stays failed.

**Test plan.** Authority state-machine tests, fault injection, takeover race
tests, mock and supervised hardware scenarios, operator study.

**Safety risks.** Authority confusion, delayed takeover, policy fighting the
operator, incomplete correction labels.

**Exit criteria.** Shared-autonomy behavior is auditable and bounded; evidence
supports only the tested modes.

## M9 — mobile manipulation teleoperation

**Scope.** Coordinate arm teleoperation with base motion while preserving
`jcheng-mobile` as the base-intent owner. Teleop proposes arm and, through the
mobile contract, coordinated base intent; it never publishes `/cmd_vel`
directly.

**Depends on.** M8; mobile base intent and Nav2 integration; a coordinated
lease/scope model; simulation of the mobile plant; industrial task profiles.

**Non-goals.** Teleop owning `/cmd_vel`, bypassing Nav2, outdoor autonomy,
certified industrial safety.

**Acceptance (quantified).**

- Base and arm intents have separate scopes/leases or an explicit coordinated
  scope; no command bypasses the mobile layer; teleop publishes zero
  `/cmd_vel` messages.
- A base stop, arm stop and coordinated stop are each tested; coordinated
  stop is within 300 ms and the scope is reported.
- Simulation covers at least one mobile manipulation task; hardware evidence
  is separate and authorized.
- Base teleoperation is not claimed until the mobile stack provides the
  contract and evidence.

The 300 ms coordinated-stop bound is aligned with the teleop deadman target and
is re-confirmed by the mobile stack's own stop evidence before the M9 gate.

**Test plan.** Simulation coordinated tasks, lease/scope matrix, latency and
stop tests, supervised hardware pilot if authorized.

**Safety risks.** Base/arm coordination, collision, network loss, one operator
controlling two authorities, no e-stop.

**Exit criteria.** Coordinated teleoperation is demonstrated within a defined
scope and contract; industrial claims wait for separate certification work.

## Next

1. **M1 acceptance review.** The M1 core and 111 tests are in place. Review
   [ACCEPTANCE.md](ACCEPTANCE.md) and `evidence/20261126_m1_core/`.
2. **M2 preparation (design and cross-repository review).** Review the system
   teleoperation intake and simulation bridge proposals with the
   system/simulation owners. M2 implementation does not start until those
   proposals are accepted and B0/B1/B5/B11 are resolved.
3. **M2 — system mock + simulation.** Execute only after the system-side
   intake and simulation bridge are approved; no hardware.

## Out of scope

- Device access and owning the operator input adapter. Physical gamepad,
  keyboard, wheel, pendant and leader-arm drivers are operator-side and outside
  the capability boundary.
- Direct hardware commands, vendor topics, `/move_action`, `ExecuteMotion` and
  any servo/motor write path.
- `/cmd_vel` and base chassis intent; `jcheng-mobile` owns the base stream.
- Acting as an e-stop or a safety-rated function. The platform has no e-stop,
  brake, encoder or self-collision model.
- Remote internet control, cross-network real-time teleoperation and
  unattended motion.
- Training, model weights or datasets inside git.
- Replacing the system gateway, lease manager, motion arbiter, safety
  supervisor, simulation catalog or benchmark harness.

## Dependencies

- `jcheng-interfaces` `>=0.1,<0.2`; contract hash
  `sha256:0b8d72ced7f54d444d6851d8b99a51a78e2bed3f687324f51a15f76557f24b42`.
  A v0.2 change requires a new tag, a regenerated manifest and matching
  consumer updates.
- `jcheng-system` gateway/lease/arbiter API `>=0.1,<0.2` as declared; the
  repository is currently `0.3.0-dev0`, so the range must be reconciled before
  M2. The system layer remains the only motion origin.
- `jcheng-simulation` `0.1.0` catalog and `/sim/*` surfaces, pinned by commit;
  the catalog schema is repository-local and Experimental.
- `jcheng-learning` committed `0.1.0`; its `0.2.0` dataset contract and writer
  are an uncommitted working tree, not a frozen dependency. `jcheng.dataset.v1`
  is a proposal until merged and, if cross-repository, registered in
  `jcheng-interfaces`.
- `jcheng-studio` `0.7.0` for M5; `jcheng-benchmark` `0.1.0` for M4 scoring.
- Real-robot work requires separate, explicit operator authorization per
  session and is never triggered by CI or unattended runs.

## Related

- [Architecture](docs/ARCHITECTURE.md)
- [Teleop core](docs/TELEOP_CORE.md)
- [Safety model](docs/SAFETY_MODEL.md)
- [Data collection](docs/DATA_COLLECTION.md)
- [Integration contract](docs/INTEGRATION_CONTRACT.md)
- [Dependency review](docs/DEPENDENCY_REVIEW.md)
- [M1 plan](docs/M1_PLAN.md)
- [Acceptance](ACCEPTANCE.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-simulation`](https://github.com/JCHENG-Robotics/jcheng-simulation)
- [`jcheng-learning`](https://github.com/JCHENG-Robotics/jcheng-learning)
- [`.github` roadmap](https://github.com/JCHENG-Robotics/.github/blob/main/ROADMAP.md)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
