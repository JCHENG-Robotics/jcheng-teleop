# M0 architecture evidence — 2026-11-26

> Scope: repository admission, ecosystem audit, architecture design, contract
> proposals, dependency review and M1 plan. No runtime, no DDS, no device, no
> robot, no recording, no hardware session.
>
> Branch: `docs/m0-architecture` (working tree), based on `fa076d3`.
> Operator: JerichoCheng. Independent review: `review.md` — Round 1 REJECT;
> Round 2 APPROVE WITH CHANGES, no blockers. The operator approved the M0
> design on 2026-11-26. The content is pinned by the tree hash below; no commit or tag was
> created (operator action after approval).
> M0 review snapshot hash: `sha256:f8f6281d4b7e9168cd9d24d4716da668f3928309be821d8e7fe90b6a65f85e6c`; M1 edits followed.

## Commands

```bash
python3 -m pytest -q tests | tee evidence/20261126_m0_design/pytest.txt
bash scripts/check_repo_gate.sh | tee evidence/20261126_m0_design/gate.txt
```

The gate prints to stdout; `tee` records it. The files are regenerated after
the final review edits.

## Results

| Check | Result |
|---|---|
| Document set and relative links | pass (see `gate.txt`) |
| Admission manifest parses and matches `VERSION` | pass |
| `hardware_access: none`, empty runtime surface | pass |
| No device/vendor/motion token in code, config or scripts | pass |
| No model weight, recording, dataset or oversized file | pass |
| No `LICENSE` before the license review | pass |
| Static no-device tests | pass |

## What was reviewed

- `jcheng-interfaces`: `TeleopCommand`, `ControlLease`, `MotionCommand`,
  `RobotState`, capability/robot-profile schemas, error registry and contract
  hash.
- `jcheng-system`: gateway routes, lease manager, motion arbiter, safety
  supervisor, mock stack, vendor executor limits and testkit scenarios.
- `jcheng-simulation`: multi-robot catalog, mock and Gazebo plants, `/sim/*`
  surfaces, domain 43 and truth labelling.
- `jcheng-learning`: `jcheng.dataset.v1` proposal, action-space constraints,
  LeRobot pin and provenance rules.
- `jcheng-studio`, `jcheng-applications`, `jcheng-benchmark`: gateway client,
  orchestration and scoring reuse surfaces.
- `.github`: layer taxonomy, documentation standard, hardware workflow,
  license review and admission checklist.

## Limitations

- This is documentation and design evidence only. It is not behavior,
  performance, safety or hardware evidence.
- The system has no teleoperation consumer; the canonical M2 path is a
  proposal, not an implemented integration.
- The learning dataset contract and writer are an untracked 0.2.0 working
  tree, not a merged or frozen contract. The committed repository is 0.1.0.
- No interface, gateway, system, simulation, learning or studio file was
  changed. The two proposals are pre-proposals.
- The governance teleop admission change is on an unmerged `.github` branch;
  this is recorded as blocker B0.
- The repository has no `LICENSE`; no third-party code was adopted.

## Artifacts

- `docs/ARCHITECTURE.md`
- `docs/TELEOP_CORE.md`
- `docs/SAFETY_MODEL.md`
- `docs/DATA_COLLECTION.md`
- `docs/INTEGRATION_CONTRACT.md`
- `docs/DEPENDENCY_REVIEW.md`
- `docs/INPUT.md`
- `docs/M1_PLAN.md`
- `docs/proposals/TELEOP_COMMAND_V0.2.md`
- `docs/proposals/SYSTEM_TELEOP_INTAKE.md`
- `review.md`
- `README.md`, `README.zh-CN.md`, `ROADMAP.md`, `CHANGELOG.md`, `ACCEPTANCE.md`
