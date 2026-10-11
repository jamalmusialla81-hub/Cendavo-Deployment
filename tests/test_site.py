import re
import struct
import unittest
from html.parser import HTMLParser
from pathlib import Path
from scripts.build_site import build, OUT


class SiteBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()

    def test_all_public_routes_are_built_with_navigation(self):
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertIn('CENDAVO', html)
                self.assertIn('href="/demo/"', html)
                self.assertIn('href="/contact/"', html)
                self.assertIn('name="viewport"', html)
                self.assertFalse(re.search(r'<script[^>]*>\s*[^<\s]', html))

    def test_demo_is_clearly_sample_only(self):
        demo = (OUT / 'demo/index.html').read_text()
        self.assertIn('Demo only', demo)
        self.assertIn('No message is sent automatically', demo)
        # Reframed as a demonstration project with sample data (not a product or workspace preview).
        hero = demo.split('<main id="main" tabindex="-1">', 1)[1].split('</h1>', 1)[0]
        self.assertIn('Demonstration project', hero)
        self.assertIn('sample data', hero)
        self.assertIn('Demonstration project, sample data', hero)  # Task 21: a comma, not a spaced em dash

    # Old SaaS/subscription framing that must not return on any page (owner decision 2026-10-11).
    SAAS_WORDING = ('shared platform', 'focused admin tool', 'hypothes', 'subscri', 'a$', '/ month', 'per month',
                    'business workspace', 'workspace', 'product demo', 'can i subscribe', 'saas', 'pilot')

    def test_no_saas_or_subscription_wording(self):
        for route in self.ROUTES:
            html = (OUT / route).read_text()
            main = html.split('<main id="main" tabindex="-1">', 1)[1].split('</main>', 1)[0].lower()
            description = re.search(r'<meta name="description" content="([^"]*)"', html).group(1).lower()
            for banned in self.SAAS_WORDING:
                with self.subTest(route=route, banned=banned):
                    self.assertNotIn(banned, main)
                    self.assertNotIn(banned, description)

    def test_pricing_is_a_fixed_quote(self):
        html = (OUT / 'pricing/index.html').read_text()
        main = html.split('<main id="main" tabindex="-1">', 1)[1].split('</main>', 1)[0]
        self.assertIn('fixed quote', main.lower())
        self.assertIn('href="/contact/"', main)
        description = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        self.assertNotIn('hypothes', description.lower())
        self.assertNotIn('pilot', description.lower())

    def test_security_headers_shipped(self):
        headers = (OUT / '_headers').read_text()
        for setting in ('Content-Security-Policy:', 'X-Content-Type-Options: nosniff', "connect-src 'self'", "object-src 'none'"):
            self.assertIn(setting, headers)

    ROUTES = ['index.html','work/index.html','services/index.html','pricing/index.html','demo/index.html','about/index.html','contact/index.html']

    def test_skip_link_and_main_target_on_every_page(self):
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertIn('<body><a class="skip-link" href="#main">', html)
                self.assertIn('<main id="main" tabindex="-1">', html)
                self.assertIn('<span aria-hidden="true">☰</span>', html)

    def test_css_focus_and_reduced_motion(self):
        css = (OUT / 'assets/site.css').read_text()
        self.assertIn(':focus-visible{', css)
        self.assertIn('scroll-padding-top:90px', css)
        self.assertIn('@media(prefers-reduced-motion:no-preference){', css)
        self.assertEqual(css.count('scroll-behavior:smooth'), 1)
        # Night Shift hover: only the primary CTA's arrow moves 2px (art direction), never the whole button.
        self.assertEqual(css.count('translateX(2px)'), 1)
        guarded = css.split('@media(prefers-reduced-motion:no-preference){', 1)[1]
        self.assertIn('scroll-behavior:smooth', guarded)
        self.assertIn('translateX(2px)', guarded)

    def test_demo_table_semantics(self):
        demo = (OUT / 'demo/index.html').read_text()
        self.assertIn('<caption class="sr-only">Sample enquiries</caption>', demo)
        self.assertEqual(demo.count('<th scope="col">'), 5)
        self.assertEqual(demo.count('<th>'), 0)

    def test_demo_script_names_buttons_and_manages_focus(self):
        js = (OUT / 'assets/demo.js').read_text()
        self.assertIn("setAttribute('aria-label','Draft reply for '+item.name)", js)
        self.assertIn("requestAnimationFrame", js)
        self.assertIn("$('#status-filter').focus()", js)

    def test_demo_export_is_local_only(self):
        demo = (OUT / 'demo/index.html').read_text()
        self.assertIn('<button class="button outline" type="button" id="export-demo">Download sample requests (CSV)</button>', demo)
        self.assertIn('Nothing is uploaded.', demo)
        js = (OUT / 'assets/demo.js').read_text()
        self.assertIn('URL.revokeObjectURL', js)
        self.assertIn("type:'text/csv;charset=utf-8'", js)
        self.assertIn('Nothing was sent.', js)
        self.assertIn('Download is not available in this browser.', js)

    ENQUIRY_FIELDS = {'name': 'name', 'email': 'email', 'phone': 'tel', 'business': 'organization', 'website': 'url'}

    def test_contact_form_fields_are_labelled_and_linked_to_errors(self):
        html = (OUT / 'contact/index.html').read_text()
        # method="post": if the script never loads, a native submit must not put personal data in the URL.
        form = re.search(r'<form [^>]*data-enquiry[^>]*>', html).group(0)
        self.assertIn('method="post"', form)
        self.assertIn(' novalidate', form)
        self.assertNotIn('method="get"', form.lower())
        self.assertNotIn('data-brief', html)
        for field in ('name', 'email', 'phone', 'business', 'website', 'service', 'message'):
            with self.subTest(field=field):
                self.assertIn(f'<label for="enquiry-{field}">', html)
                control = re.search(rf'<(input|select|textarea) id="enquiry-{field}" name="{field}"[^>]*>', html)
                self.assertIsNotNone(control)
                self.assertRegex(control.group(0), rf'aria-describedby="[^"]*\benquiry-{field}-error\b[^"]*"')
                self.assertIn(f'<p class="field-error" id="enquiry-{field}-error" data-error-for="{field}"></p>', html)
                if field in self.ENQUIRY_FIELDS:
                    self.assertIn(f'autocomplete="{self.ENQUIRY_FIELDS[field]}"', control.group(0))
                required = field in ('name', 'email', 'service', 'message')
                self.assertEqual(' required' in control.group(0), required)
        self.assertEqual(html.count('<span class="req" aria-hidden="true">*</span>'), 5)  # 4 fields + legend
        self.assertEqual(html.count('<span class="optional">(optional)</span>'), 3)
        for value in ('website-design', 'website-redesign', 'maintenance', 'not-sure'):
            self.assertIn(f'<option value="{value}">', html)
        self.assertIn('<p data-enquiry-status class="status" role="status"></p>', html)
        self.assertIn('stored in a Cloudflare database', html)
        self.assertNotIn('A$', html)
        self.assertNotIn('@', html.split('<main', 1)[1].split('</main>', 1)[0])

    def test_contact_honeypot_is_hidden_from_people_and_assistive_tech(self):
        html = (OUT / 'contact/index.html').read_text()
        honeypot = re.search(r'<div class="hp" aria-hidden="true">.*?</div>', html)
        self.assertIsNotNone(honeypot)
        self.assertRegex(honeypot.group(0), r'<input id="enquiry-company-url" name="company_url" type="text" tabindex="-1" autocomplete="off">')
        css = (OUT / 'assets/site.css').read_text()
        self.assertIn('.hp{position:absolute;left:-10000px', css)
        self.assertIn('.field-error{', css)
        self.assertIn('[aria-invalid="true"]', css)

    def test_enquiry_script_loads_only_on_contact_page(self):
        tag = '<script src="/assets/enquiry.js" defer></script>'
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertEqual(html.count(tag), 1 if route == 'contact/index.html' else 0)
                self.assertEqual(html.count('<script src="/assets/demo.js" defer></script>'), 1 if route == 'demo/index.html' else 0)
        self.assertTrue((OUT / 'assets/enquiry.js').exists())
        self.assertNotIn('innerHTML', (OUT / 'assets/enquiry.js').read_text())
        self.assertFalse((OUT / 'functions').exists())
        self.assertFalse((OUT / 'migrations').exists())
        js = (OUT / 'assets/site.js').read_text()
        self.assertIn("event.key !== 'Escape'", js)
        self.assertNotIn('data-brief', js)

    def test_header_cta_requests_a_consultation(self):
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertIn('<a class="button small" href="/contact/">Request a free consultation</a>', html)
        contact = (OUT / 'contact/index.html').read_text()
        self.assertIn('content="Request a website design, redesign or maintenance consultation with Cendavo in Sydney."', contact)

    def test_sitemap_points_at_real_project(self):
        sitemap = (OUT / 'sitemap.xml').read_text()
        self.assertIn('https://cendavo-deployment.pages.dev/demo/', sitemap)
        self.assertIn('https://cendavo-deployment.pages.dev/work/', sitemap)
        self.assertNotIn('https://cendavo.pages.dev', sitemap)


MOTION_GUARD = '@media(prefers-reduced-motion:no-preference){'


def without_blocks(css, opener):
    """Return css with every `opener ... }` block (brace-matched) removed, plus the removed blocks."""
    kept, removed, start = [], [], 0
    while (index := css.find(opener, start)) != -1:
        kept.append(css[start:index])
        depth, cursor = 1, index + len(opener)
        while depth:
            depth += {'{': 1, '}': -1}.get(css[cursor], 0)
            cursor += 1
        removed.append(css[index:cursor])
        start = cursor
    kept.append(css[start:])
    return ''.join(kept), removed


def luminance(hex_colour):
    channels = [int(hex_colour.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def jpeg_size(path):
    """(width, height) from a JPEG's start-of-frame header, using only the standard library."""
    data, index = path.read_bytes(), 2
    while index < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack('>HH', data[index + 5:index + 9])
            return width, height
        index += 2 + struct.unpack('>H', data[index + 2:index + 4])[0]
    raise ValueError(f'no SOF marker in {path}')


def base_rules(css):
    """css with every @media and @container block removed, so only top-level rules remain."""
    while (match := re.search(r'@(?:media|container)\b[^{]*\{', css)):
        css = without_blocks(css, match.group(0))[0]
    return css


def minimum_px(value):
    """Smallest size a CSS font-size can resolve to: a px/rem literal, or the first argument of clamp()/max()."""
    match = re.match(r'\s*(?:(?:clamp|max)\(\s*)?([\d.]+)(px|rem)\b', value)
    if not match:
        return 0.0
    number = float(match.group(1))
    return number * 16 if match.group(2) == 'rem' else number


VOID_ELEMENTS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}


class ImageCollector(HTMLParser):
    """Collect every <img> with its attributes and whether any ancestor has aria-hidden="true"."""

    def __init__(self):
        super().__init__()
        self.hidden_stack, self.images = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'img':
            self.images.append((attrs, any(self.hidden_stack)))
        elif tag not in VOID_ELEMENTS:
            self.hidden_stack.append(attrs.get('aria-hidden') == 'true')

    def handle_endtag(self, tag):
        if tag not in VOID_ELEMENTS and self.hidden_stack:
            self.hidden_stack.pop()


CONCEPT_LABEL = 'Concept project · fictional business'
SHOWREEL_CAPTION = 'Showreel · concept projects, fictional businesses'
GSAP_TAGS = ['<script src="/assets/vendor/gsap/gsap.min.js" defer></script>',
             '<script src="/assets/vendor/gsap/ScrollTrigger.min.js" defer></script>',
             '<script src="/assets/motion.js" defer></script>']
HOME_TAG = '<script src="/assets/home.js" defer></script>'
# Pages that show device or quote mockups and so load the shared mockup kit (kit.css).
KIT_ROUTES = ['index.html', 'work/index.html', 'pricing/index.html']
# Pages with GSAP motion (Night Shift Task 10; About added in Task 15). Contact (the enquiry form) and Demo (the browser app) stay static.
MOTION_ROUTES = ['index.html', 'work/index.html', 'services/index.html', 'pricing/index.html', 'about/index.html']
STATIC_ROUTES = ['contact/index.html', 'demo/index.html']
MOTION_HOOKS = ('data-ph', 'data-reveal', 'data-parallax', 'data-devices', 'data-rise', 'data-work', 'data-intro')
# Network, storage and markup-injection APIs no motion script may use; autoAlpha (visibility:hidden), snap (scroll
# hijacking) and preventDefault (swallowing a visitor's key or click) are banned too.
MOTION_SCRIPT_BANS = ('fetch(', 'XMLHttpRequest', 'innerHTML', 'http', 'localStorage', 'autoAlpha', 'snap', 'preventDefault',
                      'sendBeacon', 'WebSocket', 'eval(')


class DesignSystemTests(unittest.TestCase):
    ROUTES = SiteBuildTests.ROUTES

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = (OUT / 'assets/site.css').read_text()
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.pages_css = (OUT / 'assets/pages.css').read_text()
        cls.kit_css = (OUT / 'assets/kit.css').read_text()
        cls.home = (OUT / 'index.html').read_text()
        cls.home_main = cls.home.split('<main id="main" tabindex="-1">', 1)[1].split('</main>', 1)[0]
        root = re.search(r':root\{(.*?)\}', cls.css, re.S).group(1)
        cls.tokens = dict(re.findall(r'(--[\w-]+):([^;]+)', root))

    def test_palette_tokens_match_art_direction(self):
        # Night Shift palette (docs/design/night-shift/NIGHT_SHIFT.md); success/danger darkened for AA on bone.
        palette = {'--ink': '#0E0E0D', '--ink-2': '#171716', '--bone': '#EDEAE3', '--bone-2': '#E3DFD6',
                   '--paper': '#F7F5F0', '--stone': '#A8A49B', '--ink-soft': '#4F4C46', '--amber': '#D9A441',
                   '--amber-hover': '#E6B65A', '--success': '#1E6B47', '--danger': '#A3341F'}
        for name, value in palette.items():
            with self.subTest(token=name):
                self.assertEqual(self.tokens.get(name, '').strip().upper(), value)

    def test_scale_tokens(self):
        spaces = {k: v for k, v in self.tokens.items() if k.startswith('--space-')}
        self.assertGreaterEqual(len(spaces), 8)
        for name, value in spaces.items():
            with self.subTest(token=name):
                self.assertEqual(int(value.removesuffix('px')) % 4, 0)
        self.assertTrue(any(k.startswith('--radius-') for k in self.tokens))
        shadows = [k for k in self.tokens if k.startswith('--shadow')]
        self.assertTrue(1 <= len(shadows) <= 3)
        self.assertEqual([self.tokens[k] for k in ('--dur-1', '--dur-2', '--dur-3')], ['120ms', '200ms', '400ms'])
        self.assertEqual(len([k for k in self.tokens if k.startswith('--ease')]), 1)
        for name in ('--font-display', '--font-text'):
            with self.subTest(token=name):
                self.assertIn('sans-serif', self.tokens[name])
        self.assertIn('clamp(', self.tokens['--text-display'])

    def test_colour_pairs_meet_wcag(self):
        t = {k: v.strip() for k, v in self.tokens.items() if v.strip().startswith('#')}
        text_pairs = [('bone', 'ink'), ('bone', 'ink-2'), ('stone', 'ink'), ('stone', 'ink-2'), ('ink', 'bone'),
                      ('ink', 'bone-2'), ('ink', 'paper'), ('ink-soft', 'bone'), ('ink-soft', 'bone-2'), ('ink-soft', 'paper'),
                      ('ink', 'amber'), ('ink', 'amber-hover'), ('danger', 'paper'), ('danger', 'bone'), ('danger', 'bone-2'),
                      ('success', 'paper'), ('success', 'bone'), ('success', 'bone-2')]
        for fg, bg in text_pairs:
            with self.subTest(pair=f'{fg}/{bg}'):
                self.assertGreaterEqual(contrast(t[f'--{fg}'], t[f'--{bg}']), 4.5)
        # Focus rings: bone on dark surfaces (the default), ink inside light (bone/paper) sections.
        self.assertIn(':focus-visible{outline:2px solid var(--bone)', self.css)
        self.assertIn('.bone :focus-visible,.section :focus-visible{outline-color:var(--ink)}', self.css)
        self.assertRegex(self.css, r'\.demo-side :focus-visible[^{]*\{outline-color:var\(--bone\)\}')
        for ring, bg in (('bone', 'ink'), ('bone', 'ink-2'), ('ink', 'bone'), ('ink', 'bone-2'), ('ink', 'paper')):
            with self.subTest(ring=f'{ring}/{bg}'):
                self.assertGreaterEqual(contrast(t[f'--{ring}'], t[f'--{bg}']), 3)
        self.assertLess(contrast(t['--amber'], t['--bone']), 3)  # why light sections use the ink ring, not amber

    def test_fonts_are_self_hosted(self):
        faces = re.findall(r'@font-face\{([^}]*)\}', self.css)
        self.assertGreaterEqual(len(faces), 3)
        for face in faces:
            with self.subTest(face=face[:60]):
                self.assertIn('font-display:swap', face)
                urls = re.findall(r'url\("([^"]+)"\)', face)
                self.assertTrue(urls)
                for url in urls:
                    self.assertTrue(url.startswith('/assets/fonts/') and url.endswith('.woff2'), url)
                    self.assertTrue((OUT / url.lstrip('/')).is_file(), url)
        self.assertIn('font-stretch:62% 125%', self.css)  # Archivo's width axis, used for condensed headlines
        for licence in ('OFL-Archivo.txt', 'OFL-AtkinsonHyperlegible.txt'):
            self.assertTrue((OUT / 'assets/fonts' / licence).is_file())
        preload = '<link rel="preload" href="/assets/fonts/archivo-var-latin.woff2" as="font" type="font/woff2" crossorigin>'
        for route in self.ROUTES:
            with self.subTest(route=route):
                self.assertEqual((OUT / route).read_text().count(preload), 1)

    def test_no_third_party_requests(self):
        for css in (self.css, self.home_css, self.pages_css, self.kit_css):
            for banned in ('@import', 'http', 'fonts.googleapis'):
                self.assertNotIn(banned, css)
        from scripts.build_site import BASE_URL
        for route in self.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertNotRegex(html, r'\bsrc="(?!/)')
                self.assertNotRegex(html, r'\bsrcset="(?!/)')
                # The one absolute <link> allowed is the canonical URL, and only on our own origin.
                rest = re.sub(rf'<link rel="canonical" href="{re.escape(BASE_URL)}/[^"]*">', '', html, count=1)
                self.assertNotRegex(rest, r'<link[^>]+href="(?!/)')
                # Absolute URLs in Open Graph metadata (read by link-preview crawlers, never by visitors) stay on our origin.
                for url in re.findall(r'content="([a-z][a-z0-9+.-]*:/*[^"]*)"', html, re.I):
                    self.assertTrue(url.startswith(BASE_URL + '/'), url)
        headers = (OUT / '_headers').read_text()
        self.assertIn("style-src 'self';", headers)
        self.assertIn("font-src 'self';", headers)
        self.assertIn("script-src 'self';", headers)
        self.assertNotIn('googleapis', headers)
        self.assertNotIn('gstatic', headers)

    def test_global_chrome(self):
        from scripts.build_site import NAV
        self.assertEqual([label for label, _ in NAV], ['Home', 'Work', 'Services', 'Pricing', 'Demo project', 'About', 'Contact'])
        self.assertEqual([href for _, href in NAV], ['/', '/work/', '/services/', '/pricing/', '/demo/', '/about/', '/contact/'])
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertIn('<html lang="en-AU">', html)
                self.assertIn('<meta name="theme-color" content="#0E0E0D">', html)
                title = re.search(r'<title>(.*?)</title>', html).group(1)
                self.assertNotIn('Product demo', title)
                self.assertNotIn('Less admin', title)
                footer = html.split('<footer', 1)[1]
                self.assertNotIn('Product in development', footer)
                self.assertNotIn('systems', footer)
                self.assertIn('aria-controls="site-nav"', html)
                self.assertIn('<nav class="nav-links" id="site-nav" data-nav', html)
                self.assertIn('aria-expanded="false"', html)
        self.assertIn('<title>Cendavo — Website design for Sydney’s local service businesses</title>', self.home)
        self.assertRegex(self.home, r'<meta name="description" content="[^"]*websites for local service businesses in Sydney')

    def test_dark_first_frame_without_changing_form_controls(self):
        # Night Shift Task 25: the browser paints its dark canvas (not white) before site.css arrives, while
        # native form controls on bone/paper sections keep their light rendering.
        for route in self.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                head = html.split('</head>', 1)[0]
                self.assertEqual(html.count('<meta name="color-scheme" content="dark">'), 1)
                self.assertEqual(html.count('<meta name="theme-color" content="#0E0E0D">'), 1)
                self.assertIn('<meta name="color-scheme" content="dark">', head)
                self.assertLess(head.index('<meta name="color-scheme" content="dark">'),
                                head.index('<link rel="stylesheet" href="/assets/site.css">'))
        self.assertIn('input,select,textarea{color-scheme:light}', self.css)
        self.assertNotRegex(self.css, r'(?:^|[;{}\s])color-scheme:dark')

    def test_mobile_menu_collapses_only_with_javascript(self):
        self.assertIn("document.documentElement.classList.add('js')", (OUT / 'assets/site.js').read_text())
        self.assertIn('.js .nav-links{display:none}', self.css)
        self.assertNotRegex(self.css, r'(?<!\.js )\.nav-links\{[^}]*display:none')
        self.assertIn('.js .menu{display:inline-flex}', self.css)

    def test_desktop_header_drops_demo_but_menu_and_footer_keep_it(self):
        # Night Shift Task 16: Demo project leaves the desktop header row (CSS at 1081px+) but stays in the
        # mobile menu (the same nav) and the footer; header labels and the CTA do not wrap on desktop.
        from scripts.build_site import NAV
        expected = [href for _, href in NAV]
        for route in self.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                header = re.search(r'<nav class="nav-links" id="site-nav"[^>]*>(.*?)</nav>', html).group(1)
                footer = re.search(r'<nav class="footer-links"[^>]*>(.*?)</nav>', html).group(1)
                header_links = re.findall(r'<a([^>]*)>', header)
                self.assertEqual([re.search(r'href="([^"]+)"', a).group(1) for a in header_links], expected)
                optional = [re.search(r'href="([^"]+)"', a).group(1) for a in header_links if 'nav-optional' in a]
                self.assertEqual(optional, ['/demo/'])
                self.assertEqual(re.findall(r'<a href="([^"]+)"', footer), expected)
                self.assertNotIn('nav-optional', footer)
                self.assertNotIn('class=', footer)
        demo = (OUT / 'demo/index.html').read_text()
        self.assertIn('<a class="nav-optional" href="/demo/" aria-current="page">Demo project</a>', demo)
        self.assertIn('<a href="/demo/" aria-current="page">Demo project</a>', demo.split('<footer', 1)[1])
        desktop = re.search(r'@media\(min-width:1081px\)\{(.*?)\n\}', self.css, re.S)
        self.assertIsNotNone(desktop)
        self.assertIn('.nav-links .nav-optional{display:none}', desktop.group(1))
        self.assertIn('.nav-links a,.nav>.button{white-space:nowrap}', desktop.group(1))
        outside = self.css.replace(desktop.group(0), '')
        self.assertNotIn('nav-optional', outside)  # nothing hides Demo in the mobile menu
        for rule in re.findall(r'([^{}]+)\{[^{}]*white-space:nowrap', outside):
            with self.subTest(rule=rule.strip()):
                self.assertNotRegex(rule, r'\.nav-links a|\.nav>\.button')

    def test_homepage_structure(self):
        main = self.home_main
        self.assertEqual(main.count('<h1'), 1)
        levels = [int(n) for n in re.findall(r'<h([1-6])', main)]
        self.assertEqual(levels[0], 1)
        for previous, current in zip(levels, levels[1:]):
            self.assertLessEqual(current, previous + 1)
        h2s = [re.sub(r'<[^>]+>', '', h) for h in re.findall(r'<h2[^>]*>(.*?)</h2>', main)]
        # Night Shift Task 28 (owner): hero, showreel, three project cards, before/after, what we do, closing call to action.
        self.assertEqual(h2s, ['Twenty seconds of what we build', 'Concept projects', 'Same business. A very different first impression.',
                               'What we do', 'Let’s make your website as good as your work.'])
        sections = re.findall(r'<section class="([a-z ]+)"', main)
        self.assertEqual(sections, ['hero', 'reel', 'work', 'ba bone', 'services', 'band'])
        # The process now lives on /services/ and the questions on /services/ and /pricing/.
        self.assertNotIn('<ol class="steps"', main)
        self.assertEqual(main.count('<details'), 0)

    def test_homepage_calls_to_action(self):
        main = self.home_main
        cta = 'href="/contact/">Request a free consultation</a>'
        hero = main.split('</section>', 1)[0]
        band = main.split('<section class="band"', 1)[1]
        self.assertIn(cta, hero)
        self.assertIn(cta, band)
        self.assertIn('<a class="button go" href="/contact/">Request a free consultation</a>', hero)
        self.assertIn('<a class="button large go" href="/contact/">', band)
        work = main.split('id="work-title"', 1)[1].split('</section>', 1)[0]
        # The work section is honest that it shows concepts, and links to the working demonstration project.
        self.assertIn('href="/demo/">See a demonstration project</a>', work)
        self.assertIn('The photos are real; the businesses are not.', work)
        # Each card leads to its project on /work/, and "See all work" to the page itself (Task 28).
        self.assertEqual(re.findall(r'<h3 id="t\d-title"><a href="([^"]+)">', work), ['/work/#harbourside', '/work/#greenline', '/work/#fade-co'])
        self.assertIn('<a class="ulink strong" href="/work/">See all work</a>', work)
        self.assertNotIn('href="/pricing/"', main)

    def test_homepage_makes_no_unvalidated_claims(self):
        # The required concept label and the showreel caption (Task 28) are the only places a middle dot may appear.
        self.assertEqual(self.home_main.count(SHOWREEL_CAPTION), 1)
        text = self.home_main.replace(CONCEPT_LABEL, '').replace(SHOWREEL_CAPTION, '').lower()
        for banned in ('less admin', 'product demo', 'platform', 'subscription', 'saas', 'a$', '$', '%', 'testimonial',
                       'trusted by', 'award', '·', '↗', '→'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, text)
        self.assertNotRegex(text, r'\d+\s*(day|week|hour)')

    def test_before_after_comparison(self):
        figure = re.search(r'<figure class="compare" data-compare>.*?</figure>', self.home_main, re.S).group(0)
        self.assertRegex(figure, r'<figcaption>Illustration of a fictional business[^<]*</figcaption>')
        self.assertIn('<div class="mock mock-before" aria-hidden="true">', figure)
        self.assertIn('<div class="mock mock-after" aria-hidden="true">', figure)
        self.assertIn('<label class="compare-label">Compare before and after<input type="range" min="0" max="100" value="50"></label>', figure)
        self.assertRegex(figure, r'<div class="compare-controls" data-compare-controls hidden>')
        for label, value in (('Before', 0), ('After', 100)):
            with self.subTest(button=label):
                self.assertIn(f'<button class="compare-button" type="button" aria-pressed="false" data-compare-set="{value}">{label}</button>', figure)
        text = re.sub(r'<[^>]+>', ' ', figure)
        for address in re.findall(r'\b[\w-]+(?:\.[\w-]+)+\b', text):
            with self.subTest(address=address):
                self.assertTrue(address.endswith('.example'))
        # Real photography is allowed in the mockups now, but only as silent decoration inside the aria-hidden mocks.
        parser = ImageCollector()
        parser.feed(figure)
        self.assertTrue(parser.images)
        for attrs, hidden in parser.images:
            with self.subTest(img=attrs.get('src')):
                self.assertTrue(hidden)
                self.assertEqual(attrs.get('alt'), '')
        # Fictional phone numbers only from ACMA's reserved drama range.
        for number in re.findall(r'\(0\d\)\s*[\d ]+', text):
            self.assertTrue(number.startswith('(02) 5550'))
        self.assertIn('.compare{--pos:50%', self.home_css)
        self.assertIn('clip-path:inset(0 calc(100% - var(--pos)) 0 0)', self.home_css)

    def test_dated_before_page_reads_as_a_full_2009_site(self):
        # Supervisor review (Task 11): no large empty area; a second column of news, a guestbook link and a hit counter.
        before = re.search(r'<div class="mock mock-before" aria-hidden="true">(.*?)<div class="mock mock-after"', self.home_main, re.S).group(1)
        news = re.search(r'<div class="old-news">(.*?)</div>', before, re.S).group(1)
        self.assertIn('<b>Latest news</b>', news)
        self.assertGreaterEqual(len(re.findall(r'<i>\d{2}/\d{2}/20\d{2}</i>', news)), 2)
        self.assertIn('<div class="old-cols">', before)
        self.assertRegex(before, r'<u>[^<]*[Gg]uestbook[^<]*</u>')
        self.assertIn('class="old-count"', before)
        self.assertIn('Under construction', before)
        self.assertIn('2009', before)
        self.assertRegex(self.home_css, r'\.old-cols\{[^}]*grid-template-columns:auto minmax\(0,1fr\)')

    def test_moved_and_dropped_sections_are_gone_from_the_homepage(self):
        # Night Shift Task 28 (owner): the statement band, "Who it's for", "How it works", the pricing band and the questions
        # leave the homepage (the process and the trades row move to /services/ and /about/), markup and styles alike.
        for gone in ('class="statement', 'class="who', 'class="process', 'class="pricing', 'class="questions', '<details',
                     'Built for the businesses that keep Sydney running', 'How it works', 'Fixed quote after a free consultation'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.home_main)
        for selector in ('.statement', '.who', '.process', '.step', '.pricing', '.questions', '.proj', '.work-stage', '.work-count',
                         '.work-exit', '.devices-', '.phone-home', '.skip-proj'):
            with self.subTest(selector=selector):
                self.assertNotRegex(self.home_css, re.escape(selector) + r'(?![\w-])' if not selector.endswith('-') else re.escape(selector))
        self.assertNotIn('garden-walk', self.home_main)  # the pricing band's photo went with it

    def test_concept_cards_link_to_their_work_sections(self):
        # Night Shift Task 28: three compact cards (photo, name, label, one line) replace the pinned sequence; each title links
        # to its project on /work/, whose sections carry those ids.
        section = re.search(r'<section class="work" id="work"[^>]*>(.*?)</section>', self.home_main, re.S).group(1)
        cards = re.findall(r'<article class="teaser-card" aria-labelledby="(t\d-title)">(.*?)</article>', section, re.S)
        self.assertEqual(len(cards), 3)
        work = main_of((OUT / 'work/index.html').read_text())
        expected = (('harbourside', 'Harbourside Mobile Detailing', 'detail-headlight'), ('greenline', 'Greenline Landscapes', 'garden-lawn'),
                    ('fade-co', 'Fade &amp; Co', 'barber-interior'))
        for (label_id, card), (slug, name, photo) in zip(cards, expected):
            with self.subTest(project=slug):
                self.assertIn(f'<h3 id="{label_id}"><a href="/work/#{slug}">{name}</a></h3>', card)
                self.assertRegex(work, rf'<article [^>]*id="{slug}"')
                self.assertRegex(card, r'<p class="teaser-line">[^<]{40,160}</p>')
                parser = ImageCollector()
                parser.feed(card)
                self.assertEqual(len(parser.images), 1)
                attrs, hidden = parser.images[0]
                self.assertIn(f'/assets/images/{photo}-800.jpg', attrs['src'])
                self.assertFalse(hidden)
                self.assertTrue(attrs['alt'].strip())
                self.assertEqual((attrs.get('loading'), attrs.get('decoding')), ('lazy', 'async'))
                self.assertTrue(attrs.get('width') and attrs.get('height'))
                self.assertLess(card.index('<figure'), card.index('<h3'))
        self.assertEqual(section.count('<a class="ulink strong" href="/work/">See all work</a>'), 1)
        # A row of three on wide screens, stacked at 860px and below; the title link covers the card (one tab stop each).
        base = base_rules(self.home_css)
        self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', rules_for(base, '.teaser')[0])
        self.assertIn('grid-template-columns:1fr', rules_for(media_blocks(self.home_css, 'max-width:860px'), '.teaser')[0])
        self.assertIn('position:relative', rules_for(base, '.teaser-card')[0])
        self.assertIn('position:absolute;inset:0', rules_for(base, '.teaser-card h3 a::after')[0])
        self.assertEqual(section.count('<a '), 5)  # three titles, the demonstration project and "See all work"

    def test_concept_projects_are_labelled(self):
        articles = re.findall(r'<article class="teaser-card"[^>]*>(.*?)</article>', self.home_main, re.S)
        self.assertEqual(len(articles), 3)
        for article, name in zip(articles, ('Harbourside Mobile Detailing', 'Greenline Landscapes', 'Fade &amp; Co')):
            with self.subTest(project=name):
                self.assertEqual(article.count(CONCEPT_LABEL), 1)
                self.assertIn(f'>{name}</a></h3>', article)
        for route in self.ROUTES:
            with self.subTest(route=route):
                footer = (OUT / route).read_text().split('<footer', 1)[1]
                self.assertIn('Harbourside Mobile Detailing, Greenline Landscapes and Fade &amp; Co are fictional concept businesses.', footer)

    def test_homepage_images_are_local_sized_and_described(self):
        parser = ImageCollector()
        parser.feed(self.home_main)
        self.assertGreaterEqual(len(parser.images), 10)
        hero = parser.images[0][0]
        self.assertEqual(hero.get('fetchpriority'), 'high')
        self.assertNotIn('loading', hero)
        self.assertTrue(hero.get('alt'))
        for index, (attrs, hidden) in enumerate(parser.images):
            with self.subTest(index=index, src=attrs.get('src')):
                for name in ('src', 'srcset', 'sizes', 'width', 'height', 'alt'):
                    self.assertIn(name, attrs)
                self.assertEqual(attrs.get('decoding'), 'async')
                if index:
                    self.assertEqual(attrs.get('loading'), 'lazy')
                if not attrs['alt'].strip():
                    self.assertTrue(hidden, 'an empty alt is only allowed inside an aria-hidden mockup')
                candidates = dict(reversed(part.split()) for part in attrs['srcset'].split(','))
                self.assertEqual(set(candidates), {'800w', '1600w'})
                small, large = candidates['800w'], candidates['1600w']
                self.assertRegex(small, r'^/assets/images/[a-z-]+-800\.jpg$')
                self.assertEqual(large, small.replace('-800.jpg', '-1600.jpg'))
                self.assertIn(attrs['src'], (small, large))
                for url in (small, large):
                    self.assertTrue((OUT / url.lstrip('/')).is_file(), url)
                width, height = jpeg_size(OUT / large.lstrip('/'))
                self.assertAlmostEqual(int(attrs['height']) / int(attrs['width']), height / width, delta=0.01 * height / width)

    def test_home_script_is_small_isolated_and_safe(self):
        # GSAP, then ScrollTrigger, then motion.js (then home.js on /): deferred, in that order, only on the motion pages.
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                for tag in GSAP_TAGS:
                    self.assertEqual(html.count(tag), 1 if route in MOTION_ROUTES else 0)
                self.assertEqual(html.count(HOME_TAG), 1 if route == 'index.html' else 0)
                if route in MOTION_ROUTES:
                    tags = GSAP_TAGS + ([HOME_TAG] if route == 'index.html' else [])
                    positions = [html.index(tag) for tag in tags]
                    self.assertEqual(positions, sorted(positions))
                    self.assertGreater(positions[0], html.index('</footer>'))
                else:
                    self.assertNotIn('gsap', html.lower())
                    self.assertNotIn('scrolltrigger', html.lower())
                    self.assertNotIn('motion', html.lower())
        for name in ('gsap.min.js', 'ScrollTrigger.min.js', 'LICENSE.txt'):
            self.assertTrue((OUT / 'assets/vendor/gsap' / name).is_file())
        budgets = {'home.js': 12 * 1024, 'motion.js': 8 * 1024, 'motion-boot.js': 1024}
        scripts = {}
        for name, budget in budgets.items():
            path = OUT / 'assets' / name
            with self.subTest(script=name):
                self.assertLessEqual(path.stat().st_size, budget)
            scripts[name] = path.read_text()
            for banned in MOTION_SCRIPT_BANS:
                with self.subTest(script=name, banned=banned):
                    self.assertNotIn(banned, scripts[name])
            # Session storage is only ever touched inside try/catch (it throws when storage is blocked).
            for line in scripts[name].splitlines():
                if 'sessionStorage' in line:
                    with self.subTest(script=name, line=line.strip()[:60]):
                        self.assertIn('try {', line)
                        self.assertIn('catch (', line)
        js = scripts['home.js']
        self.assertIn("addEventListener('input'", js)
        self.assertIn("setProperty('--pos'", js)
        self.assertIn('controls.hidden = false', js)
        self.assertIn("setAttribute('aria-pressed'", js)
        # Motion is optional and only runs for people who have not asked for reduced motion.
        for name in ('home.js', 'motion.js'):
            with self.subTest(script=name):
                self.assertIn('if (!gsap || !ScrollTrigger)', scripts[name])
                self.assertIn('gsap.matchMedia()', scripts[name])
                self.assertIn("'(prefers-reduced-motion: no-preference)'", scripts[name])
        # Without GSAP the intro ends at once: the class is removed before returning.
        self.assertIn('if (!gsap || !ScrollTrigger) { endIntro(); return; }', js)
        self.assertIn("root.classList.remove('ns-intro')", js)
        # The intro skip listens to every kind of input, passively, and removes its listeners when the intro ends.
        self.assertIn("const SKIP_EVENTS = ['keydown', 'pointerdown', 'wheel', 'touchstart'];", js)
        self.assertIn('window.addEventListener(type, onSkip, { passive: true })', js)
        self.assertIn('window.removeEventListener(type, onSkip)', js)
        # Night Shift Task 28: no pinned project sequence any more; the showreel controller needs no GSAP and observes the
        # video's visibility instead of listening to scroll.
        self.assertNotIn('pin:', js)
        self.assertNotIn('PIN_', js)
        self.assertNotIn("addEventListener('scroll'", js)
        self.assertIn("const NARROW = '(max-width: 640px)';", js)
        self.assertIn('new window.IntersectionObserver(', js)
        self.assertIn("video.removeAttribute('controls')", js)
        self.assertIn('toggle.hidden = false', js)
        self.assertNotIn('autoplay', js)
        # Magnetic buttons: fine pointers only, clamped to 6px or less.
        motion = scripts['motion.js']
        self.assertIn("(hover: hover) and (pointer: fine)", motion)
        pull = re.search(r'const MAX_PULL = (\d+(?:\.\d+)?);', motion)
        self.assertIsNotNone(pull)
        self.assertLessEqual(float(pull.group(1)), 6)
        self.assertIn('Math.max(-MAX_PULL, Math.min(MAX_PULL, value))', motion)
        # Parallax only on large screens; FAQ answers fade with opacity/transform after the native toggle.
        self.assertIn("mm.add(MOTION + ' and (min-width: 1081px)'", motion)
        self.assertIn("addEventListener('toggle', onToggle)", motion)
        # Layout properties are never tweened (media-query features such as min-width are not tween properties).
        for name in ('home.js', 'motion.js'):
            with self.subTest(script=name):
                self.assertNotRegex(scripts[name], r'(?<![-\w])(height|width|top|left|right|bottom|margin|padding)\s*:\s*[-\d\'"]')

    def test_motion_boot_script_runs_first_and_opts_in_to_the_intro_only_on_home(self):
        boot = '<script src="/assets/motion-boot.js"'
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                head = html.split('</head>', 1)[0]
                if route in MOTION_ROUTES:
                    self.assertEqual(html.count(boot), 1)
                    tag = re.search(r'<script src="/assets/motion-boot\.js"[^>]*></script>', head).group(0)
                    self.assertNotIn('defer', tag)
                    self.assertNotIn('async', tag)
                    self.assertEqual('data-intro' in tag, route == 'index.html')
                else:
                    self.assertNotIn(boot, html)
                self.assertNotIn('data-intro', html.split('<script src="/assets/motion-boot.js"', 1)[-1] if route != 'index.html' else '')
        js = (OUT / 'assets/motion-boot.js').read_text()
        self.assertIn("c.add('js')", js)
        self.assertIn("c.add('motion')", js)
        self.assertIn("matchMedia('(prefers-reduced-motion: reduce)').matches) return;", js)
        self.assertIn("hasAttribute('data-intro')", js)
        self.assertIn('w.location.hash) return;', js)
        delay = re.search(r"setTimeout\(function \(\) \{ c\.remove\('ns-intro'\); \}, (\d+)\)", js)
        self.assertIsNotNone(delay)
        self.assertLessEqual(int(delay.group(1)), 2500)

    def test_intro_panel_is_hidden_from_assistive_tech_and_never_blocks(self):
        main = self.home_main
        intro = re.search(r'<div class="intro" aria-hidden="true">.*?<span class="intro-hint">[^<]*</span></div>', main, re.S)
        self.assertIsNotNone(intro)
        for focusable in ('<button', '<a ', '<input', 'tabindex'):
            with self.subTest(focusable=focusable):
                self.assertNotIn(focusable, intro.group(0))
        hero = re.search(r'<section class="hero"[^>]*>', main).group(0)
        self.assertNotIn('aria-hidden', hero)
        self.assertNotIn('inert', hero)
        self.assertNotIn('inert', main)
        unguarded, guarded = without_blocks(self.home_css, MOTION_GUARD)
        self.assertIn('.intro{display:none;pointer-events:none}', unguarded)
        self.assertNotIn('.ns-intro', unguarded)
        shown = [block for block in guarded if '.ns-intro .intro{' in block]
        self.assertEqual(len(shown), 1)
        rule = shown[0].split('.ns-intro .intro{', 1)[1].split('}', 1)[0]
        self.assertIn('position:fixed', rule)
        self.assertNotIn('pointer-events:auto', rule)
        self.assertNotIn('overflow:hidden', self.home_css.split('.ns-intro', 1)[0][-40:])
        self.assertNotRegex(self.home_css, r'\.ns-intro[^{]*body')

    def test_homepage_has_no_pinned_sequence_to_skip(self):
        # Night Shift Task 28 (owner: "making it all one scroll thing looks very AI"): the pinned sequence, its skip link,
        # counter and bone exit layer are gone, so nothing on the homepage holds the scroll.
        main = self.home_main
        for gone in ('skip-proj', 'Skip projects', 'id="after-work"', 'data-work', 'work-stage', 'work-exit', 'work-count',
                     'is-pinned', 'class="proj', 'proj-mask', 'proj-devices'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, main)
                self.assertNotIn(gone, self.home_css)
        self.assertNotIn('position:sticky', ''.join(rules_for(base_rules(self.home_css), '.work')))
        # The hero's "See concept projects" still lands on the project cards.
        self.assertIn('<a class="button outline" href="#work">See concept projects</a>', main)
        self.assertEqual(main.count('id="work"'), 1)

    def test_first_party_javascript_budget_per_page(self):
        # Motion pages may spend up to 20 KB of first-party script (GSAP excluded); Contact and Demo keep the 15 KB cap.
        for route in self.ROUTES:
            with self.subTest(route=route):
                sources = re.findall(r'<script src="(/assets/[^"]+)"', (OUT / route).read_text())
                own = [src for src in sources if not src.startswith('/assets/vendor/')]
                budget = 20 * 1024 if route in MOTION_ROUTES else 15 * 1024
                self.assertLessEqual(sum((OUT / src.lstrip('/')).stat().st_size for src in own), budget)

    def test_home_stylesheet_loads_only_on_homepage(self):
        tag = '<link rel="stylesheet" href="/assets/home.css">'
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertEqual(html.count(tag), 1 if route == 'index.html' else 0)
                self.assertEqual(html.count('<link rel="stylesheet" href="/assets/site.css">'), 1)
                # Inner pages share one page stylesheet; the homepage never loads it.
                self.assertEqual(html.count('<link rel="stylesheet" href="/assets/pages.css">'), 0 if route == 'index.html' else 1)
                # The mockup kit loads once, before the page stylesheet, only where mockups appear.
                kit = '<link rel="stylesheet" href="/assets/kit.css">'
                self.assertEqual(html.count(kit), 1 if route in KIT_ROUTES else 0)
                if route in KIT_ROUTES:
                    page_style = re.search(r'<link rel="stylesheet" href="/assets/(?:home|pages)\.css">', html).start()
                    self.assertLess(html.index('<link rel="stylesheet" href="/assets/site.css">'), html.index(kit))
                    self.assertLess(html.index(kit), page_style)

    def test_motion_is_guarded_and_compositor_only(self):
        for name, css in (('site.css', self.css), ('home.css', self.home_css), ('pages.css', self.pages_css), ('kit.css', self.kit_css)):
            unguarded, guarded = without_blocks(css, MOTION_GUARD)
            if name == 'site.css':
                self.assertTrue(guarded)
            for word in ('transition', 'animation', '@keyframes'):
                with self.subTest(css=name, word=word):
                    self.assertNotIn(word, unguarded)
            for block in guarded:
                for value in re.findall(r'transition:([^;}]+)', block):
                    properties = [part.split()[0] for part in value.split(',')]
                    self.assertTrue(set(properties) <= {'transform', 'opacity'}, value)
                self.assertNotIn('animation', block)

    def test_reveal_states_come_from_javascript_only(self):
        # Content stays visible without JS, if GSAP fails, and with reduced motion: CSS never hides it.
        for name, css in (('site.css', self.css), ('home.css', self.home_css), ('pages.css', self.pages_css), ('kit.css', self.kit_css)):
            with self.subTest(css=name):
                unguarded, guarded = without_blocks(css, MOTION_GUARD)
                guarded = re.sub(r'/\*.*?\*/', '', ''.join(guarded), flags=re.S)
                for hook in ('data-rise', 'data-hero-fade') + MOTION_HOOKS:
                    self.assertNotIn(hook, css)
                self.assertNotRegex(unguarded, r'opacity:0(?![.\d])')
                self.assertNotIn('visibility:hidden', unguarded)
                # Night Shift Task 23: the one exception is the page openings' start states, guarded and only while
                # motion-boot.js holds .ph-wait. Any guarded rule that hides content (opacity:0, an off-mask transform or a
                # closed clip-path) is either such a .ph-wait rule or the existing Services photo crossfade.
                self.assertNotIn('.ph-wait', re.sub(r'/\*.*?\*/', '', unguarded, flags=re.S))
                for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', guarded):
                    hides = re.search(r'opacity:0(?![.\d])|translateY\(1\d\d%\)|clip-path:inset\([^)]*100%', body)
                    if hides:
                        with self.subTest(css=name, selectors=selectors.strip()[:60]):
                            # Top-level selectors only: commas inside :is(...) do not split a selector.
                            parts = [part.strip() for part in re.sub(r'\([^()]*\)', '()', selectors).split(',')]
                            # Task 26: the one narrower hold is the homepage hero photo, clipped only without the intro.
                            self.assertTrue(all(part.startswith('.ph-wait ') for part in parts)
                                            or parts == ['.svc-panel.is-live .svc-photo']
                                            or selectors.strip() == '.ph-wait:not(.ns-intro) .hero-photo', selectors)

    def test_layout_basics(self):
        for selector, css in (('.button{', self.css), ('.menu{', self.css), ('.compare-button{', self.home_css)):
            with self.subTest(selector=selector):
                rule = css.split(selector, 1)[1].split('}', 1)[0]
                height = re.search(r'min-height:(\d+)px', rule)
                self.assertIsNotNone(height)
                self.assertGreaterEqual(int(height.group(1)), 44)  # tap targets of at least 44px
        self.assertIn(':focus-visible{', self.css)
        self.assertIn('@media(max-width:640px){', self.css)
        self.assertLessEqual((OUT / 'assets/site.css').stat().st_size, 30 * 1024)
        self.assertLessEqual((OUT / 'assets/home.css').stat().st_size, 30 * 1024)
        self.assertLessEqual((OUT / 'assets/pages.css').stat().st_size, 30 * 1024)
        self.assertLessEqual((OUT / 'assets/kit.css').stat().st_size, 30 * 1024)

    def test_mockup_kit_is_defined_once_and_shared(self):
        # Task 12: device frames, mini-sites and the quote sheet live only in kit.css, not copied per page.
        # Base rules only: responsive overrides inside @media/@container blocks are not second definitions.
        sheets = {name: base_rules(css) for name, css in (('site.css', self.css), ('home.css', self.home_css),
                                                         ('pages.css', self.pages_css), ('kit.css', self.kit_css))}
        for selector in ('.laptop{', '.laptop-screen{', '.phone{', '.phone-screen{', '.ms{', '.hb{', '.gl{', '.fc{',
                         '.gls{', '.fcd{', '.quote-paper{', '.quote-top{', '.quote-lines li{'):
            with self.subTest(selector=selector):
                pattern = r'(?:^|[}\n])' + re.escape(selector)
                counts = {name: len(re.findall(pattern, css)) for name, css in sheets.items()}
                self.assertEqual(sum(counts.values()), 1, counts)
                self.assertEqual(counts['kit.css'], 1, counts)

    def test_how_it_works_has_quiet_numerals_a_photo_and_readable_steps(self):
        # Night Shift Task 28: the five steps moved from the homepage to /services/, before "Questions owners ask us", with
        # their styles moved to pages.css unchanged.
        services = main_of((OUT / 'services/index.html').read_text())
        self.assertEqual(services.count('<section class="process"'), 1)
        self.assertLess(services.index('<section class="process"'), services.index('id="sv-faq-title"'))
        self.assertGreater(services.index('<section class="process"'), services.index('id="care-title"'))
        steps = re.search(r'<ol class="steps"[^>]*>(.*?)</ol>', services).group(1)
        self.assertEqual(re.findall(r'<h3>(.*?)</h3>', steps), ['Discover', 'Design', 'Build', 'Launch', 'Look after'])
        self.assertIn('<h2 id="process-title" data-rise>How it works</h2>', services)
        self.assertNotIn('.step', self.home_css)
        section = re.search(r'<section class="process"[^>]*>(.*?)</section>', services, re.S).group(1)
        steps = re.findall(r'<li class="step">(.*?)</li>', section, re.S)
        self.assertEqual(len(steps), 5)
        for number, step in enumerate(steps, 1):
            with self.subTest(step=number):
                self.assertIn(f'<span class="step-n" aria-hidden="true">{number:02d}</span>', step)
                self.assertLess(step.index('step-n'), step.index('<h3>'))
        parser = ImageCollector()
        parser.feed(section)
        self.assertEqual(len(parser.images), 1)
        attrs, hidden = parser.images[0]
        self.assertEqual(attrs.get('loading'), 'lazy')
        self.assertTrue(attrs.get('width') and attrs.get('height'))
        self.assertTrue(attrs.get('alt', '').strip())
        self.assertFalse(hidden)
        numeral = re.search(r'(?:^|[}\n])\.step-n\{([^}]*)\}', self.pages_css).group(1)
        self.assertIn('var(--font-display)', numeral)
        self.assertGreaterEqual(int(re.search(r'font-stretch:(\d+)%', numeral).group(1)), 105)
        # Night Shift Task 17: numerals (20-24px, stone, amber for the first) no longer compete with the ~28px step headings.
        size = re.search(r'font:\d+ ([^/]+)/', numeral).group(1)
        self.assertEqual(size, 'clamp(1.25rem,1.6vw,1.5rem)')
        self.assertIn('color:var(--stone)', numeral)
        self.assertIn('.step:first-child .step-n{color:var(--amber)}', self.pages_css)
        for value in re.findall(r'\.step-n\{[^}]*?font(?:-size)?:(?:\d+ )?([^;/}]+)', self.pages_css):
            with self.subTest(numeral_size=value):
                sizes = [float(n) * (16 if unit == 'rem' else 1) for n, unit in re.findall(r'([\d.]+)(px|rem)', value)]
                self.assertTrue(sizes)
                self.assertTrue(all(20 <= px <= 24 for px in sizes), value)
        self.assertRegex(self.pages_css, r'(?:^|[}\n])\.step h3\{[^}]*font-size:1\.75rem')
        rules = re.findall(r'(?:^|[}\n])\.step p\{([^}]*)\}', self.pages_css)
        self.assertTrue(rules)
        for rule in rules:
            with self.subTest(rule=rule):
                self.assertGreaterEqual(minimum_px(re.search(r'font-size:([^;]+)', rule).group(1)), 17)

    def test_pricing_teaser_shows_the_quote_sheet_without_prices(self):
        # Night Shift Task 28: the homepage no longer carries a pricing band (Pricing and Services already explain the fixed
        # quote); the quote sheet is still shown once, on /pricing/, and no amount appears on the homepage.
        self.assertNotIn('class="pricing', self.home_main)
        self.assertNotIn('pricing-media', self.home_css)
        self.assertNotIn('quote-paper', self.home_main)
        self.assertNotIn('Always included', self.home_main)
        self.assertNotIn('inc-list', self.home_main)
        self.assertNotIn('barber-client', (OUT / 'index.html').read_text())
        self.assertIn('fixed quote after a free consultation', visible_text(main_of((OUT / 'pricing/index.html').read_text())).lower())
        # The quote sheet itself is still on /pricing/, as a labelled illustration whose parts are hidden from AT.
        pricing = main_of((OUT / 'pricing/index.html').read_text())
        paper = re.search(r'<div class="quote-paper" data-devices role="img" aria-label="([^"]+)">(.*?)</div>\n<figcaption>', pricing, re.S)
        self.assertIsNotNone(paper)
        self.assertIn('Illustration', paper.group(1))
        children = re.findall(r'<(?:div|ul) class="quote-[a-z]+"([^>]*)>', paper.group(2))
        self.assertGreaterEqual(len(children), 4)
        for attrs in children:
            with self.subTest(child=attrs):
                self.assertIn('aria-hidden="true"', attrs)
        # The care plan and build prices are unconfirmed: no amount appears anywhere on the homepage.
        self.assertNotRegex(self.home_main, r'\$\s*\d')
        self.assertNotIn('A$', self.home_main)

    def test_questions_sit_in_two_columns(self):
        # Night Shift Task 28: the homepage questions are dropped; Services keeps its two-column FAQ (heading left, answers right).
        self.assertNotIn('<details', self.home_main)
        self.assertNotIn('.questions', self.home_css)
        services = main_of((OUT / 'services/index.html').read_text())
        section = re.search(r'<section class="section" aria-labelledby="sv-faq-title">(.*?)</section>', services, re.S).group(1)
        self.assertIn('<h2 data-rise id="sv-faq-title" class="h-lg">Questions owners ask us</h2>', section)
        self.assertGreaterEqual(section.count('<details>'), 4)
        self.assertLess(section.index('<h2'), section.index('<details>'))
        self.assertIn('.faq-head{grid-column:1/span 4;', self.pages_css)
        self.assertIn('.faq-list{grid-column:6/-1;max-width:none}', self.pages_css)

    def test_every_page_class_has_a_css_rule(self):
        # The homepage loads site.css + home.css; inner pages load site.css + pages.css; /, /work/ and /pricing/ add kit.css.
        pages = Path(__file__).resolve().parents[1] / 'pages'
        checked = 0
        for page in pages.glob('*.html'):
            css = self.css + (self.home_css if page.stem == 'index' else self.pages_css)
            if page.stem in ('index', 'work', 'pricing'):
                css += self.kit_css
            classes = set()
            for attribute in re.findall(r'class="([^"]*)"', page.read_text()):
                classes.update(attribute.split())
            for name in sorted(classes):
                checked += 1
                with self.subTest(page=page.name, css_class=name):
                    self.assertRegex(css, rf'\.{re.escape(name)}(?![\w-])')
        self.assertTrue(checked)


def main_of(html):
    return html.split('<main id="main" tabindex="-1">', 1)[1].split('</main>', 1)[0]


def visible_text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


HEADERS = ("/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: DENY\n"
           "  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
           "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'\n")


class InnerPageTests(unittest.TestCase):
    """Work, Services, Pricing, Contact and Demo pages (Night Shift Task 9): static, honest, accessible."""
    ROUTES = SiteBuildTests.ROUTES
    INNER = [route for route in ROUTES if route != 'index.html']

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = {route: (OUT / route).read_text() for route in cls.ROUTES}
        cls.main = {route: main_of(html) for route, html in cls.html.items()}

    def test_work_route_title_and_description(self):
        html = self.html['work/index.html']
        self.assertIn('<title>Work — Cendavo</title>', html)
        self.assertIn('<a href="/work/" aria-current="page">Work</a>', html)
        self.assertRegex(html, r'<meta name="description" content="[^"]*fictional[^"]*">')

    def test_inner_pages_have_no_script_motion(self):
        # Contact and Demo stay fully static: no GSAP, no motion scripts and no motion hooks.
        for route in STATIC_ROUTES:
            with self.subTest(route=route):
                html = self.html[route].lower()
                for banned in ('gsap', 'ns-boot', 'ns-pages', 'ns.js', 'home.js', 'scrolltrigger', 'motion.js', 'motion-boot'):
                    self.assertNotIn(banned, html)
                for hook in MOTION_HOOKS:
                    self.assertNotIn(hook, self.html[route])
        # Every route: no prototype scripts, no home.js off the homepage, and no prototype notes in the content.
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = self.html[route].lower()
                for banned in ('ns-boot', 'ns-pages', 'ns.js', 'data-quote', 'data-hero-device'):
                    self.assertNotIn(banned, html)
                if route != 'index.html':
                    self.assertNotIn('home.js', html)
                    self.assertNotIn('data-intro', html)
                self.assertNotIn('Prototype', self.main[route])
                self.assertNotIn('proto-note', self.html[route])

    def test_motion_hooks_only_mark_existing_content(self):
        # Work, Services and Pricing: the page head opens with motion, headings rise, frames reveal, photos drift.
        for route in ('work/index.html', 'services/index.html', 'pricing/index.html'):
            with self.subTest(route=route):
                main = self.main[route]
                self.assertEqual(main.count(' data-ph '), 1)
                head = re.search(r'<section [^>]*data-ph [^>]*>.*?</section>', main, re.S).group(0)
                self.assertEqual(head.count('<h1'), 1)
                self.assertIn('data-ph-fade', head)
                self.assertIn('data-rise', main)
                self.assertIn('data-parallax', main)
                # Hooks are bare attributes: no inline values, styles or scripts ride along with them.
                for hook in re.findall(r'data-(?:ph|ph-fade|ph-media|rise|reveal|parallax|devices)(=?)', main):
                    self.assertEqual(hook, '')
        # Parallax and reveals only wrap images; parallax frames clip their overflow in CSS.
        for route in MOTION_ROUTES:
            for frame in re.findall(r'<(?:div|figure|span)[^>]*data-parallax[^>]*>(.*?)</(?:div|figure|span)>', self.main[route], re.S):
                with self.subTest(route=route, frame=frame[:50]):
                    # Exactly one photo: its <picture> (AVIF source, then the JPEG img) and nothing else.
                    self.assertRegex(frame.strip(), r'^<picture><source type="image/avif" [^>]*><img [^>]*></picture>$')

    def test_images_on_every_route_are_local_sized_and_described(self):
        for route in self.ROUTES:
            parser = ImageCollector()
            parser.feed(self.main[route])
            for index, (attrs, hidden) in enumerate(parser.images):
                with self.subTest(route=route, index=index, src=attrs.get('src')):
                    for name in ('src', 'srcset', 'sizes', 'width', 'height', 'alt'):
                        self.assertIn(name, attrs)
                    self.assertEqual(attrs.get('decoding'), 'async')
                    if index:
                        self.assertEqual(attrs.get('loading'), 'lazy')
                    if attrs.get('fetchpriority') == 'high':
                        self.assertEqual(index, 0)
                        self.assertNotIn('loading', attrs)
                    if not attrs['alt'].strip():
                        self.assertTrue(hidden, 'decorative images must sit inside an aria-hidden wrapper')
                    candidates = dict(reversed(part.split()) for part in attrs['srcset'].split(','))
                    self.assertEqual(set(candidates), {'800w', '1600w'})
                    small, large = candidates['800w'], candidates['1600w']
                    self.assertRegex(small, r'^/assets/images/[a-z-]+-800\.jpg$')
                    self.assertEqual(large, small.replace('-800.jpg', '-1600.jpg'))
                    self.assertIn(attrs['src'], (small, large))
                    for url in (small, large):
                        self.assertTrue((OUT / url.lstrip('/')).is_file(), url)
                    width, height = jpeg_size(OUT / large.lstrip('/'))
                    self.assertAlmostEqual(int(attrs['height']) / int(attrs['width']), height / width, delta=0.01 * height / width)
        for route in self.ROUTES:
            with self.subTest(route=route):
                # This photo shows a third-party product logo.
                self.assertNotIn('barber-tools', self.html[route])

    def test_every_route_has_one_h1_and_no_skipped_levels(self):
        for route in self.ROUTES:
            with self.subTest(route=route):
                main = self.main[route]
                self.assertEqual(main.count('<h1'), 1)
                levels = [int(n) for n in re.findall(r'<h([1-6])', main)]
                self.assertEqual(levels[0], 1)
                for previous, current in zip(levels, levels[1:]):
                    self.assertLessEqual(current, previous + 1)
                self.assertEqual(main.count('<details'), main.count('<summary>'))
                for details in re.findall(r'<details[^>]*>(.*?)</details>', main, re.S):
                    self.assertTrue(details.lstrip().startswith('<summary>'))

    def test_work_page_lists_three_labelled_concepts(self):
        main = self.main['work/index.html']
        articles = re.findall(r'<article\b[^>]*>(.*?)</article>', main, re.S)
        self.assertEqual(len(articles), 3)
        for article, name in zip(articles, ('Harbourside Mobile Detailing', 'Greenline Landscapes', 'Fade &amp; Co')):
            with self.subTest(project=name):
                self.assertEqual(article.count(CONCEPT_LABEL), 1)
                self.assertIn(f'>{name}</h2>', article)
        self.assertEqual(main.count(CONCEPT_LABEL), 3)
        self.assertIn('href="/demo/"', main)
        self.assertIn('href="/contact/"', main)
        self.assertIn('Demonstration project, sample data', main)
        text = visible_text(main).lower()
        for banned in ('testimonial', 'trusted by', 'award', '%', '$'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, text)
        for number in re.findall(r'\(0\d\)\s*[\d ]+', text):
            self.assertTrue(number.startswith('(02) 5550'))
        for address in re.findall(r'\b[\w-]+(?:\.[\w-]+)+\b', text):
            with self.subTest(address=address):
                self.assertTrue(address.endswith('.example'))

    def test_work_page_shows_key_screens_for_each_concept(self):
        # Task 12: each concept project shows 2-3 labelled device screens; the mock text and photos stay silent.
        main = self.main['work/index.html']
        rest, stems = main, set()
        for slug, name in (('harbourside', 'Harbourside'), ('greenline', 'Greenline'), ('fade-co', 'Fade and Co')):
            with self.subTest(project=slug):
                article = re.search(rf'<article [^>]*id="{slug}"[^>]*>(.*?)</article>', main, re.S).group(1)
                self.assertEqual(article.count(' data-devices'), 1)
                screens = re.search(r'<section class="cs-screens[^"]*" aria-labelledby="([^"]+)">(.*?)</section>', article, re.S)
                self.assertIsNotNone(screens)
                block = screens.group(2)
                rest = rest.replace(block, '')
                self.assertRegex(block, rf'<h3 id="{screens.group(1)}"[^>]*>Key screens</h3>')
                self.assertLess(block.index('Key screens'), block.index(' data-devices'))
                devices = re.findall(r'<div class="(?:laptop|phone)" role="img" aria-label="([^"]+)">', block)
                self.assertTrue(2 <= len(devices) <= 3, len(devices))
                self.assertEqual(block.count('role="img"'), len(devices))
                for label in devices:
                    self.assertIn(name, label)
                self.assertEqual(len(re.findall(r'<div class="(?:laptop|phone)-screen" aria-hidden="true">', block)), len(devices))
                parser = ImageCollector()
                parser.feed(block)
                self.assertTrue(parser.images)
                for attrs, hidden in parser.images:
                    with self.subTest(img=attrs.get('src')):
                        self.assertTrue(hidden)
                        self.assertEqual(attrs.get('alt'), '')
                        self.assertEqual(attrs.get('loading'), 'lazy')
                        self.assertEqual(attrs.get('decoding'), 'async')
                        self.assertTrue(attrs.get('width') and attrs.get('height'))
                        self.assertRegex(attrs['src'], r'^/assets/images/[a-z-]+-800\.jpg$')
                        stems.add(attrs['src'].rsplit('-', 1)[0])
        # Page weight: the screens load only these photos that the rest of the Work page does not already load. Until Task 24
        # this was a cap of eight; Task 24's brief moves Work's closing photo off garden-lawn while the Greenline mockup keeps
        # its garden-lawn screenshot, so that one becomes screen-only. The exact set is pinned so any further addition fails.
        elsewhere = {url.rsplit('-', 1)[0] for url in re.findall(r'/assets/images/[a-z-]+-(?:800|1600)\.jpg', rest)}
        self.assertEqual({stem.rsplit('/', 1)[1] for stem in stems - elsewhere},
                         {'barber-cut', 'barber-shave', 'detail-buffer', 'detail-dash', 'detail-splash', 'detail-wax',
                          'garden-deck', 'garden-lawn', 'garden-wall'})

    def test_inner_pages_make_no_unconfirmed_operational_promises(self):
        # The owner has not confirmed call length, timelines or staffing; say "a short free consultation" instead.
        # The one exception: About (Task 15) restates the homepage's published "fixed quote … in writing" commitment
        # (pages/index.html); every other inner page keeps the full list.
        for route in self.INNER:
            text = visible_text(self.main[route]).lower()
            with self.subTest(route=route):
                for banned in ('20-minute', 'twenty minutes', 'same person', 'a few weeks', 'in writing'):
                    if route == 'about/index.html' and banned == 'in writing':
                        continue
                    self.assertNotIn(banned, text)
                self.assertNotRegex(text, r'\d+\s*(day|week|hour|minute)')
        for route in ('services/index.html', 'pricing/index.html', 'contact/index.html'):
            with self.subTest(route=route):
                self.assertIn('free consultation', visible_text(self.main[route]))

    def test_contact_page_keeps_the_enquiry_contract(self):
        main = self.main['contact/index.html']
        self.assertEqual(main.count('<form '), 1)
        self.assertIn('<form data-enquiry class="form" method="post" novalidate>', main)
        # Layout wrappers only: the service select sits in a styling wrapper, controls keep their hooks.
        self.assertIn('<div class="select"><select id="enquiry-service" name="service" required aria-describedby="enquiry-service-error">', main)
        self.assertIn('<p class="notice" id="enquiry-privacy">', main)
        self.assertNotIn('@', main)
        self.assertNotIn('<script', main)

    def test_demo_table_scrolls_inside_a_labelled_region(self):
        # Supervisor review (Task 11): the page must not scroll sideways on phones. Every table sits in a focusable,
        # labelled overflow container, and the demo columns may shrink below the table's width (minmax(0,1fr), not 1fr).
        main = self.main['demo/index.html']
        self.assertGreaterEqual(main.count('<table'), 1)
        wraps = re.findall(r'<div class="table-wrap"([^>]*)><table\b', main)
        self.assertEqual(len(wraps), main.count('<table'))
        for attrs in wraps:
            with self.subTest(wrap=attrs):
                self.assertIn('role="region"', attrs)
                self.assertIn('tabindex="0"', attrs)
                label = re.search(r'aria-labelledby="([^"]+)"', attrs).group(1)
                self.assertRegex(main, rf'<h2 id="{re.escape(label)}">[^<]+</h2>')
        css = (OUT / 'assets/site.css').read_text() + (OUT / 'assets/pages.css').read_text()
        self.assertIn('.table-wrap{overflow-x:auto}', css)
        checked = 0
        for selector, body in re.findall(r'([^{}]*)\{([^{}]*)\}', css):
            if not re.search(r'\.demo-(?:shell|grid)(?![\w-])', selector):
                continue
            for value in re.findall(r'grid-template-columns:([^;]+)', body):
                checked += 1
                with self.subTest(selector=selector.strip()[:60], value=value):
                    self.assertNotRegex(value, r'(?<![,\w.])1fr')
        self.assertGreaterEqual(checked, 3)

    def test_no_inline_scripts_or_styles_and_headers_unchanged(self):
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = self.html[route]
                self.assertNotRegex(html, r'<script(?![^>]*\bsrc=)')
                self.assertNotIn(' style="', html)
                self.assertNotIn('<style', html)
        self.assertEqual((OUT / '_headers').read_text(), HEADERS)

    def test_digits_render_in_archivo_inside_body_text(self):
        css = (OUT / 'assets/site.css').read_text()
        faces = [(match.start(), match.group(1)) for match in re.finditer(r'@font-face\{([^}]*)\}', css)]
        atkinson = [start for start, face in faces if 'atkinson-hyperlegible' in face]
        digits = [(start, face) for start, face in faces if 'unicode-range' in face]
        self.assertEqual(len(atkinson), 2)
        self.assertTrue(digits)
        weights = set()
        for start, face in digits:
            with self.subTest(face=face[:60]):
                self.assertIn('font-family:"Atkinson Hyperlegible"', face)
                self.assertIn('unicode-range:U+0030-0039', face)
                self.assertIn('src:url("/assets/fonts/archivo-var-latin.woff2")', face)
                self.assertIn('font-display:swap', face)
                self.assertGreater(start, max(atkinson))  # later faces win for the characters they cover
                weight = re.search(r'font-weight:(\d+)(?: (\d+))?', face)
                low, high = int(weight.group(1)), int(weight.group(2) or weight.group(1))
                weights.update(w for w in (400, 700) if low <= w <= high)
        self.assertEqual(weights, {400, 700})


class PictureCollector(HTMLParser):
    """Collect every <img> with its parent tag name and the <source> elements of its enclosing <picture>."""

    def __init__(self):
        super().__init__()
        self.stack, self.sources, self.images = [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'picture':
            self.sources = []
        if tag == 'source':
            self.sources.append((attrs, self.stack[-1] if self.stack else None))
        elif tag == 'img':
            parent = self.stack[-1] if self.stack else None
            self.images.append((attrs, parent, list(self.sources) if parent == 'picture' else []))
        elif tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag not in VOID_ELEMENTS and self.stack:
            self.stack.pop()


class ImagePerformanceAndSharingTests(unittest.TestCase):
    """Night Shift Task 13: AVIF photos with JPEG fallback, canonical/Open Graph/Twitter metadata, and the 404 page."""
    ROUTES = SiteBuildTests.ROUTES
    PATHS = {'index.html': '/', 'work/index.html': '/work/', 'services/index.html': '/services/',
             'pricing/index.html': '/pricing/', 'demo/index.html': '/demo/', 'about/index.html': '/about/',
             'contact/index.html': '/contact/'}

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = {route: (OUT / route).read_text() for route in cls.ROUTES}

    def test_base_url_is_defined_once_and_used_by_the_sitemap(self):
        from scripts.build_site import BASE_URL
        self.assertEqual(BASE_URL, 'https://cendavo-deployment.pages.dev')
        source = (Path(__file__).resolve().parents[1] / 'scripts/build_site.py').read_text()
        self.assertEqual(source.count('cendavo-deployment.pages.dev'), 1)
        sitemap = (OUT / 'sitemap.xml').read_text()
        self.assertEqual(re.findall(r'<loc>([^<]+)</loc>', sitemap), [BASE_URL + path for path in self.PATHS.values()])

    def test_every_photo_has_an_avif_source_ahead_of_its_jpeg(self):
        total = 0
        for route in self.ROUTES:
            parser = PictureCollector()
            parser.feed(main_of(self.html[route]))
            total += len(parser.images)
            for attrs, parent, sources in parser.images:
                with self.subTest(route=route, src=attrs.get('src')):
                    self.assertEqual(parent, 'picture')
                    self.assertEqual(len(sources), 1)
                    source, source_parent = sources[0]
                    self.assertEqual(source_parent, 'picture')
                    self.assertEqual(source.get('type'), 'image/avif')
                    self.assertEqual(source.get('srcset'), attrs['srcset'].replace('.jpg', '.avif'))
                    self.assertEqual(source.get('sizes'), attrs['sizes'])
                    self.assertTrue(attrs['src'].endswith('.jpg'))  # the fallback img stays JPEG
                    urls = [part.split()[0] for part in source['srcset'].split(',')]
                    self.assertEqual(len(urls), 2)
                    for url in urls:
                        self.assertRegex(url, r'^/assets/images/[a-z-]+-(?:800|1600)\.avif$')
                        self.assertTrue((OUT / url.lstrip('/')).is_file(), url)
            with self.subTest(route=route):
                main = main_of(self.html[route])
                self.assertEqual(main.count('<picture>'), len(parser.images))
                # Task 28: the showreel's <video> has the one other <source> on the site (an mp4, on the homepage only).
                video_sources = re.findall(r'<source src="[^"]+\.mp4" type="video/mp4">', main)
                self.assertEqual(len(video_sources), 1 if route == 'index.html' else 0)
                self.assertEqual(main.count('<source '), len(parser.images) + len(video_sources))
        self.assertGreaterEqual(total, 40)

    def test_wrapping_keeps_the_original_img_markup(self):
        # The build only wraps: each img tag in the page source appears unchanged in the built page.
        pages = Path(__file__).resolve().parents[1] / 'pages'
        for route, path in self.PATHS.items():
            name = 'index' if path == '/' else path.strip('/')
            tags = re.findall(r'<img\b[^>]*>', (pages / f'{name}.html').read_text())
            built = main_of(self.html[route])
            for tag in tags:
                with self.subTest(route=route, tag=tag[:70]):
                    self.assertIn(f'>{tag}</picture>', built)
            self.assertEqual(built.count('<img '), len(tags))

    def test_picture_does_not_change_layout(self):
        css = (OUT / 'assets/site.css').read_text()
        self.assertIn('picture{display:contents}', base_rules(css))
        # display:contents promotes <picture>'s children into the parent grid/flex, and <source> is not
        # display:none by default, so every stylesheet using it must hide picture>source at top level.
        for name in ('site.css', 'home.css', 'pages.css', 'kit.css'):
            rules = base_rules((OUT / 'assets' / name).read_text())
            if re.search(r'(?:^|[}\s,])picture\s*\{[^}]*display\s*:\s*contents', rules):
                with self.subTest(stylesheet=name):
                    self.assertRegex(rules, r'(?:^|[}\s,])picture\s*>\s*source\s*\{[^}]*display\s*:\s*none')

    def test_no_img_selectors_broken_by_picture_wrapper(self):
        # Every photo is wrapped in <picture>, so child/sibling/position selectors on img would silently stop matching.
        fragile = re.compile(r'>\s*img\b|\bimg\s*[+~]|\bimg:(?:first|last|nth)-')
        for name in ('site.css', 'home.css', 'pages.css', 'kit.css'):
            css = re.sub(r'/\*.*?\*/', '', (OUT / 'assets' / name).read_text(), flags=re.S)
            selectors = re.findall(r'([^{}]+)\{', css)
            with self.subTest(stylesheet=name):
                self.assertEqual([s.strip() for s in selectors if fragile.search(s)], [])

    def test_canonical_open_graph_and_twitter_metadata(self):
        from scripts.build_site import BASE_URL
        for route, path in self.PATHS.items():
            html = self.html[route]
            head = html.split('</head>', 1)[0]
            url = BASE_URL + path
            title = re.search(r'<title>(.*?)</title>', head).group(1)
            desc = re.search(r'<meta name="description" content="([^"]*)">', head).group(1)
            expected = {'og:type': 'website', 'og:site_name': 'Cendavo', 'og:title': title, 'og:description': desc,
                        'og:url': url, 'og:image': BASE_URL + '/assets/social/cendavo-og.jpg', 'og:image:width': '1200',
                        'og:image:height': '630'}
            with self.subTest(route=route):
                self.assertEqual(head.count('rel="canonical"'), 1)
                self.assertIn(f'<link rel="canonical" href="{url}">', head)
                for name, value in expected.items():
                    with self.subTest(route=route, property=name):
                        self.assertEqual(re.findall(rf'<meta property="{re.escape(name)}" content="([^"]*)">', head), [value])
                alt = re.findall(r'<meta property="og:image:alt" content="([^"]*)">', head)
                self.assertEqual(len(alt), 1)
                self.assertTrue(alt[0].strip())
                self.assertEqual(head.count('<meta name="twitter:card" content="summary_large_image">'), 1)
                self.assertEqual(head.count('twitter:'), 1)
                self.assertNotIn('noindex', html)
        # Titles and descriptions keep their wording.
        self.assertIn('<title>Pricing — Cendavo</title>', self.html['pricing/index.html'])
        self.assertIn('<meta property="og:title" content="Cendavo — Website design for Sydney’s local service businesses">', self.html['index.html'])

    def test_share_card_is_1200_by_630(self):
        card = OUT / 'assets/social/cendavo-og.jpg'
        self.assertTrue(card.is_file())
        self.assertEqual(jpeg_size(card), (1200, 630))

    def test_not_found_page(self):
        from scripts.build_site import NAV
        self.assertTrue((OUT / '404.html').is_file())
        self.assertFalse((OUT / '404').exists())
        self.assertNotIn('404', (OUT / 'sitemap.xml').read_text())
        self.assertNotIn('404', ''.join(href for _, href in NAV))
        html = (OUT / '404.html').read_text()
        head = html.split('</head>', 1)[0]
        self.assertIn('<meta name="robots" content="noindex">', head)
        self.assertIn('<title>Page not found — Cendavo</title>', head)
        for banned in ('rel="canonical"', 'og:', 'twitter:'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, html)
        # Standard chrome: skip link, main target, header, header CTA, footer; no page marked current.
        self.assertIn('<body><a class="skip-link" href="#main">', html)
        self.assertIn('<main id="main" tabindex="-1">', html)
        self.assertIn('<header class="site-header">', html)
        self.assertIn('<a class="button small" href="/contact/">Request a free consultation</a>', html)
        self.assertIn('<footer class="footer">', html)
        self.assertNotIn('aria-current', html)
        self.assertIn('<link rel="stylesheet" href="/assets/pages.css">', html)
        self.assertNotIn('kit.css', html)
        self.assertNotIn('home.css', html)
        # No motion: no GSAP, motion scripts or hooks; only the shared site script.
        self.assertEqual(re.findall(r'<script src="([^"]+)"', html), ['/assets/site.js'])
        for hook in MOTION_HOOKS:
            self.assertNotIn(hook, html)
        main = main_of(html)
        self.assertEqual(main.count('<h1'), 1)
        for href in ('/', '/work/', '/contact/'):
            with self.subTest(href=href):
                self.assertIn(f'href="{href}"', main)
        self.assertNotIn('<img', main)
        self.assertNotIn(' style="', html)


class AboutPageTests(unittest.TestCase):
    """Night Shift Task 15: an honest About page. The owner has given no names, credentials, client history or years in
    business, so the page restates commitments the site already makes and claims nothing else."""
    ROUTE = 'about/index.html'
    # Phrases that would state or imply size, history, endorsements or guarantees nobody has confirmed.
    INVENTED_CLAIMS = ('years of experience', 'years in business', 'since 19', 'since 20', 'founded', 'award',
                       'clients include', 'trusted by', 'testimonial', 'certified', 'guarantee', 'lock-in',
                       'month to month', 'team of', '%', '$')

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = (OUT / cls.ROUTE).read_text()
        cls.head = cls.html.split('</head>', 1)[0]
        cls.main = main_of(cls.html)
        cls.text = visible_text(cls.main).lower()
        cls.source = (Path(__file__).resolve().parents[1] / 'pages/about.html').read_text()

    def test_title_description_and_sharing_metadata(self):
        from scripts.build_site import BASE_URL
        url = BASE_URL + '/about/'
        self.assertIn('<title>About — Cendavo</title>', self.head)
        desc = re.search(r'<meta name="description" content="([^"]*)">', self.head).group(1)
        self.assertIn('Sydney', desc)
        self.assertIn('local service businesses', desc)
        self.assertIn(f'<link rel="canonical" href="{url}">', self.head)
        self.assertEqual(re.findall(r'<meta property="og:url" content="([^"]*)">', self.head), [url])
        self.assertIn(f'<loc>{url}</loc>', (OUT / 'sitemap.xml').read_text())

    def test_nav_marks_only_about_as_current(self):
        current = re.findall(r'<a href="([^"]+)" aria-current="page">([^<]+)</a>', self.html)
        self.assertEqual(self.html.count('aria-current'), len(current))
        self.assertEqual(set(current), {('/about/', 'About')})
        for route in SiteBuildTests.ROUTES:
            if route != self.ROUTE:
                with self.subTest(route=route):
                    self.assertNotIn('href="/about/" aria-current', (OUT / route).read_text())
                    self.assertIn('<a href="/about/">About</a>', (OUT / route).read_text())

    def test_sections_appear_in_order(self):
        self.assertEqual(self.main.count('<h1'), 1)
        h2s = [visible_text(h).strip() for h in re.findall(r'<h2[^>]*>(.*?)</h2>', self.main, re.S)]
        # Night Shift Task 18: "What you can expect" repeated Services and Pricing; it is now one line in "How we build"
        # that links to Pricing's full list.
        self.assertEqual(h2s[:2], ['How we think', 'How we build'])
        # Night Shift Task 28: the trades row moved here from the homepage, just before the closing call to action.
        self.assertEqual(h2s[2], 'Built for the businesses that keep Sydney running')
        self.assertEqual(len(h2s), 4)  # the fourth is the closing call to action
        self.assertLess(self.main.index('<section class="who bone"'), self.main.index('<section class="cta-band ab-closing"'))
        self.assertGreater(self.main.index('<section class="who bone"'), self.main.index('<section class="ab-build"'))
        think = self.main.split('id="ab-think-title"', 1)[1].split('<h2', 1)[0]
        self.assertTrue(3 <= think.count('<h3') <= 4)
        self.assertNotIn('ab-expect-title', self.source)
        self.assertNotIn('class="exp"', self.source)
        # "How we build" is one typographic band: four large statements, no card grid and no photo.
        build = re.search(r'<section class="ab-build" aria-labelledby="ab-build-title">(.*?)</section>', self.main, re.S).group(1)
        self.assertNotIn('inc-grid', build)
        self.assertNotIn('<img', build)
        self.assertEqual(re.search(r'<ul class="ab-build-list">(.*?)</ul>', build, re.S).group(1).count('<li>'), 4)
        promise = re.search(r'<p class="ab-promise">(.*?)</p>', build, re.S).group(1)
        self.assertIn('<a class="ulink strong" href="/pricing/">What every project includes</a>', promise)
        closing = self.main.rsplit('<section', 1)[1]
        self.assertIn('href="/contact/">Request a free consultation</a>', closing)

    def test_states_only_published_commitments(self):
        for fact in ('sydney', 'fixed quote', 'in writing', 'domain', 'plain language', 'the care plan is optional'):
            with self.subTest(fact=fact):
                self.assertIn(fact, self.text)
        # "In writing" appears only as the homepage's published quote commitment.
        self.assertEqual(self.text.count('in writing'), self.text.count('fixed price in writing'))
        for banned in self.INVENTED_CLAIMS + SiteBuildTests.SAAS_WORDING:
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.text)
        self.assertNotRegex(self.text, r'\d+\s*\+?\s*(clients|projects|websites|years)')
        self.assertNotRegex(self.text, r'\d+\+')

    def test_photos_are_existing_described_and_few(self):
        # Night Shift Task 21: the opening holds three decorative 4:5 photos beside the headline; below it, at most two more.
        hero, rest = self.main.split('</section>', 1)
        parser = ImageCollector()
        parser.feed(hero)
        names = [re.search(r'/images/([a-z-]+)-(?:800|1600)\.jpg$', attrs['src']).group(1) for attrs, _ in parser.images]
        self.assertEqual(names, ['barber-shave', 'garden-wall', 'detail-wax'])
        self.assertIn('<div class="ab-photos" aria-hidden="true">', hero)
        for index, (attrs, hidden) in enumerate(parser.images):
            with self.subTest(hero_photo=names[index]):
                self.assertTrue(hidden)
                self.assertEqual(attrs.get('alt'), '')
                self.assertTrue(attrs.get('width') and attrs.get('height'))
                self.assertEqual(attrs.get('decoding'), 'async')
                # Only the first loads straight away; the other two are lazy.
                self.assertEqual(attrs.get('loading'), 'lazy' if index else None)
                self.assertRegex(attrs['src'], r'-800\.jpg$')
                self.assertNotIn('fetchpriority', attrs)
        self.assertEqual(hero.count('<picture><source type="image/avif" '), 3)
        # The intro paragraph sits directly under the headline, before the photos.
        self.assertRegex(hero, r'</h1>\s*<p class="pg-sub">')
        self.assertLess(hero.index('</h1>'), hero.index('ab-photos'))
        below = ImageCollector()
        below.feed(rest)
        # Below the opening: the "How we think" photo, the five trades photos moved from the homepage (Task 28, same
        # photos, alt text and captions) and the closing photo. The exact set is pinned so any further addition fails.
        names = [re.search(r'/images/([a-z-]+)-(?:800|1600)\.jpg$', attrs['src']).group(1) for attrs, _ in below.images]
        self.assertEqual(names, ['barber-cut', 'clean-living', 'trade-panel', 'barber-cut', 'garden-lawn', 'detail-wax', 'garden-deck'])
        row = re.search(r'<ul class="who-row">(.*?)</ul>', rest, re.S).group(1)
        self.assertEqual(re.findall(r'<figcaption>([^<]+)</figcaption>', row),
                         ['Cleaners', 'Electricians and trades', 'Barbers', 'Landscapers', 'Mobile detailers'])
        self.assertEqual(re.findall(r' alt="([^"]+)"', row),
                         ['A cleaner mopping the floor of a bright living room', 'An electrician in gloves testing a switchboard with probes',
                          'A barber trimming the back of a client’s hair with scissors', 'A landscaped backyard with a stone wall, pergola and lawn',
                          'A detailer fitting protective film over the headlight of a grey car'])
        self.assertEqual(row.count(' data-parallax>'), 5)
        described = [attrs for attrs, hidden in below.images if not hidden]
        self.assertTrue(described)
        for attrs, _ in below.images:
            with self.subTest(src=attrs['src']):
                self.assertEqual(attrs.get('loading'), 'lazy')  # every photo below the opening is lazy
        for attrs in described:
            self.assertTrue(attrs['alt'].strip())
        self.assertNotIn('barber-tools', self.html)

    def test_opening_sets_copy_left_and_staggered_photos_right(self):
        css = (OUT / 'assets/pages.css').read_text()
        base = base_rules(css)
        self.assertIn('grid-column:1/span 5', rules_for(base, '.ab-hero-copy')[0])
        photos = rules_for(base, '.ab-photos')[0]
        self.assertIn('grid-column:6/-1', photos)
        self.assertIn('gap:16px', photos)
        self.assertIn('margin-right:calc(-1 * var(--gut))', photos)  # runs past the right gutter
        self.assertIn('aspect-ratio:4/5', rules_for(base, '.ab-photo')[0])
        self.assertEqual(rules_for(base, '.ab-photo:nth-child(2)'), ['margin-top:64px'])
        self.assertEqual(rules_for(base, '.ab-photo:nth-child(3)'), ['margin-top:32px'])
        self.assertIn('overflow:hidden', rules_for(base, '.ab-hero')[0])  # the bleed never widens the page
        narrow = media_blocks(css, 'max-width:900px')
        self.assertIn('grid-column:1/-1', rules_for(narrow, '.ab-photos')[0])
        self.assertIn('margin:40px 0 0', rules_for(narrow, '.ab-photos')[-1])

    def test_reuses_shared_assets_and_motion_hooks_only(self):
        self.assertEqual(re.findall(r'<link rel="stylesheet" href="([^"]+)">', self.head), ['/assets/site.css', '/assets/pages.css'])
        scripts = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertEqual(scripts, ['/assets/motion-boot.js', '/assets/site.js', '/assets/vendor/gsap/gsap.min.js',
                                   '/assets/vendor/gsap/ScrollTrigger.min.js', '/assets/motion.js'])
        self.assertNotIn('data-intro', self.html)
        # Night Shift Task 23: About opens like Work, Services and Pricing (headline line masks, staggered photo reveal).
        self.assertEqual(self.main.count(' data-ph '), 1)
        self.assertEqual(self.main.count(' data-ph-media>'), 3)
        self.assertNotIn('data-ph-fade', self.main)  # the intro paragraph is never held back
        self.assertIn('data-rise', self.main)
        for hook in re.findall(r'data-(?:rise|reveal|parallax)(=?)', self.main):
            self.assertEqual(hook, '')
        self.assertNotIn('http', self.source)


def media_blocks(css, query):
    """Concatenated bodies of every `@media(query){...}` block in css."""
    return ''.join(without_blocks(css, f'@media({query}){{')[1])


def rules_for(css, selector):
    """Bodies of every rule whose comma-separated selector list contains `selector` exactly."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    return [body for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css)
            if selector in [part.strip() for part in selectors.split(',')]]


def gradient_stops(gradient):
    """[(alpha, position %)] for a linear-gradient's ink stops (`rgba(14,14,13,a) p%` or `var(--ink) p%`)."""
    stops = []
    for colour, position in re.findall(r'(rgba\(14,14,13,[\d.]+\)|var\(--ink\)) ([\d.]+)%', gradient):
        alpha = 1.0 if colour == 'var(--ink)' else float(re.search(r',([\d.]+)\)$', colour).group(1))
        stops.append((alpha, float(position)))
    return stops


def ink_over_white(alpha, ink='#0E0E0D'):
    """Hex colour of ink at `alpha` composited over pure white (the worst case for light text)."""
    channels = [int(ink.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    return '#' + ''.join(f'{round(alpha * c + (1 - alpha) * 255):02X}' for c in channels)


class DesignCritiqueFixTests(unittest.TestCase):
    """Night Shift Task 17: fixes from the independent design critique (docs/design/night-shift/critique/CRITIQUE.md)."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = (OUT / 'assets/site.css').read_text()
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.pages_css = (OUT / 'assets/pages.css').read_text()
        cls.home = main_of((OUT / 'index.html').read_text())
        cls.work = main_of((OUT / 'work/index.html').read_text())
        root = re.search(r':root\{(.*?)\}', cls.css, re.S).group(1)
        cls.tokens = {k: v.strip() for k, v in re.findall(r'(--[\w-]+):([^;]+)', root)}

    def test_work_index_sits_inside_the_page_gutter(self):
        self.assertIn('<ul class="wrap wk-index">', self.work)
        self.assertIn('.wrap{width:100%;max-width:var(--max);margin-inline:auto;padding-inline:var(--gut)}', self.css)
        base = base_rules(self.pages_css)
        rules = rules_for(base, '.wk-index')
        self.assertEqual(len(rules), 1)  # no shared list reset overrides .wrap's gutter any more
        rule = rules[0]
        self.assertNotRegex(rule, r'(?<![-\w])(?:margin|padding)(?:-inline|-left|-right)?:')
        self.assertIn('grid-template-columns:repeat(4,minmax(0,1fr))', rule)
        self.assertIn('gap:24px', rule)
        self.assertNotIn('.6fr', self.pages_css)
        tablet = rules_for(media_blocks(self.pages_css, 'max-width:860px'), '.wk-index')
        self.assertEqual(tablet, ['grid-template-columns:repeat(2,minmax(0,1fr));gap:28px 12px'])
        self.assertEqual(rules_for(media_blocks(self.pages_css, 'max-width:640px'), '.wk-index'), ['padding-inline:16px'])

    def test_harbourside_cover_text_meets_contrast_over_white(self):
        base = base_rules(self.pages_css)
        self.assertIn('#harbourside .cs-cover-media img{object-position:70% 50%}', base)
        self.assertIn('#harbourside .cs-label,#harbourside .cs-facts{max-width:44%}', base)
        stone, bone = self.tokens['--stone'], self.tokens['--bone']
        # Text colours: the label and fact terms are stone; fact values and the title inherit the body's bone.
        self.assertIn('color:var(--stone)', rules_for(base, '.cs-label')[0])
        self.assertIn('color:var(--stone)', rules_for(base, '.cs-facts dt')[0])
        for selector in ('.cs-facts dd', '.cs-title'):
            for rule in rules_for(base, selector):
                self.assertNotRegex(rule, r'(?<![-\w])color:')
        self.assertRegex(self.css, r'(?:^|[}\n])body\{[^}]*;color:var\(--bone\)')
        # Wide screens: the left scrim holds its darkest value across the left half, where the 44%-wide copy sits.
        # Phones/tablets (<=860px): the copy overlaps the bottom 18vw (at most about 28%) of the photo.
        for name, css, hold in (('wide', base, 50), ('narrow', media_blocks(self.pages_css, 'max-width:860px'), 28)):
            with self.subTest(layout=name):
                rules = rules_for(css, '#harbourside .cs-cover-media::after')
                self.assertEqual(len(rules), 1)
                first = re.search(r'background:linear-gradient\(([^()]*(?:\([^()]*\)[^()]*)*)\)', rules[0]).group(1)
                stops = gradient_stops(first)
                held = [alpha for alpha, position in stops if position <= hold]
                self.assertTrue(held)
                self.assertTrue(any(position >= hold and alpha >= 0.85 for alpha, position in stops), stops)
                alpha = min(held + [a for a, p in stops if p >= hold][:1])
                self.assertGreaterEqual(alpha, 0.85)
                backdrop = ink_over_white(alpha)
                for text, colour, minimum in (('label', stone, 4.5), ('dt', stone, 4.5), ('dd', bone, 4.5), ('title', bone, 3)):
                    with self.subTest(layout=name, text=text):
                        self.assertGreaterEqual(contrast(colour, backdrop), minimum)

    def test_concept_label_sits_under_each_title(self):
        home = re.findall(r'<article class="teaser-card"[^>]*>(.*?)</article>', self.home, re.S)
        work = re.findall(r'<article\b[^>]*>(.*?)</article>', self.work, re.S)
        self.assertEqual((len(home), len(work)), (3, 3))
        for page, articles, closing in (('home', home, '</a></h3>'), ('work', work, '</h2>')):
            for article in articles:
                with self.subTest(page=page, article=article[:60]):
                    self.assertEqual(article.count(CONCEPT_LABEL), 1)
                    label = article.index(CONCEPT_LABEL)
                    title = article.index(closing)
                    self.assertGreater(label, title)
                    # Directly under the title: nothing but whitespace and the label's own opening tag between them.
                    self.assertRegex(article[title + len(closing):label], r'^\s*<p class="(?:teaser|cs)-label">$')
        self.assertIn('<p class="hero-cap">Harbourside Mobile Detailing<span>Concept project · fictional business</span></p>', self.home)
        self.assertIn('.teaser-card h3{margin:20px 0 0;', self.home_css)
        self.assertIn('.teaser-label{margin:10px 0 0;', self.home_css)

    def test_showreel_frame_stays_inside_the_viewport(self):
        # Night Shift Task 28 replaces the pinned devices with the showreel: its frame is never taller than the viewport
        # allows (62svh on wide screens, 74svh for the vertical cut on phones) and never wider than its column.
        base = base_rules(self.home_css)
        frame = rules_for(base, '.reel-frame')[0]
        self.assertIn('width:min(100%,calc(62svh * 16 / 9))', frame)
        self.assertIn('aspect-ratio:16/9', frame)
        phone = rules_for(media_blocks(self.home_css, 'max-width:640px'), '.reel-frame')[0]
        self.assertIn('width:min(100%,calc(74svh * 9 / 16))', phone)
        self.assertIn('aspect-ratio:9/16', phone)

    def test_mobile_hero_overlays_the_copy_on_a_darkened_photo(self):
        phone = media_blocks(self.home_css, 'max-width:640px')
        hero = rules_for(phone, '.hero')[0]
        self.assertIn('min-height:calc(100svh - 77px)', hero)
        self.assertIn('justify-content:flex-end', hero)
        photo = rules_for(phone, '.hero-photo')[0]
        self.assertIn('position:absolute', photo)
        self.assertIn('inset:0', photo)
        self.assertIn('z-index:-1', photo)
        scrim = rules_for(phone, '.hero-photo::after')[0]
        alpha = float(re.search(r'linear-gradient\(0deg,rgba\(14,14,13,([\d.]+)\) 0%', scrim).group(1))
        self.assertGreaterEqual(alpha, 0.85)
        self.assertEqual(rules_for(phone, '.hero-device'), ['display:none'])
        source = (Path(__file__).resolve().parents[1] / 'pages/index.html').read_text()
        self.assertIn('<img src="/assets/images/detail-darkroom-1600.jpg" srcset="/assets/images/detail-darkroom-800.jpg 800w, '
                      '/assets/images/detail-darkroom-1600.jpg 1600w" sizes="(max-width: 900px) 100vw, 64vw" width="1600" '
                      'height="1067" alt="The front of a black classic sedan in a dark garage, its round headlights glowing warm '
                      'amber" fetchpriority="high" decoding="async">', source)

    def test_services_rows_do_not_slide(self):
        self.assertNotIn('translateX(', self.home_css)
        self.assertNotRegex(self.home_css, r'\.svc[^{]*h3\{[^}]*transition')
        # Night Shift Task 21: no scale on inactive rows (it misaligned their edges); the photo panel crossfades instead.
        self.assertNotIn('scale(.94)', self.home_css)
        _, guarded = without_blocks(self.home_css, MOTION_GUARD)
        self.assertIn('.svc-panel.is-live .svc-photo.is-active{opacity:1;transition-delay:0s}', ''.join(guarded))

    def test_contact_has_no_photo_sliver_and_one_line_of_expectations(self):
        # Night Shift Task 21 (second critique): the thin photo band under the steps is gone on every screen size, and
        # "What to expect from us" is one short line under the submit button instead of another heading and grid.
        html = (OUT / 'contact/index.html').read_text()
        main = main_of(html)
        self.assertNotIn('ct-photo', html)
        self.assertNotIn('ct-photo', self.pages_css)
        self.assertNotIn('detail-headlight', html)
        self.assertNotIn('<img', main)
        self.assertNotIn('What to expect from us', html)
        self.assertNotIn('ct-expect', html)
        self.assertNotRegex(self.pages_css, r'\.exp(?![\w-])')
        foot = re.search(r'<div class="form-foot">(.*?)</div></form>', main, re.S).group(1)
        self.assertRegex(foot, r'^<button class="button large" type="submit">Send enquiry</button><p class="form-promise">[^<]{20,120}</p>'
                               r'<p class="notice" id="enquiry-privacy">')
        line = re.search(r'<p class="form-promise">([^<]+)</p>', foot).group(1)
        for claim in ('person', 'plain language', 'no hard sell'):
            self.assertIn(claim, line)
        self.assertEqual(rules_for(base_rules(self.pages_css), '.form-promise'), ['margin:0;max-width:62ch;font-size:.9375rem'])


class RepetitionTests(unittest.TestCase):
    """Night Shift Task 18: fewer repeated devices across pages (footer, closing photos, pricing steps, list markers)."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.routes = SiteBuildTests.ROUTES + ['404.html']
        cls.html = {route: (OUT / route).read_text() for route in cls.routes}
        cls.css = (OUT / 'assets/site.css').read_text()
        cls.pages_css = (OUT / 'assets/pages.css').read_text()
        cls.home_css = (OUT / 'assets/home.css').read_text()

    def test_footer_signature_replaces_the_repeated_button(self):
        for route in self.routes:
            with self.subTest(route=route):
                footer = self.html[route].split('<footer class="footer">', 1)[1].split('</footer>', 1)[0]
                self.assertNotIn('class="button', footer)
                # The wordmark is decorative: one aria-hidden frame, after the legal lines, holding only the word.
                self.assertEqual(footer.count('footer-sign'), 1)
                self.assertTrue(footer.endswith('<div class="footer-sign" aria-hidden="true"><span class="footer-word">CENDAVO</span></div>'))
                self.assertLess(footer.index('class="footer-bottom"'), footer.index('footer-sign'))
                # The text logo is still the one accessible name in the footer.
                self.assertEqual(visible_text(footer.split('footer-sign', 1)[0]).count('CENDAVO'), 1)
                self.assertIn('Sydney, Australia.', footer)
        rule = rules_for(base_rules(self.css), '.footer-sign')
        self.assertEqual(len(rule), 1)
        rule = rule[0]
        self.assertIn('overflow:hidden', rule)  # crops the letters and never widens the page on a phone
        self.assertIn('white-space:nowrap', rule)
        self.assertIn('var(--font-display)', rule)  # Archivo, already preloaded: no new font download
        self.assertIn('font-stretch:125%', rule)
        height = float(re.search(r'height:([\d.]+)em', rule).group(1))
        line = float(re.search(r'/([\d.]+) var\(--font-display\)', rule).group(1))
        self.assertLess(height, line)  # shorter than the line box, so the bottom of the word is cut off
        # Low contrast on purpose: it is a texture, not text anyone needs to read.
        colour = re.search(r'(?<![-\w])color:(#[0-9A-Fa-f]{6})', rule).group(1)
        self.assertLess(contrast(colour, '#0E0E0D'), 1.5)

    def test_closing_photo_differs_per_page(self):
        # Night Shift Task 21: Services no longer opens and closes on barbershop photos.
        # Night Shift Task 24: Services no longer closes on its own New website photo, and garden-lawn closes no page.
        expected = {'index.html': 'detail-rear', 'work/index.html': 'detail-rear', 'services/index.html': 'garden-path',
                    'pricing/index.html': 'garden-deck', 'about/index.html': 'garden-deck'}
        for route, photo in expected.items():
            with self.subTest(route=route):
                main = main_of(self.html[route])
                band = re.search(r'<div class="(?:cta-)?band-media" aria-hidden="true" data-parallax>(.*?)</div>', main, re.S)
                self.assertIsNotNone(band)
                self.assertEqual(set(re.findall(r'/assets/images/([a-z-]+)-(?:800|1600)\.(?:jpg|avif)', band.group(1))), {photo})
                self.assertTrue(main.rstrip().endswith('</section>'))
                self.assertGreater(main.index(band.group(0)), main.rindex('<section'))  # it is the page's last section
        for route in ('contact/index.html', 'demo/index.html', '404.html'):
            with self.subTest(route=route):
                self.assertNotIn('cta-band', self.html[route])
        for route in self.routes:
            with self.subTest(route=route):
                self.assertNotIn('barber-tools', self.html[route])

    def test_pricing_steps_sit_on_one_timeline(self):
        main = main_of(self.html['pricing/index.html'])
        steps = re.search(r'<ol class="pr-steps">(.*?)</ol>', main, re.S).group(1)
        items = re.findall(r'<li class="pr-step">(.*?)</li>', steps, re.S)
        self.assertEqual(len(items), 3)
        for number, item in enumerate(items, 1):
            with self.subTest(step=number):
                self.assertIn(f'<span class="pr-step-n" aria-hidden="true">{number}</span><h3>', item)
        base = base_rules(self.pages_css)
        line = rules_for(base, '.pr-steps::before')
        self.assertEqual(len(line), 1)
        self.assertIn('height:1px', line[0])
        self.assertIn('left:0;right:0', line[0])
        self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', rules_for(base, '.pr-steps')[-1])
        # No card per step: no background, border or shadow on the items themselves.
        for rule in rules_for(base, '.pr-step'):
            with self.subTest(rule=rule):
                self.assertNotRegex(rule, r'(?<![-\w])(?:background|border|box-shadow)(?:-[a-z]+)?:')
        # Small screens (900px and below, so every phone): one column, the rule turns vertical down the left.
        narrow = media_blocks(self.pages_css, 'max-width:900px')
        self.assertIn('grid-template-columns:1fr', rules_for(narrow, '.pr-steps')[0])
        vertical = rules_for(narrow, '.pr-steps::before')[0]
        self.assertIn('width:1px', vertical)
        self.assertIn('top:0;bottom:0', vertical)

    def test_list_markers_are_small_squares_not_dashes(self):
        rule = rules_for(base_rules(self.pages_css), '.tick li::before')[0]
        self.assertIn('width:6px', rule)
        self.assertIn('height:6px', rule)
        self.assertIn('background:var(--amber)', rule)
        for name, css in (('site.css', self.css), ('pages.css', self.pages_css), ('home.css', self.home_css)):
            with self.subTest(css=name):
                self.assertNotRegex(css, r'content:\s*"[^"]*[—–-][^"]*"')
                self.assertNotIn('\\2014', css)


# Night Shift Task 20: the Work page's Harbourside case study is left exactly as it was (sha256 of its source <article>).
HARBOURSIDE_SHA256 = '55eee74d6abbd44b17cffe7bd56b4704abae5169c6eaedd2c2d38b558a4a1301'
# The photos /work/ referenced before Task 20; the new art direction reuses them and adds no new downloads.
# Task 24 adds detail-rear (the closing photo, already used on Home); garden-lawn stays inside the Greenline mockup.
WORK_PHOTOS = {'barber-chair', 'barber-cut', 'barber-interior', 'barber-shave', 'detail-buffer', 'detail-dash', 'detail-headlight',
               'detail-mono', 'detail-rear', 'detail-splash', 'detail-wax', 'garden-deck', 'garden-lawn', 'garden-path', 'garden-walk',
               'garden-wall'}


class WorkArtDirectionTests(unittest.TestCase):
    """Night Shift Task 20: three concept projects, three art directions (Harbourside as is, Greenline mirrored with a pull
    line and overlapping screens, Fade & Co led by its screens on a dimmed photo band), in markup and CSS only."""

    @classmethod
    def setUpClass(cls):
        build()
        root = Path(__file__).resolve().parents[1]
        cls.source = (root / 'pages/work.html').read_text()
        cls.work = main_of((OUT / 'work/index.html').read_text())
        cls.pages_css = (OUT / 'assets/pages.css').read_text()
        cls.base = base_rules(cls.pages_css)
        cls.narrow = media_blocks(cls.pages_css, 'max-width:860px')
        site = (OUT / 'assets/site.css').read_text()
        cls.tokens = {k: v.strip() for k, v in re.findall(r'(--[\w-]+):([^;]+)', re.search(r':root\{(.*?)\}', site, re.S).group(1))}

    def article(self, slug, html=None):
        return re.search(rf'<article [^>]*id="{slug}"[^>]*>.*?</article>', html or self.source, re.S).group(0)

    def test_harbourside_is_unchanged(self):
        import hashlib
        self.assertEqual(hashlib.sha256(self.article('harbourside').encode()).hexdigest(), HARBOURSIDE_SHA256)
        self.assertEqual(re.findall(r'<article [^>]*id="([^"]+)"', self.source), ['harbourside', 'greenline', 'fade-co'])

    def test_greenline_is_mirrored_with_a_pull_line(self):
        gl = self.article('greenline')
        self.assertIn('grid-column:1/span 7', rules_for(self.base, '.gl-cover-media')[0])
        self.assertIn('grid-column:8/-1', rules_for(self.base, '.gl-cover-copy')[0])
        # Mirrored in CSS only: the copy (and its h2) still comes before the photo, and the screens follow the cover.
        self.assertLess(gl.index('class="gl-cover-copy"'), gl.index('</h2>'))
        self.assertLess(gl.index('</h2>'), gl.index('class="gl-cover-media"'))
        self.assertLess(gl.index('</header>'), gl.index('<section class="cs-screens'))
        self.assertLess(gl.index('<section class="cs-screens'), gl.index('class="cs-brief"'))
        brief = re.search(r'<section class="cs-brief"[^>]*>(.*?)</section>', gl, re.S).group(1)
        self.assertEqual(re.findall(r'<p class="([^"]+)"', brief), ['gl-pull'])
        self.assertEqual(len(re.findall(r'<li><b>', gl)), 3)  # the three "what the site does" points stay
        pull = rules_for(self.base, '.gl-pull')
        self.assertEqual(len(pull), 1)
        self.assertIn('clamp(1.9rem,3.4vw,3.25rem)', pull[0])
        self.assertIn('var(--font-display)', pull[0])

    def test_greenline_screens_overlap_the_cover_on_wide_screens_only(self):
        stage = rules_for(self.base, '.stage-gl')
        self.assertEqual(len(stage), 1)
        self.assertIn('margin-top:calc(var(--gl-lift) * -1)', stage[0])
        self.assertRegex(stage[0], r'--gl-lift:clamp\(\d+px,\d+vw,\d+px\)')
        # The phone drops below "Key screens" by the full lift, so only the laptop rises over the photo.
        self.assertIn('calc(var(--gl-lift) + 24px)', rules_for(self.base, '.stage-gl .scr-phone')[0])
        self.assertIn('overflow-x:clip', rules_for(self.base, '#greenline .cs-screens')[0])
        narrow = rules_for(self.narrow, '.stage-gl')
        self.assertEqual(len(narrow), 1)
        self.assertIn('margin-top:0', narrow[0])
        self.assertEqual(rules_for(self.narrow, '.stage-gl .scr-phone'), ['margin:40px auto 0'])
        self.assertEqual(rules_for(self.narrow, '#greenline .cs-screens .pg-label'), ['margin:0 0 40px'])
        # Phones (390px): nothing in the small-screen rules is wider than the viewport.
        for css in (self.narrow, media_blocks(self.pages_css, 'max-width:640px'), media_blocks(self.pages_css, 'max-width:900px')):
            for px in re.findall(r'(?<![-\w])(?:min-)?width:(\d+)px', css):
                self.assertLessEqual(int(px), 390)
            for vw in re.findall(r'([\d.]+)vw', css):
                self.assertLessEqual(float(vw), 100)

    def test_greenline_green_is_one_sparing_accessible_accent(self):
        greenline = [(selectors, body) for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', self.pages_css, flags=re.S))
                     if '#greenline' in selectors or '.gl-' in selectors]
        colours = {c.upper() for _, body in greenline for c in re.findall(r'#[0-9A-Fa-f]{6}\b', body)}
        self.assertEqual(colours, {'#23422F'})
        self.assertLessEqual(self.pages_css.upper().count('#23422F'), 3)
        self.assertIn('color:#23422F', rules_for(self.base, '#greenline .cs-label')[0])
        self.assertGreaterEqual(contrast('#23422F', self.tokens['--bone']), 4.5)

    def test_fade_co_leads_with_its_screens_on_a_dimmed_band(self):
        fc = self.article('fade-co')
        self.assertNotIn('cs-cover', fc)
        order = ['</h2>', CONCEPT_LABEL, '<dl class="cs-facts">', '</header>', '<div class="fc-band" aria-hidden="true"',
                 '<section class="cs-screens', 'class="cs-brief"', 'class="cs-does"']
        positions = [fc.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))
        band = re.search(r'<div class="fc-band"[^>]*>(.*?)</div>', fc, re.S).group(1)
        screens = re.search(r'<section class="cs-screens[^"]*"[^>]*>.*?</section>', fc, re.S).group(0)
        self.assertNotIn('fc-band', screens)
        parser = ImageCollector()
        parser.feed(band)
        self.assertEqual(len(parser.images), 1)
        attrs, _ = parser.images[0]
        self.assertRegex(attrs['src'], r'^/assets/images/barber-interior-(?:800|1600)\.jpg$')
        self.assertIn('barber-interior-800.jpg 800w', attrs['srcset'])
        self.assertTrue(attrs.get('sizes'))
        self.assertEqual((attrs.get('alt'), attrs.get('loading'), attrs.get('decoding')), ('', 'lazy', 'async'))
        # Dimming: a solid ink overlay (no CSS filter), checked over pure white as the worst case.
        overlay = rules_for(self.base, '.fc-band::after')
        self.assertEqual(len(overlay), 1)
        alpha = float(re.fullmatch(r'.*background:rgba\(14,14,13,([\d.]+)\).*', overlay[0]).group(1))
        self.assertGreaterEqual(alpha, 0.75)
        for selector in ('.fc-band', '.fc-band::after', '.fc-band img', '.fc-stage'):
            for rule in rules_for(self.pages_css, selector):
                self.assertNotRegex(rule, r'(?<![-\w])filter:')
        for colour in (self.tokens['--stone'], self.tokens['--bone']):
            self.assertGreaterEqual(contrast(colour, ink_over_white(alpha)), 4.5)

    def test_fade_co_screens_keep_their_band_padding(self):
        # Resolve padding on the Fade & Co screens section the way the cascade does: of the top-level rules whose selector is
        # a compound of classes the section carries, the highest specificity wins, then the later rule.
        section = re.search(r'<section class="([^"]+)" aria-labelledby="fc-screens">', self.source).group(1).split()
        self.assertEqual(section, ['cs-screens', 'fc-screens'])
        winner = None
        rules = re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', self.base, flags=re.S))
        for order, (selectors, body) in enumerate(rules):
            for selector in (part.strip() for part in selectors.split(',')):
                classes = re.fullmatch(r'((?:\.[\w-]+)+)', selector)
                if not classes or not re.search(r'(?<![-\w])padding(?:-block|-top)?:', body):
                    continue
                names = classes.group(1).lstrip('.').split('.')
                if set(names) <= set(section) and (winner is None or (len(names), order) >= winner[:2]):
                    winner = (len(names), order, selector, body)
        self.assertIsNotNone(winner)
        self.assertEqual(winner[2], '.cs-screens.fc-screens')
        top = re.search(r'padding-block:(\S+?)(?: \S+)?(?:;|$)', winner[3]).group(1)
        self.assertNotEqual(top, '0')
        self.assertTrue(top.startswith('clamp(56px'))

    def test_page_layout_classes_do_not_reuse_mockup_class_names(self):
        # kit.css styles the mini-site mockups with unscoped classes (e.g. .fc-body is absolutely positioned inside a
        # phone screen); a page-level wrapper with the same name would inherit that layout and be pulled out of flow.
        kit = set(re.findall(r'\.([a-z][\w-]*)', re.sub(r'/\*.*?\*/', '', (OUT / 'assets/kit.css').read_text(), flags=re.S)))
        outside_mockups = re.sub(r'<div class="(?:laptop|phone)-screen" aria-hidden="true">.*?</figure>', '', self.source, flags=re.S)
        for article in re.findall(r'<article\b.*?</article>', outside_mockups, re.S):
            for classes in re.findall(r'class="([^"]+)"', article):
                for name in classes.split():
                    if name.startswith(('fc-', 'gl-', 'hb-')):
                        with self.subTest(name=name):
                            self.assertNotIn(name, kit)
        self.assertIn('<div class="wrap g12 cs-body fc-copy">', self.source)

    def test_work_images_stay_lazy_and_reuse_existing_photos(self):
        self.assertEqual({u.rsplit('-', 1)[0] for u in re.findall(r'/assets/images/([a-z-]+-(?:800|1600))\.jpg', self.source)}, WORK_PHOTOS)
        self.assertEqual(self.source.count('fetchpriority="high"'), 1)
        below = self.source.split('</ul>', 1)[1]  # everything after the project index
        parser = ImageCollector()
        parser.feed(below)
        self.assertTrue(parser.images)
        for attrs, _ in parser.images:
            with self.subTest(img=attrs.get('src')):
                self.assertEqual((attrs.get('loading'), attrs.get('decoding')), ('lazy', 'async'))
                for name in ('width', 'height', 'srcset', 'sizes'):
                    self.assertTrue(attrs.get(name), name)
        # Motion: only the existing hooks, and still one device stage per project.
        self.assertTrue(set(re.findall(r'\s(data-[a-z-]+)', self.work)) <= set(MOTION_HOOKS) | {'data-ph-fade'})
        for slug in ('harbourside', 'greenline', 'fade-co'):
            self.assertEqual(self.article(slug, self.work).count(' data-devices'), 1)

    def test_work_sections_are_shorter(self):
        self.assertEqual(rules_for(self.base, '.cs-body'), ['padding-block:clamp(48px,6vw,88px)'])
        self.assertEqual(rules_for(self.base, '.cs.bone'), ['padding-top:var(--section)'])
        self.assertIn('padding-block:0 var(--section)', rules_for(self.base, '.cs-screens')[0])
        self.assertIn('padding-top:clamp(48px,6vw,88px)', rules_for(self.base, '.cs-screens-dark')[0])
        # Only Harbourside's cover keeps a near-full-screen height; the other projects open compactly.
        for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', self.pages_css):
            if re.search(r'\.(?:cs|gl|fc|stage|scr|wk)-', selectors):
                for value in re.findall(r'min-height:min\((\d+)s?vh', body) + re.findall(r'min-height:(\d+)s?vh', body):
                    with self.subTest(selectors=selectors.strip()):
                        self.assertTrue(int(value) < 90 or selectors.strip() == '.cs-cover')
        self.assertEqual(self.source.count('class="cs-cover"'), 1)
        for needle in ('class="wrap wk-index"','id="demo"', 'href="/demo/"', 'class="cta-band"', 'href="/contact/"'):
            self.assertIn(needle, self.work)


if __name__ == '__main__':
    unittest.main()


class SecondCritiqueFixTests(unittest.TestCase):
    """Night Shift Task 21: remaining fixes from docs/design/night-shift/critique/CRITIQUE2.md (demo stacked rows deferred)."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.pages_css = (OUT / 'assets/pages.css').read_text()
        cls.home = main_of((OUT / 'index.html').read_text())
        cls.services = re.search(r'<section class="services"[^>]*>(.*?)</section>', cls.home, re.S).group(1)

    def test_services_have_one_decorative_photo_panel(self):
        panels = re.findall(r'<div class="svc-panel" aria-hidden="true">.*?</div>\s*<ul class="svc-list">', self.services, re.S)
        self.assertEqual(len(panels), 1)
        self.assertEqual(self.home.count('class="svc-panel"'), 1)
        parser = ImageCollector()
        parser.feed(panels[0])
        names = [re.search(r'/images/([a-z-]+)-(?:800|1600)\.jpg$', attrs['src']).group(1) for attrs, _ in parser.images]
        self.assertEqual(names, ['detail-wax', 'detail-dash', 'garden-deck'])  # New website, Redesign, Care plan (Task 23)
        self.assertEqual(panels[0].count('<div class="svc-photo"><picture><source type="image/avif" '), 3)
        for attrs, hidden in parser.images:
            with self.subTest(src=attrs['src']):
                self.assertTrue(hidden)
                self.assertEqual((attrs.get('alt'), attrs.get('loading'), attrs.get('decoding')), ('', 'lazy', 'async'))
                self.assertTrue(attrs.get('width') and attrs.get('height'))
        rows = re.findall(r'<li class="svc">(.*?)</li>', self.services, re.S)
        self.assertEqual(len(rows), 3)
        for row in rows:
            with self.subTest(row=row[:40]):
                self.assertNotIn('<img', row)
                self.assertRegex(row, r'^<h3><a href="/services/#[a-z]+">[^<]+</a></h3><p>')
        # garden-walk was the pricing band's photo (and the Greenline laptop mockup's); both left the homepage in Task 28.
        self.assertNotIn('garden-walk', self.home)
        self.assertNotIn('garden-walk', self.services)

    def test_services_panel_is_sticky_and_crossfades_opacity_only(self):
        base = base_rules(self.home_css)
        self.assertIn('grid-column:1/span 7', rules_for(base, '.svc-list')[0])
        panel = rules_for(base, '.svc-panel')[0]
        for needle in ('grid-column:8/-1', 'position:sticky', 'top:12vh', 'aspect-ratio:4/5', 'overflow:hidden'):
            self.assertIn(needle, panel)
        self.assertIn('align-items:start', rules_for(base, '.svc-grid')[0])  # the panel must not stretch, or it cannot stick
        self.assertIn('position:absolute;inset:0', rules_for(base, '.svc-photo')[0])
        # Without JS (no .is-live) the first photo is on top; afterwards the active one is. No hiding outside the guard.
        self.assertEqual(rules_for(base, '.svc-panel:not(.is-live) .svc-photo:first-child'), ['z-index:1'])
        self.assertEqual(rules_for(base, '.svc-photo.is-active'), ['z-index:1'])
        self.assertNotIn('scale(.94)', self.home_css)
        unguarded, guarded = without_blocks(self.home_css, MOTION_GUARD)
        self.assertNotIn('.svc-panel.is-live', unguarded)
        guarded = ''.join(guarded)
        self.assertIn('.svc-panel.is-live .svc-photo{opacity:0;transition:opacity 500ms var(--ease) 500ms}', guarded)
        self.assertIn('.svc-panel.is-live .svc-photo.is-active{opacity:1;transition-delay:0s}', guarded)
        for rule in rules_for(guarded, '.svc-panel.is-live .svc-photo') + rules_for(guarded, '.svc-panel.is-live .svc-photo.is-active'):
            self.assertNotRegex(rule, r'transform|scale')
        # Up to 900px: one photo above the list, not sticky.
        narrow = media_blocks(self.home_css, 'max-width:900px')
        self.assertEqual(rules_for(narrow, '.svc-list'), ['grid-column:1/-1;grid-row:auto'])
        small_panel = rules_for(narrow, '.svc-panel')[-1]
        self.assertIn('position:relative', small_panel)
        self.assertIn('top:auto', small_panel)
        self.assertLess(self.services.index('svc-panel'), self.services.index('svc-list'))  # above the list in source order

    def test_home_lists_have_no_dash_bullets(self):
        self.assertFalse(rules_for(self.home_css, '.proj-points li::before'))
        self.assertNotIn('padding:13px 0 13px 26px', self.home_css)
        for list_html in re.findall(r'<ul class="proj-points">(.*?)</ul>', self.home, re.S):
            self.assertNotRegex(visible_text(list_html), r'(?:^|\s)[—–-]\s')
        self.assertNotRegex(self.home_css, r'content:\s*"[^"]*[—–-][^"]*"')

    def test_demonstration_label_uses_a_comma_everywhere(self):
        for route in SiteBuildTests.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertNotIn('Demonstration project — sample data', html)
        self.assertIn('Demonstration project, sample data', (OUT / 'demo/index.html').read_text())
        self.assertIn('Demonstration project, sample data', (OUT / 'work/index.html').read_text())

    def test_demo_panel_overlaps_the_hero_on_large_tall_screens_only(self):
        query = 'min-width:1081px) and (min-height:700px'
        block = media_blocks(self.pages_css, query)
        self.assertIn('margin-top:-18vh', rules_for(block, '.demo-shell')[0])
        self.assertIn('position:relative;z-index:1', rules_for(block, '.demo-shell')[0])
        # The hero gains the same room underneath, so the panel never covers its heading, intro or notice.
        self.assertEqual(rules_for(block, '.demo-hero'), ['padding-bottom:calc(clamp(48px,6vw,88px) + 18vh)'])
        self.assertEqual(rules_for(block, '.demo-app'), ['padding-top:0'])
        self.assertNotIn('-18vh', base_rules(self.pages_css))
        self.assertNotIn('-18vh', (OUT / 'assets/site.css').read_text())
        self.assertEqual(self.pages_css.count('-18vh'), 1)
        demo = main_of((OUT / 'demo/index.html').read_text())
        self.assertIn('<section class="page-hero demo-hero"><div class="wrap demo-hero-in"><div class="demo-hero-copy">', demo)
        self.assertIn('<section class="section alt demo-app"><div class="wrap demo-shell">', demo)
        # The 404 page shares .page-hero but not the demo layout.
        self.assertNotIn('demo-hero', (OUT / '404.html').read_text())

    def test_closing_photos_and_removed_photos(self):
        for route, photo in (('about/index.html', 'garden-deck'), ('services/index.html', 'garden-path')):
            with self.subTest(route=route):
                band = re.search(r'<div class="cta-band-media"[^>]*>(.*?)</div>', main_of((OUT / route).read_text()), re.S).group(1)
                self.assertIn(f'/assets/images/{photo}-1600.jpg', band)
        services = (OUT / 'services/index.html').read_text()
        self.assertNotIn('barber-interior', services)
        self.assertIn('.ab-closing .cta-band-media img{object-position:50% 70%}', self.pages_css)
        self.assertNotIn('detail-headlight', (OUT / 'about/index.html').read_text())


class ServicesCareBandTests(unittest.TestCase):
    """Night Shift Task 24: the Care plan is a full-bleed dark band set in type, with no photo; garden-lawn closes no page."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = {route: (OUT / route).read_text() for route in SiteBuildTests.ROUTES + ['404.html']}
        cls.services = main_of(cls.html['services/index.html'])
        cls.care = re.search(r'<section class="care-band" id="care" aria-labelledby="care-title">(.*?)</section>', cls.services, re.S)
        cls.pages_css = (OUT / 'assets/pages.css').read_text()
        cls.site_css = (OUT / 'assets/site.css').read_text()

    def test_care_band_keeps_its_content_and_has_no_photo(self):
        self.assertIsNotNone(self.care)
        care = self.care.group(1)
        self.assertIn('<h2 data-rise id="care-title" class="chap-name">Care plan</h2>', care)
        self.assertIn('A website isn’t finished at launch.', care)
        self.assertRegex(care, r'<h3 [^>]*>Every month</h3>')
        self.assertLess(care.index('care-title'), care.index('Every month'))
        items = re.findall(r'<li><b>([^<]+)</b><span>([^<]+)</span></li>', re.search(r'<ul class="care-cycle">(.*?)</ul>', care, re.S).group(1))
        self.assertEqual([name for name, _ in items], ['Updates', 'Backups', 'Form check', 'Small changes'])
        facts = re.search(r'<dl class="care-facts">(.*?)</dl>', care, re.S).group(1)
        self.assertEqual(re.findall(r'<div><dt>([^<]+)</dt><dd>[^<]+</dd></div>', facts),
                         ['Who it’s for', 'When it starts', 'What we need from you'])
        for banned in ('<img', '<picture', '<figure', 'data-reveal', 'garden-wall'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, care)
        self.assertNotIn('garden-wall', self.services)
        self.assertNotIn('.care-photo', self.pages_css)
        # No price for the care plan: it is still unconfirmed.
        self.assertNotRegex(visible_text(care), r'A?\$\s*\d')
        # The chapter link still lands on the band.
        self.assertIn('<a href="#care">', self.services)

    def test_care_band_type_and_columns(self):
        base = base_rules(self.pages_css)
        band = rules_for(base, '.care-band')
        self.assertEqual(len(band), 1)
        self.assertIn('background:var(--ink-2)', band[0])
        # Full bleed: the band is the section itself, outside .wrap; its content sits inside .wrap.
        self.assertRegex(self.care.group(1), r'^\s*<div class="wrap">')
        name = rules_for(base, '.care-cycle b')
        self.assertEqual(len(name), 1)
        self.assertIn('var(--font-display)', name[0])
        sizes = re.search(r'clamp\(([\d.]+)rem,[^,]+,([\d.]+)rem\)', name[0])
        self.assertGreaterEqual(float(sizes.group(1)), 2)
        self.assertGreaterEqual(float(sizes.group(2)), float(sizes.group(1)))
        self.assertIn('grid-template-columns:repeat(2,minmax(0,1fr))', ''.join(rules_for(base, '.care-cycle')))
        self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', ''.join(rules_for(base, '.care-facts')))
        phone = media_blocks(self.pages_css, 'max-width:640px')
        for selector in ('.care-cycle', '.care-facts'):
            with self.subTest(selector=selector):
                self.assertIn('grid-template-columns:1fr', rules_for(phone, selector)[0])

    def test_care_band_text_contrast(self):
        tokens = dict(re.findall(r'--([a-z0-9-]+):(#[0-9A-Fa-f]{6})', self.site_css))
        background = tokens['ink-2']
        for name, colour in (('headings and item names', tokens['bone']), ('lede', '#D6D2CA'),
                             ('item descriptions and facts', tokens['stone'])):
            with self.subTest(text=name):
                self.assertGreaterEqual(contrast(colour, background), 4.5)
        self.assertIn('color:var(--stone)', rules_for(base_rules(self.pages_css), '.care-facts dd')[0])

    def test_garden_lawn_only_on_home_and_in_the_greenline_mockup(self):
        # Night Shift Task 28: the trades row (with its Landscapers photo) moved from the homepage to /about/, so About now
        # shows garden-lawn once, inside that row; the homepage keeps it on the Greenline card.
        for route, html in self.html.items():
            main = main_of(html)
            with self.subTest(route=route):
                # It closes no page.
                for band in re.findall(r'<div class="(?:cta-)?band-media"[^>]*>(.*?)</div>', main, re.S):
                    self.assertNotIn('garden-lawn', band)
                if route == 'work/index.html':
                    # The made-up client's own screenshot keeps it; nothing else on Work uses it.
                    mockup = re.search(r'<div class="gls-photos">.*?</div>', main, re.S).group(0)
                    self.assertIn('/assets/images/garden-lawn-800.jpg', mockup)
                    main = main.replace(mockup, '')
                if route == 'about/index.html':
                    row = re.search(r'<ul class="who-row">.*?</ul>', main, re.S).group(0)
                    self.assertEqual(row.count('/assets/images/garden-lawn-800.jpg"'), 1)
                    main = main.replace(row, '')
                if route == 'index.html':
                    card = re.search(r'<article class="teaser-card" aria-labelledby="t2-title">.*?</article>', main, re.S).group(0)
                    self.assertIn('/assets/images/garden-lawn-800.jpg', card)
                    self.assertEqual(main.replace(card, '').count('garden-lawn'), 0)
                else:
                    self.assertNotIn('garden-lawn', main)
        self.assertEqual(self.services.count('/assets/images/trade-panel-1600.jpg"'), 1)
        about = self.html['about/index.html']
        self.assertNotIn('detail-headlight', about)
        self.assertNotIn('barber-tools', about)


class MotionQualityTests(unittest.TestCase):
    """Night Shift Task 23 (docs/NIGHT_SHIFT_PLAN.md): no flash of content before page openings, line-mask openings on the
    inner motion pages, pinned projects without opacity ghosting, scroll-driven "What we do" rows and a pin release layer."""
    INNER = {'work/index.html': 'Three made-up businesses. Built as if they were real.',
             'services/index.html': 'Built new. Rebuilt properly. Looked after.',
             'pricing/index.html': 'Fixed quote after a free consultation.',
             'about/index.html': 'A small Sydney studio for local service businesses.'}

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = (OUT / 'assets/site.css').read_text()
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.pages_css = (OUT / 'assets/pages.css').read_text()
        cls.motion = (OUT / 'assets/motion.js').read_text()
        cls.home_js = (OUT / 'assets/home.js').read_text()
        cls.boot = (OUT / 'assets/motion-boot.js').read_text()
        cls.home = main_of((OUT / 'index.html').read_text())

    def guarded(self, css):
        return re.sub(r'/\*.*?\*/', '', ''.join(without_blocks(css, MOTION_GUARD)[1]), flags=re.S)

    def test_boot_holds_openings_only_with_motion_and_always_lets_go(self):
        self.assertLess(self.boot.index("c.add('motion')"), self.boot.index("c.add('ph-wait')"))
        self.assertLess(self.boot.index("matchMedia('(prefers-reduced-motion: reduce)').matches) return;"), self.boot.index("c.add('ph-wait')"))
        delay = re.search(r"setTimeout\(function \(\) \{ c\.remove\('ph-wait'\); \}, (\d+)\)", self.boot)
        self.assertIsNotNone(delay)
        self.assertLessEqual(int(delay.group(1)), 2500)
        # The hold is set before the intro checks, so pages without an intro get it too.
        self.assertLess(self.boot.index("c.add('ph-wait')"), self.boot.index("hasAttribute('data-intro')"))
        # Both scripts let go: motion.js also when GSAP is missing, home.js once its hero states are applied.
        self.assertIn("const release = () => root.classList.remove('ph-wait');", self.motion)
        self.assertIn('if (!gsap || !ScrollTrigger) { release(); return; }', self.motion)
        self.assertIn("root.classList.remove('ph-wait');", self.home_js)
        # home.js also releases the hold when GSAP is missing (motion.js leaves the homepage hero to home.js).
        no_gsap = self.home_js.index('if (!gsap || !ScrollTrigger) { endIntro(); return; }')
        self.assertIn("if (!gsap || !ScrollTrigger) root.classList.remove('ph-wait');", self.home_js[no_gsap - 120:no_gsap])

    def test_inner_headlines_rise_through_line_masks_with_unchanged_text(self):
        for route, text in self.INNER.items():
            with self.subTest(route=route):
                main = main_of((OUT / route).read_text())
                h1 = re.search(r'<h1 [^>]*>(.*?)</h1>', main, re.S).group(1)
                # Every line is a mask holding one span; nothing else sits in the heading.
                self.assertRegex(h1, r'^<span class="ln"><span>[^<]+</span></span>(?: <span class="ln"><span>[^<]+</span></span>)+$')
                self.assertEqual(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', h1)).strip(), text)
                head = re.search(r'<section [^>]*data-ph [^>]*>.*?</section>', main, re.S)
                self.assertIsNotNone(head)
                self.assertIn('<h1', head.group(0))
        for route in STATIC_ROUTES:
            with self.subTest(route=route):
                self.assertNotIn('class="ln"', (OUT / route).read_text())
        self.assertIn('.ln{display:block;overflow:hidden;', self.pages_css)
        # The opening animates the line spans' yPercent, never the heading's opacity.
        opening = self.motion.split("$$('[data-ph]')", 1)[1].split('const rises', 1)[0]
        self.assertIn("$$('h1 .ln > span', head)", opening)
        self.assertIn('{ yPercent: 108, y: 0 }', opening)  # Task 27: the pixel y GSAP reads from the CSS hold is reset
        self.assertNotIn('.from(', opening)
        self.assertNotIn("$$('h1', head)", opening)

    def test_css_hold_matches_the_opening_elements(self):
        guarded = self.guarded(self.pages_css)
        held = {'.ph-wait :is(.wk-hero,.sv-hero,.pr-hero,.ab-hero) .ln>span': 'transform:translateY(108%)',
                '.ph-wait :is(.wk-hero-sub,.sv-hero .pg-sub,.sv-chapters,.pr-hero .pg-sub,.pr-hero .btn-row)': 'opacity:0;transform:translateY(18px)',
                '.ph-wait :is(.sv-hero-media,.ab-photo)': 'clip-path:inset(0 0 0 100%)'}
        for selector, body in held.items():
            with self.subTest(selector=selector):
                self.assertIn(selector + '{' + body + '}', guarded)
        # Every element the opening animates is covered by those selectors (and nothing else is held).
        fade_classes = {'wk-hero-sub', 'pg-sub', 'sv-chapters', 'btn-row'}
        for route in self.INNER:
            main = main_of((OUT / route).read_text())
            head = re.search(r'<section class="([a-z-]+)" data-ph [^>]*>(.*?)</section>', main, re.S)
            with self.subTest(route=route):
                self.assertIn(head.group(1), ('wk-hero', 'sv-hero', 'pr-hero', 'ab-hero'))
                for classes in re.findall(r'class="([^"]+)" data-ph-fade', head.group(2)):
                    self.assertTrue(set(classes.split()) & fade_classes, classes)
                for classes in re.findall(r'class="([^"]+)" data-ph-media', head.group(2)):
                    self.assertIn(classes, ('sv-hero-media', 'ab-photo'))
        # The homepage hero and intro are held the same way and opened with fromTo, never from.
        home = self.guarded(self.home_css)
        for rule in ('.ph-wait .hero-h .ln>span{transform:translateY(108%)}', '.ph-wait:not(.ns-intro) .hero-photo{clip-path:inset(0 0 0 100%)}',
                     '.ph-wait :is(.hero-sub,.hero .actions){opacity:0;transform:translateY(18px)}',
                     '.ph-wait .hero-device{opacity:0;transform:translateY(70px)}', '.ph-wait .intro-mark path{opacity:0}',
                     '.ph-wait .intro-word>span{transform:translateY(110%)}'):
            with self.subTest(rule=rule):
                self.assertIn(rule, home)
        # Night Shift Task 26: under the first-visit intro the hero photo is never clip-hidden, so it paints beneath the
        # panel and stays the first-visit LCP element. Only the no-intro hold clips it, and nothing else hides it.
        bare = re.sub(r'/\*.*?\*/', '', home, flags=re.S)
        photo_rules = [(sel.strip(), body) for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', bare) if '.hero-photo' in sel]
        hiding = [sel for sel, body in photo_rules if re.search(r'clip-path|opacity:0(?![.\d])|visibility', body)]
        self.assertEqual(hiding, ['.ph-wait:not(.ns-intro) .hero-photo'])
        for sel, body in photo_rules:
            if '.ns-intro' in sel and ':not(.ns-intro)' not in sel:
                self.assertNotIn('clip-path', body, sel)
        self.assertNotRegex(bare, r'\.ph-wait \.hero-photo\{')
        hero = self.home_js.split('const heroTimeline', 1)[1].split("mm.add('(prefers-reduced-motion: reduce)'", 1)[0]
        self.assertNotIn('.from(', hero)
        self.assertIn('class="hero-sub" data-hero-fade', self.home)
        self.assertIn('class="actions" data-hero-fade', self.home)

    def test_homepage_has_no_pin_and_moved_sections_keep_shared_hooks(self):
        # Night Shift Task 28: the pinned projects and their bone release layer are gone from home.js and home.css. The
        # sections that moved to /services/ and /about/ use only hooks motion.js already handles (rise, reveal, parallax).
        for gone in ('pin:', 'PIN_', 'work-exit', 'proj-mask', 'is-pinned'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.home_js)
                self.assertNotIn(gone, self.home_css)
        for route, section in (('services/index.html', 'process'), ('about/index.html', 'who bone')):
            with self.subTest(route=route):
                main = main_of((OUT / route).read_text())
                block = re.search(rf'<section class="{section}"[^>]*>.*?</section>', main, re.S).group(0)
                self.assertTrue(set(re.findall(r'\s(data-[a-z-]+)', block)) <= {'data-rise', 'data-reveal', 'data-parallax'})
                self.assertIn('data-rise', block)
        for hook in ('[data-rise]', '[data-reveal]', '[data-parallax]'):
            self.assertIn(f"$$('{hook}')", self.motion)

    def test_services_rows_follow_scroll_wipe_and_dim_accessibly(self):
        large = self.motion.split("mm.add(MOTION + ' and (min-width: 1081px)'", 1)[1].split('mm.add(', 1)[0]
        self.assertIn("ScrollTrigger.create({ trigger: row, start: 'top center', end: 'bottom center'", large)
        self.assertIn("row.addEventListener('mouseenter'", self.motion)
        self.assertIn("row.addEventListener('focusin'", self.motion)
        self.assertIn("{ clipPath: 'inset(100% 0 0 0)' }, { clipPath: 'inset(0% 0 0 0)'", self.motion)
        guarded = self.guarded(self.home_css)
        for rule in ('.svc-panel.is-wipe .svc-photo{opacity:1}', '.svc-panel.is-wipe .svc-photo.is-prev{z-index:1}',
                     '.svc-panel.is-wipe .svc-photo.is-active{z-index:2}'):
            self.assertIn(rule, guarded)
        self.assertNotIn('is-wipe', re.sub(r'/\*.*?\*/', '', base_rules(self.home_css), flags=re.S))
        # Inactive headings: bone at DIM opacity over the ink page must still clear 3:1 (large bold text).
        dim = float(re.search(r'const DIM = ([\d.]+);', self.motion).group(1))
        tokens = dict(re.findall(r'(--[\w-]+):([^;]+)', re.search(r':root\{(.*?)\}', self.css, re.S).group(1)))
        bone, ink = tokens['--bone'].strip(), tokens['--ink'].strip()
        self.assertIn('body{margin:0;background:var(--ink);color:var(--bone);', self.css)
        mix = '#' + ''.join(f'{round(dim * int(bone[i:i + 2], 16) + (1 - dim) * int(ink[i:i + 2], 16)):02X}' for i in (1, 3, 5))
        self.assertGreaterEqual(contrast(mix, ink), 3)
        self.assertLess(dim, 1)
        self.assertIn('<div class="svc-panel" aria-hidden="true">', self.home)


class ShowreelMarkupTests(unittest.TestCase):
    """Night Shift Task 28 (owner): one self-hosted, silent showreel directly after the homepage hero. Playback behaviour is
    tested in tests/test_demo_js.py; these tests cover the markup, files, styles and security headers."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.home = main_of((OUT / 'index.html').read_text())
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.section = re.search(r'<section class="reel"[^>]*>(.*?)</section>', cls.home, re.S)

    def test_one_silent_video_with_poster_size_and_no_autoplay(self):
        self.assertIsNotNone(self.section)
        self.assertLess(self.home.index('<section class="hero"'), self.home.index('<section class="reel"'))
        self.assertLess(self.home.index('<section class="reel"'), self.home.index('<section class="work"'))
        self.assertEqual(self.home.count('<video'), 1)
        for route in SiteBuildTests.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertNotIn('<iframe', html)
                self.assertNotIn('<audio', html)
                if route != 'index.html':
                    self.assertNotIn('<video', html)
        tag = re.search(r'<video ([^>]*)>', self.section.group(1)).group(1)
        attrs = dict(re.findall(r'([a-z-]+)(?:="([^"]*)")?', tag))
        for flag in ('muted', 'loop', 'playsinline', 'controls'):
            with self.subTest(flag=flag):
                self.assertIn(flag, attrs)
        self.assertEqual(attrs['preload'], 'none')
        self.assertEqual(attrs['poster'], '/assets/video/cendavo-showreel-poster-1600.jpg')
        self.assertEqual((attrs['width'], attrs['height']), ('1600', '900'))
        self.assertNotIn('autoplay', tag)
        self.assertNotIn('src', attrs)  # the file comes from <source>
        sources = re.findall(r'<source ([^>]*)>', self.section.group(1))
        self.assertEqual(sources, ['src="/assets/video/cendavo-showreel-1600.mp4" type="video/mp4"'])
        # The phone cut is named in the markup for home.js; every referenced file ships with the site.
        self.assertEqual(attrs['data-narrow-src'], '/assets/video/cendavo-showreel-vertical-720.mp4')
        self.assertEqual(attrs['data-narrow-poster'], '/assets/video/cendavo-showreel-vertical-poster-720.jpg')
        for path in (attrs['poster'], attrs['data-narrow-src'], attrs['data-narrow-poster'], '/assets/video/cendavo-showreel-1600.mp4'):
            with self.subTest(path=path):
                self.assertTrue((OUT / path.lstrip('/')).is_file())
        # Described for assistive technology by the visible line under the heading.
        self.assertEqual(attrs['aria-describedby'], 'reel-desc')
        self.assertRegex(self.section.group(1), r'<p id="reel-desc"[^>]*>[^<]{60,}No sound\.</p>')

    def test_caption_heading_and_button(self):
        section = self.section.group(1)
        self.assertIn('<h2 id="reel-title" data-rise>Twenty seconds of what we build</h2>', section)
        self.assertIn(f'<figcaption class="reel-cap">{SHOWREEL_CAPTION}</figcaption>', section)
        # Without JS the button stays hidden and the native controls work; home.js reveals it and removes the controls.
        self.assertIn('<button class="reel-toggle" type="button" data-reel-toggle hidden>Play showreel</button>', section)
        self.assertLess(section.index('</video>'), section.index('<button class="reel-toggle"'))

    def test_frame_shape_follows_the_screen_without_layout_shift(self):
        base = base_rules(self.home_css)
        self.assertIn('aspect-ratio:16/9', rules_for(base, '.reel-frame')[0])
        phone = media_blocks(self.home_css, 'max-width:640px')
        self.assertIn('aspect-ratio:9/16', rules_for(phone, '.reel-frame')[0])
        self.assertIn("const NARROW = '(max-width: 640px)';", (OUT / 'assets/home.js').read_text())  # same breakpoint as the CSS
        video = rules_for(base, '.reel-video')[0]
        for needle in ('width:100%', 'height:100%', 'object-fit:cover'):
            self.assertIn(needle, video)
        toggle = rules_for(base, '.reel-toggle')[0]
        self.assertGreaterEqual(int(re.search(r'min-height:(\d+)px', toggle).group(1)), 44)
        self.assertIn('background:var(--ink)', toggle)  # solid behind the label, whatever frame is playing
        self.assertIn('color:var(--bone)', toggle)
        focus = rules_for(base, '.reel-toggle:focus-visible')
        self.assertEqual(len(focus), 1)
        self.assertIn('outline:2px solid var(--bone)', focus[0])

    def test_headers_still_allow_self_hosted_media_only(self):
        headers = (OUT / '_headers').read_text()
        self.assertEqual(headers, HEADERS)
        self.assertIn("default-src 'self'", headers)
        self.assertNotIn('media-src', headers)
