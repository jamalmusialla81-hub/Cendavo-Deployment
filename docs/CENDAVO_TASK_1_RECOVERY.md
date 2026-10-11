# Task 1 recovery: enquiry workflow

## Why original Task 1 failed (evidence from `.cendavo-run`)

Original Task 1 asked for a small improvement to the **product demo's request queue** (`pages/demo.html`). Its Strategist report proposed a one-session fix: give the "Other service" option `value="Other"`, use concrete seed data for one trade, explain "Done", update `PROGRESS.md`, add tests.

The Builder never implemented it. Every attempt ended in infrastructure:

| When (UTC) | Event | Category |
| --- | --- | --- |
| 10-10 13:44 | `audit-2` hit a provider usage limit | provider limit |
| 10-10 13:57 | `audit-preflight-1` hit a provider usage limit | provider limit |
| 10-10 14:30 | refused: source tree had uncommitted changes | environment (dirty tree) |
| 10-10 14:32 | `[Errno 1] Operation not permitted` | environment |
| 10-10 14:37 | **failed:** pre-flight `build` exited 1 — `python3: realpath: /opt/homebrew/bin/: Operation not permitted` | **Forge sandbox defect** |

Root cause of the terminal failure: the v1 checks sandbox allowed reads under `/opt/homebrew` but not of `/opt` itself, so Homebrew's `python3` could not resolve its own path inside `sandbox-exec`, before any product code ran. Forge v2 (`73f8023`, "probe with the checks stage's python3 and reject vacuous sandbox denials") fixed this; `forge.py doctor` now passes its checks-sandbox probe on this Mac.

**Category: environment / supervisor-infrastructure failure, not a product implementation failure.** No repair attempt should be spent on it again.

The original demo fix is still worth doing and is folded into the recovery task below (item 9).

## Recovery task A — real enquiry workflow (profile `app`)

The site's contact page currently has a "Prepare my brief" form that sends nothing. Replace it with a working enquiry ("request a consultation") flow for a **website design agency**, stored in Cloudflare D1 through a Cloudflare Pages Function. Keep the site's zero-dependency static build.

### Scope

1. **Form** on `pages/contact.html` (and reachable from the header CTA): name, email, phone (optional), business name, current website URL (optional), service interest (`website-design`, `website-redesign`, `maintenance`, `not-sure`), budget range (optional), message. Visible labels, `autocomplete` attributes, required markers, inline error messages linked with `aria-describedby`, focus moved to the first invalid field on submit.
2. **Client behaviour** (`assets/site.js` or a new `assets/enquiry.js`): same validation rules as the server, submit with `fetch('/api/enquiry', {method:'POST'})` as JSON, disabled button + loading text while sending, success message in a `role="status"` region, useful error message that keeps everything the visitor typed, a client-generated idempotency key (`crypto.randomUUID()`) reused for retries so one enquiry is never stored twice.
3. **Server** `functions/api/enquiry.js` (Cloudflare Pages Functions, `onRequestPost`): accept only `application/json` up to 16 KB; validate and normalise every field (lengths, email format, allowed enum values, http(s) URL only); reject with `400` and per-field errors; spam protection without paid services: a hidden honeypot field and a minimum fill time (reject quietly with a fake success); insert into D1 with a parameterised statement; `UNIQUE(idempotency_key)` so a repeat returns the original success (`200`) instead of a duplicate; return `201 {ok:true, id}`; on database errors return `503` with a generic message and never echo internals. Respond only to POST (`405` otherwise).
4. **Schema** `migrations/0001_enquiries.sql`: `enquiries(id INTEGER PRIMARY KEY, created_at TEXT, name, email, phone, business, website, service, budget, message, status TEXT DEFAULT 'new', idempotency_key TEXT UNIQUE, user_agent_hash TEXT)`. Status values `new`, `contacted`, `qualified`, `closed` (lead status tracking groundwork; no admin UI yet).
5. **Binding name** `ENQUIRIES_DB`. Do **not** add `wrangler.toml` (it would change the Git-linked Pages project's configuration). Document the one-time Cloudflare setup in `docs/ENQUIRIES.md`: create the D1 database, run the migration, add the `ENQUIRIES_DB` binding to the Pages project.
6. **Missing binding** (local preview, or before setup): the function returns `503` with "Enquiries are temporarily unavailable — please email …" and the form shows that message; nothing is silently lost.
7. **Security**: no secrets in code; parameterised SQL only; output rendered with `textContent`; keep the existing CSP (`connect-src 'self'` already allows the request); store a salted hash of the user agent, not the IP address.
8. **Tests** (existing Node-via-Python harness, `tests/`): server validation table (valid, each invalid field, oversize body, wrong content type, honeypot, too-fast submit), idempotent repeat, missing binding → 503, DB failure → 503, method not allowed; client validation and that inputs are preserved after a failed submit. Use an in-memory fake for the D1 binding.
9. **Demo fix from original Task 1**: in `pages/demo.html` give "Other service" `value="Other"` so its tailored draft appears, with a regression test.
10. **Docs**: update `docs/PROGRESS.md` (filtering already exists; enquiry workflow added).

### Acceptance criteria

1. A visitor can submit a valid enquiry and gets an accurate confirmation.
2. Invalid input gets specific, accessible feedback; the server rejects it independently of the browser.
3. Valid enquiries are written to D1 exactly once (idempotency key).
4. Failures (no binding, DB error, network error) never crash, never lose what the visitor typed, and say what to do next.
5. Works at 360 px and desktop widths; keyboard-only and screen-reader friendly (labels, errors, status announcements).
6. Task 2 accessibility work and Task 3 CSV export in the demo still work (their tests still pass).
7. All owner checks pass: build, unit tests, `node --check`.

### Out of scope (later tasks)

Admin dashboard (needs authentication, e.g. Cloudflare Access), email notifications (needs an email provider), Turnstile CAPTCHA (needs a site key), visual redesign (task B).
