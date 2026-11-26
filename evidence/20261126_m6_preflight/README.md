# M6 supervised authorization + offline preflight

> Status: **Partially verified (offline only, 2026-11-26)**. No robot motion, no
> device, no DDS, no system session. Hardware remains blocked (B2/B3/B9/B4,
> no e-stop).

## Implemented

`src/jcheng_teleop/supervised/`:

- `authorization.py`: `jcheng.teleop.authorization.v1` with operator,
  supervisor, authorization ref, workspace checklist hash, profile/contract
  hashes, exact joint order, motion scope, velocity bound and a timezone-aware
  validity window (≤ 8 h). Operator and supervisor must be different people.
- `preflight.py`: validates the record against the supplied profile and pinned
  contract, returns the authorization hash and a fixed blocker list;
  `hardware_ready` is always false until streaming, v0.2 wire and stop
  confirmation exist.
- `cli.py`: `jcheng-teleop-preflight`; exit 0 authorized (hardware still
  blocked), 1 refused, 2 configuration error.

## Valid authorization

```json
{"authorization_hash": "sha256:a28f6017c608f8553d9ac9ca3a11a62ef8a9606db110ec5336630d3d2283f521",
 "hardware_ready": false,
 "status": "authorized",
 "errors": [],
 "session": {"session_id": "m6-armpi-20261126-01", "operator_id": "operator-name",
             "supervisor_id": "supervisor-name", "motion_scope": ["joint1"],
             "max_velocity_rad_s": 0.2}}
```

Blockers in the same report: streaming executor missing (B2), `TeleopCommand`
v0.2 missing (B3), stop confirmation open (R5/B9), no e-stop/brake/encoder,
PiPER X canonical profile missing (B4).

## Refused authorization

`workspace_clear: false`:

```json
{"status": "refused", "errors": ["workspace_clear must be true"],
 "hardware_ready": false,
 "authorization_hash": "sha256:326f992683cfc91fc4e6f7ad7f1cfae1ec24bd500002c35647ff810003a4f164"}
```

Exit code 1.

## Tests

`python3 -m pytest -q tests/test_supervised.py` — **17 passed**. Full suite:
**176 passed**; gate OK.

Covered: valid record; operator == supervisor refused; workspace clear;
reversed joint order refused; unknown scope joint; velocity above the profile
limit; expired, not-yet-valid and >8 h windows; profile/contract mismatch;
preflight blockers and `hardware_ready=false`; refused record; deterministic
record hash; CLI authorized/refused/config-error exit codes; no runtime imports
in the supervised package.

## Limits

- Offline paperwork gate only. It does not authorize motion by itself and it
  does not replace the system lease, deadman, limits or stop latch.
- The profile used in this drill is the teleop demo fixture, not a hardware
  session profile.
- No hardware session was run; the runbook in `docs/M6_PLAN.md` is unexecuted.
- The platform has no e-stop; a future hardware report must state that.
