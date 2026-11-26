# Acceptance report — jcheng-teleop

> Status: **pass** as of 2026-11-26 for the M0 design and the M1 ROS-free core
> (L1 / in-process L2). Version 0.3.0, commit `ca5584b`, tag `v0.3.0`.
> M1 is not hardware evidence; M2+ remains unverified.
> Operator: JerichoCheng approved the M0 design on 2026-11-26. Reviewer:
> independent design review Round 1 REJECT; Round 2 APPROVE WITH CHANGES, no
> blockers. M1 code review is recorded separately.
> Scope: M0 architecture and M1 core. The M1 result is not hardware evidence;
> M2+ and all robot behavior remain unverified. M2 has a test-only ROS
> publisher and simulation L3 (ArmPi, Gate-2, PiPER X mock) but no input
> device, capture, deployment or hardware session. No motion command reaches
> a robot.
> M0 reviewed content: `sha256:f8f6281d4b7e9168cd9d24d4716da668f3928309be821d8e7fe90b6a65f85e6c`
> on branch `docs/m0-architecture`; no commit or tag was created (operator
> action after approval).

## 1. Scope

This report covers:

1. the M0 design package: admission, ecosystem audit, architecture, contract
   proposals, dependency review and M1 plan;
2. the M1 ROS-free core: input conditioning, profile mapping, deadman,
   session state machine, safety guard, in-process mock gateway, device-free
   adapters and CLI.

It does not cover a ROS 2 node, DDS transport, system gateway integration,
simulation plant, capture, replay, dataset export, studio integration or
hardware.

## 2. Gates

| Gate | Command | Level | Result | Evidence |
|---|---|---|---|---|
| Repository gate | `bash scripts/check_repo_gate.sh` | L0 | pass | `evidence/20261126_m1_core/gate.txt` |
| M0 document tests | `python3 -m pytest tests` | L0/L1 | pass | `evidence/20261126_m0_design/pytest.txt` |
| M1 unit and in-process L2 tests | `python3 -m pytest tests` | L1/L2 | pass (111 tests) | `evidence/20261126_m1_core/pytest.txt` |
| 2/5/6-DoF profile fixtures | `pytest tests/test_profile.py::test_2_5_6_dof_profiles_resolve` | L1 | pass | `evidence/20261126_m1_core/profiles.txt` |
| Deterministic trace | `pytest tests/test_runner_determinism.py`; CLI twice | L1/L2 | pass | `evidence/20261126_m1_core/determinism.txt`; `cli_trace_sha256.txt` |
| CLI virtual run | `jcheng-teleop --input virtual --ticks 20` | L2 | pass | `evidence/20261126_m1_core/cli_summary_1.txt` |
| Independent design review | review agent / operator | L0 | Round 1 REJECT; Round 2 APPROVE WITH CHANGES; operator approved | `evidence/20261126_m0_design/review.md` |
| Independent M1 code review | review agent | L1 | Round 1 REJECT; Round 2 APPROVE WITH CHANGES; six majors fixed; final re-review pending | `evidence/20261126_m1_core/review.md` |
| Simulation / mock end-to-end | — | L3 | not applicable (no system intake/sim bridge) | — |
| Replay of a real capture | — | L4 | not applicable (no capture) | — |
| Hardware | — | L5 | not applicable; no session authorized | — |

## 3. Verified claims

| Claim | Level | Evidence |
|---|---|---|
| The repository is an L3 capability with `hardware_access: none` and `safety.class: offline`; the manifest still declares an empty runtime surface until the M2 capability PR merges | L0 | `capability.yaml`; `tests/test_contract.py` |
| The M0 document set, links and full M0–M9 roadmap exist | L0 | gate; `tests/test_contract.py` |
| The nine module responsibilities, dependencies, interfaces and lifecycles are recorded | L0 | `docs/ARCHITECTURE.md`; `docs/TELEOP_CORE.md` |
| The ecosystem audit identifies the missing system consumer, discrete motion path and vendor executor limits | L0 | `docs/INTEGRATION_CONTRACT.md`; `docs/proposals/SYSTEM_TELEOP_INTAKE.md` |
| The contract gaps and two contract-first proposals are recorded | L0 | `docs/proposals/` |
| Prior art and licenses are recorded with adopt/reject decisions | L0 | `docs/DEPENDENCY_REVIEW.md` |
| The core is importable and testable without ROS, DDS, a device or a robot | L1 | `src/jcheng_teleop/`; `tests/` |
| No intent is emitted before a fresh enable edge and a valid lease/state | L1/L2 | `tests/test_session.py` |
| Deadman release and input timeout produce one mode-specific stop intent and stop the session; no auto-resume | L1/L2 | `tests/test_deadman.py`; `tests/test_session.py` |
| Velocity clamping emits one limit event per continuous saturation episode | L1 | `tests/test_conditioning.py` |
| Position mode is typed and refused when the wire does not support it; no velocity emulation | L1/L2 | `tests/test_mapper.py`; `tests/test_session.py` |
| Profile/binding mismatch, duplicate/rollback seq, stamp rollback and non-finite input are rejected | L1 | `tests/test_profile.py`; `tests/test_conditioning.py` |
| The mock gateway covers lease, submit, unknown, busy, unavailable and stop; no motion retry | L2 | `tests/test_mock_gateway.py`; `tests/test_session.py` |
| 2/5/6-DoF profiles run through the same core | L1 | `tests/test_profile.py`; `evidence/20261126_m1_core/profiles.txt` |
| The same script produces a byte-identical trace | L1/L2 | `tests/test_runner_determinism.py`; `cli_trace_sha256.txt` |
| Capture provenance is immutable; mock/simulation cannot be relabelled hardware; `replay` is not a new capture | L1 | `tests/test_capture.py`; `docs/DATA_COLLECTION.md` |
| Observation rows copy `truth`/`verification` and gate `bus`/`simulated` by environment; a rejected row is recorded as an event | L1 | `tests/test_capture.py`; `capture/observation.py` |
| The recorder cannot block the tick loop or the stop path (bounded queue, observer isolation, stop on recorder fault) | L1/L2 | `tests/test_capture.py`; `core/runner.py` |
| A sealed capture re-reads with matching hashes; tampering is detected | L1 | `tests/test_capture.py`; `capture/verify.py` |
| Input replay re-derives recorded actions byte-identically; tampering and missing inputs are findings | L1 | `tests/test_replay.py`; `evidence/20261126_m4_replay/` |
| A capture with a `bus` label in a non-hardware environment, or non-monotonic time, is an anomaly error | L1 | `tests/test_replay.py`; `replay/anomaly.py` |
| 30 × 60 s mock captures are valid with complete provenance and 0 label violations | L1 | `tools/capture_acceptance_drill.py`; `evidence/20261126_m3_capture/drills.txt` |
| A storage write failure faults the recorder, sends a stop and stops the session; no tick is blocked | L1 | `tools/disk_full_drill.py`; `evidence/20261126_m3_capture/drills.txt` |
| No device, vendor topic, motion call, model weight or recording exists in the tree | L0 | `tests/test_no_hardware.py`; gate |

## 4. Not verified

| Item | Reason | Risk |
|---|---|---|
| ROS 2 Humble node, DDS QoS and lease handshake | Publisher and Humble build exist (M2); no lease handshake from teleop, no deployment | No deployed intent path |
| System teleoperation intake and streaming session | Intake + ROS subscriber merged for mock only; `TeleopState` absent | No production consumer |
| Simulation bridge and multi-robot teleoperation | Test-only bridge; ArmPi, Gate-2 and PiPER X mock L3 proven on domain 42 + 43 | No hardware or canonical PiPER X profile |
| Measured state at teleop rate | Mock state only | Position/leader teleoperation not validated |
| Episode capture | Capture core implemented (M3): provenance gate, non-blocking writer, seal/verify, 26 tests, mock CLI recording, ROS-harness observation rows from the system telemetry tap, a 30 × 60 s mock acceptance set and a storage-fault drill; media, a simulation/hardware episode set and cross-stream time sync open | No demonstration dataset yet |
| Offline replay | Input replay implemented (M4 slice 1): recorded mock/simulation captures replay with 0 divergences; anomaly scan covers schema, tick/time order, stop/deadman, label and coverage checks; replay imports no runtime/network module. Command replay, quality metrics, benchmark export and LeRobot export open | No export evidence yet |
| Studio teleoperation panel | Not implemented (M5) | Operator cannot observe a live session |
| Leader-arm and hardware teleoperation | Not implemented (M6); vendor executor cannot stream multi-joint | No hardware claim; no e-stop |
| Independent M1 code review | Round 1 REJECT; Round 2 APPROVE WITH CHANGES; final re-review pending | M1 acceptance is not final |
| Hardware behavior | No authorization, no session | No L5 evidence |

## 5. Limitations

- M1 is an L1 / in-process L2 result. Mock behavior is not system behavior and
  never hardware validation.
- The mock gateway is a semantic fake, not the system arbiter; it does not
  prove the system gateway, lease manager or safety supervisor.
- The keyboard adapter consumes injected key events; a real terminal wrapper
  and a real gamepad driver remain operator-side.
- The demo profile is a fixture, not the canonical system profile; M2 must
  resolve the canonical profile and hash.
- The 50 Hz / 300 ms values are local design bounds; they are not a physical
  stop guarantee. The platform has no e-stop, brake, encoder or self-collision
  model.
- The system has a mock-only teleop intake and a test-only simulation bridge;
  there is no production consumer, no gateway lease adapter and no
  `TeleopState`. M2 is a cross-repository effort.
- PiPER X is simulation-only: `robot-profile.v1` cannot express a CAN arm and
  no CAN read has established whether vendor feedback is a measurement.
- The vendor executor accepts one-joint `JOINT_STEP` at about 5 commands/s;
  M6 hardware streaming is blocked.
- `jcheng.dataset.v1` and its writer are an untracked learning working tree,
  not a frozen contract.
- The `.github` teleop admission change is on an unmerged branch.
- No `LICENSE`; no third-party code was copied.

## 6. Sign-off

| Role | Name | Date |
|---|---|---|
| Operator | JerichoCheng | 2026-11-26 |
| M0 reviewer | independent review (Round 2 APPROVE WITH CHANGES) | 2026-11-26 |
| M0 design approval | JerichoCheng | 2026-11-26 |
| M1 code review | independent review (Round 2 APPROVE WITH CHANGES; final re-review pending) | 2026-11-26 |
| Commit/tag | operator action | pending |

M0 design is approved. M1 is not yet accepted: its tests pass at L1/in-process
L2, but the independent code review must be re-run on a frozen artifact. M2,
M3–M5, M6 and all hardware remain unverified.

## 7. Machine-readable report

None. When produced, reports must validate against
`jcheng-interfaces/schemas/acceptance-report.v1.schema.json`.

## 8. Related

- [README](README.md)
- [ROADMAP](ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Integration contract](docs/INTEGRATION_CONTRACT.md)
- [Dependency review](docs/DEPENDENCY_REVIEW.md)
- [M1 plan](docs/M1_PLAN.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`.github` documentation standard](https://github.com/JCHENG-Robotics/.github/blob/main/docs/documentation-standard.md)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
