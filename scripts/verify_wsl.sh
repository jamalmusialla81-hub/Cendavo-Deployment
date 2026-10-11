#!/bin/sh
# Verify Forge on Linux/WSL2 without starting any Claude agent. Run from the Forge checkout inside WSL2.
# Uses throwaway Forge state for the checks-stage run; the real .cendavo-run queue is only read by `inspect`.
set -eu
cd "$(dirname "$0")/.."
step() { printf '\n== %s\n' "$1"; }
step "Kernel and distribution"
uname -r
( . /etc/os-release && echo "$PRETTY_NAME" ) || true
step "Forge compatibility doctor (WSL2, filesystem, bubblewrap self-test, process groups, limits, locks)"
python3 scripts/forge.py doctor
step "Platform and sandbox tests (includes real bubblewrap boundary tests)"
python3 -m unittest tests.test_forge_platform -v 2>&1 | tee /tmp/forge-platform-tests.log | tail -n 25
if grep -q "skipped 'requires Linux/WSL2" /tmp/forge-platform-tests.log; then
  echo "ERROR: the real bubblewrap tests were skipped; they must run on this host." >&2; exit 1
fi
step "Full Forge test suite"
python3 -m unittest discover -s tests 2>&1 | tail -n 4
step "Forge checks stage through bubblewrap (throwaway state)"
python3 - <<'PY'
import sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, '.')
from scripts import forge
with tempfile.TemporaryDirectory() as tmp:
    st = Path(tmp)
    (st / 'logs').mkdir()
    with patch.multiple(forge, STATE=st, LOGS=st / 'logs', ACTIVE=st / 'active.json', STOP=st / 'STOP'):
        started = time.time()
        forge.tests(99, time.monotonic() + 1800, root=Path('.').resolve())
        print(f'checks stage passed via {forge.forge_platform.checks_sandbox().name} in {time.time() - started:.0f}s')
PY
step "Read-only inspect interface (used by JARVIS on Windows)"
python3 scripts/forge.py inspect --events 3 --progress 0 | python3 -c 'import json,sys; d=json.load(sys.stdin); print("platform", d["platform"], "| tasks", len(d["tasks"]), "| runner_active", d["runner_active"])'
step "Claude Code login (no model call)"
python3 -c 'import sys; sys.path.insert(0, "."); from scripts import forge; print(forge.check_subscription_auth() or "claude.ai Max login verified")'
printf '\nALL NON-AGENT WSL2 CHECKS PASSED\n'
