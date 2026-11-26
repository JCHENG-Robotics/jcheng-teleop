# M7 plan — hybrid demonstration and policy data (offline data side)

> Status: **Offline data side implemented; training/deployment blocked**,
> 2026-11-26. No policy was trained, no rollout was run, no hardware was used.
> M7 depends on M6 (blocked) and on the learning dataset contract and policy
> store, which are not ready.

## 1. What this slice covers

| Piece | State |
|---|---|
| Per-episode `environment_class` + `source_class` | Already in the capture manifest; the index keeps both per episode |
| Human-correction provenance | Implemented: `corrected_from_capture_id`, `corrected_from_tick_id`, `policy_action_seq`, plus `policy_id`/`policy_version` |
| Mixed-source index `jcheng.teleop.dataset.v1` | Implemented: verifies sealed captures, groups by source class, keeps environment labels, checks correction references |
| `jcheng-teleop-index` CLI | Implemented; writes the index outside git |
| Training / SmolVLA / ACT | **Not implemented**; learning M2/M3 and a policy store are missing |
| Policy rollout under a non-teleop lease, operator preemption | **Blocked on M6** and a policy execution path |
| Evaluation protocol and thresholds | Not started (needs a policy and hardware/task setup) |
| Model artifacts | Not started; weights stay outside git in `/opt/jcheng/models/` |

## 2. Data model

The capture manifest already has one `environment_class` and one
`source_class` per episode. A correction episode adds:

```yaml
source_class: human_correction
policy_id: smolvla-armpi
policy_version: 0.1.0
corrected_from_capture_id: policy-run-20261126-01
corrected_from_tick_id: 412
policy_action_seq: 207
```

Rules:

- A `human_correction` capture requires `policy_id`, `policy_version`, a
  `corrected_from_capture_id` and a `policy_action_seq`; the tick is optional.
- The correction does **not** replace the policy action. The policy capture
  remains immutable and the index records both; a consumer can pair them by
  reference.
- Only `human_correction` may carry correction fields; any other source class
  with them is refused.
- The referenced capture must be in the index unless
  `--allow-external-corrections` is explicit; an external reference is recorded
  as such, not silently accepted.

## 3. Mixed dataset index `jcheng.teleop.dataset.v1`

```json
{
  "schema": "jcheng.teleop.dataset.v1",
  "episodes": [
    {"capture_id": "...", "manifest_sha256": "sha256:...",
     "environment_class": "simulation", "source_class": "human_teleop",
     "policy_id": null, "corrected_from_capture_id": null}
  ],
  "groups": {"human_teleop": ["..."], "human_correction": ["..."]},
  "counts": {"episodes": 2, "per_source_class": {...}, "per_environment": {...}},
  "mixed_source_classes": true,
  "mixed_environments": false,
  "limitations": ["..."]
}
```

- The index is teleop-local. It is **not** the learning `jcheng.dataset.v1`
  dataset and never writes one.
- There is no dataset-level `source_class`: the learning contract forbids
  mixing, so the index exposes `groups` for splitting.
- `environment_class` is never flattened; a mock and a simulation capture in
  one index stay two labelled episodes.
- Every episode carries its capture's manifest hash; the capture data stays
  outside git.
- `write_index` refuses any path inside a git worktree.

## 4. Workflow (when the blockers close)

1. Capture human teleoperation, policy execution and correction episodes as
   sealed captures (M3 recorder).
2. Build an index with `jcheng-teleop-index`; resolve every correction
   reference.
3. Split by `groups` into learning datasets, or wait for a learning contract
   that supports per-episode provision.
4. Train offline (learning M2/M3); store weights in `/opt/jcheng/models/` with
   a hash.
5. Deploy under a non-teleop lease; operator takeover must stop the policy
   before any teleop intent is accepted.
6. Evaluate with pre-registered tasks, seeds and thresholds; hardware and
   mock/simulation results are reported separately.

## 5. M7 acceptance mapping

| Acceptance item | State |
|---|---|
| ≥ 2 source classes in separate datasets or one approved mixed dataset; ≥ 30 episodes; no ambiguous environment | **Not met**: the index supports it, but no policy/correction capture exists and the learning contract is not frozen |
| Policy rollouts under a non-teleop lease with operator preemption | **Blocked** (M6 + policy execution path) |
| ≥ 3 pre-registered tasks, fixed seeds, ≥ 10 hardware trials, thresholds fixed before the run | **Not started** (needs hardware and a policy) |
| Hash-pinned model artifacts outside git | **Not started** |
| No mixing simulation and hardware without labels | **Enforced** by the index and capture manifest |

## 6. Non-goals

Fully autonomous operation, safety certification, model weights in git,
mixing simulation and hardware without labels, training in this repository,
policy motion without a system lease.

## 7. Blockers

- M6: no privileged streaming executor, no wire position/gripper, no stop
  confirmation, no e-stop (see `docs/M6_PLAN.md`).
- Learning: `jcheng.dataset.v1` writer/validator and the absolute-position
  action decision are not frozen; LeRobot export is blocked (M4).
- No policy artifact store or policy execution lease path yet.
- No hardware/task setup for the pre-registered evaluation.
