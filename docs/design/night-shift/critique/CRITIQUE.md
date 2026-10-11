# Cendavo: creative direction critique (shots16 plus live scroll captures)

The site is close. The type, the palette and the photography carry it. What still holds it back is repetition: every inner page ends with the same three-part kit (a heading-left/2x2-grid section, an FAQ, then a dark photo CTA), and it has a few broken edges. Ranked by visual impact per effort:

## Top 8

**1. Work index strip and mobile grid have no gutter (looks broken).** `/work/`, the four thumbnails under the hero. Images and captions sit flush against x=0, and at 1440 the fourth caption ("Demonstration project, sample data") is clipped on the right. On 390 the 2x2 grid also touches both edges. *Fix:* if it is meant to scroll sideways, set `padding-inline: var(--gutter)` with `scroll-padding-inline` the same, and keep captions inside the gutter. If it is not, put it in the container as a 4-column grid with a 24px gap, captions aligned to the headline's left edge. On mobile use 2 columns with a 12px gap inside a 16px gutter. Risk: none.

**2. Harbourside case-study hero has white type over a white photo.** `/work/` Harbourside band, `detail-mono`. "Mobile Detailing" and the meta row sit over blown-out spray, and on mobile the "Concept project · fictional business" label all but disappears. *Fix:* set `object-position: 70% 50%` so the car sits right of centre, and add a left scrim (`linear-gradient(90deg, rgb(14 13 10/.78) 0 38%, transparent 70%)`). Or swap in `detail-splash`, which is darker. Check that the label reaches 4.5:1. Risk: fixes an accessibility failure.

**3. About page is three of the same section in a row.** "How we think" / "How we build" / "What you can expect" each use a heading and intro on the left with a ruled list or 2x2 grid on the right. This is exactly the "headline+paragraph+cards" pattern the client rejected. *Fix:* keep "How we think" as it is (the photo and list work). Turn "How we build" into one full-width typographic band: four short claims set at `clamp(1.6rem,3vw,2.6rem)` and run inline with hairline separators, no photo (the cleaner photo is reused anyway). Cut "What you can expect", since it repeats services and pricing, and link to `/pricing/` instead. Saves about 900px. Risk: none.

**4. The quote card and "always included" appear twice.** The rotated Quote card is on Home and is also the Pricing hero, and Home's "Always included" list repeats Pricing's "Every project includes". *Fix:* on Home, replace the card with a full-bleed `garden-walk` band (`object-position: 50% 65%`) with the fixed-quote line in white at `clamp(2.4rem,5vw,4.5rem)` and one link. Keep the card only on Pricing, where it is the hero idea. Risk: one more lazy image (about 150 KB AVIF).

**5. The pinned concept-projects crossfade passes through a muddy frame.** Home, scroll position about 3600 at 1440. Mid-transition, both laptops show at about 50% and the left text block is invisible for a full viewport of scroll. The Greenline laptop also runs about 20px past the right edge. *Fix:* shorten the crossfade to 25% of each segment and let the outgoing text fade in the first 10% and the incoming text in the last 10%, so text is never absent. Clip mockups with `max-width: min(58vw, 820px)`. Optionally scale the outgoing photo from 1 to 1.04 for depth. Under reduced motion, keep the static stacked fallback. Risk: none.

**6. Home intro has dead space.** "We make websites for people who do the work…" sits about 130px under the hero, but then the `detail-buffer` photo (left, about 530px) and the two paragraphs (right) float with about 120px of air between them and no shared baseline. *Fix:* top-align the paragraphs with the top of the photo. Make the photo span 5 columns at a 4:5 crop (`object-position: 40% 60%`, centred on the pad). Pull the statement into a 9-column measure and cut section padding from about 200px to `clamp(96px,10vw,160px)`. Risk: none.

**7. Every page ends with the same footer stack.** FAQ, then a dark photo CTA, then a footer whose outlined button repeats the CTA directly above it. *Fix:* drop the footer button. Make the footer the signature: the wordmark "Cendavo" set at `clamp(5rem,16vw,15rem)`, cropped by the bottom edge (`margin-bottom: -.18em`, `overflow: hidden`), with nav and legal in one 13px row above it. Vary the CTA photos: Home `detail-rear` (keep), Services `barber-tools` (unused at present, warm, on-brand), About `garden-deck` (keep), Pricing `garden-wall`. Risk: none. Mark the giant wordmark `aria-hidden` and keep the text logo.

**8. Pricing "How the price is set" is a stock 1/2/3 card row.** Three equal columns with big numerals. *Fix:* the steps really are a sequence, so set them as one horizontal timeline: a single 1px rule across the container with three ticks, labels hanging below, numerals at 14px in the stone colour. Let the headings carry the hierarchy. Do the same on Home "How it works": the 01–05 numerals are about 72px in amber/stone and compete with the 24px step headings, so drop them to 20px tabular figures in `--stone` and set the headings at 28px. Risk: none.

## Still reads templated

- "Concept project · fictional business" over every block, plus middle-dot meta strings. The honesty label must stay; show it once per project, under the title, in sentence case.
- The "— item" dash lists repeat across projects, services and pricing. Use plain ruled rows.
- The Pricing "Straight answers" FAQ uses the same accordion as Home and Services. Fine, but give each page's FAQ a different heading treatment or drop it from Services.
- The demo hero leaves its right half empty. Bring a cropped live screenshot of the queue in from the right edge.

## Mobile

- The Work grid touching the edges (#1) is the only real break.
- Home hero: the photo takes about 420px before the headline. Overlay the headline on the lower photo with a bottom scrim so the H1 and CTA land above the fold at 844px tall.
- Contact: the `detail-headlight` crop in the left column cuts the car awkwardly under the steps. On mobile hide it; on desktop set `object-position: 30% 50%`.
- Services list: the active-row `translateX(6px)` reads as misalignment in stills. Use an opacity change only.

## Do not touch

- Home hero: the darkroom headlight photo, the stacked H1, the amber CTA and the phone mockup.
- The before/after slider section. It is the best conversion idea on the site.
- Display type (condensed grotesk, tight leading) and the near-black/bone palette with a single amber.
- The "Built for the businesses that keep Sydney running" staggered photo row.
- Pricing "What affects the quote" spectrum rows, and the care-plan photo panel.
- The honest labelling and copy tone everywhere.
