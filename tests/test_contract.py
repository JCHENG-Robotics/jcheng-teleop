"""Contract checks for the jcheng-teleop capability manifest.

The checks mirror `capability-manifest.v1.schema.json` in jcheng-interfaces
without adding a jsonschema runtime dependency. They also pin the document set
and the README structure required by the organization documentation standard.
"""

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = yaml.safe_load((ROOT / "capability.yaml").read_text(encoding="utf-8"))

TOP_LEVEL = {
    "schema_version",
    "name",
    "version",
    "contract",
    "safety",
    "hardware_access",
    "runtime",
}
CONTRACT_HASH = (
    "sha256:afca22a42f7163e0351d185d5a8577b0b51f2f3da4b92278f161a4a7d2c35b1c"
)


def test_top_level_fields():
    assert set(MANIFEST) == TOP_LEVEL


def test_identity_and_version():
    assert MANIFEST["schema_version"] == 1
    assert MANIFEST["name"] == "jcheng-teleop"
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", MANIFEST["version"])
    assert MANIFEST["version"] == (ROOT / "VERSION").read_text().strip()


def test_contract_hash_and_ranges():
    contract = MANIFEST["contract"]
    assert set(contract) == {"interfaces", "contract_hash", "system_api"}
    assert contract["interfaces"] == ">=0.2,<0.3"
    assert contract["system_api"] == ">=0.1,<0.2"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", contract["contract_hash"])
    assert contract["contract_hash"] == CONTRACT_HASH


def test_safety_is_offline_and_scoped_out():
    safety = MANIFEST["safety"]
    assert set(safety) == {
        "class",
        "scopes",
        "requires_lease",
        "max_rate_hz",
        "deadman_ms",
    }
    assert safety["class"] == "offline"
    assert safety["scopes"] == []
    # Required by the v1 schema; the envelope is declared but inactive while
    # the capability is offline.
    assert safety["requires_lease"] is True
    assert safety["max_rate_hz"] == 50
    assert safety["deadman_ms"] == 300


def test_hardware_access_is_none():
    assert MANIFEST["hardware_access"] == "none"


def test_runtime_surface_is_empty():
    runtime = MANIFEST["runtime"]
    assert set(runtime) == {"ros_domains", "publishes", "subscribes"}
    assert runtime["ros_domains"] == []
    assert runtime["publishes"] == []
    assert runtime["subscribes"] == []


def test_reserved_teleop_stream_is_documented_not_claimed():
    integration = (ROOT / "docs/INTEGRATION_CONTRACT.md").read_text(encoding="utf-8")
    # The stream contract exists in jcheng-interfaces v0.1.0 but is reserved
    # until the system-side intake and the first teleoperation pilot exist.
    assert "TeleopCommand" in integration
    assert "/jcheng/intent/teleop" in integration
    assert MANIFEST["runtime"]["publishes"] == []


def test_document_set_exists():
    for name in (
        "README.md",
        "README.zh-CN.md",
        "ROADMAP.md",
        "CHANGELOG.md",
        "ACCEPTANCE.md",
        "LICENSE-REVIEW.md",
        "docs/ARCHITECTURE.md",
        "docs/TELEOP_CORE.md",
        "docs/SAFETY_MODEL.md",
        "docs/DATA_COLLECTION.md",
        "docs/INTEGRATION_CONTRACT.md",
        "docs/DEPENDENCY_REVIEW.md",
        "docs/INPUT.md",
        "docs/M1_PLAN.md",
        "docs/proposals/TELEOP_COMMAND_V0.2.md",
        "docs/proposals/SYSTEM_TELEOP_INTAKE.md",
        "pyproject.toml",
        "src/jcheng_teleop/cli.py",
        "tests/test_session.py",
        "scripts/check_repo_gate.sh",
        "evidence/20261126_scaffold/README.md",
        "evidence/20261126_m0_design/README.md",
        "evidence/20261126_m0_design/review.md",
        "evidence/20261126_m1_core/README.md",
        "evidence/20261126_m1_core/review.md",
    ):
        assert (ROOT / name).is_file(), f"missing {name}"


def test_roadmap_covers_the_full_m0_to_m9_path():
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    for index in range(10):
        assert f"## M{index} —" in roadmap, f"missing M{index} section"


def test_acceptance_is_explicit_about_m1_scope():
    acceptance = (ROOT / "ACCEPTANCE.md").read_text(encoding="utf-8")
    assert "M1" in acceptance
    assert "L1" in acceptance
    assert "in-process L2" in acceptance or "in-process" in acceptance
    assert "hardware" in acceptance.lower()
    assert "not hardware evidence" in acceptance.lower() or "not a hardware" in acceptance.lower()


def test_readme_required_sections():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in (
        "## Scope and boundary",
        "## Repository layout",
        "## Requirements",
        "## Quick start",
        "## Validation status",
        "## Related repositories",
        "## License",
    ):
        assert heading in text, f"missing section {heading}"


def test_status_vocabulary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"Status: \*\*([^*]+)\*\*", readme)
    assert match, "README status block not found"
    assert match.group(1) in {"Experimental", "Deployed", "Frozen", "Archived"}

    # No ad-hoc status synonyms in the root documents.
    for name in ("README.md", "ROADMAP.md", "ACCEPTANCE.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"\b(Done|Finished|WIP|TODO|TBD)\b", text), name
