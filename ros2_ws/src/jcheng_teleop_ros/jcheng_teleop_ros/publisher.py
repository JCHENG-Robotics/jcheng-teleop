"""ROS 2 teleoperation intent publisher (M2 mock/sim).

This node is deliberately thin: it uses the ROS-free core for conditioning and
mapping, publishes the reserved `TeleopCommand` stream, and leaves lease,
arbitration, safety and stop authority to `jcheng-system`. It does not connect
to a robot, a device or a simulation plant directly.

The lease id is supplied by the operator (or a test harness) after the system
gateway grants it. The node never mints a lease.
"""

from __future__ import annotations

import sys

from jcheng_interfaces.msg import TeleopCommand
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

from jcheng_teleop.adapters.input.virtual import VirtualInputSource
from jcheng_teleop.core.conditioning import Conditioner
from jcheng_teleop.core.mapper import ActionMapper
from jcheng_teleop.core.model import InputSample, Mode
from jcheng_teleop.core.profile import load_binding, load_profile, resolve_profile

CONTRACT_HASH = "sha256:0b8d72ced7f54d444d6851d8b99a51a78e2bed3f687324f51a15f76557f24b42"


def _demo_samples(profile, *, duration_s: float, rate_hz: float) -> list[InputSample]:
    count = max(1, int(duration_s * rate_hz))
    samples: list[InputSample] = []
    for index in range(count):
        t_ns = int(index * 1_000_000_000 / rate_hz)
        values = [0.0] * profile.joint_count
        if profile.joint_count:
            values[0] = 0.2 if index < count - 5 else 0.0
        samples.append(
            InputSample(
                schema=InputSample.SCHEMA,
                source_id="ros_virtual",
                source_class="virtual",
                seq=index,
                t_source_ns=t_ns,
                t_host_mono_ns=t_ns,
                mode=Mode.JOINT_VELOCITY,
                joint_velocities_rad_s=tuple(values),
                deadman=index < count - 3,
                profile_id=profile.profile_id,
            )
        )
    return samples


class TeleopPublisher(Node):
    def __init__(self) -> None:
        super().__init__("jcheng_teleop_publisher")
        self.declare_parameter("profile", "")
        self.declare_parameter("binding", "")
        self.declare_parameter("lease_id", "")
        self.declare_parameter("source", "jcheng-teleop")
        self.declare_parameter("rate_hz", 50.0)
        self.declare_parameter("duration_s", 2.0)
        self.declare_parameter("contract_major", 0)
        self.declare_parameter("contract_minor", 1)
        self.declare_parameter("contract_patch", 0)
        self.declare_parameter("contract_hash", CONTRACT_HASH)

        profile_path = str(self.get_parameter("profile").value or "")
        binding_path = str(self.get_parameter("binding").value or "")
        self.lease_id = str(self.get_parameter("lease_id").value or "")
        self.source = str(self.get_parameter("source").value or "jcheng-teleop")
        if not profile_path or not binding_path:
            raise ValueError("profile and binding parameters are required")
        if not self.lease_id:
            raise ValueError("lease_id parameter is required (the node never mints a lease)")
        self.profile = resolve_profile(load_profile(profile_path), load_binding(binding_path))
        self.conditioner = Conditioner(self.profile)
        self.mapper = ActionMapper(self.profile)
        self.rate_hz = float(self.get_parameter("rate_hz").value)
        duration_s = float(self.get_parameter("duration_s").value)
        if self.rate_hz <= 0 or duration_s <= 0:
            raise ValueError("rate_hz and duration_s must be positive")
        self.samples = _demo_samples(self.profile, duration_s=duration_s, rate_hz=self.rate_hz)
        self.source_reader = VirtualInputSource(self.samples, respect_time=False)
        self.source_reader.open()
        self._stopped = False
        self._last_seq = -1
        self._last_source_ns = 0

        qos = QoSProfile(
            depth=1,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        self.publisher = self.create_publisher(TeleopCommand, "/jcheng/intent/teleop", qos)
        self.create_timer(1.0 / self.rate_hz, self._tick)
        self.get_logger().info(
            f"teleop publisher ready: profile={self.profile.profile_id} lease={self.lease_id} "
            f"rate={self.rate_hz}Hz duration={duration_s}s"
        )

    def _contract(self):
        contract = TeleopCommand().contract
        contract.major = int(self.get_parameter("contract_major").value)
        contract.minor = int(self.get_parameter("contract_minor").value)
        contract.patch = int(self.get_parameter("contract_patch").value)
        contract.contract_hash = str(self.get_parameter("contract_hash").value)
        return contract

    def _publish(self, intent, *, seq: int) -> None:
        message = TeleopCommand()
        message.header.stamp = self.get_clock().now().to_msg()
        message.seq = int(seq)
        message.lease_id = self.lease_id
        message.source = self.source
        message.contract = self._contract()
        message.mode = intent.mode.value
        message.joint_velocity_rad_s = list(intent.joint_velocities_rad_s)
        message.deadman = bool(intent.deadman)
        self.publisher.publish(message)
        self._last_seq = int(seq)

    def _tick(self) -> None:
        sample = self.source_reader.poll(self.get_clock().now().nanoseconds)
        if sample is not None:
            conditioned = self.conditioner.process(sample)
            intent = self.mapper.map(conditioned)
            self._last_source_ns = sample.t_source_ns
            self._publish(intent, seq=sample.seq)
            return
        if not self._stopped:
            # One explicit neutral frame after the script ends. The system
            # intake treats deadman=false as a non-latching session abort.
            last = InputSample(
                schema=InputSample.SCHEMA,
                source_id="ros_virtual",
                source_class="virtual",
                seq=max(0, self._last_seq + 1),
                t_source_ns=self._last_source_ns,
                t_host_mono_ns=self._last_source_ns,
                mode=Mode.JOINT_VELOCITY,
                joint_velocities_rad_s=(0.0,) * self.profile.joint_count,
                deadman=False,
                profile_id=self.profile.profile_id,
            )
            self._publish(self.mapper.map(self.conditioner.process(last)), seq=last.seq)
            self._stopped = True

    def close(self) -> None:
        self.source_reader.close()


def main(argv: list[str] | None = None) -> int:
    import rclpy

    rclpy.init(args=argv)
    node = None
    try:
        node = TeleopPublisher()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
