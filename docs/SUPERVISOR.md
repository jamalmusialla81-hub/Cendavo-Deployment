# Forge Supervisor

`CENDAVO_APPROVE_PROVIDER_NETWORK=yes ./scripts/supervise.sh` (or `python3 scripts/supervisor.py run --hours 8 --max-tasks 10 --approve-provider-network`) runs the same Claude-only Forge pipeline as `forge.py run`, but classifies each failure and recovers from the ordinary ones itself. `forge.py run` is unchanged for manual, unsupervised runs.

## Failure handling

| Kind | Detected from | Action |
| --- | --- | --- |
| Product | Failing checks other than unit tests, unresolved in-scope audit findings | The Builder repairs within the task's permission profile, in the task workspace and its persisted session, using the failure log; the repaired change is security-reviewed, checked and audited again. Budget: `limits.product_repairs` (default 3). A repair that leaves its profile, touches the control plane, or skips, deletes or weakens tests blocks the task. |
| Product (unit tests) | Failing non-Forge unit tests | Handled first inside Forge: the read-only `cendavo-debugger` classifies the failure; `PRODUCT` (and `TEST`, when the profile may change tests) allows a bounded Builder fix (`limits.test_fixes`, recorded in the checkpoint). A `TEST`/`UNKNOWN` diagnosis or an exhausted budget stops for the owner; an `INFRASTRUCTURE` diagnosis goes to maintenance. |
| Infrastructure | Sandbox denial of Forge state or tools, only Forge runner tests failing, Forge's own runner/sandbox heuristic, agent CLI/verdict/report handling | Isolated maintenance worktree + `cendavo-maintainer` agent (below). Budget: `limits.maintenance_attempts` (default 2). |
| Provider limit | Claude usage limit | Stop. Resume after the limit resets; no API key, paid fallback or budget flag is ever used. |
| Security | Security reviewer `BLOCK`, protected-file change, test weakening | Stop; task `blocked`. Always needs the owner. |
| Environment / needs human | Not macOS, missing CLI/auth, runtime limit, STOP, unvalidated dirty tree, unrecognised error | Stop with a report. |

Every decision is recorded in the task's event history and in `.cendavo-run/supervisor/reports/`.

## Maintenance flow

1. `git worktree add` creates `../.Cendavo-forge-maintenance/<id>` (beside the project, so the live test sandbox can never write it) on branch `forge-maint/<id>`. The live checkout and its uncommitted work are not touched.
2. `cendavo-maintainer` (file tools plus a sandboxed shell in its worktree with no network; no MCP, `.env`, `.git` or Forge state; the whole live checkout is denied by absolute path, and any change to it or to checkpoints is a security stop) diagnoses from the fenced log evidence and proposes a minimal fix with a regression test.
3. Deterministic policy check of the patch:
   - **Rejected:** product files, `.env`/`.git`/`.cendavo-run`, removing tests or assertions, adding skips, or no new `def test_`.
   - **Needs your approval:** changed lines touching sandbox profiles, permissions, tool lists, protected-file policy, credentials/auth, environment or subprocess/network handling, product-repair containment, verdict parsing or checkpoint fingerprints; any change to `scripts/supervisor.py`, `scripts/forge_sandbox.py`, launch scripts, `.claude/`, `.github/`, `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `requirements.txt`; test code gaining process, network or home-directory access.
   - **Safe:** everything else under `scripts/`, `tests/`, `docs/`.
4. Sandboxed tests run in the worktree, then an independent read-only `cendavo-security-reviewer` session reviews the patch. Any non-`PASS` rejects it.
5. A safe patch is committed in the worktree and cherry-picked onto the live branch only if its files are clean there and disjoint from the task's workspace change. The sandboxed checks run again on the live checkout; on failure the commit is reverted (a new commit, never a reset).
6. The task workspace fast-forwards to the new live HEAD, and its checkpoint moves only if the task's change is byte-identical relative to it, so validated stages stay valid. The supervisor re-executes itself to load the new Forge code and resumes the task.

## Approvals

```sh
python3 scripts/supervisor.py approvals          # list pending patches
less .cendavo-run/supervisor/patches/<id>.diff   # review
python3 scripts/supervisor.py approve <id>       # integrate + re-test; then resume with supervise.sh
python3 scripts/supervisor.py reject <id>
python3 scripts/supervisor.py diagnose [--task N]  # classify the latest failure from logs; no agents
```

Approval re-checks that the commit matches the validated patch hash before integrating.

## Limits

Runtime is capped at 8 hours across re-executions; each agent and test command keeps Forge's own timeouts. A stopped task is never re-queued automatically; use `python3 scripts/forge.py resume` after review. Integrations create local commits only; nothing is pushed or deployed.

Sandboxed commands run with the open-file limit capped at 4096: the sandbox hides `/dev/fd`, so an inherited limit near 1M (common when launched from an IDE or agent session) made every process spawn ~70x slower and timed out the test stage.

## Budgets and progress

Repair budgets come from `forge.config.json` `limits` and can be raised for one run with `--max-repairs N` / `--max-maintenance N` (capped at 10). `python3 scripts/supervisor.py watch` streams progress as it happens: stages, verdicts, every agent tool call (for example `builder: Bash npm test`) and a heartbeat for commands running longer than a minute.
