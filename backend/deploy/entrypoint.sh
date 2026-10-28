#!/bin/sh
# Image entrypoint. When SECRETS_FILE is set, its KEY=value lines are exported before the
# command runs: the compose demo generates its keys into that file on first start (D60).
# Deploys leave it unset; their environment comes from compose's env_file (D57).
set -eu
if [ -n "${SECRETS_FILE:-}" ]; then
  set -a
  . "$SECRETS_FILE"
  set +a
fi
exec "$@"
