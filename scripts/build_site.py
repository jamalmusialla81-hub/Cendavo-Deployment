#!/usr/bin/env python3
"""Build the zero-dependency Cloudflare Pages static site."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
NAV = [('Home', '/'), ('Services', '/services/'), ('Pricing', '/pricing/'), ('Demo project', '/demo/'), ('Contact', '/contact/')]
# Page-specific scripts: each is loaded only on the page that uses it.
PAGE_SCRIPTS = {'index': '<script src="/assets/home.js" defer></script>', 'demo': '<script src="/assets/demo.js" defer></script>', 'contact': '<script src="/assets/enquiry.js" defer></script>'}


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
        html = f'''<!doctype html><html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0E2A33"><meta name="description" content="{desc}"><title>{title}</title><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/site.css"></head><body><a class="skip-link" href="#main">Skip to main content</a><header class="site-header"><div class="wrap nav"><a class="brand" href="/" aria-label="Cendavo home"><span class="mark" aria-hidden="true"></span>CENDAVO</a><button class="menu" type="button" data-menu aria-label="Toggle menu" aria-controls="site-nav" aria-expanded="false"><span aria-hidden="true">☰</span></button><nav class="nav-links" id="site-nav" data-nav aria-label="Main navigation">{links}</nav><a class="button small dark" href="/contact/">Request a free consultation</a></div></header><main id="main" tabindex="-1">{page}</main><footer class="footer"><div class="wrap"><div class="footer-row"><div><a class="brand" href="/"><span class="mark" aria-hidden="true"></span>CENDAVO</a><p>Website design, redesign and care for local service businesses.<br>Sydney, Australia.</p></div><nav class="footer-links" aria-label="Footer navigation">{links}</nav></div><div class="footer-bottom">© 2026 Cendavo. The demonstration project uses sample data only.</div></div></footer><script src="/assets/site.js" defer></script>{PAGE_SCRIPTS.get(key, '')}</body></html>'''
        dest = OUT / ('index.html' if key == 'index' else f'{key}/index.html')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html)
    (OUT / '_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: DENY\n  Content-Security-Policy: default-src \'self\'; script-src \'self\'; style-src \'self\'; font-src \'self\'; img-src \'self\' data:; connect-src \'self\'; object-src \'none\'; base-uri \'self\'; frame-ancestors \'none\'\n')
    (OUT / 'robots.txt').write_text('User-agent: *\nAllow: /\n')
    (OUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>https://cendavo-deployment.pages.dev{href}</loc></url>' for _,href in NAV) + '</urlset>')
    print(f'Built {len(list((ROOT / "pages").glob("*.html")))} pages in {OUT}')


if __name__ == '__main__':
    build()
