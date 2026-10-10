# Cendavo Forge local runner

The runner is Claude-only (no Codex). For each queued task it runs:

1. **Strategist** (read-only) — value, risk and requirements; may `DECISION: REJECT`.
2. **Builder** (Read/Glob/Grep/Edit/Write) — implements; for frontend tasks it may also use the `insane-web-design` plugin skills.
3. **Security Reviewer** (independent, read-only) — reviews the diff before any code runs. `VERDICT: PASS`, `FIX` (bounded Builder repair) or `BLOCK` (run stops).
4. **Local tests, no AI** — build, unit tests and JS syntax checks in the macOS `sandbox-exec` profile.
5. **Functional Auditor** (independent, read-only) — checks the change against the Strategist's requirements. `FIX` triggers a Builder repair, then security review and tests run again on the new change.
6. **Local Git checkpoint** — only after security, tests and audit all pass on the exact final change.

Reviewer sessions are separate `claude -p` calls with `--no-session-persistence`, read-only tools, Bash/MCP denied, and no Builder report or reasoning in their input (the diff is passed as fenced data). Agents are loaded inline via `--agents` from `.claude/agents/`, so a missing or malformed definition stops the run at start-up with a clear message. Each review phase allows at most two cycles.

**Reuse after interruption.** `.cendavo-run/checkpoints/<task>.json` records the Strategist report and the fingerprint of the change each stage validated. After a stop, the Strategist, Builder, security, test and audit stages are skipped only when the working tree still matches the recorded fingerprint; any edit invalidates later stages. An unrecognised dirty tree is refused.

**Stops.** The run halts on a provider usage limit (the attempt is not counted), a security `BLOCK` or exhausted security cycles (task becomes `blocked`), or any unexpected error. Nothing is retried automatically; inspect, then `resume`. Reports, command logs and a persistent SQLite queue live in `.cendavo-run/` and are ignored by Git. Checkpoint commits are local; the runner never pushes, deploys, sends email or purchases anything. The host computer must remain awake and online. This runner currently requires macOS `sandbox-exec` for executing agent-edited tests; other hosts pause rather than running them unsandboxed.

## Requirements and setup

Claude Code has been installed in `.cendavo-tools/` for this checkout. Alternatively, install it from [Anthropic's official instructions](https://code.claude.com/docs/en/setup). Sign in to Claude Code with your Claude subscription (`.cendavo-tools/node_modules/.bin/claude auth login`) Check `claude auth status`. The runner accepts Claude's `claude.ai` or `oauth_token` authentication; it does not use API keys. Optionally install the `insane-web-design` plugin; Forge warns if it is missing and frontend tasks then run without it. An `ANTHROPIC_API_KEY` in your shell is removed from agent subprocesses to avoid accidentally choosing API billing. Provider usage limits remain in force. There is no promise of eight hours of uninterrupted model access.

From a clean local feature branch with an initial commit:

```sh
python3 scripts/forge.py init
python3 scripts/forge.py status
./scripts/overnight.sh
```

Set `CENDAVO_HOURS=2` or `CENDAVO_MAX_TASKS=3` for a shorter run. The hard maximum is eight hours. Add a specific task with `python3 scripts/forge.py add 'Task description' --priority 4`. Lower priority numbers run first.

To stop an active command, run `python3 scripts/forge.py stop` from another terminal or press `Ctrl+C`. A child process is terminated when it exceeds the task timeout or total runtime. Inspect `.cendavo-run/summary.json`, `.cendavo-run/reports/`, logs and `git status` the next morning. Use `python3 scripts/forge.py resume` after inspecting interrupted work. If `.cendavo-run/active-child.json` remains after a hard crash, check that process manually before removing the marker. If an agent is unavailable, the runner pauses and records why. A failed task is retried at most twice only when the working tree is clean. Each review phase is limited to two audits; unresolved findings need a human decision.

The summary includes a Claude CLI cost estimate when the CLI reports one. This is a usage signal, not a charge or a guarantee of remaining subscription capacity. Provider rate or quota errors pause the run instead of retrying through the limit.

Do not run Forge concurrently in the same checkout. Use a dedicated branch. Local logs may contain task content and should remain private. Review every checkpoint before pushing it to GitHub. Production deployment is a separate manual action requiring approval.
