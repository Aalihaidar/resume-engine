#!/usr/bin/env bash
# Dev container entrypoint.
# Prepares GitHub SSH access (host key + correct perms on the forwarded
# ~/.ssh, since bind mounts often come in with the wrong mode bits) and
# marks /workspace as a safe git directory (needed because the container
# runs as root but the mounted repo is owned by the host user).
set -euo pipefail

if [ -d "$HOME/.ssh" ]; then
  chmod 700 "$HOME/.ssh" || true
  find "$HOME/.ssh" -type f -exec chmod 600 {} \; 2>/dev/null || true

  if [ ! -f "$HOME/.ssh/known_hosts" ] || ! grep -q "github.com" "$HOME/.ssh/known_hosts" 2>/dev/null; then
    ssh-keyscan -t rsa,ecdsa,ed25519 github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
  fi
fi

git config --global --add safe.directory /workspace || true

/usr/local/bin/welcome.sh || true

exec "$@"
