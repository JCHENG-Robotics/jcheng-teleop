"""M5 read-only teleop status payload and loopback server tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from jcheng_teleop_ros.status import SCHEMA, status_payload
from jcheng_teleop_ros.status_server import StatusServer

HASH = "sha256:" + "1" * 64


def _payload(**overrides):
    base = dict(
        teleop_version="0.3.0",
        contract_hash=HASH,
        profile_id="armpi_ultra_demo",
        profile_hash=HASH,
        lease_ref=HASH,
        phase="running",
        last_wire_seq=12,
        mode="JOINT_VELOCITY",
        source_id="ros_virtual",
        sample_seq=13,
        sample_t_source_ns=260_000_000,
        deadman=True,
        input_age_ms=20.0,
        capture={"enabled": False},
        now_mono_ns=1_000_000_000,
    )
    base.update(overrides)
    return status_payload(**base)


def test_payload_is_read_only_and_fresh() -> None:
    payload = _payload()
    assert payload["schema"] == SCHEMA
    assert payload["input"]["stale"] is False
    assert payload["input"]["deadman"] is True
    assert payload["lease_ref"] == HASH
    assert "no lease, intent or motion authority" in payload["limitations"][0]


def test_missing_input_is_stale_not_ready() -> None:
    payload = _payload(
        sample_seq=None,
        sample_t_source_ns=None,
        deadman=None,
        mode=None,
        source_id=None,
        input_age_ms=None,
    )
    assert payload["input"]["present"] is False
    assert payload["input"]["stale"] is True


def test_old_input_is_stale() -> None:
    payload = _payload(input_age_ms=1500.0)
    assert payload["input"]["stale"] is True


def test_unsupported_phase_is_rejected() -> None:
    with pytest.raises(ValueError, match="phase"):
        _payload(phase="ready")


def test_server_serves_one_read_only_route() -> None:
    payload = _payload()
    server = StatusServer(lambda: payload)
    server.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/v1/status", timeout=5
        ) as response:
            assert response.status == 200
            body = json.loads(response.read())
            assert body["schema"] == SCHEMA
        with pytest.raises(urllib.error.HTTPError) as not_found:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.port}/v1/stop", timeout=5
            )
        assert not_found.value.code == 404
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/v1/status", method="POST", data=b"{}"
        )
        with pytest.raises(urllib.error.HTTPError) as method_not_allowed:
            urllib.request.urlopen(request, timeout=5)
        assert method_not_allowed.value.code == 405
    finally:
        server.stop()


def test_server_refuses_a_non_loopback_bind() -> None:
    with pytest.raises(ValueError, match="loopback"):
        StatusServer(lambda: {}, host="0.0.0.0")
