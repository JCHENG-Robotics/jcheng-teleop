# Proposal — TeleopCommand v0.2

> Status: **Proposal only**, 2026-11-26. No IDL, JSON Schema, contract hash,
> lock file or consumer is changed by this document. This is a pre-proposal for
> discussion with the `jcheng-interfaces` maintainers and the system owner.

## 1. Context

`jcheng_interfaces/msg/TeleopCommand.msg` v0.1.0 is reserved but not consumed.
It carries:

```text
std_msgs/Header header
uint64 seq
string lease_id
string source
ContractVersion contract
string mode                    # JOINT_VELOCITY | CARTESIAN_VELOCITY
float64[] joint_velocity_rad_s
geometry_msgs/Twist cartesian_velocity
bool deadman
```

The M0 audit found four gaps for the planned teleoperation subsystem:

1. **No joint position.** Leader-follower teleoperation and the learning
   contract's `joint_position_absolute` action cannot be expressed. Converting
   position to velocity inside teleop hides the operator's actual target.
2. **No gripper.** Continuous gripper teleoperation is not expressible; the
   ArmPi `r_joint` and PiPER X prismatic gripper have different units.
3. **No session/episode identity or profile pin.** A sample cannot be tied to a
   session, capture episode, profile hash or source class for provenance.
4. **No mode-conditional payload.** The JSON schema requires both
   `joint_velocity_rad_s` and `cartesian_velocity` regardless of mode, so a
   joint frame carries an empty/irrelevant twist and vice versa.

The current message also has no `idempotency_key` and no explicit expiry; a
high-rate stream does not need per-tick idempotency, but it does need a strict
sequence and host-arrival liveness. A clock-sync bound is optional until one is
measured.

## 2. Decision requested

Add a minor version (0.2.0) of `TeleopCommand` with the fields below, a
mode-conditional JSON schema, and matching error codes for stale/deadman/seq
rejection. The message remains an **intent** stream consumed by the system
layer only; it is never a hardware command.

## 3. Proposed message

```text
# Reserved high-rate teleoperation intent. Consumed by the system teleop
# intake/arbiter only; validated by the same safety path. Not a hardware
# command and not a trajectory.
std_msgs/Header header        # header.stamp = sample source time
uint64 seq                    # strictly increasing per session
string lease_id
string source                 # adapter/capability identity
ContractVersion contract

# JOINT_POSITION | JOINT_VELOCITY | CARTESIAN_VELOCITY
string mode

float64[] joint_positions_rad        # JOINT_POSITION; profile joint order
float64[] joint_velocities_rad_s     # JOINT_VELOCITY; profile joint order
geometry_msgs/Twist cartesian_velocity  # CARTESIAN_VELOCITY; profile frame
float64 gripper_normalized           # 0.0 closed .. 1.0 open
bool gripper_valid                   # true when the frame carries a gripper target
bool deadman

string session_id                    # operator session identity
string episode_id                    # capture episode, empty outside capture
string profile_hash                  # canonical robot profile hash
string source_class                  # human_teleop | human_correction | ...
```

### 3.1 Field rules

- `header.stamp` is the sample source time, not the publish time. It is used
  for latency/provenance; the intake uses host-arrival liveness, `seq` and the
  deadman for safety, and enforces a clock-sync bound only when one is measured.
- `seq` is strictly increasing per `session_id`; rollback and duplicates are
  rejected, never reordered.
- `mode` selects exactly one **arm** payload. The JSON schema uses
  `oneOf`/`if-then` so a joint frame does not require a twist and a twist frame
  does not require joint arrays. The gripper fields are orthogonal and may
  accompany any arm mode.
- `joint_positions_rad`/`joint_velocities_rad_s` length equals the profile's
  arm-joint count and order. Revolute joints are radians; a prismatic arm joint
  would need an explicit unit decision (see open questions).
- `cartesian_velocity` is in the profile workspace frame (`base_link` for the
  ArmPi profile) with linear m/s and angular rad/s. The field is reserved; no
  Cartesian execution is claimed until the system supports it. The wire string
  stays `CARTESIAN_VELOCITY` for v0.1 compatibility; internal code may call the
  type `CartesianTwist`, but v0.2 does not rename the mode.
- `gripper_normalized` is dimensionless; the profile maps it to radians
  (ArmPi `r_joint`, 0..2.22 rad) or metres (PiPER X, 0..0.1 m). The raw
  actuator position is recorded in capture, not on the wire. Gripper is
  orthogonal to `mode`, not a fourth mode; `gripper_valid=false` means this
  frame carries no gripper target.
- `deadman` is the operator's held enable input. It is not an e-stop.
- `session_id`/`episode_id` are opaque identities; they contain no personal
  data.
- `profile_hash` pins the canonical profile. A mismatch rejects the sample.
- `source_class` distinguishes human teleoperation from correction or policy
  execution. A policy should not publish on the teleoperation stream; this
  field exists for capture provenance and future shared autonomy.

## 4. Compatibility and impact

- This is a **minor** change under the 0.y.z policy; it changes the contract
  hash and the ROS 2 type hash.
- There is no current consumer, so the compatibility risk is low today. The
  message is reserved and must be enabled in lockstep with the system intake.
- Consumers to update: `jcheng-system` teleop intake, `jcheng-teleop` gateway
  adapter, `jcheng-learning` dataset mapping (read `joint_positions_rad` and
  `gripper_normalized`), `jcheng-studio` status display (read-only).
- A new `interface_manifest.json`, tag and lock update are required. Do not
  mutate the v0.1.0 tag or its hash.
- The old v0.1.0 message remains readable in history; a mixed deployment with
  v0.1 and v0.2 nodes will fail the type/contract handshake and must not be
  used.

## 5. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| Separate `TeleopPositionCommand.msg` | Fragments the stream and forces the system to arbitrate two teleop types; one mode field is simpler |
| Encode position in `joint_velocity_rad_s` | Abuses units and defeats validation; impossible to tell velocity from position |
| Reuse `MotionCommand` at 50 Hz | It is a discrete command with one active motion and 20/s gateway/arbiter limits; not a stream |
| Put gripper in the joint array | Mixes revolute radians with prismatic metres and bypasses the gripper scope |
| Keep v0.1 and integrate velocity in teleop | Fabricates an absolute target and loses the operator's actual action; unsuitable for learning |

## 6. Verification plan

1. Update `TeleopCommand.msg`, `messages.v1.schema.json` (mode-conditional),
   `interface_manifest.json` and `VERSION`; run the interfaces gate.
2. Add consumer tests in `jcheng-system`: mode validation, joint count/order,
   profile hash, gripper range, seq/stamp, deadman, contract hash.
3. Add producer tests in `jcheng-teleop`: position/velocity/gripper mapping and
   capture fields.
4. Add a learning mapping test: absolute position action and normalized
   gripper become the dataset's canonical fields with the profile mapping.
5. No hardware test is implied by this proposal; hardware remains M6 and
   separately authorized.

## 7. Open questions

- Should the wire carry normalized gripper or profile actuator units? This
  proposal uses normalized; the profile owns the conversion.
- Is `source_class` needed on every tick, or only at session start? Per-tick is
  simpler for capture but adds bytes; 50 Hz × ~30 bytes is negligible.
- Should `episode_id` be on the wire or supplied out-of-band by the recorder?
  On-wire makes provenance exact; out-of-band avoids coupling recording to
  control.
- Does the system intake need `operator_id` for audit, or is `session_id`
  sufficient with the gateway lease holder?
- Cartesian frame: `base_link` only, or a configurable frame with a TF check?
- Should `deadman_ms`/acceptance window be fields or profile/intake config?
  This proposal keeps them in config to avoid a per-tick payload.
- Does a future bimanual arm need a joint-group dimension, or one stream per
  arm? One stream per arm is simpler and preserves scopes.

## 8. Related

- [Integration contract](../INTEGRATION_CONTRACT.md)
- [Teleop core](../TELEOP_CORE.md)
- [Safety model](../SAFETY_MODEL.md)
- [Data collection](../DATA_COLLECTION.md)
- [`TeleopCommand.msg`](https://github.com/JCHENG-Robotics/jcheng-interfaces/blob/main/ros2_ws/src/jcheng_interfaces/msg/TeleopCommand.msg)
- [`jcheng-interfaces` contract rules](https://github.com/JCHENG-Robotics/jcheng-interfaces/blob/main/docs/CONTRACT.md)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
