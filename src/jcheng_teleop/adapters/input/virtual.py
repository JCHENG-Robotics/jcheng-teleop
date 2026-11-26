"""Scripted input source for deterministic tests and the M1 CLI."""

from __future__ import annotations

from typing import Iterable

from ...core.model import InputSample
from .base import InputHealth


class VirtualInputSource:
    def __init__(self, samples: Iterable[InputSample], *, respect_time: bool = True) -> None:
        self._samples = list(samples)
        self._index = 0
        self._respect_time = respect_time
        self._opened = False
        self._health = InputHealth("CLOSED")
        self._last: int | None = None

    def open(self) -> None:
        self._opened = True
        self._health = InputHealth("READY")

    def poll(self, now_ns: int) -> InputSample | None:
        if not self._opened:
            raise RuntimeError("input source is not open")
        if self._index >= len(self._samples):
            self._health = InputHealth("CLOSED", "script exhausted", self._last)
            return None
        sample = self._samples[self._index]
        if self._respect_time and sample.t_host_mono_ns > now_ns:
            return None
        self._index += 1
        self._last = sample.t_host_mono_ns
        self._health = InputHealth("STREAMING", "", self._last)
        return sample

    def close(self) -> None:
        self._opened = False
        self._health = InputHealth("CLOSED", "", self._last)

    @property
    def health(self) -> InputHealth:
        return self._health
