# Independent design review — M0

> Status: **Round 2 verdict: APPROVE WITH CHANGES; no blockers. Operator
> approved the M0 design on 2026-11-26.** The only remaining condition is
> acceptance provenance (commit/tag is an explicit operator request; content
> is pinned by hash). No hardware, robot or device was used.
> Reviewer: independent ZCode design-review agent (read-only), 2026-11-26.

## 1. Round 2 verdict

**APPROVE WITH CHANGES — no blockers.** All five Round 1 blockers and the
majors are closed. The remaining MAJOR is procedural: the reviewed content is
not committed/tagged, so acceptance must pin a commit hash (or the recorded
tree hash) and the operator must perform the commit/tag. The review also asked
for `review.md` to exist (it does), the gate-log sentence to match `tee` (it
does), and `CHANGELOG.md` to carry the standard Related links (fixed).

Conditions for M1 authorization:

1. Commit the M0 branch and record the commit hash in this evidence file and
   in `ACCEPTANCE.md`; or explicitly accept the recorded tree hash as the
   review pin until the commit.
2. Keep the tag/version discipline: 0.2.0 is untagged until operator approval
   and merge.
3. Operator approves the M0 design.

Minor items: `CHANGELOG.md` Related links, the `TELEOP_CORE.md` binding example
(position disabled for v0.1), and the `TELEOP_COMMAND_V0.2.md` wire-string
comment were fixed after the review snapshot.

## 2. Round 1 verdict

**REJECT — return for rework.** The architecture was judged directionally
sound and structurally complete, but five blockers were raised:

| ID | Finding | Resolution |
|---|---|---|
| B1 | ROADMAP claimed the independent review passed while ACCEPTANCE said pending | ROADMAP no longer claims a pass; Round 2 confirms the status is delivery complete with acceptance Inconclusive |
| B2 | "One zero command" was undefined and unsafe in position mode | Added mode-specific stop intent: zero velocity / hold position / hold gripper; all-zero position is forbidden |
| B3 | 300 ms was claimed end-to-end while detection alone consumed it | Split detection, transport, intake and actuation; input-timeout end-to-end is reported separately |
| B4 | Manifest declared 1 Hz / 500 ms against a 50 Hz / 300 ms design | Manifest now declares 50 Hz / 300 ms; tests assert it |
| B5 | Package uncommitted; review artifact missing | This file plus a recorded working-tree hash and regenerated gate/pytest evidence; commit/tag remains an operator action |

## 3. Major findings addressed

- Normal deadman/timeout/lease-loss paths now use a **non-latching session
  abort**; `/v1/motion/stop` is reserved for explicit system stop. The system
  currently only has the latching stop, so this is a required S-M2 change.
- Test-only HTTP fallback now requires `/v1/health` `capabilities: ["mock"]`,
  not just a loopback URL; an SSH tunnel to the robot is refused.
- Domain 42 publisher authentication is recorded as missing; the intake must
  bind the lease holder to a registered capability or use DDS Security.
- The intake control law is specified (dt, step limit, measured-state age,
  saturation counter, no integrator, no all-zero position stop).
- Teleop `environment_class`/`source_class` is mapped explicitly to learning's
  dataset-level `source_class`; mixed-source data must be split or learning
  must add per-episode provenance.
- Input/capture schema identifiers are unified under `jcheng.teleop.*.v1`.
- Gripper is an orthogonal field, not a fourth mode.
- Cross-host `header.stamp` is for latency/provenance; liveness uses host
  arrival + `seq` + deadman, with a sync bound only when measured.
- Position mode is typed but refused without native v0.2; no proportional
  velocity emulation.
- Profile precedence is explicit: hardware → system profile, simulation →
  simulation catalog, fail closed on mismatch.
- M4's position-action precondition and blockers B13–B15 are recorded.
- Related lists include contract, system, ops and `.github`.

## 4. Round 2 result

Round 2 returned **APPROVE WITH CHANGES** with no blockers. All B1–B5 and the
majors are closed. The remaining condition is procedural: pin the reviewed
content to a commit (or the recorded tree hash) and have the operator approve
and commit/tag. The M0 acceptance stays `Inconclusive` until then.

## 5. What remains proposed or blocked

- `TeleopCommand` v0.2, system teleop intake/streaming session, `TeleopState`,
  teleop error codes, robot-profile v2, dataset contract/writer, simulation
  bridge, studio panel, and the vendor streaming executor.
- M2 canonical path, M3 measured truth, M4 LeRobot round-trip, M6 hardware,
  M9 mobile base, governance admission merge, license review.

## 6. Method

Read-only review of the M0 document set against the interfaces, system,
simulation, learning, studio, applications and benchmark repositories, plus
the governance standard. The reviewer ran no robot, no device and no hardware
session. Findings were checked against the current working tree; the final
content is pinned by the hash recorded in `README.md`.

## 7. Related

- [M0 evidence](README.md)
- [Acceptance](../../ACCEPTANCE.md)
- [Roadmap](../../ROADMAP.md)
- [Integration contract](../../docs/INTEGRATION_CONTRACT.md)
- [Safety model](../../docs/SAFETY_MODEL.md)
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
