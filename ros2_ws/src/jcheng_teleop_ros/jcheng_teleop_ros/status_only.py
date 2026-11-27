"""Status-only teleop surface: no ROS, no intent, no motion authority.

This entry point exists so the operator console can show a truthful "no input"
teleop status on a loopback endpoint without starting the test-only intent
publisher. It never imports rclpy, never publishes `TeleopCommand` and never
commands motion. A missing input is reported as stale, never as ready.

The status-only surface is not a production teleop runtime: the operator input
adapter and the lease handoff are still out of scope until the `intent_source`
class is approved in `jcheng-interfaces`.
"""

from __future__ import annotations

import argparse
import time
from typing import Sequence

from jcheng_teleop import __version__

from .status import status_payload
from .status_server import StatusServer

CONTRACT_HASH = (
    "sha256:afca22a42f7163e0351d185d5a8577b0b51f2f3da4b92278f161a4a7d2c35b1c"
)
LIMITATIONS = [
    "read-only status; no lease, intent or motion authority",
    "status-only runtime: no operator input adapter is connected",
]


def snapshot(*, now_mono_ns: int | None = None) -> dict:
    """Return a truthful idle payload: no sample, stale input, phase starting."""
    payload = status_payload(
        teleop_version=__version__,
        contract_hash=CONTRACT_HASH,
        profile_id="status-only",
        profile_hash="none",
        lease_ref=None,
        phase="starting",
        last_wire_seq=0,
        mode=None,
        source_id=None,
        sample_seq=None,
        sample_t_source_ns=None,
        deadman=None,
        input_age_ms=None,
        capture={"state": "no input adapter"},
        now_mono_ns=time.monotonic_ns() if now_mono_ns is None else now_mono_ns,
    )
    payload["limitations"] = list(LIMITATIONS)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Loopback-only teleop status surface (no input, no motion)"
    )
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args(argv)

    server = StatusServer(lambda: snapshot(), port=args.port)
    server.start()
    print(
        f"teleop status-only listening on http://127.0.0.1:{server.port}/v1/status",
        flush=True,
    )
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
