#!/usr/bin/env bash
# Dev container entrypoint.
# Prepares GitHub SSH access (host key + correct owner/perms on the forwarded
# ~/.ssh — bind mounts from Windows come in with no real Unix ownership, and
# OpenSSH's StrictModes rejects config/key files that aren't owned by root
# even when the permission bits are otherwise correct) and marks /workspace
# as a safe git directory (needed because the container runs as root but the
# mounted repo is owned by the host user).
set -euo pipefail

if [ -d "$HOME/.ssh" ]; then
  chown -R root:root "$HOME/.ssh" || true
  chmod 700 "$HOME/.ssh" || true
  find "$HOME/.ssh" -type f -exec chmod 600 {} \; 2>/dev/null || true
  find "$HOME/.ssh" -name "*.pub" -exec chmod 644 {} \; 2>/dev/null || true

  if [ ! -f "$HOME/.ssh/known_hosts" ] || ! grep -q "github.com" "$HOME/.ssh/known_hosts" 2>/dev/null; then
    ssh-keyscan -t rsa,ecdsa,ed25519 github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
  fi
fi

git config --global --add safe.directory /workspace || true

/usr/local/bin/welcome.sh || true

exec "$@"