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

## Notes from Task 7 attempt 1 (blocked by the test-weakening guard, a verified false positive)
- Do not add any new `skip`/`skipUnless`/`skipIf` decorator or call anywhere in tests, even one that copies an existing pattern. Put new Node-based tests inside the existing `DemoScriptTests` class in `tests/test_demo_js.py` (it already carries the `node` skip) instead of a new decorated class.
- Do not name helper parameters or functions `skip` in test code (e.g. use `exclude`); the guard pattern-matches `skip(`.
- When old assertions about the previous design are removed, replace each accessibility guarantee with an equivalent new assertion (skip link, `<main id="main">`, reduced-motion rule, Escape closes the menu, `aria-expanded`). Attempt 1 did this correctly; keep it.
- The supervisor kept attempt 1's patch for reference outside the repo.

## Task 9 — inner pages (supersedes "Task 8 — inner pages" above; Forge task ids shifted after the Task 7 retry)
Reference prototype: `docs/design/night-shift/prototype/` now also contains `work.html`, `services.html`, `pricing.html`, `contact.html`, `ns-pages.css`, `ns-pages.js`, `ns-boot.js` and screenshots `pages-*-d-top.jpg`. Build these pages into the site (`pages/work.html` as a new route `/work/` added to `NAV`/titles/descriptions in `scripts/build_site.py`, and `pages/services.html`, `pages/pricing.html`, `pages/contact.html`, plus the demo page reframed as "Demonstration project — sample data"). Apply everything in the Task 8 list above (remove all SaaS wording).

Supervisor review notes for Task 9:
- Contact: keep the production form markup and `assets/enquiry.js` behaviour exactly (ids, `data-enquiry`, `aria-describedby`, `.field-error[data-error-for]`, honeypot, status region, 429 retry, idempotency). Only layout wrappers and classes may change. Existing enquiry tests must keep passing unchanged.
- Numerals: Atkinson Hyperlegible draws a slashed zero ("2Ø-minute"). Add an `@font-face` for the body family that maps digits only (`unicode-range: U+0030-0039`) to the local Archivo file, declared so digits render in Archivo inside body text.
- Services hero: replace `barber-tools` (it shows a third-party product logo) with an unbranded photo, e.g. `barber-chair` or `garden-wall`.
- Reuse the shared design system from Task 8; do not fork styles per page beyond a page stylesheet.
- Same test rules as the Task 7 notes (no new skip decorators; no helpers named `skip`; replace any removed accessibility assertion).

## Task 10 — cinematic motion layer (OWNER-MANDATED; profile `site`)
The owner has explicitly and repeatedly required a cinematic, motion-design-led website (2026-10-11: "the website itself should feel like an interactive motion-graphics experience"; "kinetic typography, sophisticated scroll choreography, dramatic website mockup transitions"). Earlier strategist reviews cut this motion for conversion/accessibility reasons. Those concerns are valid as **constraints**, not as reasons to drop the work: implement the motion within the constraints below. Strategist: do not reduce this scope; challenge only how it is done.

Implement on top of the delivered Night Shift pages, using `assets/vendor/gsap/` (GSAP + ScrollTrigger), following the prototype `docs/design/night-shift/prototype/ns.js`, `ns-pages.js`, `ns-boot.js`:
1. **Intro** (homepage, first visit per browser session only): C-mark assembles from three arcs, wordmark resolves, panel wipes away to the hero. Hard limits: ≤ 1.8 s total; skippable by any click, key or scroll; never blocks typing in form fields; does not run with reduced motion, without JS, or when the URL has a hash; hero content is in the DOM and visible to assistive technology throughout. Session flag in `sessionStorage` wrapped in try/catch. Boot logic in an external file (CSP `script-src 'self'`).
2. **Hero choreography:** headline lines rise through masks (stagger), hero photo un-masks with a clip-path wipe and settles from scale 1.08 to 1, CTA follows; total ≤ 1.2 s; CTA clickable immediately.
3. **Concept projects (homepage):** on viewports ≥ 1081 × 620 a pinned sequence of at most ~2 viewport-heights total: photo wipes, device rises/turns into place, caption swaps, 1–3 counter. Provide a visible "Skip projects" link that jumps past the pinned section; keyboard focus entering a project scrolls it into view. Smaller viewports: stacked with clip-path reveals.
4. **Scroll choreography elsewhere:** gentle photo parallax (yPercent ±6, scrub), section headings rise once, process rail fills on scroll, services row/photo swap on hover/focus, inner-page openings and device reveals per the prototype.
5. **Microinteractions:** primary CTA arrow nudge, link underline draw, magnetic primary button (≤ 6 px, fine pointers only), FAQ `<details>` height animation.
Constraints for everything: `gsap.matchMedia()` with `(prefers-reduced-motion: no-preference)`; no content hidden by CSS (initial states only from JS; CSS failsafe reveals content if GSAP fails to load); animate transform/opacity/clip-path only; no smooth-scroll library or scroll hijacking beyond the capped pin; CLS < 0.05; GSAP loaded only on pages that use it, deferred; page JS (excluding GSAP) < 20 KB. Tests: reduced-motion guard and failsafe present, intro skippable and session-limited, skip link exists, GSAP only on pages that need it, no inline scripts. Same test rules as earlier notes (no new skip decorators; no helpers named `skip`).
