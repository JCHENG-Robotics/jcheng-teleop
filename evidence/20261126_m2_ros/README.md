# M2 ROS publisher and Humble build evidence

> Status: **Partially verified (build/L3 simulation, 2026-11-26)**. No hardware.
> Domain-43 ArmPi L3 is recorded in `jcheng-system`
> `e2e/reports/20261126_teleop_sim/`; Humble validation of the system side is in
> `e2e/reports/20261126_teleop_humble/`.

## Teleop ROS package

- Package: `ros2_ws/src/jcheng_teleop_ros`
- Build (Jazzy): pass
- Build (Humble container `armpi-humble-moveit:latest`):
  `jcheng_interfaces` + `jcheng_teleop_ros` built successfully.
- The node imports `jcheng_teleop` from the core package; a real deployment
  must install the core (pip editable) or set `PYTHONPATH` to `src/`.

## L3 ArmPi simulation

The system test-only bridge and probe are recorded in
`jcheng-system/e2e/reports/20261126_teleop_sim/README.md`:

```text
arm True armed
lease True lease-49b5ba36fa06 OK
sim_positions [0.2049832552584121, 0.0, 0.0, 0.0, 0.0, -0.4]
```

joint1 moved 0 -> ~0.205 rad; domain 43 only; no hardware.

## Limits

- ArmPi only. Gate-2/PiPER X system profiles and sequential multi-robot runs
  are not implemented.
- Canonical domain-42 runtime + domain-43 bridge split is not proven.
- No Humble run with the simulation plant; only build/tests.
- No hardware, vendor path or `jcheng-interfaces` change.
