# Cendavo progress — 10 October 2026

## Product

| Capability | Current state | Next decision |
| --- | --- | --- |
| Business website | Five public pages live on Cloudflare Pages | Add a real contact channel when supplied |
| Enquiry and booking request flow | Browser-local demo using synthetic requests | Validate flow with local service businesses before a hosted backend |
| Request tracking | New, Follow-up and Done states in demo | Add filtering and clearer handling of completed work |
| Follow-up preparation | Local text draft and copy action; nothing sends | Design review and consent before any real messaging |
| Shared business accounts | Not built | Define tenant isolation, sign-in and access policy first |
| Payments and subscriptions | Not built | Validate pricing and operating cost first |

The current increment is a functional demo, not a production SaaS for real customer information. Do not enter customer data into it.

## Business assumptions

- **Proposed price:** A$49–99 per month, unvalidated. No checkout exists.
- **Customer acquisition:** Initial target groups are laundromats, tailors, cleaners, repair shops and other local services. Demand, conversion, sales cycle and acquisition cost have not been measured.
- **Revenue:** No verified revenue data has been supplied. The website makes no revenue or customer claims.
- **Operating cost:** The static site has no application database or messaging provider. Cloudflare account billing and future backend costs have not been verified; calculate them before launching paid subscriptions. Claude and Codex usage depends on their subscription terms and limits; no separate API billing is configured by Forge.

## Engineering and release

- **Tests:** The site build, eight local unit tests, JavaScript syntax checks and macOS sandboxed test run pass. GitHub Checks passed for the deployed revision.
- **Security:** The demo stores sample data in the browser, inserts text through DOM text nodes, sends no requests to Cendavo, and ships restrictive response headers. The future hosted product needs authentication, tenant isolation, data retention and abuse controls before real customer use.
- **Deployment:** `main` is connected to Cloudflare Pages project `cendavo-deployment`. Build command and output directory are configured. The home page and demo return HTTP 200. The manual GitHub Actions deploy workflow also passed for commit `2d83b7b`.
- **Agent workflow:** Two Claude Code role files, Codex review, persistent queue, bounded runtime, stop switch, logs and local Git checkpoints are implemented. Codex CLI is authenticated. Claude Code is installed but authentication has not completed; the runner paused without starting a task. No Claude Builder or Strategist output has been produced yet.

## Next queued tasks

1. Improve the demo request workflow for a real local service task.
2. Improve keyboard and screen reader access.
3. Add browser-local export of synthetic demo requests.

Forge will process these after Claude Code is authenticated with the user's subscription. The host must remain awake and online during an overnight run.
