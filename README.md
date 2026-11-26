# jcheng-teleop

> Status: **Experimental** as of 2026-11-26. Version 0.1.0.
> Admission-only scaffold: the repository defines the teleoperation intent
> boundary, but contains no operator input adapter, no ROS node and no
> published intent. Nothing in it is used by the running robot.
> English canonical; see [README.zh-CN.md](README.zh-CN.md) for the Chinese
> translation.

`jcheng-teleop` is the L3 teleoperation capability of the JCHENG ecosystem. Its
charter is to turn operator input into bounded, lease-gated,
deadman-protected **teleoperation intent** for the system layer. Intent is a
proposal: the motion arbiter samples it and the system layer applies the lease,
deadman, limits and stop latch before anything moves. This repository never
commands hardware, never opens a device and never becomes a motion authority.

The contract already exists. `TeleopCommand.msg` is defined and reserved in
`jcheng-interfaces` v0.1.0. The stream is enabled only at the first
teleoperation pilot; v0.1.0 does not publish it.

## Scope and boundary

| Item | This repository |
|---|---|
| Layer | L3 capability (`capability.yaml`) |
| Inputs | Operator input samples from an adapter outside this repository (M1 onward); robot, safety and lease state from the system layer (M2) |
| Outputs | Teleoperation intent on the planned `/jcheng/intent/teleop` stream, domain 42 (M2); nothing in v0.1.0 |
| Motion authority | None in v0.1.0 (`safety.class: offline`, empty runtime surface) |
| Hardware access | `none` |
| Owned devices | none; a physical input adapter is operator-side and outside the capability boundary |
| Forbidden | device access, vendor topics, `/move_action`, `/cmd_vel`, `ExecuteMotion`, hardware commands, fabricated state |

The system layer is the only origin of motion. This repository publishes
intent, never a trajectory or a servo/motor command. Base chassis intent
belongs to `jcheng-mobile`; teleoperation does not publish it.

## Repository layout

```text
jcheng-teleop/
├── capability.yaml                 # admission manifest (offline, hardware_access: none)
├── docs/
│   ├── ARCHITECTURE.md             # input, intent and system planes
│   ├── INPUT.md                    # input samples, conditioning and deadman rules
│   └── INTEGRATION.md              # admission, lease, preemption and failure semantics
├── tests/
│   ├── test_contract.py            # manifest and document-set checks
│   └── test_no_hardware.py         # static no-device / no-motion scan
├── scripts/check_repo_gate.sh      # repository gate (local and CI)
├── evidence/20261126_scaffold/     # M0 evidence record
├── VERSION
├── README.md / README.zh-CN.md
├── ROADMAP.md / CHANGELOG.md / ACCEPTANCE.md
└── LICENSE-REVIEW.md
```

## Requirements

- Python 3.10 or newer (CI uses 3.12), `pytest` 8.3.4 and `PyYAML` 6.0.2.
- No ROS installation for v0.1.0. ROS 2 Humble is required only from M2, when
  the intent node exists.
- No input device is required for the gate. A physical gamepad, wheel or
  pendant adapter is operator-side and never opened by this repository.
- Session records stay outside the repository; recordings are never committed.

## Quick start

```bash
python3 -m pytest -q tests
bash scripts/check_repo_gate.sh
```

The gate checks the document set, the admission manifest, relative links,
secrets, model weights, recordings and the two test modules. It touches no
robot and opens no device.

## Validation status

| Claim | Status | Evidence |
|---|---|---|
| Repository gate and unit tests pass | Partially verified (local 2026-11-26; CI pending) | `evidence/20261126_scaffold/` |
| Manifest declares `hardware_access: none` and an empty runtime surface | Verified (L0, 2026-11-26) | `tests/test_contract.py` |
| No device, vendor topic or motion call exists in the tree | Verified (L0, 2026-11-26) | `tests/test_no_hardware.py` |
| Teleoperation intent behavior | Unverified | Not implemented (M1–M2) |

Full report: [ACCEPTANCE.md](ACCEPTANCE.md).

## Related repositories

- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces) — contract source, `TeleopCommand.msg` and the contract hash.
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system) — privileged runtime; sole owner of leases, arbitration, motion and hardware access.
- [`jcheng-mobile`](https://github.com/JCHENG-Robotics/jcheng-mobile) — base chassis capability and the base intent stream.
- [`jcheng-perception`](https://github.com/JCHENG-Robotics/jcheng-perception) — advisory perception targets; read-only context for the operator.
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops) — unattended health and watchdogs.
- [`.github`](https://github.com/JCHENG-Robotics/.github) — ecosystem roadmap, changelog, acceptance and the repository taxonomy.

## License

Pending third-party and copyright review; no `LICENSE` file has been added.
See [LICENSE-REVIEW.md](LICENSE-REVIEW.md).
