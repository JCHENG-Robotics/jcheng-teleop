# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
