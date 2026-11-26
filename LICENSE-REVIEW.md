# License review — jcheng-teleop

> Status: **pending** as of 2026-11-26.
> No `LICENSE` file exists. This repository follows the organization rule that
> no license is added before the review is signed off
> (`.github/docs/license-review.md`).

## 1. Current facts

| Item | Fact |
|---|---|
| `LICENSE` file | none |
| Code in v0.1.0 | documentation, tests and a shell gate; no runtime code |
| Runtime dependencies | none in v0.1.0 |
| Test dependencies | `pytest` (MIT), `PyYAML` (MIT) — CI only |
| Operator input adapter | outside the repository and not distributed here |
| Recordings | outside the repository; each carries its own license |
| Vendor code or assets | none copied |

## 2. Decision recorded on 2026-11-26

The repository is created **without** a `LICENSE` file until the ecosystem
review closes. Adding MIT now would pre-empt the organization decision.

The review must decide before the ecosystem reaches v1.0:

1. The copyright holder and year for new repositories.
2. Whether MIT is the intended license for capability repositories.
3. How operator input adapters and session records are licensed and surfaced;
   they are not part of this repository.
4. Whether a `THIRD_PARTY_NOTICES.md` is required once ROS 2 packages enter
   the M2 runtime.

## 3. Third-party inventory (to verify at M1/M2)

| Dependency | Use | Known/probable license | Risk |
|---|---|---|---|
| Python standard library | M1 core | PSF | Low |
| pytest | tests only | MIT | Low |
| PyYAML | manifest parsing | MIT | Low |
| ROS 2 Humble | M2 runtime | Apache-2.0 | Low; keep notices |
| CycloneDDS | M2 RMW (system-provided) | EPL-2.0 / EDL | Medium; no vendoring |
| Gamepad/SDL client library | operator-side adapter, not adopted | per library | Medium; must stay out of the repository |
| Session recordings | outside the repository | per record | Must not enter git |

## 4. Open questions

- [ ] Confirm the copyright holder and year.
- [ ] Confirm MIT for this capability repository.
- [ ] Define how the operator-side input adapter is licensed and recorded.
- [ ] Decide the notice requirement for the ROS 2 runtime stack.
- [ ] Record the ecosystem-wide decision in `.github/docs/license-review.md`.

## 5. Related

- [`.github/docs/license-review.md`](https://github.com/JCHENG-Robotics/.github/blob/main/docs/license-review.md)
- [Acceptance report](ACCEPTANCE.md)
- [README](README.md)
