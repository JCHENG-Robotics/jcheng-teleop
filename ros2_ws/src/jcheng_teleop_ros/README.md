# jcheng_teleop_ros

> Status: **Experimental**, M2 mock/simulation transport. No device, no
> hardware and no motion authority.

ROS 2 transport wrapper for the `jcheng-teleop` core. It loads the teleop
profile/binding, consumes a virtual input script, conditions/maps it with the
ROS-free core, and publishes the reserved `TeleopCommand` stream on
`/jcheng/intent/teleop`. The system layer owns the lease, arbiter, safety and
stop authority; this node never mints a lease.

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
