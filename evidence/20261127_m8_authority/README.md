# M8 shared-authority model (offline)

> Status: **Partially verified (offline state machine, 2026-11-27)**. No policy,
> no runtime, no 20-trial takeover measurement and no hardware.

## Implemented

`src/jcheng_teleop/core/authority.py`: `AuthorityMachine` with modes
`STOPPED` / `POLICY` / `OPERATOR` / `BLEND` and per-tick logging.

- Every tick has one source, or explicit weights summing to 1; `STOPPED` has
  zero weights.
- Policy start requires an action reference and a confidence ≥ `min_confidence`
  (0.5 default).
- Low confidence or a policy fault hands over to the operator (or `STOPPED`
  with no operator), never a silent switch; the reason is recorded.
- Operator takeover is authoritative on the request tick, sets
  `correction=true` and keeps the policy action reference; the policy is
  marked stopped on that tick.
- `coverage()` reports expected/covered ticks and gaps.

## Results (model)

```text
policy 20 ticks: coverage 20/20 = 1.0, gaps []
takeover at +40 ms: mode OPERATOR, correction true,
  policy_action_ref retained, policy_stopped_at == request
low confidence with operator: OPERATOR; without: STOPPED
policy fault: STOPPED with reason
blend 0.3: operator 0.3 / policy 0.7
```

## Tests

`python3 -m pytest -q tests/test_authority.py` — **12 passed**. Full suite:
**214 passed**; gate OK.

Covered: complete coverage; takeover and policy-stop on the request tick over
20 simulated trials; low-confidence start/tick with and without an operator;
policy fault; explicit blend weights and invalid weight; start outside
`STOPPED`; takeover without a policy; coverage gap detection.

## Limits

- The model's same-tick takeover is **not** a latency measurement. The 100 ms /
  150 ms bounds over ≥20 real trials are not measured.
- No policy contract, no policy execution path, no studio authority indicator.
- Correction provenance fields exist (M7), but a takeover does not yet emit a
  `human_correction` capture.
- No simulation or hardware scenario; these are L1 model tests only.
