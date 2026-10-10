# Decision record

## 001 — Static first increment

**Decision:** Ship a zero-dependency static website with a browser-local request demo. This works on Cloudflare Pages and allows the core workflow to be assessed before choosing a customer database and authentication provider.

**Strategist challenge:** A polished site alone does not prove demand, and A$49–99/month is an untested price. The demo must show an actual admin task. Do not imply subscriptions are open.

**Builder feasibility:** A local-only queue can demonstrate intake, status tracking and follow-up draft preparation without storing personal data on a server. It cannot support a real business team.

**Codex audit criterion:** Check that the product and copy clearly label the demo and that no information is transmitted or messages sent. Verify safe rendering of user text.

**Resolution:** Use synthetic samples and on-device storage. Defer hosted accounts, database and payments until a real pilot need and security design exist. The first milestone is workflow feedback, not revenue.

## 002 — Deployment control

**Decision:** GitHub Actions deployment is manual and restricted to `main`. Development commits go to a feature branch for review. This respects the user's production deployment approval requirement.

## 003 — Agent billing

**Decision:** Forge uses the authenticated Claude Code and Codex CLIs. It does not use API keys, does not start without Claude Code, and strips `ANTHROPIC_API_KEY` from agent subprocesses. Claude Max CLI usage and limits must be checked in the user's account; API billing is not assumed.
