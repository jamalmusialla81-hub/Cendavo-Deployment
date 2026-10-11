# Night Shift overhaul — Forge plan (overnight 2026-10-11 → 12)

Owner direction (2026-10-11): the Task 5 redesign is not visually acceptable. Build a premium, cinematic, photography-led studio site; no neon/glow/"AI" look; real photography for samples; GSAP motion; self-hosted fonts. Work lands on branch `design/night-shift`; `forge/linux-wsl-backend` moves only after the owner approves the visuals. No deploy, no `main`.

Reference material (read-only for Forge):
- `docs/design/night-shift/NIGHT_SHIFT.md` — art direction (palette, type, components, motion, honesty rules).
- `docs/design/night-shift/prototype/` — the approved-direction HTML/CSS/JS prototype (`index.html`, `ns.css`, `ns.js`). It is a design reference, not production code: port it into the site's build system, keep behaviour accessible and tested.
- Vendored assets already in the repo: `assets/fonts/` (Archivo variable + Atkinson Hyperlegible WOFF2, OFL), `assets/vendor/gsap/` (GSAP 3.13.0 + ScrollTrigger), `assets/images/` (22 Unsplash photos at -1600/-800 widths, `CREDITS.md`).

## Task 7 — design system, global chrome and homepage (profile `site`)
Port the prototype's design system into `assets/site.css` (or a new `assets/ns.css` loaded globally), header/footer/nav into `scripts/build_site.py`, and the homepage into `pages/index.html` + `assets/home.js`. Self-host fonts with `@font-face` (`font-display: swap`) and remove the Google Fonts `@import`; update the CSP in `build_site.py` to `font-src 'self'` and drop `fonts.googleapis.com` from `style-src`. Load GSAP only on the homepage, deferred. Images via `<img srcset>` using -800/-1600. Keep the enquiry form, Task 2 accessibility and Task 3 CSV export working. Update/extend `tests/test_site.py` (CSP has no third-party font hosts, fonts and GSAP are local, homepage images have width/height/alt, reduced-motion guard present, no SaaS wording on the homepage, concept projects labelled).

## Task 8 — inner pages in Night Shift (profile `site`)
Rebuild `pages/services.html`, `pages/pricing.html`, `pages/contact.html` and `pages/demo.html` in the new system. Remove all SaaS/product messaging: "A shared platform", "focused admin tool", "research hypotheses", "Future subscription A$49–99 / month", "Business workspace", "Can I subscribe now?", "product demo"/"workspace preview" framing, and the `pricing` meta description about "pricing hypotheses and pilot options". Services: New website, Redesign, Care plan with what's included and how it works. Pricing: fixed quote after a free consultation, what every project includes, what affects the quote, care plan described without numbers (owner has not confirmed prices). Contact: the existing working enquiry form restyled (keep all hooks, validation, idempotency, 429 retry, privacy note). Demo page: reframed as "Demonstration project — sample data" (a browser app we built), keep its functionality and tests. Add a Work page section or page listing the three concept projects if the prototype has one.

## Supervisor review after each task
Rendered screenshots at 1440/768/390, keyboard pass, reduced-motion pass, enquiry flow smoke test, full test suite. Visual sign-off is the owner's.
