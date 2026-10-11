# Cendavo test results — Night Shift run (2026-10-11 → 12)

All checks run by the supervisor (Claude Code) independently of Forge's own gates.

| Check | Command / method | Result on frozen commit 2c99099 |
| --- | --- | --- |
| Unit and integration tests | `python3 -m unittest discover -s tests` (on a clean `git archive` export) | **343 ran, OK (4 skipped)** |
| JS syntax | `node --check assets/*.js` | pass |
| Build | `python3 scripts/build_site.py` | 8 pages built |
| Rendered layout | Playwright + installed Chrome, full-page captures of 8 pages at 1440×900 and 390×844 | 0 px horizontal overflow, 0 console errors on all 16 |
| Keyboard focus | Tab through every page (reduced motion) | every focus stop has a visible indicator (137 stops) |
| Text contrast | computed WCAG ratio for text on solid backgrounds | 0 failures |
| Performance (local) | Playwright, first load | desktop 503 KB, mobile 357 KB initial; CLS 0.000; first-visit LCP 0.10 s (hero photo); hero headline visible (verified by screenshot and computed transform after Task 27) |
| Flash of content | Chrome screencast frames (~16 ms) + headline-region luminance on Work/Services/Pricing/About | no visible-then-hidden frames; first frame is dark |
| Motion | timed frames of intro/hero/pinned projects; reduced-motion pass | intro ≤ 1.8 s and skippable; pin 2.5 viewports with "Skip projects"; reduced motion hides nothing |
| Enquiry backend | Node harness against `functions/api/enquiry.js` with a fake D1 | valid 201, idempotent retry 200 (1 row), invalid 400, honeypot silent 200 (0 rows), too fast 429 (0 rows), cross-site 403, no DB 503, GET 405 |

Test count grew from 202 (start of the trial) to 343 through Forge tasks 4–27.
