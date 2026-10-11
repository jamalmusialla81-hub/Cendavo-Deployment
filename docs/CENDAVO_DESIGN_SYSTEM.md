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

## Art direction (supervisor, 2026-10-11) — follow this over the generic token guidance above

Audience: owners of Sydney local service businesses (mobile detailers, landscapers, cleaners, barbers, trades) who are proud of their work and embarrassed by their website. Job of the homepage: make them think "that's what my business should look like" and request a consultation.

### The one memorable thing: the polish sweep (hero)

A browser-frame mockup of a **fictional** business, "Harbourside Mobile Detailing", labelled visibly *Illustration · fictional business*. It has two states built in HTML/CSS (no images required): a dated **before** (cramped, clip-art feel, low contrast, tiny phone number) and a polished **after** (Cendavo's design language, clear "Book a detail" button, reviews area left as an empty placeholder box, not fake reviews). On first load a single specular highlight — a soft diagonal band of light like a polished paint panel — sweeps left to right across the frame once (~1.2 s, `transform` only), revealing the after state behind it. Then a draggable seam (a native `<input type="range">`, labelled "Compare before and after", keyboard operable, visible focus) lets the visitor wipe between states. WCAG 2.2 (2.5.7 dragging): also provide two buttons, "Before" and "After", as a single-pointer alternative; the range must be keyboard operable with visible focus. Reduced motion: no sweep, after state shown, slider still works. On ≤ 640 px the frame stacks under the headline and shows a phone-width version of the same mock.

Everything else on the page is calm. No scroll-triggered fade-ups on every section, no hover animation on every card, no particles, no 3D.

### Palette (CSS custom properties)

| Token | Hex | Role |
| --- | --- | --- |
| `--harbour` | `#0E2A33` | text, dark sections, header on scroll |
| `--fog` | `#EEF2F1` | page surface (cool, not cream) |
| `--paper` | `#FFFFFF` | raised surfaces, the "after" mock |
| `--jacaranda` | `#6E4FD8` | primary actions and the sweep highlight tint only; flat, never a gradient wash |
| `--sandstone` | `#C98B3D` | decoration only on light surfaces (2.6:1 on fog — never text there); text-safe on `--harbour` (5.2:1) |
| `--sandstone-ink` | `#8C5A1C` | sandstone for text on light surfaces (5.2:1 on fog) |
| `--jacaranda-light` | `#B9A6F2` | jacaranda accents on dark `--harbour` sections (7.0:1); plain `--jacaranda` on harbour fails (2.7:1) |
| `--slate` | `#55666C` | secondary text (check ≥ 4.5:1 on `--fog`) |
| success / danger | `#1F7A52` / `#B93A26` | form states only |

Measured contrast (WCAG): harbour/fog 13.3, slate/fog 5.3, white/jacaranda 5.6, jacaranda/fog 4.9 — all AA. Buttons in the dark closing band use `--fog` fill with `--harbour` text, not jacaranda. Check any new pair for AA. Dark theme is optional; if added, derive it from `--harbour`, do not invert blindly.

### Type

- Display: **Archivo** (Google Fonts variable, use the width axis at 112–125 = expanded, weight 700–800) — wide, confident letterforms like sign-writing on a work van. Headlines set tight (−0.02em), sentence case.
- Text: **Atkinson Hyperlegible** (Google Fonts) 400/700 — designed for legibility, fits the accessibility priority.
- Scale with `clamp()`: display ≈ 2.6–5.2 rem, h2 ≈ 1.9–3 rem, body 1.0625–1.125 rem / 1.6, line length ≤ 70ch. Left-aligned throughout; no centred paragraphs.
- Avoid: all-caps eyebrow labels above headings, accenting one word of a headline in a colour/italic, middle-dot meta strings, "→" appended to buttons.

### Homepage sections (in order)

1. **Hero** — headline (sentence case, pick the strongest): "Your work is excellent. Your website should say so." or "Websites as sharp as the work you do." One-line support: "Cendavo designs, builds and looks after websites for Sydney's local service businesses, so the people searching for you can see why to call." Primary button "Request a free consultation" (→ `/contact/`), secondary text link "See a demonstration project". Polish-sweep frame on the right (7 of 12 columns on desktop).
2. **What we do** — three services as large typographic rows, not cards: *New website*, *Redesign*, *Care plan* — each with one plain sentence on what you get. Hairline separators between rows are fine here.
3. **Who it's for** — one large wrapping line of trades in the display face (detailers, landscapers, cleaners, barbers, electricians, plumbers…), followed by one sentence on what they have in common (customers judge them on their phone in seconds).
4. **How it works** — a real five-step sequence, numbered: Discover → Design → Build → Launch → Look after. Horizontal on desktop, vertical on mobile. Each step: short title and one sentence with what the client does vs what Cendavo does.
5. **Work** — the existing request-queue demo as "Demonstration project — sample data", with a real screenshot or live link to `/demo/`, and an honest line: "Our first client sites will appear here." No fabricated portfolio.
6. **Pricing** — do not publish numbers until the owner confirms them (see docs/CENDAVO_BUSINESS_LAUNCH.md for the recommended ranges). Use "Fixed quote after a free 20-minute call" with a link to `/pricing/` and the consultation CTA.
7. **Questions** — 5–6 FAQs with native `<details>` (timelines, who writes the words, who owns the site, what the care plan covers, what happens after launch).
8. **Closing CTA** — dark `--harbour` band: "Tell us about your business." + the consultation button.

### Conversion

One primary action everywhere: "Request a free consultation". The enquiry form asks only what is needed to reply, shows sending progress and a clear confirmation (task 4). No exit pop-ups, no countdowns, no fake scarcity.

### Copy voice

Plain, confident, Australian English, second person, short sentences. Name things by what owners understand ("your website shows up properly on phones"), not by tech ("responsive breakpoints"). No hype words ("cutting-edge", "next-level"), no invented numbers.

### Done means

Screenshots at 1440, 768 and 375 px look intentional; the sweep plays once and never shifts layout; the slider works by mouse, touch and keyboard; Lighthouse-style basics pass; the enquiry form from task 4 still works; tests updated.
