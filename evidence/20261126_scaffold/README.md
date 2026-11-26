# M0 evidence — repository scaffold

> Status: **in progress** as of 2026-11-26.
> Scope: the document set, admission manifest, repository gate and CI for
> `jcheng-teleop` v0.1.0. No input adapter, no runtime node, no intent stream
> and no hardware session.

## 1. Environment

| Item | Value |
|---|---|
| Host | operator laptop, Linux 7.0.0-43-generic x86_64, Python 3.12.3, pytest 7.4.4 |
| Repository | `JCHENG-Robotics/jcheng-teleop`, `main` |
| Robot | not used |
| Motion | none; no command was sent |

## 2. Commands and results

| Command | Result | Log |
|---|---|---|
| `python3 -m pytest -q tests` | pending | — |
| `bash scripts/check_repo_gate.sh` | pending | — |
| Manifest schema validation against `capability-manifest.v1.schema.json` | pending | — |
| CI `teleop-gate` | pending | — |

## 3. Claims supported

- The admission manifest parses, matches `VERSION`, validates against the v1
  schema and declares `hardware_access: none` with an empty runtime surface.
- The reserved `TeleopCommand` stream is documented and not claimed.
- The static scan finds no device, vendor-topic or motion token in code,
  configuration or scripts.
- No recording or oversized file is tracked.
- The documentation set required by the organization standard exists and its
  relative links resolve.

## 4. Not covered

- Input conditioning and the deadman state machine (M1).
- Intent publication, lease gating and preemption (M2).
- Any hardware or motion behavior (M3).
- CI success until the first run is recorded above.

## 5. Related

- [Acceptance report](../../ACCEPTANCE.md)
- [Roadmap](../../ROADMAP.md)
- [Architecture](../../docs/ARCHITECTURE.md)
