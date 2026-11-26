# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- M4 offline replay in `src/jcheng_teleop/replay/`: verified capture reader,
  input replay against a fresh conditioner/mapper, a pure anomaly scan, quality
  metrics, and the `jcheng-teleop-replay` CLI (exit 0 clean, 1
  divergence/anomaly, 2 verification/profile mismatch). The package imports no
  rclpy, gateway, socket or subprocess module. `tests/test_replay.py` (16
  tests) and `evidence/20261126_m4_replay/`.
- `command.jsonl` records the submitted `payload` (wire projection), and
  replay compares it with the action at the same tick; a payload-less capture
  is counted, not invented. `TickResult.submitted_intent` exposes the intent
  handed to the gateway.
- Benchmark JSONL export (`src/jcheng_teleop/export/benchmark.py`) with one row
  per motion action; `data_source` maps hardware→`recorded`,
  simulation→`synthetic`, mock→`mock`; an in-repo output path is refused.
  `jcheng-benchmark` `read_dataset` accepts the output and a mock suite passes
  over it.
- `TickResult.stop_intent`: the session exposes the mode-specific stop intent
  it sends, so a capture records the stop as an `action` row instead of only
  an event code.

### Fixed

- Capture writer ordering: priority rows no longer jump ahead of earlier rows
  (one FIFO queue; `priority` only decides who is dropped under pressure). The
  first replay exposed this as `tick_id regressed` in `action.jsonl`.
- ROS harness capture timestamps use the host monotonic clock; the ROS wall
  clock is kept as `t_ros_ns`. The first mock capture showed a wall-clock
  regression in `observation.jsonl`.

### Added (M3)

- M3 capture core in `src/jcheng_teleop/capture/`: `jcheng.teleop.capture.v1`
  provenance metadata and validation, an append-only non-blocking JSONL writer
  with a bounded queue and priority rows, an `EpisodeRecorder` for the
  input/action/command/event streams, and a read-only seal/verify path
  (`manifest.json`, `SHA256SUMS`, tamper detection). Lease ids are hashed.
- `TeleopRunner.observer`: recorder/tracing hook isolated from the control
  loop; an observer exception is counted, `False` requests a system stop.
- CLI `--record DATA_ROOT`, `--capture-id` and `--task`; CLI captures are
  `environment_class=mock`, `source_class=scripted`, and the capture root must
  be outside a git worktree.
- `tests/test_capture.py` (26 tests) and `evidence/20261126_m3_capture/`.
- Observation rows (`jcheng.teleop.observation.v1`) copied from
  `/jcheng/telemetry/state`, with `truth`/`verification` never reinterpreted.
  The label gate accepts `bus` only in a hardware capture and `simulated` only
  in a simulation capture with a truth label; a rejected row becomes an
  `OBSERVATION_REJECTED` event.
- ROS demo harness capture: `record_root`, `capture_id`, `task`,
  `environment_class` (`mock|simulation`), `sim_truth_label`, `simulator_repo`,
  `simulator_version`, `state_topic` parameters; input/action/observation rows
  and a `SESSION_CLOSED` event. A capture fault sends one neutral frame and
  stops the script.
- Integration evidence: mock capture 252 observation rows (`commanded`/`timed`);
  simulation capture 188 rows (`measured`/`simulated`), joint1 0 -> 0.1361 rad.
- `tools/capture_acceptance_drill.py`: 30 × 60 s mock captures, each sealed and
  re-read; 30/30 `valid`, 270,060 rows, 0 label violations.
- `tools/disk_full_drill.py`: `RLIMIT_FSIZE` storage-failure drill; the
  recorder faults on EFBIG, the session stops with a stop intent, and the
  sealed capture carries `recorder_fault`. The faulted package may be
  unreadable and is retained, not exported. Evidence:
  `evidence/20261126_m3_capture/drills.txt`.

- M2 ROS 2 publisher `ros2_ws/src/jcheng_teleop_ros` and its Humble build
  evidence. The publisher takes an operator-supplied lease id and never mints
  one.
- ArmPi test-only simulation L3 evidence is recorded in `jcheng-system`
  (`e2e/reports/20261126_teleop_sim/`); a Jazzy/Humble build record is in
  `evidence/20261126_m2_ros/`.
- Gate-2 canonical domain-42 L3: runtime/teleop on 42, simulation bridge in a
  separate domain-43 context; both joints moved to about ±0.125 rad. Evidence
  is in `jcheng-system/e2e/reports/20261126_teleop_domain42/`.
- `examples/piper_x_demo/` (profile + identity binding, six revolute joints,
  no gripper): simulation-only, mirrors the non-canonical system profile.
- ArmPi canonical domain-42 L3 (joint1 0 -> 0.2375 rad) and PiPER X six-joint
  mock L3 (±0.1379 rad per joint), both runtime 42 + bridge 43, in
  `jcheng-system/e2e/reports/20261126_teleop_domain42_armpi/` and
  `..._piperx_mock/`.


## [0.3.0] — 2026-11-26

> M1 candidate; tag after merge. Contract remains `jcheng-interfaces` v0.1.0.

### Added

- ROS-free `jcheng_teleop` package: typed input samples, conditioning with
  deadzone/hysteresis, per-axis clamp and one-shot limit events, deadman and
  watchdog, canonical profile + teleop binding resolution, joint velocity and
  typed joint-position mapping, normalized gripper, session state machine,
  mode-specific stop intent and an in-process mock gateway.
- Device-free virtual, JSONL, keyboard and gamepad mapping adapters; no OS
  device driver, ROS, DDS or network listener.
- CLI `jcheng-teleop` with a demo profile/binding and a deterministic trace.
- 111 L0/L1 and in-process L2 tests, including 2/5/6-DoF profile fixtures,
  deterministic traces, lease/deadman/stop behavior, gateway fault injection
  and static no-device checks.
- M1 evidence under `evidence/20261126_m1_core/`.

### Changed

- Version 0.3.0. The capability remains `safety.class: offline`,
  `hardware_access: none` and has an empty runtime surface; no DDS topic is
  published.

## [0.2.0] — 2026-11-26

> M0 candidate. This version is not tagged yet; tag after operator approval
> and merge. The contract remains `jcheng-interfaces` v0.1.0.

### Added

- M0 architecture package: context, module responsibilities, session and
  process lifecycles, deployment topologies, timing budget and architecture
  decisions in `docs/ARCHITECTURE.md`.
- `docs/TELEOP_CORE.md`: typed input, conditioning, joint-position and
  joint-velocity mapping, normalized gripper, profile resolver, session state
  machine and gateway port.
- `docs/SAFETY_MODEL.md`: local state machine, deadman/watchdog timings, stop
  paths, hazard analysis, simulation/hardware isolation and residual risks.
- `docs/DATA_COLLECTION.md`: capture package, time synchronization, provenance
  taxonomy, quality gates and learning-owned LeRobot mapping.
- `docs/INTEGRATION_CONTRACT.md`: current system/gateway facts, the canonical
  streaming path, M2 test paths, failure semantics and blockers.
- `docs/DEPENDENCY_REVIEW.md`: LeRobot, `teleop_twist_joy`, MoveIt Servo,
  ALOHA, Mobile ALOHA, Open-TeleVision, GELLO, UMI and SmolVLA review with
  licenses and adopt/reject decisions.
- `docs/M1_PLAN.md`: work packages, module tree, test matrix, dependencies,
  risks and evidence plan for the ROS-free core.
- `docs/proposals/TELEOP_COMMAND_V0.2.md` and
  `docs/proposals/SYSTEM_TELEOP_INTAKE.md`: contract-first proposals only; no
  interface, gateway or system file is changed.
- M0 evidence record in `evidence/20261126_m0_design/`.

### Changed

- README, README.zh-CN, ROADMAP and ACCEPTANCE now describe the full M0–M9
  path, the current M0 state and the system-side blockers.
- The superseded `docs/INTEGRATION.md` is replaced by
  `docs/INTEGRATION_CONTRACT.md`; `docs/INPUT.md` is updated to the adapter and
  sample contract.
- `capability.yaml` and `VERSION` move to 0.2.0. The manifest remains
  `safety.class: offline`, `hardware_access: none` and has an empty runtime
  surface. The reserved `TeleopCommand` stream is still not published.
- The repository gate and contract tests now require the M0 document set and
  the full M0–M9 roadmap.

### Security

- No runtime, device, DDS, network listener, credential or recording was
  added. The static no-device scan and secret/artifact checks remain in force.

## [0.1.0] — 2026-11-26

### Added

- Initial repository scaffold: bilingual documentation set, admission manifest,
  repository gate, no-device static scan and `teleop-gate` CI.
- L3 admission for teleoperation intent: `safety.class: offline`,
  `hardware_access: none` and an empty runtime surface. The reserved
  `TeleopCommand` stream from `jcheng-interfaces` v0.1.0 is referenced but not
  published.
- Input, intent and integration boundary documents for the planned ROS-free
  core (M1) and intent node (M2).

## Related

- [README](README.md)
- [ROADMAP](ROADMAP.md)
- [ACCEPTANCE](ACCEPTANCE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
