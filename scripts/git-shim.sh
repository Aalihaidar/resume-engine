#!/usr/bin/env bash
# Dev container only: installed as /usr/local/bin/git by setup-git-hooks.sh.
#
# Runs ensure-git-hooks.sh before every `git commit` (from the terminal and from
# VS Code's Source Control, which both find `git` on PATH) and then hands over to
# the real git unchanged. A commit is never blocked or altered by this wrapper.
REAL_GIT=/usr/bin/git
ENSURE=/workspace/scripts/ensure-git-hooks.sh

# The subcommand is the first argument that is not a global option, e.g. the
# `commit` in `git -c core.quotepath=false -C repo commit -m msg`.
args=("$@")
i=0
while [ "$i" -lt "${#args[@]}" ]; do
  case "${args[$i]}" in
    -c | -C | --git-dir | --work-tree | --namespace | --exec-path) i=$((i + 2)) ;;
    -*) i=$((i + 1)) ;;
    *) break ;;
  esac
done

# Run through bash, and test with -f rather than -x: the dev container sets
# core.fileMode=false, so a checkout may not carry the executable bit.
if [ "${args[$i]:-}" = "commit" ] && [ -f "$ENSURE" ]; then
  REAL_GIT="$REAL_GIT" bash "$ENSURE" || true
fi

exec "$REAL_GIT" "$@"
