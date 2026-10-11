# Cendavo — "Night Shift" art direction (overnight master direction)

Owner feedback this direction answers: earlier concepts looked "AI" (neon, glows, gradient pills, empty dark space, basic cards); samples need real photography; it must look extremely professional — like an expensive real studio, not a template.

## Principle
Photography carries the colour and drama. Type and layout are restrained, precise and confident. Motion reveals content (photos, headlines, mockups) — it never decorates empty space. If an element doesn't help an owner understand "these people make websites that win customers", cut it.

## Palette (no neon, no glows, no gradient fills on UI)
- `--ink` #0E0E0D (main dark), `--ink-2` #171716 (raised dark), `--line` rgba(237,234,227,.14)
- `--bone` #EDEAE3 (light sections + text on dark), `--stone` #A8A49B (secondary text on dark; check ≥4.5:1)
- `--amber` #D9A441 — the only accent: primary CTA fill, active states, one small mark. Text on amber is `--ink`.
- Alternate dark and bone sections for rhythm; photography sections are full-bleed.
- Allowed "lighting": photographic vignette (dark-to-transparent over photos for legibility), film grain at ≤4% opacity. Nothing else.

## Type
- Display: Archivo variable. Headlines heavy (wght 760–820) at a slightly condensed width (wdth 82–90), tight leading (0.92–1.0), tracking −0.02em, sentence case. Use size contrast, not colour, for emphasis.
- Small display labels (project names, step titles): Archivo wdth 100–110, wght 600.
- Body: Atkinson Hyperlegible 400/700, 17–19 px, line-height 1.55, ≤ 65ch.
- Never: tracked all-caps eyebrows above every heading, one coloured word in a headline, gradient text, middle-dot meta strings (except the required "Concept project · fictional business" label), "→" on every button.

## Components
- Buttons: rectangular, radius 2 px, height ≥ 48 px, padding 0 22 px. Primary: `--amber` fill, `--ink` text. Secondary on dark: 1 px `--bone` border, transparent. Hover: background shift + 2 px translate of an inline arrow icon *only on the primary CTA*. Focus: 2 px solid `--bone` outline offset 3 px (amber on light sections).
- Links: underline that draws on hover (transform-based).
- Image frames: no rounded corners on full-bleed photos; device mockups use realistic thin bezels (laptop with hinge shadow, phone with 38 px radius), soft contact shadow (no glow).

## Imagery (local files: ../images/*.jpg, 1600 px wide; see ../images/manifest.tsv)
- Harbourside Mobile Detailing (concept): detail-darkroom, detail-splash, detail-wax, detail-buffer, detail-dash, detail-headlight, detail-rear, detail-mono
- Greenline Landscapes (concept): garden-path, garden-lawn, garden-deck, garden-wall, garden-walk
- Fade & Co barbers (concept): barber-interior, barber-chair, barber-client, barber-cut, barber-tools, barber-shave
- Also: clean-living, clean-kitchen, trade-panel (for "Who it's for")
- Use `<img>` with width/height, `loading="lazy"` below the fold, `decoding="async"`, meaningful alt text, `object-fit: cover`. Hero image eager + `fetchpriority="high"`.

## Honesty
Concept projects are always labelled "Concept project · fictional business". No invented clients, testimonials, reviews, ratings, stats, awards or prices. Pricing = fixed quote after a free consultation.

## Motion (GSAP 3.13 + ScrollTrigger, files ../gsap.min.js ../ScrollTrigger.min.js)
All inside `gsap.matchMedia()` with `(prefers-reduced-motion: no-preference)`; content fully visible without JS and with reduced motion; initial states only set from JS; animate transform/opacity/clip-path only.
1. Intro (first visit per session only, ≤ 2.4 s, skippable with any key/click, "Skip" button): the C mark assembles from three arcs, wordmark resolves, then the intro panel wipes up (clip-path) to reveal the hero already in place. Store `sessionStorage` flag (wrapped in try/catch).
2. Hero: headline lines rise through masks (stagger 0.08), hero photo scales from 1.08 → 1 as it un-masks (clip-path inset wipe), CTA fades up.
3. Concept projects: on desktop a pinned sequence — photo full-bleed behind, the device mockup slides/rotates into place, caption swaps per project; on mobile, stacked with clip-path image reveals.
4. Photos parallax gently (yPercent ±6, scrub) — never more.
5. Before/after slider (Harbourside): accessible `<input type="range">` "Compare before and after" + Before/After buttons with aria-pressed. The "after" uses real photography; the "before" is convincingly dated (clip-art, cramped table layout, low contrast).
6. Process: horizontal step rail that fills on scroll (desktop), simple list on mobile.

## Quality floor
Responsive 360–1920 px, no horizontal overflow, tap targets ≥ 44 px, visible focus, landmarks + heading order, AA contrast, CLS < 0.05, lazy images, total JS (excluding GSAP) < 15 KB.

## Notes for Forge
- In the prototype, images are referenced as `../images/<name>.jpg`; in the repo they are `assets/images/<name>-1600.jpg` and `-800.jpg` (use srcset). Fonts are in `assets/fonts/`, GSAP in `assets/vendor/gsap/`.
- Supervisor review notes: use Archivo (not Atkinson) for years/numerals to avoid the slashed zero; fill the empty lower area of the Harbourside booking phone; keep the inline head script only if the CSP allows it (current CSP is `script-src 'self'` — move it to an external file instead of loosening the CSP).
- Reference screenshots: `p3-hero.jpg`, `p3-work1.jpg`, `p3-ba.jpg`, `p3-m-hero.jpg` in this folder.
