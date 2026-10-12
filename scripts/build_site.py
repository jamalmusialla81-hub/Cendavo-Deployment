#!/usr/bin/env python3
"""Build the zero-dependency Cloudflare Pages static site."""
from html import escape
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
# Footer signature (Night Shift Task 18): an oversized, low-contrast wordmark cropped by the bottom of the page. It is
# decorative and hidden from assistive technology (the footer's text logo already names the business). The page's
# closing call-to-action band carries the consultation button, so the footer no longer repeats it.
FOOTER_SIGNATURE = '<div class="footer-sign" aria-hidden="true"><span class="footer-word">CENDAVO</span></div>'
NAV = [('Home', '/'), ('Work', '/work/'), ('Services', '/services/'), ('Pricing', '/pricing/'), ('Demo project', '/demo/'), ('About', '/about/'), ('Contact', '/contact/')]
# Links left out of the desktop header row (CSS, 1081px+) but kept in the mobile menu and the footer (Night Shift Task 16).
HEADER_OPTIONAL = {'/demo/'}
# Page-specific scripts: each is loaded only on the page that uses it.
# Page-specific stylesheets: the homepage's sections and device mockups (home.css) load only on /;
# every inner page loads the shared inner-page stylesheet (pages.css) instead. The mockup kit (kit.css: device frames,
# concept mini-sites and the quote sheet) loads, before the page stylesheet, only on the pages that show mockups.
PAGE_STYLES = {'index': '<link rel="stylesheet" href="/assets/home.css">'}
INNER_STYLE = '<link rel="stylesheet" href="/assets/pages.css">'
# Services loads it too (Task 29): its two social videos sit in the kit's phone frame.
KIT_PAGES = ('index', 'work', 'services', 'pricing')
KIT_STYLE = '<link rel="stylesheet" href="/assets/kit.css">'


def page_styles(key):
    return (KIT_STYLE if key in KIT_PAGES else '') + PAGE_STYLES.get(key, INNER_STYLE)
# Motion (Night Shift Task 10). GSAP 3.13 (vendored in /assets/vendor/gsap/, GSAP Standard "No Charge" License; see
# LICENSE.txt there) loads, deferred, only on the pages that animate: GSAP, then ScrollTrigger, then motion.js (shared
# reveals), then details.js (card tilt, cursor ring, step count-up; Task 29), then reel.js (the shared silent-video
# controller) on the pages with video, then home.js on /. Those pages also load motion-boot.js in <head> (external, not
# deferred) to set the .js/.motion classes before first paint; only the homepage's tag carries data-intro, which allows the
# first-visit intro. Pricing and About reuse the shared scripts only. Contact (the enquiry form) and Demo (the browser app)
# load no GSAP and no motion scripts.
MOTION_PAGES = ('index', 'work', 'services', 'pricing', 'about')
GSAP = '<script src="/assets/vendor/gsap/gsap.min.js" defer></script><script src="/assets/vendor/gsap/ScrollTrigger.min.js" defer></script><script src="/assets/motion.js" defer></script><script src="/assets/details.js" defer></script>'
REEL = '<script src="/assets/reel.js" defer></script>'
PAGE_SCRIPTS = {'index': GSAP + REEL + '<script src="/assets/home.js" defer></script>', 'work': GSAP + REEL, 'services': GSAP + REEL, 'pricing': GSAP, 'about': GSAP, 'demo': '<script src="/assets/demo.js" defer></script>', 'contact': '<script src="/assets/enquiry.js" defer></script>'}


def boot_script(key):
    if key not in MOTION_PAGES:
        return ''
    return '<script src="/assets/motion-boot.js"' + (' data-intro' if key == 'index' else '') + '></script>'


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


IMG_TAG = re.compile(r'<img\b[^>]*>')


def with_avif(page):
    """Wrap every photo in <picture> with an AVIF source ahead of the unchanged JPEG <img> fallback.

    The AVIF srcset is the img's srcset with .jpg swapped for .avif, and sizes is copied as is, so browsers pick the same
    width either way. The build stops if a photo has no srcset/sizes or an AVIF file is missing."""
    def wrap(match):
        tag = match.group(0)
        srcset, sizes = re.search(r'\ssrcset="([^"]+)"', tag), re.search(r'\ssizes="([^"]+)"', tag)
        if not (srcset and sizes):
            raise ValueError(f'image needs srcset and sizes for its AVIF source: {tag[:100]}')
        avif = srcset.group(1).replace('.jpg', '.avif')
        for url in re.findall(r'(\S+)\s+\d+w', avif):
            if not url.startswith('/assets/images/') or not (ROOT / url.lstrip('/')).is_file():
                raise FileNotFoundError(f'missing AVIF image: {url}')
        return f'<picture><source type="image/avif" srcset="{avif}" sizes="{sizes.group(1)}">{tag}</picture>'
    return IMG_TAG.sub(wrap, page)


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / 'assets', OUT / 'assets')
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
        html = f'''<!doctype html><html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><meta name="theme-color" content="#0E0E0D"><meta name="description" content="{desc}"><title>{title}</title>{head_meta(key, title, desc)}<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="preload" href="/assets/fonts/archivo-var-latin.woff2" as="font" type="font/woff2" crossorigin><link rel="stylesheet" href="/assets/site.css">{page_styles(key)}{boot_script(key)}</head><body><a class="skip-link" href="#main">Skip to main content</a><header class="site-header"><div class="wrap nav"><a class="brand" href="/" aria-label="Cendavo home">{MARK}CENDAVO</a><button class="menu" type="button" data-menu aria-label="Toggle menu" aria-controls="site-nav" aria-expanded="false"><span aria-hidden="true">☰</span></button><nav class="nav-links" id="site-nav" data-nav aria-label="Main navigation">{header_links}</nav><a class="button small" href="/contact/">Request a free consultation</a></div></header><main id="main" tabindex="-1">{page}</main><footer class="footer"><div class="wrap"><div class="footer-row"><div><a class="brand" href="/">{MARK}CENDAVO</a><p>Website design, redesign and care for local service businesses.<br>Sydney, Australia.<br>{MAIL_LINK}</p></div><nav class="footer-links" aria-label="Footer navigation">{links}</nav></div><div class="footer-bottom"><p>© 2026 Cendavo. The demonstration project uses sample data only.</p><p>Harbourside Mobile Detailing, Greenline Landscapes and Fade &amp; Co are fictional concept businesses.</p></div></div>{FOOTER_SIGNATURE}</footer><script src="/assets/site.js" defer></script>{PAGE_SCRIPTS.get(key, '')}</body></html>'''
        if '{{' in html:
            raise ValueError(f'unreplaced placeholder in {source.name}')
        dest = OUT / ('index.html' if key == 'index' else '404.html' if key == NOT_FOUND else f'{key}/index.html')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html)
    (OUT / '_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: DENY\n  Content-Security-Policy: default-src \'self\'; script-src \'self\'; style-src \'self\'; font-src \'self\'; img-src \'self\' data:; connect-src \'self\'; object-src \'none\'; base-uri \'self\'; frame-ancestors \'none\'\n')
    (OUT / 'robots.txt').write_text('User-agent: *\nAllow: /\n')
    (OUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{BASE_URL}{href}</loc></url>' for _,href in NAV) + '</urlset>')
    print(f'Built {len(list((ROOT / "pages").glob("*.html")))} pages in {OUT}')


if __name__ == '__main__':
    build()
