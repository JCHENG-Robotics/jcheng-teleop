"""Re-read and verify a sealed capture package.

Verification is read-only: it never repairs, rewrites or deletes a capture. A
failed check makes the capture `invalid`; a capture with dropped rows or a
recorder fault is `degraded` but still readable for diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
from typing import Any

from .provenance import SCHEMA
from .writer import STREAMS

_EXPECTED_SCHEMA = {
    "input": "jcheng.teleop.input.v1",
    "action": "jcheng.teleop.action.v1",
    "command": "jcheng.teleop.command.v1",
    "observation": "jcheng.teleop.observation.v1",
    "events": "jcheng.teleop.event.v1",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


@dataclass
class VerifyReport:
    capture_path: Path
    status: str = "valid"          # valid | degraded | invalid
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    manifest_sha256: str | None = None

    @property
    def ok(self) -> bool:
        return self.status != "invalid"


def verify_capture(root: str | Path, capture_id: str) -> VerifyReport:
    path = Path(root).expanduser() / capture_id
    report = VerifyReport(capture_path=path)
    if not path.is_dir():
        report.status = "invalid"
        report.errors.append(f"capture directory missing: {path}")
        return report
    manifest_path = path / "manifest.json"
    sums_path = path / "SHA256SUMS"
    if not manifest_path.is_file():
        report.status = "invalid"
        report.errors.append("manifest.json missing")
        return report
    if not sums_path.is_file():
        report.status = "invalid"
        report.errors.append("SHA256SUMS missing")
        return report
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.status = "invalid"
        report.errors.append(f"manifest unreadable: {exc}")
        return report
    if manifest.get("schema") != SCHEMA:
        report.errors.append(f"unsupported manifest schema: {manifest.get('schema')!r}")
    report.manifest_sha256 = _sha256_file(manifest_path)
    for field_name in ("capture_id", "created_at", "ended_at", "identity", "environment"):
        if field_name not in manifest:
            report.errors.append(f"manifest field missing: {field_name}")

    files = manifest.get("capture", {}).get("files", [])
    listed = {entry.get("path") for entry in files}
    for name in STREAMS.values():
        if name not in listed:
            report.errors.append(f"stream not listed in manifest: {name}")
    for entry in files:
        file_path = path / str(entry.get("path", ""))
        if file_path.parent != path:
            report.errors.append(f"manifest path escapes the capture: {entry.get('path')!r}")
            continue
        if not file_path.is_file():
            report.errors.append(f"listed file missing: {entry.get('path')}")
            continue
        actual = _sha256_file(file_path)
        if actual != entry.get("sha256"):
            report.errors.append(f"hash mismatch: {entry.get('path')}")

    try:
        sums_lines = sums_path.read_text(encoding="utf-8").splitlines()
        for line in sums_lines:
            if not line.strip():
                continue
            digest, _, name = line.partition("  ")
            file_path = path / name
            if not file_path.is_file():
                report.errors.append(f"SHA256SUMS lists a missing file: {name}")
                continue
            actual = _sha256_file(file_path).split(":", 1)[1]
            if digest != actual:
                report.errors.append(f"SHA256SUMS mismatch: {name}")
    except OSError as exc:
        report.errors.append(f"SHA256SUMS unreadable: {exc}")

    for stream, filename in STREAMS.items():
        file_path = path / filename
        if not file_path.is_file():
            continue
        expected = _EXPECTED_SCHEMA[stream]
        count = 0
        last_tick: int | None = None
        with file_path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    report.errors.append(f"{filename}:{line_no}: invalid JSON: {exc}")
                    continue
                count += 1
                if row.get("schema") != expected:
                    report.errors.append(f"{filename}:{line_no}: unexpected schema")
                tick_id = row.get("tick_id")
                if not isinstance(tick_id, int):
                    report.errors.append(f"{filename}:{line_no}: tick_id missing")
                elif last_tick is not None and stream in {"input", "action"} and tick_id < last_tick:
                    report.errors.append(f"{filename}:{line_no}: tick_id regressed")
                last_tick = tick_id if isinstance(tick_id, int) else last_tick
                t_mono = row.get("t_mono_ns")
                if not isinstance(t_mono, int) or t_mono < 0:
                    report.errors.append(f"{filename}:{line_no}: t_mono_ns invalid")
        report.row_counts[stream] = count

    environment = manifest.get("environment", {}).get("environment_class")
    if environment not in {"mock", "simulation", "hardware"}:
        report.errors.append(f"invalid environment_class: {environment!r}")
    if environment == "simulation" and not manifest.get("environment", {}).get("sim_truth_label"):
        report.errors.append("simulation capture has no sim_truth_label")
    if environment == "hardware":
        session = manifest.get("session", {})
        for name in ("authorization_ref", "operator_id", "session_id"):
            if not session.get(name):
                report.errors.append(f"hardware capture missing {name}")

    if report.errors:
        report.status = "invalid"
    elif manifest.get("capture", {}).get("quality_flags"):
        report.status = "degraded"
        report.warnings.extend(manifest["capture"]["quality_flags"])
    return report
