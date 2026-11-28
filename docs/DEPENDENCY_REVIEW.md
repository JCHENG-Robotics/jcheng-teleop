# Dependency and prior-art review — jcheng-teleop

> Status: **Proposed** as of 2026-11-26. Research was performed against
> public sources on 2026-11-26. Versions and licenses are recorded as observed;
> a dependency is not adopted until it is pinned, reviewed and tested. No
> third-party code is copied into this repository.

## 1. Method

Each candidate is assessed for:

1. **Problem fit** — does it solve a problem this repository actually has?
2. **Architecture fit** — does it preserve the system layer as the only motion
   authority and the L3 boundary (`hardware_access: none`)?
3. **License** — is reuse compatible with the open ecosystem license review?
4. **Operational cost** — runtime weight, ROS/RMW coupling, device access,
   maintenance and supply-chain surface.
5. **Evidence** — is the claim from a primary source (paper, official docs,
   source tree) rather than a secondary summary?

The default is to adopt **design ideas** and reject **runtime dependencies**
unless the dependency is small, permissively licensed, actively maintained and
does not duplicate an ecosystem owner.

## 2. Ecosystem components reused, not rebuilt

| Component | Owner | What teleop reuses | What teleop must not duplicate |
|---|---|---|---|
| Contract and hashes | `jcheng-interfaces` | `TeleopCommand`, `ControlLease`, `MotionCommand`, `RobotState`, error registry, schema validation | Message definitions, enum values, contract hashing |
| Gateway, lease, arbiter, safety | `jcheng-system` | HTTP/WS admission, lease lifecycle, priority 40, stop latch, evidence | Motion execution, arbitration, safety policy, hardware bridge |
| Robot catalog and profiles | `jcheng-simulation` / system config | Joint names/order/limits, profile hashes, simulation topics | Catalog schema, URDF/controller configs, plant |
| Dataset contract and LeRobot export | `jcheng-learning` | `jcheng.dataset.v1`, writer/validator, LeRobot pin | Dataset schema, training, model artifacts |
| Operator console | `jcheng-studio` | Session/auth UI, gateway client, status panels | Gateway client, browser shell, session store |
| Gateway client patterns | `jcheng-applications` | Strict parsers, no-retry transport, hash-chained run records | Recipe runner, task engine |
| Offline scoring | `jcheng-benchmark` | JSONL suite/report format, thresholds | Benchmark runner, metrics implementation |
| Governance | `.github` | Layer rules, documentation standard, hardware workflow | Status vocabulary, acceptance levels |

## 3. Prior art

### 3.1 LeRobot (Hugging Face)

- **Source:** <https://github.com/huggingface/lerobot>
- **License:** Apache-2.0 (repository `LICENSE`; some derived notices are MIT
  or Apache-2.0, retained in the repository).
- **Relevant design:** `Teleoperator` abstract base class with
  `action_features`, `feedback_features`, `is_connected`, `connect`,
  `calibrate`, `configure`, `get_action`, `send_feedback`, `disconnect`;
  `get_action()` returns a flat action dictionary; factory
  `make_teleoperator_from_config`; leader arms (`so_leader`, `koch_leader`,
  `bi_so_leader`), gamepad and keyboard teleoperators; dataset v3.0 with
  Parquet/MP4 shards and episode metadata; `lerobot-record` and
  `lerobot-teleoperate`.
- **Action/rate:** dataset FPS-driven recording (commonly 30 FPS for SmolVLA
  community data); leader arms stream joint positions; gamepad/keyboard emit
  deltas and gripper actions.
- **Adopt:** the lifecycle contract (features declared before connection,
  explicit connect/configure/get_action/disconnect), flat action dictionaries,
  a device-free `get_action` test surface, and the dataset v3.0 concepts.
- **Reject as runtime:** the full package pulls PyTorch and device drivers and
  owns robot I/O. Teleop must not import it in the core or open a device.
  Dataset conversion belongs to `jcheng-learning`.
- **Why:** the lifecycle is proven and small; the runtime would duplicate the
  learning owner and violate the L3 device boundary.

### 3.2 ROS 2 `teleop_twist_joy`

- **Source:** <https://github.com/ros2/teleop_twist_joy>
- **Version/license:** 2.6.5, BSD (package.xml).
- **Relevant design:** `require_enable_button` defaults to true;
  `enable_button` is a hold-to-run deadman; linear/angular axis mapping;
  normal and turbo scales; `publish_stamped_twist`; explicit statement that
  the node provides **no rate limiting or autorepeat**.
- **Adopt:** hold-to-run enable as the default, explicit axis/scale mapping,
  no implicit rate limiting (the teleop core owns the tick).
- **Reject:** it publishes `cmd_vel` for a base, has no arm/gripper semantics,
  no lease and no stop latch. Base intent belongs to `jcheng-mobile`.
- **Why:** the deadman semantics are directly reusable; the transport and
  authority model are not.

### 3.3 MoveIt Servo (MoveIt 2)

- **Source:** <https://moveit.picknik.ai/main/doc/examples/realtime_servo/realtime_servo_tutorial.html>,
  <https://github.com/moveit/moveit2>
- **License:** BSD-3-Clause.
- **Relevant design:** three command types (joint velocities via
  `control_msgs/JointJog`, Cartesian twist via `geometry_msgs/TwistStamped`,
  pose via `geometry_msgs/PoseStamped`); `switch_command_type` service;
  `pause_servo`; `publish_period` (default 0.01 s); `incoming_command_timeout`;
  `command_in_type: unitless|speed_units`; collision and singularity velocity
  scaling; `ServoStatus`; joint limit margins.
- **Adopt:** the typed command-mode model, an explicit command timeout, a
  status surface, velocity scaling near limits, and pause/stop semantics as
  design references.
- **Reject as runtime:** MoveIt Servo would become a motion controller inside
  the capability, requires MoveIt/robot model/kinematics, and bypasses the
  JCHENG gateway/lease/arbiter. It also assumes a collision model the platform
  does not have. Cartesian modes are reserved, not implemented.
- **Why:** proven teleoperation patterns, wrong authority boundary.

### 3.4 ALOHA / ACT

- **Source:** <https://github.com/tonyzhaozh/aloha>; paper
  <https://arxiv.org/abs/2304.13705>
- **License:** MIT (repository `LICENSE`, Copyright 2023 Tony Z. Zhao).
- **Relevant design:** low-cost bimanual leader-follower; direct joint-position
  mapping (no IK); absolute joint positions as actions; ~50 Hz teleoperation,
  camera streaming and policy execution; 14-DoF action vector for two 6-DoF
  arms plus grippers; an ablation reported a large slowdown at 5 Hz, which is
  why the reference rate matters.
- **Adopt:** 50 Hz as the reference control rate; absolute joint-position
  mapping for leader-style teleoperation; bimanual support as a profile
  extension; the separation of observation and action.
- **Reject:** the Dynamixel/vendor code, the fixed 14-DoF assumption and the
  hardware-specific calibration.
- **Why:** the control semantics are the closest match to the planned M6
  leader-arm path; the code is hardware-bound.

### 3.5 Mobile ALOHA

- **Source:** <https://github.com/MarkFzp/mobile-aloha>; paper
  <https://arxiv.org/abs/2401.02117>
- **License:** MIT.
- **Relevant design:** whole-body teleoperation with a wheeled base and two
  arms; co-training with static ALOHA data; base and arm commands collected
  together.
- **Adopt:** the coordinated base/arm demonstration model for M9; the
  separation of base and arm authority in the data model.
- **Reject:** the tethered hardware and the assumption that teleop owns
  `/cmd_vel`.
- **Why:** M9 needs coordinated data, but `jcheng-mobile` owns base intent.

### 3.6 Open-TeleVision

- **Source:** <https://github.com/OpenTeleVision/TeleVision>; paper
  <https://arxiv.org/abs/2407.01512>
- **License:** Apache-2.0 (repository `LICENSE`, Copyright 2024 the authors).
- **Relevant design:** VR head/hand tracking; relative end-effector position
  with absolute orientation; closed-loop inverse kinematics (CLIK); active
  stereo camera at ~60 Hz; retargeting; immersive feedback.
- **Adopt:** relative Cartesian action semantics with an explicit frame, and
  the idea of operator visual feedback as a separate concern.
- **Reject as runtime:** VR/web streaming stack, Vuer, headset dependency and
  IK inside teleop. The system has no Cartesian execution path and teleop must
  not become a kinematics authority.
- **Why:** useful for future M6/M9 Cartesian design; not needed for M1–M2.

### 3.7 GELLO

- **Source:** <https://github.com/wuphilipp/gello_software>; paper
  <https://arxiv.org/abs/2309.13037>
- **License:** MIT (software), Copyright 2023 Philipp Wu.
- **Relevant design:** a kinematically equivalent, low-cost leader arm; joint
  positions streamed directly to the follower; no IK; supports Franka, UR5 and
  xArm; user study favored it over VR/spacemouse for demonstration collection.
- **Adopt:** the leader-arm profile concept and direct joint-position mapping;
  the operator-side device boundary.
- **Reject:** the specific 3D-printed hardware and Dynamixel code.
- **Why:** validates the M6 leader-arm approach without adding a device
  dependency to this repository.

### 3.8 UMI (Universal Manipulation Interface)

- **Source:** <https://github.com/real-stanford/universal_manipulation_interface>;
  paper <https://arxiv.org/abs/2402.10329>
- **License:** MIT (repository `LICENSE`, Copyright 2023 Columbia AI and
  Robotics Lab).
- **Relevant design:** handheld gripper data collection; relative-trajectory
  action representation; inference-time latency matching; camera-centric,
  calibration-free policy interface; cross-embodiment deployment.
- **Adopt:** relative action representation and latency matching as design
  references for M7/M9; the requirement to record latency explicitly.
- **Reject:** the handheld hardware and the assumption that a policy can be
  deployed without the JCHENG lease/safety path.
- **Why:** strong evidence for cross-embodiment data, not for the current
  system boundary.

### 3.9 SmolVLA

- **Source:** <https://arxiv.org/abs/2506.01844>;
  <https://github.com/huggingface/lerobot>
- **License:** Apache-2.0 (code, weights and community dataset per the paper
  and LeRobot release).
- **Relevant design:** ~450M-parameter VLA; flow-matching action chunks;
  asynchronous inference (RobotClient + PolicyServer); community datasets at
  30 FPS; six-dimensional state/action and up to three cameras for the SO-100
  setup.
- **Adopt:** the dataset/action requirements (absolute joint positions,
  chunking, 30 FPS community-data convention, camera naming) as inputs to the
  learning-owned dataset contract; asynchronous inference as an M7 design
  consideration.
- **Reject:** training, inference or model storage in teleop. The learning
  repository owns these; teleop only captures and labels.
- **Why:** the target policy family defines what a usable episode must contain,
  not what teleop should implement.

### 3.10 Supporting libraries

| Library | Use | License | Decision |
|---|---|---|---|
| ROS 2 Jazzy / `rclpy` | M2 node (default) | Apache-2.0 | Adopt in the thin wrapper; test in `ros:jazzy` |
| ROS 2 Humble build | ArmPi compatibility only | Apache-2.0 | Keep the existing `ros:humble` build record; not CI-default |
| CycloneDDS | System RMW | EPL-2.0 / EDL | System-provided; no vendoring |
| `sensor_msgs`, `geometry_msgs` | M2 wire types | Apache-2.0 | Adopt via ROS |
| PyYAML | Profile/binding parsing | MIT | Adopt in core (already ecosystem-standard) |
| pytest | Tests | MIT | Adopt as a test dependency |
| NumPy | Optional numeric helpers | BSD-3-Clause | Not required in M1; avoid in the control core |
| `jsonschema` | Optional schema tests | MIT | Test-only if needed; not a runtime dependency |
| `joy` (ROS 2) | Operator-side gamepad driver | BSD | Operator-side only; not a dependency of this repo |
| `pygame`/`evdev`/`hidapi` | Device access | LGPL/MIT/BSD variants | Rejected in this repo; operator-side only |
| LeRobot | Dataset/training | Apache-2.0 | Learning-owned; not a teleop runtime dependency |
| MoveIt Servo | Cartesian servo | BSD-3-Clause | Rejected as runtime; design reference only |
| MCAP / rosbag2 | Recording | Apache-2.0 | Rejected for M3 capture; JSONL + sidecar is smaller and replayable |

### 3.11 Comparison matrix

| System | Input adaptation | Action space | Control rate | Data collection | Safety boundary | Multi-robot |
|---|---|---|---|---|---|---|
| LeRobot | Leader arms, gamepad, keyboard; `Teleoperator` lifecycle | Flat action dict; joint positions or deltas; gripper enum | Dataset-FPS-driven; commonly 30 FPS | Dataset v3.0, episode metadata, LeRobot Hub | No lease/arbiter; record loop and device limits | Per-device classes/configs; one robot per process |
| `teleop_twist_joy` | Joy axes/buttons; hold-to-run enable | Base linear/angular twist | No rate limiting | None | Enable button only; publishes `cmd_vel` | Base robots only |
| MoveIt Servo | JointJog, TwistStamped, PoseStamped; switch service | Joint velocity, Cartesian twist, pose | `publish_period` default 0.01 s (100 Hz) | None | Collision/singularity scaling, command timeout, pause/status; no lease | One MoveIt robot model per node |
| ALOHA | Bimanual leader arms | Absolute joint positions (14-DoF) + gripper | ~50 Hz | Teleoperation + ACT dataset | No formal lease; operator holds leader | Fixed dual-arm hardware |
| Mobile ALOHA | Leader arms + tethered base | Joint positions + base motion | ~50 Hz teleoperation | Whole-body demonstrations | No formal lease; physical tether | Fixed mobile dual-arm |
| Open-TeleVision | VR head/hand tracking; retargeting | Relative EE position + absolute orientation; hand | ~60 Hz stereo/control | Teleoperation + ACT-style data | CLIK, no lease/arbiter; headset and network | Humanoid-specific; retargeting config |
| GELLO | Kinematically equivalent leader arm | Absolute joint positions | Device-dependent | Demonstration collection | No formal lease; leader hardware | Per-robot leader build |
| UMI | Handheld gripper | Relative trajectory; latency-matched policy interface | Device-dependent | In-the-wild demonstrations | No formal lease; handheld device | Cross-embodiment policy interface |
| SmolVLA | Policy, not a teleoperator | Action chunks (flow matching) | Async inference; 30 FPS community data | LeRobot community datasets | No safety layer; policy server only | Multi-robot via dataset/embodiment configs |

The matrix is deliberately about **mechanisms**, not endorsement. The JCHENG
design borrows the lifecycle, hold-to-run, typed command modes, joint-position
mapping and relative-action ideas, while keeping lease/arbiter/safety in the
system layer and the device boundary operator-side.

## 4. Dependency plan

| Milestone | Runtime dependencies | Test/CI dependencies | Deliberately absent |
|---|---|---|---|
| M1 | Python stdlib, PyYAML | pytest, PyYAML | ROS, numpy, pydantic, device libraries |
| M2 | Python stdlib, PyYAML, `rclpy`, `jcheng_interfaces` (Jazzy) | pytest, `ros:jazzy` container, system mock | MoveIt Servo, LeRobot, torch, device libraries |
| M3 | M2 + filesystem/JSONL | pytest | pyarrow, LeRobot, torch |
| M4 | M2 + stdlib replay | pytest, benchmark CLI (optional) | LeRobot/torch in teleop; learning owns export |
| M5 | M2 + studio HTTP/WS client (studio side) | studio tests, Playwright | DDS in studio, device access |
| M6 | M2 + operator-side adapter (not in repo) | supervised session tooling | device drivers, vendor SDK in repo |

Rules:

- Pin every runtime version and hash in the release lock; no floating `latest`.
- No vendored code, no copied vendor headers, no model weights in git.
- The core must remain importable and testable on a host with no ROS.
- The ROS wrapper is thin: it translates messages and delegates to the core.
- A new dependency needs a named problem, a license check, a maintenance
  check, a size/attack-surface note and a removal plan.

## 5. Licenses and the open review

All candidates above are permissive (Apache-2.0, MIT, BSD). The ecosystem has
**no `LICENSE` file** in this repository until the organization review closes.
That means:

- adopting **ideas** is fine;
- copying **code** is not approved, even from a permissive project, until the
  review and copyright holder are settled;
- a future `THIRD_PARTY_NOTICES.md` is required if any code or notices are
  incorporated;
- the operator-side adapter and capture data carry their own licenses and are
  not distributed here.

## 6. Rejected heavy or misplaced dependencies

| Candidate | Why rejected |
|---|---|
| MoveIt 2 / Servo as a runtime | Would own motion and kinematics inside L3; violates the gateway/lease/arbiter boundary; heavy ROS/MoveIt dependency |
| LeRobot / PyTorch in teleop | Duplicates learning; large GPU stack; device I/O in the same package |
| Open-TeleVision / Vuer / VR stack | Requires a headset/web stack; IK in teleop; not needed for M1–M2 |
| ALOHA / GELLO hardware stacks | Vendor-specific Dynamixel code; operator-side hardware |
| `teleop_twist_joy` | Base `cmd_vel` only; no arm/gripper/lease; no rate limiting |
| `pygame`/`evdev`/`hidapi`/SDL | Device access forbidden by the capability manifest; operator-side only |
| MCAP/rosbag2 | Larger storage/decoder surface; capture is a controlled JSONL package, and recordings stay outside git |
| Pydantic/FastAPI | Useful in studio, not in the deterministic core; adds a validation/runtime dependency |
| ZeroMQ/nanomsg | A second transport beside HTTP and DDS; no ecosystem need |
| Pinocchio/KDL | IK belongs to the system/robot model, not teleop; Cartesian is reserved |
| pandas/pyarrow in teleop | Dataset conversion is learning-owned; avoid a data-science stack in the control path |

## 7. Open dependency decisions

- Whether M1 uses PyYAML only or a small schema validator; the current gate
  avoids `jsonschema` at runtime.
- Whether the M2 DDS adapter uses `rclpy` in the same process as the core or a
  separate process with a local transport; the former is simpler, the latter
  isolates ROS failures.
- Whether the operator-side gamepad adapter is a separate repository/package;
  it cannot live here under `hardware_access: none`.
- Whether the learning adapter runs in learning (preferred) or ships as a
  teleop extra after the dataset contract is frozen.
- The exact ROS 2 Jazzy pin for the M2 container and the `rclpy` version; the
  ArmPi robot runtime remains Humble for the vendor stack.

## 8. Sources

- LeRobot: <https://github.com/huggingface/lerobot> (Apache-2.0; `Teleoperator`
  base, dataset v3.0 docs at <https://huggingface.co/docs/lerobot/lerobot-dataset-v3>).
- `teleop_twist_joy`: <https://github.com/ros2/teleop_twist_joy> (2.6.5, BSD;
  README and `package.xml`).
- MoveIt Servo: <https://moveit.picknik.ai/main/doc/examples/realtime_servo/realtime_servo_tutorial.html>
  and <https://github.com/moveit/moveit2> (BSD-3-Clause).
- ALOHA: <https://github.com/tonyzhaozh/aloha> (MIT);
  <https://arxiv.org/abs/2304.13705>.
- Mobile ALOHA: <https://github.com/MarkFzp/mobile-aloha> (MIT);
  <https://arxiv.org/abs/2401.02117>.
- Open-TeleVision: <https://github.com/OpenTeleVision/TeleVision>
  (Apache-2.0); <https://arxiv.org/abs/2407.01512>.
- GELLO: <https://github.com/wuphilipp/gello_software> (MIT);
  <https://arxiv.org/abs/2309.13037>.
- UMI: <https://github.com/real-stanford/universal_manipulation_interface>
  (MIT); <https://arxiv.org/abs/2402.10329>.
- SmolVLA: <https://arxiv.org/abs/2506.01844>;
  <https://github.com/huggingface/lerobot> (Apache-2.0).

## 9. Related

- [Architecture](ARCHITECTURE.md)
- [Teleop core](TELEOP_CORE.md)
- [Safety model](SAFETY_MODEL.md)
- [Data collection](DATA_COLLECTION.md)
- [Integration contract](INTEGRATION_CONTRACT.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-learning`](https://github.com/JCHENG-Robotics/jcheng-learning)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
