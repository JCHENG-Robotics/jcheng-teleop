# M6 blocker proposals (offline)

> Status: **Proposal only**, 2026-11-26. No code, IDL, contract hash, device or
> hardware session is changed by this record.

Two documents close the design gap between the implemented offline preflight
and a future supervised hardware session:

| Blocker | Proposal | Owner |
|---|---|---|
| B2: the vendor executor accepts one-joint `JOINT_STEP` at ~5/s and cannot stream a 5-joint loop | [`jcheng-system/docs/proposals/STREAMING-EXECUTOR.md`](https://github.com/JCHENG-Robotics/jcheng-system/blob/main/docs/proposals/STREAMING-EXECUTOR.md) | `jcheng-system` |
| B3: the wire carries velocity only; leader/position intent and gripper cannot be expressed | [`docs/proposals/TELEOP_COMMAND_V0.2.md`](../../docs/proposals/TELEOP_COMMAND_V0.2.md) (M6 enablement checklist added) | `jcheng-interfaces` + teleop |
| R5/B9: no stop confirmation | [`jcheng-interfaces/docs/proposals/stop-confirmation-levels.md`](https://github.com/JCHENG-Robotics/jcheng-interfaces/blob/main/docs/proposals/stop-confirmation-levels.md) (existing) | `jcheng-interfaces` + system |

The streaming proposal deliberately offers three outcomes: a privileged
multi-joint stream, a reduced single-joint M6 scope, or an explicit
vendor-stack block. The first task it defines is a **read-only capability
probe** of `~/ArmPiUltra/` and the vendor container; a negative result is a
valid outcome and is preferable to emulating a stream with rapid single-joint
steps.

## State

- Offline authorization + preflight: implemented and tested (17 tests).
- `hardware_ready` remains false; the preflight report lists every blocker.
- No hardware probe, no servo write, no motion was performed.
- M6 stays In progress; it cannot exit until the chosen streaming option and
  the wire/stop-confirmation changes are reviewed and implemented.

## Next

1. Operator decision on the streaming option (proposal §2).
2. If option 1/2: read-only vendor capability probe with evidence.
3. Interface proposal review for `TeleopCommand` v0.2 and stop confirmation.
4. Only then a separately authorized, low-speed hardware session.
