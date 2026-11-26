# jcheng_teleop_ros

> Status: **Experimental**, M2 mock/simulation transport and M3 demo capture.
> No device, no hardware and no motion authority.

ROS 2 transport wrapper for the `jcheng-teleop` core. It loads the teleop
profile/binding, consumes a virtual input script, conditions/maps it with the
ROS-free core, and publishes the reserved `TeleopCommand` stream on
`/jcheng/intent/teleop`. With capture enabled it also records a
`jcheng.teleop.capture.v1` package (input/action rows plus observation rows
from the system telemetry topic). The system layer owns the lease, arbiter,
safety and stop authority; this node never mints a lease.

## Build

```bash
cd jcheng-teleop
colcon build --base-paths ros2_ws/src --packages-select jcheng_teleop_ros
source install/setup.bash
# The core package is installed separately (pip install -e .), or put src/ on
# PYTHONPATH for a source-tree run.
```

The node imports `jcheng_teleop` from the core package. This package does not
vendor the core and does not add a ROS dependency to the core.

## Run

The lease id must come from the system gateway/operator; it is not generated
here.

```bash
ros2 run jcheng_teleop_ros jcheng_teleop_publisher --ros-args \
  -p profile:=$PWD/examples/armpi_ultra_demo/profile.yaml \
  -p binding:=$PWD/examples/armpi_ultra_demo/binding.yaml \
  -p lease_id:=<lease-from-system> \
  -p duration_s:=2.0 \
  -p rate_hz:=50.0
```

The publisher sends a final neutral frame (`deadman=false`) after the script
ends. The system intake treats that as a non-latching session abort.

## Capture

```bash
ros2 run jcheng_teleop_ros jcheng_teleop_publisher --ros-args \
  -p profile:=$PWD/examples/armpi_ultra_demo/profile.yaml \
  -p binding:=$PWD/examples/armpi_ultra_demo/binding.yaml \
  -p lease_id:=<lease-from-system> \
  -p record_root:=/data/jcheng-captures \
  -p capture_id:=sim-20261126 \
  -p environment_class:=simulation \
  -p sim_truth_label:=/sim/truth/source=simulated \
  -p simulator_repo:=jcheng-simulation \
  -p simulator_version:=<commit>
```

- `record_root` must stay outside any git worktree; the directory is created
  with the capture id.
- `environment_class` is `mock` or `simulation`. A hardware capture requires a
  supervised system session, so this demo node refuses it.
- Observations are copied verbatim from `/jcheng/telemetry/state`
  (`state_topic`); `truth`/`verification` are never reinterpreted. A `bus`
  label outside a hardware capture is rejected and recorded as an
  `OBSERVATION_REJECTED` event.
- A capture fault stops the script and sends one neutral frame.

## Boundary

- No lease acquisition or renewal here.
- No `ExecuteMotion`, no vendor topic, no device, no `/cmd_vel`.
- No simulation plant directly; a test bridge is a separate system/simulation
  concern.
- No hardware claim. M6 remains blocked by the vendor executor.

## Related

- [Teleop core](../../../README.md)
- [Integration contract](../../../docs/INTEGRATION_CONTRACT.md)
- [Safety model](../../../docs/SAFETY_MODEL.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
