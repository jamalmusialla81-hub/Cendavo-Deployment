# Forge recovery audit — 2026-10-11

Verified by Claude Code (supervisor) before the "Project Ascension" trial. Everything below was read from the live checkout, not from earlier reports.

## Repository

| Item | Verified state |
| --- | --- |
| Checkout | `~/Documents/Cendavo` (Cendavo site + Forge, remote `jamalmusialla81-hub/Cendavo-Deployment`) |
| Branch / HEAD | `forge/linux-wsl-backend` @ `c811aa1` (Forge v2 + Linux/WSL2 backend) |
| Working tree | clean (0 changed files) |
| Worktrees | `~/Documents/Cendavo-infra` on `forge/infra-hardening` @ `d6c053f` (left untouched) |
| `main` | local `66a6f62`, remote `31758db` (local is 1 behind). **A push to `main` deploys production (Cloudflare Pages).** |
| Backup branches | `backup/20261011-pre-supervisor/*`, `backup/20261011-pre-v2/supervisor-integration`, `backup/forge-before-claude-merge` |
| Running Forge / Supervisor | none (`runner_active: false`, no `active_child`, no stop request) |
| Other agents | one other Claude Code session had this directory as its working directory; owner confirmed it is idle |

## Queue (`forge.py inspect`)

| ID | State | Attempts | Title |
| --- | --- | --- | --- |
| 1 | failed | 3 | Improve the demo request workflow for a real local service task. Preserve browser-local synthetic data and clear status controls. |
| 2 | completed | 1 | Improve keyboard and screen-reader access in the site and demo. |
| 3 | completed | 1 | Add a safe way to export synthetic demo requests from the browser without sending them to a server. |

- Task 2 delivered commit `f378fdb`; Task 3 delivered `b9dc7b4`. Both are ancestors of the current HEAD (not merged to `main`, not pushed to `origin/main`).
- Task 1 never reached product implementation. See [CENDAVO_TASK_1_RECOVERY.md](CENDAVO_TASK_1_RECOVERY.md).

## Checkpoint taken before this trial

`~/Documents/Cendavo-backups/20261011-1859-pre-ascension/` — `all-refs.bundle` (verified) and `cendavo-run.tgz` (queue, logs, reports, supervisor state), following the existing backup layout. No earlier backup was modified.

## Preflight

| Check | Result |
| --- | --- |
| `forge.py doctor` | ok — platform, filesystem, locking, process termination, resource limits (4096 fds, per-command timeouts), checks sandbox (project writable; outside, secrets, Forge state, tests, network, home denied), agent sandbox (Seatbelt) |
| Claude Code auth | `loggedIn: true`, `authMethod: claude.ai` (subscription; no API key) |
| Tools | git, python3 3.14.7, node 26.8.2, npm, sandbox-exec |
| Owner checks (forge.config.json) | build ok (5 pages); unit tests 202 ran, OK (4 skipped); `node --check` site.js and demo.js ok |
| Limits (forge.config.json) | review_cycles 3, test_fixes 3, **product_repairs 3, maintenance_attempts 2**; builder 80 turns |
| Billing guard | Forge strips API-billing env vars and refuses `--max-budget-usd`, `--fallback-model`, `--betas` |
| Disk | ~10 GB free |
| Design plugin | `insane-web-design` enabled, 7 local skills (animation-forge, awwwards, awwwards-3d, particle-system, scroll-world, shader-glsl, threejs-animation); Forge passes it to Strategist/Builder on frontend tasks |

## Supported run commands (from `--help`, nothing invented)

- `forge.py add TITLE [--priority N] [--profile app|site|docs]` — title ≤ 300 characters.
- `supervisor.py run [--hours H] [--max-tasks N] [--approve-provider-network] [--max-repairs N] [--max-maintenance N]`
- `forge.py stop` (stop switch), `forge.py inspect` (read-only), `supervisor.py watch`.

## Owner decisions (2026-10-11)

1. Reposition the site as a website design / redesign / maintenance agency; keep the request-queue demo as a clearly labelled demonstration project.
2. Store enquiries with a Cloudflare Pages Function + D1.
3. Deliver trial tasks to the current branch `forge/linux-wsl-backend`; never `main`.

## Findings

- The live site still sells "a reusable local service admin platform" (A$49–99/month hypothesis). It does not yet describe the agency business.
- Lead Hunter does not exist anywhere in the repository, docs or queue.
- The TikTok "vibe coding / website design" transcript was not found in any accessible file (the only transcript found is an unrelated compositing tutorial).
