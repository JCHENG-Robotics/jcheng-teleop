"""ROS 2 teleoperation intent publisher and capture harness (M2/M3).

This node is deliberately thin: it uses the ROS-free core for conditioning and
mapping, publishes the reserved `TeleopCommand` stream, and leaves lease,
arbitration, safety and stop authority to `jcheng-system`. It does not connect
to a robot, a device or a simulation plant directly.

With `record_root` set it also records a `jcheng.teleop.capture.v1` package:
input/action rows from the demo script and observation rows from the read-only
system telemetry topic. The recorder is non-blocking; a capture fault stops the
script and sends one neutral frame.

The lease id is supplied by the operator (or a test harness) after the system
gateway grants it. The node never mints a lease.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sys

from jcheng_interfaces.msg import RobotState, TeleopCommand
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

from jcheng_teleop import __version__
from jcheng_teleop.adapters.input.virtual import VirtualInputSource
from jcheng_teleop.capture import CaptureMetadata, EpisodeRecorder, ObservationSample
from jcheng_teleop.core.conditioning import Conditioner
from jcheng_teleop.core.mapper import ActionMapper
from jcheng_teleop.core.model import InputSample, Mode, Severity
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
        # M3 capture (optional; this demo path is mock/simulation only).
        self.declare_parameter("record_root", "")
        self.declare_parameter("capture_id", "")
        self.declare_parameter("task", "ros-demo")
        self.declare_parameter("environment_class", "mock")
        self.declare_parameter("sim_truth_label", "")
        self.declare_parameter("simulator_repo", "")
        self.declare_parameter("simulator_version", "")
        self.declare_parameter("state_topic", "/jcheng/telemetry/state")

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
        self._state_errors = 0

        qos = QoSProfile(
            depth=1,
            history=HistoryPolicy.KEEP_LAST,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        self.publisher = self.create_publisher(TeleopCommand, "/jcheng/intent/teleop", qos)
        self.state_topic = str(self.get_parameter("state_topic").value or "/jcheng/telemetry/state")
        self.recorder: EpisodeRecorder | None = None
        record_root = str(self.get_parameter("record_root").value or "")
        if record_root:
            self.recorder = EpisodeRecorder(
                record_root, self._capture_metadata(self._contract_hash())
            )
            self.create_subscription(RobotState, self.state_topic, self._on_state, qos)
            self.get_logger().info(
                f"capture enabled: {self.recorder.writer.path} "
                f"env={self.recorder.metadata.environment_class} "
                f"state_topic={self.state_topic}"
            )
        self.create_timer(1.0 / self.rate_hz, self._tick)
        self.get_logger().info(
            f"teleop publisher ready: profile={self.profile.profile_id} lease={self.lease_id} "
            f"rate={self.rate_hz}Hz duration={duration_s}s"
        )

    def _contract_hash(self) -> str:
        return str(self.get_parameter("contract_hash").value)

    def _contract(self):
        contract = TeleopCommand().contract
        contract.major = int(self.get_parameter("contract_major").value)
        contract.minor = int(self.get_parameter("contract_minor").value)
        contract.patch = int(self.get_parameter("contract_patch").value)
        contract.contract_hash = self._contract_hash()
        return contract

    def _capture_metadata(self, contract_hash: str) -> CaptureMetadata:
        environment = str(self.get_parameter("environment_class").value or "mock")
        if environment not in {"mock", "simulation"}:
            raise ValueError(
                "environment_class must be mock or simulation; a hardware capture "
                "requires a supervised system session, not this demo node"
            )
        capture_id = str(self.get_parameter("capture_id").value or "") or (
            "capture-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        task = str(self.get_parameter("task").value or "ros-demo")
        config = {
            "profile_hash": self.profile.profile_hash,
            "binding_hash": self.profile.binding.binding_hash,
            "rate_hz": self.rate_hz,
            "duration_s": self.get_parameter("duration_s").value,
            "state_topic": self.state_topic,
        }
        return CaptureMetadata(
            capture_id=capture_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            teleop_version=__version__,
            contract_hash=contract_hash,
            profile_id=self.profile.profile_id,
            profile_hash=self.profile.profile_hash,
            binding_hash=self.profile.binding.binding_hash,
            environment_class=environment,
            source_class="scripted",
            session_id=capture_id,
            task_id=task,
            task_description=f"ROS demo teleoperation ({task})",
            joint_names=self.profile.joint_names,
            profile_source="fixture",
            has_gripper=self.profile.gripper is not None,
            sim_truth_label=str(self.get_parameter("sim_truth_label").value or "") or None,
            simulator_repo=str(self.get_parameter("simulator_repo").value or "") or None,
            simulator_version=str(self.get_parameter("simulator_version").value or "") or None,
            generator_id="jcheng-teleop-ros-demo",
            generator_seed=0,
            generator_config_hash="sha256:"
            + hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest(),
            tick_ms=max(1, round(1000.0 / self.rate_hz)),
            nominal_hz=self.rate_hz,
            deadman_ms=300,
            limitations=(
                "demo script only; the operator input adapter is out of scope",
                "observations are copied from system telemetry and never reinterpreted",
            ),
        )

    def _on_state(self, message: RobotState) -> None:
        if self.recorder is None:
            return
        now_ns = self.get_clock().now().nanoseconds
        stamp_ns = int(message.header.stamp.sec) * 1_000_000_000 + int(
            message.header.stamp.nanosec
        )
        observation = ObservationSample(
            topic=self.state_topic,
            source=str(message.source),
            seq=int(message.seq),
            fresh=bool(message.fresh),
            joint_names=tuple(message.joint_names),
            positions=tuple(float(item) for item in message.positions),
            velocities=tuple(float(item) for item in message.velocities),
            gripper_position=float(message.gripper_position),
            base_duty=tuple(float(item) for item in message.base_duty),
            battery_voltage=float(message.battery_voltage),
            profile_hash=str(message.profile_hash),
            truth=str(message.truth),
            verification=str(message.verification),
            stamp_ns=stamp_ns,
            received_ns=int(now_ns),
        )
        try:
            self.recorder.record_observation(observation, now_ns)
        except Exception as exc:  # a capture callback must never kill the node
            self._state_errors += 1
            if self._state_errors <= 5:
                self.get_logger().warning(f"state capture failed: {exc}")

    def _capture_tick(self, sample, intent, now_ns: int) -> None:
        if self.recorder is None or self.recorder.faulted:
            return
        tick = self.recorder.begin_tick(now_ns)
        if sample is not None:
            self.recorder.record_input(sample, now_ns, tick_id=tick)
        if intent is not None:
            self.recorder.record_action(intent, now_ns, tick_id=tick)

    def _publish(self, intent, *, seq: int, sample=None) -> None:
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
        self._capture_tick(sample, intent, self.get_clock().now().nanoseconds)

    def _neutral_frame(self) -> InputSample:
        return InputSample(
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

    def _publish_neutral(self) -> None:
        sample = self._neutral_frame()
        self._publish(
            self.mapper.map(self.conditioner.process(sample)), seq=sample.seq, sample=sample
        )
        self._stopped = True

    def _tick(self) -> None:
        if self._stopped:
            return
        if self.recorder is not None and self.recorder.faulted:
            # A capture fault ends the script; the neutral frame is a
            # non-latching abort at the system intake.
            self.get_logger().error("capture faulted; sending a neutral frame and stopping")
            self._publish_neutral()
            return
        now_ns = self.get_clock().now().nanoseconds
        sample = self.source_reader.poll(now_ns)
        if sample is not None:
            conditioned = self.conditioner.process(sample)
            intent = self.mapper.map(conditioned)
            self._last_source_ns = sample.t_source_ns
            self._publish(intent, seq=sample.seq, sample=sample)
            return
        # One explicit neutral frame after the script ends.
        self._publish_neutral()

    def close(self) -> None:
        self.source_reader.close()
        if self.recorder is None:
            return
        self.recorder.record_event(
            "SESSION_CLOSED",
            Severity.INFO,
            self.get_clock().now().nanoseconds,
            detail={"reason": "node_close", "state_errors": self._state_errors},
        )
        summary = self.recorder.close(outcome="unknown", outcome_source="automatic")
        self.get_logger().info(
            f"capture sealed: {summary.capture_path} manifest={summary.manifest_sha256} "
            f"written={summary.written} rejected_observations={summary.rejected_observations} "
            f"fault={summary.fault}"
        )


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
