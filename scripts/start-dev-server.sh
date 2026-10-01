#!/usr/bin/env bash
# Starts the web app + API for the dev container, in the background.
#
# Run by the dev container on every start (postStartCommand), so the site is
# already up when VS Code attaches; safe to run by hand too. If the server
# already answers on $PORT it does nothing.
#
# Reload is limited to src/ so edits elsewhere (output/, .venv/) don't restart
# it. RESUME_ALLOW_EMBEDDING=1 lets VS Code's Simple Browser show the page in an
# iframe; it is set here, for development only — never in the production image.
set -euo pipefail

PORT="${PORT:-8000}"
LOG="${TMPDIR:-/tmp}/resume-engine-dev-server.log"
URL="http://127.0.0.1:${PORT}"

cd "$(dirname "$0")/.."

is_up() { curl -fsS -m 2 "${URL}/healthz" >/dev/null 2>&1; }

if is_up; then
  echo "resume-engine: already running at http://localhost:${PORT}"
  exit 0
fi

RESUME_ALLOW_EMBEDDING=1 nohup uv run uvicorn resume_builder.api:app \
  --host 0.0.0.0 --port "${PORT}" --reload --reload-dir src \
  >"${LOG}" 2>&1 &
disown

for _ in $(seq 1 60); do
  if is_up; then
    echo "resume-engine: running at http://localhost:${PORT} (log: ${LOG})"
    exit 0
  fi
  sleep 1
done

echo "resume-engine: server did not come up within 60s; last log lines:" >&2
tail -n 20 "${LOG}" >&2 || true
exit 1
