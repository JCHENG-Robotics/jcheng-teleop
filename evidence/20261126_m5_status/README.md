# M5 teleop status API (read-only)

> Status: **Partially verified (mock demo harness, 2026-11-26)**. Read-only
> loopback status only; no hardware, no studio panel yet, no stop path.

## Run

```bash
source /opt/ros/jazzy/setup.bash
source ../jcheng-interfaces/install/setup.bash && source install/setup.bash
PYTHONPATH=$PWD/src:$PYTHONPATH \
  ./install/jcheng_teleop_ros/lib/jcheng_teleop_ros/jcheng_teleop_publisher \
  --ros-args \
  -p profile:=$PWD/examples/armpi_ultra_demo/profile.yaml \
  -p binding:=$PWD/examples/armpi_ultra_demo/binding.yaml \
  -p lease_id:=lease-status-demo -p duration_s:=6.0 -p rate_hz:=50.0 \
  -p status_port:=8765
```

## Result

While running:

```text
{"schema": "jcheng.teleop.status.v1", "phase": "running",
 "profile_id": "armpi_ultra_demo",
 "lease_ref": "sha256:bba477c249aa1cbf656c68706fb7f2a32f3ccd15d76c471fc24e1d21a4a35846"}
{"age_ms": 19.0, "deadman": true, "mode": "JOINT_VELOCITY",
 "present": true, "seq": 42, "source_id": "ros_virtual",
 "stale": false, "t_source_ns": 840000000}
{"enabled": false}
```

After the script ended and 2.45 s passed:

```text
{"input": {"age_ms": 2452.984, "deadman": false, "mode": "JOINT_VELOCITY",
 "present": true, "seq": 300, "source_id": "ros_virtual",
 "stale": true, "t_source_ns": 5980000000},
 "phase": "completed"}
```

`POST /v1/status` → **405**; the only route is `GET /v1/status`.

## Tests

`python3 -m pytest -q tests/test_status.py` — **6 passed**. Full suite:
**159 passed**; gate OK.

Covered: payload schema and fresh state; missing input is stale, not ready;
input older than 1 s is stale; unsupported phase rejected; one read-only route,
404 for another path and 405 for POST; non-loopback bind refused.

## Limits

- Demo harness only: the operator input adapter and the production teleop
  process are not wired. `phase` is the script phase, not a session state.
- `lease_ref` is a hash; the raw lease id is not exposed. The system lease view
  remains authoritative.
- No panel or stop in this evidence; the studio panel and the system stop path
  are the next M5 step.
- No authentication: the server binds loopback only and must not be exposed.
