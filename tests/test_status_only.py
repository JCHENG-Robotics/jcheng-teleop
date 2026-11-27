"""Status-only teleop surface: truthful idle payload, loopback, no ROS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from jcheng_teleop_ros.status import SCHEMA
from jcheng_teleop_ros.status_only import LIMITATIONS, snapshot
from jcheng_teleop_ros.status_server import StatusServer

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = yaml.safe_load((ROOT / "capability.yaml").read_text(encoding="utf-8"))


def test_snapshot_reports_no_input_as_stale() -> None:
    payload = snapshot(now_mono_ns=1_000_000_000)

    assert payload["schema"] == SCHEMA
    assert payload["phase"] == "starting"
    assert payload["input"]["present"] is False
    assert payload["input"]["stale"] is True
    assert payload["input"]["age_ms"] is None
    assert payload["input"]["deadman"] is None
    assert payload["lease_ref"] is None
    assert payload["last_wire_seq"] == 0
    assert payload["contract_hash"] == MANIFEST["contract"]["contract_hash"]
    assert payload["limitations"] == LIMITATIONS


def test_status_only_module_does_not_import_ros() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(ROOT / "src"),
            str(ROOT / "ros2_ws" / "src" / "jcheng_teleop_ros"),
        ]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import jcheng_teleop_ros.status_only, sys; "
            "print('rclpy' in sys.modules)",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_server_serves_only_get_status() -> None:
    server = StatusServer(lambda: snapshot(now_mono_ns=1), port=0)
    server.start()
    try:
        base = f"http://127.0.0.1:{server.port}"
        with urllib.request.urlopen(f"{base}/v1/status", timeout=3) as response:
            payload = json.load(response)
        assert response.status == 200
        assert payload["schema"] == SCHEMA
        assert payload["input"]["stale"] is True

        for path, method, expected in (
            ("/v1/status", "POST", 405),
            ("/v1/stop", "GET", 404),
        ):
            request = urllib.request.Request(
                f"{base}{path}", method=method, data=b"" if method == "POST" else None
            )
            try:
                urllib.request.urlopen(request, timeout=3)
            except urllib.error.HTTPError as exc:
                assert exc.code == expected
            else:  # pragma: no cover - defensive
                raise AssertionError(f"{method} {path} should return {expected}")
    finally:
        server.stop()
