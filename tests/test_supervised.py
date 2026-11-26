"""M6 supervised authorization and offline preflight tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ast
import json
from pathlib import Path

import pytest
import yaml

from jcheng_teleop.core.profile import load_binding, load_profile, resolve_profile
from jcheng_teleop.supervised import (
    HARDWARE_BLOCKERS,
    SupervisedAuthorization,
    SupervisedError,
    run_preflight,
)
from jcheng_teleop.supervised import cli

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "sha256:" + "0" * 64
HASH = "sha256:" + "1" * 64
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def _profile():
    return resolve_profile(
        load_profile(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
        load_binding(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
    )


def _raw(**overrides):
    profile = _profile()
    base = {
        "schema": "jcheng.teleop.authorization.v1",
        "session_id": "session-m6-1",
        "operator_id": "operator-1",
        "supervisor_id": "supervisor-1",
        "authorization_ref": "auth-20261126-01",
        "workspace_clear": True,
        "checklist_hash": HASH,
        "profile_id": profile.profile_id,
        "profile_hash": profile.profile_hash,
        "contract_hash": CONTRACT,
        "joint_names": list(profile.joint_names),
        "motion_scope": ["joint1"],
        "max_velocity_rad_s": 0.2,
        "issued_at": (NOW - timedelta(hours=1)).isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    base.update(overrides)
    return base


def _auth(**overrides) -> SupervisedAuthorization:
    return SupervisedAuthorization.from_mapping(_raw(**overrides))


def test_valid_authorization_passes() -> None:
    _auth().validate(profile=_profile(), contract_hash=CONTRACT, now=NOW)


def test_operator_and_supervisor_must_differ() -> None:
    with pytest.raises(SupervisedError, match="different people"):
        _auth(supervisor_id="operator-1").validate(
            profile=_profile(), contract_hash=CONTRACT, now=NOW
        )


def test_workspace_must_be_clear() -> None:
    with pytest.raises(SupervisedError, match="workspace_clear"):
        _auth(workspace_clear=False).validate(
            profile=_profile(), contract_hash=CONTRACT, now=NOW
        )


def test_joint_order_must_match_the_profile() -> None:
    profile = _profile()
    reversed_names = list(reversed(profile.joint_names))
    with pytest.raises(SupervisedError, match="joint_names"):
        _auth(joint_names=reversed_names).validate(
            profile=profile, contract_hash=CONTRACT, now=NOW
        )


def test_scope_unknown_joint_is_refused() -> None:
    with pytest.raises(SupervisedError, match="unknown joints"):
        _auth(motion_scope=["joint99"]).validate(
            profile=_profile(), contract_hash=CONTRACT, now=NOW
        )


def test_velocity_above_the_profile_limit_is_refused() -> None:
    with pytest.raises(SupervisedError, match="exceeds the profile limit"):
        _auth(max_velocity_rad_s=5.0).validate(
            profile=_profile(), contract_hash=CONTRACT, now=NOW
        )


def test_expired_authorization_is_refused() -> None:
    with pytest.raises(SupervisedError, match="expired"):
        _auth(
            issued_at=(NOW - timedelta(hours=2)).isoformat(),
            expires_at=(NOW - timedelta(hours=1)).isoformat(),
        ).validate(profile=_profile(), contract_hash=CONTRACT, now=NOW)


def test_not_yet_valid_authorization_is_refused() -> None:
    with pytest.raises(SupervisedError, match="not valid yet"):
        _auth(
            issued_at=(NOW + timedelta(hours=1)).isoformat(),
            expires_at=(NOW + timedelta(hours=2)).isoformat(),
        ).validate(profile=_profile(), contract_hash=CONTRACT, now=NOW)


def test_authorization_window_is_bounded() -> None:
    with pytest.raises(SupervisedError, match="8 hours"):
        _auth(
            issued_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(hours=9)).isoformat(),
        ).validate(profile=_profile(), contract_hash=CONTRACT, now=NOW)


def test_profile_and_contract_mismatch_are_refused() -> None:
    with pytest.raises(SupervisedError) as exc:
        _auth(profile_hash=HASH, contract_hash=HASH).validate(
            profile=_profile(), contract_hash=CONTRACT, now=NOW
        )
    joined = " ".join(exc.value.problems)
    assert "profile_hash" in joined
    assert "contract_hash" in joined


def test_preflight_reports_blockers_and_never_hardware_ready() -> None:
    report = run_preflight(_auth(), _profile(), contract_hash=CONTRACT, now=NOW)
    payload = report.to_dict()
    assert payload["status"] == "authorized"
    assert payload["hardware_ready"] is False
    assert len(payload["blockers"]) == len(HARDWARE_BLOCKERS)
    assert any("streaming executor" in item for item in payload["blockers"])
    assert any("e-stop" in item for item in payload["blockers"])
    assert payload["authorization_hash"].startswith("sha256:")


def test_preflight_refuses_a_bad_authorization() -> None:
    report = run_preflight(
        _auth(workspace_clear=False), _profile(), contract_hash=CONTRACT, now=NOW
    )
    assert report.status == "refused"
    assert report.hardware_ready is False
    assert any("workspace_clear" in error for error in report.errors)


def test_record_hash_is_deterministic() -> None:
    assert _auth().record_hash() == _auth().record_hash()


def test_cli_preflight_end_to_end(tmp_path: Path, capsys) -> None:
    authorization = tmp_path / "authorization.yaml"
    authorization.write_text(yaml.safe_dump(_raw()), encoding="utf-8")
    code = cli.main(
        [
            "--authorization",
            str(authorization),
            "--profile",
            str(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
            "--binding",
            str(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
            "--contract-hash",
            CONTRACT,
            "--now",
            NOW.isoformat(),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.out
    payload = json.loads(captured.out)
    assert payload["status"] == "authorized"
    assert payload["hardware_ready"] is False


def test_cli_refuses_an_expired_authorization(tmp_path: Path, capsys) -> None:
    authorization = tmp_path / "authorization.yaml"
    raw = _raw(
        issued_at=(NOW - timedelta(hours=2)).isoformat(),
        expires_at=(NOW - timedelta(hours=1)).isoformat(),
    )
    authorization.write_text(yaml.safe_dump(raw), encoding="utf-8")
    code = cli.main(
        [
            "--authorization",
            str(authorization),
            "--profile",
            str(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
            "--binding",
            str(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
            "--contract-hash",
            CONTRACT,
            "--now",
            NOW.isoformat(),
        ]
    )
    assert code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "refused"


def test_cli_reports_a_configuration_error(tmp_path: Path, capsys) -> None:
    authorization = tmp_path / "authorization.yaml"
    authorization.write_text("not: [yaml", encoding="utf-8")
    code = cli.main(
        [
            "--authorization",
            str(authorization),
            "--profile",
            str(ROOT / "examples/armpi_ultra_demo/profile.yaml"),
            "--binding",
            str(ROOT / "examples/armpi_ultra_demo/binding.yaml"),
        ]
    )
    assert code == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_supervised_package_has_no_runtime_imports() -> None:
    for path in (ROOT / "src/jcheng_teleop/supervised").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        forbidden = ("rclpy", "jcheng_teleop.adapters.gateway", "socket", "subprocess")
        for module in modules:
            assert not any(
                module == item or module.startswith(item + ".") for item in forbidden
            ), f"{path.name} imports {module}"
