# M0 evidence — repository scaffold

> Status: **complete** as of 2026-11-26.
> Scope: the document set, admission manifest, repository gate and CI for
> `jcheng-teleop` v0.1.0. No input adapter, no runtime node, no intent stream
> and no hardware session.

## 1. Environment

| Item | Value |
|---|---|
| Host | operator laptop, Linux 7.0.0-43-generic x86_64, Python 3.12.3, pytest 7.4.4 |
| Repository | `JCHENG-Robotics/jcheng-teleop` (public, created 2026-11-26T05:40:37Z) |
| Initial commit | `50bf6dd` (`chore: initialize jcheng-teleop repository`) |
| Robot | not used |
| Motion | none; no command was sent |

## 2. Commands and results

| Command | Result | Log |
|---|---|---|
| `python3 -m pytest -q tests` | pass, 14 tests | `gate.txt` |
| `bash scripts/check_repo_gate.sh` | pass | `gate.txt` |
| Manifest schema validation against `capability-manifest.v1.schema.json` | pass | `gate.txt` header; `tests/test_contract.py` |
| CI `teleop-gate` on `50bf6dd` | pass ([run 45763190477](https://github.com/JCHENG-Robotics/jcheng-teleop/actions/runs/45763190477)) | `README.md` |

## 3. Claims supported

- The admission manifest parses, matches `VERSION`, validates against the v1
  schema and declares `hardware_access: none` with an empty runtime surface.
- The reserved `TeleopCommand` stream is documented and not claimed.
- The static scan finds no device, vendor-topic or motion token in code,
  configuration or scripts.
- No recording or oversized file is tracked.
- The documentation set required by the organization standard exists and its
  relative links resolve.
- The same gate passes in CI on `main`.

## 4. Not covered

- Input conditioning and the deadman state machine (M1).
- Intent publication, lease gating and preemption (M2).
- Any hardware or motion behavior (M3).
- Reviewer sign-off; the operator is the only account.

## 5. Related

- [Acceptance report](../../ACCEPTANCE.md)
- [Roadmap](../../ROADMAP.md)
- [Architecture](../../docs/ARCHITECTURE.md)
