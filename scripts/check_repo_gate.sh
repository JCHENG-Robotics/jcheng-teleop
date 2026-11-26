#!/usr/bin/env bash
# Repository gate for jcheng-teleop. Run locally or from CI.
#
#   bash scripts/check_repo_gate.sh
#
# It checks the required document set, the absence of a LICENSE file, secrets,
# model weights and recordings, oversized files, relative links and the tests.
# It touches no robot and opens no device.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
require_file() {
  if [[ ! -f "$1" ]]; then
    echo "MISSING: $1" >&2
    fail=1
  fi
}

for f in \
  README.md \
  README.zh-CN.md \
  ROADMAP.md \
  CHANGELOG.md \
  ACCEPTANCE.md \
  LICENSE-REVIEW.md \
  VERSION \
  .gitignore \
  capability.yaml \
  docs/ARCHITECTURE.md \
  docs/TELEOP_CORE.md \
  docs/SAFETY_MODEL.md \
  docs/DATA_COLLECTION.md \
  docs/INTEGRATION_CONTRACT.md \
  docs/DEPENDENCY_REVIEW.md \
  docs/INPUT.md \
  docs/M1_PLAN.md \
  docs/proposals/TELEOP_COMMAND_V0.2.md \
  docs/proposals/SYSTEM_TELEOP_INTAKE.md \
  pyproject.toml \
  src/jcheng_teleop/cli.py \
  tests/test_contract.py \
  tests/test_no_hardware.py \
  tests/test_session.py \
  scripts/check_repo_gate.sh \
  evidence/20261126_scaffold/README.md \
  evidence/20261126_m0_design/README.md \
  evidence/20261126_m0_design/review.md \
  evidence/20261126_m1_core/README.md \
  evidence/20261126_m1_core/review.md \
  .github/workflows/ci.yml
do
  require_file "$f"
done

# The organization license review is open: no LICENSE file yet.
if [[ -e LICENSE ]]; then
  echo "ERROR: LICENSE must not exist before the license review is approved." >&2
  fail=1
fi

# No credentials. This script is excluded because it contains the pattern.
if grep -RIqE \
  --exclude-dir=.git \
  --exclude='check_repo_gate.sh' \
  'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----' \
  . ; then
  echo "ERROR: possible secret material found." >&2
  fail=1
fi

# No model weights, recordings or rosbag/MCAP data in the tree.
if find . -path ./.git -prune -o \
    \( -name '*.pt' -o -name '*.onnx' -o -name '*.engine' \
       -o -name '*_openvino_model' -o -name '*.bag' -o -name '*.mcap' \
       -o -name '*.db3' -o -name '*.mp4' -o -name '*.avi' \) -print \
    | grep -q .; then
  echo "ERROR: model weights or recorded data found; keep them outside the repository." >&2
  fail=1
fi

# No dataset or model store inside the repository.
for d in datasets models recordings sessions captures episodes; do
  if [[ -d "$d" ]] && find "$d" -type f -print | grep -q .; then
    echo "ERROR: $d/ must stay outside the repository." >&2
    fail=1
  fi
done

# No oversized files (catches accidental blobs before they enter history).
big="$(find . -path ./.git -prune -o -type f -size +5M -print)"
if [[ -n "$big" ]]; then
  echo "ERROR: files larger than 5 MB:" >&2
  echo "$big" >&2
  fail=1
fi

# Relative Markdown links must resolve from the file that contains them.
while IFS= read -r f; do
  dir="$(dirname "$f")"
  while IFS= read -r link; do
    case "$link" in
      http://*|https://*|mailto:*|'#'*|'') continue ;;
    esac
    target="${link%%#*}"
    [[ -z "$target" ]] && continue
    if [[ ! -e "$dir/$target" ]]; then
      echo "BROKEN LINK in $f: $link" >&2
      fail=1
    fi
  done < <(grep -oE '\]\([^)]+\)' "$f" | sed -e 's/^](//' -e 's/)$//')
done < <(find . -path ./.git -prune -o -name '*.md' -print)

if [[ "$fail" -ne 0 ]]; then
  echo "Repository gate FAILED" >&2
  exit 1
fi

echo "== tests"
python3 -m pytest -q tests

echo "Repository gate OK: document set, manifest, no LICENSE, no secrets, no weights, no recordings, links resolve"
