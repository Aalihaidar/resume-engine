#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "  resume-engine dev container"
echo "  -------------------------------------------------------------"
echo "  uv run resume-build render     build output/resume.pdf"
echo "  uv run pytest                  run tests"
echo "  uv run ruff check .            lint"
echo "  git status                     GitHub SSH is forwarded from host"
echo "  gh auth status                 check GitHub CLI auth"
echo "  -------------------------------------------------------------"
echo ""
