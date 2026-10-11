# Cendavo Forge local runner (Autonomous Developer v2)

The runner is Claude-only (no Codex). Every task runs in **its own Git worktree** beside the project (`../.Cendavo-forge-workspaces/task-NNNN` on branch `forge-task/NNNN`); agents never edit the live checkout. For each queued task Forge runs:

1. **Strategist** (read-only) — value, risk and requirements achievable within the task's permission profile; manual checks listed separately. May `DECISION: REJECT` (the workspace is then discarded).
2. **Builder** — implements in the workspace with file tools and, for profiles with a shell, a **sandboxed development shell** (builds, tests, linters, package installs from allowed registries, read-only Git). Frontend tasks may use the `insane-web-design` skills.
3. **Security Reviewer** (independent, read-only) — reviews the full diff before Forge executes any of it; dependency, build and hosting files are flagged for extra scrutiny. `PASS`, `FIX` (bounded Builder repair) or `BLOCK` (run stops).
4. **Local checks, no AI** — the `checks` commands in `forge.config.json`, inside the macOS `sandbox-exec` profile (see Sandbox boundary).
5. **Functional Auditor** (independent, read-only) — checks the change against the requirements and reports structured findings (see Permissions). In-scope `FIX` findings trigger a Builder repair; security review and checks then run again.
6. **Checkpoint and delivery** — Forge commits in the workspace only after security, checks and audit pass on the exact final change, then **fast-forwards** the live branch to that commit (never merge, rebase or force). If the live branch moved or has uncommitted changes, the validated commit stays on `forge-task/NNNN` and the task resumes straight into delivery later.

Builder calls for one task share a persisted Claude session (`--session-id`, then `--resume`), so fixes keep the context of earlier work. Reviewers are separate `claude -p` calls with `--no-session-persistence`, read-only tools, no shell, and no Builder report in their input (the diff is fenced data). Agents are loaded inline via `--agents` from `.claude/agents/`. Progress — stages, every agent tool call, heartbeats for long commands — streams to the console and `.cendavo-run/progress.jsonl`; `python3 scripts/supervisor.py watch` follows it.

**Reuse after interruption.** `.cendavo-run/checkpoints/<task>.json` records the Strategist report, the fingerprint of the change each stage validated, the Builder session and owner follow-ups. Stages are skipped only when the workspace still matches the recorded fingerprint; any edit invalidates later stages, and unvalidated workspace changes are refused. `python3 scripts/forge.py discard N` rolls a task back (workspace, branch, checkpoint) without touching the live checkout.

**Stops.** The run halts on a provider usage limit (the attempt is not counted), a security `BLOCK`, a permission violation, exhausted review cycles, or any unexpected error. Reports, logs, follow-ups and the SQLite queue live in `.cendavo-run/` (ignored by Git). Commits are local; Forge never pushes, deploys, sends email or purchases anything. The host must stay awake and online. Forge's checks stage needs a verified OS sandbox: macOS `sandbox-exec` or Linux/WSL2 bubblewrap (see [WINDOWS.md](WINDOWS.md)); other hosts refuse rather than run agent-edited code unsandboxed. `python3 scripts/forge.py doctor` checks a host, and `python3 scripts/forge.py inspect` prints a read-only JSON snapshot for supervisors such as JARVIS.

## Permissions

Permissions are enforced in `scripts/forge.py`, not by prompts. Each task has a **profile** (`forge.py add "..." --profile app|site|docs`; default from `forge.config.json`):

| Profile | Builder may change | Shell | Network from the shell |
| --- | --- | --- | --- |
| `app` (default) | any project file except the control plane: source, backend, frontend, tests, docs, ordinary config, dependency manifests | yes | configured package registries only |
| `site` | `assets/`, `pages/`, `scripts/build_site.py`, site tests | yes | none |
| `docs` | `docs/`, `README.md` | no | — |

**Control plane — never writable in any profile:** `scripts/forge.py`, `scripts/forge_sandbox.py`, `scripts/supervisor.py`, launch scripts, Forge's own tests, `forge.config.json`, `.claude/`, `.github/`, `CLAUDE.md`, `AGENTS.md`, `.gitignore`, `.mcp.json`, `.git`, and secret-like names (`.env*`, `secret*`, `credential*`, keys, `auth.json`, `.npmrc` …).

Layers, from the agent outward:

1. **Claude tool permissions** (`--restricted`, `dontAsk`): file tools confined to the workspace; Edit/Write denied on the control plane and limited to the profile; secret reads denied; consequential commands (`git push/commit/reset/…`, `npm publish`, `gh`, `wrangler`, `vercel`, `ssh`, `open`, `osascript`, `security` …) denied; MCP denied unless configured. Anything not allowed is refused automatically, so there are no interactive approval prompts.
2. **Claude Code's OS sandbox for Bash** (`failIfUnavailable`, `allowUnsandboxedCommands: false`): the home directory is unreadable except the workspace and the repository's Git objects; `.env` and other secret files in the workspace are unreadable; writes stay inside the workspace, with the control plane, secrets, Git metadata and (for narrow profiles) everything outside the profile write-denied; network only to `package_registries` for `app`, none otherwise. Git config and tool caches point into the workspace (`.forge-cache/`, ignored).
3. **Forge's guard after every writable call:** the live checkout, Forge checkpoints and the workspace's control files must be byte-identical; every changed file must be inside the profile; no symlinks; no test skipped, deleted or weakened. Any violation is a `SecurityFailure` and stops the task.
4. **Independent review and sandboxed checks** before anything is committed, then fast-forward delivery.

**MCP.** Only servers in `forge.config.json` `mcp_servers` are loaded (`--mcp-config` with `--strict-mcp-config`): local stdio commands with an explicit `tools` list (no wildcards), the agents and profiles allowed to use them, and no `env`/credentials or remote URLs. MCP servers run outside the Bash sandbox with your user's privileges: add only servers you trust, and never list tools that spend money, publish, deploy or contact people.

**Limits.** `forge.config.json` sets per-agent turn limits (defaults: Builder 80, maintainer 60, reviewers 30; capped at 200), review cycles, test-fix and repair budgets (capped at 10), the largest reviewable diff and the check commands. It is part of the control plane.

**Auditor scope.** Reviewers report `- [code] path: defect`, `- [manual] check` or `- [out-of-scope] path: note`. Only `[code]` findings inside the Builder's profile go back for fixing. A `FIX` without one is accepted, and manual and out-of-scope items are written to `.cendavo-run/followups/task-NNNN.md` for the owner. A security `FIX` the Builder cannot perform stops for the owner.

**What still needs you:** pushing, deploying, spending money, contacting customers, changing the control plane or adding MCP servers. Agents can run the code they write inside their sandbox *before* the security review — that is what a development shell is for — so the sandbox, not the review, is what contains it.

## Supervised runs

`CENDAVO_APPROVE_PROVIDER_NETWORK=yes ./scripts/supervise.sh` wraps this pipeline with automatic recovery: product failures are repaired by the Builder, infrastructure failures are fixed in an isolated maintenance worktree and integrated only after policy, test and independent security checks (security-boundary changes wait for approval). See [SUPERVISOR.md](SUPERVISOR.md).

## Requirements and setup

Claude Code has been installed in `.cendavo-tools/` for this checkout. Alternatively, install it from [Anthropic's official instructions](https://code.claude.com/docs/en/setup). Sign in to Claude Code with your Claude subscription (`.cendavo-tools/node_modules/.bin/claude auth login`) Check `claude auth status`. The runner accepts Claude's `claude.ai` or `oauth_token` authentication; it does not use API keys. Optionally install the `insane-web-design` plugin; Forge warns if it is missing and frontend tasks then run without it. An `ANTHROPIC_API_KEY` in your shell is removed from agent subprocesses to avoid accidentally choosing API billing. Provider usage limits remain in force. There is no promise of eight hours of uninterrupted model access.

From a clean local feature branch with an initial commit:

```sh
python3 scripts/forge.py init
python3 scripts/forge.py status
CENDAVO_APPROVE_PROVIDER_NETWORK=yes ./scripts/overnight.sh
```

Set `CENDAVO_HOURS=2` or `CENDAVO_MAX_TASKS=3` for a shorter run. The hard maximum is eight hours. A direct invocation of `forge.py run` requires `--approve-provider-network` for that run. This acknowledges the Claude model connections; it does not approve arbitrary network access from build or test code. Add a specific task with `python3 scripts/forge.py add 'Task description' --priority 4`. Lower priority numbers run first.

## Sandbox boundary

This profile is used for Forge's own checks stage, not the agents' shell. Before Forge executes Claude-edited build or test code, an independent read-only Claude Security Reviewer inspects the diff. The macOS Seatbelt profile in `scripts/forge_sandbox.py` then permits reading and writing **throughout the current Cendavo checkout**, including creating new directories and files. It resolves the checkout path, so a checkout at `~/Documents/Cendavo` gets that entire project tree. It also grants read/write access to one private temporary directory created for the test run and removed afterward. Homebrew Python and Node, the installed Git binary, and the installed Claude launcher can start; runtime libraries are readable without allowing writes to those locations. Homebrew Python's resolved Cellar path is included. The runner sets `TMPDIR`, `HOME`, and cache paths to the private temporary directory, and uses the direct Apple Git binary to avoid `xcrun` writing outside it.

The profile denies reads and writes to `.git`, `.cendavo-run`, `.cendavo-tools`, `.env` variants, paths named `secret` or `credential` (including common variants), common key files, and auth/token JSON files at any project depth. It denies network operations, unrelated home directories, SSH keys, browser profiles, and non-runtime system files. In-project symlinks cannot grant access outside the allowed paths. The narrow external runtime exceptions include macOS libraries, Command Line Tools, Homebrew, the installed model-client binaries, `/dev/null`, and a few required system metadata files. Filename rules cannot detect a credential hidden in an ordinary-looking source file; keep all secrets outside the project and review new files before running them.

The **model-client processes themselves** run outside this profile: they must reach their provider and use private local authentication. Their containment is described under Permissions. Keep customer data and credentials out of ordinary project files. Pushes, deployments, purchases and contacting customers each require explicit approval; Forge grants none of them.

Run `python3 -m unittest tests.test_forge_sandbox -v` **outside** an existing sandbox to exercise the permission-denial tests. macOS does not permit a nested `sandbox-exec`, so those behavioral tests are skipped when the full suite runs inside the sandbox. The Forge test phase still runs the site build, the remaining unit tests, and JavaScript syntax checks within the profile. The autonomous queue is not resumed by these verification commands.

## Frontend design plugin

Before each queued task, Forge checks `claude plugin list --json` for an enabled local `insane-web-design` plugin and validates that its directory contains a matching manifest and local skills. On frontend work, both Strategist and Builder are instructed to inspect the relevant plugin skills with Claude's `Skill` tool before recommending or implementing a design. The tool is enabled only when discovery succeeds. Their reports must name the skills considered and explain why any design, animation or 3D guidance is useful. Performance, accessibility, responsive behavior, reduced-motion support and conversion take priority; no animation, 3D layer, paid service or CDN should be added merely because the plugin can produce it.

This host's Claude Code CLI now lists `insane-web-design@synced` as enabled. Forge discovers its seven local skills: `animation-forge`, `awwwards`, `awwwards-3d`, `particle-system`, `scroll-world`, `shader-glsl` and `threejs-animation`. Claude's plugin validation passes; the package has no hooks or MCP servers. Availability is checked again for each queued task, so a later disablement or removal will be reported rather than assumed away. If the plugin exists locally but is not registered with this CLI, set `CENDAVO_INSANE_WEB_DESIGN_PLUGIN_DIR` to its directory for a future run. Forge will load only a local plugin whose manifest names `insane-web-design`, whose skills are present, and whose package has no hooks or MCP server configuration; it never downloads or installs a plugin. A package with executable integrations needs separate review. The CLI's existing `frontend-design` plugin is a different plugin and is not treated as `insane-web-design`.

The discovery and command-construction regression tests use a temporary skills-only plugin fixture. They prove that a frontend task would expose its skills to both agents without restarting the queue or contacting a model provider. An end-to-end Skill invocation remains to be checked when the queue is separately resumed. Some skills suggest costly rendering services or heavy 3D stacks; the Strategist and Builder must reject those unless a specific task justifies them and the user separately approves any expense or new network access.

To stop an active command, run `python3 scripts/forge.py stop` from another terminal or press `Ctrl+C`. A child process is terminated when it exceeds the task timeout or total runtime. Inspect `.cendavo-run/summary.json`, `.cendavo-run/reports/`, logs and `git status` the next morning. Use `python3 scripts/forge.py resume` after inspecting interrupted work. If `.cendavo-run/active-child.json` remains after a hard crash, check that process manually before removing the marker. If an agent is unavailable, the runner pauses and records why. A failed task is retried at most twice. Review cycles and repair budgets come from `forge.config.json`; unresolved findings need a human decision.

The summary includes a Claude CLI cost estimate when the CLI reports one. This is a usage signal, not a charge or a guarantee of remaining subscription capacity. Provider rate or quota errors pause the run instead of retrying through the limit.

Do not run Forge concurrently in the same checkout. Use a dedicated branch. Local logs may contain task content and should remain private. Review every checkpoint before pushing it to GitHub. Production deployment is a separate manual action requiring approval.
