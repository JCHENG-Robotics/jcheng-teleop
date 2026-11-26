from __future__ import annotations

import json

from jcheng_teleop.adapters.input.virtual import VirtualInputSource
from jcheng_teleop.core.clock import ManualClock
from jcheng_teleop.core.model import Mode
from jcheng_teleop.core.runner import TeleopRunner
from conftest import make_sample, make_session, write_resolved


def _samples(resolved, count=8):
    return [
        make_sample(
            resolved,
            index,
            values=((0.2,) + (0.0,) * (resolved.joint_count - 1)),
            deadman=index < count - 2,
            t_ns=index * 20_000_000,
        )
        for index in range(count)
    ]


def _trace(resolved):
    session, gateway, clock = make_session(resolved)
    source = VirtualInputSource(_samples(resolved))
    runner = TeleopRunner(session=session, source=source, clock=clock, tick_ns=20_000_000)
    results = runner.run_ticks(8)
    return [json.dumps(result.to_dict(), sort_keys=True) for result in results]


def test_same_script_is_byte_identical(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    assert _trace(resolved) == _trace(resolved)


def test_rate_gate_and_deadman_stop_are_deterministic(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    trace = _trace(resolved)
    parsed = [json.loads(line) for line in trace]
    assert any(item["submitted"] for item in parsed)
    assert any(item["stop_sent"] for item in parsed)
