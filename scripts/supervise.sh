#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077
exec python3 scripts/supervisor.py run --hours "${CENDAVO_HOURS:-8}" --max-tasks "${CENDAVO_MAX_TASKS:-10}"
