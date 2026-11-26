from __future__ import annotations

from jcheng_teleop.core.deadman import DeadmanTracker
from conftest import make_sample, write_resolved


def test_engage_release_reengage(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    tracker = DeadmanTracker(300_000_000)
    assert tracker.update(make_sample(resolved, 0, deadman=False), 0).enabled is False
    engaged = tracker.update(make_sample(resolved, 1, deadman=True), 1)
    assert engaged.enabled is True
    assert [event.code for event in engaged.events] == ["DEADMAN_ENGAGED"]
    released = tracker.update(make_sample(resolved, 2, deadman=False), 2)
    assert released.enabled is False
    assert [event.code for event in released.events] == ["DEADMAN_RELEASED"]
    assert tracker.update(make_sample(resolved, 3, deadman=True), 3).enabled is True


def test_timeout_blocks_until_release(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    tracker = DeadmanTracker(300_000_000)
    tracker.update(make_sample(resolved, 0, deadman=True), 0)
    assert tracker.check(299_000_000).expired is False
    expired = tracker.check(300_000_000)
    assert expired.expired is True
    assert [event.code for event in expired.events] == ["INPUT_STALE"]
    assert tracker.update(make_sample(resolved, 1, deadman=True, t_ns=302_000_000), 302_000_000).enabled is False
    assert tracker.update(make_sample(resolved, 2, deadman=False, t_ns=303_000_000), 303_000_000).enabled is False
    assert tracker.update(make_sample(resolved, 3, deadman=True, t_ns=304_000_000), 304_000_000).enabled is True


def test_block_requires_release_and_new_edge(tmp_path):
    resolved = write_resolved(tmp_path, joints=1)
    tracker = DeadmanTracker(300_000_000)
    tracker.update(make_sample(resolved, 0, deadman=True), 0)
    tracker.block()
    assert tracker.update(make_sample(resolved, 1, deadman=True, t_ns=1_000_000), 1_000_000).enabled is False
    assert tracker.update(make_sample(resolved, 2, deadman=False, t_ns=2_000_000), 2_000_000).enabled is False
    assert tracker.update(make_sample(resolved, 3, deadman=True, t_ns=3_000_000), 3_000_000).enabled is True
