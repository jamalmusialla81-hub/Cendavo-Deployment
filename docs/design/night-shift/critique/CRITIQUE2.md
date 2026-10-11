# Cendavo: second-round critique (shots19 plus live scroll captures)

Round one's fixes are in: the Work gutter, the Harbourside scrim, the About cut, the footer wordmark, the pricing timeline and the mobile hero overlay. What is left is composition: half-empty heroes, a Work page that runs one template three times, and rows that look misaligned in stills.

## Top 6 (ranked by impact per effort)

**1. Home, "What we do": thumbnails look misaligned and the middle is empty.** `.svc-list.is-live .svc:not(.is-active) img{transform:scale(.94)}` scales the inactive images towards their right edge, so their left edges sit 20px apart (1040 vs 1060 at 1440). About 500px of dead black sits between text and thumbnail. Care plan also uses `garden-walk`, its third use on Home. *Fix:* use a 7/5 grid. Put one sticky 4:5 media panel in the right 5 columns (`position:sticky; top:12vh`) that crossfades to the active row's photo (opacity only, 500ms). Drop the scale. Photos: New website `detail-wax` (the stock kitchen clashes with the grade), Redesign `detail-dash`, Care plan `garden-wall`. *Risk:* the panel should be `aria-hidden` and the row must activate on `:focus-within` too. One more lazy AVIF.

**2. About and Demo heroes have an empty half.** On About, a 1,000px black field holds one paragraph at bottom right. On Demo, the right half is still empty (round one, not done). *Fix:* About: move the paragraph under the H1 (left 5 columns). In the right 7 columns, set three 4:5 photos, `barber-shave`, `garden-wall`, `detail-wax`, with vertical offsets 0/64/32px and a 16px gap, bleeding past the right gutter. Demo: pull the live app up with `margin-top:-22vh` so the "Requests at a glance" panel and table overlap the hero's lower right. *Risk:* none. The photos are decorative (`alt=""`).

**3. Work: the same case-study kit three times (10,500px).** Each project runs hero, a "The brief" / "What the site does" split, then "Key screens". *Fix:* keep Harbourside in full. Greenline: mirror it (photo left 7 columns, title right) and set the brief as one large pull line at `clamp(1.8rem,3vw,2.6rem)` with no list. Fade & Co: lead with the key screens on a full-bleed `barber-interior` band at 25% brightness, then add the brief as two sentences. Target about 7,500px. *Risk:* none; keep each honesty label.

**4. Demo table is broken on mobile (390).** The table is 746px wide inside a 340px card. Dates are cut off ("Thu, 8 Oct 202"), and Status and Next action, the point of the demo, are off-screen. *Fix:* at `max-width:640px`, render each `tr` as a grid block: `grid-template-columns:1fr auto`, name and service on line 1, date on line 2, status pill top right, select and "Draft reply" in a full-width row below. Keep a visually hidden `thead`. *Risk:* improves accessibility.

**5. Home pinned projects: the counter is out of sync and one frame is muddy.** At scroll 2,900 the Greenline laptop is on screen, but the counter still reads "1" and the Greenline title is a grey ghost at about 40% opacity. *Fix:* compute the index as `Math.round(progress*(count-1))`. Fade the outgoing copy out by 30% of the segment and bring the incoming copy in from 70% to 100%. Wipe media with `clip-path: inset()` instead of an opacity crossfade. *Risk:* none.

**6. Contact repeats the kit and has a photo sliver.** The `detail-headlight` crop is a 180px band under the steps on desktop. The photo is also About's CTA and a Work thumbnail. "What to expect from us" is another heading-left 2x2 that repeats About. *Fix:* remove the image so the steps column ends cleanly. Cut "What to expect" and put its four claims as one 15px line under "Send enquiry". Change About's CTA to `garden-lawn` (`object-position:50% 70%`). *Risk:* none.

## Still reads templated (low effort)
- "Concept project · fictional business" with the middle dot is still used everywhere. Write it as "Concept project, fictional business."
- The "—" dash bullets in the Home project lists and the amber square bullets on Services: use plain ruled rows.
- "Demonstration project — sample data" chip: use "Demonstration project with sample data."
- Services opens and closes on Fade & Co's barbershop photos. Use `trade-panel` for the CTA.

## Mobile
- The demo table (#4) is the only real break. No route overflows horizontally at 390, and no tap target is under 24px.

## Verdict
This is now a credible, well-made studio site. The type, palette, real photography, honest labels and before/after slider all hold up. It is not yet at elite-agency level. Too many sections are still text beside a same-sized photo, and the Work page, which buyers judge a studio by, is one layout repeated. The single change that would raise it most is #3 done properly: give each concept project its own art direction (composition, pacing, one signature moment per project) so the Work page reads as three commissions rather than three records in a CMS.
