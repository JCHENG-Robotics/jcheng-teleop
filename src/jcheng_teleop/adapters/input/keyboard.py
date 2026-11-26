"""Device-free keyboard adapter.

Key events come from an injected ``KeySource`` (a terminal wrapper is
operator-side). The adapter does not read a device file or use a device API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ...core.model import InputSample, Mode
from .base import InputHealth


class KeySource(Protocol):
    def poll(self) -> str | None: ...


class ScriptedKeySource:
    def __init__(self, events: list[str]) -> None:
        self._events = list(events)
        self._index = 0

    def poll(self) -> str | None:
        if self._index >= len(self._events):
            return None
        event = self._events[self._index]
        self._index += 1
        return event


@dataclass(frozen=True)
class KeyboardMapping:
    joint_keys: dict[str, tuple[int, float]] = field(
        default_factory=lambda: {
            "w": (0, 1.0),
            "s": (0, -1.0),
            "a": (1, 1.0),
            "d": (1, -1.0),
            "q": (2, 1.0),
            "e": (2, -1.0),
            "r": (3, 1.0),
            "f": (3, -1.0),
            "t": (4, 1.0),
            "g": (4, -1.0),
        }
    )
    deadman_key: str = "space"
    stop_key: str = "esc"


class KeyboardInputSource:
    def __init__(
        self,
        keys: KeySource,
        *,
        joint_count: int,
        profile_id: str | None = None,
        mapping: KeyboardMapping | None = None,
        source_id: str = "keyboard_01",
    ) -> None:
        if joint_count <= 0:
            raise ValueError("joint_count must be positive")
        self.keys = keys
        self.joint_count = joint_count
        self.profile_id = profile_id
        self.mapping = mapping or KeyboardMapping()
        self.source_id = source_id
        self._held: set[str] = set()
        self._stopped = False
        self._seq = 0
        self._opened = False
        self._health = InputHealth("CLOSED")
        self._last: int | None = None

    def open(self) -> None:
        self._opened = True
        self._health = InputHealth("READY")

    def _drain(self) -> None:
        # One event per poll keeps ordering deterministic; a terminal wrapper
        # may call poll at a higher rate than the control tick.
        event = self.keys.poll()
        if event is None:
            return
        token = event.strip().lower()
        if not token:
            return
        if token.endswith("_down"):
            key = token[:-5]
            self._held.add(key)
            if key == self.mapping.stop_key:
                self._stopped = True
        elif token.endswith("_up"):
            key = token[:-3]
            self._held.discard(key)
        elif token in self.mapping.joint_keys or token in {self.mapping.deadman_key, self.mapping.stop_key}:
            self._held.add(token)
            if token == self.mapping.stop_key:
                self._stopped = True
        else:
            # A bare token is a tap; it remains held until an explicit _up.
            self._held.add(token)
            if token == self.mapping.stop_key:
                self._stopped = True

    def poll(self, now_ns: int) -> InputSample | None:
        if not self._opened:
            raise RuntimeError("input source is not open")
        self._drain()
        values = [0.0] * self.joint_count
        for key, (joint, sign) in self.mapping.joint_keys.items():
            if key in self._held and joint < self.joint_count:
                values[joint] += sign
        deadman = self.mapping.deadman_key in self._held and not self._stopped
        if self._stopped:
            values = [0.0] * self.joint_count
        self._seq += 1
        sample = InputSample(
            schema=InputSample.SCHEMA,
            source_id=self.source_id,
            source_class="keyboard",
            seq=self._seq,
            t_source_ns=now_ns,
            t_host_mono_ns=now_ns,
            mode=Mode.JOINT_VELOCITY,
            joint_velocities_rad_s=tuple(values),
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
