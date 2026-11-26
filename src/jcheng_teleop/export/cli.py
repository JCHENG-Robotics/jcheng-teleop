"""`jcheng-teleop-index`: build a mixed-source index from sealed captures.

Offline and read-only over captures; it writes the index outside any git
worktree. It does not train, copy rows or call the learning writer.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .mixed import DatasetError, build_index, capture_entry, write_index


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jcheng-teleop-index",
        description="Build a jcheng.teleop.dataset.v1 index (no training, no copy)",
    )
    parser.add_argument("--capture-root", required=True, help="data root outside git")
    parser.add_argument(
        "--capture-id",
        action="append",
        required=True,
        help="capture id under the root (repeat for each episode)",
    )
    parser.add_argument("--out", required=True, help="index JSON path outside git")
    parser.add_argument("--allow-external-corrections", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        entries = [capture_entry(args.capture_root, capture_id) for capture_id in args.capture_id]
        index = build_index(
            entries,
            allow_external_corrections=args.allow_external_corrections,
        )
        written = write_index(args.out, index)
    except (DatasetError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"index": index["counts"], "written": written}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
