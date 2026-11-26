# jcheng-teleop roadmap

> Status: **v0.1.0** as of 2026-11-26. Admission-only scaffold complete; no
> input adapter, no runtime node and no hardware access.

## Current state

| Item | State | Evidence |
|---|---|---|
| Admission manifest (`capability.yaml`) | Complete (2026-11-26) | `capability.yaml`; `tests/test_contract.py` |
| Repository scaffold, gate and CI | Complete (2026-11-26) | `scripts/check_repo_gate.sh`; CI `teleop-gate` passed |
| ROS-free intent core (conditioning, rate limit, deadman) | Planned | — |
| ROS 2 teleoperation intent node | Planned | — |
| Supervised hardware teleoperation | Not started | — |

## Milestones

| Milestone | Scope | State | Exit criterion | Evidence |
|---|---|---|---|---|
| M0 | Repository scaffold and admission manifest | Complete (2026-11-26) | The document set, gate and CI `teleop-gate` pass; the manifest claims no runtime surface | `evidence/20261126_scaffold/`; CI run 45763190477 |
| M1 | ROS-free intent core | Planned | Deterministic tests cover input samples, deadzone, scaling, per-axis limits, rate limiting, `seq`/`stamp` and the deadman state machine; no DDS, no device and no hardware | — |
| M2 | Teleoperation intent node on the system API | Planned | A contract-first PR enables the reserved `TeleopCommand` stream on domain 42; mock integration (L2/L3) proves lease gating, preemption and deadman behavior; no motion | — |
| M3 | Supervised hardware teleoperation | Planned | An operator-side adapter feeds the node; every session is separately authorized; the system layer applies limits and the stop latch; L5 evidence is recorded | — |

## Next

1. **M1 — ROS-free intent core.** Define the input sample model, conditioning
   rules and deadman state machine in [docs/INPUT.md](docs/INPUT.md), add the
   core module and its tests, and keep it importable without ROS. Prerequisites:
   none; `TeleopCommand.msg` is already reserved in `jcheng-interfaces`
   v0.1.0. No robot session is required.
2. **M2 — teleoperation intent node.** Add a thin ROS 2 Humble wrapper that
   publishes the reserved `TeleopCommand` stream on domain 42 behind a lease,
   and prove lease gating, preemption and deadman behavior against the mock
   system stack. Prerequisites: M1 accepted; the contract-first PR that updates
   `capability.yaml`; the mock gateway and arbiter.

## Out of scope

- Device access and owning the operator input adapter. Physical gamepad, wheel
  and pendant adapters are operator-side and outside the capability boundary;
  `capability-manifest.v1` cannot express device access.
- Direct hardware commands, vendor topics, `/move_action` and `ExecuteMotion`.
- `/cmd_vel` and base chassis intent; the base intent stream belongs to
  `jcheng-mobile`.
- Acting as an e-stop or a safety function. The platform has no e-stop, brake,
  encoder or self-collision model; the system layer's stop latch is not an
  e-stop.
- Remote internet control, cross-network real-time teleoperation and
  unattended motion.
- Recordings, session databases or model weights in git.

## Dependencies

- `jcheng-interfaces` `>=0.1,<0.2`; contract hash
  `sha256:0b8d72ced7f54d444d6851d8b99a51a78e2bed3f687324f51a15f76557f24b42`.
- `jcheng-system` API `>=0.1,<0.2` from M2; the system layer remains the only
  origin of motion.
- `TeleopCommand.msg` is reserved in interfaces v0.1.0 and is enabled only at
  the first teleoperation pilot.
- Real-robot work requires separate, explicit operator authorization per
  session and is never triggered by CI or unattended runs.
