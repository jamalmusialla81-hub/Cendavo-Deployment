# Cendavo: third-round critique (motion frames in critique3/)

Rounds one and two are in, and the stills hold up. What is left is mostly motion: one flash bug, and a pinned sequence that still ghosts.

## Top 6 (ranked by impact per effort)

**1. Work, Services, Pricing: the content flashes, blanks, then replays (broken).** Screencast frames show the full page painted at 60–126 ms. At about 145 ms it goes black, because `gsap.from` sets its start state only after the deferred scripts run, and then it animates back in. *Fix:* hide the elements in CSS under the `.motion` class that `motion-boot.js` already sets in `<head>`: `.motion [data-ph] h1,.motion [data-ph-fade]{opacity:0}` and `.motion [data-ph-media]{clip-path:inset(0 0 0 100%)}`. Switch the JS to `fromTo`. Add the failsafe `animation:ph-show 0s 2.5s forwards`. *Risk:* if GSAP fails, content shows at 2.5 s. Without JS the page is unaffected.

**2. Home pinned projects: the handover still ghosts.** At pin +300 px and +1,100 px (`home-pin-03`, `-12`), the outgoing title sits at about 35% while its list stays at full strength. The incoming device is a translucent white slab at about 40%. *Fix:* take opacity out of both. Devices: outgoing `yPercent:-120`, 0.3, `power3.in`; incoming `120→0`, 0.5, `power4.out`, starting at `at+0.35` with no overlap. Copy: put each child in an `overflow:hidden` mask and move `yPercent 0→-105` out and `105→0` in, 0.22 each, as one group. Raise `PIN_VIEWPORTS` to 2.5 so each project holds still for about 0.5 vh. *Risk:* none.

**3. Page openings do not match.** Home's H1 rises line by line through masks. Inner pages fade the whole H1 through about 250 ms of 50% grey. About, the inner page with a photo hero, has no opening at all. *Fix:* emit `.ln > span` line wrappers on inner H1s and reuse the home recipe (`yPercent:108`, 0.8 s, stagger 0.08, `power4.out`, copy at 0.35 s). On About, add `data-ph`: the three photos un-mask `inset(100% 0 0 0)→0` with stagger 0.12 and `img` 1.08→1. Trim the first-visit intro so the wipe starts at 0.8 s (not 1.05 s) and the hero at 1.0 s. The H1 is then readable at about 1.7 s. *Risk:* none.

**4. Home "What we do": the active row is invisible, and the panel follows hover only.** All three headings are full bone. A visitor who scrolls past without hovering always sees photo 1. *Fix:* at ≥1081 px, also activate rows on scroll (one ScrollTrigger per row, `start:'top 55%'`, `end:'bottom 55%'`). Set inactive `h3` to `color-mix(in oklab,var(--bone) 55%,var(--ink))`, keeping ≥3:1, and active to bone, over 300 ms. Replace the opacity swap with the pin's wipe: `inset(100% 0 0 0)→0`, 600 ms, `img` 1.06→1. Swap Care plan's flat daylight `garden-wall` for `garden-deck` (`50% 60%`). *Risk:* keep `:focus-within` activation and keep the panel `aria-hidden`.

**5. The pin releases with a hard cut into the bone "Same business" section.** The dark film snaps to full bone just before the best conversion moment. *Fix:* add a 0.35-unit exit to the timeline: the Fade & Co photo scales 1→1.04 while a bone layer wipes up (`power4.inOut`), so the unpin lands on the next section's colour. *Risk:* none. Mark the layer `aria-hidden`.

**6. Services repeats one chapter template three times and uses `trade-panel` twice.** Each chapter is photo, title, ruled list, then a big photo. `trade-panel` is both New website's image and the closing CTA. *Fix:* the CTA uses `garden-path` (`50% 60%`, 30% brightness). Care plan becomes one full-bleed dark band: four monthly tasks in one row, no photo. *Risk:* none.

## Broken or minor
- `garden-lawn` is used on Home and closes both Work and About.
- The 28 px fade-up `data-rise` on every heading is the generic default. Once #2–#4 land, drop it below the fold.

## Verdict
In stills, Cendavo reads as a confident, honest studio site: the type, grade, real photography and labelling would pass an agency review. The motion does not yet match. The ideas are right: one intro, masked lines, a pinned project film. But at the moments that matter the execution falls back on opacity crossfades, and inner pages flash before they animate. Elite studios are judged on exactly those handover frames. With #1 and #2 fixed, the site is credible for an award shortlist.
