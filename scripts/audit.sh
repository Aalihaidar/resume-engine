#!/usr/bin/env bash
# Dependency vulnerability audit of uv.lock, shared by CI and `make audit`.
#
#   scripts/audit.sh runtime   packages that ship in the production image;
#                              any known vulnerability fails (exit 1)
#   scripts/audit.sh dev       dev-only tooling; findings are reported as a
#                              warning and never fail — they don't reach
#                              production, and Dependabot security updates
#                              fix them
#
# Audits the lock (exported with hashes) rather than the installed venv, so
# the result is exactly what uv.lock pins and the local project itself isn't
# reported as "not found on PyPI".
#
# pip-audit makes one request per package to PyPI and has no retry, so a
# single dropped connection used to fail the job with no vulnerability found.
# Network errors are retried with backoff; a real finding fails immediately.
set -euo pipefail

scope="${1:-}"
case "$scope" in
  runtime) export_args=(--no-dev) ; audit_args=(--strict) ;;
  dev)     export_args=(--only-dev); audit_args=() ;;
  *) echo "usage: $0 runtime|dev" >&2; exit 2 ;;
esac

attempts=3
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
requirements="$workdir/requirements.txt"
stderr_log="$workdir/stderr.log"

uv export --frozen "${export_args[@]}" --no-emit-project --format requirements.txt -q -o "$requirements"

run_audit() {
  local attempt
  for attempt in $(seq 1 "$attempts"); do
    if uv run --frozen pip-audit "${audit_args[@]}" --disable-pip --progress-spinner off \
      -r "$requirements" 2>"$stderr_log"; then
      cat "$stderr_log" >&2
      return 0
    fi
    # Anything other than a requests/urllib3 exception is a real result
    # (vulnerabilities found, bad input): report it without retrying.
    if ! grep -q -E "(requests|urllib3)\.exceptions\." "$stderr_log"; then
      cat "$stderr_log" >&2
      return 1
    fi
    if [ "$attempt" -lt "$attempts" ]; then
      echo "pip-audit: network error talking to PyPI (attempt $attempt/$attempts), retrying in $((attempt * 15))s" >&2
      sleep $((attempt * 15))
    fi
  done
  cat "$stderr_log" >&2
  echo "pip-audit: PyPI still unreachable after $attempts attempts" >&2
  return 1
}

if run_audit; then
  exit 0
fi

if [ "$scope" = "dev" ]; then
  msg="A dev-only package has a known vulnerability (or PyPI was unreachable); see the log above. It does not ship in the image: merge the Dependabot security update or run 'uv lock --upgrade-package <name>'."
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    echo "::warning title=Dev dependency audit::$msg"
  else
    echo "warning: $msg" >&2
  fi
  exit 0
fi
exit 1
