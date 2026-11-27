# M8 plan — shared autonomy and human-in-the-loop correction (offline model)

> Status: **Offline authority model**, 2026-11-27. No policy, no training, no
> simulation trial and no hardware. The state machine records authority; it
> does not publish intent or move anything.

## 1. Authority model

| Mode | Operator weight | Policy weight | Meaning |
|---|---|---|---|
| `STOPPED` | 0 | 0 | No authority; no motion |
| `POLICY` | 0 | 1 | The policy holds authority |
| `OPERATOR` | 1 | 0 | The operator holds authority |
| `BLEND` | w | 1−w | Explicit blend; weights sum to 1 |

Invariants enforced by `core/authority.py`:

- Every recorded tick has exactly one source, or explicit weights summing to 1.
- No implicit mixing: a blend needs an explicit `operator_weight`.
- Every transition carries a `reason`; there is no silent switch.
- A policy episode keeps its `policy_action_ref` on the authority record.
- `STOPPED` has zero weights.

## 2. Transitions

| Event | From | To | Notes |
|---|---|---|---|
| `start_policy(confidence ≥ min)` | `STOPPED` | `POLICY` | action reference required |
| `start_policy(confidence < min)` | `STOPPED` | `STOPPED` | reason `policy_low_confidence_at_start` |
| `policy_tick(confidence < min)` | `POLICY` | `OPERATOR` if present else `STOPPED` | correction=true, policy stopped at this tick |
| `policy_fault(reason)` | `POLICY`/`BLEND` | `STOPPED` | reason includes the fault |
| `request_takeover` | `POLICY`/`BLEND` | `OPERATOR` | correction=true, policy stops on this tick |
| `blend(operator_weight)` | `POLICY`/`OPERATOR`/`BLEND` | `BLEND` | explicit weights, sum=1 |
| `stop(reason)` | any | `STOPPED` | zero weights |

A takeover or handover **is** a correction episode: `correction=true` and the
policy action reference is retained. The capture layer can then emit a
`human_correction` capture with `corrected_from_capture_id` /
`policy_action_seq` (M7 provenance), keeping the policy capture immutable.

## 3. Timing

- `request_takeover` returns at the request timestamp; in the model the
  operator is authoritative on that tick and the policy stops on that tick.
- The acceptance bounds are fixed before a run: takeover accepted ≤100 ms and
  policy stopped ≤150 ms, measured on the host monotonic clock over ≥20 trials.
- The model's same-tick result is **not** a latency measurement. A future
  runtime must stamp the operator request, the authority transition and the
  policy-stop confirmation, and report the distribution; a failed bound stays
  failed.
- M7/M6 latency evidence may revise the bounds before the M8 gate, but not
  after a run starts.

## 4. Audit and coverage

- Every tick is appended to the authority log (`AuthorityTick`): time, mode,
  weights, reason, correction flag, policy action reference, policy stop time.
- `coverage()` reports expected/covered ticks and the first gaps over a window.
  The acceptance target is 100% coverage (ratio 1.0) over the measured set.
- The log is an evaluation artifact: it never rewrites a capture and is never
  a new demonstration.

## 5. Acceptance mapping

| Item | State |
|---|---|
| Every tick has one authority source or an explicit blend; 100% coverage | **Model implemented and tested** (coverage ratio 1.0 in the 20-tick test) |
| Takeover ≤100 ms, policy stop ≤150 ms over ≥20 trials | **Model same-tick only**; no runtime measurement, no 20-trial hardware/sim run |
| Policy fault/low confidence yields a defined stop/handover, not a silent switch | **Model implemented and tested** |
| Correction episodes labelled `human_correction` and retain the policy action | Provenance fields exist (M7); capture emission from an authority takeover is **not wired** |

## 6. Non-goals

Implicit blending without an audit trail, silent policy takeover, unbounded
correction authority, policy motion without a lease, autonomy claims beyond
the tested modes.

## 7. Blockers

- No policy intent contract or policy execution path; M7 training/rollout is
  blocked.
- M6 hardware teleoperation is blocked (streaming executor, wire v0.2, stop
  confirmation).
- No studio authority indicator; the studio panel shows teleop status only.
- No simulation/hardware scenario for the 20 takeover trials; the model is the
  only evidence today.
