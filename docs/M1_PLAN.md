# M1 implementation plan — jcheng-teleop

> Status: **Delivered and accepted at L1/in-process L2** as of 2026-11-26. The
> operator approved M0 and the M1 work packages W1-W12 are implemented with
> 111 tests. Independent review Round 2 approved with changes and all findings
> were fixed. See `evidence/20261126_m1_core/`.

## 1. Goal

Deliver a deterministic, ROS-free teleoperation core that turns normalized
operator input into bounded, deadman-guarded action intent and exercises the
session/gateway semantics against an in-process mock. M1 proves the semantics;
it does not publish DDS, connect to a real gateway, record episodes or touch
hardware.

## 2. Preconditions

- M0 design approved by the operator; M1 authorized separately.
- The `.github` teleop admission branch is merged, or the operator records a
  written exception (the branch is currently not on `origin/main`).
- No interface change is required. `TeleopCommand` v0.1.0 remains the
  read-only reference; M1 does not publish it.
- The repository gate and tests pass on the M0 branch.
- Python 3.10+ on the host; CI uses 3.12. No ROS, no device, no robot.

### 2.1 Blockers vs M1

| ID | Blocker | M1 impact |
|---|---|---|
| B0 | `.github` teleop admission branch unmerged | Gate for M1; merge or written operator exception |
| B1 | No system teleop consumer | Non-blocking for M1; M2 |
| B2 | Vendor executor single-joint step | Non-blocking for M1; M6 |
| B3 | `TeleopCommand` lacks position/gripper | Non-blocking for M1; M2/M6 and the v0.2 proposal |
| B4 | `robot-profile.v1` cannot express CAN arms | Non-blocking for M1 fixtures; M2/M6 |
| B5 | No simulation bridge | Non-blocking for M1; M2 |
| B6 | Learning dataset/writer unmerged | Non-blocking for M1; M3/M4 |
| B7 | No measured state at teleop rate | Non-blocking for M1 mock; M3/M6 |
| B8 | Preemption surfaces as expiry | Non-blocking for M1; M2 |
| B9 | No stop confirmation | Non-blocking for M1; M6 |
| B10 | No `LICENSE` | Non-blocking for original M1 code; no third-party copy |
| B11 | `system_api` range mismatch | Non-blocking for M1; M2 |
| B12 | No e-stop/brake/encoder | Non-blocking for M1; M6 |
| B13 | No domain-42 publisher authentication | Non-blocking for M1; M2 security review |
| B14 | Mixed-source dataset not supported | Non-blocking for M1; M3/M4/M7 |
| B15 | Velocity-only episodes cannot satisfy learning's position action | Non-blocking for M1; M4 |

Only B0 gates M1. Everything else is recorded so M1 does not quietly depend
on an unapproved cross-repository change.

## 3. Work packages

| ID | Work package | Deliverables | Depends on | Exit |
|---|---|---|---|---|
| W1 | Package skeleton | `pyproject.toml`, `src/jcheng_teleop/{__init__,cli}.py`, `core/`, `adapters/`, test layout | M0 | `python -m jcheng_teleop --help` works without ROS |
| W2 | Typed model and validation | `core/model.py`: `Mode`, `InputSample`, `ActionIntent`, `TeleopEvent`, errors; finite/length/mode checks | W1 | Unit tests for every invalid shape |
| W3 | Clock and determinism harness | `core/clock.py`, manual clock, fixed tick runner, no wall-clock in logic | W2 | Same input → byte-identical action trace |
| W4 | Conditioning | `core/conditioning.py`: deadzone/hysteresis, scale once, per-axis clamp, rate limiter, seq/stamp ordering | W2 | Boundary tests; one clamp event per saturation episode |
| W5 | Deadman/watchdog | `core/deadman.py`: enable edge, release, timeout, re-arm, one-zero-then-silence | W4 | Timeout ≤ one tick; no auto-resume |
| W6 | Profile resolver | `core/profile.py`: canonical profile + teleop binding, hash/order/sign/unit validation; 2/5/6-DoF fixtures | W2 | Mismatch and sign/order tests; no hard-coded robot names |
| W7 | Action mapper | `core/mapper.py`: joint velocity; joint position typed but refused without native v0.2; normalized gripper; Cartesian refusal | W5, W6 | Mapping/limit tests; no IK; no velocity emulation |
| W8 | Session state machine | `core/session.py`: `BOOT/SELFTEST/IDLE/READY/ACTIVE/STOPPING/FAULT/PREEMPTED`; mode change; no auto transitions | W5, W7 | Transition table tests; forbidden transitions fail |
| W9 | Gateway port and mock | `core/gateway.py`, `adapters/gateway/mock.py`: admit/acquire/renew/release/state/submit/stop; scriptable faults | W8 | No retry; one submit per tick; stop once; lease loss stops |
| W10 | Input adapters | `adapters/input/{virtual,keyboard,jsonl,gamepad}.py`: sample protocol, sample-gap semantics, injected gamepad source | W4 | Adapter lifecycle tests; no device API |
| W11 | CLI and golden runs | `cli.py`: `--input virtual|keyboard|jsonl`, `--profile`, `--binding`, `--mock`, `--duration`, `--trace`; deterministic exit codes | W9, W10 | Golden trace and help tests |
| W12 | Gate, docs and evidence | Update `check_repo_gate.sh`, tests, `INPUT.md` freeze note; `evidence/20261126_m1_core/` | W1–W11 | Gate passes; L1/L2 evidence recorded |

## 4. Proposed module tree

```text
src/jcheng_teleop/
├── __init__.py
├── __main__.py
├── cli.py
├── core/
│   ├── __init__.py
│   ├── model.py
│   ├── clock.py
│   ├── conditioning.py
│   ├── deadman.py
│   ├── mapper.py
│   ├── profile.py
│   ├── session.py
│   ├── safety.py
│   ├── gateway.py
│   └── runner.py
└── adapters/
    ├── __init__.py
    ├── input/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── virtual.py
    │   ├── keyboard.py
    │   ├── jsonl.py
    │   └── gamepad.py
    └── gateway/
        ├── __init__.py
        └── mock.py
tests/
├── conftest.py
├── test_model.py
├── test_conditioning.py
├── test_deadman.py
├── test_mapper.py
├── test_profile.py
├── test_session.py
├── test_safety.py
├── test_runner_determinism.py
├── test_mock_gateway.py
├── test_input_adapters.py
├── test_cli.py
└── test_no_hardware.py
```

Rules:

- `core/` imports only the standard library and PyYAML. No ROS, NumPy,
  pydantic, device library or network client.
- `adapters/input/` imports no device library. `keyboard` consumes injected key
  events (a terminal wrapper is operator-side); `gamepad` consumes an injected
  `JoySource`; `jsonl` reads a local stream.
- `adapters/gateway/mock.py` is in-process. A future HTTP/DDS adapter is a
  separate module, added only at M2.
- No module under `core/` or `adapters/` writes datasets or model artifacts.

## 5. Public API sketch

```python
# Construction is explicit; no global state.
session = TeleopSession(
    profile=resolved_profile,
    gateway=mock_gateway,
    clock=ManualClock(),
    config=SessionConfig(deadman_ms=300, tick_ms=20, max_rate_hz=50),
)
session.start()                    # admits the mock and acquires a lease
session.on_sample(sample)          # updates the latest sample/deadman
result = session.tick(now_ns)      # at most one intent or one stop per tick
session.stop("operator")           # one mode-specific stop intent + false
session.close()
```

`TickResult` exposes `intent`, `events`, `state`, `stop_sent`, `submitted` and
`gateway_result`, so tests and the CLI can assert without reading internals.

## 6. Test matrix

| Area | Cases | Level | Expected |
|---|---|---|---|
| Model | Empty/wrong-length vectors; both mode payloads; unknown mode; NaN/Inf; negative seq | L1 | Rejected, typed event, no intent |
| Ordering | Duplicate seq; rollback; stamp rollback; large gap | L1 | Rejected; no reorder/repair |
| Deadzone | Inside, edge, hysteresis, return to zero | L1 | Exact zero inside; no chatter |
| Scaling | One conversion; profile scale; session scale | L1 | Applied once; record source conversion |
| Limits | Per-axis bound; saturation; request > profile | L1 | Clamp; one `LIMIT_CLAMPED` per episode; no silent truncation |
| Rate | 50 Hz tick; late tick; backlog | L1 | No burst; at most one per tick; `LOOP_OVERRUN` |
| Deadman | Engage, release, timeout, re-arm, held-before-stop | L1 | One zero + false; fresh edge required |
| Session | Every allowed transition; every forbidden transition; reset; atomic STOPPING phase | L1 | Forbidden transitions raise/refuse; final state after stop is asserted |
| Mode change | While active; while ready; stale payload | L1 | Stop first; re-arm; no reinterpretation |
| Profile | 2/5/6-DoF; joint order; sign; offset; hash mismatch | L1 | Resolve or refuse; no hard-coded names |
| Mapping velocity | Zero, positive, negative, saturation | L1 | Correct sign/order/units |
| Mapping position | Typed target; limit; native-mode refusal | L1 | No velocity emulation; `MODE_UNSUPPORTED` without v0.2 |
| Gripper | 0/1, clamp, profile range (rad and m) | L1 | Normalized in, profile units out |
| Cartesian | Request in M1 | L1 | `MODE_UNSUPPORTED`; no fallback |
| Mock gateway | Admit, acquire, renew, release, submit, busy, stop, fault | L2 | No retry; one stop; lease loss stops |
| Determinism | Same fixture twice; reverse order; manual clock | L1/L2 | Byte-identical trace |
| Adapters | Virtual, keyboard event injection, JSONL, gamepad source; source silence; disconnect | L1 | No synthetic sample; silence reaches the deadman |
| CLI | Virtual run; JSONL file; bad profile; bad binding; stop file | L2 | Deterministic exit codes and trace |
| Static | Forbidden tokens; weights; data dirs; links | L0 | Gate passes |

## 7. Quantified M1 acceptance

- 100% of invalid-shape and ordering tests reject with a typed event and zero
  intent.
- 100% of runs emit no intent before a fresh enable edge.
- Deadman timeout is detected at the first tick at or after 300 ms; the stop
  emits exactly one mode-specific stop intent with `deadman=false` (zero
  velocity, hold position, or hold gripper), then silence.
- Every over-limit request produces exactly one limit event per continuous
  saturation episode and a bounded output.
- Determinism: two runs of the same fixture produce identical bytes for the
  action trace; a reversed sample order is rejected, not reordered.
- 2-DoF, 5-DoF and 6-DoF profile fixtures all pass without robot-specific code.
- Mock gateway: exactly one submit per tick, zero retries, exactly one stop per
  stop episode.
- Static scan: zero device/motion/model/recording tokens outside docs/tests.
- No DDS, network, subprocess, device or filesystem write in the control tick.

## 8. Out of scope for M1

- DDS/domain 42, real gateway, lease acquisition against the system.
- System arbiter/safety integration, simulation plant, Gazebo.
- Episode recording, replay, dataset/LeRobot export.
- Cartesian motion, IK, FK, collision checking.
- Device drivers, real gamepad/leader arm, hardware.
- Any claim of real-time performance or hardware safety.

## 9. Cross-repository dependencies

| Dependency | M1 need | Status |
|---|---|---|
| `jcheng-interfaces` `TeleopCommand` semantics | Read-only reference; no import required | Available |
| `jcheng-system` profile `armpi_ultra` | Fixture source for joint order/limits | Available; copy only into test fixtures with hash, no runtime dependency |
| `jcheng-simulation` catalog | 2/6-DoF fixtures for tests | Available; repository-local, pin by commit |
| `jcheng-learning` dataset contract | Not needed | Not frozen; M3 |
| Gateway HTTP/DDS | Not needed; mock port only | M2 |
| License review | Original code only; no third-party code | Pending |

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The mock port is mistaken for the system | Label it in the CLI, docs and evidence; no system claim |
| Profile fixtures drift from the canonical profile | Record fixture hashes; add a contract test that compares names/limits when the canonical file is available |
| Keyboard adapter is flaky in CI | Inject events in tests; the real terminal adapter is a thin wrapper |
| Position mapping becomes a hidden controller | Do not emulate position with a velocity loop; require native v0.2 and bench characterization; test `MODE_UNSUPPORTED` |
| Determinism breaks through wall-clock use | Inject the clock; static scan for `time.time`/`datetime.now` in `core/`; manual-clock tests |
| Scope creep into M2 | Freeze the M1 non-goals; any DDS/HTTP/real-gateway code is rejected in review |

## 11. Evidence plan

`evidence/20261126_m1_core/` (created at M1, not in M0):

- `gate.txt` — repository gate output.
- `pytest.txt` — L1/L2 test output and counts.
- `determinism.txt` — two trace hashes and the comparison.
- `profiles.txt` — 2/5/6-DoF fixture results and hashes.
- `README.md` — scope, commands, environment, limitations, and the explicit
  statement that no DDS/device/hardware was used.
- An independent review note confirming no motion authority and no device.

## 12. Definition of done

M1 is done when the work packages W1–W12 are complete, the gate and tests
pass, the evidence records L1/L2 only, the independent review finds no
contradiction with the M0 contracts, and the operator authorizes M2
preparation. M1 does **not** authorize publishing intent or connecting to a
system gateway.

## 13. Related

- [Architecture](ARCHITECTURE.md)
- [Teleop core](TELEOP_CORE.md)
- [Safety model](SAFETY_MODEL.md)
- [Input model](INPUT.md)
- [Data collection](DATA_COLLECTION.md)
- [Integration contract](INTEGRATION_CONTRACT.md)
- [Dependency review](DEPENDENCY_REVIEW.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
