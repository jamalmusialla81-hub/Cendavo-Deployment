# Cendavo design references

## TikTok "vibe coding / premium website design" transcript

**Not found.** A Spotlight search of the home folder and a check of the Codex conversation workspaces found only one transcript (`~/Documents/Codex/2026-09-14/…/work/transcript.jsonl`), and it is an unrelated video-compositing tutorial. No recommendations are attributed to the TikTok source here. If you can export the transcript (text file or screenshot), add it to `docs/` and this file should be completed from it.

## Verified design tooling (2026-10-11)

| Tool | Status | Use for Cendavo | Cost / licensing |
| --- | --- | --- | --- |
| `insane-web-design` Claude plugin (skills: awwwards, animation-forge, awwwards-3d, scroll-world, threejs-animation, shader-glsl, particle-system) | Enabled; Forge passes it to Strategist and Builder for frontend tasks | Visual direction, typography/layout critique, motion patterns | Local skills, no hooks or MCP servers; no cost |
| `frontend-design`, `ui-ux-pro-max` skills (supervisor session) | Available to Claude Code, not to Forge agents | Supervisor design review | No cost |
| Built-in browser (Claude desktop) | Available | Before/after screenshots at desktop and 375 px mobile | No cost |
| `scroll-world` skill | Present, **not used** | Needs paid Higgsfield/Monid video generation | Paid; not approved |

## Constraints that shape technique choices

- CSP `script-src 'self'`: no CDN libraries (GSAP/Three.js would have to be vendored and justified).
- `site` profile has no network: no new packages in task B.
- No stock footage or paid video. A hero "website reel" must be built from CSS/SVG mockups or real screenshots of Cendavo's own demo project until real client work exists.
- Every animation needs a `prefers-reduced-motion` fallback.

## Before screenshots (current admin-platform site)

Taken 2026-10-11 from `dist/` at 1280 px and 375 px: green SaaS-style layout, headline "Less admin. More room to grow.", product-demo CTA, contact page with a "Prepare my brief" form that sends nothing. Kept in the supervisor session for comparison with the redesign.
