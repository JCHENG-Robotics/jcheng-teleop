"""Newline-delimited JSON input transport.

The file/stream is produced by an operator-side adapter. This module parses
the documented sample contract; it does not open a device.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TextIO

from ...core.model import InputSample
from .base import InputHealth


class JsonlInputSource:
    def __init__(self, path: str | Path | TextIO) -> None:
        self._path = path
        self._rows: list[InputSample] | None = None
        self._index = 0
        self._opened = False
        self._health = InputHealth("CLOSED")
        self._last: int | None = None

    def _load(self) -> list[InputSample]:
        if self._rows is not None:
            return self._rows
        if hasattr(self._path, "read"):
            text = self._path.read()  # type: ignore[union-attr]
        else:
            text = Path(self._path).read_text(encoding="utf-8")
        rows: list[InputSample] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("row must be an object")
                rows.append(InputSample.from_mapping(value))
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{self._path}:{line_number}: {exc}") from exc
        self._rows = rows
        return rows

    def open(self) -> None:
        self._load()
        self._opened = True
        self._health = InputHealth("READY")

    def poll(self, now_ns: int) -> InputSample | None:
        if not self._opened:
            raise RuntimeError("input source is not open")
        rows = self._rows or []
        if self._index >= len(rows):
            self._health = InputHealth("CLOSED", "jsonl exhausted", self._last)
            return None
        sample = rows[self._index]
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
