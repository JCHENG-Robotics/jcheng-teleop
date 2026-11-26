# Data collection and provenance — jcheng-teleop

> Status: **Proposed** as of 2026-11-26; to be frozen at M3.
> No recorder exists. No capture, dataset or model weight is stored in this
> repository. The learning dataset contract is owned by `jcheng-learning` and
> is not yet frozen; this document records the negotiation boundary.

## 1. Ownership boundary

| Concern | Owner | This repository |
|---|---|---|
| Raw operator input, mapped action, wire command, session events | `jcheng-teleop` | Writes an immutable **capture package** outside git |
| Training dataset schema (`jcheng.dataset.v1`), writer, validator, LeRobot export | `jcheng-learning` | Consumes the frozen contract; provides an adapter, not a second schema |
| Measured robot state | `jcheng-system` (bus read) or `jcheng-simulation` (truth) | Reads and records; never fabricates |
| Policy artifacts and training | `jcheng-learning` | Never trains, selects or stores weights |
| Benchmark scoring | `jcheng-benchmark` | Exports JSONL; does not import the harness at runtime |
| Task recipe and run provenance | `jcheng-applications` | May reference a task/run id; does not own recipes |

The capture package is **teleop-local**. It becomes a cross-repository
contract only when another repository consumes it. Writing
`jcheng.dataset.v1` directly from teleop requires an approved
`jcheng-interfaces` proposal and a new contract hash, because teleop would
then be a cross-repository dataset producer. Until that approval, teleop
produces capture packages and the adapter converts them through the
learning-owned writer. The learning writer and `docs/m1/` contract currently
exist only as an uncommitted 0.2.0 working tree; they are not a stable
dependency until merged and frozen.

### 1.1 Mapping to the learning `source_class`

Learning's `jcheng.dataset.v1` has one dataset-level `source_class`
(`synthetic|simulation|public-real|own-real`) and currently forbids mixing
classes in one dataset. Teleop records two orthogonal fields
(`environment_class` and `source_class`). The adapter maps them explicitly:

| Teleop `environment_class` | Teleop `source_class` | Learning dataset `source_class` | Note |
|---|---|---|---|
| `mock` | `scripted`/`human_teleop` | `synthetic` | Mock is not a physical robot |
| `simulation` | `human_teleop`/`policy_execution` | `simulation` | Simulator truth, never hardware |
| `hardware` | `human_teleop`/`human_correction`/`autonomous_grasp`/`policy_execution` | `own-real` | Per-episode teleop source stays in the sidecar |
| any | `replay` | not exported as a new dataset | Replay is evaluation, not a demonstration |

A mixed-source collection is split into one dataset per learning
`source_class`, or the learning contract must add per-episode provenance
before a mixed dataset is written. Teleop must not flatten
`environment_class` into `source_class` or relabel simulation as `own-real`.

## 2. Capture package

One package per session or per episode set, written under an
operator-controlled data root outside any git worktree:

```text
<data-root>/captures/<capture_id>/
├── manifest.json          # capture identity, environment, provenance, files
├── input.jsonl            # accepted operator input samples
├── action.jsonl           # mapped action intents (post-conditioning)
├── command.jsonl          # wire commands and gateway results
├── observation.jsonl      # measured/commanded state, simulation truth
├── events.jsonl           # session, safety, limit, fault and annotation events
├── media/                 # optional camera frames or video references
├── SHA256SUMS             # every file except itself
└── README.txt             # human-readable capture summary (optional)
```

Rules:

- The package is append-only while recording; after `SEALED` it is immutable.
- A corrected export creates a new `capture_id`; it never edits the old one.
- No symlinks, hardlinks, absolute paths, `..` components or unlisted files.
- The package never lives inside the repository, a git worktree, or the
  simulation asset tree.
- `SHA256SUMS` covers every file and is itself excluded; a derived dataset
  records the capture hash.

## 3. Manifest

`manifest.json` is versioned (`jcheng.teleop.capture.v1`). Required fields:

| Group | Fields |
|---|---|
| Identity | `schema`, `capture_id`, `created_at`, `teleop_version`, `git_commit`, `contract_hash`, `profile_id`, `profile_hash`, `binding_hash` |
| Environment | `environment_class` (`mock|simulation|hardware`), `source_class` (`human_teleop|human_correction|autonomous_grasp|policy_execution|scripted|replay`), `sim_truth_label` (if simulation) |
| Session | `session_id`, `operator_id`, `operator_role`, `supervisor_id` (hardware), `authorization_ref` (hardware), `lease_ref_hash`, `started_at`, `ended_at` |
| Task | `task_id`, `task_description`, `outcome` (`success|failure|unknown|aborted`), `outcome_source` (`operator|automatic|policy`) |
| Robot | `profile_id`, `profile_hash`, `profile_source` (`system|simulation|fixture`), `joint_names`, `dof`, `has_gripper`, `calibration_id`, `mode_set` |
| Time | `clock_source`, `clock_id`, `offset_ns`, `offset_uncertainty_ns`, `nominal_fps`, `deadman_ms`, `tick_ms` |
| Capture | `files` (path, bytes, sha256), `frame_count`, `episode_count`, `quality_flags`, `limitations` |
| Policy | `policy_id`, `policy_version`, `checkpoint_hash`, `action_chunk` (only for policy execution or correction) |
| Consent | `human_present`, `consent_ref`, `redaction` (when images/audio include people) |

`source_class` and `environment_class` are immutable. A derived dataset keeps
the original values and adds `derived_from`; it never relabels simulation as
hardware.

## 4. Streams

Each JSONL row has `schema`, `tick_id`, `t_mono_ns`, `t_source_ns` (where
applicable), `t_ros_ns` (where synchronized), and `clock_id`. Stream schemas
are `jcheng.teleop.input.v1`, `jcheng.teleop.action.v1`,
`jcheng.teleop.command.v1`, `jcheng.teleop.observation.v1` and
`jcheng.teleop.event.v1`.

### 4.1 `input.jsonl`

The **accepted** sample after validation, plus the source identity and whether
a rejection occurred. Rejected samples are recorded in `events.jsonl`, not
silently omitted. This is the adapter-normalized raw operator input; if the
adapter exposes pre-normalization device values, they are carried in an
optional `raw` object with their units, but the control path never uses them.

```json
{"schema":"jcheng.teleop.input.v1","tick_id":42,"t_mono_ns":123456789,
 "source_id":"keyboard_01","source_class":"keyboard","seq":42,
 "mode":"JOINT_VELOCITY","joint_velocities_rad_s":[0.1,0,0,0,0],
 "gripper_normalized":0.4,"deadman":true,"profile_id":"armpi_ultra",
 "profile_hash":"sha256:...","calibration_id":null}
```

### 4.2 `action.jsonl`

The post-conditioning action intent, before transport. This is the primary
learning action when the action space is supported. It records the requested
and applied values after clamping, and the limit events.

### 4.3 `command.jsonl`

The wire command actually sent (or the transport error), the lease reference
(hashed, not the raw id), the gateway result and the latency. When the system
reports an applied target or a measured post-state, it is recorded as
`applied` with the system's `truth`/`verification` label; teleop never invents
an applied value. It never records a token or raw credential.

### 4.4 `observation.jsonl`

Separate rows for:

- `truth: measured`, `verification: bus` — a bus read (hardware);
- `truth: commanded` — a command cache such as `/joint_states`; labelled as
  not measurement;
- `truth: simulated`, `verification: simulator` — simulation state, with the
  truth topic label.

The three are never merged into one "state" field. A training dataset that
claims `bus_read` must be backed by `measurements` rows.

### 4.5 `events.jsonl`

Session transitions, deadman edges, limit clamps, sequence/stamp rejections,
lease events, gateway outcomes, recorder health, operator annotations and
mode changes. Every event has a code, severity, time and detail. Event codes
are teleop-local unless they map to the canonical registry.

## 5. Time synchronization

| Clock | Use |
|---|---|
| Operator host monotonic | Control loop, watchdog, ordering, replay |
| Adapter source clock | Sample provenance; may be the same monotonic clock |
| Robot/ROS time | Observation alignment when the system provides it |
| Simulation time | Simulation observation alignment; never mixed with hardware |

Rules:

- Control decisions use the operator host monotonic clock only.
- `t_source_ns` is preserved, never rewritten. An offset estimate and its
  uncertainty are recorded separately.
- Alignment uses nearest-neighbor within a declared skew threshold; it does
  not silently interpolate or rebase.
- A skew above the threshold marks the episode `sync_degraded` and records the
  affected rows. A degraded episode is not silently exported as clean.
- A capture that spans a clock source change is split or marked; it is never
  spliced into one monotonic timeline.
- The system's `/joint_states` command cache is not a time reference for
  measurement.

## 6. Provenance taxonomy

| Field | Values | Rule |
|---|---|---|
| `environment_class` | `mock`, `simulation`, `hardware` | Immutable; determines what evidence level is allowed |
| `source_class` | `human_teleop`, `human_correction`, `autonomous_grasp`, `policy_execution`, `scripted`, `replay` | One value per episode; a mixed episode is split |
| `outcome` | `success`, `failure`, `unknown`, `aborted` | `outcome_source` states who decided |
| `operator_role` | `teleoperator`, `supervisor`, `annotator` | Hardware sessions require an authorization ref |
| `policy_id` | string or null | Required for policy execution/correction |
| `derived_from` | capture/dataset id | Set on every derived artifact |

Rules:

- A hardware episode requires `authorization_ref`, `operator_id`, `session_id`
  and a bus measurement if it claims measured pose.
- A simulation episode requires the simulator repo/version/profile hash and
  the truth topic label.
- A synthetic/scripted episode requires the generator name/version/seed/config
  hash and is never called real.
- A correction episode records the policy action that preceded the human
  correction; it does not replace the policy action with the corrected one.
- A replay is labelled `replay`; it is not a new demonstration.
- Relabelling is forbidden. A new label means a new artifact with
  `derived_from`.

## 7. Quality gates

A capture is `valid`, `degraded` or `invalid`. The validator reports every
check ID; it never auto-repairs.

| Group | Checks (examples) |
|---|---|
| Identity | Manifest parses; required fields present; hashes match; profile/contract/binding hashes present |
| Completeness | Expected tick coverage ≥ 99.9%; every gap has an event; frame indices contiguous; no duplicate `tick_id` |
| Time | Monotonic `t_mono_ns`; `t_source_ns` non-decreasing; sync uncertainty recorded; no silent rebase |
| Values | All finite; vector lengths match the profile; units match the mode; gripper range valid |
| Safety | Deadman edges consistent; stop episodes have one mode-specific stop intent; limit events have requested/applied values; no command after stop |
| Provenance | Environment/source class present; hardware authorization present; simulation truth label present; no sim-as-hardware |
| Alignment | Action/observation skew within threshold; camera stamps within skew; no fabricated frame |
| Storage | Every file listed; SHA256SUMS verifies; no path escape; no oversized/unlisted file |

Quality metrics for evaluation (not a safety certification):

- tick coverage and maximum gap;
- loop jitter p50/p95/p99;
- action/observation skew p50/p95;
- limit events per minute and saturation ratio;
- deadman releases and stop latency;
- zero-command ratio and command smoothness (jerk);
- provenance completeness;
- replay divergence.

## 8. Dataset adapter and LeRobot mapping

The learning-owned proposal is `jcheng.dataset.v1` with
`action.kind: joint_position_absolute` in its M1 scope. The current
`TeleopCommand` v0.1 wire carries velocity only and has no gripper field, so a
velocity-only episode cannot be silently converted into an absolute-position
dataset. The adapter must either:

1. use the captured **position action intent** (leader/position mode) for
   `joint_position_absolute`, or
2. label the episode with a different action kind and wait for the learning
   contract to accept it, or
3. keep the episode as capture-only and not export it as a training dataset.

It never integrates velocity into a fake target or relabels a velocity action
as a position action.

When the contracts are frozen, the mapping is:

| `jcheng.dataset.v1` | Teleop capture |
|---|---|
| `observation.state` | measured joint positions (bus read) or simulation truth; never command cache |
| `action` | position action intent (preferred) or the contract-approved velocity action |
| `observation.images.*` | camera frames with `stamp_ns`, `frame_id`, `calibration_id` |
| `timestamp` | seconds from episode start on the chosen clock |
| `task` | operator/task description |
| `fps` | declared; 30 FPS for SmolVLA-style export, 50 Hz capture may be resampled only with a documented policy |
| `provenance` | sidecar with capture hash, environment/source class, profile/contract hashes |

LeRobot v3.0 export:

- `lerobot==0.7.0` is the learning-side pin; teleop does not import LeRobot.
- `meta/info.json` keeps the standard fields; JCHENG-specific provenance goes
  in a sidecar (`jcheng/export.json`, `jcheng/provenance.json`) because LeRobot
  may drop unknown fields.
- `finalize()` is mandatory before `push_to_hub` or packaging.
- The capture declares its required camera set; a missing required camera makes
  the episode invalid, not silently black.
- A 30 FPS SmolVLA export from a 50 Hz capture records the resampling policy
  and does not duplicate frames to fake a higher rate.

## 9. Replay and anomaly detection

Replay is offline and has no gateway port. It uses the same core with a fake
clock, so a replay cannot accidentally connect to a live system.

| Mode | Input | What is compared |
|---|---|---|
| Input replay | `input.jsonl` | Recorded action intent vs re-derived action intent |
| Command replay | Recorded action intent | Recorded wire command vs re-derived wire command |
| Episode replay | All rows | Timing, events, limits, stop path and provenance |

Anomaly codes include: non-monotonic time, sequence gap, missing tick, action
divergence above the declared epsilon, unexpected limit clamp, deadman edge
mismatch, lease/gateway state mismatch, missing measurement row, provenance
mismatch and data-hash mismatch. A divergence is a finding, not a reason to
edit the recording.

The replay report is an evaluation artifact. It never rewrites the capture and
is never reported as a new demonstration or as hardware evidence.

## 10. Privacy, retention and storage

- Capture data stays outside git and outside the repository tree.
- Raw operator video/audio is optional; if people appear, record consent and a
  redaction status. No biometric processing is in scope.
- Tokens, lease ids and credentials are never recorded; lease references are
  hashed.
- Retention is operator-defined; deletion is explicit and recorded. A deleted
  capture is not silently re-created from a cache.
- A capture that fails validation is retained (for diagnosis) but marked
  invalid; it is not exported.
- Dataset storage and model weights follow `jcheng-learning` and
  `/opt/jcheng/models/`; no weights in this repository.

## 11. M3/M4 acceptance summary

M3:

- 30 episodes × 60 s, valid capture, complete provenance.
- 0 simulation episodes labelled hardware.
- Recorder cannot block stop; disk-full test stops the session.
- Re-read and hash verification pass.

M4:

- Byte-identical replay of the same capture.
- Benchmark JSONL export with `data_source: recorded` only for genuine
  captures.
- LeRobot round-trip equality (frame count, dimensions, task, timestamps,
  provenance sidecar).
- No gateway/device/DDS in replay.

## 12. Open issues

- `jcheng.dataset.v1` is an untracked learning proposal, not a frozen contract.
- `jcheng-interfaces` has no dataset/episode schema; teleop cannot write a
  cross-repository dataset until a proposal is approved.
- The learning contract's M1 action space is absolute joint position only;
  velocity teleoperation and continuous gripper need a contract decision.
- The system's measured state at bus-read rate is not yet characterized for
  capture; `/joint_states` is a command cache.
- Camera ingestion and timestamp alignment are perception-owned; teleop
  records references and stamps, it does not decode or re-encode video in M3.
- A 30 FPS SmolVLA export from a 50 Hz capture needs a documented resampling
  policy and a quality check.

## 13. Related

- [Architecture](ARCHITECTURE.md)
- [Teleop core](TELEOP_CORE.md)
- [Safety model](SAFETY_MODEL.md)
- [Integration contract](INTEGRATION_CONTRACT.md)
- [Dependency review](DEPENDENCY_REVIEW.md)
- [`jcheng-learning`](https://github.com/JCHENG-Robotics/jcheng-learning) — dataset contract and training ownership; `docs/m1/` is not yet on `main`.
- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)
- [LeRobot dataset v3.0](https://huggingface.co/docs/lerobot/lerobot-dataset-v3)
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)
- [`.github`](https://github.com/JCHENG-Robotics/.github)
