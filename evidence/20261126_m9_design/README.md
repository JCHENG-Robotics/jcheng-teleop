# M9 mobile teleoperation — offline interface design

> Status: **Partially verified (offline guard only, 2026-11-26)**. No DDS node,
> no `/cmd_vel`, no device, no simulation task and no hardware motion.

## Implemented

`src/jcheng_teleop/core/base.py`: `jcheng.teleop.base_intent.v1` with an
offline guard mirroring the mobile limits:

| Check | Bound |
|---|---|
| Forward velocity | 0.25 m/s |
| Lateral velocity | 0.20 m/s |
| Yaw rate | 0.60 rad/s |
| Input age | ≤500 ms |
| Rate | ≤20 Hz |
| Deadman | required for non-zero motion |
| Lease | required (base scope) |
| Sequence | strictly increasing |
| Frame | `base_link` |

The guard is early feedback, not authority: `jcheng-mobile` owns `/cmd_vel`
and re-applies its limits; `jcheng-system` owns the hardware duty cap, lease,
stop latch and bus truth. Teleop publishes **zero** `/cmd_vel` messages.

## Tests

`python3 -m pytest -q tests/test_base_intent.py` — **14 passed**. Full suite:
**202 passed**; gate OK.

Covered: valid forward intent and state update; zero intent is a stop without a
deadman; non-zero needs a deadman; forward/lateral/yaw limits; stale and future
timestamps; sequence rollback; missing lease; >20 Hz; wrong frame; non-finite
values; a rejected intent does not advance state.

## Design record

`docs/M9_PLAN.md`:

- authority table (teleop intent / mobile `/cmd_vel` / system hardware),
- proposed `BaseTeleopCommand` fields (pre-proposal; no IDL change),
- Nav2 ↔ operator mode arbitration and handover,
- three stop paths (arm ≤300 ms, base ≤500 ms, coordinated reports each scope),
- a simulation-first mobile manipulation task and its blockers.

## Limits

- No contract: `BaseTeleopCommand` does not exist in `jcheng-interfaces`.
- No mobile operator-base subscriber, no mode arbitration, no lease check.
- No coordinated mobile plant; Nav2 lives on the robot stack.
- No simulation task and no hardware base motion; the base motor power blocker
  (0 mV sag at duty 40) and no-e-stop limitation remain.
- M6 is blocked, so arm+base coordinated work cannot be demonstrated yet.
