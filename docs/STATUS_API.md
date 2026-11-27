# Teleop status API (M5)

> Status: **Implemented in the ROS demo harness**, 2026-11-26. Read-only,
> loopback-only, presentation contract for the studio teleop panel. It is not
> a lease, a command or a motion surface.

## Endpoint

```text
GET http://127.0.0.1:<status_port>/v1/status
```

- The server binds `127.0.0.1` only; any other host is rejected at construction.
- Only `GET /v1/status` exists. `POST` returns 405, any other path 404.
- No request body, no authentication token, no lease and no stop endpoint.
- `Cache-Control: no-store`.
- Enabled by the `jcheng_teleop_publisher` parameter `status_port`; `0`
  (default) disables the server.
- Stop authority stays in `jcheng-system`; the panel must call the system stop
  path, never this server.

## Status-only entry point

`jcheng_teleop_status --port 8770` serves the same loopback contract without
starting the test-only intent publisher. The payload reports
`phase=starting`, `input.present=false` and `input.stale=true`; it never
fabricates a live sample. This is the endpoint the studio can poll when no
operator input adapter is connected, and the row must stay degraded. A
production teleop runtime still needs the `intent_source` approval and a real
input/lease adapter.

## Schema `jcheng.teleop.status.v1`

```json
{
  "schema": "jcheng.teleop.status.v1",
  "teleop_version": "0.3.0",
  "contract_hash": "sha256:...",
  "profile_id": "armpi_ultra_demo",
  "profile_hash": "sha256:...",
  "lease_ref": "sha256:...",
  "phase": "starting|running|completed|faulted",
  "generated_at_ns": 123456789,
  "stale_after_ms": 1000,
  "input": {
    "present": true,
    "age_ms": 20.0,
    "stale": false,
    "deadman": true,
    "mode": "JOINT_VELOCITY",
    "source_id": "ros_virtual",
    "seq": 13,
    "t_source_ns": 260000000
  },
  "last_wire_seq": 12,
  "capture": {
    "enabled": true,
    "capture_id": "sim-20261126",
    "environment_class": "simulation",
    "rows_written": {"input": 100, "action": 100, "command": 0, "observation": 240, "events": 1},
    "rejected_observations": 0,
    "fault": null
  },
  "limitations": ["read-only status; no lease, intent or motion authority", "..."]
}
```

Rules:

- `lease_ref` is the hash of the operator-supplied lease id; the raw id is
  never exposed.
- `input.stale` is true when there is no sample or `age_ms > stale_after_ms`.
  A stale or missing status must render as degraded, never as ready.
- `phase` describes the demo harness only; it is not a session state machine
  and cannot be used as a lease.
- `capture` is present only when recording is enabled; `rows_written` are
  counters, not evidence that the rows reached disk (`fault` says otherwise).

## Consumer rules (studio)

- Poll at 2–5 Hz; render the age and the stale flag, not just a color.
- Show the profile/contract hashes and the capture id next to the state.
- Never infer "armed" or "lease held" from this payload alone; the system
  safety/lease view is separate and authoritative.
- A missing endpoint or a 5xx is degraded, not ready.

## Non-goals

- No intent submission, no lease acquisition, no stop, no device and no DDS.
- No remote (non-loopback) exposure; a future remote UI needs an authenticated
  proxy with a written contract.
