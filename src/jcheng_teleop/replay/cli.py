"""`jcheng-teleop-replay`: re-read a capture, replay inputs, scan anomalies.

Exit codes: 0 = clean, 1 = divergence or anomaly error, 2 = setup/verification
error. The command is offline: it opens no gateway, socket, DDS graph or device.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from ..core.profile import load_binding, load_profile, resolve_profile
from .anomaly import scan_streams
from .capture_reader import ReplayError, read_capture
from .replay import replay_capture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jcheng-teleop-replay",
        description="Offline capture replay and anomaly scan (no gateway, no device)",
    )
    parser.add_argument("--capture-root", required=True, help="data root outside git")
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--profile", required=True, help="teleop profile YAML")
    parser.add_argument("--binding", required=True, help="teleop binding YAML")
    parser.add_argument("--max-divergences", type=int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        capture = read_capture(Path(args.capture_root), args.capture_id)
    except (ReplayError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    try:
        resolved = resolve_profile(
            load_profile(Path(args.profile)), load_binding(Path(args.binding))
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": f"profile error: {exc}"}, sort_keys=True))
        return 2
    identity = capture.manifest.get("identity", {})
    if identity.get("profile_hash") != resolved.profile_hash:
        print(
            json.dumps(
                {
                    "error": "capture profile_hash does not match the supplied profile",
                    "capture_profile_hash": identity.get("profile_hash"),
                    "supplied_profile_hash": resolved.profile_hash,
                },
                sort_keys=True,
            )
        )
        return 2
    if identity.get("binding_hash") != resolved.binding.binding_hash:
        print(
            json.dumps(
                {
                    "error": "capture binding_hash does not match the supplied binding",
                    "capture_binding_hash": identity.get("binding_hash"),
                    "supplied_binding_hash": resolved.binding.binding_hash,
                },
                sort_keys=True,
            )
        )
        return 2

    replay_report = replay_capture(capture, resolved)
    anomaly_report = scan_streams(capture.streams, capture.environment_class)
    payload = {
        "capture_id": capture.capture_id,
        "environment_class": capture.environment_class,
        "replay": replay_report.to_dict(),
        "anomalies": {
            "status": anomaly_report.status,
            "errors": anomaly_report.errors,
            "warnings": anomaly_report.warnings,
            "metrics": anomaly_report.metrics,
        },
    }
    divergences = payload["replay"]["divergences"]
    if len(divergences) > args.max_divergences:
        payload["replay"]["divergences"] = divergences[: args.max_divergences]
        payload["replay"]["divergences_truncated"] = len(divergences)
    print(json.dumps(payload, sort_keys=True))
    return 0 if replay_report.ok and anomaly_report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
