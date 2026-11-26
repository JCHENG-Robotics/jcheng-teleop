"""Mixed-source dataset index (M7, teleop-local).

This is an **index**, not a training dataset: it verifies sealed captures and
points at them with per-episode provenance. It never copies rows, never
flattens the environment class and never writes a learning `jcheng.dataset.v1`
dataset (that contract is not frozen and forbids mixing source classes).

A correction episode must reference the policy capture/tick/action it corrects;
the reference is checked inside the indexed set unless explicitly allowed to be
external.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from ..capture.provenance import ENVIRONMENT_CLASSES, SOURCE_CLASSES
from ..capture.verify import verify_capture
from ..capture.writer import assert_outside_git

SCHEMA = "jcheng.teleop.dataset.v1"
CAPTURE_SCHEMA = "jcheng.teleop.capture.v1"
_SHA256_LEN = 71


class DatasetError(ValueError):
    pass


@dataclass(frozen=True)
class CaptureEntry:
    capture_id: str
    manifest: dict[str, Any]
    manifest_sha256: str

    @property
    def environment_class(self) -> str:
        return str(self.manifest.get("environment", {}).get("environment_class", ""))

    @property
    def source_class(self) -> str:
        return str(self.manifest.get("environment", {}).get("source_class", ""))

    @property
    def correction(self) -> dict[str, Any]:
        value = self.manifest.get("correction")
        return value if isinstance(value, dict) else {}


def capture_entry(root: str | Path, capture_id: str) -> CaptureEntry:
    path = Path(root).expanduser()
    report = verify_capture(path, capture_id)
    if not report.ok:
        raise DatasetError(
            f"{capture_id}: capture failed verification: " + "; ".join(report.errors[:3])
        )
    manifest_path = path / capture_id / "manifest.json"
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    return CaptureEntry(
        capture_id=capture_id,
        manifest=manifest,
        manifest_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
    )


def build_index(
    entries: Iterable[CaptureEntry],
    *,
    allow_external_corrections: bool = False,
) -> dict[str, Any]:
    items = list(entries)
    if not items:
        raise DatasetError("at least one capture is required")
    seen: set[str] = set()
    for entry in items:
        if entry.manifest.get("schema") != CAPTURE_SCHEMA:
            raise DatasetError(f"{entry.capture_id}: unsupported capture schema")
        if entry.capture_id in seen:
            raise DatasetError(f"duplicate capture_id: {entry.capture_id}")
        seen.add(entry.capture_id)
        if entry.environment_class not in ENVIRONMENT_CLASSES:
            raise DatasetError(
                f"{entry.capture_id}: unsupported environment {entry.environment_class!r}"
            )
        if entry.source_class not in SOURCE_CLASSES:
            raise DatasetError(
                f"{entry.capture_id}: unsupported source class {entry.source_class!r}"
            )
        if not (
            isinstance(entry.manifest_sha256, str)
            and entry.manifest_sha256.startswith("sha256:")
            and len(entry.manifest_sha256) == _SHA256_LEN
        ):
            raise DatasetError(f"{entry.capture_id}: invalid manifest hash")
        correction = entry.correction
        source_id = correction.get("corrected_from_capture_id")
        if source_id is not None:
            if entry.source_class != "human_correction":
                raise DatasetError(
                    f"{entry.capture_id}: correction reference without human_correction"
                )
            if source_id == entry.capture_id:
                raise DatasetError(f"{entry.capture_id}: a correction cannot reference itself")
            if source_id not in seen and not allow_external_corrections:
                # The referenced capture may appear later in the input list.
                if source_id not in {item.capture_id for item in items}:
                    raise DatasetError(
                        f"{entry.capture_id}: corrected_from capture {source_id!r} "
                        "is not in the index"
                    )

    episodes = []
    groups: dict[str, list[str]] = {}
    environments: set[str] = set()
    for entry in sorted(items, key=lambda item: item.capture_id):
        identity = entry.manifest.get("identity", {})
        policy = entry.manifest.get("policy", {})
        correction = entry.correction
        groups.setdefault(entry.source_class, []).append(entry.capture_id)
        environments.add(entry.environment_class)
        episodes.append(
            {
                "capture_id": entry.capture_id,
                "manifest_sha256": entry.manifest_sha256,
                "environment_class": entry.environment_class,
                "source_class": entry.source_class,
                "profile_id": identity.get("profile_id"),
                "profile_hash": identity.get("profile_hash"),
                "contract_hash": entry.manifest.get("contract_hash"),
                "policy_id": policy.get("policy_id"),
                "policy_version": policy.get("policy_version"),
                "corrected_from_capture_id": correction.get("corrected_from_capture_id"),
                "corrected_from_tick_id": correction.get("corrected_from_tick_id"),
                "policy_action_seq": correction.get("policy_action_seq"),
                "task_id": entry.manifest.get("task", {}).get("task_id"),
                "outcome": entry.manifest.get("task", {}).get("outcome"),
            }
        )
    return {
        "schema": SCHEMA,
        "episodes": episodes,
        "groups": {name: sorted(ids) for name, ids in sorted(groups.items())},
        "counts": {
            "episodes": len(episodes),
            "per_source_class": {
                name: len(ids) for name, ids in sorted(groups.items())
            },
            "per_environment": {
                name: sum(1 for ep in episodes if ep["environment_class"] == name)
                for name in sorted(environments)
            },
        },
        "mixed_source_classes": len(groups) > 1,
        "mixed_environments": len(environments) > 1,
        "allow_external_corrections": bool(allow_external_corrections),
        "limitations": [
            "teleop-local index, not a jcheng.dataset.v1 training dataset",
            "learning dataset v1 forbids mixing source classes; split by groups",
            "environment_class is per episode and is never flattened",
            "manifest hashes point at sealed captures; capture data stays outside git",
        ],
    }


def write_index(path: str | Path, index: dict[str, Any]) -> dict[str, Any]:
    output = Path(path).expanduser().resolve()
    assert_outside_git(output)
    text = json.dumps(index, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return {
        "path": str(output),
        "bytes": len(text.encode("utf-8")),
        "sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
