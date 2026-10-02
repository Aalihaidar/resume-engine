#!/usr/bin/env bash
# Run by the dev container on every start (postStartCommand):
#   1. installs the pre-commit hook if it is missing,
#   2. installs the `git` shim that re-checks that before each commit,
#   3. downloads the hook tools (ruff, cspell, ...) in the background so the
#      first commit does not wait for them.
# Safe to run by hand; every step is idempotent and none of them can fail the start.
set -uo pipefail

cd "$(dirname "$0")/.."

bash scripts/ensure-git-hooks.sh

if [ -w /usr/local/bin ]; then
  install -m 0755 scripts/git-shim.sh /usr/local/bin/git \
    && echo "git hooks: commit-time check enabled (/usr/local/bin/git)"
fi

LOG="${TMPDIR:-/tmp}/resume-engine-hook-envs.log"
if command -v pre-commit >/dev/null 2>&1; then
  (nohup pre-commit install-hooks >"$LOG" 2>&1 &)
elif command -v uv >/dev/null 2>&1; then
  (nohup uv run pre-commit install-hooks >"$LOG" 2>&1 &)
fi
exit 0
