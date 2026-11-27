"""`jcheng-teleop-preflight`: validate an M6 authorization offline.

Exit codes: 0 = authorization consistent (hardware still blocked), 1 = refused,
2 = configuration error. It opens no system, DDS, device or robot connection.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Sequence

import yaml

from ..core.profile import load_binding, load_profile, resolve_profile
from .authorization import SupervisedAuthorization, SupervisedError
from .preflight import run_preflight

PINNED_CONTRACT = "sha256:afca22a42f7163e0351d185d5a8577b0b51f2f3da4b92278f161a4a7d2c35b1c"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jcheng-teleop-preflight",
        description="Validate a supervised-session authorization offline (no motion)",
    )
    parser.add_argument("--authorization", required=True, help="authorization YAML")
    parser.add_argument("--profile", required=True, help="teleop profile YAML")
    parser.add_argument("--binding", required=True, help="teleop binding YAML")
    parser.add_argument("--contract-hash", default=PINNED_CONTRACT)
    parser.add_argument(
        "--now",
        default="",
        help="ISO 8601 time for the validity check (default: now, UTC)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        resolved = resolve_profile(
            load_profile(Path(args.profile)), load_binding(Path(args.binding))
        )
        raw = yaml.safe_load(Path(args.authorization).read_text(encoding="utf-8"))
        authorization = SupervisedAuthorization.from_mapping(raw)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    try:
        now = (
            datetime.fromisoformat(args.now)
            if args.now
            else datetime.now(timezone.utc)
        )
    except ValueError as exc:
        print(json.dumps({"error": f"--now is not ISO 8601: {exc}"}, sort_keys=True))
        return 2
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    report = run_preflight(
        authorization, resolved, contract_hash=args.contract_hash, now=now
    )
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if report.status == "authorized" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
