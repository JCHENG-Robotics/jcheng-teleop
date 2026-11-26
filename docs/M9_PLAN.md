# M9 plan — mobile manipulation teleoperation (offline interface design)

> Status: **Offline interface design**, 2026-11-26. No DDS node, no `/cmd_vel`,
> no device and no hardware motion. `jcheng-mobile` still owns the base intent;
> the coordinated contract does not exist yet.

## 1. Authority model

| Layer | Owns | Never does |
|---|---|---|
| `jcheng-teleop` | Bounded operator **base intent** (velocity, deadman, lease ref) and arm intent | Publish `/cmd_vel`, open a motor device, bypass the mobile layer |
| `jcheng-mobile` | `/cmd_vel` intent, Nav2, base limits (0.25 m/s forward, 0.20 lateral, 0.60 rad/s yaw), 500 ms deadman | Accept a second base-intent owner while Nav2 is driving |
| `jcheng-system` | Lease grant, arbiter, hardware duty cap (duty 60 ≈ 0.33 m/s), stop latch, bus truth | Depend on an L3 node at runtime |

Teleop publishes **zero** `/cmd_vel` messages. The base intent is a new
capability-plane stream that mobile consumes and arbitrates; mobile remains the
only `/cmd_vel` publisher.

## 2. Proposed base intent contract (pre-proposal, no file changed)

A new `BaseTeleopCommand.msg` (name provisional) on domain 42:

```text
std_msgs/Header header        # sample source time
uint64 seq                    # strictly increasing per session
string lease_id               # base-scope lease, operator-supplied
string session_id
string source
ContractVersion contract
float64 vx_m_s
float64 vy_m_s
float64 wz_rad_s
bool deadman
string frame                  # base_link
string source_class           # human_teleop | human_correction | ...
```

Rules:

- `vx/vy/wz` are bounded by the mobile limits above; the mobile layer clamps
  and the system hardware cap still applies.
- A non-zero intent requires `deadman=true`, a live base lease and an input age
  ≤500 ms; zero velocity with `deadman=false` is a stop.
- `seq` strictly increases per session; rollback/duplicate is rejected.
- Separate from the arm stream: separate rate (≤20 Hz), separate lease scope,
  separate stop. A single combined message is rejected because an arm stop must
  not implicitly stop the base and vice versa.
- The intent is not a motor command; mobile converts it to `/cmd_vel` after its
  own mode/limit checks.

The offline guard for this contract is implemented in
`src/jcheng_teleop/core/base.py` (limits, deadman, lease presence, sequence,
input age, 20 Hz bound). It is early feedback, not authority.

## 3. Mode arbitration with Nav2

- Mobile has one base-intent authority at a time: `NAV2` or `OPERATOR`.
- Entering operator mode requires a live base lease and an explicit operator
  action; a Nav2 goal is rejected while operator mode is active, and operator
  intent is rejected while Nav2 is executing. A handover emits an event.
- The operator cannot drive while a Nav2 goal is active, and an autonomous
  goal cannot preempt operator mode without an explicit handover.
- Loss of the base intent for 500 ms → mobile publishes zero `/cmd_vel`; a
  system stop latches independently.

## 4. Stops

Three separate paths:

| Stop | Path | Bound |
|---|---|---|
| Arm stop | Teleop stop intent → system intake → arbiter latch | ≤300 ms (M2/M6 path) |
| Base stop | Zero base intent + deadman=false → mobile → zero `/cmd_vel` | ≤500 ms (mobile deadman) |
| Coordinated stop | Operator action stops both; each path reports its own result | ≤300 ms target for the arm, ≤500 ms for the base; the report names the scope |

There is no atomic cross-layer stop. A coordinated stop is only a claim if both
paths report their own outcome; the system software stop latch remains the
authority. The platform has no e-stop, brake or encoder; a base stop is not
proven without the system's base evidence.

## 5. Mobile manipulation task (simulation first)

1. Drive to a staging pose in Nav2 mode.
2. Hand over to operator mode; drive the base at ≤0.1 m/s inside the staging
   area while the arm is idle.
3. Arm teleoperation (M6) with the base stationary; a base motion request while
   the arm is moving is refused unless the coordinated scope is explicit.
4. Coordinated move: base creep + arm hold; any deadman release stops the
   active scope.
5. Return to Nav2 mode and a parking goal.

No hardware claim until the base motor power blocker (0 mV battery sag at duty
40) and a supervised session are resolved.

## 6. Acceptance mapping

| Item | State |
|---|---|
| Separate base/arm scopes or explicit coordinated scope; no `/cmd_vel` from teleop | Designed; contract not implemented; teleop publishes no `/cmd_vel` today |
| Base stop, arm stop, coordinated stop tested | **Not started**; only the offline base guard is tested |
| One mobile manipulation task in simulation | **Not started**; mobile/simulation coordinated plant not wired |
| Base teleoperation not claimed before mobile contract/evidence | **Honored**: this is a design document only |

## 7. Non-goals

Teleop owning `/cmd_vel`, bypassing Nav2, outdoor autonomy, certified
industrial safety, hardware base motion in this slice.

## 8. Blockers

- No `BaseTeleopCommand` contract in `jcheng-interfaces`; mobile has no
  operator base-intent subscriber or mode arbitration.
- No lease-check path in mobile for a base-scope lease (L3→L2 client allowed,
  not implemented).
- No coordinated mobile plant in `jcheng-simulation`; Nav2 is on the robot
  stack, not in the offline plant.
- Base motor power blocker (no motion at duty 40), no encoders/IMU, no e-stop.
- M6 remains blocked, so arm+base coordinated work cannot be demonstrated on
  hardware.
