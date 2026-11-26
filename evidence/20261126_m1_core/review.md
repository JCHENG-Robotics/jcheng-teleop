# Independent M1 code review — Round 1

> Status: **Round 1 REJECT; Round 2 focused review APPROVE WITH CHANGES.**
> The six Round 2 majors were addressed after the review; final re-review and
> commit/tag remain. No hardware, robot or device was used.

## Round 1 blockers and disposition

| ID | Finding | Disposition |
|---|---|---|
| B1 | M1 was an untracked, moving artifact; evidence did not exist at review start | Evidence now exists; content hash recorded. **Commit/tag is still pending an explicit operator request**, so this remains a process condition, not a code claim |
| B2 | ACCEPTANCE was still the M0 report and contradicted the M1 claim | ACCEPTANCE rewritten for 0.3.0 with M1 L1/L2 scope and explicit no-DDS/device/hardware limits |
| B3 | `STOPPING`/`PREEMPTED` unused; no reset; no mode-change operation | `STOPPING` used; lease loss sets `PREEMPTED`; local `reset()` added; mode change stops and requires re-arm |
| B4 | Mode switch while active was unguarded | Session latches the active mode; a different mode triggers a stop and re-arm |
| B5 | CLI lacked keyboard/`--mock`/`--duration`/stop-file | Added `--input keyboard`, `--key-script`, `--mock` (M1 only), `--duration` and `--stop-file`; stop-file exercises a system stop |

## Round 2 focused review

Round 2 returned **APPROVE WITH CHANGES** and confirmed the named fixes. Six
majors were then addressed:

| Finding | Disposition |
|---|---|
| Mock lease/seq gating bypassed for `deadman=False` | `ActionIntent.purpose` is `motion|stop`; motion requires an active lease, `deadman=true` and increasing seq; stops are exempt and tested |
| `StopResult.accepted/confirmed` ignored | System stop records `accepted` and `confirmed` in the event; a rejected stop emits `SYSTEM_STOP_FAILED`; mock fault added and tested |
| Position-stop fallback unreachable | Removed the unreachable fallback; docs now say "no prior target → no command, system hold" |
| `STOPPING` transient/untested | Documented as an atomic internal phase; final state is asserted; M2 may expose it |
| `LOOP_OVERRUN` inverted | Now emitted for `tick < delta <= 2*tick`; `LOOP_WATCHDOG` for `>2*tick`; 30 ms and 60 ms tests |
| ROADMAP header stale | Header updated to v0.3.0 / M1 in progress / acceptance Inconclusive |

Minor fixes: CLI stop-file exception documented, exact joint-vector width
enforced, README M1 rows marked partially verified, dead state removed, and the
review artifact is included in the gate.

## Major findings and disposition

- Lease identity is now plumbed through `ActionIntent.lease_id`, the session
  attaches it, stop intents carry it, and the mock rejects a live intent with
  no active lease and a non-increasing seq.
- Deadman release is latched (`_release_seen`) so a re-press inside one tick
  cannot erase the stop.
- Timeout uses `>=` and receipt uses the injected session clock; the exact
  300 ms boundary is tested.
- Gateway state age is checked against `state_age_max_ms`.
- Mock state is labelled `truth=mock`, `verification=none` (not a bus
  measurement).
- Position stop holds the last accepted target; with no prior target it emits
  no command and relies on the system hold. Stop provenance uses the sample
  source stamp.
- Wire sequence is assigned per submit; the mock rejects non-increasing seq.
- `max_rate_hz` is enforced; a late tick triggers `LOOP_WATCHDOG`.
- Profile hashes are recomputed and rejected if declared content differs;
  scale/offset are validated; velocity mapping does not add a position offset;
  position mode does not apply a zero-command deadzone.
- Profile-mismatched samples stop the session; gamepad gripper is neutral when
  centered; adapter silence is documented as a deadman gap rather than an
  unimplemented focus-loss event.

## Remaining conditions

1. **Freeze the M1 artifact.** Commit and tag the M1 tree, then regenerate
   `gate.txt`/`pytest.txt`/traces from that commit. Without a commit, the
   acceptance cannot be pinned, even though the tree hash is recorded.
2. Re-run the independent code review on the frozen artifact.
3. Operator acceptance of M1; M2 remains blocked by the system intake,
   simulation bridge and contract gaps listed in `docs/INTEGRATION_CONTRACT.md`.

## What is verified at this stage

- 111 tests pass; the repository gate passes.
- No ROS/DDS/network/device/subprocess path in `src/`; no hardware.
- The M1 core is deterministic for the same input/clock/profile/mock script.
- Stop, deadman, lease, mode-change, reset, preemption, state-age, sequence and
  limit paths have direct tests.

## What is not verified

- A frozen commit/tag and re-reviewed artifact.
- ROS 2/DDS/system gateway/simulation integration.
- Real measured state, recording, replay of a real capture, datasets or
  hardware.
- Physical stop confirmation; the platform has no e-stop.

## Related

- [M1 evidence](README.md)
- [Acceptance](../../ACCEPTANCE.md)
- [Roadmap](../../ROADMAP.md)
- [Teleop core](../../docs/TELEOP_CORE.md)
- [Safety model](../../docs/SAFETY_MODEL.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
