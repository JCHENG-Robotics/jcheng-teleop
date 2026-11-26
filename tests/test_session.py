from __future__ import annotations

from jcheng_teleop.core.model import Mode, SessionState
from conftest import make_sample, make_session, write_resolved


def _activate(session, resolved, *, values=(0.2, 0.0, 0.0, 0.0, 0.0), t_ns=0):
    sample = make_sample(resolved, 0, values=values, deadman=True, t_ns=t_ns)
    events = session.on_sample(sample)
    result = session.tick(t_ns)
    return sample, events, result


def test_start_acquires_lease_and_idles(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    assert session.state is SessionState.IDLE
    assert session.lease is not None
    assert gateway.acquire_requests[0].priority == 40
    assert gateway.acquire_requests[0].deadman_required is True


def test_enable_edge_activates_and_submits(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _, events, result = _activate(session, resolved)
    assert session.state is SessionState.ACTIVE
    assert result.submitted is True
    assert len(gateway.submitted) == 1
    assert gateway.submitted[0].joint_velocities_rad_s[0] == 0.2
    assert gateway.submitted[0].lease_id == session.lease.lease_id
    assert any(event.code == "DEADMAN_ENGAGED" for event in events)


def test_no_intent_before_enable(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    session.on_sample(make_sample(resolved, 0, values=(0.0,) * 5, deadman=False, t_ns=0))
    result = session.tick(0)
    assert result.submitted is False
    assert gateway.submitted == []
    assert session.state is SessionState.READY


def test_one_submit_per_tick(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    session.tick(10_000_000)  # less than one tick
    assert len(gateway.submitted) == 1


def test_deadman_release_is_session_abort_not_system_stop(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    session.on_sample(make_sample(resolved, 1, values=(0.0,) * 5, deadman=False, t_ns=20_000_000))
    result = session.tick(20_000_000)
    assert result.stop_sent is True
    assert session.state is SessionState.IDLE
    assert gateway.stop_requests == []
    assert gateway.submitted[-1].deadman is False
    assert gateway.submitted[-1].joint_velocities_rad_s[0] == 0.0
    assert sum(1 for intent in gateway.submitted if intent.deadman is False) == 1
    session.tick(40_000_000)
    assert sum(1 for intent in gateway.submitted if intent.deadman is False) == 1


def test_no_auto_resume_after_stop(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    session.on_sample(make_sample(resolved, 1, values=(0.0,) * 5, deadman=False, t_ns=20_000_000))
    session.tick(20_000_000)
    session.on_sample(make_sample(resolved, 2, values=(0.2,) * 5, deadman=True, t_ns=40_000_000))
    result = session.tick(40_000_000)
    assert result.submitted is False
    assert session.state is SessionState.IDLE
    assert len(gateway.submitted) == 2  # initial + stop intent


def test_input_timeout_stops(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, clock = make_session(resolved)
    _activate(session, resolved)
    result = None
    for tick in range(1, 17):
        now = tick * 20_000_000
        clock.set(now)
        result = session.tick(now)
        if result.stop_sent:
            break
    assert result is not None and result.stop_sent is True
    assert session.state is SessionState.IDLE
    assert any(
        event.code == "SESSION_ABORT" and event.detail.get("reason") == "deadman_timeout"
        for event in result.events
    )
    assert gateway.stop_requests == []


def test_lease_loss_stops_session_and_preempts(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, clock = make_session(resolved)
    _activate(session, resolved)
    for tick in range(1, 17):
        now = tick * 20_000_000
        clock.set(now)
        session.on_sample(make_sample(resolved, tick, values=(0.1,) * 5, deadman=True, t_ns=now))
        session.tick(now)
    gateway.revoke(session.lease.lease_id)
    clock.set(340_000_000)
    session.on_sample(make_sample(resolved, 17, values=(0.1,) * 5, deadman=True, t_ns=340_000_000))
    result = session.tick(340_000_000)
    assert result.stop_sent is True
    assert session.state is SessionState.PREEMPTED
    assert any(event.code == "SESSION_PREEMPTED" for event in result.events)
    assert session.lease is None


def test_unknown_outcome_requests_system_stop_and_faults(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    gateway.fail("submit_unknown")
    result = session.tick(20_000_000)
    assert result.gateway_result is not None
    assert result.gateway_result.outcome == "UNKNOWN"
    assert session.state is SessionState.FAULT
    assert gateway.stop_requests == ["gateway_unknown"]


def test_unavailable_gateway_faults_without_retry(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    gateway.fail("submit_unavailable")
    result = session.tick(20_000_000)
    assert session.state is SessionState.FAULT
    assert result.submitted is False
    assert len(gateway.stop_requests) == 1


def test_unsupported_position_mode_is_not_emulated(tmp_path):
    resolved = write_resolved(tmp_path, joints=2, modes=("JOINT_VELOCITY", "JOINT_POSITION"))
    session, gateway, _ = make_session(resolved)
    session.on_sample(
        make_sample(resolved, 0, values=(0.1, 0.2), mode=Mode.JOINT_POSITION, deadman=True, t_ns=0)
    )
    result = session.tick(0)
    assert result.submitted is False
    assert session.state is SessionState.IDLE
    assert gateway.submitted == []


def test_duplicate_sequence_stops(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    # Same seq, different timestamp: this must be rejected, not reused.
    session.on_sample(make_sample(resolved, 0, values=(0.1,) * 5, deadman=True, t_ns=20_000_000))
    result = session.tick(20_000_000)
    assert session.state is SessionState.IDLE
    assert any(event.code == "SEQ_DUPLICATE" for event in result.events)


def test_mode_change_stops_and_requires_rearm(tmp_path):
    resolved = write_resolved(tmp_path, joints=2, modes=("JOINT_VELOCITY", "JOINT_POSITION"))
    session, gateway, clock = make_session(resolved)
    _activate(session, resolved, values=(0.1, 0.0))
    session.on_sample(
        make_sample(resolved, 1, values=(0.2, 0.2), mode=Mode.JOINT_POSITION, deadman=True, t_ns=20_000_000)
    )
    result = session.tick(20_000_000)
    assert session.state is SessionState.IDLE
    assert any(event.code == "SESSION_ABORT" and event.detail.get("reason") == "mode_change" for event in result.events)


def test_release_then_repress_in_same_tick_does_not_skip_stop(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    session.on_sample(make_sample(resolved, 1, values=(0.1,) * 5, deadman=False, t_ns=20_000_000))
    session.on_sample(make_sample(resolved, 2, values=(0.1,) * 5, deadman=True, t_ns=20_000_000))
    result = session.tick(20_000_000)
    assert result.stop_sent is True
    assert session.state is SessionState.IDLE


def test_reset_after_preemption_requires_new_edge(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, clock = make_session(resolved)
    _activate(session, resolved)
    for tick in range(1, 17):
        now = tick * 20_000_000
        clock.set(now)
        session.on_sample(make_sample(resolved, tick, values=(0.1,) * 5, deadman=True, t_ns=now))
        session.tick(now)
    gateway.revoke(session.lease.lease_id)
    clock.set(340_000_000)
    session.on_sample(make_sample(resolved, 17, values=(0.1,) * 5, deadman=True, t_ns=340_000_000))
    session.tick(340_000_000)
    assert session.state is SessionState.PREEMPTED
    events = session.reset()
    assert session.state is SessionState.IDLE
    assert session.lease is not None
    assert any(event.code == "SESSION_RESET" for event in events)
    result = session.tick(500_000_000)
    assert result.submitted is False


def test_state_age_is_bounded(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, clock = make_session(resolved)
    _activate(session, resolved)
    clock.set(150_000_000)
    session.on_sample(make_sample(resolved, 1, values=(0.1,) * 5, deadman=True, t_ns=150_000_000))
    # The mock state stamp is the clock at access; this test primarily proves
    # the age check is wired, not a stale gateway implementation.
    assert session._state_valid(150_000_000) is True
    assert session._state_valid(400_000_000) is False


def test_explicit_system_stop_latches_and_requests_stop(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    stop_sent, events = session.stop("operator", system=True, now_ns=20_000_000)
    assert stop_sent is True
    assert session.state is SessionState.FAULT
    assert gateway.stop_requests == ["operator"]
    event = next(event for event in events if event.code == "SYSTEM_STOP")
    assert event.detail["accepted"] is True
    assert event.detail["confirmed"] is None


def test_late_tick_triggers_loop_watchdog(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    result = session.tick(60_000_000)
    assert result.stop_sent is True
    assert session.state is SessionState.IDLE
    assert any(event.code == "LOOP_WATCHDOG" for event in result.events)


def test_rejected_system_stop_is_reported(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    gateway.fail("stop_rejected")
    _, events = session.stop("operator", system=True, now_ns=20_000_000)
    event = next(event for event in events if event.code == "SYSTEM_STOP_FAILED")
    assert event.detail["accepted"] is False
    assert session.state is SessionState.FAULT


def test_late_tick_below_watchdog_is_loop_overrun(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    result = session.tick(30_000_000)
    assert any(event.code == "LOOP_OVERRUN" for event in result.events)
    assert result.submitted is True
    assert session.state is SessionState.ACTIVE


def test_exact_duplicate_sample_is_rejected(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    sample = make_sample(resolved, 0, values=(0.1,) * 5, deadman=True, t_ns=0)
    session.on_sample(sample)
    session.tick(0)
    events = session.on_sample(sample)
    assert any(event.code == "SEQ_DUPLICATE" for event in events)
    assert session.state is SessionState.IDLE


def test_failed_stop_intent_requests_system_stop(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    gateway.fail("submit_unavailable")
    _, events = session.stop("operator", system=False, now_ns=20_000_000)
    assert session.state is SessionState.FAULT
    assert any(event.code == "STOP_INTENT_FAILED" for event in events)
    assert gateway.stop_requests == ["operator"]


def test_reset_requires_fresh_enable_edge(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, clock = make_session(resolved)
    _activate(session, resolved)
    session.stop("operator", system=True, now_ns=20_000_000)
    assert session.state is SessionState.FAULT
    session.reset()
    assert session.state is SessionState.IDLE
    # A held enable is not enough after reset; it must be released first.
    session.on_sample(make_sample(resolved, 1, values=(0.1,) * 5, deadman=True, t_ns=40_000_000))
    session.tick(40_000_000)
    assert not any(intent.deadman for intent in gateway.submitted[1:])
    session.on_sample(make_sample(resolved, 2, values=(0.0,) * 5, deadman=False, t_ns=60_000_000))
    session.on_sample(make_sample(resolved, 3, values=(0.1,) * 5, deadman=True, t_ns=60_000_000))
    result = session.tick(60_000_000)
    assert result.submitted is True


def test_stale_gateway_state_stops(tmp_path):
    resolved = write_resolved(tmp_path, joints=5)
    session, gateway, _ = make_session(resolved)
    _activate(session, resolved)
    gateway.set_stale(True)
    result = session.tick(20_000_000)
    assert session.state is SessionState.IDLE
    assert result.stop_sent is True
