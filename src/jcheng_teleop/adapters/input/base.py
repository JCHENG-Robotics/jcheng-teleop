"""Input source protocol and health."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...core.model import InputSample


@dataclass(frozen=True)
class InputHealth:
    state: str = "CLOSED"
    message: str = ""
    last_sample_ns: int | None = None


class InputSource(Protocol):
    def open(self) -> None: ...

    def poll(self, now_ns: int) -> InputSample | None: ...

    def close(self) -> None: ...

    @property
    def health(self) -> InputHealth: ...
