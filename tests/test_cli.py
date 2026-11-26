from __future__ import annotations

import json
from pathlib import Path

from jcheng_teleop.cli import main
from jcheng_teleop.core.model import InputSample, Mode


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "examples" / "armpi_ultra_demo" / "profile.yaml"
BINDING = ROOT / "examples" / "armpi_ultra_demo" / "binding.yaml"


def test_cli_virtual_run(capsys):
    code = main(["--profile", str(PROFILE), "--binding", str(BINDING), "--input", "virtual", "--ticks", "10"])
    assert code == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["ticks"] == 10
    assert summary["submitted"] >= 1


def test_cli_jsonl_run(tmp_path, capsys):
    sample = InputSample(
        schema=InputSample.SCHEMA,
        source_id="jsonl",
        source_class="jsonl",
        seq=0,
        t_source_ns=0,
        t_host_mono_ns=0,
        mode=Mode.JOINT_VELOCITY,
        joint_velocities_rad_s=(0.1, 0.0, 0.0, 0.0, 0.0),
        deadman=True,
        profile_id="armpi_ultra_demo",
    )
    path = tmp_path / "input.jsonl"
    path.write_text(json.dumps(sample.to_dict()) + "\n", encoding="utf-8")
    code = main(
        [
            "--profile",
            str(PROFILE),
            "--binding",
            str(BINDING),
            "--input",
            "jsonl",
            "--jsonl",
            str(path),
            "--ticks",
            "2",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["submitted"] == 2


def test_cli_bad_profile(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("not: a profile\n", encoding="utf-8")
    assert main(["--profile", str(path), "--binding", str(BINDING)]) == 3


def test_cli_keyboard_input(capsys):
    code = main(
        [
            "--profile",
            str(PROFILE),
            "--binding",
            str(BINDING),
            "--input",
            "keyboard",
            "--ticks",
            "4",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["ticks"] == 4


def test_cli_stop_file_requests_system_stop(tmp_path, capsys):
    stop_file = tmp_path / "stop"
    stop_file.write_text("stop\n", encoding="utf-8")
    code = main(
        [
            "--profile",
            str(PROFILE),
            "--binding",
            str(BINDING),
            "--input",
            "virtual",
            "--ticks",
            "5",
            "--stop-file",
            str(stop_file),
        ]
    )
    assert code == 1
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["state"] == "FAULT"
    assert summary["faults"] >= 1


def test_cli_duration_sets_tick_count(capsys):
    code = main(
        [
            "--profile",
            str(PROFILE),
            "--binding",
            str(BINDING),
            "--input",
            "virtual",
            "--duration",
            "0.1",
            "--tick-ms",
            "20",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["ticks"] == 5
