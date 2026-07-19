#!/usr/bin/env sh
set -eu
docker compose run --rm worker codex --login
docker compose restart worker
echo "Codex OAuth credentials are stored in the persistent codex_auth Docker volume."
