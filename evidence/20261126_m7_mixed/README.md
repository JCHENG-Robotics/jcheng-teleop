# M7 mixed-source index (offline data side)

> Status: **Partially verified (offline index, 2026-11-26)**. No policy, no
> training, no rollout, no hardware. The learning dataset contract remains
> unfrozen.

## Implemented

- Correction provenance on the capture manifest: `corrected_from_capture_id`,
  `corrected_from_tick_id`, `policy_action_seq`, with `policy_id/version`.
  Only `human_correction` may carry them; the policy capture is never replaced.
- `jcheng.teleop.dataset.v1` index (`src/jcheng_teleop/export/mixed.py`):
  verifies sealed captures, groups by source class, keeps each episode's
  environment class, checks correction references and writes outside git.
- `jcheng-teleop-index` CLI.

## Index over two recorded captures

Two real captures (one mock, one simulation, both scripted) were already
recorded for M4 replay. The index keeps both labels instead of flattening:

```bash
PYTHONPATH=src python3 -m jcheng_teleop.export.cli \
  --capture-root /tmp/jcheng-m4-ros \
  --capture-id mock-mono-20261126 --capture-id sim-mono-20261126 \
  --out /tmp/jcheng-m7-index.json
```

```json
{"index": {"episodes": 2,
           "per_environment": {"mock": 1, "simulation": 1},
           "per_source_class": {"scripted": 2}},
 "written": {"bytes": 2100, "sha256": "sha256:8e42e82f295965490066cb79afdf6cf73b53f58dd2ea2963289d0337c337793f"}}
```

```json
{"groups": {"scripted": ["mock-mono-20261126", "sim-mono-20261126"]},
 "mixed_source_classes": false, "mixed_environments": true}
```

There is no dataset-level `source_class`; a learning export must split by
`groups`. A mock episode can never be read as the simulation episode.

## Tests

`python3 -m pytest -q tests/test_mixed_dataset.py` — **12 passed**. Full suite:
**188 passed**; gate OK.

Covered: grouping by source class with per-episode environment; duplicate
capture id; unsupported source class; missing/self/external correction
references; correction fields only on `human_correction`; correction requires
a prior policy action; capture entry verification and manifest hash; index
write outside git; CLI end-to-end.

## Limits

- No human_correction or policy_execution capture exists yet: there is no
  policy, no M6 teleoperation and no policy execution path. The correction
  rules are tested with synthetic manifests, not with a real correction.
- The index is not a training dataset and does not write `jcheng.dataset.v1`;
  the learning writer and the absolute-position action decision are missing.
- 30 multi-source episodes, rollouts under a non-teleop lease, takeover and
  pre-registered evaluation are not met.
- No model weights; no training in this repository.
