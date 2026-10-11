# Cendavo

Cendavo is an early product concept for local service businesses in Sydney. The public site and interactive demo are static and use synthetic browser-local data. There is no hosted customer account, database, payment system, or automated messaging yet.

Use `.claude/agents/cendavo-strategist.md` for adversarial business analysis and `.claude/agents/cendavo-builder.md` for implementation. The local Forge runner calls them in separate Claude Code invocations. Independent read-only Claude reviewer sessions (`cendavo-security-reviewer` before tests, `cendavo-auditor` after tests) check the Builder's work; Codex is not used. The Forge Supervisor (`scripts/supervisor.py`) may run `cendavo-maintainer` in an isolated worktree for infrastructure failures; see `docs/SUPERVISOR.md`. Each Forge task runs in its own worktree with a permission profile and a sandboxed shell; see `docs/FORGE.md` (Permissions). Never claim agent work occurred unless an actual CLI run and report exist.

Priorities: security, reliability, customer value, maintainability, performance, visual quality. Build one reusable platform. No secrets or customer data in Git. No paid services, customer messages or production deployments. Only use sample data in the demo. Validate behavior with `python3 -m unittest discover -s tests` and `python3 scripts/build_site.py`.
