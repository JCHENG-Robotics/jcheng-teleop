"""Static boundary check: the teleop capability must not touch devices or motion.

The scan covers Python, YAML, shell, XML and config files outside the
documentation, evidence, CI and test directories. Documentation may name
forbidden devices when explaining the boundary; code and configs may not use
them.

The forbidden set includes operator input devices. v0.1.0 ships no input
adapter: a physical adapter is operator-side and outside the capability
boundary, and `capability-manifest.v1` cannot express device access.

This file itself contains the forbidden tokens, so the tests directory is
excluded from the scan.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_DIRS = {
    ".git",
    "tests",
    "docs",
    "evidence",
    ".github",
    "__pycache__",
    ".pytest_cache",
    ".venv",
}
TEXT_SUFFIXES = {
    ".py",
    ".yaml",
    ".yml",
    ".sh",
    ".xml",
    ".xacro",
    ".cfg",
    ".toml",
    ".json",
    ".txt",
}
FORBIDDEN = (
    # Robot devices and vendor paths.
    "/dev/",
    "serial.Serial",
    "pyserial",
    "socketcan",
    "can0",
    "pigpio",
    "RPi.GPIO",
    "gpiod",
    "cv2.VideoCapture",
    "picamera",
    "/ros_robot_controller",
    "set_motor_speeds",
    "MotorsSpeedControl",
    "controller/mecanum",
    # Motion and hardware commands.
    "ExecuteMotion",
    "execute_motion",
    "/move_action",
    "/cmd_vel",
    # Operator input devices (adapter lives outside this repository).
    "evdev",
    "pygame.joystick",
    "hidapi",
    "usb.core",
)
ARTIFACT_SUFFIXES = {
    ".pt",
    ".onnx",
    ".engine",
    ".bag",
    ".mcap",
    ".db3",
    ".mp4",
    ".avi",
}


def _scanned_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(ROOT).parts[:-1]
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        yield path


def test_no_device_or_motion_tokens():
    problems = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN:
            if token in text:
                problems.append(f"{path.relative_to(ROOT)}: {token}")
    assert not problems, "forbidden device/motion tokens found:\n" + "\n".join(
        problems
    )


def test_no_model_weights_or_recordings():
    found = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.relative_to(ROOT).parts:
            continue
        if path.suffix in ARTIFACT_SUFFIXES:
            found.append(str(path.relative_to(ROOT)))
    assert not found, "model weights or recordings found:\n" + "\n".join(found)


def test_no_data_or_session_store_directories():
    for name in ("datasets", "models", "recordings", "sessions"):
        directory = ROOT / name
        if directory.is_dir():
            files = [p for p in directory.rglob("*") if p.is_file()]
            assert not files, f"{name}/ must stay outside the repository"


def test_gitignore_covers_data_and_weights():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("datasets/", "models/", "recordings/", "sessions/"):
        assert pattern in ignored, f".gitignore missing {pattern}"
    for pattern in ("*.pt", "*.onnx", "*.engine", "*.bag", "*.mcap"):
        assert pattern in ignored, f".gitignore missing {pattern}"
