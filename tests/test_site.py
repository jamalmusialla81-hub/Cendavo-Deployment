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
        routes = ['index.html','services/index.html','pricing/index.html','demo/index.html','contact/index.html']
        for route in routes:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertIn('CENDAVO', html)
                self.assertIn('href="/demo/"', html)
                self.assertIn('href="/contact/"', html)
                self.assertIn('name="viewport"', html)
                self.assertFalse(re.search(r'<script[^>]*>\s*[^<\s]', html))

    def test_demo_is_clearly_sample_only(self):
        demo = (OUT / 'demo/index.html').read_text()
        pricing = (OUT / 'pricing/index.html').read_text()
        self.assertIn('Demo only', demo)
        self.assertIn('No message is sent automatically', demo)
        self.assertIn('No paid plans or checkout', pricing)
        self.assertIn('research hypotheses', pricing)

    def test_security_headers_shipped(self):
        headers = (OUT / '_headers').read_text()
        for setting in ('Content-Security-Policy:', 'X-Content-Type-Options: nosniff', "connect-src 'self'", "object-src 'none'"):
            self.assertIn(setting, headers)

    ROUTES = ['index.html','services/index.html','pricing/index.html','demo/index.html','contact/index.html']

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
GSAP_TAGS = ['<script src="/assets/vendor/gsap/gsap.min.js" defer></script>',
             '<script src="/assets/vendor/gsap/ScrollTrigger.min.js" defer></script>',
             '<script src="/assets/home.js" defer></script>']


class DesignSystemTests(unittest.TestCase):
    ROUTES = SiteBuildTests.ROUTES

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = (OUT / 'assets/site.css').read_text()
        cls.home_css = (OUT / 'assets/home.css').read_text()
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
        for css in (self.css, self.home_css):
            for banned in ('@import', 'http', 'fonts.googleapis'):
                self.assertNotIn(banned, css)
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertNotRegex(html, r'\bsrc="(?!/)')
                self.assertNotRegex(html, r'<link[^>]+href="(?!/)')
        headers = (OUT / '_headers').read_text()
        self.assertIn("style-src 'self';", headers)
        self.assertIn("font-src 'self';", headers)
        self.assertIn("script-src 'self';", headers)
        self.assertNotIn('googleapis', headers)
        self.assertNotIn('gstatic', headers)

    def test_global_chrome(self):
        from scripts.build_site import NAV
        self.assertEqual([label for label, _ in NAV], ['Home', 'Services', 'Pricing', 'Demo project', 'Contact'])
        self.assertEqual([href for _, href in NAV], ['/', '/services/', '/pricing/', '/demo/', '/contact/'])
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

    def test_mobile_menu_collapses_only_with_javascript(self):
        self.assertIn("document.documentElement.classList.add('js')", (OUT / 'assets/site.js').read_text())
        self.assertIn('.js .nav-links{display:none}', self.css)
        self.assertNotRegex(self.css, r'(?<!\.js )\.nav-links\{[^}]*display:none')
        self.assertIn('.js .menu{display:inline-flex}', self.css)

    def test_homepage_structure(self):
        main = self.home_main
        self.assertEqual(main.count('<h1'), 1)
        levels = [int(n) for n in re.findall(r'<h([1-6])', main)]
        self.assertEqual(levels[0], 1)
        for previous, current in zip(levels, levels[1:]):
            self.assertLessEqual(current, previous + 1)
        h2s = [re.sub(r'<[^>]+>', '', h) for h in re.findall(r'<h2[^>]*>(.*?)</h2>', main)]
        self.assertEqual(h2s, ['We make websites for people who do the work, so the first thing a customer sees online is as good as the job you do.',
                               'Concept projects', 'Same business. A very different first impression.', 'What we do',
                               'Built for the businesses that keep Sydney running', 'How it works',
                               'Fixed quote after a free consultation', 'Questions', 'Let’s make your website as good as your work.'])
        steps = re.search(r'<ol class="steps"[^>]*>(.*?)</ol>', main).group(1)
        self.assertEqual(re.findall(r'<h3>(.*?)</h3>', steps), ['Discover', 'Design', 'Build', 'Launch', 'Look after'])
        self.assertTrue(1 <= main.count('<details>') <= 4)
        self.assertEqual(main.count('<details>'), main.count('<summary>'))

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
        pricing = main.split('id="pricing-title"', 1)[1].split('</section>', 1)[0]
        self.assertIn('fixed quote after a free consultation', pricing)
        self.assertIn('href="/contact/"', pricing)
        self.assertNotIn('href="/pricing/"', main)

    def test_homepage_makes_no_unvalidated_claims(self):
        # The required concept label is the only place a middle dot may appear.
        text = self.home_main.replace(CONCEPT_LABEL, '').lower()
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

    def test_concept_projects_are_labelled(self):
        articles = re.findall(r'<article class="proj [^"]*"[^>]*>(.*?)</article>', self.home_main, re.S)
        self.assertEqual(len(articles), 3)
        for article, name in zip(articles, ('Harbourside Mobile Detailing', 'Greenline Landscapes', 'Fade &amp; Co')):
            with self.subTest(project=name):
                self.assertEqual(article.count(CONCEPT_LABEL), 1)
                self.assertIn(f'>{name}</h3>', article)
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
        # GSAP, then ScrollTrigger, then home.js: deferred, in that order, and only on the homepage.
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                for tag in GSAP_TAGS:
                    self.assertEqual(html.count(tag), 1 if route == 'index.html' else 0)
                if route == 'index.html':
                    positions = [html.index(tag) for tag in GSAP_TAGS]
                    self.assertEqual(positions, sorted(positions))
                else:
                    self.assertNotIn('gsap', html.lower())
        for name in ('gsap.min.js', 'ScrollTrigger.min.js', 'LICENSE.txt'):
            self.assertTrue((OUT / 'assets/vendor/gsap' / name).is_file())
        path = OUT / 'assets/home.js'
        self.assertLessEqual(path.stat().st_size, 6 * 1024)
        js = path.read_text()
        for banned in ('fetch(', 'XMLHttpRequest', 'innerHTML', 'http', 'localStorage', 'sessionStorage', 'pin:', 'snap'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, js)
        self.assertIn("addEventListener('input'", js)
        self.assertIn("setProperty('--pos'", js)
        self.assertIn('controls.hidden = false', js)
        self.assertIn("setAttribute('aria-pressed'", js)
        # Motion is optional and only runs for people who have not asked for reduced motion.
        self.assertIn('if (!gsap) return;', js)
        self.assertIn('gsap.matchMedia()', js)
        self.assertIn("mm.add('(prefers-reduced-motion: no-preference)'", js)

    def test_first_party_javascript_budget_per_page(self):
        for route in self.ROUTES:
            with self.subTest(route=route):
                sources = re.findall(r'<script src="(/assets/[^"]+)"', (OUT / route).read_text())
                own = [src for src in sources if not src.startswith('/assets/vendor/')]
                self.assertLessEqual(sum((OUT / src.lstrip('/')).stat().st_size for src in own), 15 * 1024)

    def test_home_stylesheet_loads_only_on_homepage(self):
        tag = '<link rel="stylesheet" href="/assets/home.css">'
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertEqual(html.count(tag), 1 if route == 'index.html' else 0)
                self.assertEqual(html.count('<link rel="stylesheet" href="/assets/site.css">'), 1)

    def test_motion_is_guarded_and_compositor_only(self):
        for name, css in (('site.css', self.css), ('home.css', self.home_css)):
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
        for name, css in (('site.css', self.css), ('home.css', self.home_css)):
            with self.subTest(css=name):
                unguarded, _ = without_blocks(css, MOTION_GUARD)
                for hook in ('data-rise', 'data-hero-fade'):
                    self.assertNotIn(hook, css)
                self.assertNotRegex(unguarded, r'opacity:0(?![.\d])')
                self.assertNotIn('visibility:hidden', unguarded)

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

    def test_every_page_class_has_a_css_rule(self):
        # Inner pages only load site.css; the homepage also loads home.css.
        pages = Path(__file__).resolve().parents[1] / 'pages'
        checked = 0
        for page in pages.glob('*.html'):
            css = self.css + self.home_css if page.stem == 'index' else self.css
            classes = set()
            for attribute in re.findall(r'class="([^"]*)"', page.read_text()):
                classes.update(attribute.split())
            for name in sorted(classes):
                checked += 1
                with self.subTest(page=page.name, css_class=name):
                    self.assertRegex(css, rf'\.{re.escape(name)}(?![\w-])')
        self.assertTrue(checked)


if __name__ == '__main__':
    unittest.main()
