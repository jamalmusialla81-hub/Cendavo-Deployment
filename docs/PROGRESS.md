# Cendavo progress

Updated 2026-10-12.

Cendavo is a website design, redesign and care studio for local service businesses. The earlier plan for a hosted admin product is no longer what the site offers, and that work is not being continued.

## Built

| Area | Current state |
| --- | --- |
| Studio site | Home, Work, Services, Pricing, About, Contact, Demonstration project and a 404 page (`noindex`, not in the sitemap), built from `pages/` by `scripts/build_site.py`. "Night Shift" photography-led design, see [NIGHT_SHIFT_PLAN.md](NIGHT_SHIFT_PLAN.md). |
| Work | Fictional concept projects only, each labelled "Concept project · fictional business". No real clients, testimonials or results. |
| Demonstration project | Browser-local request queue on synthetic sample data, with a CSV download. Sends and uploads nothing. |
| Enquiries | Contact form → Pages Function `functions/api/enquiry.js` → D1 binding `ENQUIRIES_DB` (`migrations/0001_enquiries.sql`, `0002_enquiry_throttle.sql`). Server-side validation, idempotent retries, honeypot, minimum fill time, built-in throttle (20 per 10 minutes, 3 per email per hour) and a plain-text Resend alert email to the owner for each new enquiry once the secrets are set. No admin view, retention rule or CAPTCHA yet. See [ENQUIRIES.md](ENQUIRIES.md). |
| Assets | Self-hosted Archivo and Atkinson Hyperlegible fonts, vendored GSAP and ScrollTrigger with reduced-motion handling, AVIF photos with JPEG fallback, Open Graph share card, self-only Content Security Policy. |

## Open owner decisions

1. **Enquiry setup:** the D1 database and `ENQUIRIES_DB` binding are live (per [NIGHT_SHIFT_PLAN.md](NIGHT_SHIFT_PLAN.md) Task 30). Still to do: apply `migrations/0002_enquiry_throttle.sql` to the live database, add the `RESEND_API_KEY` and `ALERT_TO` secrets for Production, redeploy and confirm one alert arrives. The steps are in [ENQUIRIES.md](ENQUIRIES.md).
2. **Public contact channel:** the site publishes the business address cendavo.au@gmail.com (Night Shift Task 31) beside the contact form, in the privacy note, in every page footer and in the enquiry failure messages. No phone number is published. Still to do: confirm the inbox is monitored and decide whether the privacy note should say that email sent directly is handled by Google (Gmail).
3. **Prices:** none are confirmed. The site says only "fixed quote after a free consultation". Project prices and care-plan pricing are still to be decided. The earlier SaaS hypothesis of A$49–99 per month was never validated and is retired.
4. **Enquiry handling:** decide how long enquiries are kept and how often D1 is checked.
5. **Enquiry scope:** confirm or reverse the "Differences from the task spec" in [ENQUIRIES.md](ENQUIRIES.md). They are not owner decisions yet.
6. **Design approval:** review the Night Shift design on branch `design/night-shift` and decide whether to merge it to `main`.
7. **Decision record:** record the pivot from a SaaS product to a studio in [DECISIONS.md](DECISIONS.md). There is no entry for it yet.
8. **Lead Hunter:** not built and not queued. It needs a decision on acceptable data sources and where research data lives. See [CENDAVO_LEAD_HUNTER_PLAN.md](CENDAVO_LEAD_HUNTER_PLAN.md).

## Business assumptions

- **Customers:** local service businesses in Sydney, such as detailers, landscapers, cleaners and barbers. Demand, conversion, sales cycle and acquisition cost have not been measured.
- **Revenue:** no verified revenue data exists, and the site makes no revenue or customer claims.
- **Operating cost:** Cloudflare Pages, Functions and D1 on the account's current plan. Resend (free tier) sends the owner's enquiry alerts only; there is no customer messaging and no checkout. Check the current free-plan limits on the account.

## Engineering and release

- **Branch and deployment:** the Night Shift design is on `design/night-shift`. It is not deployed and won't be merged to `main` until the owner approves the visuals. Pushes to `main` deploy to Cloudflare Pages project `cendavo-deployment`, and the GitHub Actions deploy workflow is manual and limited to `main`.
- **Tests:** `python3 -m unittest discover -s tests -v` covers the build, pages, demo script, enquiry function and Forge tooling. The run commands are in the [README](../README.md).
- **CI gap (open):** `.github/workflows/checks.yml` runs `node --check` on `assets/site.js` and `assets/demo.js` only. `enquiry.js`, `home.js`, `motion.js` and `motion-boot.js` are not syntax-checked in CI. Adding them needs a task with permission to change CI.
- **Security:** the enquiry endpoint accepts same-origin JSON up to 16 KB, validates every field on the server, uses parameterised SQL, stores no IP or user-agent data and never returns database errors. Spam controls are the honeypot, fill time and a built-in soft throttle; a flood can block real visitors for up to 10 minutes. The only outbound request is the alert to Resend's fixed API address, sent after the response; its key is never returned or logged.
- **Agent workflow:** Forge runs the Claude-only Strategist → Builder → Security Reviewer → tests → Functional Auditor loop. See [FORGE.md](FORGE.md).
