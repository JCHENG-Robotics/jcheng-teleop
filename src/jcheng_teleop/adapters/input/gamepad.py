"""Device-free gamepad mapping.

A real gamepad driver is operator-side and emits a normalized ``JoyFrame``.
This module owns the mapping to teleoperation samples, not the device.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ...core.model import InputSample, Mode
from .base import InputHealth


@dataclass(frozen=True)
class JoyFrame:
    axes: tuple[float, ...] = ()
    buttons: tuple[bool, ...] = ()


class JoySource(Protocol):
    def poll(self) -> JoyFrame | None: ...


class VirtualJoySource:
    def __init__(self, frames: list[JoyFrame]) -> None:
        self._frames = list(frames)
        self._index = 0

    def poll(self) -> JoyFrame | None:
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame


@dataclass(frozen=True)
class GamepadMapping:
    axes: tuple[int, ...] = (0, 1, 2, 3, 4)
    signs: tuple[float, ...] = (1.0, 1.0, 1.0, 1.0, 1.0)
    deadzone: float = 0.08
    deadman_button: int = 0
    stop_button: int = 1
    gripper_axis: int | None = 5

    def __post_init__(self) -> None:
        if len(self.axes) != len(self.signs):
            raise ValueError("axes and signs must have the same length")
        if self.deadzone < 0:
            raise ValueError("deadzone must be non-negative")


class GamepadInputSource:
    def __init__(
        self,
        joy: JoySource,
        *,
        joint_count: int,
        profile_id: str | None = None,
        mapping: GamepadMapping | None = None,
        source_id: str = "gamepad_01",
    ) -> None:
        if joint_count <= 0:
            raise ValueError("joint_count must be positive")
        self.joy = joy
        self.joint_count = joint_count
        self.profile_id = profile_id
        self.mapping = mapping or GamepadMapping()
        if len(self.mapping.axes) > joint_count:
            raise ValueError("mapping has more axes than joints")
        if len(set(self.mapping.axes)) != len(self.mapping.axes):
            raise ValueError("mapping axes must be unique")
        self.source_id = source_id
        self._seq = 0
        self._opened = False
        self._health = InputHealth("CLOSED")
        self._last: int | None = None

    def open(self) -> None:
        self._opened = True
        self._health = InputHealth("READY")

    def _axis(self, frame: JoyFrame, index: int) -> float:
        if index < 0 or index >= len(frame.axes):
            return 0.0
        value = float(frame.axes[index])
        if abs(value) <= self.mapping.deadzone:
            return 0.0
        return max(-1.0, min(1.0, value))

    def poll(self, now_ns: int) -> InputSample | None:
        if not self._opened:
            raise RuntimeError("input source is not open")
        frame = self.joy.poll()
        if frame is None:
            self._health = InputHealth("STALE", "no joy frame", self._last)
            return None
        values = [0.0] * self.joint_count
        for joint_index, (axis, sign) in enumerate(zip(self.mapping.axes, self.mapping.signs)):
            if joint_index < len(values):
                values[joint_index] = self._axis(frame, axis) * sign
        deadman = bool(
            self.mapping.deadman_button < len(frame.buttons)
            and frame.buttons[self.mapping.deadman_button]
        )
        stopped = bool(
            self.mapping.stop_button < len(frame.buttons)
            and frame.buttons[self.mapping.stop_button]
        )
        if stopped:
            values = [0.0] * self.joint_count
            deadman = False
        gripper = None
        if self.mapping.gripper_axis is not None:
            raw = self._axis(frame, self.mapping.gripper_axis)
            if abs(raw) >= 0.05:
                gripper = max(0.0, min(1.0, (raw + 1.0) / 2.0))
        self._seq += 1
        sample = InputSample(
            schema=InputSample.SCHEMA,
            source_id=self.source_id,
            source_class="gamepad",
            seq=self._seq,
            t_source_ns=now_ns,
            t_host_mono_ns=now_ns,
            mode=Mode.JOINT_VELOCITY,
            joint_velocities_rad_s=tuple(values),
            gripper_normalized=gripper,
            gripper_valid=gripper is not None,
            deadman=deadman,
            profile_id=self.profile_id,
        )
        self._last = now_ns
        self._health = InputHealth("STREAMING", "", self._last)
        return sample

    def close(self) -> None:
        self._opened = False
        self._health = InputHealth("CLOSED", "", self._last)

    @property
    def health(self) -> InputHealth:
        return self._health
