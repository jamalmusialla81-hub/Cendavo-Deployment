#!/usr/bin/env python3
"""Build the zero-dependency Cloudflare Pages static site."""
from datetime import date
from html import escape
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
# The live site's origin: canonical URLs, Open Graph URLs and the sitemap are all built from this one constant.
BASE_URL = 'https://cendavo-deployment.pages.dev'
SHARE_IMAGE = '/assets/social/cendavo-og.jpg'  # 1200×630 share card
# The public business address (owner-provided, Night Shift Task 31). The one Python copy: the footer uses it directly and
# page fragments write the CONTACT_TOKEN placeholder, replaced at build time. assets/enquiry.js and functions/api/enquiry.js
# each hold their own CONTACT_EMAIL constant; tests check all three match.
CONTACT_EMAIL = 'cendavo.au@gmail.com'
CONTACT_TOKEN = '{{CONTACT_EMAIL}}'
MAIL_LINK = f'<a class="mail" href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>'
SHARE_IMAGE_ALT = 'Websites for Sydney’s local service businesses. The Cendavo logo and a Request a free consultation button.'
TITLES = {'index': 'Cendavo — Website design for Sydney’s local service businesses', 'work': 'Work — Cendavo', 'services': 'Services — Cendavo', 'pricing': 'Pricing — Cendavo', 'demo': 'Demo project — Cendavo', 'about': 'About — Cendavo', 'contact': 'Contact — Cendavo', '404': 'Page not found — Cendavo'}
DESCRIPTIONS = {'index': 'Cendavo designs, builds, redesigns and looks after websites for local service businesses in Sydney.', 'work': 'Concept projects by Cendavo: three fictional Sydney service businesses, designed the way we would design yours.', 'services': 'New websites, redesigns and care plans for local service businesses in Sydney, from Cendavo.', 'pricing': 'How Cendavo prices websites: a fixed quote after a free consultation, what every project includes and what affects the quote.', 'demo': 'A Cendavo demonstration project that runs in your browser with sample data only.', 'about': 'About Cendavo, a small Sydney studio that designs, builds and looks after websites for local service businesses: how we think, what you can expect and how we build.', 'contact': 'Request a website design, redesign or maintenance consultation with Cendavo in Sydney.', '404': 'This page could not be found on the Cendavo website.'}
# The 404 page is built to dist/404.html (Cloudflare Pages serves it, with a 404 status, for unknown URLs). It is not in
# NAV or the sitemap, carries noindex and no canonical or sharing metadata.
NOT_FOUND = '404'
# Brand mark: three arcs forming a C (first arc amber via CSS). Inline SVG, decorative.
MARK = '<svg class="mark" viewBox="0 0 200 200" aria-hidden="true" focusable="false"><path d="M55.67 43.26C86.24 19.38 130.22 24.01 155.16 53.72L135.24 70.43C119.31 51.45 91.21 48.5 71.68 63.75Z"/><path d="M48.21 150.02C21.26 122.11 21.26 77.89 48.21 49.98L66.91 68.05C49.7 85.87 49.7 114.13 66.91 131.95Z"/><path d="M155.16 146.28C130.22 175.99 86.24 180.62 55.67 156.74L71.68 136.25C91.21 151.5 119.31 148.55 135.24 129.57Z"/></svg>'
# Footer signature (Night Shift Task 18; light in Daylight, Task 33): an oversized, low-contrast wordmark cropped by the bottom of the page. It is
# decorative and hidden from assistive technology (the footer's text logo already names the business). The page's
# closing call-to-action band carries the consultation button, so the footer no longer repeats it.
FOOTER_SIGNATURE = '<div class="footer-sign" aria-hidden="true"><span class="footer-word">CENDAVO</span></div>'
NAV = [('Home', '/'), ('Work', '/work/'), ('Services', '/services/'), ('Pricing', '/pricing/'), ('Demo project', '/demo/'), ('About', '/about/'), ('Contact', '/contact/')]
# Links left out of the desktop header row (CSS, 1081px+) but kept in the mobile menu and the footer (Night Shift Task 16).
HEADER_OPTIONAL = {'/demo/'}
# Page-specific scripts: each is loaded only on the page that uses it.
# Page-specific stylesheets: the homepage's sections and device mockups (home.css) load only on /. Every inner page loads
# the shared Daylight inner-page stylesheet (pages.css: page hero, sections, questions, closing band, Contact, Demo, 404),
# and Work, Services, Pricing and About add their own sheet after it (Task 34). The mockup kit (kit.css: the homepage's
# "after" mini-site, the device bench that plays the concept loops and the social-clip phone frame) loads, before the page
# stylesheets, only on the pages that show those.
PAGE_STYLES = {'index': '<link rel="stylesheet" href="/assets/home.css">'}
INNER_STYLE = '<link rel="stylesheet" href="/assets/pages.css">'
OWN_STYLE = ('work', 'services', 'pricing', 'about')
KIT_PAGES = ('index', 'work', 'services')
KIT_STYLE = '<link rel="stylesheet" href="/assets/kit.css">'


def page_styles(key):
    own = f'<link rel="stylesheet" href="/assets/{key}.css">' if key in OWN_STYLE else ''
    return (KIT_STYLE if key in KIT_PAGES else '') + PAGE_STYLES.get(key, INNER_STYLE + own)
# Motion (Night Shift Task 10). GSAP 3.13 (vendored in /assets/vendor/gsap/, GSAP Standard "No Charge" License; see
# LICENSE.txt there) loads, deferred, only on the pages that animate: GSAP, then ScrollTrigger, then motion.js (shared
# openings and reveals), then scenes.js on the inner motion pages, then reel.js (the one silent-video controller) on the
# pages with video (Pricing since Task 41, for its closing panel's ambient loop), then home.js on / (which, since Liquid
# Glass, Task 37, replaces motion.js there: see GSAP_ONLY). No
# page loads details.js since Daylight (Task 34): the motion rules allow no
# decorative rotation, so cards neither tilt nor get a cursor ring. These pages also load motion-boot.js in <head>
# (external, not deferred) to set the .js/.motion classes before first paint. Contact (the enquiry form), Demo (the
# browser app) and the 404 page load no GSAP and no motion scripts.
MOTION_PAGES = ('index', 'work', 'services', 'pricing', 'about')
# Task 59: the homepage hero's still (the LCP on phones) is a CSS background on .hero-gl, found only once home.css has
# loaded. One high-priority preload per poster starts it with the HTML instead. The media queries mirror home.css exactly
# (the phone poster at max-width:760px unless max-height:500px puts the wide one back), so a screen preloads only the
# poster it shows: no extra request.
HERO_POSTERS = (('/assets/glass/hero-glass-poster-m.jpg', '(max-width: 760px) and (min-height: 501px)'),
                ('/assets/glass/hero-glass-poster.jpg', '(min-width: 761px), (max-height: 500px)'))
HERO_PRELOAD = ''.join(f'<link rel="preload" href="{url}" as="image" media="{media}" fetchpriority="high">' for url, media in HERO_POSTERS)
GSAP_CORE = '<script src="/assets/vendor/gsap/gsap.min.js" defer></script><script src="/assets/vendor/gsap/ScrollTrigger.min.js" defer></script><script src="/assets/motion.js" defer></script>'
# The inner motion pages add scenes.js (Task 34: device benches, drawn lines, the Services vignettes, the Work queue and the
# film frame) after motion.js; the homepage does not need it, which keeps its first-party script within the 30 KB budget.
SCENES = '<script src="/assets/scenes.js" defer></script>'
REEL = '<script src="/assets/reel.js" defer></script>'
# Liquid Glass (Task 37): the homepage runs its own motion in home.js (headings, cards, the hero exit), so it no longer
# loads motion.js; that keeps it inside the 30 KB first-party script budget with the glass shell and the WebGL boot.
GSAP_ONLY = '<script src="/assets/vendor/gsap/gsap.min.js" defer></script><script src="/assets/vendor/gsap/ScrollTrigger.min.js" defer></script>'
PAGE_SCRIPTS = {'index': GSAP_ONLY + REEL + '<script src="/assets/home.js" defer></script>', 'work': GSAP_CORE + SCENES + REEL,
                'services': GSAP_CORE + SCENES + REEL, 'pricing': GSAP_CORE + SCENES + REEL, 'about': GSAP_CORE + SCENES + REEL,
                'demo': '<script src="/assets/demo.js" defer></script>', 'contact': '<script src="/assets/enquiry.js" defer></script>'}


# Liquid Glass shell (Task 37). Every page loads glass.css after site.css (glass nav pill, colour-field atmosphere, glass
# panels, glass footer) and the small shell in site.js (menu, nav hide/show). The motion pages add Lenis smooth scrolling
# and glass.js (pointer light, Chromium edge refraction, the drifting atmosphere), after their page scripts; Contact, Demo
# and the 404 page do not (the form, the demo app and plain scrolling stay as they are). The homepage, Work, Services,
# Pricing, About and Contact load glass-boot.js, which decides after load and idle whether to import the WebGL hero
# (assets/glass-scene.js on the homepage, the inner-page scene assets/glass-page.js elsewhere, Tasks 39 and 40). On Contact
# it is the only addition: no Lenis, no glass.js, and the form and enquiry.js are untouched.
GLASS_STYLE = '<link rel="stylesheet" href="/assets/glass.css">'
ATMOSPHERE = '<div class="atmos" aria-hidden="true"><i></i><i></i><i></i><i></i></div>'
GLASS_MOTION = '<script src="/assets/vendor/lenis/lenis.min.js" defer></script><script src="/assets/glass.js" defer></script>'
GLASS_BOOT = '<script src="/assets/glass-boot.js" defer></script>'
# Where glass.js builds its SVG displacement filters (Chromium only); empty and invisible otherwise.
GLASS_DEFS = '<svg class="lg-defs" width="0" height="0" aria-hidden="true" focusable="false"><defs data-lg-defs></defs></svg>'
# First-party classic scripts ship without whole-line comments and indentation (see strip_js). ES modules are copied as is:
# the two WebGL scenes and, since Task 48, glass-shapes.js, the helpers they share (so the inner pages never fetch
# glass-scene.js or three's SVGLoader and BufferGeometryUtils).
STRIP_SKIP = {'glass-scene.js', 'glass-page.js', 'glass-shapes.js'}
GL_PAGES = ('index', 'work', 'services', 'pricing', 'about', 'contact')
# Pause motion (Task 41, WCAG 2.2.2): every page with ongoing motion (the WebGL scene, the drifting atmosphere, the marquee,
# video loops) gets one button. Task 46: it sits in the header's glass pill (after the logo, before the menu button), so it
# can never cover page content; glass.css styles it. site.js reveals and drives it; it stays hidden without JavaScript,
# when nothing moves either. Demo and the 404 page have no ongoing motion. Task 59 (owner-mandated): site.js switches its
# visible name to "Play motion" while paused and sets aria-pressed with it; the icon follows aria-pressed (pause bars, then
# a play triangle). It ships in the running state: "Pause motion", aria-pressed="false".
MOTION_TOGGLE = '<button class="motion-btn" type="button" data-motion-toggle aria-pressed="false" hidden>Pause motion</button>'


def strip_js(text):
    """Remove whole-line // comments, /* */ comment blocks that start a line, blank lines and indentation.

    Only applied to scripts without template literals, so no string can span lines; code is never reordered or rewritten."""
    out, in_block = [], False
    for line in text.splitlines():
        s = line.strip()
        if in_block:
            if '*/' not in s:
                continue
            in_block, s = False, s.split('*/', 1)[1].strip()
        elif s.startswith('/*'):
            if '*/' not in s:
                in_block = True
                continue
            s = s.split('*/', 1)[1].strip()
        if s and not s.startswith('//'):
            out.append(s)
    return '\n'.join(out) + '\n'


def shell_scripts(key):
    return (GLASS_MOTION if key in MOTION_PAGES else '') + (GLASS_BOOT if key in GL_PAGES else '')


def boot_script(key):
    return '<script src="/assets/motion-boot.js"></script>' if key in MOTION_PAGES else ''


def route_path(key):
    return '/' if key == 'index' else f'/{key}/'


def head_meta(key, title, desc):
    """Canonical and sharing metadata for a public page; the 404 page gets noindex instead."""
    if key == NOT_FOUND:
        return '<meta name="robots" content="noindex">'
    url = BASE_URL + route_path(key)
    meta = [f'<link rel="canonical" href="{url}">']
    for name, value in (('og:type', 'website'), ('og:site_name', 'Cendavo'), ('og:title', title), ('og:description', desc),
                        ('og:url', url), ('og:image', BASE_URL + SHARE_IMAGE), ('og:image:width', '1200'),
                        ('og:image:height', '630'), ('og:image:alt', SHARE_IMAGE_ALT)):
        meta.append(f'<meta property="{name}" content="{escape(value)}">')
    meta.append('<meta name="twitter:card" content="summary_large_image">')
    return ''.join(meta)


def structured_data():
    """The homepage's schema.org identity (Night Shift Task 49), built only from the constants above.

    Deliberately minimal: no address, telephone, founder, ratings, reviews or sameAs links, and the fictional concept
    projects never appear in it. json.dumps output with every '<' escaped can never close the script element early; the
    browser treats application/ld+json as data and never runs it, so the CSP's script-src 'self' still applies."""
    data = {'@context': 'https://schema.org', '@type': 'ProfessionalService', 'name': 'Cendavo', 'url': BASE_URL + '/',
            'email': CONTACT_EMAIL, 'description': DESCRIPTIONS['index'],
            'areaServed': {'@type': 'City', 'name': 'Sydney, NSW, Australia'},
            'serviceType': ['Website design', 'Website redesign', 'Website care']}
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace('<', '\\u003c') + '</script>'


# Security headers. HSTS stays without includeSubDomains or preload: both are hard to undo once a custom domain is chosen.
HEADERS = ("/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: DENY\n"
           "  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
           "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'\n"
           "  Strict-Transport-Security: max-age=31536000\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
           # Task 62: cold-call previews stay out of search. Cloudflare Pages applies every matching block, so the /* rules
           # above (the CSP included) still apply to them.
           "/preview/*\n  X-Robots-Tag: noindex, nofollow\n")
# Task 62: cold-call previews (previews/<slug>/, complete concept sites for one prospect each) are published at
# /preview/<slug>/. robots.txt disallows the path, _headers adds noindex, and the sitemap lists only NAV.
PREVIEW_SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def copy_previews(src, dest):
    """Copy each folder directly inside src to dest/<slug>/ byte for byte (no stripping, <picture> wrapping or template).

    Files at the top level (README.md), hidden files and folders, and symlinks (anywhere) are skipped, so a stray link can
    never publish files from outside the repository. Folder names must be lowercase slugs. dest is created only when
    there is at least one preview."""
    if not src.is_dir():
        return []
    slugs = []
    for entry in sorted(src.iterdir()):
        if entry.name.startswith('.') or entry.is_symlink() or not entry.is_dir():
            continue
        if not PREVIEW_SLUG.match(entry.name):
            raise ValueError(f'preview folder name must be a lowercase slug (a-z, 0-9, hyphens): {entry.name!r}')
        slugs.append(entry.name)

    def skipped(folder, names):
        return {name for name in names if name.startswith('.') or Path(folder, name).is_symlink()}
    for slug in slugs:
        shutil.copytree(src / slug, dest / slug, ignore=skipped)
    return slugs


IMG_TAG = re.compile(r'<img\b[^>]*>')
# Task 59: phones (up to 640 CSS px wide) get only the 800w AVIF. A DPR3 phone multiplies every sizes width by 3 (a 320px
# marquee tile wants 960 device pixels), so with the 1600w file on offer it always took that; 800w is about 2x density
# there, sharp enough, and half the bytes or less. Tablets and desktops keep the full srcset.
PHONE_MEDIA = '(max-width: 640px)'


def with_avif(page):
    """Wrap every photo in <picture> with AVIF sources ahead of the unchanged JPEG <img> fallback.

    The AVIF srcset is the img's srcset with .jpg swapped for .avif, and sizes is copied as is, so browsers pick the same
    width either way. When the srcset offers more than the 800w file, a phone-only AVIF source listing just the 800w file
    comes first (PHONE_MEDIA). The build stops if a photo has no srcset/sizes or an AVIF file is missing."""
    def wrap(match):
        tag = match.group(0)
        srcset, sizes = re.search(r'\ssrcset="([^"]+)"', tag), re.search(r'\ssizes="([^"]+)"', tag)
        if not (srcset and sizes):
            raise ValueError(f'image needs srcset and sizes for its AVIF source: {tag[:100]}')
        avif = srcset.group(1).replace('.jpg', '.avif')
        candidates = re.findall(r'(\S+)\s+(\d+)w', avif)
        for url, _ in candidates:
            if not url.startswith('/assets/images/') or not (ROOT / url.lstrip('/')).is_file():
                raise FileNotFoundError(f'missing AVIF image: {url}')
        small = [url for url, width in candidates if width == '800']
        if not small:
            raise ValueError(f'image needs an 800w file for phones: {tag[:100]}')
        phone = ''
        if len(candidates) > 1:
            phone = f'<source type="image/avif" media="{PHONE_MEDIA}" srcset="{small[0]} 800w" sizes="{sizes.group(1)}">'
        return f'<picture>{phone}<source type="image/avif" srcset="{avif}" sizes="{sizes.group(1)}">{tag}</picture>'
    return IMG_TAG.sub(wrap, page)


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / 'assets', OUT / 'assets')
    for script in (OUT / 'assets').glob('*.js'):
        text = script.read_text()
        if script.name not in STRIP_SKIP and '`' not in text:
            script.write_text(strip_js(text))
    for source in (ROOT / 'pages').glob('*.html'):
        key = source.stem
        title, desc = TITLES[key], DESCRIPTIONS[key]
        page = with_avif(source.read_text()).replace(CONTACT_TOKEN, CONTACT_EMAIL)
        links = header_links = ''
        for label, href in NAV:
            current = ' aria-current="page"' if (key == 'index' and href == '/') or href == f'/{key}/' else ''
            links += f'<a href="{href}"{current}>{label}</a>'
            # The header nav is also the mobile menu; site.css hides HEADER_OPTIONAL links only at 1081px+ so the
            # desktop row fits without wrapping. The footer keeps every link.
            optional = ' class="nav-optional"' if href in HEADER_OPTIONAL else ''
            header_links += f'<a{optional} href="{href}"{current}>{label}</a>'
        html = f'''<!doctype html><html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="theme-color" content="#FFFFFF"><meta name="description" content="{desc}"><title>{title}</title>{head_meta(key, title, desc)}<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="preload" href="/assets/fonts/archivo-var-latin.woff2" as="font" type="font/woff2" crossorigin>{HERO_PRELOAD if key == 'index' else ''}<link rel="stylesheet" href="/assets/site.css">{GLASS_STYLE}{page_styles(key)}{boot_script(key)}{structured_data() if key == 'index' else ''}</head><body><a class="skip-link" href="#main">Skip to main content</a>{ATMOSPHERE}<header class="site-header"><div class="wrap nav"><a class="brand" href="/" aria-label="Cendavo home">{MARK}CENDAVO</a>{MOTION_TOGGLE if key in GL_PAGES else ''}<button class="menu" type="button" data-menu aria-label="Toggle menu" aria-controls="site-nav" aria-expanded="false"><span aria-hidden="true">☰</span></button><nav class="nav-links" id="site-nav" data-nav aria-label="Main navigation">{header_links}</nav><a class="button small" href="/contact/">Request a free consultation</a></div></header><main id="main" tabindex="-1">{page}</main><footer class="footer"><div class="wrap"><div class="footer-row"><div><a class="brand" href="/">{MARK}CENDAVO</a><p>Website design, redesign and care for local service businesses.<br>Sydney, Australia.<br>{MAIL_LINK}</p></div><nav class="footer-links" aria-label="Footer navigation">{links}</nav></div><div class="footer-bottom"><p>© 2026 Cendavo. The demonstration project uses sample data only.</p><p>Harbourside Mobile Detailing, Greenline Landscapes and Fade &amp; Co are fictional concept businesses.</p></div></div>{FOOTER_SIGNATURE}</footer><script src="/assets/site.js" defer></script>{PAGE_SCRIPTS.get(key, '')}{shell_scripts(key)}{GLASS_DEFS if key in MOTION_PAGES else ''}</body></html>'''
        if '{{' in html:
            raise ValueError(f'unreplaced placeholder in {source.name}')
        dest = OUT / ('index.html' if key == 'index' else '404.html' if key == NOT_FOUND else f'{key}/index.html')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html)
    copy_previews(ROOT / 'previews', OUT / 'preview')
    (OUT / '_headers').write_text(HEADERS)
    (OUT / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nDisallow: /preview/\nSitemap: {BASE_URL}/sitemap.xml\n')
    # lastmod is the build date: every page is rebuilt on every deploy.
    lastmod = date.today().isoformat()
    (OUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{BASE_URL}{href}</loc><lastmod>{lastmod}</lastmod></url>' for _, href in NAV) + '</urlset>')
    print(f'Built {len(list((ROOT / "pages").glob("*.html")))} pages in {OUT}')


if __name__ == '__main__':
    build()
