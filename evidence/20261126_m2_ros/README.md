# M2 ROS publisher and Humble build evidence

> Status: **Partially verified (build/L3 simulation, 2026-11-26)**. No hardware.
> All L3 records live in `jcheng-system/e2e/reports/`; Humble validation of the
> system side is in `e2e/reports/20261126_teleop_humble/`.

## Teleop ROS package

- Package: `ros2_ws/src/jcheng_teleop_ros`
- Build (Jazzy): pass
- Build (Humble container `armpi-humble-moveit:latest`):
  `jcheng_interfaces` + `jcheng_teleop_ros` built successfully.
- The node imports `jcheng_teleop` from the core package; a real deployment
  must install the core (pip editable) or set `PYTHONPATH` to `src/`.

## L3 simulation

| Robot | Shape | Result | Evidence |
|---|---|---|---|
| ArmPi | domain 43 only | joint1 0 → 0.205 rad | `20261126_teleop_sim/` |
| Gate-2 | domain 43 only | both joints ±0.501 rad | `20261126_teleop_sim_gate2/` |
| Gate-2 | runtime 42 + bridge 43 | both joints ±0.125 rad | `20261126_teleop_domain42/` |
| ArmPi | runtime 42 + bridge 43 | joint1 0 → 0.2375 rad | `20261126_teleop_domain42_armpi/` |
| PiPER X (mock) | runtime 42 + bridge 43 | six joints ±0.1379 rad | `20261126_teleop_piperx_mock/` |

The canonical shape is the runtime/probe on domain 42 with
`RosSimHardwareBridge` and the plant on domain 43. It is proven, not deployed:
the bridge is test-only.

Teleop-side demo profiles: `examples/armpi_ultra_demo/`,
`examples/gate2_arm_demo/`, `examples/piper_x_demo/` (six joints, no gripper,
simulation-only).

## Limits

- No hardware, vendor path or `jcheng-interfaces` change.
- PiPER X is simulation-only: v1 cannot express a CAN arm and no CAN read has
  established whether vendor feedback is a measurement.
- No Humble run with the simulation plant; only build/tests.
- Plant tracking/lag is not characterized as a bound.
- No input device, lease adapter, `TeleopState` or production gateway client.
