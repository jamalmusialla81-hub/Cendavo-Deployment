import re
import unittest
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
        self.assertEqual(css.count('translateY(-2px)'), 1)
        guarded = css.split('@media(prefers-reduced-motion:no-preference){', 1)[1]
        self.assertIn('scroll-behavior:smooth', guarded)
        self.assertIn('translateY(-2px)', guarded)

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
                self.assertIn('<a class="button small dark" href="/contact/">Request a free consultation</a>', html)
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


class DesignSystemTests(unittest.TestCase):
    ROUTES = SiteBuildTests.ROUTES

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = (OUT / 'assets/site.css').read_text()
        cls.home = (OUT / 'index.html').read_text()
        cls.home_main = cls.home.split('<main id="main" tabindex="-1">', 1)[1].split('</main>', 1)[0]
        root = re.search(r':root\{(.*?)\}', cls.css, re.S).group(1)
        cls.tokens = dict(re.findall(r'(--[\w-]+):([^;]+)', root))

    def test_palette_tokens_match_art_direction(self):
        palette = {'--harbour': '#0E2A33', '--fog': '#EEF2F1', '--paper': '#FFFFFF', '--jacaranda': '#6E4FD8',
                   '--jacaranda-light': '#B9A6F2', '--sandstone': '#C98B3D', '--sandstone-ink': '#8C5A1C',
                   '--slate': '#55666C', '--success': '#1F7A52', '--danger': '#B93A26'}
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
        text_pairs = [('harbour', 'fog'), ('slate', 'fog'), ('slate', 'paper'), ('paper', 'jacaranda'), ('jacaranda', 'fog'),
                      ('jacaranda', 'paper'), ('sandstone-ink', 'fog'), ('sandstone-ink', 'paper'), ('jacaranda-light', 'harbour'),
                      ('fog', 'harbour'), ('fog-muted', 'harbour'), ('sandstone', 'harbour'), ('danger', 'paper'),
                      ('success', 'paper'), ('paper', 'jacaranda-deep'), ('fog', 'harbour-raised')]
        for fg, bg in text_pairs:
            with self.subTest(pair=f'{fg}/{bg}'):
                self.assertGreaterEqual(contrast(t[f'--{fg}'], t[f'--{bg}']), 4.5)
        # Focus rings: jacaranda on light surfaces, jacaranda-light inside dark sections.
        self.assertIn(':focus-visible{outline:3px solid var(--jacaranda)', self.css)
        self.assertRegex(self.css, r'\.footer :focus-visible[^{]*\{outline-color:var\(--jacaranda-light\)\}')
        for ring, bg in (('jacaranda', 'fog'), ('jacaranda', 'paper'), ('jacaranda-light', 'harbour')):
            with self.subTest(ring=f'{ring}/{bg}'):
                self.assertGreaterEqual(contrast(t[f'--{ring}'], t[f'--{bg}']), 3)
        self.assertLess(contrast(t['--jacaranda'], t['--harbour']), 3)  # why dark sections need the light ring

    def test_no_third_party_requests(self):
        for banned in ('@import', 'http', 'fonts.googleapis'):
            self.assertNotIn(banned, self.css)
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
                self.assertIn('<meta name="theme-color" content="#0E2A33">', html)
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
        self.assertEqual(h2s, ['What we do', 'Who it’s for', 'How it works', 'Work', 'Pricing', 'Questions', 'Tell us about your business.'])
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
        self.assertIn('<a class="button light" href="/contact/">', band)
        self.assertIn('href="/demo/">See a demonstration project</a>', hero)
        work = main.split('id="work-title"', 1)[1].split('</section>', 1)[0]
        self.assertIn('<span class="badge">Demonstration project — sample data</span>', work)
        self.assertIn('Our first client sites will appear here.', work)
        pricing = main.split('id="pricing-title"', 1)[1].split('</section>', 1)[0]
        self.assertIn('fixed quote after a free consultation', pricing)
        self.assertIn('href="/contact/"', pricing)
        self.assertNotIn('href="/pricing/"', main)

    def test_homepage_makes_no_unvalidated_claims(self):
        text = self.home_main.lower()
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
        self.assertNotIn('<img', figure)
        # Fictional phone numbers only from ACMA's reserved drama range.
        for number in re.findall(r'\(0\d\)\s*[\d ]+', text):
            self.assertTrue(number.startswith('(02) 5550'))
        self.assertIn('.compare{--pos:50%', self.css)
        self.assertIn('clip-path:inset(0 calc(100% - var(--pos)) 0 0)', self.css)

    def test_home_script_is_small_isolated_and_safe(self):
        tag = '<script src="/assets/home.js" defer></script>'
        for route in self.ROUTES:
            with self.subTest(route=route):
                self.assertEqual((OUT / route).read_text().count(tag), 1 if route == 'index.html' else 0)
        path = OUT / 'assets/home.js'
        self.assertLessEqual(path.stat().st_size, 2048)
        js = path.read_text()
        for banned in ('fetch(', 'XMLHttpRequest', 'innerHTML', 'http', 'localStorage'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, js)
        self.assertIn("addEventListener('input'", js)
        self.assertIn("setProperty('--pos'", js)
        self.assertIn('controls.hidden = false', js)
        self.assertIn("setAttribute('aria-pressed'", js)

    def test_motion_is_guarded_and_compositor_only(self):
        unguarded, guarded = without_blocks(self.css, MOTION_GUARD)
        self.assertTrue(guarded)
        for word in ('transition', 'animation', '@keyframes'):
            with self.subTest(word=word):
                self.assertNotIn(word, unguarded)
        for block in guarded:
            for value in re.findall(r'transition:([^;}]+)', block):
                properties = [part.split()[0] for part in value.split(',')]
                self.assertTrue(set(properties) <= {'transform', 'opacity'}, value)
            self.assertNotIn('animation', block)

    def test_layout_basics(self):
        for selector in ('.button{', '.menu{', '.compare-button{'):
            with self.subTest(selector=selector):
                rule = self.css.split(selector, 1)[1].split('}', 1)[0]
                self.assertIn('min-height:44px', rule)
        self.assertIn(':focus-visible{', self.css)
        self.assertIn('@media(max-width:640px){', self.css)
        self.assertLessEqual((OUT / 'assets/site.css').stat().st_size, 30 * 1024)

    def test_every_page_class_has_a_css_rule(self):
        classes = set()
        for page in (Path(__file__).resolve().parents[1] / 'pages').glob('*.html'):
            for attribute in re.findall(r'class="([^"]*)"', page.read_text()):
                classes.update(attribute.split())
        self.assertTrue(classes)
        for name in sorted(classes):
            with self.subTest(css_class=name):
                self.assertRegex(self.css, rf'\.{re.escape(name)}(?![\w-])')


if __name__ == '__main__':
    unittest.main()
