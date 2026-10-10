#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077
if [ "${CENDAVO_APPROVE_PROVIDER_NETWORK:-}" != "yes" ]; then
  echo "Set CENDAVO_APPROVE_PROVIDER_NETWORK=yes to approve model connections for this run." >&2
  exit 2
fi
exec python3 scripts/forge.py run --hours "${CENDAVO_HOURS:-8}" --max-tasks "${CENDAVO_MAX_TASKS:-10}" --approve-provider-network
