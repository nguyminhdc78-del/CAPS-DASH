#!/usr/bin/env bash
# Thin wrapper around scripts/soak_test_setup.py - see that file for what a
# soak test actually does and how to read its output. This SETS UP a soak
# run; it does not run one for you, and no number it produces has been
# recorded as "the" soak-test result (see docs/deployment-guide.md, which
# says so plainly rather than implying an unmeasured figure).
#
#   scripts/soak-test.sh                    # the real 8h/4-camera run
#   scripts/soak-test.sh --duration-s 60 --cameras 2 --sample-interval-s 5
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python="${PYTHON:-.venv/bin/python}"
[ -x "$python" ] || python="python3"

exec "$python" scripts/soak_test_setup.py "$@"
