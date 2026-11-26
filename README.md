# jcheng-teleop
**English** | [简体中文](README.zh-CN.md)

> Status: **Experimental** as of 2026-11-26. Version 0.3.0.
> M0 design is approved. The M1 ROS-free core and CLI are implemented and
> covered by L1 and in-process L2 tests; M1 is accepted at that level. M2 is
> In progress: the mock system-core teleop intake has landed on a
> `jcheng-system` branch; the ROS subscriber and simulation bridge are pending. There is still no ROS node, no DDS
> domain, no input device access, no published intent and no motion. The
> physical operator input adapter is outside this repository; device-free input
> sources and mappings are in-repo. Nothing here is used by the running robot.
>
> English canonical; the Chinese README is a translation.

`jcheng-teleop` is the L3 teleoperation and demonstration-capture capability of
the JCHENG ecosystem. Its charter is to turn operator input into bounded,
lease-gated, deadman-protected **teleoperation intent** for the system layer,
and to capture reproducible demonstration episodes without becoming a motion
authority. The design targets one code base across the ArmPi Ultra 5-DoF arm,
the Gate-2 arm, the PiPER X 6-DoF arm and future leader arms; robot differences
belong in profiles, not in copied control cores. This is a design target: the
PiPER X CAN profile and hardware path do not exist yet, and Gate-2 is
simulation-only today.

The system layer remains the only origin of motion. Teleoperation proposes;
the gateway, lease, motion arbiter and safety supervisor decide. This
repository never opens a robot device, never publishes a vendor topic, never
calls `ExecuteMotion` and never sends a servo or motor command.

## Scope and boundary

| Item | This repository |
|---|---|
| Layer | L3 capability (`capability.yaml`) |
| Inputs | Normalized input samples from a device-free source (virtual/keyboard/JSONL/gamepad mapping) or an operator-side adapter (M1 onward); read-only robot, safety and lease state from the system layer (M2 onward) |
| Outputs | Bounded action intent to an in-process mock gateway (M1); `TeleopCommand` on the planned `/jcheng/intent/teleop` stream, domain 42 (M2 onward); capture packages outside git (M3 onward). Nothing leaves the process in v0.3.0 |
| Motion authority | None. The system gateway, lease, arbiter and safety supervisor remain authoritative |
| Hardware access | `none` (`capability.yaml`); no robot device and no operator input device is opened here |
| Owned devices | None. A physical gamepad, keyboard, wheel, pendant or leader arm is operator-side and outside the capability boundary. M1 provides device-free mapping and tests; the OS device driver stays operator-side. |
| Forbidden | Robot device access, vendor topics, `/move_action`, `/cmd_vel`, `ExecuteMotion`, hardware commands, fabricated state, simulation data labelled as hardware |
| Runtime in v0.3.0 | Local CLI only: no DDS domain, no ROS node, no publisher, no subscriber, no service, no device |

The current `jcheng-system` has **no teleoperation consumer**. Its gateway and
motion arbiter accept discrete `MotionCommand` requests; the reserved
`TeleopCommand` stream is not subscribed anywhere. M2 therefore depends on a
system-side teleoperation intake and streaming servo path, proposed in
[docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md) and
[docs/proposals/SYSTEM_TELEOP_INTAKE.md](docs/proposals/SYSTEM_TELEOP_INTAKE.md).
Publishing the reserved topic without that consumer would be inert and is not
claimed.

## Repository layout

```text
jcheng-teleop/
├── capability.yaml                 # admission manifest (offline, hardware_access: none)
├── docs/
│   ├── ARCHITECTURE.md             # context, modules, lifecycles, decisions
│   ├── TELEOP_CORE.md              # input conditioning, mapping, sessions, APIs
│   ├── SAFETY_MODEL.md             # hazards, state machine, stop paths, residual risk
│   ├── DATA_COLLECTION.md          # capture, provenance, time sync, LeRobot mapping
│   ├── INTEGRATION_CONTRACT.md     # system, simulation, learning, studio contracts
│   ├── DEPENDENCY_REVIEW.md        # prior art, licenses, dependency decisions
│   ├── INPUT.md                    # input sample and adapter boundary
│   ├── M1_PLAN.md                  # M1 work packages, tree, test matrix, blockers
│   └── proposals/                  # contract-first proposals; no interface is changed
├── src/jcheng_teleop/              # ROS-free core, adapters, CLI
├── examples/armpi_ultra_demo/      # demo profile + binding
├── tests/                          # unit, in-process L2 and static boundary tests
├── scripts/check_repo_gate.sh      # repository gate (local and CI)
├── evidence/                       # L0/L1/L2 evidence records
├── pyproject.toml                  # package metadata and pytest config
├── VERSION
├── README.md / README.zh-CN.md
├── ROADMAP.md / CHANGELOG.md / ACCEPTANCE.md
└── LICENSE-REVIEW.md
```

## Requirements

- Python 3.10 or newer (CI uses 3.12), `PyYAML` 6.0+ at runtime, `pytest` 7.4+
  for tests. CI pins `pytest==8.3.4` and `PyYAML==6.0.2`.
- No ROS installation is required for M1. ROS 2 Humble is required only when
  the intent node exists (M2), and it is tested in a `ros:humble` container.
- No input device and no robot are required. A physical adapter is
  operator-side; this repository consumes normalized samples, not devices.
- Capture packages and datasets stay outside the repository, under an
  operator-controlled data root. They are never committed.

## Quick start

```bash
python3 -m pytest -q tests
bash scripts/check_repo_gate.sh

PYTHONPATH=src python3 -m jcheng_teleop \
  --profile examples/armpi_ultra_demo/profile.yaml \
  --binding examples/armpi_ultra_demo/binding.yaml \
  --input virtual --ticks 20
```

The gate checks the document set, the admission manifest, relative links,
secrets, model weights, recordings and the static boundary tests. The CLI runs
against an in-process mock gateway. Neither touches a robot or opens a device.

## Validation status

| Claim | Status | Evidence |
|---|---|---|
| M0 document set, links, manifest and static no-device scan pass | Verified (L0/L1, 2026-11-26) | `evidence/20261126_m0_design/`; `tests/` |
| M1 ROS-free core: conditioning, mapping, deadman, session, mock gateway | Partially verified (L1, 2026-11-26; M1 acceptance pending) | `evidence/20261126_m1_core/`; `tests/` |
| M1 deterministic trace and no-device boundary | Partially verified (L1/L2 in-process, 2026-11-26; acceptance pending) | `evidence/20261126_m1_core/`; `tests/test_runner_determinism.py` |
| Ecosystem audit and cross-repository contract gaps are recorded | Verified (L0, 2026-11-26) | [docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md); [docs/DEPENDENCY_REVIEW.md](docs/DEPENDENCY_REVIEW.md) |
| Input conditioning, mapping, sessions and deadman behavior | Partially verified (L1, 2026-11-26; acceptance pending) | `tests/test_conditioning.py`, `test_deadman.py`, `test_session.py` |
| Intent publication, lease gating and preemption | Unverified | Not implemented (M2); system consumer absent |
| Capture, replay and LeRobot export | Unverified | Not implemented (M3–M4) |
| Hardware teleoperation | Unverified | No session authorized; no e-stop on the platform |

Full report: [ACCEPTANCE.md](ACCEPTANCE.md). M0 design is approved. M1 tests
pass at L1/in-process L2, but M1 acceptance is **Inconclusive** until the
independent code review is re-run on a frozen artifact. M2 and hardware are
unverified.

## Related repositories

- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces) — contract source, `TeleopCommand.msg`, schemas and contract hash.
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system) — privileged runtime; gateway, leases, arbiter, safety and the only motion origin.
- [`jcheng-simulation`](https://github.com/JCHENG-Robotics/jcheng-simulation) — robot catalog and offline plant on domain 43; one plant at a time; profiles and `/sim/*` surfaces.
- [`jcheng-learning`](https://github.com/JCHENG-Robotics/jcheng-learning) — dataset contract, training and policy artifacts; owns `jcheng.dataset.v1`.
- [`jcheng-studio`](https://github.com/JCHENG-Robotics/jcheng-studio) — operator console; gateway HTTP/WS only, no DDS or device.
- [`jcheng-applications`](https://github.com/JCHENG-Robotics/jcheng-applications) — task orchestration and reusable gateway-client patterns.
- [`jcheng-benchmark`](https://github.com/JCHENG-Robotics/jcheng-benchmark) — offline JSONL scoring; no replay execution.
- [`jcheng-mobile`](https://github.com/JCHENG-Robotics/jcheng-mobile) — base chassis intent owner.
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops) — unattended health probes and watchdogs.
- [`.github`](https://github.com/JCHENG-Robotics/.github) — governance, taxonomy, documentation standard and hardware workflow.

## License

Pending third-party and copyright review; no `LICENSE` file has been added.
See [LICENSE-REVIEW.md](LICENSE-REVIEW.md).
