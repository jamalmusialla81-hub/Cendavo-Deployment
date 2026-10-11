# Cendavo design system and homepage redesign (task B, profile `site`)

Goal: the site should read as a premium, trustworthy website studio for local service businesses and turn visitors into enquiries. It must not look like a generic AI template (no stock purple gradients, glowing buttons or meaningless 3D).

## Positioning (owner decision 2026-10-11)

Cendavo designs, builds, redesigns and maintains websites for local service businesses in Sydney (detailers, landscapers, cleaners, trades, barbers…). Message: *websites that make a local business look as good as its work and bring in enquiries.* Choose the strongest headline from the codebase's context; candidates: "Websites that make your business impossible to ignore." / "Your business deserves more than an average website."

Honesty rules: no invented clients, testimonials, logos, awards, metrics or "trusted by". The request-queue demo is presented as **"Demonstration project — sample data"**, not as client work. Prices only as "starting from" ranges marked as indicative.

## Design tokens (`assets/site.css`, CSS custom properties)

- **Colour:** a deliberate palette: deep ink neutral for text and dark sections, warm off-white surface, one confident brand accent and one supporting accent, semantic success/warning/danger. All text ≥ 4.5:1 contrast (3:1 for large text). Light theme first; add `prefers-color-scheme: dark` tokens if it does not compromise quality.
- **Type:** one expressive display face and one highly legible text face (Google Fonts are already allowed by the CSP; at most 2 families, `font-display: swap`). Fluid type scale with `clamp()`; tight display tracking, comfortable 1.5–1.7 body line height.
- **Space / layout:** 4 px base scale, consistent section rhythm, max content width, 12-column grid on desktop collapsing to one column at ≤ 640 px.
- **Shape / depth / motion:** radius scale, 2–3 shadow levels, motion durations (120/200/400 ms) and one easing curve. Everything animated must respect `prefers-reduced-motion: reduce`.

## Components (reusable classes, used by every page)

Buttons (primary, secondary, ghost; focus-visible rings), header with accessible mobile menu, footer, section headings, cards, service tiles, process steps, pricing card, FAQ accordion (native `<details>`), form fields with error states (keep task A's enquiry form behaviour and markup hooks intact), status/toast region, badges ("Demonstration project").

## Homepage (`pages/index.html`) and global chrome (`scripts/build_site.py`)

1. **Hero:** strong headline, one-sentence value proposition, primary CTA "Request a free consultation" → `/contact/`, secondary CTA "See our work" → the demo showcase. Visual: a CSS/SVG composition of a website mock transitioning desktop → mobile (no external video, no CDN scripts — the CSP is `script-src 'self'`). Subtle entrance animation; static under reduced motion; no layout shift.
2. **Sections:** services (design, redesign, maintenance), why it matters for local businesses, process (discover → design → build → launch → maintain), work (the labelled demo project), indicative starting prices with a link to /pricing/, FAQ, final CTA band.
3. **Global:** update `NAV`, page titles/meta descriptions and footer text in `scripts/build_site.py` to the agency positioning (keep the demo page, relabel "Product demo" → "Demo project" or similar). Header CTA → `/contact/`.
4. Other pages inherit the new tokens and components so nothing looks broken; their content rewrite is a later task.

## Quality bar

- Lighthouse-style basics: no horizontal scroll at 360 px, tap targets ≥ 44 px, visible focus, landmarks and heading order, alt text, `lang="en-AU"`.
- Performance: no new JS dependency; total added JS small and deferred; CSS animations on `transform`/`opacity` only.
- Tests: extend `tests/test_site.py` for the new structure (nav, CTA targets, headings, reduced-motion rule present, no "SaaS/admin platform" positioning left on the homepage, demo badge present). All owner checks must pass.
- Task 2 accessibility and task 3 CSV export must keep working.

Use the `insane-web-design` skills (e.g. `awwwards`, `animation-forge`) for direction, but performance, accessibility, honesty and conversion win over effects.
