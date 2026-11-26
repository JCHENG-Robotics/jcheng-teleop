# Teleop core — jcheng-teleop

> Status: **Implemented for M1** as of 2026-11-26. The core is ROS-free,
> deterministic and device-free; it does not publish, record or command
> hardware. M2+ sections remain proposed.

## 1. Purpose and boundary

The core is the single semantic layer between an operator-side input adapter
and the system-layer gateway/intake. It owns:

- input validation and conditioning;
- action mapping for the supported control modes;
- the session state machine and mode changes;
- the deadman, watchdog and local limit guard;
- the typed intent and event model;
- a deterministic tick that can be replayed.

It does **not** own:

- the input device or its OS driver;
- the robot profile or its limits (it resolves and references them);
- the lease (the system grants it);
- motion execution, arbitration or the safety supervisor;
- episode storage or the dataset schema.

## 2. M1 package tree

The M1 tree is a proposal; M1 may rename files, but the module boundaries and
invariants are fixed.

```text
src/jcheng_teleop/
├── core/
│   ├── model.py          # typed samples, intents, events, errors
│   ├── clock.py          # injected monotonic clock; no wall-clock in logic
│   ├── conditioning.py   # validation, deadzone, scaling, bounds, rate
│   ├── deadman.py        # enable edge, release, timeout state machine
│   ├── mapper.py         # joint position/velocity mapping; Cartesian reserved
│   ├── profile.py        # canonical profile + teleop binding resolver
│   ├── session.py        # core session lifecycle and mode changes
│   ├── safety.py         # local guard, limit events, fault latch
│   ├── gateway.py        # GatewayPort protocol + result types
│   └── runner.py         # deterministic tick loop; no blocking I/O
├── adapters/
│   ├── input/
│   │   ├── virtual.py    # scripted samples
│   │   ├── keyboard.py   # stdin/terminal events; no /dev/input
│   │   ├── jsonl.py      # newline-delimited sample transport
│   │   ├── gamepad.py    # normalized JoyFrame -> InputSample; injected source
│   │   └── replay.py     # capture -> samples (M4; reserved in M1)
│   └── gateway/
│       └── mock.py       # in-process lease/state/submit/stop fake
├── cli.py                # `python -m jcheng_teleop ...`
└── __init__.py
tests/
├── test_model.py
├── test_conditioning.py
├── test_deadman.py
├── test_mapper.py
├── test_profile.py
├── test_session.py
├── test_safety.py
├── test_runner_determinism.py
├── test_mock_gateway.py
└── test_no_hardware.py
```

`pyproject.toml` or `setup.cfg` is added at M1; no ROS dependency is allowed in
`src/jcheng_teleop/core` or `adapters/input`.

## 3. Typed model

The names are normative for M1; the serialization is versioned.

```python
# All times are integer nanoseconds. All floats are finite; NaN/Inf is invalid.
class Mode(str, Enum):
    JOINT_POSITION = "JOINT_POSITION"
    JOINT_VELOCITY = "JOINT_VELOCITY"
    CARTESIAN_TWIST = "CARTESIAN_TWIST"   # internal; wire string CARTESIAN_VELOCITY
    # Gripper is an orthogonal field, not a mode.

@dataclass(frozen=True)
class InputSample:
    schema: str                  # jcheng.teleop.input.v1
    source_id: str               # adapter identity, stable per process
    source_class: str            # keyboard|gamepad|leader_arm|jsonl|virtual|studio
    seq: int                     # strictly increasing per session
    t_source_ns: int             # adapter clock at capture
    t_host_mono_ns: int          # host monotonic clock at receipt
    mode: Mode
    joint_positions_rad: tuple[float, ...] = ()
    joint_velocities_rad_s: tuple[float, ...] = ()
    cartesian_twist: CartesianTwist | None = None
    gripper_normalized: float | None = None   # 0 closed .. 1 open
    deadman: bool = False
    calibration_id: str | None = None
    profile_id: str | None = None
    session_hint: str | None = None

@dataclass(frozen=True)
class ActionIntent:
    mode: Mode
    profile_id: str
    profile_hash: str
    deadman: bool
    t_source_ns: int             # source sample stamp
    seq: int                     # wire sequence assigned per submit
    joint_positions_rad: tuple[float, ...] = ()
    joint_velocities_rad_s: tuple[float, ...] = ()
    cartesian_twist: CartesianTwist | None = None
    gripper_normalized: float | None = None
    gripper_valid: bool = False
    frame_id: str = ""           # required for Cartesian; empty for joint
    lease_id: str = ""           # active lease, attached by the session
    purpose: str = "motion"      # motion | stop

@dataclass(frozen=True)
class TeleopEvent:
    code: str                    # local event code, see SAFETY_MODEL.md
    severity: str                # info|warning|fault
    at_ns: int
    detail: dict[str, object]
```

### 3.1 Input sample invariants

1. `seq` increases strictly within a session; the core never reorders or
   repairs a gap.
2. `t_source_ns` is monotonic non-decreasing; a rollback is rejected.
3. A sample carries exactly one **arm** mode payload; the other arm payloads
   are empty (or `None`). Both arm payloads populated is invalid. The gripper
   is an orthogonal field and may accompany any arm mode (`gripper_valid`).
4. Joint vectors have exactly the profile's arm-joint count; the gripper is a
   separate normalized value.
5. Every float is finite. A non-finite value is rejected, counted, and stops
   the active session (fail closed); it cannot be retried as motion.
6. `deadman` is the operator's held enable input. It is not a safety-rated
   signal and does not replace the system's stop latch.
7. `t_host_mono_ns` is used for watchdog and ordering; `t_source_ns` is kept
   for provenance and replay. They are never mixed silently.

## 4. Input adapters

All adapters implement the same protocol. They are device-free unless an
operator-side process feeds them.

```python
class InputSource(Protocol):
    def open(self) -> None: ...
    def poll(self, now_ns: int) -> InputSample | None: ...
    def close(self) -> None: ...
    @property
    def health(self) -> InputHealth: ...
```

| Adapter | Device access in this repo | Source | Maturity |
|---|---|---|---|
| `VirtualInputSource` | none | Scripted samples with timestamps | M1 |
| `KeyboardInputSource` | none; reads stdin/terminal key events | Operator keyboard focus | M1 |
| `JsonlInputSource` | none | Newline JSON from an operator-side bridge over stdin or a local Unix socket | M1 |
| `GamepadInputSource` | none; consumes `JoyFrame` | Injected `JoySource`; a real source is operator-side | M1 semantics, real adapter operator-side |
| `LeaderArmInputSource` | none | JSONL absolute joint positions + enable | M6 |
| `StudioInputSource` | none | Local studio bridge samples | M5, reserved |
| `ReplayInputSource` | none | Sealed capture | M4, reserved |

Rules:

- An adapter failure is a sample gap, never a synthetic sample.
- Keyboard focus loss, gamepad disconnect and leader-arm unplug stop the
  sample stream; the deadman/watchdog handles the gap. An explicit adapter
  health event is M2.
- The adapter normalizes raw units to SI once and records the conversion with
  `source_id`. The core does not guess device units.
- The repository does not ship a gamepad driver, `evdev`, `hidapi`, SDL,
  `pygame`, a vendor SDK or a serial reader. A real gamepad/leader arm requires
  an operator-side process and a boundary review; see
  [INPUT.md](INPUT.md).

## 5. Conditioning pipeline

The order is fixed; each stage is a pure function with a typed result.

```text
validate schema and finiteness
  → check seq/timestamp ordering
  → deadzone with hysteresis per axis
  → normalize/scale exactly once
  → per-axis absolute bound
  → rate limit (fixed period, no catch-up)
  → mode-specific validity
  → emit ConditionedSample or a typed rejection
```

### 5.1 Deadzone and hysteresis

Each axis has `deadzone` and `hysteresis` from the binding. Inside the
deadzone the output is exactly zero. Hysteresis prevents chatter at the edge.
The deadzone applies to the operator input, not to the profile limit.

### 5.2 Scaling and units

- Joint velocity: rad/s.
- Joint position: rad for revolute joints; the profile may declare a prismatic
  arm joint, but the current arm profiles do not.
- Gripper: normalized 0.0 (closed) to 1.0 (open) internally; the profile maps
  to radians (ArmPi) or metres (PiPER X).
- Cartesian twist: m/s and rad/s in the profile workspace frame (`base_link`
  for the current ArmPi profile). Cartesian is reserved and not enabled.
- The adapter's raw-to-SI conversion is recorded; the core never applies a
  second scale factor.

### 5.3 Bounds and rate

- Per-axis bound is `min(profile limit × mode scale, session scale)`.
- An over-limit request is **clamped** to the bound and emits exactly one
  `LIMIT_CLAMPED` event per axis per continuous saturation episode, with the
  requested and applied values.
- The rate limiter uses a fixed tick period. It never emits a burst to catch
  up and never shortens the period. If the loop is late, it emits at most one
  sample for the current tick and records `LOOP_OVERRUN`.
- The stop path bypasses smoothing and rate limiting: it emits zero
  immediately.

### 5.4 Rejected samples

| Condition | Result |
|---|---|
| Non-finite value | `SAMPLE_INVALID`; no intent |
| Wrong vector length | `SAMPLE_INVALID`; no intent |
| Both mode payloads set | `SAMPLE_INVALID`; no intent |
| `seq` not strictly increasing | `SEQ_GAP`/`SEQ_DUPLICATE`; no intent |
| `t_source_ns` rollback | `STAMP_ROLLBACK`; no intent |
| Unknown mode | `MODE_UNSUPPORTED`; no intent |
| Mode without required calibration | `CALIBRATION_REQUIRED`; no intent |

Rejections are counted and recorded; the core does not silently drop them.

## 6. Action mapping

### 6.1 Joint velocity

```text
v_out[i] = clamp(scale[i] * input[i], -v_max[i], +v_max[i])
```

`v_max` comes from the resolved profile and the session cap. The output is a
`JOINT_VELOCITY` intent in profile joint order. The system clips again; teleop
does not assume its clip is the final one.

### 6.2 Joint position (leader-style)

```text
q_target[i] = offset[i] + sign[i] * input_position[i]
q_target[i] = clamp(q_target[i], lower[i], upper[i])
```

A position intent is a typed target in profile order. It is **not** converted
to a velocity by teleop: a proportional position-to-velocity loop would be a
motion controller with unanalyzed gains, state-age limits and anti-windup, and
the measured-state path does not exist at the teleop rate today. Without the
v0.2 native `JOINT_POSITION` wire mode, the gateway adapter refuses the intent
with `MODE_UNSUPPORTED`; it does not emulate it.

The core never integrates velocity to invent a target and never treats a
command cache as measurement. M6 may enable position mode only after the v0.2
contract and a bench characterization of state age, gain, saturation and
latency. This is a library-level action type, not a claimed system capability.

### 6.3 Gripper

`gripper_normalized` is mapped by the profile to the actuator range:
`closed_rad`/`open_rad` for ArmPi, `0.0`/`0.1 m` for PiPER X. The wire v0.1
`TeleopCommand` has no gripper field; v0.2 proposes one. M2 may use the
system's `GRIPPER` command for a discrete gripper action, but continuous
gripper teleoperation is not claimed before v0.2.

### 6.4 Cartesian (reserved)

A `CARTESIAN_TWIST` intent carries `frame_id`, linear m/s and angular rad/s.
The core validates the frame against the profile and refuses the mode if the
system cannot accept it. There is no IK, no FK-based workspace check and no
Cartesian claim in M1/M2. `CARTESIAN_POSE` is not planned before M6.

## 7. Profile resolution

```python
@dataclass(frozen=True)
class ResolvedProfile:
    profile_id: str
    profile_hash: str
    profile_source: str                    # system|simulation|fixture
    arm_joint_names: tuple[str, ...]       # canonical order
    arm_joint_lower_rad: tuple[float, ...]
    arm_joint_upper_rad: tuple[float, ...]
    arm_joint_max_velocity_rad_s: tuple[float, ...]
    gripper: GripperBinding | None
    workspace_frame: str
    tip_link: str
    modes: frozenset[Mode]
    binding: TeleopBinding
```

`TeleopBinding` is teleop-local and references the canonical profile; it must
not repeat limits.

```yaml
schema: jcheng.teleop.binding.v1
profile_id: armpi_ultra
profile_hash: "sha256:..."
source_id: operator_gamepad_01
joints:
  - {input: 0, joint: joint1, sign: 1, offset_rad: 0.0, deadzone: 0.05, hysteresis: 0.02}
  - {input: 1, joint: joint2, sign: 1, offset_rad: 0.0, deadzone: 0.05, hysteresis: 0.02}
gripper: {input: 7, closed: 0.0, open: 1.0}
modes: [JOINT_VELOCITY]   # JOINT_POSITION stays disabled until the v0.2 wire
```

Validation rules:

- `profile_id` and `profile_hash` must match the canonical profile and the
  gateway/session hash.
- Every arm joint appears exactly once and in canonical order after mapping.
- `sign` is `+1` or `-1`; offsets/scales are finite and bounded.
- `modes` is a subset of the profile's supported modes; Cartesian requires a
  workspace frame and a system capability.
- The binding is hashed and recorded in every session and capture.

## 8. Session state machine

The detailed transitions, guards and fault responses are in
[SAFETY_MODEL.md](SAFETY_MODEL.md). The core uses these states:

| State | Meaning | May emit intent? |
|---|---|---|
| `BOOT` | Process start; no config loaded | No |
| `SELFTEST` | Config, profile, clock and storage checks | No |
| `IDLE` | Valid config, no lease or not ready | No |
| `READY` | Lease valid, state fresh, deadman released | No (armed but neutral) |
| `ACTIVE` | Fresh enable edge and valid input | Yes |
| `STOPPING` | Stop in progress; one mode-specific stop intent sent | No (except the one stop intent) |
| `FAULT` | Latched local fault; reset required | No |
| `PREEMPTED` | Lease lost to a higher-priority holder | No |

`ACTIVE → STOPPING` is entered on any of: deadman release, input timeout,
lease revocation/expiry/preemption, gateway error, mode-change request, local
watchdog, repeated invalid input, or operator stop. There is no automatic
`STOPPING → ACTIVE` or `FAULT → ACTIVE`; a new enable edge and, for a fault, an
explicit operator reset are required.

## 9. Gateway port

The core depends on a narrow port, not on HTTP or DDS:

```python
class GatewayPort(Protocol):
    def admit(self) -> Admission: ...          # contract, profile, health
    def acquire(self, request: LeaseRequest) -> Lease: ...
    def renew(self, lease_id: str) -> Lease: ...
    def release(self, lease_id: str) -> None: ...
    def state(self) -> RobotStateView: ...     # freshness, truth, positions
    def submit(self, intent: ActionIntent) -> GatewayResult: ...
    def stop(self, reason: str) -> StopResult: ...
```

Rules:

- Lease ownership is explicit. In `managed` mode the teleop process acquires
  and renews a lease on the operator's behalf, with the operator/session in the
  holder string and an operator authorization reference. In `external` mode the
  operator console acquires the lease and teleop only presents it. Hardware
  defaults to `external`; the in-process mock may use `managed`. Teleop never
  self-grants a lease without an operator identity.
- The session attaches its active lease id to every live intent; the mock
  gateway rejects a live `purpose=motion` intent with no active lease and
  requires `deadman=true`. A `purpose=stop` intent has `deadman=false` and may
  be presented without a lease; it uses the system stop/abort path.
- `submit` is called at most once per tick; if the previous result is not
  terminal in the chosen transport, the tick is skipped with `MOTION_BUSY`,
  not queued.
- A transport exception becomes `UNKNOWN`, never a retry.
- `stop` is idempotent from the core's perspective but is sent at most once per
  stop episode; the system may also stop independently.
- The mock port implements the same semantics with a manual clock and a
  scriptable fault list. It is not a system emulator and does not claim to be.
- The HTTP adapter must validate the bare endpoint, require a token from the
  environment, bound the timeout/response size and disable redirects/proxies.
  The DDS adapter, when it exists, joins domain 42 only and uses the system's
  RMW.

## 10. Recorder, replay and dataset ports

These ports keep the core independent of storage and of the learning
repository.

```python
class RecorderPort(Protocol):
    def open_episode(self, meta: EpisodeMeta) -> None: ...
    def append_input(self, row: InputRow) -> None: ...
    def append_action(self, row: ActionRow) -> None: ...
    def append_command(self, row: CommandRow) -> None: ...
    def append_observation(self, row: ObservationRow) -> None: ...
    def append_event(self, row: EventRow) -> None: ...
    def seal(self) -> CaptureRef: ...

class ReplaySource(Protocol):
    def manifest(self) -> CaptureManifest: ...
    def iter_ticks(self) -> Iterator[ReplayTick]: ...

class DatasetPort(Protocol):
    def export(self, capture: CaptureRef, contract: DatasetContract) -> DatasetRef: ...
```

Rules:

- The recorder writer runs off the control path with a bounded queue. A full
  queue is a declared drop plus an event; a required-recording session stops
  motion when the queue cannot drain.
- `seal()` is the only operation that makes a capture immutable; it writes the
  manifest and hashes.
- Replay consumes a sealed capture and cannot open a gateway port.
- The dataset port is implemented by the learning-owned writer or a converter
  that targets the frozen contract; it is not a second schema.
- No port is allowed to raise into the control tick. A port failure is
  converted to a typed event and, where required, a stop.

## 11. Determinism and concurrency

- The core is single-threaded. Input adapters may produce into a bounded queue;
  the core drains at most one sample per tick and records a drop if the queue
  overflows. It never drains a backlog to catch up.
- The clock is injected. Tests use a manual clock; production uses a monotonic
  clock with an explicit source id. Wall time is recorded but never used for
  control decisions.
- The recorder and evidence writer run off the control path. A bounded queue
  and a drop policy are explicit; the stop path does not wait for the writer.
- No filesystem, network, subprocess or device call is allowed in the core tick.
  The CLI runner may poll an operator stop file and call `session.stop` before
  the tick; that is a harness input, not core control logic.
- Given the same input sequence, profile, binding, clock and mock gateway
  script, the emitted action sequence is byte-identical. This is the M1
  determinism acceptance criterion.

## 12. Events and error mapping

Local event codes (teleop telemetry, not a cross-repository contract):

| Code | Meaning |
|---|---|
| `INPUT_OPENED`, `INPUT_STALE`, `INPUT_CLOSED` | Adapter lifecycle |
| `DEADMAN_ENGAGED`, `DEADMAN_RELEASED` | Enable edge transitions |
| `SESSION_READY`, `SESSION_ACTIVE`, `SESSION_STOPPING` | Session lifecycle |
| `SEQ_GAP`, `SEQ_DUPLICATE`, `STAMP_ROLLBACK` | Ordering rejection |
| `SAMPLE_INVALID`, `MODE_UNSUPPORTED`, `CALIBRATION_REQUIRED` | Input validity |
| `LIMIT_CLAMPED`, `RATE_LIMITED_LOCAL` | Local bound/rate events |
| `LEASE_LOST`, `LEASE_PREEMPTED`, `LEASE_EXPIRED` | Lease events |
| `GATEWAY_UNAVAILABLE`, `GATEWAY_UNKNOWN`, `GATEWAY_REJECTED` | Gateway outcomes |
| `RECORDER_DEGRADED`, `RECORDER_FAULT` | Capture health |
| `FAULT_LATCHED`, `FAULT_RESET` | Local latch |

Wire-facing failures use the canonical `jcheng-interfaces` registry where a
code exists (`NO_LEASE`, `LEASE_EXPIRED`, `LEASE_REVOKED`, `STATE_STALE`,
`RATE_LIMITED`, `VELOCITY_LIMIT`, `JOINT_LIMIT`, `SAFETY_STOP_LATCHED`,
`MOTION_BUSY`, `MOTION_OUTCOME_UNKNOWN`, `TIMEOUT`). Codes that do not exist
(`TELEOP_INPUT_STALE`, `TELEOP_DEADMAN`, `TELEOP_SEQ`) are proposed in
[docs/proposals/TELEOP_COMMAND_V0.2.md](proposals/TELEOP_COMMAND_V0.2.md);
until accepted, teleop reports local events and maps wire errors to the
existing registry. It never invents a canonical code in a response.

## 13. Test strategy

| Layer | What is proven |
|---|---|
| L0 | No device/motion tokens; schema/document set; no unapproved interface change |
| L1 | Pure functions: conditioning, mapping, profile validation, deadman, state machine, determinism |
| L2 | In-process mock gateway: lease, submit, stop, fault injection, no retry |
| L3 | System mock + simulation (M2, external) |
| L4 | Replay of sealed captures (M4) |
| L5 | Supervised hardware (M6, separate authorization) |

The M1 test matrix is in [M1_PLAN.md](M1_PLAN.md). Property-style table tests
are preferred over random fuzzing; every failure has a named fixture.

## 14. Related

- [Architecture](ARCHITECTURE.md)
- [Safety model](SAFETY_MODEL.md)
- [Input model](INPUT.md)
- [Data collection](DATA_COLLECTION.md)
- [Integration contract](INTEGRATION_CONTRACT.md)
- [M1 plan](M1_PLAN.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
