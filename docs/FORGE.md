# Cendavo Forge local runner

The runner executes this bounded sequence: queued task → Claude Strategist report → Claude Builder edit → read-only Codex security preflight → sandboxed tests → Codex functional audit → limited Claude fixes and Codex re-audits → local Git checkpoint. Reports, command logs and a persistent SQLite queue live in `.cendavo-run/` and are ignored by Git. Checkpoint commits are local; the runner never pushes, deploys, sends email or purchases anything. The host computer must remain awake and online. A laptop sleeping will pause work. This runner currently requires macOS `sandbox-exec` for executing agent-edited tests; other hosts pause rather than running them unsandboxed.

## Requirements and setup

Claude Code has been installed in `.cendavo-tools/` for this checkout. Alternatively, install it from [Anthropic's official instructions](https://code.claude.com/docs/en/setup). Sign in to Claude Code with your Claude subscription (`.cendavo-tools/node_modules/.bin/claude auth login`) and Codex with ChatGPT (`codex login`). Check Claude's `auth status` and `codex login status`. The runner accepts Claude's `claude.ai` or `oauth_token` authentication and Codex's ChatGPT login; it does not use API keys. An `ANTHROPIC_API_KEY` in your shell is removed from agent subprocesses to avoid accidentally choosing API billing. Provider usage limits remain in force. There is no promise of eight hours of uninterrupted model access.

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
