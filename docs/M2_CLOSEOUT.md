# M2 closeout — transport, governance and remaining gaps

> Status: **In progress (not Complete)**, 2026-11-26. The test-only transport
> works end to end; the production lease adapter, `TeleopState` and the
> capability-class governance change are missing.

## 1. What M2 delivered

| Piece | Evidence |
|---|---|
| System-side `TeleopIntake`: contract/lease/seq/deadman/mode checks, latest-setpoint sampling, multi-joint `JOINT_STEP` through `MotionArbiter` | `jcheng-system` PR #20; `tests/test_teleop.py` |
| ROS runtime subscriber `/jcheng/intent/teleop` (best-effort depth 1), 20 Hz intake timer | merged; `tests_ros/test_teleop_runtime.py` |
| Teleop ROS publisher on domain 42, operator-supplied lease, never mints one | `ros2_ws/src/jcheng_teleop_ros` |
| Test-only domain-43 simulation bridge + L3 runs for ArmPi, Gate-2, PiPER X mock | `jcheng-system/e2e/reports/20261126_teleop_*` |
| Humble build/tests | `e2e/reports/20261126_teleop_humble/` |
| Systematic read-only state tap for consumers | `/jcheng/telemetry/state` (system PR #25) |

## 2. What M2 did **not** deliver

- No production **lease adapter**: the publisher takes an operator-supplied
  lease id; it cannot acquire, renew or release.
- No `TeleopState` status surface from the system side; the teleop status API
  is a separate loopback demo surface.
- No operator input device; the publisher's input is a virtual demo script.
- No deployed gateway client, no authentication flow, no operator console
  lease handoff.
- No hardware streaming: the vendor executor is single-joint at ~5/s (B2), so
  the L3 runs are mock/simulation only.

Because of these, M2 stays **In progress**. The transport is proven; the
production path is not.

## 3. Governance gap and resolution

The manifest says `class: offline`, `runtime: {}` (empty), which matches the
production capability but not the test-only publisher shipped under
`ros2_ws/`. `capability-manifest.v1` has no class for a capability that
publishes bounded intent without motion authority:

| Class | Fits teleop? |
|---|---|
| `motion_source` | No: teleop has no motion authority and never calls `ExecuteMotion` |
| `observer` | No: the publisher is not read-only; it publishes an intent stream |
| `offline` | Only while the publisher is test-only and undeployed (current interim state) |

Resolution, contract-first:

1. `jcheng-interfaces` proposal
   [`capability-intent-source.md`](https://github.com/JCHENG-Robotics/jcheng-interfaces/blob/main/docs/proposals/capability-intent-source.md)
   adds `intent_source` to the class enum; no schema change is applied yet.
2. Until it is approved and tagged, `capability.yaml` stays `offline` with an
   empty runtime. The `ros2_ws/` publisher is explicitly test-only.
3. The org taxonomy entry is updated to the current state (v0.3.0
   Experimental, test-only transport, no production runtime).
4. When approved, the manifest moves to `intent_source` with
   `ros_domains: [42]` and `publishes: ["/jcheng/intent/teleop"]`, and the
   contract test is updated in the same change.

## 4. M2 acceptance mapping

| Item | State |
|---|---|
| Intent stream published on domain 42 with a lease id | Verified in mock/simulation L3 |
| System intake validates contract/lease/seq/deadman/mode; stops on release/timeout | Verified (L2 tests + L3) |
| Stop is mode-specific and latched only by the system path | Verified in core/mock |
| No device, vendor topic or motion authority in teleop | Verified (static scan) |
| Production lease acquisition/renewal | **Not implemented** |
| `TeleopState` / operator console lease flow | **Not implemented** |
| Hardware transport | **Blocked** (B2, wire v0.2) |
| Manifest class expresses the intent publisher | **Blocked** on the `intent_source` proposal |

## 5. Exit decision

M2 is **not** marked Complete. It can be closed when:

- the `intent_source` class is approved/tagged and the manifest/runtime/test
  are updated in one change;
- a production lease adapter (or an approved operator-console lease handoff)
  exists and is exercised in a mock/simulation session;
- a `TeleopState` surface (or the teleop status API as the contracted surface)
  is accepted by the studio panel and the system owner.

Hardware remains M6 and separately authorized.
