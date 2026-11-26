"""Read a sealed capture for offline replay.

The reader verifies the package first: a capture that does not pass hash and
schema verification is not replayed. It never writes to the capture.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..capture.verify import VerifyReport, verify_capture
from ..capture.writer import STREAMS


class ReplayError(ValueError):
    pass


@dataclass(frozen=True)
class CaptureData:
    root: Path
    capture_id: str
    manifest: dict[str, Any]
    streams: dict[str, list[dict[str, Any]]]
    verification: VerifyReport

    @property
    def environment_class(self) -> str:
        return str(self.manifest.get("environment", {}).get("environment_class", ""))

    def stream(self, name: str) -> list[dict[str, Any]]:
        return self.streams.get(name, [])


def read_capture(root: str | Path, capture_id: str) -> CaptureData:
    path = Path(root).expanduser()
    report = verify_capture(path, capture_id)
    if not report.ok:
        raise ReplayError(
            "capture failed verification: " + "; ".join(report.errors[:3])
        )
    capture_path = path / capture_id
    manifest = json.loads((capture_path / "manifest.json").read_text(encoding="utf-8"))
    streams: dict[str, list[dict[str, Any]]] = {}
    for name, filename in STREAMS.items():
        rows: list[dict[str, Any]] = []
        with (capture_path / filename).open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        streams[name] = rows
    return CaptureData(
        root=path, capture_id=capture_id, manifest=manifest, streams=streams,
        verification=report,
    )
