# Cendavo

An early business website and product demo for a reusable local service admin platform. The first increment lets visitors try a browser-local request queue, change statuses, prepare follow-up drafts, and download the sample requests as a CSV file built in the browser (nothing is uploaded). The demo uses synthetic data and does not send messages or take payments. The contact page has a working enquiry form: a Cloudflare Pages Function (`functions/api/enquiry.js`) validates submissions and stores them in a Cloudflare D1 database. See [docs/ENQUIRIES.md](docs/ENQUIRIES.md) for the one-time setup.

## Run locally

```sh
python3 scripts/build_site.py
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000`. To validate: `python3 -m unittest discover -s tests -v`, then `node --check assets/site.js`, `node --check assets/demo.js` and `node --check assets/enquiry.js`. The static preview has no Pages Functions, so locally the enquiry form says it could not send and keeps what was typed.

## Development loop

[Forge instructions](docs/FORGE.md) explain the local Claude-only Strategist → Builder → Security Reviewer → tests → Functional Auditor runner, persistent queue, logs, stop switch and overnight launcher. [Decision record](docs/DECISIONS.md) explains the first product and deployment choices.
[Progress and assumptions](docs/PROGRESS.md) tracks MVP completeness, unvalidated pricing, security work and the queued improvements.

## Deployment

The site builds into `dist/` with Python's standard library. The Git-linked Cloudflare Pages project `cendavo-deployment` uses build command `python3 scripts/build_site.py` and output directory `dist`; pushes to `main` deploy automatically at [cendavo-deployment.pages.dev](https://cendavo-deployment.pages.dev/). The backup GitHub Actions deployment workflow is manual and restricted to `main`. It needs a repository secret `CLOUDFLARE_API_TOKEN` (or the existing `CLOUDFLARE_API`) and repository variable `CLOUDFLARE_ACCOUNT_ID`. GitHub's check workflow runs on pushes and pull requests. Review local Forge checkpoints before pushing because a `main` push can publish them.

## Current scope

The demo is suitable for workflow evaluation only. A secure multi-tenant backend, sign-in, audit logging, data retention policy and real business onboarding are still required before using real customer data. A$49–99/month is a pricing hypothesis, not a subscription offer.
