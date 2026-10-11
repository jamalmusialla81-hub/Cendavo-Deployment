#!/usr/bin/env python3
"""Build the zero-dependency Cloudflare Pages static site."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
# Brand mark: three arcs forming a C (first arc amber via CSS). Inline SVG, decorative.
MARK = '<svg class="mark" viewBox="0 0 200 200" aria-hidden="true" focusable="false"><path d="M55.67 43.26C86.24 19.38 130.22 24.01 155.16 53.72L135.24 70.43C119.31 51.45 91.21 48.5 71.68 63.75Z"/><path d="M48.21 150.02C21.26 122.11 21.26 77.89 48.21 49.98L66.91 68.05C49.7 85.87 49.7 114.13 66.91 131.95Z"/><path d="M155.16 146.28C130.22 175.99 86.24 180.62 55.67 156.74L71.68 136.25C91.21 151.5 119.31 148.55 135.24 129.57Z"/></svg>'
NAV = [('Home', '/'), ('Services', '/services/'), ('Pricing', '/pricing/'), ('Demo project', '/demo/'), ('Contact', '/contact/')]
# Page-specific scripts: each is loaded only on the page that uses it.
# Page-specific stylesheet: the homepage's sections and device mockups load only on /.
PAGE_STYLES = {'index': '<link rel="stylesheet" href="/assets/home.css">'}
# GSAP 3.13 (vendored in /assets/vendor/gsap/, GSAP Standard "No Charge" License; see LICENSE.txt there) loads only on the homepage, before home.js.
PAGE_SCRIPTS = {'index': '<script src="/assets/vendor/gsap/gsap.min.js" defer></script><script src="/assets/vendor/gsap/ScrollTrigger.min.js" defer></script><script src="/assets/home.js" defer></script>', 'demo': '<script src="/assets/demo.js" defer></script>', 'contact': '<script src="/assets/enquiry.js" defer></script>'}


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / 'assets', OUT / 'assets')
    for source in (ROOT / 'pages').glob('*.html'):
        key = source.stem
        title = {'index': 'Cendavo — Website design for Sydney’s local service businesses', 'services': 'Services — Cendavo', 'pricing': 'Pricing — Cendavo', 'demo': 'Demo project — Cendavo', 'contact': 'Contact — Cendavo'}[key]
        desc = {'index': 'Cendavo designs, builds, redesigns and looks after websites for local service businesses in Sydney.', 'services': 'Explore Cendavo services for local businesses.', 'pricing': 'Explore Cendavo pricing hypotheses and pilot options.', 'demo': 'A Cendavo demonstration project that runs in your browser with sample data only.', 'contact': 'Request a website design, redesign or maintenance consultation with Cendavo in Sydney.'}[key]
        page = source.read_text()
        links = ''
        for label, href in NAV:
            current = ' aria-current="page"' if (key == 'index' and href == '/') or href == f'/{key}/' else ''
            links += f'<a href="{href}"{current}>{label}</a>'
        html = f'''<!doctype html><html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0E0E0D"><meta name="description" content="{desc}"><title>{title}</title><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="preload" href="/assets/fonts/archivo-var-latin.woff2" as="font" type="font/woff2" crossorigin><link rel="stylesheet" href="/assets/site.css">{PAGE_STYLES.get(key, '')}</head><body><a class="skip-link" href="#main">Skip to main content</a><header class="site-header"><div class="wrap nav"><a class="brand" href="/" aria-label="Cendavo home">{MARK}CENDAVO</a><button class="menu" type="button" data-menu aria-label="Toggle menu" aria-controls="site-nav" aria-expanded="false"><span aria-hidden="true">☰</span></button><nav class="nav-links" id="site-nav" data-nav aria-label="Main navigation">{links}</nav><a class="button small" href="/contact/">Request a free consultation</a></div></header><main id="main" tabindex="-1">{page}</main><footer class="footer"><div class="wrap"><div class="footer-row"><div><a class="brand" href="/">{MARK}CENDAVO</a><p>Website design, redesign and care for local service businesses.<br>Sydney, Australia.</p></div><nav class="footer-links" aria-label="Footer navigation">{links}</nav><a class="button outline" href="/contact/">Request a free consultation</a></div><div class="footer-bottom"><p>© 2026 Cendavo. The demonstration project uses sample data only.</p><p>Harbourside Mobile Detailing, Greenline Landscapes and Fade &amp; Co are fictional concept businesses.</p></div></div></footer><script src="/assets/site.js" defer></script>{PAGE_SCRIPTS.get(key, '')}</body></html>'''
        dest = OUT / ('index.html' if key == 'index' else f'{key}/index.html')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html)
    (OUT / '_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: DENY\n  Content-Security-Policy: default-src \'self\'; script-src \'self\'; style-src \'self\'; font-src \'self\'; img-src \'self\' data:; connect-src \'self\'; object-src \'none\'; base-uri \'self\'; frame-ancestors \'none\'\n')
    (OUT / 'robots.txt').write_text('User-agent: *\nAllow: /\n')
    (OUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>https://cendavo-deployment.pages.dev{href}</loc></url>' for _,href in NAV) + '</urlset>')
    print(f'Built {len(list((ROOT / "pages").glob("*.html")))} pages in {OUT}')


if __name__ == '__main__':
    build()
