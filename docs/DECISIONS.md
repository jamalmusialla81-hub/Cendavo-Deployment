# Decision record

## 001 — Static first increment

**Decision:** Ship a zero-dependency static website with a browser-local request demo. This works on Cloudflare Pages and allows the core workflow to be assessed before choosing a customer database and authentication provider.

**Strategist challenge:** A polished site alone does not prove demand, and A$49–99/month is an untested price. The demo must show an actual admin task. Do not imply subscriptions are open.

**Builder feasibility:** A local-only queue can demonstrate intake, status tracking and follow-up draft preparation without storing personal data on a server. It cannot support a real business team.

**Codex audit criterion:** Check that the product and copy clearly label the demo and that no information is transmitted or messages sent. Verify safe rendering of user text.

**Resolution:** Use synthetic samples and on-device storage. Defer hosted accounts, database and payments until a real pilot need and security design exist. The first milestone is workflow feedback, not revenue.

## 002 — Deployment control

**Decision:** The backup GitHub Actions deployment is manual and restricted to `main`. The user's Git-linked Cloudflare Pages project automatically deploys `main`; after the user explicitly requested deployment, commit `e1f7ea1` was published and the build settings were corrected. Development runs remain on a feature branch and Forge never pushes checkpoints automatically.

## 003 — Agent billing

**Decision:** Forge uses the authenticated Claude Code and Codex CLIs. It does not use API keys, does not start without Claude Code, and strips `ANTHROPIC_API_KEY` from agent subprocesses. Claude Max CLI usage and limits must be checked in the user's account; API billing is not assumed.

## 004 — First release result

**Outcome:** The production project is `cendavo-deployment`. Cloudflare builds with `python3 scripts/build_site.py` and serves `dist`. The live home and demo routes returned HTTP 200. GitHub Checks and the manual Pages workflow passed on commit `2d83b7b`.

**Remaining constraint:** Claude Code is installed locally but not authenticated. Forge's first start attempt recorded a pause before any agent task began. The user must review and authorize the Claude Code account connection before the three queued tasks can run.
