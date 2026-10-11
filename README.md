# Cendavo

Cendavo is a small Sydney studio that designs, redesigns and looks after websites for local service businesses. This repository holds the studio's own website and its enquiry backend. The site shows fictional concept projects, each labelled "Concept project · fictional business". It names no real clients, testimonials or results and publishes no prices: pricing is a fixed quote after a free consultation.

**Status:** the current "Night Shift" design is on branch `design/night-shift`. It is **not deployed** and needs the owner's visual approval before it is merged to `main`. See [progress and open decisions](docs/PROGRESS.md).

## Pages

Home, Work, Services, Pricing, Demonstration project (`/demo/`), About and Contact, plus a 404 page. The 404 page carries `noindex` and is left out of the sitemap. The desktop header leaves out the Demonstration project link, but the mobile menu and the footer include it. The Demonstration project is a request queue that runs in the browser on synthetic sample data. It can download that data as a CSV file, sends nothing and uploads nothing.

Pages are written in `pages/` and built by `scripts/build_site.py` into `dist/`, with shared navigation, canonical and Open Graph metadata, `sitemap.xml`, `robots.txt` and `_headers`.

## Enquiries

The contact form (`assets/enquiry.js`) posts to the Cloudflare Pages Function `functions/api/enquiry.js`. The function validates each enquiry on the server and stores it in Cloudflare D1 through the binding `ENQUIRIES_DB`; the schema is in `migrations/0001_enquiries.sql`. No one is notified when an enquiry arrives. Owner setup, read queries and limits are in [docs/ENQUIRIES.md](docs/ENQUIRIES.md).

## Assets

- Self-hosted fonts: Archivo and Atkinson Hyperlegible (`assets/fonts/`, OFL licences included).
- Vendored GSAP and ScrollTrigger (`assets/vendor/gsap/`) for motion. Motion respects `prefers-reduced-motion`.
- Photos are served as AVIF with a JPEG fallback, and the build stops if an AVIF file is missing. Credits are in `assets/images/CREDITS.md`.
- Open Graph share card: `assets/social/cendavo-og.jpg`.
- The Content Security Policy in `dist/_headers` allows only the site's own origin. The site makes no third-party requests and runs no tracking scripts.

## Run locally

```sh
python3 scripts/build_site.py
python3 -m http.server 8000 --directory dist
```

Then open `http://localhost:8000`. The static preview has no Pages Functions, so locally the enquiry form reports that it could not send and keeps what was typed.

## Test

```sh
python3 -m unittest discover -s tests -v
node --check assets/site.js
node --check assets/demo.js
node --check assets/enquiry.js
node --check assets/home.js
node --check assets/motion.js
node --check assets/motion-boot.js
```

## Development loop

[Forge instructions](docs/FORGE.md) explain the local Claude-only Strategist → Builder → Security Reviewer → tests → Functional Auditor runner, persistent queue, logs, stop switch and overnight launcher. The [decision record](docs/DECISIONS.md) explains the first product and deployment choices.
[Progress and assumptions](docs/PROGRESS.md) tracks what is built, open owner decisions and engineering status.

## Deployment

The site builds into `dist/` using only Python's standard library. The Git-linked Cloudflare Pages project `cendavo-deployment` uses build command `python3 scripts/build_site.py` and output directory `dist`. Pushes to `main` deploy automatically to [cendavo-deployment.pages.dev](https://cendavo-deployment.pages.dev/). The backup GitHub Actions deployment workflow is manual and restricted to `main`. It needs a repository secret `CLOUDFLARE_API_TOKEN` (or the existing `CLOUDFLARE_API`) and a repository variable `CLOUDFLARE_ACCOUNT_ID`. GitHub's check workflow runs on pushes and pull requests. Review local Forge checkpoints before pushing, because a push to `main` can publish them.
