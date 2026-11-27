# M6 plan — leader-arm and supervised hardware teleoperation

> Status: **Blocked for hardware; offline prerequisites implemented**,
> 2026-11-26. No robot motion, no device and no DDS were used for this slice.
> The authorization/preflight gate is ready; the streaming and stop-confirmation
> prerequisites are not.

## 1. What exists now

| Piece | State |
|---|---|
| Input contract for absolute leader positions | Core `InputSample` already types `JOINT_POSITION`; the operator-side leader adapter emits it and the JSONL transport carries it. No leader device is opened in this repo. |
| Supervised authorization record | Implemented: `jcheng.teleop.authorization.v1` (`src/jcheng_teleop/supervised/authorization.py`) |
| Offline preflight | Implemented: `jcheng-teleop-preflight` validates the record against the profile/contract and reports blockers; it never contacts the system |
| Position/gripper wire intent | **Missing**: `TeleopCommand` v0.1 carries velocity only (P-001/B3) |
| System streaming executor | **Missing**: `jcheng_vendor` serializes one joint per `JOINT_STEP`; the read-only probe found the vendor `ServosPosition` multi-servo vector, but no privileged bridge and no measured rate/interpolation (B2) |
| Stop confirmation | **Missing**: `StopResult` has no confirmation field (R5/B9) |
| PiPER X canonical profile | **Missing**: `robot-profile.v1` cannot express a CAN arm (B4) |
| e-stop / brake / encoder | **None on the platform**; the software stop is not an e-stop |

`hardware_ready` is always false in a preflight report until the missing rows
above are closed. A passing authorization is necessary, not sufficient.

## 2. Authorization record `jcheng.teleop.authorization.v1`

```yaml
schema: jcheng.teleop.authorization.v1
session_id: m6-armpi-20261126-01
operator_id: operator-name
supervisor_id: supervisor-name
authorization_ref: signed-ticket-or-operator-log-reference
workspace_clear: true
checklist_hash: "sha256:<hash of the executed checklist>"
profile_id: armpi_ultra
profile_hash: "sha256:<system profile hash>"
contract_hash: "sha256:<pinned interfaces contract>"
joint_names: [joint1, joint2, joint3, joint4, joint5]
motion_scope: [joint1]
max_velocity_rad_s: 0.2
issued_at: "2026-11-26T10:00:00+08:00"
expires_at: "2026-11-26T12:00:00+08:00"
notes: low-speed single-joint supervised session
```

Rules enforced (`validate`):

- schema, session, operator, supervisor, authorization ref and checklist hash;
- `operator_id != supervisor_id`; `workspace_clear` must be true;
- profile id/hash and contract hash must match the supplied profile and pin;
- `joint_names` must equal the profile joint order exactly (order is safety
  relevant, not cosmetic);
- `motion_scope` non-empty, subset of the profile joints, no duplicates;
- `max_velocity_rad_s` finite, positive and not above the profile limit for the
  authorized joints;
- timezone-aware `issued_at`/`expires_at`, `expires_at > issued_at`, window
  ≤ 8 h, and `issued_at <= now < expires_at`.

A per-session authorization is never reused; each motion session needs its own
record (AGENTS.md hardware rule).

## 3. Offline preflight

```bash
PYTHONPATH=src python3 -m jcheng_teleop.supervised.cli \
  --authorization authorization.yaml \
  --profile examples/armpi_ultra_demo/profile.yaml \
  --binding examples/armpi_ultra_demo/binding.yaml \
  --contract-hash sha256:0b8d72ced7f54d444d6851d8b99a51a78e2bed3f687324f51a15f76557f24b42 \
  --now 2026-11-26T11:00:00+08:00
```

Exit codes: 0 authorized (hardware still blocked), 1 refused, 2 config error.
The JSON report contains the authorization hash, the session summary and the
blocker list; it is evidence for the paperwork, not for motion.

## 4. Session runbook (not executed)

1. Operator and supervisor agree the scope; write the authorization record.
2. Run preflight; a refusal stops the session.
3. Close the remaining blockers (wire v0.2, streaming executor, stop
   confirmation). Do not start otherwise.
4. Authorize the system session (`ArmSystem`), acquire a priority-40 arm lease,
   verify measured state, then run at the authorized velocity scope.
5. Test the stop path first: deadman release within one tick, system abort
   within 300 ms, and a bus read back of the stopped joints when the
   confirmation field exists.
6. Record: authorization hash, lease ref, profile/contract hashes, latency and
   tracking distributions, stop outcome (`confirmed` or `unknown`), and the
   explicit statement that no e-stop exists.

## 5. M6 acceptance mapping

| Acceptance item | State |
|---|---|
| Separate per-session authorization with operator, supervisor, checklist, hashes and scope | **Implemented offline** |
| Joint order/sign/limits validated; mismatch refuses the session | **Implemented** (order/scope/velocity); sign is binding-owned and tested in M1 |
| No motion before enable, after lease loss or after a latch | Existing M1/M2 core tests; **not revalidated on hardware** |
| Deadman stop within one tick, system abort ≤300 ms, bus-read confirmation | Core/M2 mock only; **hardware/confirmation blocked** |
| Tracking/latency distributions with numeric bounds | **Not started** (needs hardware) |
| No e-stop statement | Recorded in the plan and reports |

## 6. Non-goals

Unattended motion, e-stop claims, Cartesian teleoperation, force feedback,
self-collision avoidance, industrial certification, PiPER X hardware.

## 7. Related proposals

- `TeleopCommand` v0.2: [TELEOP_COMMAND_V0.2.md](proposals/TELEOP_COMMAND_V0.2.md)
- System streaming executor (B2):
  [`jcheng-system/docs/proposals/STREAMING-EXECUTOR.md`](https://github.com/JCHENG-Robotics/jcheng-system/blob/main/docs/proposals/STREAMING-EXECUTOR.md)
- Stop-confirmation levels (R5/B9):
  [`stop-confirmation-levels.md`](https://github.com/JCHENG-Robotics/jcheng-interfaces/blob/main/docs/proposals/stop-confirmation-levels.md)
