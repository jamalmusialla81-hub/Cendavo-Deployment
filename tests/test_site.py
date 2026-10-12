import hashlib
import re
import struct
import unittest
from html.parser import HTMLParser
from pathlib import Path
from scripts.build_site import build, OUT

ROOT = Path(__file__).resolve().parents[1]
# Night Shift Task 31: the public business address, written out here rather than imported from the code under test.
CONTACT_EMAIL = 'cendavo.au@gmail.com'
MAIL_LINK = f'<a class="mail" href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>'


class ContactEmailTests(unittest.TestCase):
    """Night Shift Task 31: cendavo.au@gmail.com on Contact, in the privacy note and in every footer, defined once per language."""
    ROUTES = ['index.html', 'work/index.html', 'services/index.html', 'pricing/index.html', 'demo/index.html',
              'about/index.html', 'contact/index.html', '404.html']

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = {route: (OUT / route).read_text() for route in cls.ROUTES}

    def test_every_footer_has_one_mailto_link_after_the_location(self):
        for route, html in self.html.items():
            with self.subTest(route=route):
                footer = html.split('<footer class="footer">', 1)[1].split('</footer>', 1)[0]
                self.assertEqual(footer.count('mailto:'), 1)
                self.assertIn(f'<br>Sydney, Australia.<br>{MAIL_LINK}</p>', footer)
                links = re.search(r'<nav class="footer-links"[^>]*>(.*?)</nav>', footer).group(1)
                self.assertNotIn('mailto:', links)
                self.assertNotIn('@', footer.replace(MAIL_LINK, ''))

    def test_every_mailto_link_is_well_formed(self):
        for route, html in self.html.items():
            links = re.findall(r'<a\b([^>]*)\bhref="(mailto:[^"]*)"([^>]*)>(.*?)</a>', html)
            with self.subTest(route=route):
                # Contact: beside the form, in the no-JavaScript notice (Task 47) and in the privacy note.
                self.assertEqual(len(links), 4 if route == 'contact/index.html' else 1)
                self.assertEqual(html.count('mailto:'), len(links))
                self.assertNotIn('{{', html)  # no placeholder left behind
            for before, href, after, text in links:
                with self.subTest(route=route, href=href):
                    self.assertRegex(href, r'^mailto:cendavo\.au@gmail\.com$')  # no query string, cc or subject
                    self.assertEqual(text, CONTACT_EMAIL)  # the visible text is the address itself
                    self.assertNotIn('target=', before + after)

    def test_address_is_defined_once_per_language(self):
        from scripts import build_site
        self.assertEqual(build_site.CONTACT_EMAIL, CONTACT_EMAIL)
        definitions = {ROOT / 'scripts/build_site.py': f"CONTACT_EMAIL = '{CONTACT_EMAIL}'",
                       ROOT / 'assets/enquiry.js': f"var CONTACT_EMAIL = '{CONTACT_EMAIL}';",
                       ROOT / 'functions/api/enquiry.js': f"export const CONTACT_EMAIL = '{CONTACT_EMAIL}';"}
        for path, definition in definitions.items():
            with self.subTest(path=path.name):
                source = path.read_text()
                self.assertEqual(source.count(definition), 1)
                self.assertEqual(source.count(CONTACT_EMAIL), 1)  # the definition is the only literal copy
        sources = [p for d in ('pages', 'assets', 'functions') for p in (ROOT / d).rglob('*')
                   if p.suffix in ('.html', '.js', '.css', '.mjs') and p not in definitions]
        self.assertTrue(sources)
        for path in sources:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertNotIn(CONTACT_EMAIL, path.read_text(errors='ignore'))
        self.assertIn('{{CONTACT_EMAIL}}', (ROOT / 'pages/contact.html').read_text())

    def test_contact_mail_line_sits_beside_the_form(self):
        html = self.html['contact/index.html']
        side = html.split('<div class="ct-side">', 1)[1].split('<div class="ct-form bone">', 1)[0]
        self.assertEqual(side.count(f'<p class="ct-mail">Prefer email? Write to {MAIL_LINK}</p>'), 1)
        self.assertLess(side.index('class="ct-next"'), side.index('class="ct-mail"'))
        css = (OUT / 'assets/site.css').read_text()
        self.assertIn('.mail{text-decoration-thickness:1px;text-underline-offset:.2em;overflow-wrap:anywhere}', css)
        self.assertNotIn('text-decoration:none', css.split('.mail{', 1)[1].split('}', 1)[0])


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
        # Task 30: enquiries may also be emailed to the owner through Resend, so the notice must say so. Task 47: the email
        # copy is only sent when the alert is configured, so the note says "may" and never claims it always happens.
        # Task 31: the note may hold one element, the mailto link, and it ends the deletion sentence.
        notice = re.search(r'<p class="notice" id="enquiry-privacy">(.*?)</p>', html).group(1)
        self.assertEqual(re.findall(r'<[^>]+>', notice), [f'<a class="mail" href="mailto:{CONTACT_EMAIL}">', '</a>'])
        self.assertIn('stored in a Cloudflare database', notice)
        self.assertIn('may also be emailed to Cendavo through our email delivery provider, Resend', notice)
        self.assertNotIn('and also emailed', notice)
        self.assertIn('not added to mailing lists or sold', notice)
        self.assertTrue(notice.endswith(f'you can ask us to delete them at any time by emailing {MAIL_LINK}.'))
        self.assertNotIn('A$', html)
        # Task 31: the business address is the only "@" in the page's main content, in exactly three links (beside the form,
        # in the no-JavaScript notice (Task 47) and in the privacy note). Nothing else (no other address, no placeholder
        # email) may appear.
        main = html.split('<main', 1)[1].split('</main>', 1)[0]
        self.assertEqual(main.count(MAIL_LINK), 3)
        self.assertIn(f'<p class="ct-mail">Prefer email? Write to {MAIL_LINK}</p>', main)
        self.assertNotIn('@', main.replace(MAIL_LINK, ''))

    def test_contact_honeypot_is_hidden_from_people_and_assistive_tech(self):
        html = (OUT / 'contact/index.html').read_text()
        honeypot = re.search(r'<div class="hp" aria-hidden="true">.*?</div>', html)
        self.assertIsNotNone(honeypot)
        # Task 47: a name and id with no meaning for autofill (a filled trap silently drops a real enquiry); enquiry.js
        # still sends its value to the server as company_url.
        field = re.search(r'<input id="([^"]+)" name="([^"]+)" type="text" tabindex="-1" autocomplete="off">', honeypot.group(0))
        self.assertIsNotNone(field)
        self.assertEqual(honeypot.group(0).count('<input'), 1)
        self.assertIn(f'<label for="{field.group(1)}">', honeypot.group(0))
        for word in ('company', 'url', 'website', 'name', 'email', 'mail', 'phone', 'tel', 'org', 'address', 'addr'):
            with self.subTest(word=word):
                self.assertNotIn(word, field.group(1).lower())
                self.assertNotIn(word, field.group(2).lower())
        script = (ROOT / 'assets/enquiry.js').read_text()
        self.assertIn(f"var HONEYPOT = '{field.group(2)}';", script)
        self.assertIn('fields.company_url = trap ? trap.value', script)
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


VT_KEYFRAMES = re.compile(r'@keyframes vt-[\w-]*\{')
VT_RULE = re.compile(r'::view-transition-[a-z]+\([^)]*\)(?:,::view-transition-[a-z]+\([^)]*\))*\{[^}]*\}')


def without_view_transitions(css):
    """css without Night Shift Task 29's page-transition rules: @keyframes vt-* blocks, rules whose selectors are all
    ::view-transition-* pseudo-elements, and the reduced-motion block left empty once those are gone. Those rules are the
    one place CSS animation is allowed; ViewTransitionAndDetailTests pins them, so every other check stays as strict."""
    while (match := VT_KEYFRAMES.search(css)):
        css = without_blocks(css, match.group(0))[0]
    return VT_RULE.sub('', css).replace('@media(prefers-reduced-motion:reduce){}', '')


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
# Night Shift Task 29: the caption under each social clip (Services and Work).
CLIP_CAPTION = 'Concept projects · fictional businesses'
GSAP_TAGS = ['<script src="/assets/vendor/gsap/gsap.min.js" defer></script>',
             '<script src="/assets/vendor/gsap/ScrollTrigger.min.js" defer></script>',
             '<script src="/assets/motion.js" defer></script>',
             '<script src="/assets/details.js" defer></script>']
HOME_TAG = '<script src="/assets/home.js" defer></script>'
# Task 29: the shared silent-video controller, only on the pages that show video.
REEL_TAG = '<script src="/assets/reel.js" defer></script>'
# Daylight (Task 34): the inner pages' scroll scenes (benches, drawn lines, vignettes, the Work queue, the film frame), after
# motion.js on the inner motion pages only, so the homepage stays inside the 30 KB script budget.
SCENES_TAG = '<script src="/assets/scenes.js" defer></script>'
SCENES_ROUTES = ['work/index.html', 'services/index.html', 'pricing/index.html', 'about/index.html']
# Daylight (Task 34): About adds the launch film, so it loads reel.js too.
# Task 41: Pricing loads it for the ambient loop behind its closing panel.
REEL_ROUTES = ['index.html', 'work/index.html', 'services/index.html', 'pricing/index.html', 'about/index.html']
# Pages that show the homepage mini-site, the device bench or the phone-framed clips and so load the mockup kit (kit.css).
# Pricing's quote sheet moved to pricing.css in Daylight (Task 34).
KIT_ROUTES = ['index.html', 'work/index.html', 'services/index.html']
# Every stylesheet the site ships (Daylight, Task 34, adds one sheet per large inner page). Global CSS rules are checked on all.
# Liquid Glass (Task 37) adds the shared glass shell, glass.css, loaded on every page right after site.css.
SHEETS = ('site.css', 'glass.css', 'home.css', 'pages.css', 'kit.css', 'work.css', 'services.css', 'pricing.css', 'about.css')
# The inner pages with their own stylesheet, loaded after pages.css.
OWN_SHEET_ROUTES = {'work/index.html': 'work.css', 'services/index.html': 'services.css', 'pricing/index.html': 'pricing.css',
                    'about/index.html': 'about.css'}
# Pages with GSAP motion (Night Shift Task 10; About added in Task 15). Contact (the enquiry form) and Demo (the browser app) stay static.
MOTION_ROUTES = ['index.html', 'work/index.html', 'services/index.html', 'pricing/index.html', 'about/index.html']
STATIC_ROUTES = ['contact/index.html', 'demo/index.html']
# Night Shift Task 29: <video> elements per built page (the showreel on /, social clips on /services/ and /work/). Daylight
# (Task 33) adds the homepage hero's two device loops (laptop and phone).
# Daylight (Task 34): Work adds six device loops (a laptop and a phone per concept), Services the Care plan phone loop and
# About the launch film.
# Liquid Glass (Task 37): the homepage's hero has no <video> (the WebGL scene makes its own, after load); it shows the
# showreel, the marquee's footage, the closing band's footage and its two glass phones.
# Task 41: Work, Services, Pricing and About add the ambient glass loop behind their closing panel (wide screens only).
VIDEOS_PER_ROUTE = {'index.html': 5, 'services/index.html': 4, 'work/index.html': 8, 'about/index.html': 2, 'pricing/index.html': 1}
# Daylight (Task 34) adds the inner-page choreography hooks from the prototype (lists, benches and their cues, drawn lines,
# the Services illustrations, the Work queue and the Pricing quote sheet).
MOTION_HOOKS = ('data-ph', 'data-reveal', 'data-parallax', 'data-devices', 'data-rise', 'data-work', 'data-intro', 'data-stagger',
                'data-bench', 'data-cue', 'data-line', 'data-build', 'data-month', 'data-redir', 'data-queue', 'data-sheet')
# Hooks for reel.js (Task 28 showreel, Task 29 clips; Task 33 hero loops, Pause motion and showreel chapters); playback,
# not motion, so they may appear wherever a video is.
REEL_HOOKS = ('data-reel', 'data-reel-toggle', 'data-loop', 'data-motion-toggle', 'data-chapters', 'data-reel-ui', 'data-progress',
              'data-time', 'data-hover-src', 'data-poster')  # data-poster: a loop's still, set only near the screen
# Daylight (Task 33/34): every motion page loads GSAP, ScrollTrigger and motion.js but no page loads details.js (no card tilt
# or cursor ring under the Daylight motion rules).
HOME_GSAP_TAGS = GSAP_TAGS[:3]
# Liquid Glass (Task 37): the homepage runs its own motion in home.js and loads GSAP and ScrollTrigger without motion.js.
INDEX_GSAP_TAGS = GSAP_TAGS[:2]
# The glass shell's scripts: Lenis and glass.js on the motion pages, the WebGL boot on the homepage only.
GLASS_TAGS = ['<script src="/assets/vendor/lenis/lenis.min.js" defer></script>', '<script src="/assets/glass.js" defer></script>']
GLASS_BOOT_TAG = '<script src="/assets/glass-boot.js" defer></script>'
GL_HOOKS = {'data-gl', 'data-gl-kind', 'data-gl-video', 'data-gl-anchor', 'data-gl-hide'}  # the scene host (Task 39)
GL_ROUTES = ('index.html', 'work/index.html', 'services/index.html', 'pricing/index.html', 'about/index.html',
             'contact/index.html')  # pages with a WebGL scene host (Tasks 39 and 40)
DETAILS_TAG = GSAP_TAGS[3]
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
        # Daylight palette (Task 33, docs/design/daylight/prototype): paper, two warm greys, ink, one amber. Every colour
        # token is a solid hex (the prototype's rgba --mute could not be contrast-checked). The Night Shift greys stay for the
        # few ink surfaces (the demo's side panel, the homepage showreel button).
        palette = {'--paper': '#FFFFFF', '--warm': '#F6F5F1', '--warm-2': '#EEECE5', '--ink': '#0E0E0D', '--ink-2': '#2A2926',
                   '--mute': '#605D57', '--amber': '#D9A441', '--amber-ink': '#8C5A1C', '--ok': '#1E6B47', '--danger': '#A3341F',
                   '--bone': '#EDEAE3', '--bone-2': '#E3DFD6', '--stone': '#A8A49B', '--ink-soft': '#4F4C46', '--amber-hover': '#E6B65A'}
        for name, value in palette.items():
            with self.subTest(token=name):
                self.assertEqual(self.tokens.get(name, '').strip().upper(), value)
        self.assertNotIn('--success', self.tokens)  # renamed --ok
        # Daylight (Task 34): lines are ink at low alpha on paper.
        self.assertEqual(self.tokens['--line'], 'rgba(14,14,13,.1)')
        self.assertEqual(self.tokens['--line-2'], 'rgba(14,14,13,.16)')
        for name in SHEETS:
            with self.subTest(css=name):
                self.assertNotIn('var(--success)', (OUT / 'assets' / name).read_text())

    def test_scale_tokens(self):
        spaces = {k: v for k, v in self.tokens.items() if k.startswith('--space-')}
        self.assertGreaterEqual(len(spaces), 8)
        for name, value in spaces.items():
            with self.subTest(token=name):
                self.assertEqual(int(value.removesuffix('px')) % 4, 0)
        self.assertTrue(any(k.startswith('--radius-') for k in self.tokens))
        shadows = [k for k in self.tokens if k.startswith('--shadow')]
        self.assertTrue(1 <= len(shadows) <= 3)
        # Daylight motion rules (Task 33): two curves, (.2,.8,.2,1) for entrances and (.7,0,.2,1) between states, and
        # four durations. No stylesheet uses any other cubic-bezier.
        self.assertEqual([self.tokens[k] for k in ('--dur-1', '--dur-2', '--dur-3', '--dur-4')], ['200ms', '400ms', '700ms', '1000ms'])
        self.assertEqual(len([k for k in self.tokens if k.startswith('--dur')]), 4)
        self.assertEqual({k: v for k, v in self.tokens.items() if k.startswith('--ease')},
                         {'--ease-out': 'cubic-bezier(.2,.8,.2,1)', '--ease-io': 'cubic-bezier(.7,0,.2,1)'})
        for name in SHEETS:
            sheet = (OUT / 'assets' / name).read_text()
            with self.subTest(css=name):
                self.assertTrue(set(re.findall(r'cubic-bezier\([^)]*\)', sheet)) <= {'cubic-bezier(.2,.8,.2,1)', 'cubic-bezier(.7,0,.2,1)'})
                self.assertNotIn('var(--ease)', sheet)
        for name in ('--font-display', '--font-text'):
            with self.subTest(token=name):
                self.assertIn('sans-serif', self.tokens[name])
        self.assertIn('clamp(', self.tokens['--text-display'])

    def test_colour_pairs_meet_wcag(self):
        t = {k: v.strip() for k, v in self.tokens.items() if v.strip().startswith('#')}
        # Daylight text on paper and the warm bands, white on the booked green and on ink, and the bone/stone pairs the
        # demo's ink side panel and the homepage showreel button still use.
        text_pairs = [('ink', 'paper'), ('ink', 'warm'), ('ink', 'warm-2'), ('ink-2', 'paper'), ('ink-2', 'warm'), ('ink-2', 'warm-2'),
                      ('mute', 'paper'), ('mute', 'warm'), ('mute', 'warm-2'), ('amber-ink', 'paper'), ('amber-ink', 'warm'),
                      ('ink', 'amber'), ('danger', 'paper'), ('danger', 'warm'), ('ok', 'paper'), ('ok', 'warm'),
                      ('paper', 'ok'), ('paper', 'ink'), ('paper', 'ink-2'),
                      ('bone', 'ink'), ('bone', 'ink-2'), ('stone', 'ink'), ('stone', 'ink-2'), ('ink', 'bone'), ('ink', 'bone-2'),
                      ('ink-soft', 'bone'), ('ink-soft', 'bone-2'), ('ink-soft', 'paper'), ('ink', 'amber-hover'),
                      ('danger', 'bone'), ('danger', 'bone-2'), ('ok', 'bone'), ('ok', 'bone-2')]
        for fg, bg in text_pairs:
            with self.subTest(pair=f'{fg}/{bg}'):
                self.assertGreaterEqual(contrast(t[f'--{fg}'], t[f'--{bg}']), 4.5)
        # Focus rings: ink on paper and warm surfaces (the default); bone on the demo's ink side panel; white in the ink
        # closing bands (homepage and inner pages) and on the Harbourside photo cover.
        self.assertIn(':focus-visible{outline:2px solid var(--ink)', self.css)
        self.assertIn('.close :focus-visible{outline-color:#fff}', self.pages_css)
        self.assertIn('.cs-cover :focus-visible{outline-color:#fff}', (OUT / 'assets/work.css').read_text())
        self.assertNotIn('main :focus-visible', self.pages_css)  # the inner pages' <main> is paper now (Task 34)
        self.assertRegex(self.css, r'\.demo-side :focus-visible[^{]*\{outline-color:var\(--bone\)\}')
        self.assertIn('.band :focus-visible{outline-color:#fff}', self.home_css)
        for ring, bg in (('ink', 'paper'), ('ink', 'warm'), ('ink', 'warm-2'), ('bone', 'ink'), ('bone', 'ink-2'), ('ink', 'bone'), ('ink', 'bone-2')):
            with self.subTest(ring=f'{ring}/{bg}'):
                self.assertGreaterEqual(contrast(t[f'--{ring}'], t[f'--{bg}']), 3)
        self.assertGreaterEqual(contrast('#FFFFFF', t['--ink']), 3)
        self.assertLess(contrast(t['--amber'], t['--paper']), 3)  # why amber is never a focus ring

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
        for name in SHEETS:
            css = (OUT / 'assets' / name).read_text()
            for banned in ('@import', 'http', 'fonts.googleapis'):
                with self.subTest(css=name, banned=banned):
                    self.assertNotIn(banned, css)
        from scripts.build_site import BASE_URL
        for route in self.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertNotRegex(html, r'\bsrc="(?!/)')
                self.assertNotRegex(html, r'\bsrcset="(?!/)')
                self.assertNotRegex(html, r'\bposter="(?!/)')
                self.assertNotRegex(html, r'\bdata-(?:narrow-)?(?:src|poster|hover-src)="(?!/)')
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
                self.assertIn('<meta name="theme-color" content="#FFFFFF">', html)
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

    def test_light_first_frame_and_light_form_controls(self):
        # Night Shift Task 25 restated for Daylight (Task 33): the browser's first frame, painted before site.css arrives,
        # is the same white as the page (light color-scheme, white theme colour), so nothing flashes dark; native form
        # controls render light.
        for route in self.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                head = html.split('</head>', 1)[0]
                self.assertEqual(html.count('<meta name="color-scheme" content="light">'), 1)
                self.assertEqual(html.count('<meta name="theme-color" content="#FFFFFF">'), 1)
                self.assertEqual(html.count('name="color-scheme"'), 1)
                self.assertEqual(html.count('name="theme-color"'), 1)
                for meta in ('<meta name="color-scheme" content="light">', '<meta name="theme-color" content="#FFFFFF">'):
                    self.assertLess(head.index(meta), head.index('<link rel="stylesheet" href="/assets/site.css">'))
        self.assertIn('input,select,textarea{color-scheme:light}', self.css)
        self.assertNotRegex(self.css, r'(?:^|[;{}\s])color-scheme:dark')
        self.assertIn('body{margin:0;background:var(--paper);color:var(--ink);', self.css)
        self.assertEqual(self.tokens['--paper'].upper(), '#FFFFFF')

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
        sections = re.findall(r'<section class="([a-z -]+)"', main)
        # Daylight (Task 33): the same order on paper, with warm bands behind the showreel and the comparison.
        # Liquid Glass (Task 37): the marquee (decorative, labelled "What we make", no heading) sits between the showreel and
        # the concept projects.
        self.assertEqual(sections, ['hero', 'reel band-warm', 'marq', 'work', 'ba band-warm', 'services', 'band'])
        self.assertIn('<section class="marq" aria-label="What we make">\n<p class="sr-only">New websites, redesigns and care plans.</p>', main)
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
        self.assertIn('<a class="button dark go" href="/contact/">Request a free consultation</a>', hero)  # ink on paper (Daylight)
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
        # Liquid Glass (Task 37): the hero is described as an illustration of fictional concept businesses; its glass cards
        # sit in an aria-hidden layer, the booking card is tagged "Concept" and the enquiry card says it is an example.
        hero = re.search(r'<section class="hero".*?</section>', self.home_main, re.S).group(0)
        label = re.search(r'<div class="hero-gl" data-gl role="img" aria-label="([^"]+)"></div>', hero)
        self.assertIsNotNone(label)
        self.assertTrue(label.group(1).startswith('Illustration:'))
        self.assertIn('fictional concept businesses', label.group(1))
        cards = re.search(r'<div class="hero-cards" aria-hidden="true">(.*?)</div>\n</div>\n<p class="hero-cap', hero, re.S)
        self.assertIsNotNone(cards)
        self.assertIn('<span class="tag">Concept</span>', cards.group(1))
        self.assertIn('<small>Example, Sam, website redesign</small>', cards.group(1))
        self.assertNotIn('Lighthouse', self.home_main)
        self.assertNotIn('Page speed', self.home_main)

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
        # Daylight (Task 33): uneven sizes on a 12-column grid: a wide lead card (6 columns) and two narrow ones (3 each),
        # the last set lower.
        self.assertIn('grid-template-columns:repeat(12,minmax(0,1fr))', rules_for(base, '.teaser')[0])
        self.assertIn('grid-column:span 3', rules_for(base, '.teaser-card')[0])
        self.assertIn('grid-column:1/span 6', rules_for(base, '.teaser-card:first-child')[0])
        self.assertIn('margin-top:72px', rules_for(base, '.teaser-card:last-child')[0])
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
        # Daylight (Task 33): the hero has no photo (the devices show video posters from CSS and the headline is the
        # likely LCP element), so every photo on the page loads lazily and none asks for high priority.
        for index, (attrs, hidden) in enumerate(parser.images):
            with self.subTest(index=index, src=attrs.get('src')):
                for name in ('src', 'srcset', 'sizes', 'width', 'height', 'alt'):
                    self.assertIn(name, attrs)
                self.assertEqual(attrs.get('decoding'), 'async')
                self.assertEqual(attrs.get('loading'), 'lazy')
                self.assertNotIn('fetchpriority', attrs)
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
        # GSAP, then ScrollTrigger, then motion.js (then reel.js where there is video, then home.js on /): deferred, in that
        # order, only on the motion pages. Daylight (Task 34): no page loads details.js any more.
        for route in self.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                gsap_tags = INDEX_GSAP_TAGS if route == 'index.html' else HOME_GSAP_TAGS
                for tag in HOME_GSAP_TAGS:
                    self.assertEqual(html.count(tag), 1 if route in MOTION_ROUTES and tag in gsap_tags else 0)
                # Liquid Glass (Task 37): Lenis and glass.js follow the page scripts on every motion page; the WebGL boot
                # follows them on the homepage and the inner pages (Tasks 39 and 40). Contact loads only the boot; Demo and 404
                # load neither.
                for tag in GLASS_TAGS:
                    self.assertEqual(html.count(tag), 1 if route in MOTION_ROUTES else 0)
                self.assertEqual(html.count(GLASS_BOOT_TAG), 1 if route in GL_ROUTES else 0)
                self.assertEqual(html.count('glass-scene.js'), 0)  # imported by glass-boot.js only, never a <script>
                self.assertEqual(html.count('glass-page.js'), 0)
                self.assertEqual(html.count(DETAILS_TAG), 0)
                self.assertNotIn('details.js', html)
                self.assertEqual(html.count(HOME_TAG), 1 if route == 'index.html' else 0)
                self.assertEqual(html.count(REEL_TAG), 1 if route in REEL_ROUTES else 0)
                self.assertEqual(html.count(SCENES_TAG), 1 if route in SCENES_ROUTES else 0)
                self.assertEqual(html.count('scenes.js'), 1 if route in SCENES_ROUTES else 0)
                if route in MOTION_ROUTES:
                    tags = (gsap_tags + ([SCENES_TAG] if route in SCENES_ROUTES else []) + ([REEL_TAG] if route in REEL_ROUTES else [])
                            + ([HOME_TAG] if route == 'index.html' else []) + GLASS_TAGS + ([GLASS_BOOT_TAG] if route in GL_ROUTES else []))
                    positions = [html.index(tag) for tag in tags]
                    self.assertEqual(positions, sorted(positions))
                    self.assertGreater(positions[0], html.index('</footer>'))
                else:
                    self.assertNotIn('gsap', html.lower())
                    self.assertNotIn('scrolltrigger', html.lower())
                    self.assertNotIn('motion.js', html.lower())
        for name in ('gsap.min.js', 'ScrollTrigger.min.js', 'LICENSE.txt'):
            self.assertTrue((OUT / 'assets/vendor/gsap' / name).is_file())
        # reel.js grew from 3 KB to 4 KB in Daylight (Task 33) and to 10 KB in Task 34 (one large video at a time, the film's
        # progress, the hover previews); motion.js to 12 KB (the Pricing quote-sheet opening) and the inner pages' scroll
        # scenes went to their own scenes.js (8 KB). Every page stays inside the plan's 30 KB of first-party script
        # (test_first_party_javascript_budget_per_page).
        # Liquid Glass (Task 37): the shared shell (glass.js) and the WebGL boot (glass-boot.js, at most 2 KB) follow the
        # same rules.
        budgets = {'home.js': 12 * 1024, 'motion.js': 12 * 1024, 'motion-boot.js': 1024, 'details.js': 6 * 1024, 'reel.js': 10 * 1024,
                   'scenes.js': 8 * 1024, 'glass.js': 7 * 1024, 'glass-boot.js': 2 * 1024}
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
        for name in ('home.js', 'motion.js', 'details.js', 'scenes.js'):
            with self.subTest(script=name):
                self.assertIn('if (!gsap || !ScrollTrigger)', scripts[name])
                self.assertIn('gsap.matchMedia()', scripts[name])
                self.assertIn("'(prefers-reduced-motion: no-preference)'", scripts[name])
        # Daylight (Task 33): there is no first-visit intro any more. Without GSAP the CSS hold is released before returning.
        self.assertIn('if (!gsap || !ScrollTrigger) { release(); return; }', js)
        for gone in ('ns-intro', 'SKIP_EVENTS', 'onSkip', 'sessionStorage', "'.intro"):
            with self.subTest(gone_from_home=gone):
                self.assertNotIn(gone, js)
        # Night Shift Task 28: no pinned project sequence. Task 29: the video controller is reel.js, shared by every page
        # with video; it needs no GSAP and observes each video's visibility instead of listening to scroll.
        reel = scripts['reel.js']
        for name in ('home.js', 'reel.js', 'details.js', 'motion.js', 'scenes.js'):
            with self.subTest(script=name):
                self.assertNotIn('pin:', scripts[name])
                self.assertNotIn('PIN_', scripts[name])
                self.assertNotIn("addEventListener('scroll'", scripts[name])
                self.assertNotIn('autoplay', scripts[name])
        for needle in ('[data-reel]', 'IntersectionObserver', 'removeAttribute', 'video.play(', 'video.pause('):
            with self.subTest(gone_from_home=needle):
                self.assertNotIn(needle, js.replace("doc.querySelector('[data-reel]')", ''))  # home.js only finds the frame
        for needle in ('window.gsap', 'gsap.', 'ScrollTrigger'):  # playback needs no GSAP
            self.assertNotIn(needle, reel)
        for name in ('motion.js', 'scenes.js'):
            for needle in ('video.play(', 'video.pause(', 'IntersectionObserver', '<video', 'createElement', '.play(', '.pause('):
                with self.subTest(script=name, needle=needle):
                    self.assertNotIn(needle, scripts[name])  # neither plays video: reel.js is the one controller
        self.assertIn("const NARROW = '(max-width: 640px)';", reel)
        self.assertIn('new win.IntersectionObserver(', reel)
        self.assertIn("video.removeAttribute('controls')", reel)
        self.assertIn('toggle.hidden = false', reel)
        self.assertIn("doc.querySelectorAll('[data-reel]').forEach(", reel)
        self.assertIn("doc.querySelectorAll('video[data-loop]')", reel)  # Task 33: the hero loops share the controller
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
        for name in ('home.js', 'motion.js', 'details.js', 'scenes.js'):
            with self.subTest(script=name):
                self.assertNotRegex(scripts[name], r'(?<![-\w])(height|width|top|left|right|bottom|margin|padding)\s*:\s*[-\d\'"]')

    def test_motion_boot_script_runs_first_on_every_motion_page(self):
        # Daylight (Task 33): the boot script no longer opts the homepage into a first-visit intro; on every motion page it
        # sets .js/.motion and the opening hold (.ph-wait) in <head>, before first paint, with a failsafe that drops the hold
        # within 3 s (the plan's limit) whatever happens.
        boot = '<script src="/assets/motion-boot.js"></script>'
        for route in self.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                head = html.split('</head>', 1)[0]
                self.assertEqual(head.count(boot), 1 if route in MOTION_ROUTES else 0)
                self.assertEqual(html.count('motion-boot.js'), 1 if route in MOTION_ROUTES else 0)
                self.assertNotIn('data-intro', html)
        js = (OUT / 'assets/motion-boot.js').read_text()
        self.assertIn("c.add('js')", js)
        self.assertIn("c.add('motion')", js)
        self.assertIn("matchMedia('(prefers-reduced-motion: reduce)').matches) return;", js)
        for gone in ('ns-intro', 'data-intro', 'sessionStorage', 'cendavo-intro'):
            self.assertNotIn(gone, js)
        delay = re.search(r"setTimeout\(function \(\) \{ c\.remove\('ph-wait'\); \}, (\d+)\)", js)
        self.assertIsNotNone(delay)
        self.assertLessEqual(int(delay.group(1)), 3000)

    def test_homepage_has_no_intro_and_the_headline_is_plain_text(self):
        # Daylight (Task 33) drops the first-visit intro panel. The hero headline is the full sentence as ordinary text:
        # no aria-label replacing it and nothing in it hidden from assistive technology (the Task 23/27 regression hid it
        # visually; this keeps it whole for everyone). Only the guarded .ph-wait hold moves its lines, and motion-boot.js
        # drops that hold within 3 s.
        main = self.home_main
        self.assertNotIn('class="intro', main)
        for gone in ('.intro', '.ns-intro', 'intro-'):
            self.assertNotIn(gone, self.home_css)
        hero = re.search(r'<section class="hero"[^>]*>', main).group(0)
        self.assertNotIn('aria-hidden', hero)
        self.assertNotIn('inert', main)
        h1 = re.search(r'<h1([^>]*)>(.*?)</h1>', main, re.S)
        self.assertEqual(h1.group(1), ' id="hero-title" class="hero-h"')
        self.assertNotIn('aria-', h1.group(2))
        self.assertEqual(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', h1.group(2))).strip(), 'Your work is excellent. Your website should say so.')
        unguarded, guarded = without_blocks(self.home_css, MOTION_GUARD)
        for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', unguarded, flags=re.S)):
            if re.search(r'\.hero-h|\.ln\b|\.hero-copy', selectors):
                with self.subTest(rule=selectors.strip()):
                    self.assertNotRegex(body, r'transform|opacity|clip-path|visibility|display:none')
        holds = [sel.strip() for sel, _ in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', ''.join(guarded), flags=re.S))
                 if re.search(r'\.hero-h|\.ln\b', sel)]
        self.assertEqual(holds, ['.ph-wait .hero-h .ln>span'])

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
        # The plan's Daylight budget (Task 34): at most 30 KB of first-party script on any page (GSAP excluded). Contact, Demo
        # and the 404 page keep the 15 KB cap.
        for route in self.ROUTES + ['404.html']:
            with self.subTest(route=route):
                sources = re.findall(r'<script src="(/assets/[^"]+)"', (OUT / route).read_text())
                own = [src for src in sources if not src.startswith('/assets/vendor/')]
                budget = 30 * 1024 if route in MOTION_ROUTES else 15 * 1024
                self.assertLessEqual(sum((OUT / src.lstrip('/')).stat().st_size for src in own), budget)

    def test_home_stylesheet_loads_only_on_homepage(self):
        tag = '<link rel="stylesheet" href="/assets/home.css">'
        for route in self.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertEqual(html.count(tag), 1 if route == 'index.html' else 0)
                self.assertEqual(html.count('<link rel="stylesheet" href="/assets/site.css">'), 1)
                # Inner pages share one page stylesheet; the homepage never loads it.
                self.assertEqual(html.count('<link rel="stylesheet" href="/assets/pages.css">'), 0 if route == 'index.html' else 1)
                # Work, Services, Pricing and About add their own sheet after it, and load no other page's sheet.
                sheets = re.findall(r'<link rel="stylesheet" href="/assets/([a-z]+\.css)">', html)
                own = OWN_SHEET_ROUTES.get(route)
                for name in OWN_SHEET_ROUTES.values():
                    self.assertEqual(sheets.count(name), 1 if name == own else 0)
                if own:
                    self.assertLess(sheets.index('pages.css'), sheets.index(own))
                    self.assertEqual(sheets[-1], own)
                # The mockup kit loads once, before the page stylesheets, only where mockups appear.
                kit = '<link rel="stylesheet" href="/assets/kit.css">'
                self.assertEqual(html.count(kit), 1 if route in KIT_ROUTES else 0)
                if route in KIT_ROUTES:
                    page_style = re.search(r'<link rel="stylesheet" href="/assets/(?:home|pages)\.css">', html).start()
                    self.assertLess(html.index('<link rel="stylesheet" href="/assets/site.css">'), html.index(kit))
                    self.assertLess(html.index(kit), page_style)

    def test_motion_is_guarded_and_compositor_only(self):
        for name in SHEETS:
            css = (OUT / 'assets' / name).read_text()
            unguarded, guarded = without_blocks(without_view_transitions(css), MOTION_GUARD)
            if name == 'site.css':
                self.assertTrue(guarded)
            for word in ('transition', 'animation', '@keyframes'):
                with self.subTest(css=name, word=word):
                    self.assertNotIn(word, unguarded)
            for block in guarded:
                for value in re.findall(r'transition:([^;}]+)', block):
                    properties = [part.split()[0] for part in value.split(',')]
                    self.assertTrue(set(properties) <= {'transform', 'opacity'}, value)
                    for duration in re.findall(r'var\(--dur-(\d)\)', value):
                        self.assertEqual(duration, '1', value)  # hover feedback within 200 ms
                self.assertNotIn('animation', block)

    def test_reveal_states_come_from_javascript_only(self):
        # Content stays visible without JS, if GSAP fails, and with reduced motion: CSS never hides it.
        for name in SHEETS:
            css = (OUT / 'assets' / name).read_text()
            with self.subTest(css=name):
                unguarded, guarded = without_blocks(without_view_transitions(css), MOTION_GUARD)
                guarded = re.sub(r'/\*.*?\*/', '', ''.join(guarded), flags=re.S)
                for hook in ('data-rise', 'data-hero-fade') + MOTION_HOOKS + REEL_HOOKS:
                    self.assertNotIn(hook, css)
                self.assertNotRegex(unguarded, r'opacity:0(?![.\d])')
                self.assertNotIn('visibility:hidden', unguarded)
                # Night Shift Task 23: the one exception is the page openings' start states, guarded and only while
                # motion-boot.js holds .ph-wait. Any guarded rule that hides content (opacity:0, an off-mask transform or a
                # closed clip-path) must be such a .ph-wait rule.
                self.assertNotIn('.ph-wait', re.sub(r'/\*.*?\*/', '', unguarded, flags=re.S))
                for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', guarded):
                    hides = re.search(r'opacity:0(?![.\d])|translateY\(1\d\d%\)|clip-path:inset\([^)]*100%', body)
                    if hides:
                        with self.subTest(css=name, selectors=selectors.strip()[:60]):
                            # Top-level selectors only: commas inside :is(...) do not split a selector.
                            parts = [part.strip() for part in re.sub(r'\([^()]*\)', '()', selectors).split(',')]
                            # Task 39: or .gl-lead, which only glass-page.js sets, after its scene has drawn the anchor's
                            # media in WebGL (and never with reduced motion, so the guard is belt and braces).
                            self.assertTrue(all(part.startswith(('.ph-wait ', '.gl-lead ')) for part in parts), selectors)
                self.assertNotIn('.gl-lead', re.sub(r'/\*.*?\*/', '', unguarded, flags=re.S))

    def test_layout_basics(self):
        for selector, css in (('.button{', self.css), ('.menu{', self.css), ('.compare-button{', self.home_css),
                              ('.motion-btn{', (OUT / 'assets/glass.css').read_text()), ('.vt{', self.kit_css)):
            with self.subTest(selector=selector):
                rule = css.split(selector, 1)[1].split('}', 1)[0]
                height = re.search(r'min-height:(\d+)px', rule)
                self.assertIsNotNone(height)
                self.assertGreaterEqual(int(height.group(1)), 44)  # tap targets of at least 44px
        self.assertIn(':focus-visible{', self.css)
        self.assertIn('@media(max-width:640px){', self.css)
        for name in SHEETS:
            with self.subTest(css=name):
                self.assertLessEqual((OUT / 'assets' / name).stat().st_size, 30 * 1024)

    def test_mockup_kit_is_defined_once_and_shared(self):
        # Task 12, restated for Daylight (Task 34): the device bench, the phone frame and the homepage mini-site live only in
        # kit.css and the quote sheet only in pricing.css, not copied per page. Base rules only: responsive overrides inside
        # @media/@container blocks are not second definitions.
        sheets = {name: base_rules((OUT / 'assets' / name).read_text()) for name in SHEETS}
        homes = {'.bench{': 'kit.css', '.bench-stage{': 'kit.css', '.d-lap{': 'kit.css', '.d-scr{': 'kit.css', '.d-ph{': 'kit.css',
                 '.d-ph-scr{': 'kit.css', '.d-video{': 'kit.css', '.ui{': 'kit.css', '.sp{': 'kit.css', '.sp-frame{': 'kit.css',
                 '.sp-video{': 'kit.css', '.ms{': 'kit.css', '.hb{': 'kit.css', '.quote-paper{': 'pricing.css',
                 '.q-lines li{': 'pricing.css', '.q-total{': 'pricing.css'}
        for selector, home in homes.items():
            with self.subTest(selector=selector):
                pattern = r'(?:^|[}\n])' + re.escape(selector)
                counts = {name: len(re.findall(pattern, css)) for name, css in sheets.items()}
                self.assertEqual(sum(counts.values()), 1, counts)
                self.assertEqual(counts[home], 1, counts)
        # The Night Shift mockups (mini-site laptops and phones, the old quote sheet and clip frame) are gone with their pages.
        for gone in ('.laptop', '.phone{', '.phone-screen', '.gls', '.fcd', '.hbm', '.quote-top', '.clip-phone', '.clip-toggle'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, ''.join(sheets.values()))

    def test_how_it_works_has_quiet_numerals_a_photo_and_readable_steps(self):
        # The five steps live on /services/ (Night Shift Task 28), after the Care plan and before the questions. Daylight
        # (Task 34): numbered circles on one line that draws itself once (motion.js), a photo beside the heading.
        services = main_of((OUT / 'services/index.html').read_text())
        section = re.search(r'<section class="sec band-warm process" aria-labelledby="process-title">(.*?)</section>', services, re.S)
        self.assertIsNotNone(section)
        section = section.group(1)
        self.assertLess(services.index('<section class="sec band-warm process"'), services.index('id="sv-faq-title"'))
        self.assertGreater(services.index('<section class="sec band-warm process"'), services.index('id="care-title"'))
        self.assertIn('<h2 id="process-title" class="h2" data-rise>How it works</h2>', section)
        self.assertNotIn('.step', self.home_css)
        steps = re.findall(r'<li class="step">(.*?)</li>', section, re.S)
        self.assertEqual([re.search(r'<h3>(.*?)</h3>', s).group(1) for s in steps], ['Discover', 'Design', 'Build', 'Launch', 'Look after'])
        for number, step in enumerate(steps, 1):
            with self.subTest(step=number):
                self.assertIn(f'<span class="step-n" aria-hidden="true">{number:02d}</span>', step)
                self.assertLess(step.index('step-n'), step.index('<h3>'))
        self.assertIn('<span class="steps-line" aria-hidden="true"><i data-line-fill></i></span>', section)
        parser = ImageCollector()
        parser.feed(section)
        self.assertEqual(len(parser.images), 1)
        attrs, hidden = parser.images[0]
        self.assertEqual(attrs.get('loading'), 'lazy')
        self.assertTrue(attrs.get('width') and attrs.get('height'))
        self.assertTrue(attrs.get('alt', '').strip())
        self.assertFalse(hidden)
        css = base_rules((OUT / 'assets/services.css').read_text())
        numeral = rules_for(css, '.step-n')[0]
        self.assertIn('var(--font-display)', numeral)
        self.assertIn('width:44px;height:44px', numeral)
        self.assertIn('background:var(--amber)', rules_for(css, '.step:last-child .step-n')[0])
        self.assertIn('transform-origin:left', rules_for(css, '.steps-line i')[0])
        rules = rules_for(css, '.step p')
        self.assertTrue(rules)
        for rule in rules:
            self.assertGreaterEqual(minimum_px(re.search(r'font-size:([^;]+)', rule).group(1)), 17)
        narrow = media_blocks((OUT / 'assets/services.css').read_text(), 'max-width:960px')
        self.assertIn('grid-template-columns:minmax(0,1fr)', rules_for(narrow, '.steps')[0])
        self.assertIn('transform-origin:top', rules_for(narrow, '.steps-line i')[0])

    def test_pricing_teaser_shows_the_quote_sheet_without_prices(self):
        # Night Shift Task 28: the homepage carries no pricing band; the quote sheet is shown once, on /pricing/ (Daylight,
        # Task 34: in its hero), and no amount appears anywhere.
        self.assertNotIn('class="pricing', self.home_main)
        self.assertNotIn('pricing-media', self.home_css)
        self.assertNotIn('quote-paper', self.home_main)
        self.assertNotIn('Always included', self.home_main)
        self.assertNotIn('inc-list', self.home_main)
        self.assertNotIn('barber-client', (OUT / 'index.html').read_text())
        pricing = main_of((OUT / 'pricing/index.html').read_text())
        self.assertIn('fixed quote after a free consultation', visible_text(pricing).lower())
        hero = re.search(r'<section class="pg-hero pr-hero"[^>]*>.*?</section>', pricing, re.S).group(0)
        paper = re.search(r'<div class="quote-paper" data-sheet role="img" aria-label="([^"]+)">(.*?)</div>\n</div>\n<figcaption>', hero, re.S)
        self.assertIsNotNone(paper)
        self.assertTrue(paper.group(1).startswith('Illustration'))
        self.assertIn('one fixed price', paper.group(1))
        children = re.findall(r'<(?:div|ul) class="q-[a-z]+"([^>]*)>', paper.group(2))
        self.assertEqual(len(children), 4)
        for attrs in children:
            with self.subTest(child=attrs):
                self.assertIn('aria-hidden="true"', attrs)
        self.assertIn('<b>Fixed price</b><span>Agreed before work starts</span>', paper.group(2))
        self.assertEqual(pricing.count('data-sheet'), 1)
        for page in (self.home_main, pricing):
            self.assertNotRegex(page, r'\$\s*\d')
            self.assertNotIn('A$', page)

    def test_questions_sit_in_two_columns(self):
        # The homepage has no questions; Services and Pricing keep a two-column FAQ (heading left, answers right).
        self.assertNotIn('<details', self.home_main)
        self.assertNotIn('.questions', self.home_css)
        for route, title, heading in (('services/index.html', 'sv-faq-title', 'Questions owners ask us'), ('pricing/index.html', 'pr-faq-title', 'Straight answers')):
            with self.subTest(route=route):
                main = main_of((OUT / route).read_text())
                section = re.search(rf'<section class="sec" aria-labelledby="{title}"><div class="wrap faq-grid">(.*?)</section>', main, re.S).group(1)
                self.assertIn(f'<div class="faq-head"><h2 id="{title}" class="h2" data-rise>{heading}</h2>', section)
                self.assertGreaterEqual(section.count('<details>'), 5)
                self.assertLess(section.index('<h2'), section.index('<details>'))
        base = base_rules(self.pages_css)
        self.assertEqual(rules_for(base, '.faq-head'), ['grid-column:1/5'])
        self.assertIn('grid-column:6/13', rules_for(base, '.faq')[0])
        self.assertIn('min-height:76px', rules_for(base, '.faq summary')[0])
        self.assertIn('grid-column:1/-1', rules_for(media_blocks(self.pages_css, 'max-width:900px'), '.faq-head,.faq')[0] if rules_for(media_blocks(self.pages_css, 'max-width:900px'), '.faq-head,.faq') else rules_for(media_blocks(self.pages_css, 'max-width:900px'), '.faq')[0])

    def test_every_page_class_has_a_css_rule(self):
        # The homepage loads site.css + kit.css + home.css; inner pages load site.css + pages.css, their own sheet (Work,
        # Services, Pricing, About) and, on Work and Services, kit.css.
        pages = Path(__file__).resolve().parents[1] / 'pages'
        checked = 0
        for page in pages.glob('*.html'):
            route = 'index.html' if page.stem == 'index' else '404.html' if page.stem == '404' else f'{page.stem}/index.html'
            css = self.css + (OUT / 'assets/glass.css').read_text() + (self.home_css if page.stem == 'index' else self.pages_css)
            if route in OWN_SHEET_ROUTES:
                css += (OUT / 'assets' / OWN_SHEET_ROUTES[route]).read_text()
            if route in KIT_ROUTES:
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
        # Task 12: each concept project shows its key screens; the mock text and photos stay silent. Daylight (Task 34): one
        # device bench per project, a laptop and a phone playing that concept's screen-recording loops (reel.js), inside one
        # described role="img" group; every device part, video and interface card is aria-hidden.
        main = self.main['work/index.html']
        rest, stems = main, set()
        for slug, short, name in (('harbourside', 'hb', 'Harbourside'), ('greenline', 'gl', 'Greenline'), ('fade-co', 'fc', 'Fade and Co')):
            with self.subTest(project=slug):
                article = re.search(rf'<article [^>]*id="{slug}"[^>]*>(.*?)</article>', main, re.S).group(1)
                self.assertEqual(article.count(' data-bench='), 1)
                screens = re.search(rf'<section class="cs-screens" aria-labelledby="{short}-title ([^"]+)">(.*?)</section>', article, re.S)
                self.assertIsNotNone(screens)
                self.assertRegex(screens.group(2), rf'<h3 id="{screens.group(1)}"[^>]*>Key screens</h3>')
                bench = re.search(rf'<figure class="bench b-{short}" data-bench="{short}">(.*?)</figure>', screens.group(2), re.S)
                self.assertIsNotNone(bench)
                self.assertLess(screens.group(2).index('Key screens'), screens.group(2).index(' data-bench='))
                block = bench.group(1)
                rest = rest.replace(block, '')
                groups = re.findall(r'<div class="bench-stage" role="img" aria-label="([^"]+)">', block)
                self.assertEqual(len(groups), 1)
                self.assertEqual(block.count('role="img"'), 1)
                self.assertIn(name, groups[0])
                self.assertIn('laptop and a phone playing short screen recordings', groups[0])
                self.assertRegex(block, r'<figcaption class="bench-cap">[^<]{20,}</figcaption>$')
                stage = block.split('<figcaption', 1)[0]
                parts = re.findall(r'<div class="(?:bench-plinth|bench-floor|d-lap|d-ph|ui [^"]*)"([^>]*)>', stage)
                self.assertEqual(len(parts), 6)  # plinth, floor, laptop, phone and two interface cards
                for part in parts:
                    self.assertIn('aria-hidden="true"', part)
                videos = re.findall(r'<video ([^>]*)><source data-src="([^"]+)" type="video/mp4"></video>', stage)
                self.assertEqual([src for _, src in videos], [f'/assets/video/loop-{short}-desktop.mp4', f'/assets/video/loop-{short}-phone.mp4'])
                for (attrs, src), (poster, size, loop) in zip(videos, ((f'loop-{short}-desktop-poster-800.jpg', ('1280', '800'), 'data-loop="wide"'),
                                                                       (f'loop-{short}-phone-poster-390.jpg', ('780', '1688'), 'data-loop '))):
                    with self.subTest(video=src):
                        for needle in ('aria-hidden="true"', 'muted loop playsinline preload="none"', loop,
                                       f'poster="/assets/video/{poster}"', f'width="{size[0]}" height="{size[1]}"'):
                            self.assertIn(needle, attrs + ' ')
                        self.assertNotIn('autoplay', attrs)
                        self.assertNotIn('controls', attrs)
                        self.assertTrue((OUT / 'assets/video' / poster).is_file())
                        self.assertTrue((OUT / src.lstrip('/')).is_file())
                parser = ImageCollector()
                parser.feed(stage)
                for attrs, hidden in parser.images:
                    with self.subTest(img=attrs.get('src')):
                        self.assertTrue(hidden)
                        self.assertEqual(attrs.get('alt'), '')
                        self.assertEqual(attrs.get('loading'), 'lazy')
                        self.assertEqual(attrs.get('decoding'), 'async')
                        self.assertTrue(attrs.get('width') and attrs.get('height'))
                        self.assertRegex(attrs['src'], r'^/assets/images/[a-z-]+-800\.jpg$')
                        stems.add(attrs['src'].rsplit('-', 1)[0])
        # Page weight: the benches load only these photos (small, inside their interface cards) that the rest of the Work
        # page does not already load. The exact set is pinned so any further addition fails.
        elsewhere = {url.rsplit('-', 1)[0] for url in re.findall(r'/assets/images/[a-z-]+-(?:800|1600)\.jpg', rest)}
        self.assertEqual({stem.rsplit('/', 1)[1] for stem in stems - elsewhere}, {'barber-cut', 'garden-deck', 'garden-lawn', 'garden-wall'})

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
        self.assertEqual(main.count(MAIL_LINK), 3)  # Task 31: beside the form and in the privacy note; Task 47: the no-JS notice
        self.assertNotIn('@', main.replace(MAIL_LINK, ''))
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
                # Task 28: the showreel's <video> has the one other kind of <source> (an mp4); Task 29 adds one per social clip
                # (two on Services, one on Work). Daylight (Task 33): the two hero loops carry data-src until reel.js plays them;
                # Task 34 adds Work's six device loops and the Services Care plan phone loop, the same way.
                video_sources = re.findall(r'<source (?:data-)?src="[^"]+\.mp4" type="video/mp4">', main)
                # Liquid Glass (Task 37): the homepage's four silent loops (marquee and closing footage, two glass phones).
                # Task 41: plus the ambient glass loop behind the closing panel on Work, Services, Pricing and About.
                self.assertEqual(main.count('<source data-src='), {'index.html': 4, 'work/index.html': 7, 'services/index.html': 2, 'pricing/index.html': 1, 'about/index.html': 1}.get(route, 0))
                self.assertEqual(len(video_sources), VIDEOS_PER_ROUTE.get(route, 0))
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
        # that links to Pricing's full list. Night Shift Task 28: the trades row moved here from the homepage, just before
        # the closing call to action. Daylight (Task 34): the launch film "Cendavo in 20 seconds" follows "How we think".
        self.assertEqual(h2s[:4], ['How we think', 'Cendavo in 20 seconds', 'How we build',
                                   'Built for the businesses that keep Sydney running'])
        self.assertEqual(len(h2s), 5)  # the fifth is the closing call to action
        order = [self.main.index(f'aria-labelledby="{name}"') for name in ('ab-think-title', 'film-title', 'ab-build-title', 'who-title', 'close-title')]
        self.assertEqual(order, sorted(order))
        self.assertEqual(self.main.rsplit('<section', 1)[1].count('aria-labelledby="close-title"'), 1)
        think = self.main.split('id="ab-think-title"', 1)[1].split('<h2', 1)[0]
        self.assertTrue(3 <= think.count('<h3') <= 4)
        self.assertNotIn('ab-expect-title', self.source)
        self.assertNotIn('class="exp"', self.source)
        # "How we build" is one typographic band: four large statements, no card grid and no photo.
        build = re.search(r'<section class="sec" aria-labelledby="ab-build-title">(.*?)</section>', self.main, re.S).group(1)
        self.assertNotIn('inc-grid', build)
        self.assertNotIn('<img', build)
        self.assertEqual(re.search(r'<ul class="build-list" data-stagger>(.*?)</ul>', build, re.S).group(1).count('<li>'), 4)
        promise = re.search(r'<p class="promise">(.*?)</p>', build, re.S).group(1)
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
        # Night Shift Task 21: the opening holds three decorative photos beside the headline. Daylight (Task 34): a collage
        # in the prototype's source order (large, small, large); below it, at most two more photos than the trades row.
        hero, rest = self.main.split('</section>', 1)
        parser = ImageCollector()
        parser.feed(hero)
        names = [re.search(r'/images/([a-z-]+)-(?:800|1600)\.jpg$', attrs['src']).group(1) for attrs, _ in parser.images]
        self.assertEqual(names, ['barber-shave', 'detail-wax', 'garden-wall'])
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
        self.assertLess(hero.index('</h1>'), hero.index('<div class="ab-photos"'))  # the collage, not the scene host's anchor (Task 40)
        below = ImageCollector()
        below.feed(rest)
        # Below the opening: the "How we think" photo, the five trades photos moved from the homepage (Task 28, same
        # photos, alt text and captions) and the closing photo (Daylight: the headlight, as in the prototype). The film is
        # a <video> with a poster, not a photo. The exact set is pinned so any further addition fails.
        names = [re.search(r'/images/([a-z-]+)-(?:800|1600)\.jpg$', attrs['src']).group(1) for attrs, _ in below.images]
        self.assertEqual(names, ['barber-cut', 'clean-living', 'trade-panel', 'barber-cut', 'garden-lawn', 'detail-wax', 'detail-headlight'])
        row = re.search(r'<ul class="wrap who-row" data-stagger>(.*?)</ul>', rest, re.S).group(1)
        self.assertEqual(re.findall(r'<figcaption>([^<]+)</figcaption>', row),
                         ['Cleaners', 'Electricians and trades', 'Barbers', 'Landscapers', 'Mobile detailers'])
        self.assertEqual(re.findall(r' alt="([^"]+)"', row),
                         ['A cleaner mopping the floor of a bright living room', 'An electrician in gloves testing a switchboard with probes',
                          'A barber trimming the back of a client’s hair with scissors', 'A landscaped backyard with a stone wall, pergola and lawn',
                          'A detailer fitting protective film over the headlight of a grey car'])
        # Daylight motion rules allow at most two depth layers on scroll: the row arrives in reading order (data-stagger)
        # instead of five parallax frames.
        self.assertEqual(row.count('data-parallax'), 0)
        described = [attrs for attrs, hidden in below.images if not hidden]
        self.assertTrue(described)
        for attrs, _ in below.images:
            with self.subTest(src=attrs['src']):
                self.assertEqual(attrs.get('loading'), 'lazy')  # every photo below the opening is lazy
        for attrs in described:
            self.assertTrue(attrs['alt'].strip())
        self.assertNotIn('barber-tools', self.html)

    def test_opening_sets_copy_left_and_staggered_photos_right(self):
        # Daylight (Task 34): copy on the left half, a three-photo collage on the right whose square box reserves its space
        # before any photo loads; the photos are staggered across a 12 x 12 grid inside it, never past the page gutter.
        css = (OUT / 'assets/about.css').read_text()
        base = base_rules(css)
        self.assertIn('grid-column:1/7', rules_for(base, '.ab-hero-copy')[0])
        photos = rules_for(base, '.ab-photos')[0]
        self.assertIn('grid-column:8/13', photos)
        self.assertIn('aspect-ratio:1/1', photos)
        self.assertIn('gap:12px', photos)
        self.assertNotIn('margin-right:calc(-1', photos)
        cells = {name: rules_for(base, name)[0] for name in ('.ab-p1', '.ab-p2', '.ab-p3')}
        self.assertEqual(cells, {'.ab-p1': 'grid-column:1/9;grid-row:1/7', '.ab-p2': 'grid-column:4/13;grid-row:7/13',
                                 '.ab-p3': 'grid-column:9/13;grid-row:3/7'})
        narrow = media_blocks(css, 'max-width:1023px')
        self.assertIn('grid-column:1/-1', rules_for(narrow, '.ab-photos')[0])
        self.assertIn('grid-column:1/-1', rules_for(narrow, '.ab-hero-copy')[0])
        self.assertIn('margin-top:40px', rules_for(narrow, '.ab-photos')[-1])

    def test_reuses_shared_assets_and_motion_hooks_only(self):
        # Daylight (Task 34): the shared inner-page sheet plus About's own; reel.js plays the launch film. No details.js.
        self.assertEqual(re.findall(r'<link rel="stylesheet" href="([^"]+)">', self.head), ['/assets/site.css', '/assets/glass.css', '/assets/pages.css', '/assets/about.css'])
        scripts = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertEqual(scripts, ['/assets/motion-boot.js', '/assets/site.js', '/assets/vendor/gsap/gsap.min.js',
                                   '/assets/vendor/gsap/ScrollTrigger.min.js', '/assets/motion.js', '/assets/scenes.js', '/assets/reel.js',
                                   '/assets/vendor/lenis/lenis.min.js', '/assets/glass.js',  # Liquid Glass shell (Task 37)
                                   '/assets/glass-boot.js'])  # the WebGL scene boot (Task 40)
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


def module_graph(entry):
    """Every file an ES module loads, itself included: its static `import ... from '...'` (and `export ... from '...'`)
    specifiers, followed recursively. Task 48: what a page's WebGL scene makes the browser fetch."""
    seen, todo = [], [Path(entry).resolve()]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.append(path)
        text = path.read_text()
        for spec in re.findall(r"^\s*(?:import|export)\b[^;]*?\bfrom\s*'([^']+)'", text, re.M) + re.findall(r"^\s*import\s*'([^']+)'", text, re.M):
            todo.append((path.parent / spec).resolve())
    return seen


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
        # Restated for Daylight (Task 34): the index's rules live in work.css and never override .wrap's gutter.
        self.assertIn('<ul class="wrap wk-index" data-stagger aria-label="Projects on this page">', self.work)
        self.assertIn('.wrap{width:100%;max-width:var(--max);margin-inline:auto;padding-inline:var(--gut)}', self.css)
        work_css = (OUT / 'assets/work.css').read_text()
        base = base_rules(work_css)
        rules = rules_for(base, '.wk-index')
        self.assertEqual(len(rules), 1)  # no shared list reset overrides .wrap's gutter
        rule = rules[0]
        self.assertNotRegex(rule, r'(?<![-\w])(?:margin|padding)(?:-inline|-left|-right)?:')
        self.assertIn('grid-template-columns:repeat(4,minmax(0,1fr))', rule)
        self.assertIn('gap:24px', rule)
        self.assertNotIn('wk-index', self.pages_css)
        self.assertNotIn('.6fr', work_css)
        tablet = rules_for(media_blocks(work_css, 'max-width:1023px'), '.wk-index')
        self.assertEqual(tablet, ['grid-template-columns:repeat(2,minmax(0,1fr))'])
        self.assertEqual(rules_for(media_blocks(work_css, 'max-width:560px'), '.wk-index'), ['gap:20px 12px'])
        for query in ('max-width:1023px', 'max-width:960px', 'max-width:860px', 'max-width:560px'):
            for rule in rules_for(media_blocks(work_css, query), '.wk-index'):
                self.assertNotRegex(rule, r'(?<![-\w])(?:margin|padding)(?:-inline|-left|-right)?:')

    def test_harbourside_cover_text_meets_contrast_over_white(self):
        # Restated for Daylight (Task 34): Harbourside is the one photographic cover, with white and amber type on the
        # photo. The copy block carries its own full-width scrim, clear at its top edge and at least .88 ink from inside its
        # top padding (above the label) to the bottom, so the contrast holds however the title wraps. Checked over pure
        # white as the worst case for the photo behind it.
        work_css = (OUT / 'assets/work.css').read_text()
        base = base_rules(work_css)
        self.assertIn('position:relative', rules_for(base, '.cs-cover-in')[0])
        top_padding = int(re.search(r'padding-top:(\d+)px', rules_for(base, '.cs-cover-in')[0]).group(1))
        scrim = rules_for(base, '.cs-cover-in::before')
        self.assertEqual(len(scrim), 1)
        for part in ('position:absolute', 'z-index:-1', 'top:0', 'bottom:0', 'left:-100vw', 'right:-100vw'):
            self.assertIn(part, scrim[0])
        stops = [(float(a), int(px)) for a, px in re.findall(r'rgba\(14,14,13,([\d.]+)\) (\d+)px', scrim[0])]
        self.assertEqual(len(stops), 2)
        alpha, reached = stops[-1]
        self.assertGreaterEqual(alpha, 0.88)
        self.assertLess(reached, top_padding)  # full strength before the first line of type
        self.assertIn('overflow:hidden', rules_for(base, '.cs-cover')[0])  # the wide scrim never widens the page
        backdrop = ink_over_white(alpha)
        cover = rules_for(base, '.cs-cover')[0]
        self.assertIn('color:#fff', cover)  # the title and the fact values inherit white
        for selector in ('.cs-facts dd', '.cs-title'):
            for rule in rules_for(base, selector) + rules_for(base, '.cs-cover ' + selector):
                self.assertNotRegex(rule, r'(?<![-\w])color:')
        self.assertIn('color:var(--amber)', rules_for(base, '.cs-cover .cs-label')[0])
        self.assertIn('color:rgba(255,255,255,.78)', rules_for(base, '.cs-cover .cs-facts dt')[0])
        dt = '#' + ''.join(f'{round(.78 * 255 + .22 * int(backdrop[i:i + 2], 16)):02X}' for i in (1, 3, 5))
        for text, colour, minimum in (('label', self.tokens['--amber'], 4.5), ('dt', dt, 4.5), ('dd', '#FFFFFF', 4.5), ('title', '#FFFFFF', 3)):
            with self.subTest(text=text):
                self.assertGreaterEqual(contrast(colour, backdrop), minimum)
        self.assertNotIn('main{background:var(--ink)', self.pages_css)  # the inner pages' <main> is paper (Task 34)

    def test_concept_label_sits_under_each_title(self):
        # Homepage cards: the label sits directly under each title. Daylight Work (Task 34): the label is the eyebrow
        # directly above each project's title, once per project.
        home = re.findall(r'<article class="teaser-card"[^>]*>(.*?)</article>', self.home, re.S)
        work = re.findall(r'<article\b[^>]*>(.*?)</article>', self.work, re.S)
        self.assertEqual((len(home), len(work)), (3, 3))
        for article in home:
            with self.subTest(page='home', article=article[:60]):
                self.assertEqual(article.count(CONCEPT_LABEL), 1)
                label = article.index(CONCEPT_LABEL)
                title = article.index('</a></h3>')
                self.assertGreater(label, title)
                # Directly under the title: nothing but whitespace and the label's own opening tag between them.
                self.assertRegex(article[title + len('</a></h3>'):label], r'^\s*<p class="teaser-label">$')
        for article in work:
            with self.subTest(page='work', article=article[:60]):
                self.assertEqual(article.count(CONCEPT_LABEL), 1)
                # Task 43: the label rises with the title (both data-rise), so it never waits alone above a hidden title.
                self.assertRegex(article, rf'<p class="cs-label" data-rise>{re.escape(CONCEPT_LABEL)}</p>\s*<h2 id="[a-z]+-title" class="cs-title" data-rise>')
        # Liquid Glass (Task 37): the hero's screens show two concepts, so its glass caption says so in general terms.
        self.assertIn('<p class="hero-cap lg">On screen<span>Concept projects for fictional businesses</span></p>', self.home)
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
        # Liquid Glass (Task 37): on wide screens the lens opens to a larger frame. Task 44: full-bleed (up to the screen's
        # width), still never taller than 92% of the screen, and centred on the column (the margins match the width).
        wide = rules_for(media_blocks(self.home_css, 'min-width:961px'), '.reel-frame')[0]
        self.assertEqual(wide, 'width:min(100vw,calc(92svh * 16 / 9));margin-inline:calc(50% - min(50vw,46svh * 16 / 9))')
        self.assertIn('overflow-x:clip', rules_for(base_rules((OUT / 'assets/site.css').read_text()), 'body')[0])  # no sideways scroll

    def test_mobile_hero_puts_the_headline_and_buttons_first(self):
        # Liquid Glass (Task 37): the copy (headline, line, both buttons) comes before the glass cards and the caption in the
        # markup; below 1024px it spans the full width, the cards leave below 1200px, and at 760px and below the hero shows
        # the portrait still (logo on top) with the copy at the bottom on an opaque veil.
        tablet = media_blocks(self.home_css, 'max-width:1023px')
        self.assertIn('grid-column:1/-1', rules_for(tablet, '.hero-copy')[0])
        self.assertIn('grid-row:auto', rules_for(tablet, '.hero-copy')[0])
        self.assertEqual(rules_for(media_blocks(self.home_css, 'max-width:1199px'), '.hero-cards'), ['display:none'])
        hero = re.search(r'<section class="hero".*?</section>', self.home, re.S).group(0)
        for part in ('<p class="hero-sub"', '<div class="actions"'):
            self.assertLess(hero.index('<h1'), hero.index(part))
            self.assertLess(hero.index(part), hero.index('<div class="hero-cards"'))
        phone = media_blocks(self.home_css, 'max-width:760px')
        self.assertIn('background-image:url("/assets/glass/hero-glass-poster-m.jpg")', rules_for(phone, '.hero-gl')[0])
        self.assertIn('rgba(246,245,241,.96) 0%', rules_for(phone, '.hero-gl::after')[0])
        self.assertIn('width:100%', rules_for(media_blocks(self.home_css, 'max-width:640px'), '.actions .button')[0])
        self.assertNotIn('detail-darkroom', self.home)
        self.assertNotIn('hero-photo', self.home_css)

    def test_services_rows_do_not_slide(self):
        # Night Shift Task 17/21, restated for Daylight (Task 33): the What we do rows, their headings and their
        # illustrations never slide, scale or animate (the illustrations are still, in their finished state).
        self.assertNotIn('scale(.94)', self.home_css)
        self.assertNotIn('svc-panel', self.home_css)
        bare = re.sub(r'/\*.*?\*/', '', self.home_css, flags=re.S)
        checked = 0
        for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', bare):
            if re.search(r'\.(?:svc|vig|vb-|vr-|log)', selectors):
                checked += 1
                with self.subTest(rule=selectors.strip()[:60]):
                    self.assertNotRegex(body, r'transition|animation|translate|scale\(')
        self.assertGreaterEqual(checked, 20)

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
        self.assertRegex(foot, r'^<button class="button large" type="submit" disabled>Send enquiry</button><p class="form-promise">[^<]{20,120}</p>'
                               r'<p class="notice" id="enquiry-privacy">')
        line = re.search(r'<p class="form-promise">([^<]+)</p>', foot).group(1)
        for claim in ('person', 'plain language', 'no hard sell'):
            self.assertIn(claim, line)
        # Daylight (Task 34): one short line in ink-2 (above 4.5:1 on the warm form panel), never smaller than 15px.
        promise = rules_for(base_rules(self.pages_css), '.form-promise')
        self.assertEqual(len(promise), 1)
        for part in ('margin:0', 'max-width:62ch', 'color:var(--ink-2)'):
            self.assertIn(part, promise[0])
        self.assertGreaterEqual(minimum_px(re.search(r'font-size:([^;]+)', promise[0]).group(1)), 15)


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
        # Low contrast on purpose: it is a texture, not text anyone needs to read. Daylight (Task 33): light, on the paper footer.
        colour = re.search(r'(?<![-\w])color:(#[0-9A-Fa-f]{6})', rule).group(1)
        self.assertLess(contrast(colour, '#FFFFFF'), 1.5)
        self.assertNotIn('background', rules_for(base_rules(self.css), '.footer')[0])  # the footer sits on the paper body

    def test_closing_photo_differs_per_page(self):
        # Night Shift Task 21: Services no longer opens and closes on barbershop photos.
        # Night Shift Task 24: Services no longer closes on its own New website photo, and garden-lawn closes no page.
        # Daylight (Task 34): the inner pages close on the ink .close band; About closes on the headlight (prototype), so
        # Pricing and About no longer share a closing photo.
        expected = {'index.html': 'detail-rear', 'work/index.html': 'detail-rear', 'services/index.html': 'garden-path',
                    'pricing/index.html': 'garden-deck', 'about/index.html': 'detail-headlight'}
        for route, photo in expected.items():
            with self.subTest(route=route):
                main = main_of(self.html[route])
                band = re.search(r'<div class="(?:band|close)-media" aria-hidden="true"( data-parallax)?>(.*?)</div>', main, re.S)
                self.assertIsNotNone(band)
                # Daylight homepage (Task 33): no scrubbed parallax outside the hero, so its band photo is still.
                self.assertEqual(bool(band.group(1)), route != 'index.html')
                self.assertEqual(set(re.findall(r'/assets/images/([a-z-]+)-(?:800|1600)\.(?:jpg|avif)', band.group(2))), {photo})
                # Only the fixed Pause motion button (Work, Services) may follow the closing section.
                tail = re.sub(r'<button class="motion-btn motion-fab" type="button" data-motion-toggle aria-pressed="false" hidden>Pause motion</button>$', '', main.rstrip())
                self.assertTrue(tail.rstrip().endswith('</section>'))
                self.assertGreater(main.index(band.group(0)), main.rindex('<section'))  # it is the page's last section
        self.assertEqual(len(set(expected[r] for r in ('services/index.html', 'pricing/index.html', 'about/index.html'))), 3)
        for route in ('contact/index.html', 'demo/index.html', '404.html'):
            with self.subTest(route=route):
                self.assertNotIn('cta-band', self.html[route])
                self.assertNotIn('class="close"', self.html[route])
        for route in self.routes:
            with self.subTest(route=route):
                self.assertNotIn('barber-tools', self.html[route])

    def test_pricing_steps_sit_on_one_timeline(self):
        # Restated for Daylight (Task 34): three numbered steps on one line (pricing.css) that draws itself once (motion.js).
        main = main_of(self.html['pricing/index.html'])
        wrap = re.search(r'<div class="tl-wrap" data-line>\s*<span class="tl-line" aria-hidden="true"><i data-line-fill></i></span>\s*<ol class="tl">(.*?)</ol>', main, re.S)
        self.assertIsNotNone(wrap)
        items = re.findall(r'<li>(.*?)</li>', wrap.group(1), re.S)
        self.assertEqual(len(items), 3)
        for number, item in enumerate(items, 1):
            with self.subTest(step=number):
                self.assertIn(f'<span class="tl-n" aria-hidden="true">{number}</span><h3>', item)
        css = (OUT / 'assets/pricing.css').read_text()
        base = base_rules(css)
        line = rules_for(base, '.tl-line')
        self.assertEqual(len(line), 1)
        self.assertIn('height:2px', line[0])
        self.assertIn('left:0;right:0', line[0])
        self.assertIn('transform-origin:left', rules_for(base, '.tl-line i')[0])
        self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', rules_for(base, '.tl')[-1])
        # No card per step: no background, border or shadow on the items themselves.
        for rule in rules_for(base, '.tl li'):
            with self.subTest(rule=rule):
                self.assertNotRegex(rule, r'(?<![-\w])(?:background|border|box-shadow)(?:-[a-z]+)?:')
        # Small screens (860px and below, so every phone): one column, the line turns vertical down the left.
        narrow = media_blocks(css, 'max-width:860px')
        self.assertIn('grid-template-columns:minmax(0,1fr)', rules_for(narrow, '.tl')[0])
        vertical = rules_for(narrow, '.tl-line')[0]
        self.assertIn('width:2px', vertical)
        self.assertIn('top:0;bottom:0', vertical)
        self.assertIn('transform-origin:top', rules_for(narrow, '.tl-line i')[0])

    def test_list_markers_are_drawn_ticks_not_dashes(self):
        # Night Shift Task 18 used small amber squares; Daylight (Task 34) draws a small green tick with two borders. Still
        # no dash glyph as a list marker anywhere.
        for name, selector in (('services.css', '.tick li::before'), ('pricing.css', '.inc-list li::before')):
            with self.subTest(css=name):
                rule = rules_for(base_rules((OUT / 'assets' / name).read_text()), selector)[0]
                for part in ('content:""', 'width:11px', 'height:6px', 'border-left:2px solid var(--ok)',
                             'border-bottom:2px solid var(--ok)', 'transform:rotate(-45deg)'):
                    self.assertIn(part, rule)
        for name in SHEETS:
            css = (OUT / 'assets' / name).read_text()
            with self.subTest(css=name):
                self.assertNotRegex(css, r'content:\s*"[^"]*[—–-][^"]*"')
                self.assertNotIn('\\2014', css)


# Night Shift Task 20 pinned the Work page's Harbourside case study (sha256 of its source <article>) so later tasks could
# not change it by accident. Daylight (Task 34, owner-mandated) rebuilt it from the prototype; this is the new baseline.
# Task 43 (owner-mandated) adds only data-rise to its "Concept project" label, so it rises with the title.
HARBOURSIDE_SHA256 = 'ceef9a57c29b0a23497efbd546e6a4f94255037c7a813121d75848cda3e42fe6'
# The photos /work/ referenced before Task 20; the new art direction reuses them and adds no new downloads.
# Task 24 adds detail-rear (the closing photo, already used on Home); garden-lawn stays inside the Greenline mockup.
WORK_PHOTOS = {'barber-chair', 'barber-cut', 'barber-interior', 'barber-shave', 'detail-buffer', 'detail-dash', 'detail-headlight',
               'detail-mono', 'detail-rear', 'detail-splash', 'detail-wax', 'garden-deck', 'garden-lawn', 'garden-path', 'garden-walk',
               'garden-wall'}
# Daylight (Task 34): the photos the Work prototype uses, all from WORK_PHOTOS.
DAYLIGHT_WORK_PHOTOS = {'barber-chair', 'barber-cut', 'barber-interior', 'detail-headlight', 'detail-mono', 'detail-rear', 'garden-deck',
                        'garden-lawn', 'garden-path', 'garden-walk', 'garden-wall'}


class WorkArtDirectionTests(unittest.TestCase):
    """Night Shift Task 20: three concept projects, three art directions, in markup and CSS only. Restated for Daylight
    (Task 34, docs/design/daylight/prototype/work.html): Harbourside on a full-bleed photo cover, Greenline on a light split
    cover with a serif pull line, Fade & Co led by its screens beside a photo column; each with one device bench (kit.css)."""

    @classmethod
    def setUpClass(cls):
        build()
        root = Path(__file__).resolve().parents[1]
        cls.source = (root / 'pages/work.html').read_text()
        cls.work = main_of((OUT / 'work/index.html').read_text())
        cls.work_css = (OUT / 'assets/work.css').read_text()
        cls.base = base_rules(cls.work_css)
        site = (OUT / 'assets/site.css').read_text()
        cls.tokens = {k: v.strip() for k, v in re.findall(r'(--[\w-]+):([^;]+)', re.search(r':root\{(.*?)\}', site, re.S).group(1))}

    def article(self, slug, html=None):
        return re.search(rf'<article [^>]*id="{slug}"[^>]*>.*?</article>', html or self.source, re.S).group(0)

    def test_harbourside_is_unchanged(self):
        import hashlib
        # Task 47: its three regions are named with the project title too (aria-labelledby="hb-title hb-...").
        frozen = undo_edits(self, self.article('harbourside'), tuple((f'aria-labelledby="hb-title hb-{part}"', f'aria-labelledby="hb-{part}"') for part in ('screens', 'brief', 'does')))
        self.assertEqual(hashlib.sha256(frozen.encode()).hexdigest(), HARBOURSIDE_SHA256)
        self.assertEqual(re.findall(r'<article [^>]*id="([^"]+)"', self.source), ['harbourside', 'greenline', 'fade-co'])

    def test_greenline_is_mirrored_with_a_pull_line(self):
        # Mirrored against Harbourside's dark full-bleed cover: a light split cover, copy left and photo right.
        gl = self.article('greenline')
        self.assertIn('grid-column:1/6', rules_for(self.base, '.gl-cover-copy')[0])
        self.assertIn('grid-column:6/13', rules_for(self.base, '.gl-cover-media')[0])
        # The copy (and its h2) comes before the photo, and the screens follow the cover, then the brief.
        self.assertLess(gl.index('class="gl-cover-copy"'), gl.index('</h2>'))
        self.assertLess(gl.index('</h2>'), gl.index('class="photo gl-cover-media"'))
        self.assertLess(gl.index('</header>'), gl.index('<section class="cs-screens'))
        self.assertLess(gl.index('<section class="cs-screens'), gl.index('class="cs-brief"'))
        brief = re.search(r'<section class="cs-brief"[^>]*>(.*?)</section>', gl, re.S).group(1)
        self.assertEqual(re.findall(r'<p class="([^"]+)"', brief), ['gl-pull'])
        self.assertEqual(len(re.findall(r'<li><b>', gl)), 3)  # the three "what the site does" points stay
        pull = rules_for(self.base, '.gl-pull')
        self.assertEqual(len(pull), 1)
        self.assertIn('clamp(1.5rem,1rem + 1.5vw,2.4rem)', pull[0])
        self.assertIn('Georgia', pull[0])  # the concept's own serif, a system font: no download

    def test_work_benches_stay_inside_a_phone_viewport(self):
        # Replaces Night Shift's Greenline overlap: the Daylight benches never overlap the covers (no negative margins),
        # the kit's container query redraws each bench for a narrow column, and nothing in Work's small-screen rules is
        # wider than a 390px phone.
        self.assertNotRegex(self.work_css, r'margin(?:-top)?:\s*(?:-|calc\([^)]*\* -1)')
        kit = (OUT / 'assets/kit.css').read_text()
        self.assertIn('@container (max-width:700px){', kit)
        self.assertIn('aspect-ratio:100/128', rules_for(''.join(without_blocks(kit, '@container (max-width:700px){')[1]), '.bench-stage')[0])
        for query in ('max-width:1023px', 'max-width:960px', 'max-width:860px', 'max-width:560px'):
            css = media_blocks(self.work_css, query)
            self.assertTrue(css, query)
            for px in re.findall(r'(?<![-\w])(?:min-)?width:(\d+)px', css):
                self.assertLessEqual(int(px), 390)
            for vw in re.findall(r'([\d.]+)vw', css):
                self.assertLessEqual(float(vw), 100)

    def test_greenline_green_is_one_sparing_accessible_accent(self):
        greenline = [(selectors, body) for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', self.work_css, flags=re.S))
                     if '#greenline' in selectors or '.gl-' in selectors or '.cs-gl' in selectors]
        colours = {c.upper() for _, body in greenline for c in re.findall(r'#[0-9A-Fa-f]{6}\b', body)}
        self.assertEqual(colours, {'#1D2A22'})
        self.assertLessEqual(self.work_css.upper().count('#1D2A22'), 3)
        self.assertIn('color:#1D2A22', rules_for(self.base, '.gl-pull')[0])
        for surface in ('--paper', '--warm'):
            self.assertGreaterEqual(contrast('#1D2A22', self.tokens[surface]), 4.5)

    def test_fade_co_leads_with_its_screens_beside_a_photo(self):
        # Replaces Night Shift's dimmed photo band: the screens come straight after the title and facts, with the
        # barbershop photo as a described column beside the bench, then the brief.
        fc = self.article('fade-co')
        self.assertNotIn('cs-cover', fc)
        self.assertNotIn('fc-band', fc)
        order = [CONCEPT_LABEL, '</h2>', '<dl class="cs-facts">', '</header>', '<section class="cs-screens"', '<div class="fc-stage">',
                 '<figure class="photo fc-photo" data-reveal>', '<figure class="bench b-fc" data-bench="fc">', 'class="cs-brief"', 'class="cs-does"']
        positions = [fc.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))
        photo = re.search(r'<figure class="photo fc-photo"[^>]*>(.*?)</figure>', fc, re.S).group(1)
        parser = ImageCollector()
        parser.feed(photo)
        self.assertEqual(len(parser.images), 1)
        attrs, hidden = parser.images[0]
        self.assertFalse(hidden)
        self.assertRegex(attrs['src'], r'^/assets/images/barber-interior-(?:800|1600)\.jpg$')
        self.assertIn('barber-interior-800.jpg 800w', attrs['srcset'])
        self.assertTrue(attrs.get('sizes'))
        self.assertTrue(attrs.get('alt', '').strip())
        self.assertEqual((attrs.get('loading'), attrs.get('decoding')), ('lazy', 'async'))
        self.assertIn('grid-column:1/4', rules_for(self.base, '.fc-photo')[0])
        self.assertIn('grid-column:4/13', rules_for(self.base, '.fc-stage .bench')[0])
        for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', self.work_css):
            if '.fc-' in selectors:
                self.assertNotRegex(body, r'(?<![-\w])filter:')

    def test_fade_co_screens_keep_their_band_padding(self):
        # Resolve padding on the Fade & Co screens section the way the cascade does: of the top-level rules whose selector is
        # a compound of classes the section carries, the highest specificity wins, then the later rule. Daylight (Task 34):
        # the screens keep their bottom padding before the brief.
        section = re.search(r'<section class="([^"]+)" aria-labelledby="fc-title fc-screens">', self.source).group(1).split()
        self.assertEqual(section, ['cs-screens'])
        winner = None
        rules = re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', self.base, flags=re.S))
        for order, (selectors, body) in enumerate(rules):
            for selector in (part.strip() for part in selectors.split(',')):
                classes = re.fullmatch(r'((?:\.[\w-]+)+)', selector)
                if not classes or not re.search(r'(?<![-\w])padding(?:-block|-top|-bottom)?:', body):
                    continue
                names = classes.group(1).lstrip('.').split('.')
                if set(names) <= set(section) and (winner is None or (len(names), order) >= winner[:2]):
                    winner = (len(names), order, selector, body)
        self.assertIsNotNone(winner)
        self.assertEqual(winner[2], '.cs-screens')
        bottom = re.search(r'padding-bottom:(\S+?)(?:;|$)', winner[3]).group(1)
        self.assertNotEqual(bottom, '0')
        self.assertTrue(bottom.startswith('clamp(40px'))

    def test_page_layout_classes_do_not_reuse_mockup_class_names(self):
        # kit.css styles the mockups with unscoped classes (e.g. the homepage mini-site's .hb-*, absolutely positioned
        # inside a screen); a page-level wrapper with the same name would inherit that layout and be pulled out of flow.
        kit = set(re.findall(r'\.([a-z][\w-]*)', re.sub(r'/\*.*?\*/', '', (OUT / 'assets/kit.css').read_text(), flags=re.S)))
        outside_mockups = re.sub(r'<div class="bench-stage".*?</figure>', '', self.source, flags=re.S)
        checked = 0
        for article in re.findall(r'<article\b.*?</article>', outside_mockups, re.S):
            for classes in re.findall(r'class="([^"]+)"', article):
                for name in classes.split():
                    if name.startswith(('fc-', 'gl-', 'hb-')):
                        checked += 1
                        with self.subTest(name=name):
                            self.assertNotIn(name, kit)
        self.assertGreaterEqual(checked, 6)
        self.assertEqual(self.source.count('<div class="wrap cs-body">'), 3)

    def test_work_images_stay_lazy_and_reuse_existing_photos(self):
        used = {u.rsplit('-', 1)[0] for u in re.findall(r'/assets/images/([a-z-]+-(?:800|1600))\.jpg', self.source)}
        self.assertLessEqual(used, WORK_PHOTOS)
        self.assertEqual(used, DAYLIGHT_WORK_PHOTOS)
        # Daylight (Task 34): the opening's largest element is the headline text, so no image claims high priority.
        self.assertEqual(self.source.count('fetchpriority'), 0)
        below = self.source.split('</ul>', 1)[1]  # everything after the project index
        parser = ImageCollector()
        parser.feed(below)
        self.assertTrue(parser.images)
        for attrs, _ in parser.images:
            with self.subTest(img=attrs.get('src')):
                self.assertEqual((attrs.get('loading'), attrs.get('decoding')), ('lazy', 'async'))
                for name in ('width', 'height', 'srcset', 'sizes'):
                    self.assertTrue(attrs.get(name), name)
        # Motion: only the existing hooks, and one device bench per project.
        self.assertTrue(set(re.findall(r'\s(data-[a-z-]+)', self.work)) <= set(MOTION_HOOKS) | set(REEL_HOOKS) | {'data-ph-fade', 'data-src'} | GL_HOOKS)
        for slug in ('harbourside', 'greenline', 'fade-co'):
            self.assertEqual(self.article(slug, self.work).count(' data-bench='), 1)

    def test_work_sections_are_shorter(self):
        self.assertIn('padding-top:clamp(48px,6vw,88px)', rules_for(self.base, '.cs-body')[0])
        self.assertIn('padding-bottom:clamp(24px,3vw,40px)', rules_for(self.base, '.cs-body')[0])
        self.assertEqual(rules_for(self.base, '.cs'), ['padding:clamp(72px,8vw,128px) 0 0'])
        self.assertEqual(rules_for(self.base, '.cs-screens'), ['padding-bottom:clamp(40px,5vw,72px)'])
        # Only Harbourside's cover is tall (at most 720px); the other projects open compactly.
        self.assertIn('min-height:clamp(440px,62vw,720px)', rules_for(self.base, '.cs-cover')[0])
        for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', self.work_css):
            if re.search(r'\.(?:cs|gl|fc|bench|wk)-', selectors):
                for value in re.findall(r'min-height:min\((\d+)s?vh', body) + re.findall(r'min-height:(\d+)s?vh', body):
                    with self.subTest(selectors=selectors.strip()):
                        self.assertLess(int(value), 90)
        self.assertEqual(self.source.count('class="cs-cover"'), 1)
        for needle in ('class="wrap wk-index"', 'id="demo"', 'href="/demo/"', '<section class="close"', 'href="/contact/"'):
            self.assertIn(needle, self.work)


class LiquidGlassTests(unittest.TestCase):
    """Liquid Glass (Task 37, docs/NIGHT_SHIFT_PLAN.md and the strategist brief): the shared glass shell on every page, the
    WebGL hero's module and its fallbacks, the CSP, and the shipped scripts. Behaviour is tested in tests/test_demo_js.py
    (GlassShellScriptTests and the home.js tests)."""
    ROUTES = SiteBuildTests.ROUTES + ['404.html']

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = {route: (OUT / route).read_text() for route in cls.ROUTES}
        cls.scene = (OUT / 'assets/glass-scene.js').read_text()
        cls.glass_css = (OUT / 'assets/glass.css').read_text()

    def test_no_inline_script_import_map_or_style_and_the_csp_is_unchanged(self):
        for route, html in self.html.items():
            with self.subTest(route=route):
                self.assertNotRegex(html, r'<script(?![^>]*\bsrc=)')
                self.assertNotIn('importmap', html)
                self.assertNotIn('type="module"', html)  # the scene is imported by glass-boot.js, never a module tag
                self.assertNotIn(' style="', html)
                self.assertNotIn('<style', html)
        self.assertEqual((OUT / '_headers').read_text(), HEADERS)
        self.assertIn("script-src 'self';", HEADERS)

    def test_scene_imports_only_vendored_three_by_relative_path(self):
        imports = re.findall(r"^import [^;]*? from '([^']+)';", self.scene, re.M)
        # Task 48: the helpers both scenes share live in glass-shapes.js (vendored three only, by the same relative path).
        self.assertEqual(imports, ['./vendor/three/three.module.min.js', './vendor/three/jsm/SVGLoader.js', './vendor/three/jsm/BufferGeometryUtils.js',
                                   './glass-shapes.js'])
        for path in imports:
            self.assertTrue((OUT / 'assets' / path).resolve().is_file(), path)
        shapes = (OUT / 'assets/glass-shapes.js').read_text()
        self.assertEqual(re.findall(r"^import [^;]*? from '([^']+)';", shapes, re.M), ['./vendor/three/three.module.min.js'])
        # The vendored helpers import three by the same relative path, so the browser fetches one copy and needs no map.
        for helper in ('SVGLoader.js', 'BufferGeometryUtils.js'):
            self.assertRegex((OUT / 'assets/vendor/three/jsm' / helper).read_text(), r"\} from '\.\./three\.module\.min\.js';")
        for code in (self.scene, shapes):
            self.assertNotRegex(code, r"from 'three|import\('three")
            for banned in ('http', 'fetch(', 'XMLHttpRequest', 'innerHTML', 'eval(', 'localStorage', '?poster', 'preserveDrawingBuffer'):
                self.assertNotIn(banned, code)
        self.assertEqual(self.scene, (ROOT / 'assets/glass-scene.js').read_text())  # modules ship as written
        self.assertEqual(shapes, (ROOT / 'assets/glass-shapes.js').read_text())
        # Budgets: the scene file 40 KB at most, and everything the boot imports (three, its two helpers, the shared shapes
        # and the scene) 900 KB at most; none of it is on any page's first load (no page names it in a tag).
        self.assertLessEqual(len(self.scene.encode()), 40 * 1024)
        total = sum(path.stat().st_size for path in module_graph(OUT / 'assets/glass-scene.js'))
        self.assertLessEqual(total, 900 * 1024)
        for route, html in self.html.items():
            with self.subTest(route=route):
                self.assertNotIn('vendor/three', html)

    def test_scene_runs_only_in_view_visible_and_unpaused_and_caps_its_resolution(self):
        run = self.scene.split('function setRunning(want) {', 1)[1].split('\n  }', 1)[0]
        for needle in ('inView', '!G.paused', '!document.hidden', "host.classList.contains('is-live')",
                       'renderer.setAnimationLoop(loop)', 'renderer.setAnimationLoop(null)', 'v.pause()'):
            self.assertIn(needle, run)
        self.assertIn('new IntersectionObserver(', self.scene)
        self.assertIn("document.addEventListener('visibilitychange', () => setRunning(true));", self.scene)
        self.assertIn('(G.pauseFns = G.pauseFns || []).push(() => setRunning(true));', self.scene)
        self.assertIn("const DPR_CAP = window.matchMedia('(max-width: 760px)').matches ? 1.5 : 1.75;", self.scene)
        self.assertIn('renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, DPR_CAP));', self.scene)
        # Yaw stays within about 32 degrees, so the glass name never reads backwards.
        yaw = float(re.search(r'const YAW = ([\d.]+);', self.scene).group(1))
        self.assertLessEqual(yaw, 0.56)
        self.assertIn('-YAW, YAW)', self.scene)
        self.assertIn('clock.getDelta(), 1 / 20', self.scene)  # frame-rate independent, never a huge jump after a pause

    def test_glass_shell_is_on_every_page_with_opaque_fallbacks(self):
        atmos = '<div class="atmos" aria-hidden="true"><i></i><i></i><i></i><i></i></div>'
        defs = '<svg class="lg-defs" width="0" height="0" aria-hidden="true" focusable="false"><defs data-lg-defs></defs></svg>'
        for route, html in self.html.items():
            with self.subTest(route=route):
                self.assertEqual(html.count('<link rel="stylesheet" href="/assets/glass.css">'), 1)
                self.assertLess(html.index('/assets/site.css'), html.index('/assets/glass.css'))
                self.assertIn('Skip to main content</a>' + atmos + '<header class="site-header">', html)
                self.assertEqual(html.count(defs), 1 if route in MOTION_ROUTES else 0)
                self.assertEqual(html.count('/assets/vendor/lenis/'), 1 if route in MOTION_ROUTES else 0)  # none on Contact, Demo, 404
        css = self.glass_css
        self.assertIn('backdrop-filter:var(--lg-filter,blur(18px) saturate(1.8))', css)
        self.assertIn('@supports not ((-webkit-backdrop-filter:blur(1px)) or (backdrop-filter:blur(1px))){', css)
        reduced = media_blocks(css, 'prefers-reduced-transparency:reduce')
        self.assertIn('.lg,.site-header .nav,.button.outline{background:#FBFAF7;-webkit-backdrop-filter:none;backdrop-filter:none}', reduced)
        self.assertIn('.lenis.lenis-smooth{scroll-behavior:auto!important}', css)
        self.assertEqual(rules_for(base_rules(css), '.site-header.is-hidden'), ['transform:translateY(calc(-100% - 16px))'])
        # Glass text stays readable: ink on frosted white, white on dark glass.
        self.assertGreaterEqual(contrast('#0E0E0D', '#E8E4DC'), 4.5)  # ink over the darkest the light glass gets over the fields
        self.assertIn('color:#fff', rules_for(base_rules(css), '.lg-dark')[0])
        js = (OUT / 'assets/glass.js').read_text()
        self.assertIn("root.classList.add('lg-refract');", js)
        self.assertLess(js.index("brands.some(b => /Chromium/.test(b.brand))"), js.index("root.classList.add('lg-refract');"))
        # Task 48: under reduced motion GSAP's ticker is put to sleep and glass.js stops before Lenis.
        self.assertLess(js.index('if (!motionOK) { if (ticker) ticker.sleep(); return; }'), js.index('new win.Lenis('))
        for banned in MOTION_SCRIPT_BANS:
            self.assertNotIn(banned, js)

    def test_shipped_scripts_are_the_sources_without_comments(self):
        # The build strips whole-line comments and indentation from first-party classic scripts (not from modules, not from
        # scripts with template literals). Every shipped script must still parse, and keep every line of code in order.
        import shutil
        import subprocess
        from scripts.build_site import strip_js, STRIP_SKIP
        node = shutil.which('node')
        self.assertEqual(STRIP_SKIP, {'glass-scene.js', 'glass-page.js', 'glass-shapes.js'})  # the ES modules (Task 48)
        for path in sorted((ROOT / 'assets').glob('*.js')):
            shipped = (OUT / 'assets' / path.name).read_text()
            source = path.read_text()
            with self.subTest(script=path.name):
                if path.name in STRIP_SKIP or '`' in source:
                    self.assertEqual(shipped, source)
                else:
                    self.assertEqual(shipped, strip_js(source))
                    # Every shipped line is a source line (trimmed), in the source's order: nothing rewritten or reordered.
                    lines = iter(line.strip() for line in source.splitlines())
                    for line in shipped.splitlines():
                        self.assertTrue(any(line == candidate or candidate.endswith('*/ ' + line) for candidate in lines), line)
                if node:
                    module = ['--input-type=module'] if path.name in STRIP_SKIP else []
                    result = subprocess.run(['node', *module, '--check'], input=shipped, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(strip_js('a();\n  // note\n  /* block\n   still */ b();\n/* one */\n  c(); // kept\n'), 'a();\nb();\nc(); // kept\n')


class GlassPolishTests(unittest.TestCase):
    """Task 41: the liquid-glass showreel's files, the Contact glass C's own space, the Work queue mock and the ambient loop
    behind the inner closing panels. (Pause motion on every moving page: DaylightInnerPageTests and tests/test_demo_js.py.)"""

    @classmethod
    def setUpClass(cls):
        build()
        cls.contact = main_of((OUT / 'contact/index.html').read_text())
        cls.work = main_of((OUT / 'work/index.html').read_text())
        cls.pages_css = base_rules((OUT / 'assets/pages.css').read_text())
        cls.full_pages_css = (OUT / 'assets/pages.css').read_text()

    def test_the_old_showreel_is_gone_from_the_build(self):
        self.assertEqual(list((OUT / 'assets/video').glob('cendavo-showreel*')), [])
        for path in OUT.rglob('*'):
            if path.is_file() and path.suffix in ('.html', '.js', '.css', '.txt', '.xml'):
                with self.subTest(path=str(path.relative_to(OUT))):
                    self.assertNotIn('cendavo-showreel', path.read_text(errors='ignore'))
        home = main_of((OUT / 'index.html').read_text())
        self.assertIn('Showreel · concept projects, fictional businesses', home)
        desc = re.search(r'<p id="reel-desc"[^>]*>([^<]+)</p>', home).group(1)
        self.assertIn('white glass', desc)
        self.assertTrue(desc.endswith('No sound.'))

    def test_contact_glass_c_has_its_own_box_outside_the_form(self):
        host = re.search(r'<div class="pg-gl" data-gl data-gl-kind="mark" [^>]*></div>', self.contact).group(0)
        self.assertIn('data-gl-anchor=".ct-gl-spot"', host)
        self.assertEqual(self.contact.count('<div class="ct-gl-spot" aria-hidden="true"></div>'), 1)
        form_start = self.contact.index('<div class="ct-form">')
        self.assertLess(self.contact.index('ct-gl-spot"'), form_start)  # before the form panel, never inside it
        # A fixed size (no layout shift when the scene arrives), at the top-right; gone where WebGL never runs (<=760px).
        spot = rules_for(self.pages_css, '.ct-gl-spot')[0]
        for needle in ('width:216px', 'height:216px', 'grid-row:1', 'justify-self:end'):  # Task 42: a little larger
            self.assertIn(needle, spot)
        self.assertIn('.ct-gl-spot{display:none}', self.full_pages_css.split('@media(max-width:760px){', 1)[1].split('}}', 1)[0] + '}')
        # The form panel sits above the scene layer (.pg-gl is z-index 0).
        form = rules_for(self.pages_css, '.ct-form')[0]
        self.assertIn('position:relative', form)
        self.assertIn('z-index:2', form)
        self.assertIn('z-index:0', rules_for(self.pages_css, '.pg-gl')[0])
        # The scene centres the C on that box: no negative corner offsets any more.
        module = (OUT / 'assets/glass-page.js').read_text()
        self.assertIn('mark: [0, 0, 1.15]', module)  # centred; Task 42: scaled up a little
        self.assertNotIn('mark: [-0.5, -0.5', module)

    def test_work_queue_tile_is_a_static_illustrative_mock(self):
        tile = re.search(r'<span class="wk-tile-img wk-demo-mini" aria-hidden="true">(.*?)</span><span class="wk-tile-name">Request queue</span>', self.work, re.S)
        self.assertIsNotNone(tile)
        groups = re.findall(r'<i><em>([A-Za-z-]+) <s>(\d)</s></em>((?:<b>[^<]+</b>)+)</i>', tile.group(1))
        self.assertEqual([(name, int(n), re.findall(r'<b>([^<]+)</b>', rows)) for name, n, rows in groups], [
            ('New', 2, ['Website redesign', 'Booking question']), ('Follow-up', 1, ['Quote sent']), ('Done', 1, ['Site visit booked'])])
        self.assertNotIn('<b></b>', tile.group(1))
        self.assertNotIn('data-', tile.group(0).split('aria-hidden="true">', 1)[1])  # static: no script hooks

    def test_ambient_loop_layer_sits_over_the_photo_and_skips_phones(self):
        for route in ('work/index.html', 'services/index.html', 'pricing/index.html', 'about/index.html'):
            with self.subTest(route=route):
                main = main_of((OUT / route).read_text())
                media = main.index('<div class="close-media" aria-hidden="true" data-parallax>')
                loop = main.index('<div class="close-loop" aria-hidden="true"><video class="close-video" data-loop="wide"')
                self.assertLess(media, loop)  # the photo stays underneath as the fallback
                self.assertEqual(main.count('glass-ambient-1600.mp4'), 1)
                self.assertNotRegex(main, r'[\s<](?:src|poster)="/assets/glass/glass-ambient')  # no video bytes or still on first load
        layer = rules_for(self.pages_css, '.close-loop')[0]
        self.assertIn('pointer-events:none', layer)
        self.assertIn('filter:blur(6px)', rules_for(self.pages_css, '.close-video')[0])
        phones = self.full_pages_css.split('@media(max-width:640px){', 1)[1]
        self.assertIn('.close-loop{display:none}', phones.split('\n}\n', 1)[0])
        self.assertNotIn('close-loop', (OUT / 'contact/index.html').read_text())


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

    def test_what_we_do_has_three_still_illustrations(self):
        # Daylight (Task 33) replaces the sticky photo panel with one illustration per service, each aria-hidden above its
        # heading: a finished concept page (New website), a dated card beside a modern one (Redesign) and an example care
        # log (Care plan). Every tag says it is a concept or an illustration.
        self.assertNotIn('svc-panel', self.home)
        rows = self.services.split('<li class="svc-row">')[1:]
        self.assertEqual(len(rows), 3)
        photos = []
        for row, (slug, name, tag) in zip(rows, (('new', 'New website', 'Finished page, concept'), ('redesign', 'Redesign', 'Dated to modern, concept'),
                                                 ('care', 'Care plan', 'Illustration of a care plan log'))):
            with self.subTest(service=name):
                self.assertTrue(row.startswith('<div class="vig" aria-hidden="true">'))
                vig, text = row.split('</span></div><h3>', 1)
                self.assertTrue(vig.endswith(f'<span class="vig-tag">{tag}'))
                self.assertRegex(text, rf'^<a href="/services/#{slug}">{name}</a></h3><p>[^<]+</p></li>')
                parser = ImageCollector()
                parser.feed(vig + '</span></div>')
                for attrs, hidden in parser.images:
                    self.assertTrue(hidden)
                    self.assertEqual((attrs.get('alt'), attrs.get('loading'), attrs.get('decoding')), ('', 'lazy', 'async'))
                    self.assertTrue(attrs.get('width') and attrs.get('height'))
                    photos.append(re.search(r'/images/([a-z-]+)-800\.jpg$', attrs['src']).group(1))
        self.assertEqual(photos, ['garden-path', 'barber-cut'])
        self.assertIn('<b>Site care log</b><span>Example</span>', rows[2])
        self.assertNotIn('garden-walk', self.home)

    def test_what_we_do_illustrations_are_still_and_hold_their_shape(self):
        base = base_rules(self.home_css)
        self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', rules_for(base, '.svc-list')[0])
        vig = rules_for(base, '.vig')[0]
        for needle in ('aspect-ratio:4/3.3', 'overflow:hidden', 'container-type:inline-size'):
            self.assertIn(needle, vig)  # the frame reserves its space; the drawing scales with it (cqw)
        self.assertEqual(rules_for(media_blocks(self.home_css, 'max-width:860px'), '.svc-list'), ['grid-template-columns:1fr;gap:44px'])
        # Nothing animates them: no guarded rule and no homepage script touches them.
        guarded = ''.join(without_blocks(self.home_css, MOTION_GUARD)[1])
        self.assertNotRegex(guarded, r'\.(?:vig|vb-|vr-|log)')
        for name in ('home.js', 'motion.js'):
            self.assertNotRegex((OUT / 'assets' / name).read_text(), r"'\.(?:vig|vb-|vr-|log|svc-row)")

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

    def test_demo_app_follows_the_hero_without_covering_it(self):
        # Night Shift Task 21 pulled the demo panel up over the hero on large, tall screens. Daylight (Task 34, prototype):
        # the app sits on its own warm band under the hero, so nothing can cover the heading, intro or notice.
        for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', self.pages_css + (OUT / 'assets/site.css').read_text()):
            if '.demo' in selectors:
                with self.subTest(rule=selectors.strip()[:60]):
                    self.assertNotRegex(body, r'margin(?:-top)?:-')
        self.assertNotIn('-18vh', self.pages_css)
        self.assertNotIn('-18vh', (OUT / 'assets/site.css').read_text())
        self.assertNotIn('min-height:700px', self.pages_css)
        demo = main_of((OUT / 'demo/index.html').read_text())
        self.assertIn('<section class="pg-hero demo-hero" aria-labelledby="demo-title"><div class="wrap demo-hero-grid">\n<div class="demo-hero-copy">', demo)
        self.assertIn('<section class="sec-tight band-warm demo-app" aria-label="Demonstration app"><div class="wrap demo-shell">', demo)
        self.assertLess(demo.index('demo-hero'), demo.index('demo-app'))
        # The 404 page shares .pg-hero but not the demo layout.
        self.assertNotIn('demo-hero', (OUT / '404.html').read_text())

    def test_closing_photos_and_removed_photos(self):
        # Daylight (Task 34): About closes on the headlight and Services on the garden path, as in the prototype.
        for route, photo in (('about/index.html', 'detail-headlight'), ('services/index.html', 'garden-path')):
            with self.subTest(route=route):
                band = re.search(r'<div class="close-media"[^>]*>(.*?)</div>', main_of((OUT / route).read_text()), re.S).group(1)
                self.assertIn(f'/assets/images/{photo}-1600.jpg', band)
        services = (OUT / 'services/index.html').read_text()
        self.assertNotIn('barber-interior', services)
        self.assertIn('object-fit:cover', rules_for(base_rules(self.pages_css), '.close-media img')[0])
        # The headlight closes About and appears nowhere else on that page.
        about = main_of((OUT / 'about/index.html').read_text())
        close = re.search(r'<section class="close".*?</section>', about, re.S).group(0)
        self.assertNotIn('detail-headlight', about.replace(close, ''))


class ServicesCareBandTests(unittest.TestCase):
    """Night Shift Task 24: the Care plan set in type, with no photo; garden-lawn closes no page. Restated for Daylight
    (Task 34, prototype services.html): the Care plan is a paper section with the monthly list on a white card, a phone
    playing a concept site's loop (Task 34 spec: the Care plan phone plays loop-hb-phone) and the care-plan clip."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = {route: (OUT / route).read_text() for route in SiteBuildTests.ROUTES + ['404.html']}
        cls.services = main_of(cls.html['services/index.html'])
        cls.care = re.search(r'<section class="sec" id="care" aria-labelledby="care-title">(.*?)</section>', cls.services, re.S)
        cls.services_css = (OUT / 'assets/services.css').read_text()
        cls.site_css = (OUT / 'assets/site.css').read_text()

    def test_care_band_keeps_its_content_and_has_no_photo(self):
        self.assertIsNotNone(self.care)
        care = self.care.group(1)
        self.assertIn('<h2 id="care-title" class="h2" data-rise>Care plan</h2>', care)
        self.assertIn('A website isn’t finished at launch.', care)
        self.assertRegex(care, r'<h3>Every month</h3>')
        self.assertLess(care.index('care-title'), care.index('Every month'))
        month = re.search(r'<div class="month" data-month>(.*?)<figure', care, re.S).group(1)
        items = re.findall(r'<li><span class="box" aria-hidden="true">.*?</span><b>([^<]+)</b><span>([^<]+)</span></li>', month, re.S)
        self.assertEqual([name for name, _ in items], ['Updates', 'Backups', 'Form check', 'Small changes'])
        facts = re.search(r'<dl class="care-facts" data-stagger>(.*?)</dl>', care, re.S).group(1)
        self.assertEqual(re.findall(r'<div><dt>([^<]+)</dt><dd>[^<]+</dd></div>', facts),
                         ['Who it’s for', 'When it starts', 'What we need from you'])
        # Two moving figures, both video and neither a photo: the phone loop (described group, aria-hidden video) and the
        # care-plan clip in its phone frame (Night Shift Task 29, owner).
        loop = re.search(r'<figure class="month-dev" role="img" aria-label="([^"]+)">(.*?)</figure>', care, re.S)
        self.assertIsNotNone(loop)
        self.assertIn('fictional business', loop.group(1))
        self.assertIn('<source data-src="/assets/video/loop-hb-phone.mp4" type="video/mp4">', loop.group(2))
        clip = re.search(r'<div class="clip" data-reel>\s*<figure class="sp">.*?</figure>', care, re.S)
        self.assertIsNotNone(clip)
        self.assertIn('cendavo-social-care-plan-540.mp4', clip.group(0))
        rest = care.replace(clip.group(0), '').replace(loop.group(0), '')
        for banned in ('<img', '<picture', '<figure', 'data-reveal', 'garden-wall'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, rest)
        self.assertNotIn('garden-wall', self.services)
        self.assertNotIn('.care-photo', self.services_css)
        # No price for the care plan: it is still unconfirmed.
        self.assertNotRegex(visible_text(care), r'A?\$\s*\d')
        # The chapter link still lands on the section.
        self.assertIn('<a href="#care">', self.services)

    def test_care_band_type_and_columns(self):
        base = base_rules(self.services_css)
        self.assertIn('grid-template-columns:repeat(12,minmax(0,1fr))', rules_for(base, '.care-grid')[0])
        self.assertIn('grid-column:1/8', rules_for(base, '.care-a')[0])
        self.assertIn('grid-column:9/13', rules_for(base, '.care-b')[0])
        # The section is a .wrap grid; the white card holds the list beside the phone.
        self.assertRegex(self.care.group(1), r'^<div class="wrap care-grid">')
        name = rules_for(base, '.month b')
        self.assertEqual(len(name), 1)
        self.assertIn('var(--font-display)', name[0])
        self.assertIn('grid-template-columns:minmax(0,1fr) 112px', rules_for(base, '.month-in')[0])
        self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', ''.join(rules_for(base, '.care-facts')))
        narrow = media_blocks(self.services_css, 'max-width:960px')
        for selector in ('.care-a', '.care-b'):
            with self.subTest(selector=selector):
                self.assertIn('grid-column:1/-1', rules_for(narrow, selector)[0])
        self.assertIn('grid-template-columns:minmax(0,1fr)', rules_for(narrow, '.care-facts')[0])
        self.assertIn('grid-template-columns:minmax(0,1fr) 84px', rules_for(media_blocks(self.services_css, 'max-width:640px'), '.month-in')[0])

    def test_care_band_text_contrast(self):
        tokens = dict(re.findall(r'--([a-z0-9-]+):(#[0-9A-Fa-f]{6})', self.site_css))
        base = base_rules(self.services_css)
        # The card is white (#fff) and the section paper: ink headings, ink-2 descriptions and facts, the amber-ink tag
        # on its warm pill.
        self.assertIn('background:#fff', rules_for(base, '.month')[0])
        self.assertIn('color:var(--ink-2)', rules_for(base, '.month li>span:last-child')[0])
        self.assertIn('color:var(--ink-2)', rules_for(base, '.care-facts dd')[0])
        for name, colour, background in (('headings and item names', tokens['ink'], tokens['paper']),
                                         ('item descriptions and facts', tokens['ink-2'], tokens['paper']),
                                         ('tag', tokens['amber-ink'], tokens['warm'])):
            with self.subTest(text=name):
                self.assertGreaterEqual(contrast(colour, background), 4.5)

    def test_garden_lawn_only_on_home_and_in_the_greenline_mockup(self):
        # Night Shift Task 28: the trades row (with its Landscapers photo) moved from the homepage to /about/, so About now
        # shows garden-lawn once, inside that row; the homepage keeps it on the Greenline card.
        for route, html in self.html.items():
            main = main_of(html)
            with self.subTest(route=route):
                # It closes no page.
                for band in re.findall(r'<div class="(?:band|close)-media"[^>]*>(.*?)</div>', main, re.S):
                    self.assertNotIn('garden-lawn', band)
                if route == 'work/index.html':
                    # The made-up client's site-visit card on the Greenline bench keeps it; nothing else on Work uses it.
                    mockup = re.search(r'<div class="ui-thumbs">.*?</div>', main, re.S).group(0)
                    self.assertIn('/assets/images/garden-lawn-800.jpg', mockup)
                    self.assertIn('<figure class="bench b-gl"', main.split(mockup, 1)[0].rsplit('<article', 1)[1])
                    main = main.replace(mockup, '')
                if route == 'about/index.html':
                    row = re.search(r'<ul class="wrap who-row" data-stagger>.*?</ul>', main, re.S).group(0)
                    self.assertEqual(row.count('/assets/images/garden-lawn-800.jpg"'), 1)
                    main = main.replace(row, '')
                if route == 'index.html':
                    card = re.search(r'<article class="teaser-card" aria-labelledby="t2-title">.*?</article>', main, re.S).group(0)
                    self.assertIn('/assets/images/garden-lawn-800.jpg', card)
                    self.assertEqual(main.replace(card, '').count('garden-lawn'), 0)
                else:
                    self.assertNotIn('garden-lawn', main)
        about = self.html['about/index.html']
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
        # Every page gets the same hold (Daylight, Task 33: no intro variant any more).
        self.assertNotIn('data-intro', self.boot)
        # Both scripts let go: motion.js also when GSAP is missing, home.js once its hero states are applied.
        self.assertIn("const release = () => root.classList.remove('ph-wait');", self.motion)
        self.assertIn('if (!gsap || !ScrollTrigger) { release(); return; }', self.motion)
        # home.js also releases the hold when GSAP is missing (motion.js leaves the homepage hero to home.js).
        self.assertIn("const release = () => root.classList.remove('ph-wait');", self.home_js)
        self.assertIn('if (!gsap || !ScrollTrigger) { release(); return; }', self.home_js)

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
        # Daylight (Task 34): each inner hero holds its headline lines, its rising copy and its un-masking frames, exactly
        # the elements motion.js opens with fromTo (data-ph-fade, data-ph-media), and nothing else. Task 48: the copy is
        # only held 18px low, never at opacity 0, so it paints with the headline (LCP).
        guarded = self.guarded(self.pages_css)
        held = {'.ph-wait :is(.wk-hero,.sv-hero,.pr-hero,.ab-hero) .ln>span': 'transform:translateY(108%)',
                '.ph-wait :is(.wk-hero .pg-sub,.wk-clip,.sv-hero .pg-sub,.chap-nav,.pr-hero .pg-sub,.pr-hero .pg-actions)': 'transform:translateY(18px)',
                '.ph-wait :is(.sv-hero-media,.pr-hero .quote,.ab-photos .photo)': 'clip-path:inset(0 0 0 100%)'}
        for selector, body in held.items():
            with self.subTest(selector=selector):
                self.assertIn(selector + '{' + body + '}', guarded)
        bare = re.sub(r'/\*.*?\*/', '', guarded, flags=re.S)
        self.assertEqual(sorted(sel.strip() for sel, _ in re.findall(r'([^{}]+)\{([^{}]*)\}', bare) if '.ph-wait' in sel), sorted(held))
        # Every element the opening animates is covered by those selectors, per hero.
        fades = {'wk-hero': {'pg-sub', 'wk-clip'}, 'sv-hero': {'pg-sub', 'chap-nav'}, 'pr-hero': {'pg-sub', 'pg-actions'}, 'ab-hero': set()}
        media = {'wk-hero': set(), 'sv-hero': {'sv-hero-media'}, 'pr-hero': {'quote'}, 'ab-hero': {'photo'}}
        for route in self.INNER:
            main = main_of((OUT / route).read_text())
            head = re.search(r'<section class="pg-hero ([a-z-]+)" data-ph [^>]*>(.*?)</section>', main, re.S)
            with self.subTest(route=route):
                self.assertIsNotNone(head)
                hero = head.group(1)
                self.assertIn(hero, fades)
                found_fades = re.findall(r'class="([^"]+)"(?: data-[a-z-]+)* data-ph-fade', head.group(2))
                found_media = re.findall(r'class="([^"]+)"(?: data-[a-z-]+)* data-ph-media', head.group(2))
                self.assertEqual(len(found_fades), head.group(2).count('data-ph-fade'))
                self.assertEqual(len(found_media), head.group(2).count('data-ph-media'))
                for classes in found_fades:
                    self.assertTrue(set(classes.split()) & fades[hero], classes)
                for classes in found_media:
                    self.assertTrue(set(classes.split()) & media[hero], classes)
                if hero == 'ab-hero':
                    self.assertIn('<div class="ab-photos" aria-hidden="true">', head.group(2))
        # The homepage hero is held the same way and opened with fromTo, never from. Liquid Glass (Task 37): the headline
        # lines, the copy and the glass cards are held, and nothing else (the WebGL host and its still are never hidden).
        # Task 48: the copy and buttons only sit 18px low, never at opacity 0 (LCP).
        home = self.guarded(self.home_css)
        held = ['.ph-wait .hero-h .ln>span{transform:translateY(108%)}',
                '.ph-wait :is(.hero-sub,.hero .actions){transform:translateY(18px)}', '.ph-wait .hero-cards{opacity:0}']
        for rule in held:
            with self.subTest(rule=rule):
                self.assertIn(rule, home)
        bare = re.sub(r'/\*.*?\*/', '', home, flags=re.S)
        self.assertEqual([sel.strip() + '{' + body + '}' for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', bare) if '.ph-wait' in sel], held)
        hero = self.home_js.split('const heroTimeline', 1)[1].split('const heroExit', 1)[0]
        self.assertNotIn('.from(', hero)
        for target in ("$$('.hero-h .ln > span')", "$$('[data-hero-fade]')", "$('.hero-cards')"):
            self.assertIn(target, hero)
        self.assertIn('tl.fromTo(deck, { opacity: 0 }, { opacity: 1', hero)
        self.assertIn('class="hero-sub" data-hero-fade', self.home)
        self.assertIn('class="actions" data-hero-fade', self.home)

    def test_homepage_has_no_pin_and_moved_sections_keep_shared_hooks(self):
        # Night Shift Task 28: the pinned projects and their bone release layer are gone from home.js and home.css. The
        # sections that moved to /services/ and /about/ use only hooks motion.js already handles (rise, reveal, parallax).
        for gone in ('pin:', 'PIN_', 'work-exit', 'proj-mask', 'is-pinned'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.home_js)
                self.assertNotIn(gone, self.home_css)
        # Daylight (Task 34): How it works draws its line (data-line) and the trades row arrives in order (data-stagger);
        # still only hooks motion.js handles.
        shared = {'data-rise', 'data-reveal', 'data-parallax', 'data-stagger', 'data-line', 'data-line-fill'}
        for route, title in (('services/index.html', 'process-title'), ('about/index.html', 'who-title')):
            with self.subTest(route=route):
                main = main_of((OUT / route).read_text())
                block = re.search(rf'<section class="[^"]*" aria-labelledby="{title}">.*?</section>', main, re.S).group(0)
                self.assertTrue(set(re.findall(r'\s(data-[a-z-]+)', block)) <= shared)
                self.assertIn('data-rise', block)
        scenes = (OUT / 'assets/scenes.js').read_text()  # the inner pages' scroll scenes (Task 34)
        for hook in ('[data-rise]', '[data-reveal]', '[data-parallax]', '[data-stagger]'):
            self.assertIn(f"$$('{hook}')", self.motion)
        self.assertIn("$$('[data-line]')", scenes)
        self.assertIn("$$('[data-line-fill]', wrap)", scenes)

    def test_services_rows_follow_scroll_wipe_and_dim_accessibly(self):
        large = self.motion.split("mm.add(MOTION + ' and (min-width: 1081px)'", 1)[1].split('mm.add(', 1)[0]
        self.assertIn("ScrollTrigger.create({ trigger: row, start: 'top center', end: 'bottom center'", large)
        self.assertIn("row.addEventListener('mouseenter'", self.motion)
        self.assertIn("row.addEventListener('focusin'", self.motion)
        self.assertIn("{ clipPath: 'inset(100% 0 0 0)' }, { clipPath: 'inset(0% 0 0 0)'", self.motion)
        # Inactive headings: bone at DIM opacity over ink must still clear 3:1 (large bold text).
        dim = float(re.search(r'const DIM = ([\d.]+);', self.motion).group(1))
        tokens = dict(re.findall(r'(--[\w-]+):([^;]+)', re.search(r':root\{(.*?)\}', self.css, re.S).group(1)))
        bone, ink = tokens['--bone'].strip(), tokens['--ink'].strip()
        mix = '#' + ''.join(f'{round(dim * int(bone[i:i + 2], 16) + (1 - dim) * int(ink[i:i + 2], 16)):02X}' for i in (1, 3, 5))
        self.assertGreaterEqual(contrast(mix, ink), 3)
        self.assertLess(dim, 1)
        # Daylight (Task 33) replaced the homepage's photo panel and .svc rows with still illustrations, so this motion.js
        # code (covered in tests/test_demo_js.py) has nothing to act on today: no page carries .svc rows or the panel, and
        # home.css no longer styles them.
        for route in SiteBuildTests.ROUTES:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertNotIn('class="svc"', html)
                self.assertNotIn('svc-panel', html)
        self.assertNotRegex(self.home_css, r'\.svc(?![\w-])|svc-panel|is-wipe')


class ShowreelMarkupTests(unittest.TestCase):
    """Night Shift Task 28 (owner): one self-hosted, silent showreel directly after the homepage hero. Playback behaviour is
    tested in tests/test_demo_js.py; these tests cover the markup, files, styles and security headers."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.home = main_of((OUT / 'index.html').read_text())
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.section = re.search(r'<section class="reel band-warm"[^>]*>(.*?)</section>', cls.home, re.S)

    def test_one_silent_video_with_poster_size_and_no_autoplay(self):
        self.assertIsNotNone(self.section)
        self.assertLess(self.home.index('<section class="hero"'), self.home.index('<section class="reel '))
        self.assertLess(self.home.index('<section class="reel '), self.home.index('<section class="work"'))
        self.assertEqual(self.section.group(1).count('<video'), 1)  # the hero's two device loops are tested in DaylightTests
        for route in SiteBuildTests.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertNotIn('<iframe', html)
                self.assertNotIn('<audio', html)
                self.assertEqual(html.count('<video'), VIDEOS_PER_ROUTE.get(route, 0))  # Task 29: clips on Services and Work
        tag = re.search(r'<video ([^>]*)>', self.section.group(1)).group(1)
        attrs = dict(re.findall(r'([a-z-]+)(?:="([^"]*)")?', tag))
        for flag in ('muted', 'loop', 'playsinline', 'controls'):
            with self.subTest(flag=flag):
                self.assertIn(flag, attrs)
        self.assertEqual(attrs['preload'], 'none')
        self.assertEqual(attrs['poster'], '/assets/glass/glass-reel-poster.jpg')  # Task 41: the liquid-glass reel
        self.assertEqual((attrs['width'], attrs['height']), ('1600', '900'))
        self.assertNotIn('autoplay', tag)
        self.assertNotIn('src', attrs)  # the file comes from <source>
        sources = re.findall(r'<source ([^>]*)>', self.section.group(1))
        self.assertEqual(sources, ['src="/assets/glass/glass-reel-1600.mp4" type="video/mp4"'])
        # The phone cut is named in the markup for home.js; every referenced file ships with the site.
        self.assertEqual(attrs['data-narrow-src'], '/assets/glass/glass-reel-vertical-720.mp4')
        self.assertEqual(attrs['data-narrow-poster'], '/assets/glass/glass-reel-vertical-poster.jpg')
        for path in (attrs['poster'], attrs['data-narrow-src'], attrs['data-narrow-poster'], '/assets/glass/glass-reel-1600.mp4'):
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
        self.assertIn("const NARROW = '(max-width: 640px)';", (OUT / 'assets/reel.js').read_text())  # same breakpoint as the CSS
        video = rules_for(base, '.reel-video')[0]
        for needle in ('width:100%', 'height:100%', 'object-fit:cover'):
            self.assertIn(needle, video)
        toggle = rules_for(base, '.reel-toggle')[0]
        self.assertGreaterEqual(int(re.search(r'min-height:(\d+)px', toggle).group(1)), 44)
        # Task 44: a light glass chip, near-opaque behind the label, so it reads whatever frame is playing: even over a
        # pure black frame, ink on the chip's white keeps far more than 4.5:1.
        alpha = float(re.search(r'background:rgba\(255,255,255,(\.\d+)\)', toggle).group(1))
        self.assertGreaterEqual(alpha, 0.8)
        self.assertIn('color:var(--ink)', toggle)
        worst = round(255 * alpha)
        self.assertGreaterEqual(contrast('#0E0E0D', '#{0:02X}{0:02X}{0:02X}'.format(worst)), 7)
        focus = rules_for(base, '.reel-toggle:focus-visible')
        self.assertEqual(len(focus), 1)
        self.assertIn('outline:2px solid var(--ink)', focus[0])
        self.assertIn('box-shadow:0 0 0 6px #fff', focus[0])  # a white ring outside the ink outline, on any frame

    def test_headers_still_allow_self_hosted_media_only(self):
        headers = (OUT / '_headers').read_text()
        self.assertEqual(headers, HEADERS)
        self.assertIn("default-src 'self'", headers)
        self.assertNotIn('media-src', headers)


class ViewTransitionAndDetailTests(unittest.TestCase):
    """Night Shift Task 29: cross-document page transitions, the cursor ring, card tilt, push-in and light sweep. Behaviour
    is tested in tests/test_demo_js.py; these tests cover the CSS, markup and script constants."""
    ROUTES = SiteBuildTests.ROUTES + ['404.html']
    SHEETS = SHEETS  # every sheet the site ships (Daylight, Task 34, adds the inner pages' own sheets)
    EASE = 'cubic-bezier(.7,0,.2,1)'

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = {name: (OUT / 'assets' / name).read_text() for name in cls.SHEETS}
        cls.html = {route: (OUT / route).read_text() for route in cls.ROUTES}
        cls.details = (OUT / 'assets/details.js').read_text()

    def test_page_transitions_are_opt_in_quick_and_off_with_reduced_motion(self):
        site = self.css['site.css']
        unguarded, guarded = without_blocks(site, MOTION_GUARD)
        guarded = ''.join(guarded)
        # Opted in only inside the no-preference guard, so with reduced motion the browser navigates without a transition.
        self.assertIn('@view-transition{navigation:auto}', guarded)
        self.assertNotIn('@view-transition', unguarded)
        self.assertIn(f'::view-transition-old(root){{animation:vt-out 450ms {self.EASE} both}}', guarded)
        self.assertIn(f'::view-transition-new(root){{animation:vt-in 450ms {self.EASE} both}}', guarded)
        self.assertIn(f'::view-transition-group(page-title){{animation-duration:450ms;animation-timing-function:{self.EASE}}}', guarded)
        # The wipe animates compositor-friendly properties only.
        keyframes = re.findall(r'@keyframes (vt-[\w-]+)\{((?:[^{}]*\{[^{}]*\})*)\}', site)
        self.assertEqual(sorted(name for name, _ in keyframes), ['vt-in', 'vt-out'])
        for name, body in keyframes:
            with self.subTest(keyframes=name):
                for prop in re.findall(r'([a-z-]+):', body):
                    self.assertIn(prop, ('transform', 'clip-path'))
        # Belt and braces: if a transition does start with reduced motion on, nothing in it animates.
        reduce = re.findall(r'@media\(prefers-reduced-motion:reduce\)\{(.*?)\}\}', site, re.S)
        self.assertEqual(reduce, ['::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none!important'])
        # No other stylesheet animates anything, and no CSS animation exists outside the page transition.
        for name in self.SHEETS:
            with self.subTest(css=name):
                rest = without_view_transitions(self.css[name])
                self.assertNotIn('animation', rest)
                self.assertNotIn('@keyframes', rest)
                if name != 'site.css':
                    self.assertNotIn('view-transition', self.css[name])

    def test_transition_names_live_in_css_and_name_one_element_per_page(self):
        named = {}
        for name in self.SHEETS:
            for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', self.css[name]):
                for value in re.findall(r'view-transition-name:([\w-]+)', body):
                    named[value] = selectors.strip()
        # The header's glass pill stays put; each page's one H1 morphs into the next page's. Task 48: the name is on the pill,
        # never on .site-header (a named ancestor stops the pill's backdrop-filter blurring the page under it).
        self.assertEqual(named, {'site-header': '.site-header .nav', 'page-title': 'main h1'})
        for route, html in self.html.items():
            with self.subTest(route=route):
                self.assertNotIn('view-transition', html)  # never inline (style-src 'self')
                self.assertEqual(html.count('class="site-header"'), 1)
                self.assertEqual(len(re.findall(r'<h1[\s>]', main_of(html))), 1)
                self.assertEqual(len(re.findall(r'<h1[\s>]', html)), 1)

    def test_no_script_tweens_a_variable_font_axis(self):
        # The strategist dropped the hero's font-stretch snap (it would re-lay out the headline every frame): no script
        # animates or sets a font axis.
        for path in sorted((OUT / 'assets').glob('*.js')):
            js = path.read_text()
            with self.subTest(script=path.name):
                for banned in ('fontStretch', 'fontVariationSettings', 'font-stretch', 'font-variation', 'fontWeight'):
                    self.assertNotIn(banned, js)
                # Daylight (Task 33): nor the prototype's width variables, which re-laid out the text every frame.
                self.assertNotRegex(js, r"['\"]--s?w['\"]")

    def test_cursor_ring_never_hides_the_native_cursor_or_takes_clicks(self):
        for name in self.SHEETS:
            with self.subTest(css=name):
                self.assertNotRegex(self.css[name], r'cursor:\s*none')
        unguarded, guarded = without_blocks(self.css['site.css'], MOTION_GUARD)
        self.assertNotIn('cursor-ring', unguarded)
        ring = rules_for(''.join(guarded), '.cursor-ring')
        self.assertEqual(len(ring), 1)
        for needle in ('position:fixed', 'pointer-events:none', 'width:0', 'height:0'):
            self.assertIn(needle, ring[0])
        self.assertIn('pointer-events:none', rules_for(''.join(guarded), '.cursor-ring span')[0])
        for name in ('home.css', 'pages.css', 'kit.css'):
            self.assertNotIn('cursor-ring', self.css[name])
        # Created by details.js only (aria-hidden), never in the markup.
        self.assertIn("ring.setAttribute('aria-hidden', 'true')", self.details)
        for route, html in self.html.items():
            self.assertNotIn('cursor-ring', html)

    def test_card_tilt_is_small_fine_pointer_only_and_focus_gets_no_tilt(self):
        tilt = re.search(r'const MAX_TILT = (\d+(?:\.\d+)?);', self.details)
        self.assertIsNotNone(tilt)
        self.assertLessEqual(float(tilt.group(1)), 6)
        self.assertIn('const PERSPECTIVE = 900;', self.details)
        self.assertIn('Math.max(-MAX_TILT, Math.min(MAX_TILT, value))', self.details)
        fine = self.details.split("mm.add(MOTION + ' and (hover: hover) and (pointer: fine)'", 1)
        self.assertEqual(len(fine), 2)
        self.assertNotIn('rotation', fine[0])  # every tilt sits inside the fine-pointer, motion-allowed branch
        self.assertIn("$$('.teaser-card, .wk-tile')", fine[1])
        self.assertNotIn('focus', fine[1])  # keyboard focus gets the CSS push-in and sweep, never the tilt
        # Push-in: guarded, transform-only, within 200 ms, the same on hover and keyboard focus. Daylight (Task 33) gave the
        # homepage cards a small push-in; Daylight (Task 34) gives the /work/ tiles the same (the light sweep is gone), and
        # no page loads details.js, so no card tilts anywhere.
        for name, needle in (('home.css', '.motion .teaser-card:is(:hover,:focus-within) .teaser-img img{transform:scale(1.03)}'),
                             ('home.css', '.motion .teaser-img img{transition:transform var(--dur-1) var(--ease-out)}'),
                             ('work.css', '.wk-tile-img img{transition:transform var(--dur-1) var(--ease-out)}'),
                             ('work.css', '.wk-tile a:is(:hover,:focus-visible) .wk-tile-img img{transform:scale(1.02)}')):
            with self.subTest(css=name, rule=needle[:50]):
                unguarded, guarded = without_blocks(self.css[name], MOTION_GUARD)
                self.assertIn(needle, ''.join(guarded))
                self.assertNotIn(needle, unguarded)
        for name in self.SHEETS:
            with self.subTest(css=name):
                self.assertNotIn('wk-tile-img::after', self.css[name])  # no sweep
                for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', self.css[name]):
                    if ':hover' in selectors or ':focus' in selectors:
                        self.assertNotIn('rotate(', body.replace('rotate(45deg)', ''))  # only the arrow glyphs' fixed 45deg
        self.assertNotIn('teaser', self.css['site.css'])
        for route in self.ROUTES:
            self.assertNotIn('/assets/details.js', self.html[route])  # so no tilt on any card
        # Liquid Glass (Task 37): the homepage cards fan in from depth (home.js) and preview their loop through reel.js; the
        # owner asked for a tilt on them, so home.js tilts them within the same limits as details.js did: at most 6 degrees,
        # fine pointers with motion allowed only, and never on keyboard focus.
        home = main_of(self.html['index.html'])
        self.assertEqual(len(re.findall(r'<figure class="teaser-img" data-hover-src="/assets/video/loop-(?:hb|gl|fc)-desktop\.mp4">', home)), 3)
        js = (OUT / 'assets/home.js').read_text()
        self.assertIn('const MAX_TILT = 6;', js)
        self.assertIn('Math.max(-MAX_TILT, Math.min(MAX_TILT, value))', js)
        tilt = js.split('const tilt = () =>', 1)[1].split('const demoSweep', 1)[0]
        self.assertNotIn('focus', tilt)
        self.assertIn("mm.add(MOTION + ' and (hover: hover) and (pointer: fine)', tilt);", js)
        self.assertEqual(js.count('tilt)'), 1)  # the tilt runs only from that branch


class SocialClipTests(unittest.TestCase):
    """Night Shift Task 29 (owner): the three silent social videos, each in the mockup kit's phone frame, with a caption, a
    visible text description and the shared Pause/Play button. Playback is tested in tests/test_demo_js.py."""
    CLIPS = {'services/index.html': [('before-after', 'Play redesign video'), ('care-plan', 'Play care plan video')],
             'work/index.html': [('3-signs', 'Play three signs video')]}

    @classmethod
    def setUpClass(cls):
        build()
        cls.main = {route: main_of((OUT / route).read_text()) for route in SiteBuildTests.ROUTES + ['404.html']}

    def clips(self, route):
        # Work's intro clip also fades in with the hero opening (data-ph-fade).
        return re.findall(r'<div class="clip[^"]*" data-reel(?: data-ph-fade)?>(.*?<div class="clip-side">.*?</div>)\s*</div>', self.main[route], re.S)

    def test_each_clip_is_a_silent_framed_video_with_native_controls_until_js(self):
        # Daylight (Task 34): the clips sit in the kit's light-chrome phone frame (.sp) with the shared pill button (.vt).
        for route, expected in self.CLIPS.items():
            clips = self.clips(route)
            self.assertEqual(len(clips), len(expected), route)
            for clip, (slug, button) in zip(clips, expected):
                with self.subTest(route=route, clip=slug):
                    self.assertEqual(clip.count('<video'), 1)
                    self.assertRegex(clip, r'^\s*<figure class="sp"><div class="sp-frame"><div class="sp-scr"><video class="sp-video" ')
                    tag = re.search(r'<video ([^>]*)>', clip).group(1)
                    attrs = dict(re.findall(r'([a-z-]+)(?:="([^"]*)")?', tag))
                    for flag in ('muted', 'loop', 'playsinline', 'controls'):
                        self.assertIn(flag, attrs)
                    self.assertNotIn('autoplay', tag)
                    self.assertNotIn('src', attrs)
                    self.assertEqual(attrs['preload'], 'none')
                    self.assertEqual((attrs['width'], attrs['height']), ('540', '960'))
                    self.assertEqual(attrs['poster'], f'/assets/video/cendavo-social-{slug}-poster-540.jpg')
                    source = f'/assets/video/cendavo-social-{slug}-540.mp4'
                    self.assertEqual(re.findall(r'<source ([^>]*)>', clip), [f'src="{source}" type="video/mp4"'])
                    for path in (attrs['poster'], source):
                        self.assertTrue((OUT / path.lstrip('/')).is_file(), path)
                    # A visible one-sentence alternative (WCAG 1.2.1), linked to the video.
                    desc = re.search(rf'<p class="clip-desc" id="{re.escape(attrs["aria-describedby"])}">([^<]+)</p>', clip)
                    self.assertIsNotNone(desc)
                    self.assertGreaterEqual(len(desc.group(1)), 60)
                    self.assertTrue(desc.group(1).endswith('No sound.'))
                    self.assertTrue(attrs['aria-label'].endswith('video'))
                    self.assertIn(f'<p class="clip-cap">{CLIP_CAPTION}</p>', clip)
                    self.assertIn(f'<button class="vt" type="button" data-reel-toggle hidden>{button}</button>', clip)
                    self.assertLess(clip.index('</video>'), clip.index('<button'))
        ids = re.findall(r'aria-describedby="(clip-[\w-]+)"', ''.join(self.main.values()))
        self.assertEqual(len(ids), len(set(ids)))

    def test_clips_sit_where_the_owner_asked(self):
        services = self.main['services/index.html']
        redesign = re.search(r'<section class="sec band-warm" id="redesign".*?</section>', services, re.S).group(0)
        chap_a = re.search(r'<div class="chap-a">.*?<div class="chap-b">', redesign, re.S).group(0)
        self.assertIn('cendavo-social-before-after-540.mp4', chap_a)
        self.assertLess(chap_a.index('re-title'), chap_a.index('<video'))
        care = re.search(r'<section class="sec" id="care".*?</section>', services, re.S).group(0)
        self.assertIn('cendavo-social-care-plan-540.mp4', care)
        self.assertLess(care.index('care-title'), care.index('Every month'))
        self.assertLess(care.index('Every month'), care.index('cendavo-social-care-plan-540.mp4'))
        work = self.main['work/index.html']
        intro = re.search(r'<section class="pg-hero wk-hero".*?<ul class="wrap wk-index"', work, re.S).group(0)
        self.assertIn('cendavo-social-3-signs-540.mp4', intro)
        self.assertLess(intro.index('class="pg-sub"'), intro.index('<video'))
        for route, html in self.main.items():
            with self.subTest(route=route):
                self.assertEqual(html.count('<video'), VIDEOS_PER_ROUTE.get(route, 0))

    def test_clip_styles_never_crop_and_keep_a_visible_focus(self):
        kit = base_rules((OUT / 'assets/kit.css').read_text())
        video = rules_for(kit, '.sp-video')[0]
        for needle in ('width:100%', 'height:100%', 'object-fit:contain'):
            self.assertIn(needle, video)
        self.assertIn('aspect-ratio:9/16', rules_for(kit, '.sp-scr')[0])  # the frame keeps the clip's shape
        toggle = rules_for(kit, '.vt')[0]
        self.assertGreaterEqual(int(re.search(r'min-height:(\d+)px', toggle).group(1)), 44)
        self.assertIn('background:var(--paper)', toggle)
        self.assertIn('color:var(--ink)', toggle)
        # The button sits on paper or the warm band, where the default ink focus ring shows (no override in kit.css).
        site = (OUT / 'assets/site.css').read_text()
        self.assertIn(':focus-visible{outline:2px solid var(--ink);outline-offset:3px}', site)
        self.assertFalse(rules_for(kit, '.vt:focus-visible'))
        tokens = dict(re.findall(r'--([a-z0-9-]+):(#[0-9A-Fa-f]{6})', site))
        for background in ('paper', 'warm'):
            self.assertGreaterEqual(contrast(tokens['ink'], tokens[background]), 3)

    def test_middle_dots_only_in_the_approved_labels(self):
        # The concept label, the showreel caption and the clip caption are the only places a middle dot may appear on the
        # marketing pages. (The demo app's counter line, "0 new · 0 to follow up", is interface text, not a label.)
        for route, main in self.main.items():
            if route == 'demo/index.html':
                continue
            with self.subTest(route=route):
                text = main.replace(CONCEPT_LABEL, '').replace(SHOWREEL_CAPTION, '').replace(CLIP_CAPTION, '')
                self.assertNotIn('·', text)
                # One caption per social clip (Daylight: the device loops and the About film carry none).
                self.assertEqual(main.count(CLIP_CAPTION), len(self.CLIPS.get(route, [])))


# Daylight (Task 33): the hero loops were re-encoded by the supervisor (two-pass H.264, phone cut at 520 px wide) and now
# fit the plan's 500 KB target, which is enforced.
HERO_LOOP_TARGET = 500 * 1024
HERO_LOOPS = ('loop-hb-desktop.mp4', 'loop-hb-phone.mp4')
FIRST_LOAD_BUDGET = 650 * 1024


class DaylightTests(unittest.TestCase):
    """Daylight Task 33 (docs/NIGHT_SHIFT_PLAN.md, strategist brief 33a): the light design system and the new homepage hero
    with the real device loops, the Pause motion button, showreel chapters, page weight and the inner pages' interim surface.
    Playback and choreography behaviour is tested in tests/test_demo_js.py."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = (OUT / 'index.html').read_text()
        cls.home = main_of(cls.html)
        cls.hero = re.search(r'<section class="hero".*?</section>', cls.home, re.S).group(0)
        cls.css = {name: (OUT / 'assets' / name).read_text() for name in ('site.css', 'home.css', 'pages.css', 'kit.css')}

    def test_hero_is_a_described_glass_scene_over_a_still_that_never_goes_away(self):
        # Liquid Glass (Task 37): the hero has no <video> and no <img>. Its host is a described role="img" whose background is
        # the still render (CSS, so it is there without JS and before anything loads); glass-scene.js only ever adds an
        # aria-hidden canvas on top, and a failed import, start or a lost GPU context leaves the still showing.
        self.assertNotIn('<video', self.hero)
        self.assertNotIn('<img', self.hero)
        self.assertEqual(self.home.count('<video'), 5)  # the showreel, two footage loops and two glass phones
        host = re.search(r'<div class="hero-gl" data-gl role="img" aria-label="([^"]{80,})"></div>', self.hero)
        self.assertIsNotNone(host)
        self.assertEqual(self.html.count('data-gl'), 1)
        base = base_rules(self.css['home.css'])
        rule = rules_for(base, '.hero-gl')[0]
        self.assertIn('url("/assets/glass/hero-glass-poster.jpg")', rule)
        self.assertIn('/cover', rule)
        mobile = rules_for(media_blocks(self.css['home.css'], 'max-width:760px'), '.hero-gl')[0]
        self.assertIn('url("/assets/glass/hero-glass-poster-m.jpg")', mobile)
        for name, size in (('hero-glass-poster.jpg', (2160, 1350)), ('hero-glass-poster-m.jpg', (780, 1688))):
            with self.subTest(poster=name):
                self.assertEqual(jpeg_size(OUT / 'assets/glass' / name), size)
        # The still is never hidden by CSS; only a canvas that is not live is.
        self.assertEqual(rules_for(base, '.hero-gl:not(.is-live) .hero-canvas'), ['display:none'])
        for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', self.css['home.css'], flags=re.S)):
            if '.hero-gl' in selectors and 'canvas' not in selectors:
                self.assertNotRegex(body, r'display:none|opacity:0(?![.\d])|visibility:hidden', selectors)
        scene = (ROOT / 'assets/glass-scene.js').read_text()
        boot = (ROOT / 'assets/glass-boot.js').read_text()
        self.assertIn("canvas.setAttribute('aria-hidden', 'true')", scene)
        self.assertIn("canvas.addEventListener('webglcontextlost', () => { host.classList.remove('is-live');", scene)
        # Task 48: a failed import or start also releases the tested WebGL context (lose only calls loseContext).
        catch = re.search(r"\.catch\(\(\) => (\{[^}]*\})\);", boot)
        self.assertEqual(catch.group(1), "{ host.classList.remove('is-live'); lose(gl); }")  # nothing removes the still
        self.assertIn("const lose = gl => gl.context.getExtension?.('WEBGL_lose_context')?.loseContext();", boot)
        for code in (scene, boot):
            self.assertNotIn('.remove()', code)
            self.assertNotIn('backgroundImage', code)
            self.assertNotIn('innerHTML', code)

    def test_homepage_loops_exist_load_late_and_cards_preview_through_reel_js(self):
        # Liquid Glass (Task 37) reverses strategist brief 33a item 7 by owner direction: the concept cards preview their
        # gl/fc/hb loops (through reel.js, created only on hover or when centred) and the WebGL screens play the gl and hb
        # loops. Every loop and poster the page, its stylesheet or the scene names must exist; home.js still starts no video.
        page = self.html + self.css['home.css'] + (OUT / 'assets/glass-scene.js').read_text()
        names = set(re.findall(r'/assets/(?:video|glass)/[a-z0-9-]+\.(?:mp4|jpg|avif|svg)', page))
        names |= {f'/assets/video/loop-{n}-desktop{s}' for n in ('gl', 'hb') for s in ('.mp4', '-poster-800.jpg')}
        self.assertGreaterEqual(len(names), 12)
        for name in sorted(names):
            with self.subTest(file=name):
                self.assertTrue((OUT / name.lstrip('/')).is_file())
        cards = re.findall(r'<article class="teaser-card".*?</article>', self.home, re.S)
        self.assertEqual(len(cards), 3)
        for card, loop in zip(cards, ('hb', 'gl', 'fc')):
            self.assertNotIn('<video', card)
            self.assertIn(f'data-hover-src="/assets/video/loop-{loop}-desktop.mp4"', card)
        home_js = (OUT / 'assets/home.js').read_text()
        for needle in ('loop-', 'video', 'mouseenter', 'pointerenter'):
            self.assertNotIn(needle, home_js)  # home.js starts no video; reel.js is the only controller on the page
        # The scene's two screen videos get their file only when the scene first runs (in view, tab visible, not paused).
        scene = (OUT / 'assets/glass-scene.js').read_text()
        self.assertIn("v.preload = 'none';", scene)
        self.assertIn('if (!v.src) { v.src = v.dataset.src; v.load(); }', scene)
        self.assertNotIn("preload = 'auto'", scene)

    def test_every_homepage_video_is_silent_lazy_and_hidden_from_assistive_tech(self):
        parser = VideoCollector()
        parser.feed(self.home)
        self.assertEqual(len(parser.videos), 5)
        for attrs, sources, ancestors in parser.videos:
            with self.subTest(video=attrs.get('class') or attrs.get('data-poster')):
                for flag in ('muted', 'loop', 'playsinline'):
                    self.assertIn(flag, attrs)
                self.assertEqual(attrs.get('preload'), 'none')
                self.assertNotIn('autoplay', attrs)
                self.assertNotIn('src', attrs)
                self.assertTrue(attrs.get('width') and attrs.get('height'))
                self.assertEqual(len(sources), 1)
                if attrs.get('id') == 'reel-video':
                    continue  # the showreel: ShowreelMarkupTests
                # A silent loop: no file before reel.js plays it, no controls, its still fetched only near the screen
                # (data-poster), and hidden from assistive technology with its decorative container.
                self.assertIn('data-loop', attrs)
                self.assertNotIn('controls', attrs)
                self.assertNotIn('poster', attrs)
                self.assertEqual(attrs.get('aria-hidden'), 'true')
                self.assertTrue(any(a.get('aria-hidden') == 'true' for a in ancestors))
                self.assertEqual(list(sources[0]), ['data-src', 'type'])
                for url in (attrs['data-poster'], sources[0]['data-src']):
                    self.assertRegex(url, r'^/assets/(?:video|glass)/[a-z0-9-]+\.(?:jpg|mp4)$')
                    self.assertTrue((OUT / url.lstrip('/')).is_file(), url)
        reel = (OUT / 'assets/reel.js').read_text()
        self.assertIn("video.setAttribute('poster', video.dataset.poster);", reel)
        self.assertIn("{ rootMargin: '50% 0px' }", reel)

    def test_hero_loop_files_are_within_target(self):
        for name in HERO_LOOPS:
            with self.subTest(video=name):
                self.assertLessEqual((OUT / 'assets/video' / name).stat().st_size, HERO_LOOP_TARGET)

    def test_first_load_stays_within_650_kb(self):
        # Everything a first visit on a desktop downloads before any video or the WebGL modules: the HTML, linked CSS,
        # every script (GSAP and Lenis included), the fonts, eager photos (none), every image the stylesheets use outside
        # media queries (the desktop hero still and the marquee's type mask) and the showreel's poster. The loops' stills
        # load near the screen (data-poster), the loops after load and idle, and three.js only on capable desktops.
        total = len(self.html.encode())
        sheets = re.findall(r'<link rel="stylesheet" href="(/assets/[^"]+)">', self.html)
        for href in sheets:
            total += (OUT / href.lstrip('/')).stat().st_size
        for src in re.findall(r'<script src="(/assets/[^"]+)"', self.html):
            total += (OUT / src.lstrip('/')).stat().st_size
        for font in set(re.findall(r'url\("(/assets/fonts/[^"]+\.woff2)"\)', self.css['site.css'])):
            total += (OUT / font.lstrip('/')).stat().st_size
        parser = ImageCollector()
        parser.feed(self.home)
        eager = [attrs['src'] for attrs, _ in parser.images if attrs.get('loading') != 'lazy']
        self.assertEqual(eager, [])
        images = set(re.findall(r'\sposter="([^"]+)"', self.home))
        for href in sheets:
            images |= set(re.findall(r'url\("(/assets/(?!fonts/)[^"]+)"\)', base_rules((OUT / href.lstrip('/')).read_text())))
        self.assertIn('/assets/glass/hero-glass-poster.jpg', images)
        for image in images:
            total += (OUT / image.lstrip('/')).stat().st_size
        self.assertLessEqual(total, FIRST_LOAD_BUDGET, f'first load is {total} bytes')

    def test_pause_motion_is_a_real_toggle_button_hidden_without_js(self):
        # Task 41: the homepage's button is the site-wide one. Task 46: it sits in the header pill, after the logo.
        button = '<button class="motion-btn" type="button" data-motion-toggle aria-pressed="false" hidden>Pause motion</button>'
        self.assertEqual(self.html.count(button), 1)
        self.assertEqual(self.html.count('data-motion-toggle'), 1)
        self.assertIn('CENDAVO</a>' + button + '<button class="menu"', self.html)
        glass = base_rules((OUT / 'assets/glass.css').read_text())
        rule = rules_for(glass, '.motion-btn')[0]
        self.assertGreaterEqual(int(re.search(r'min-height:(\d+)px', rule).group(1)), 44)
        self.assertTrue(rules_for(glass, '.motion-btn[aria-pressed="true"]::before'))  # pressed looks different
        self.assertNotIn('.motion-btn', self.css['home.css'])  # styled once, in the shared glass.css

    def test_showreel_chapters_are_buttons_revealed_by_script(self):
        section = re.search(r'<section class="reel band-warm".*?</section>', self.home, re.S).group(0)
        chapters = re.search(r'<ol class="chapters" data-chapters="reel-video" aria-label="Showreel chapters" hidden>(.*?)</ol>', section, re.S)
        self.assertIsNotNone(chapters)
        self.assertIn('id="reel-video"', section)
        items = re.findall(r'<li><button type="button" data-t="([\d.]+)"><span class="ch-t">(\d:\d\d)</span>([^<]+)</button></li>', chapters.group(1))
        # Task 41: the liquid-glass reel (22.2 s) has six chapters, at the owner's times, in order.
        self.assertEqual([(float(t), title) for t, _, title in items], [
            (0, 'Cendavo'), (1.5, 'Your work is excellent'), (6, 'Three concept sites'), (12, 'Book from a phone'),
            (15.4, 'Before / after'), (17.7, 'New websites, redesigns, care plans')])
        times = [float(t) for t, _, _ in items]
        self.assertEqual(times, sorted(times))
        self.assertLess(times[-1], 22.2)  # the reel is 22.2 seconds long
        self.assertEqual(len({title for _, _, title in items}), len(items))  # distinct names, as 0:00 and 0:01 sound alike
        for t, label, _ in items:
            self.assertEqual(label, f'0:{int(float(t)):02d}')

    def test_every_homepage_image_and_video_reserves_its_space(self):
        parser = ImageCollector()
        parser.feed(self.home)
        for attrs, _ in parser.images:
            self.assertTrue(attrs.get('width') and attrs.get('height'), attrs.get('src'))
        for tag in re.findall(r'<video ([^>]*)>', self.home):
            self.assertRegex(tag, r'width="\d+" height="\d+"')
        base = base_rules(self.css['home.css'])
        for selector in ('.reel-frame', '.teaser-img', '.vig', '.gphone', '.mq-photos img'):
            with self.subTest(selector=selector):
                self.assertIn('aspect-ratio:', rules_for(base, selector)[0])
        # Liquid Glass (Task 37): the hero is one screen tall before anything loads (the still and canvas fill it).
        self.assertIn('height:100svh', rules_for(base, '.hero-pin')[0])
        self.assertIn('position:absolute;inset:0', rules_for(base, '.hero-gl')[0])

    def test_no_inline_styles_and_the_comparison_uses_set_property(self):
        for route in SiteBuildTests.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertNotIn(' style="', html)
                self.assertNotIn('<style', html)
        self.assertIn("figure.style.setProperty('--pos'", (OUT / 'assets/home.js').read_text())
        self.assertIn('.compare{--pos:50%', self.css['home.css'])

    def test_home_motion_uses_the_two_curves_and_no_banned_motion(self):
        js = (OUT / 'assets/home.js').read_text()
        self.assertIn('const OUT = bezier(0.2, 0.8, 0.2, 1);', js)
        self.assertIn('const IO = bezier(0.7, 0, 0.2, 1);', js)
        for banned in ('elastic', 'bounce', 'back.', 'power', 'expo', 'sine', 'pin:', "addEventListener('scroll'", 'repeat:', 'yoyo'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, js)
        self.assertEqual(set(re.findall(r"ease: '([^']+)'", js)), {'none'})  # named eases only for the scrubbed layers
        self.assertEqual(js.count('scrub:'), 1)  # one scrub definition, used by the two hero layers
        for name, css in self.css.items():
            with self.subTest(css=name):
                self.assertNotRegex(without_view_transitions(css), r'@keyframes|animation')

    def test_inner_pages_keep_light_text_on_ink_and_the_homepage_never_puts_it_on_paper(self):
        # Daylight (Task 34): the inner pages' <main> is paper too. On every page, Night Shift's bone and stone text appears
        # only on an ink surface: in a rule that sets an ink background itself, or inside an element that does (the demo's
        # side panel). The inner pages' one ink band (.close) uses white.
        pages = self.css['pages.css']
        self.assertNotIn('main{background:var(--ink)', pages)
        self.assertNotRegex(pages, r'(?<![-\w])main\{')
        for route in SiteBuildTests.ROUTES + ['404.html']:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertEqual(html.count('<link rel="stylesheet" href="/assets/pages.css">'), 0 if route == 'index.html' else 1)
        classes = set()
        for route in SiteBuildTests.ROUTES + ['404.html']:
            for attribute in re.findall(r'class="([^"]*)"', (OUT / route).read_text()):
                classes.update(attribute.split())
        sheets = {name: re.sub(r'/\*.*?\*/', '', base_rules((OUT / 'assets' / name).read_text()), flags=re.S) for name in SHEETS}
        ink = r'background:var\(--ink(?:-2)?\)'
        surfaces = {sel.strip()[1:] for css in sheets.values() for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css)
                    if re.fullmatch(r'\.[\w-]+', sel.strip()) and re.search(ink, body)}
        self.assertIn('demo-side', surfaces)
        self.assertIn('close', surfaces)
        self.assertIn('color:#fff', rules_for(base_rules(pages), '.close')[0])
        checked = 0
        for name, css in sheets.items():
            for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
                if not re.search(r'(?<![-\w])color:var\(--(?:bone|stone)\)', body):
                    continue
                used = [c for c in classes if re.search(rf'\.{re.escape(c)}(?![\w-])', selectors)]
                if used:
                    checked += 1
                    with self.subTest(css=name, rule=selectors.strip()[:60]):
                        inside = all(re.match(r'\.([\w-]+)', part.strip()) and re.match(r'\.([\w-]+)', part.strip()).group(1) in surfaces
                                     for part in selectors.split(','))
                        self.assertTrue(re.search(ink, body) or inside, selectors)
        self.assertGreaterEqual(checked, 2)  # the showreel's Pause/Play button and the demo's side panel text
        for rule in ('.site-header', '.footer p', '.footer-bottom', '.brand'):
            with self.subTest(chrome=rule):
                self.assertNotRegex(''.join(rules_for(base_rules(self.css['site.css']), rule)), r'var\(--(?:bone|stone)\)')


# Daylight (Task 34): the enquiry form, with every class attribute removed, is byte-identical to the form before Task 34
# (pages/contact.html at 2a91fbb, from <form data-enquiry ...> to the status line): only classes and wrappers may change.
CONTACT_FORM_SHA256 = 'bc95f8284ba6d12d27966bb5e5b2a7206d54325654f2452f2c0947cd3e5fe29d'
# Task 47 (owner-mandated) changed exactly these strings inside the frozen form: the submit button ships disabled until
# enquiry.js attaches its handler, the honeypot got a name browsers do not autofill, and the privacy note says "may" (the
# email copy is only sent when the alert is configured). The freeze hashes still cover everything else: each test undoes
# exactly these edits (each must appear once) and compares with the earlier baseline.
TASK47_FORM_EDITS = (
    (' type="submit" disabled>Send enquiry</button>', ' type="submit">Send enquiry</button>'),
    ('<label for="enquiry-hp">Leave this field empty</label><input id="enquiry-hp" name="hp_xq" ',
     '<label for="enquiry-company-url">Leave this field empty</label><input id="enquiry-company-url" name="company_url" '),
    (' used by Cendavo and may also be emailed to Cendavo ', ' used by Cendavo and also emailed to Cendavo '),
)


def undo_edits(test, text, edits):
    for new, old in edits:
        test.assertEqual(text.count(new), 1, new)
        text = text.replace(new, old)
    return text
# The demonstration app's markup, from its .demo-shell wrapper to the end of pages/demo.html, unchanged since before Task 34.
DEMO_APP_SHA256 = 'edf5d1891ad9896aa8b44f0a53635fdfee7d6bc965ffb5d2a1b81bcffa44525e'
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}


class VideoCollector(HTMLParser):
    """Every <video>'s attributes, its <source> attributes and the attributes of its open ancestors."""

    def __init__(self):
        super().__init__()
        self.stack, self.videos = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'video':
            self.videos.append((attrs, [], [a for _, a in self.stack]))
        elif tag == 'source' and self.stack and self.stack[-1][0] == 'video':
            self.videos[-1][1].append(attrs)
        if tag not in VOID_TAGS:
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


class DaylightInnerPageTests(unittest.TestCase):
    """Daylight Task 34 (docs/NIGHT_SHIFT_PLAN.md, Tasks 34 and 35): every inner page in the Daylight shell, the enquiry form
    and the demonstration app unchanged, videos built in under one set of rules, and the per-page first-load budget."""
    ROUTES = SiteBuildTests.ROUTES + ['404.html']

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = {route: (OUT / route).read_text() for route in cls.ROUTES}
        cls.pages = Path(__file__).resolve().parents[1] / 'pages'

    def test_contact_form_is_unchanged_apart_from_classes(self):
        import hashlib
        source = (self.pages / 'contact.html').read_text()
        self.assertEqual(source.count('<form'), 1)
        form = re.search(r'<form data-enquiry.*?</form><p data-enquiry-status class="status" role="status"></p>', source, re.S)
        self.assertIsNotNone(form)
        frozen = undo_edits(self, form.group(0), TASK47_FORM_EDITS)
        self.assertEqual(hashlib.sha256(re.sub(r' class="[^"]*"', '', frozen).encode()).hexdigest(), CONTACT_FORM_SHA256)
        # The built page carries the same form (the build only fills in the contact address).
        self.assertEqual(main_of(self.html['contact/index.html']).count('<form data-enquiry class="form" method="post" novalidate>'), 1)
        self.assertNotIn('data-ph', self.html['contact/index.html'])

    def test_demo_app_markup_and_every_hook_demo_js_uses_are_kept(self):
        import hashlib
        source = (self.pages / 'demo.html').read_text()
        app = source[source.index('<div class="wrap demo-shell">'):].rstrip()
        self.assertEqual(hashlib.sha256(app.encode()).hexdigest(), DEMO_APP_SHA256)
        script = (OUT / 'assets/demo.js').read_text()
        created = set(re.findall(r"\.id='([\w-]+)'", script))  # nodes demo.js makes itself
        used = set(re.findall(r"\$\('#([\w-]+)", script)) - created
        self.assertGreaterEqual(len(used), 10)
        main = main_of(self.html['demo/index.html'])
        for name in sorted(used):
            with self.subTest(id=name):
                self.assertEqual(main.count(f'id="{name}"'), 1)
        self.assertIn('<input name="date" type="date" required>', main)
        self.assertNotIn('data-ph', self.html['demo/index.html'])

    def test_every_page_has_one_h1_visible_without_javascript(self):
        for route in self.ROUTES:
            html = self.html[route]
            main = main_of(html)
            with self.subTest(route=route):
                h1s = re.findall(r'<h1 ([^>]*)>(.*?)</h1>', main, re.S)
                self.assertEqual(len(h1s), 1)
                attrs, text = h1s[0]
                self.assertNotIn('hidden', attrs)
                self.assertNotIn('aria-hidden', attrs)
                self.assertNotIn('style=', attrs)
                self.assertGreaterEqual(len(visible_text(text).strip()), 10)
                if route != 'index.html':
                    self.assertIn('class="pk', attrs)
                    self.assertEqual(html.count('<link rel="stylesheet" href="/assets/pages.css">'), 1)
                    self.assertIn('<meta name="color-scheme" content="light">', html)
        # No stylesheet hides a headline outside the guarded .ph-wait hold.
        for name in SHEETS:
            unguarded = without_blocks(without_view_transitions((OUT / 'assets' / name).read_text()), MOTION_GUARD)[0]
            for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', unguarded, flags=re.S)):
                if re.search(r'(?:\bh1\b|\.pk\b|\.ln\b|\.hero-h\b)', selectors):
                    with self.subTest(css=name, rule=selectors.strip()[:60]):
                        self.assertNotRegex(body, r'opacity:0(?![.\d])|visibility:hidden|display:none|clip-path|translateY\(1')

    def test_every_page_first_load_stays_within_650_kb(self):
        # Everything a first visit downloads before any video: the HTML, its CSS and scripts (GSAP included), the fonts,
        # the eager photos (counted at their largest AVIF candidate, the worst case) and every video poster on the page.
        fonts = set(re.findall(r'url\("(/assets/fonts/[^"]+\.woff2)"\)', (OUT / 'assets/site.css').read_text()))
        for route in self.ROUTES:
            html = self.html[route]
            main = main_of(html)
            total = len(html.encode())
            for href in re.findall(r'<link rel="stylesheet" href="(/assets/[^"]+)">', html):
                total += (OUT / href.lstrip('/')).stat().st_size
            for src in re.findall(r'<script src="(/assets/[^"]+)"', html):
                total += (OUT / src.lstrip('/')).stat().st_size
            total += sum((OUT / font.lstrip('/')).stat().st_size for font in fonts)
            for picture in re.findall(r'<picture>(.*?)</picture>', main, re.S):
                if 'loading="lazy"' in re.search(r'<img [^>]*>', picture).group(0):
                    continue
                srcset = re.search(r'type="image/avif" srcset="([^"]+)"', picture).group(1)
                total += max((OUT / part.split()[0].lstrip('/')).stat().st_size for part in srcset.split(','))
            for poster in set(re.findall(r'\sposter="([^"]+)"', main)):
                total += (OUT / poster.lstrip('/')).stat().st_size
            with self.subTest(route=route):
                self.assertLessEqual(total, FIRST_LOAD_BUDGET, f'{route} first load is {total} bytes')

    def test_every_video_follows_the_attribute_rules(self):
        # The inner pages (the homepage's hero loops take their posters from CSS; DaylightTests covers them).
        for route in self.ROUTES:
            if route == 'index.html':
                continue
            parser = VideoCollector()
            parser.feed(main_of(self.html[route]))
            with self.subTest(route=route):
                self.assertEqual(len(parser.videos), VIDEOS_PER_ROUTE.get(route, 0))
            for attrs, sources, ancestors in parser.videos:
                with self.subTest(route=route, poster=attrs.get('poster')):
                    for flag in ('muted', 'loop', 'playsinline'):
                        self.assertIn(flag, attrs)
                    self.assertEqual(attrs.get('preload'), 'none')
                    self.assertNotIn('autoplay', attrs)
                    self.assertNotIn('src', attrs)
                    self.assertTrue(attrs.get('width') and attrs.get('height'))
                    if 'close-video' in attrs.get('class', ''):
                        # Task 41: the decorative ambient loop behind the closing panel: wide screens only, its still fetched
                        # only near the screen, no file before reel.js plays it, inside an aria-hidden layer.
                        self.assertEqual(attrs.get('aria-hidden'), 'true')
                        self.assertEqual(attrs.get('data-loop'), 'wide')
                        self.assertNotIn('poster', attrs)
                        self.assertEqual(attrs.get('data-poster'), '/assets/glass/glass-ambient-poster.jpg')
                        self.assertEqual(sources, [{'data-src': '/assets/glass/glass-ambient-1600.mp4', 'type': 'video/mp4'}])
                        self.assertNotIn('controls', attrs)
                        self.assertTrue(any(a.get('class') == 'close-loop' and a.get('aria-hidden') == 'true' for a in ancestors))
                        for path in (attrs['data-poster'], sources[0]['data-src']):
                            self.assertTrue((OUT / path.lstrip('/')).is_file())
                        continue
                    self.assertRegex(attrs.get('poster', ''), r'^/assets/video/[a-z0-9-]+\.jpg$')
                    self.assertTrue((OUT / attrs['poster'].lstrip('/')).is_file())
                    self.assertEqual(len(sources), 1)
                    url = sources[0].get('src') or sources[0].get('data-src')
                    self.assertRegex(url, r'^/assets/video/[a-z0-9-]+\.mp4$')
                    self.assertTrue((OUT / url.lstrip('/')).is_file())
                    for name in ('data-narrow-src', 'data-narrow-poster'):
                        if name in attrs:
                            self.assertTrue((OUT / attrs[name].lstrip('/')).is_file())
                    if attrs.get('aria-hidden') == 'true':
                        # A silent loop: no file before reel.js plays it, no controls, and described by its device group.
                        self.assertIn('data-loop', attrs)
                        self.assertIn('data-src', sources[0])
                        self.assertNotIn('controls', attrs)
                        groups = [a for a in ancestors if a.get('role') == 'img']
                        self.assertEqual(len(groups), 1)
                        self.assertGreaterEqual(len(groups[0].get('aria-label', '')), 40)
                    else:
                        # A large video: native controls until reel.js swaps in its labelled button; a text alternative.
                        self.assertIn('controls', attrs)
                        self.assertTrue(attrs.get('aria-label'))
                        self.assertIn(f'id="{attrs["aria-describedby"]}"', self.html[route])
                        self.assertTrue(any('data-reel' in a for a in ancestors))

    def test_about_film_has_a_keyboard_button_progress_and_chapters(self):
        main = main_of(self.html['about/index.html'])
        film = re.search(r'<section class="film" aria-labelledby="film-title">(.*?)</section>', main, re.S).group(1)
        self.assertIn('<figure class="film-fig" data-reel>', film)
        self.assertIn('<video class="film-video" id="film-video" muted loop playsinline preload="none" controls', film)
        self.assertIn('data-narrow-src="/assets/video/cendavo-launch-vertical-720.mp4"', film)
        self.assertIn('<source src="/assets/video/cendavo-launch-1600.mp4" type="video/mp4">', film)
        # Hidden without JS (the native controls serve then); reel.js reveals a real button, the progress bar and the time.
        ui = re.search(r'<div class="film-ui" data-reel-ui hidden>(.*?)</div>', film, re.S).group(1)
        self.assertIn('<button class="reel-play" type="button" data-reel-toggle hidden>Play film</button>', ui)
        self.assertIn('<span class="reel-track" aria-hidden="true"><span class="reel-fill" data-progress></span></span>', ui)
        self.assertIn('<span class="reel-time" aria-hidden="true" data-time>', ui)
        chapters = re.search(r'<ol class="film-chapters" data-chapters="film-video" aria-label="Film chapters" hidden>(.*?)</ol>', film, re.S)
        self.assertIsNotNone(chapters)
        self.assertEqual(len(re.findall(r'<button type="button" data-t="\d+">', chapters.group(1))), 6)
        about_css = base_rules((OUT / 'assets/about.css').read_text())
        self.assertIn('min-height:44px', rules_for(about_css, '.reel-play')[0])
        self.assertIn('transform:scaleX(0)', rules_for(about_css, '.reel-fill')[0])  # reel.js scales it, never its width
        self.assertIn('aspect-ratio:16/9', rules_for(about_css, '.film-frame')[0])
        reel = (OUT / 'assets/reel.js').read_text()
        self.assertIn("reel.querySelector('[data-progress]')", reel)
        self.assertIn("bar.style.transform = 'scaleX('", reel)
        self.assertIn("reel.querySelector('[data-reel-ui]')", reel)

    def test_work_tiles_preview_their_loop_only_through_reel_js(self):
        work = main_of(self.html['work/index.html'])
        index = re.search(r'<ul class="wrap wk-index"[^>]*>(.*?)</ul>', work, re.S).group(1)
        previews = re.findall(r'<span class="wk-tile-img" aria-hidden="true" data-hover-src="([^"]+)">', index)
        self.assertEqual(previews, [f'/assets/video/loop-{name}-desktop.mp4' for name in ('hb', 'gl', 'fc')])
        for url in previews:
            self.assertTrue((OUT / url.lstrip('/')).is_file())
        self.assertNotIn('<video', index)  # nothing to download until a visitor hovers, focuses or centres a tile
        # Liquid Glass (Task 37) reverses the Daylight brief for the homepage: its three concept cards preview the same loops.
        for route in self.ROUTES:
            if route not in ('work/index.html', 'index.html'):
                self.assertNotIn('data-hover-src', self.html[route])
        home = main_of(self.html['index.html'])
        self.assertEqual(re.findall(r'data-hover-src="([^"]+)"', home), previews)
        self.assertNotIn('<video', ''.join(re.findall(r'<article class="teaser-card".*?</article>', home, re.S)))
        home_css = base_rules((OUT / 'assets/home.css').read_text())
        for needle in ('pointer-events:none', 'position:absolute', 'object-fit:cover'):
            self.assertIn(needle, ''.join(rules_for(home_css, '.hover-video')))
        work_css = base_rules((OUT / 'assets/work.css').read_text())
        hover = ''.join(rules_for(work_css, '.hover-video'))
        for needle in ('pointer-events:none', 'position:absolute', 'object-fit:cover'):
            self.assertIn(needle, hover)
        reel = (OUT / 'assets/reel.js').read_text()
        self.assertIn("doc.querySelectorAll('[data-hover-src]')", reel)
        self.assertIn('if (held || still || saveData || doc.hidden) return;', reel)
        self.assertIn("video.setAttribute('preload', 'none')", reel)
        self.assertIn("video.setAttribute('aria-hidden', 'true')", reel)

    def test_pause_motion_button_on_every_page_that_moves(self):
        # Task 41 (WCAG 2.2.2): every page with ongoing motion (WebGL, the drift, the marquee, video loops) gets exactly one
        # Pause motion button, hidden until site.js runs; Demo and the 404 page have none. Task 46: it lives inside the
        # header (the glass nav pill), never after <main>, so it can never cover page content.
        button = '<button class="motion-btn" type="button" data-motion-toggle aria-pressed="false" hidden>Pause motion</button>'
        moving = ('index.html', 'work/index.html', 'services/index.html', 'pricing/index.html', 'about/index.html', 'contact/index.html')
        for route in moving:
            with self.subTest(route=route):
                html = (OUT / route).read_text()
                self.assertEqual(html.count('data-motion-toggle'), 1)
                header = re.search(r'<header class="site-header">.*?</header>', html, re.S).group(0)
                self.assertIn('CENDAVO</a>' + button + '<button class="menu"', header)
                self.assertNotIn('data-motion-toggle', html.split('</header>', 1)[1])
                self.assertNotIn('data-motion-toggle', html[html.index('id="site-nav"'):])  # not inside the collapsible menu
                self.assertLess(html.index('/assets/site.js'), html.index('/assets/glass-boot.js'))  # site.js drives it
        for route in ('demo/index.html', '404.html'):
            with self.subTest(route=route):
                self.assertNotIn('data-motion-toggle', (OUT / route).read_text())
        # One style for every page, in the shared glass.css; nothing floats or pins it any more.
        for sheet in SHEETS:
            with self.subTest(sheet=sheet):
                css = (OUT / 'assets' / sheet).read_text()
                self.assertNotIn('.motion-fab', css)
                self.assertNotRegex(css, r'\.motion-btn[^{]*\{[^}]*position:(?:fixed|sticky|absolute)')
                if sheet != 'glass.css':
                    self.assertNotIn('.motion-btn', css)
        site = (OUT / 'assets/site.js').read_text()
        self.assertIn("document.querySelector('[data-motion-toggle]')", site)
        reel = (OUT / 'assets/reel.js').read_text()
        self.assertNotIn('data-motion-toggle', reel)  # reel.js only follows the shared state
        self.assertNotIn('motion.hidden', reel)


class GlassPageSceneTests(unittest.TestCase):
    """Liquid Glass inner pages, part 1 (Task 39): Work and Services each get one aria-hidden WebGL scene host behind the hero,
    fitted to a hero element, imported by glass-boot.js from a fixed list (tests/test_demo_js.py covers when). The media it
    stands in for stays in the page; the module imports only vendored three and (Task 48) glass-shapes.js by relative path."""

    PAGES = {'work/index.html': ('slab', '.wk-clip', False), 'services/index.html': ('panes', '.sv-hero-media', True),
             'pricing/index.html': ('sheets', '.quote-desk', False), 'about/index.html': ('photos', '.ab-photos', True),
             'contact/index.html': ('mark', '.ct-gl-spot', False)}
    # Task 40: the Contact form block as it stood before the scene was added (pages/contact.html source, placeholders intact).
    CONTACT_FORM_SHA256 = 'd2e002ac26f55a10571d853e20320bd8ee5fe26a07ee0e99003c9e3c10559220'

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = {route: (OUT / route).read_text() for route in cls.PAGES}
        cls.module = (OUT / 'assets/glass-page.js').read_text()
        cls.pages_css = (OUT / 'assets/pages.css').read_text()

    def test_one_aria_hidden_host_per_page_anchored_inside_its_hero(self):
        for route, (kind, anchor, hide) in self.PAGES.items():
            with self.subTest(route=route):
                main = main_of(self.html[route])
                self.assertEqual(main.count(' data-gl '), 1)
                # Contact has no .pg-hero: its scene sits in the .ct section, beside the form, never inside it.
                hero = re.search(r'<section class="(?:pg-hero[^"]*|ct)".*?</section>', main, re.S).group(0)
                host = re.search(r'<div class="pg-gl" data-gl data-gl-kind="([a-z]+)"[^>]*></div>', hero)
                self.assertIsNotNone(host)
                self.assertEqual(host.group(1), kind)
                tag = host.group(0)
                self.assertIn(f'data-gl-anchor="{anchor}"', tag)
                self.assertIn('aria-hidden="true"', tag)
                self.assertNotIn('role=', tag)
                self.assertRegex(hero, r'class="[^"]*\b' + re.escape(anchor[1:]) + r'\b')
                self.assertEqual('data-gl-hide' in tag, hide)
                self.assertTrue(main.index(tag) < main.index('<h1'))  # behind the copy, before it in source order

    def test_the_media_it_stands_in_for_stays_in_the_page(self):
        services = main_of(self.html['services/index.html'])
        # Task 45: the Services media is three static CSS glass panes (aria-hidden: the chapter links name the services).
        media = re.search(r'<div class="sv-hero-media sv-panes" data-ph-media aria-hidden="true">(.*?)</div></div>', services, re.S).group(1)
        self.assertEqual(re.findall(r'<b>([^<]+)</b>', media), ['New website', 'Redesign', 'Care plan'])
        self.assertEqual(media.count('<div class="sv-pane">'), 3)
        self.assertNotIn('<img', media)
        work = main_of(self.html['work/index.html'])
        clip = re.search(r'<div class="clip wk-clip".*?</div>\n</div>', work, re.S).group(0)
        self.assertRegex(clip, r'<video class="sp-video"[^>]* controls [^>]*aria-label="Three signs video"')
        self.assertIn('data-reel-toggle', clip)
        # Only a motion-guarded .gl-lead rule hides it, and only on Services; the canvas never takes clicks.
        guarded = without_blocks(self.pages_css, MOTION_GUARD)[1]
        self.assertIn('.gl-lead .sv-hero-media{opacity:0}', ''.join(guarded))
        self.assertRegex(self.pages_css, r'\.pg-gl\{[^}]*pointer-events:none')
        self.assertRegex(self.pages_css, r'\.pg-gl canvas\{[^}]*pointer-events:none')
        self.assertIn(".classList.add('gl-lead')", self.module)

    def test_part_two_content_stays_html_and_the_contact_form_is_unchanged(self):
        # Task 40. About: the collage photos stay in the page; only a motion-guarded .gl-lead rule fades them.
        about = main_of(self.html['about/index.html'])
        photos = re.search(r'<div class="ab-photos" aria-hidden="true">.*?</div>', about, re.S).group(0)
        for name in ('barber-shave', 'detail-wax', 'garden-wall'):
            self.assertRegex(photos, r'<img src="/assets/images/' + name + r'-800\.jpg"[^>]* alt=""')
        guarded, unguarded = without_blocks(self.pages_css, MOTION_GUARD)[1], without_blocks(self.pages_css, MOTION_GUARD)[0]
        self.assertIn('.gl-lead .ab-photos{opacity:0}', ''.join(guarded))
        self.assertNotIn('.ab-photos{opacity:0}', unguarded)
        # Pricing: every quote line is still HTML text in front of the sheets.
        quote = re.search(r'<div class="quote-desk">.*?</figure>', main_of(self.html['pricing/index.html']), re.S).group(0)
        for k, v in (('Pages', 'Home and the pages we agree on'), ('Enquiries', 'Enquiry form to your inbox'), ('Booking', 'If you need it'),
                     ('Words', 'Written with you, or supplied'), ('Photos', 'Yours, edited and optimised'), ('Launch', 'Domain, hosting setup and go-live')):
            self.assertIn(f'<span class="k">{k}</span><span class="v">{v}</span>', quote)
        self.assertIn('<b>Fixed price</b>', quote)
        # Contact: the form block is byte-for-byte what it was, there is one form, and the scene host is outside it.
        source = (ROOT / 'pages/contact.html').read_text()
        form = re.search(r'<form.*?</form>', source, re.S).group(0)
        self.assertEqual(hashlib.sha256(undo_edits(self, form, TASK47_FORM_EDITS).encode()).hexdigest(), self.CONTACT_FORM_SHA256)
        contact = main_of(self.html['contact/index.html'])
        self.assertEqual(contact.count('<form'), 1)
        built = re.search(r'<form.*?</form>', contact, re.S).group(0)
        self.assertNotIn('data-gl', built)
        self.assertLess(contact.index('class="pg-gl"'), contact.index('<form'))
        self.assertIn('<script src="/assets/enquiry.js" defer></script>', self.html['contact/index.html'])
        self.assertNotIn('glass.js"', self.html['contact/index.html'])  # Contact still gets no Lenis or glass.js shell
        self.assertRegex(self.pages_css, r':is\(\.pg-hero,\.ct\):has\(>\.pg-gl\)>\.wrap\{position:relative;z-index:1\}')

    def test_part_two_scene_photos_are_fixed_files(self):
        # The photos the About and Contact scenes draw are hard-coded and exist; no path is read from the page.
        block = re.search(r'export const PHOTOS = \{.*?\};', self.module, re.S).group(0)
        srcs = re.findall(r"'(/assets/images/[a-z-]+-800\.jpg)'", block)
        self.assertEqual(len(srcs), 4)
        for src in srcs:
            self.assertTrue((OUT / src.lstrip('/')).is_file(), src)
        self.assertNotIn('dataset.glPhoto', self.module)
        self.assertNotIn('getAttribute(', self.module)

    def test_module_imports_only_by_relative_path_and_shares_pause_motion(self):
        imports = re.findall(r"^import [^;]*? from '([^']+)';", self.module, re.M)
        # Task 48: the shared helpers come from glass-shapes.js, never from the homepage scene.
        self.assertEqual(imports, ['./vendor/three/three.module.min.js', './glass-shapes.js'])
        self.assertNotRegex(self.module, r"from 'three|from '/|import\(")
        for banned in ('http', 'fetch(', 'XMLHttpRequest', 'innerHTML', 'eval(', 'localStorage', 'preserveDrawingBuffer', 'preload = \'auto\''):
            self.assertNotIn(banned, self.module)
        # Pause motion: joins the shared fan-out; never replaces a handler glass.js already installed.
        self.assertIn('(G.pauseFns = G.pauseFns || []).push(set);', self.module)
        self.assertNotRegex(self.module, r'(?<!if \(!G\.onPauseChange\) )G\.onPauseChange =')
        self.assertIn("canvas.setAttribute('aria-hidden', 'true');", self.module)
        self.assertIn('setAnimationLoop(null)', self.module)
        self.assertEqual(self.module, (ROOT / 'assets/glass-page.js').read_text())  # modules ship as written
        self.assertLessEqual(len(self.module.encode()), 24 * 1024)
        # Videos the scene may play come from a fixed map, never from page data.
        self.assertRegex(self.module, r"const LOOP = \{ 'loop-gl-desktop': '/assets/video/loop-gl-desktop' \};")
        self.assertTrue((OUT / 'assets/video/loop-gl-desktop.mp4').is_file())
        self.assertTrue((OUT / 'assets/video/loop-gl-desktop-poster.jpg').is_file())


class MobileAndContactPolishTests(unittest.TestCase):
    """Task 42 (owner-mandated): on phones the Pause motion button is a 44x44 icon that keeps its name and never sits on the
    hero buttons; the homepage tag leaves the nav pill's corner; the Contact glass C refracts a light photo, a little larger.
    Task 46 moved the button into the header, so these now check it there."""

    BUTTON = '<button class="motion-btn" type="button" data-motion-toggle aria-pressed="false" hidden>Pause motion</button>'

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = {name: (OUT / 'assets' / name).read_text() for name in ('glass.css', 'home.css', 'pages.css')}
        cls.home = (OUT / 'index.html').read_text()
        cls.module = (OUT / 'assets/glass-page.js').read_text()

    def test_phone_pause_button_is_a_44px_icon_that_keeps_its_name(self):
        # Same markup on every page that moves, so the accessible name stays "Pause motion".
        for route in ('index.html', 'work/index.html', 'services/index.html', 'pricing/index.html', 'about/index.html', 'contact/index.html'):
            with self.subTest(route=route):
                self.assertEqual((OUT / route).read_text().count(self.BUTTON), 1)
        # Task 46: an icon on phones and tablets (the header row has no room for the words below 1200px), with its words
        # shown on wide screens. One rule, in the shared glass.css.
        narrow = rules_for(media_blocks(self.css['glass.css'], 'max-width:1199px'), '.motion-btn')
        self.assertEqual(len(narrow), 1)
        for needle in ('width:44px', 'height:44px', 'padding:0', 'font-size:0'):
            self.assertIn(needle, narrow[0])
        base = rules_for(base_rules(self.css['glass.css']), '.motion-btn')[0]
        for needle in ('min-height:44px', 'min-width:44px', 'justify-content:center'):
            self.assertIn(needle, base)
        # The label is shrunk, never removed from the accessibility tree, and the button never disappears.
        for banned in ('display:none', 'visibility:hidden', 'opacity:0'):
            self.assertNotIn(banned, narrow[0])
        self.assertNotRegex(narrow[0], r'(?<![-\w])content:')  # no generated text replacing the label
        self.assertNotIn('font-size:0', base)  # the words show on wide screens
        # The icon is drawn with borders in both states (Task 46: pause bars, then a play triangle when pressed).
        self.assertIn('border-inline:2.5px solid currentColor', rules_for(base_rules(self.css['glass.css']), '.motion-btn::before')[0])
        self.assertIn('background:var(--ink)', rules_for(base_rules(self.css['glass.css']), '.motion-btn[aria-pressed="true"]')[0])
        for sheet in ('home.css', 'pages.css'):
            with self.subTest(sheet=sheet):
                self.assertNotIn('.motion-btn', self.css[sheet])  # one place styles and sizes the button
        self.assertIn(':focus-visible{outline:2px solid var(--ink)', (OUT / 'assets/site.css').read_text())

    def test_phone_hero_buttons_cannot_meet_the_pause_button(self):
        # Task 46: the button lives in the header, so the full-width phone hero buttons need no lane beside them: nothing
        # floats over the page. The header row keeps the logo, the button and the menu button.
        for sheet in ('home.css', 'pages.css'):
            with self.subTest(sheet=sheet):
                self.assertNotIn('body:has(.motion-fab', self.css[sheet])
                self.assertNotIn('44px + max(12px,env(safe-area-inset-right))', self.css[sheet])
        self.assertNotRegex(self.css['glass.css'], r'\.motion-btn[^{]*\{[^}]*position:fixed')
        self.assertIn('CENDAVO</a>' + self.BUTTON + '<button class="menu"', self.home)
        self.assertIn('width:100%', rules_for(media_blocks(self.css['home.css'], 'max-width:640px'), '.actions .button')[0])
        self.assertIn('href="#work">See concept projects</a>', main_of(self.home))
        pricing = main_of((OUT / 'pricing/index.html').read_text())
        self.assertRegex(pricing, re.compile(r'<section class="pg-hero[^"]*"(?:(?!</section>).)*<div class="pg-actions"', re.S))  # in the hero

    def test_phone_hero_tag_follows_the_copy_instead_of_the_nav_corner(self):
        hero = re.search(r'<section class="hero".*?</section>', self.home, re.S).group(0)
        self.assertLess(hero.index('class="wrap hero-in"'), hero.index('<p class="hero-cap lg">'))  # after the stage and buttons
        # Task 46: in the flow at every width up to 1023px (at 768 the corner tag used to cover "See concept projects").
        self.assertEqual(rules_for(media_blocks(self.css['home.css'], 'max-width:760px'), '.hero-cap'), [])
        tablet = rules_for(media_blocks(self.css['home.css'], 'max-width:1023px'), '.hero-cap')
        self.assertEqual(len(tablet), 1)
        self.assertIn('position:relative', tablet[0])  # in the flow, still painted above the absolutely placed stage
        self.assertNotRegex(tablet[0], r'(?<![-\w])top:')
        self.assertIn('flex-wrap:wrap', tablet[0])
        self.assertIn('z-index:2', rules_for(base_rules(self.css['home.css']), '.hero-cap')[0])
        # The phone poster scales with the width, so the taller hero never enlarges the wordmark into the headline.
        self.assertIn('background-size:100% auto', rules_for(media_blocks(self.css['home.css'], 'max-width:760px'), '.hero-gl')[0])

    def test_contact_glass_c_refracts_a_light_photo_and_is_larger(self):
        block = re.search(r'export const PHOTOS = \{.*?\};', self.module, re.S).group(0)
        mark = re.search(r"mark: \[\['(/assets/images/[a-z-]+-800\.jpg)'", block)
        self.assertIsNotNone(mark)
        self.assertNotIn('detail-headlight', block)  # mostly black: it showed as a dark fill inside the C
        self.assertIn(mark.group(1), ('/assets/images/clean-kitchen-800.jpg', '/assets/images/clean-living-800.jpg',
                                      '/assets/images/garden-deck-800.jpg'))
        self.assertTrue((OUT / mark.group(1).lstrip('/')).is_file())
        scale = float(re.search(r'mark: \[0, 0, ([\d.]+)\]', self.module).group(1))
        self.assertGreater(scale, 1.0)
        self.assertLessEqual(scale, 1.3)  # a little larger, not a different composition
        # The scene's own background stays the light paper colour; nothing in the module paints a dark plane for the mark.
        self.assertIn('scene.background = paper;', self.module)
        spot = rules_for(base_rules(self.css['pages.css']), '.ct-gl-spot')[0]
        size = [int(v) for v in re.findall(r'(?:^|;)(?:width|height):(\d+)px', spot)]
        self.assertEqual(len(size), 2)
        self.assertTrue(all(v >= 200 for v in size), spot)
        self.assertIn('.ct-gl-spot{display:none}', media_blocks(self.css['pages.css'], 'max-width:760px'))


class GlassCritiqueFixesTests(unittest.TestCase):
    """Task 43 (owner-mandated): the Pause motion button's icon agrees with its pressed state and keeps clear of FAQ toggles
    and the marquee on phones (since Task 46 by living in the header); the demo heading fits its card; the Work queue labels show in full; the footer wordmark is no
    longer cut at its foot; reveal companions (labels, intros, card shells) rise with what they belong to."""

    LANE = 'calc(44px + max(12px,env(safe-area-inset-right)))'
    SHOWN = 'body:has(.motion-fab:not([hidden]))'

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = {name: (OUT / 'assets' / name).read_text() for name in ('site.css', 'glass.css', 'home.css', 'pages.css', 'work.css')}

    def test_pressed_pause_button_is_inverted_and_its_icon_follows_the_state(self):
        # Task 46 (owner): the icon reflects the state: pause bars while motion runs, a play triangle once pressed (motion
        # paused). The name stays "Pause motion" (a toggle button's name is fixed; aria-pressed carries the state).
        css = base_rules(self.css['glass.css'])
        rest = rules_for(css, '.motion-btn')[0]
        pressed = rules_for(css, '.motion-btn[aria-pressed="true"]')
        self.assertEqual(len(pressed), 1)
        self.assertIn('background:var(--ink)', pressed[0])
        self.assertIn('color:#fff', pressed[0])
        self.assertNotIn('background:var(--ink)', rest)  # resting and pressed look different
        self.assertEqual(rules_for(css, '.motion-btn[aria-pressed="true"]:hover'), pressed)  # hover keeps the state
        self.assertIn('border-inline:2.5px solid currentColor', rules_for(css, '.motion-btn::before')[0])  # pause bars
        icon = rules_for(css, '.motion-btn[aria-pressed="true"]::before')[0]
        for needle in ('width:0', 'height:0', 'border-inline:0', 'border-block:6px solid transparent', 'border-left:10px solid currentColor'):
            self.assertIn(needle, icon)  # a play triangle, drawn with borders
        self.assertLess(icon.index('border-inline:0'), icon.index('border-left:'))  # the triangle's side survives the reset
        forced = rules_for(media_blocks(self.css['glass.css'], 'forced-colors:active'), '.motion-btn[aria-pressed="true"]')
        self.assertEqual(len(forced), 1)  # still distinct when the system forces colours (::before inherits the opt-out)
        for needle in ('forced-color-adjust:none', 'background:ButtonText', 'color:ButtonFace'):
            self.assertIn(needle, forced[0])
        for sheet in ('home.css', 'pages.css'):
            self.assertNotIn('.motion-btn', self.css[sheet])
        # The name never changes with the state (aria-pressed carries it), so the label and state cannot disagree.
        site = (OUT / 'assets/site.js').read_text()
        toggle = site[site.index("const toggle = document.querySelector('[data-motion-toggle]');"):site.index("const asked = document.querySelector('[data-nf-path]');")]
        for banned in ('textContent', 'innerHTML', 'aria-label', 'Play motion'):
            self.assertNotIn(banned, toggle)

    def test_phone_faq_toggles_and_marquee_keep_clear_of_the_pause_button(self):
        # Task 46: the button moved into the header, so the FAQ toggles and the marquee use the full width again: no lane
        # rules remain, and nothing positions the button over the page.
        for sheet in ('home.css', 'pages.css'):
            with self.subTest(sheet=sheet):
                self.assertNotIn(self.SHOWN, self.css[sheet])
                self.assertNotIn(self.LANE, self.css[sheet])
        self.assertEqual(rules_for(media_blocks(self.css['home.css'], 'max-width:640px'), '.mq-strip'), [])
        self.assertEqual(rules_for(media_blocks(self.css['pages.css'], 'max-width:640px'), '.faq summary'), [])
        self.assertNotRegex(self.css['glass.css'], r'\.motion-btn[^{]*\{[^}]*position:fixed')

    def test_demo_heading_fits_its_card(self):
        rule = rules_for(base_rules(self.css['site.css']), '.demo-side h2')
        self.assertEqual(len(rule), 1)
        self.assertRegex(rule[0], r'font-size:clamp\(')
        self.assertIn('overflow-wrap:anywhere', rule[0])
        self.assertNotIn('nowrap', rule[0])
        self.assertIn('<h2 id="demo-glance-title">Requests at a glance</h2>', (OUT / 'demo/index.html').read_text())

    def test_work_queue_labels_show_in_full(self):
        css = base_rules(self.css['work.css'])
        for selector in ('.wk-demo-mini', '.wk-demo-mini i', '.wk-demo-mini em', '.wk-demo-mini b'):
            with self.subTest(selector=selector):
                rule = rules_for(css, selector)[0]
                for banned in ('ellipsis', 'nowrap', 'overflow:hidden'):
                    self.assertNotIn(banned, rule)
        self.assertIn('container-type:inline-size', rules_for(css, '.wk-demo-mini')[0])  # scales with its tile
        self.assertIn('font:600 min(.6875rem,3.9cqi)/1.2', rules_for(css, '.wk-demo-mini b')[0])  # capped at today's size
        work = (OUT / 'work/index.html').read_text()
        for label in ('Website redesign', 'Booking question', 'Quote sent', 'Site visit booked'):
            self.assertIn(f'<b>{label}</b>', work)

    def test_footer_wordmark_is_whole_and_reads_on_glass(self):
        sign = rules_for(base_rules(self.css['glass.css']), '.footer-sign')
        self.assertEqual(len(sign), 1)
        self.assertIn('height:auto', sign[0])  # no longer shorter than its line box
        self.assertIn('overflow:clip visible', sign[0])  # clipped sideways only: a phone page never widens
        self.assertNotIn('overflow:hidden', sign[0])
        self.assertGreaterEqual(float(re.search(r'line-height:([\d.]+)', sign[0]).group(1)), 0.9)
        self.assertNotIn('padding-bottom', sign[0])
        self.assertNotIn('margin-bottom', sign[0])
        word = rules_for(base_rules(self.css['glass.css']), '.footer-word')[0]
        shadows = re.findall(r'drop-shadow\(([^()]*\([^()]*\))\)', word)
        self.assertEqual(len(shadows), 1)  # one soft shadow: no glow layers
        alpha = float(re.search(r'rgba\(58,40,12,([\d.]+)\)', shadows[0]).group(1))  # the same warm shade, a little stronger
        self.assertGreater(alpha, 0.14)
        self.assertLessEqual(alpha, 0.3)

    def test_reveal_companions_rise_with_what_they_belong_to(self):
        work = (OUT / 'work/index.html').read_text()
        self.assertEqual(work.count('<p class="cs-label" data-rise>'), 3)
        self.assertNotIn('<p class="cs-label">', work)
        pricing = (OUT / 'pricing/index.html').read_text()
        self.assertIn('<div class="pr-care-card" data-rise>\n<h2 id="pcare-title" class="h2">', pricing)  # the card, not just its title
        self.assertIn('<p data-rise>Whatever the size of the site,', pricing)
        about = (OUT / 'about/index.html').read_text()
        self.assertIn('</h2><p data-rise>If customers find you on their phone', about)

    def test_homepage_gaps_are_tighter(self):
        css = base_rules(self.css['home.css'])
        self.assertIn('--home-sec:clamp(52px,6.4vw,92px)', css)
        for selector in ('.reel', '.work', '.ba', '.services'):
            with self.subTest(selector=selector):
                self.assertEqual(rules_for(css, selector), ['padding-block:var(--home-sec)'])
        self.assertIn('padding-block:clamp(110px,13vw,190px) clamp(56px,6vw,96px)', rules_for(css, '.band')[0])


def hsl_saturation(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    high, low = max(r, g, b), min(r, g, b)
    light = (high + low) / 2
    return 0.0 if high == low else (high - low) / (1 - abs(2 * light - 1))


class GlassHeroAndReelTests(unittest.TestCase):
    """Task 44, batch A (owner-mandated): the homepage hero's canvas feathers out at its foot, the glass name is milky white,
    the photos behind the About and Contact C are feathered, the showreel has no box (no radius, edge blend, chapters as
    page typography below it, one glass chip), the About film's control sits below the film, and the page atmosphere is
    calmer. The hero's exit pose, layout and materials are checked numerically in tests/test_demo_js.py."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.home = main_of((OUT / 'index.html').read_text())
        cls.about = main_of((OUT / 'about/index.html').read_text())
        cls.css = {name: (OUT / 'assets' / name).read_text() for name in ('home.css', 'about.css', 'glass.css')}
        cls.scene = (OUT / 'assets/glass-scene.js').read_text()
        cls.page = (OUT / 'assets/glass-page.js').read_text()

    def test_hero_canvas_feathers_out_at_its_foot(self):
        rule = rules_for(base_rules(self.css['home.css']), '.hero-gl')[0]
        for prop in ('-webkit-mask-image', 'mask-image'):
            with self.subTest(prop=prop):
                stop = re.search(rf'(?:^|;){re.escape(prop)}:linear-gradient\(180deg,#000 (\d+)%,transparent\)', rule)
                self.assertIsNotNone(stop)
                self.assertLess(int(stop.group(1)), 90)  # a real fade, not a hairline
        # The canvas fills the host, so the host's mask feathers it too; the still underneath is never hidden.
        self.assertEqual(rules_for(base_rules(self.css['home.css']), '.hero-canvas'), ['position:absolute;inset:0;width:100%;height:100%'])

    def test_glass_name_is_milky_and_screens_are_sharper(self):
        self.assertNotIn('#d9e1e6', self.scene)  # the blue-grey "gunmetal" body is gone
        self.assertIn('screen(SCREENS.gl)', self.scene)
        self.assertIn('screen(SCREENS.hb)', self.scene)
        for name in ('gl', 'hb'):
            with self.subTest(screen=name):
                bias = float(re.search(rf"{name}: \{{ name: '{name}-desktop'[^}}]*bias: ([\d.]+) \}}", self.scene).group(1))
                self.assertLessEqual(bias, 0.8)
        self.assertIn('L = heroLayout(camera.aspect);', self.scene)
        self.assertIn('const pose = heroPose(e, t, sm.px, sm.py, k);', self.scene)
        frame = self.scene.split('function frame(dt) {', 1)[1].split('\n  }', 1)[0]
        self.assertNotIn('e * 0.5', frame)  # no tilt back on exit
        self.assertNotIn('-e * 4.2', frame)  # no pulling away

    def test_photos_behind_the_c_are_feathered_in_the_scene_and_the_fallback(self):
        self.assertIn("const g = x.createRadialGradient(64, 64, 18, 64, 64, 64);", self.page)
        self.assertIn("g.addColorStop(1, '#000');", self.page)  # alphaMap reads green: black is fully transparent
        card = self.page.split('const photoCard = (src, w, h) => {', 1)[1].split('};', 1)[0]
        for needle in ('alphaMap: feather', 'blending: THREE.CustomBlending', 'depthWrite: false', 'm.renderOrder = 1'):
            self.assertIn(needle, card)
        # Both the About photos and the Contact backplate are photo cards.
        self.assertIn("const p = kind === 'photos' ? photoCard(src, 2.7, 1.8) : photoCard(src, 2.6, 1.75);", self.page)
        rule = rules_for(base_rules(self.css['about.css']), '.ab-photos .photo')[0]
        for prop in ('-webkit-mask-image', 'mask-image'):
            with self.subTest(prop=prop):
                self.assertRegex(rule, rf'(?:^|;){re.escape(prop)}:radial-gradient\([^;]*#000 \d+%,transparent 100%\)')

    def test_showreel_has_no_box_and_its_chapters_sit_below_it(self):
        css = self.css['home.css']
        frame = rules_for(base_rules(css), '.reel-frame')[0]
        self.assertIn('border-radius:0', frame)
        self.assertNotIn('box-shadow', frame)
        for prop in ('-webkit-mask-image', 'mask-image'):
            self.assertRegex(frame, rf'(?:^|;){re.escape(prop)}:linear-gradient\(90deg,transparent,[^;]*transparent\),linear-gradient\(180deg,transparent,')
        self.assertIn('mask-composite:intersect', frame)
        self.assertIn("{ clipPath: 'inset(0% 0% 0% 0% round 0px)'", (OUT / 'assets/home.js').read_text())  # the lens ends square
        section = re.search(r'<section class="reel band-warm".*?</section>', self.home, re.S).group(0)
        media = re.search(r'<div class="reel-frame">(.*?)</div>', section, re.S).group(1)
        self.assertEqual(media.count('<button'), 1)  # exactly one control over the film
        self.assertIn('<button class="reel-toggle" type="button" data-reel-toggle hidden>Play showreel</button>', media)
        self.assertNotIn('chapters', media)
        # The chapter list follows the film in the page flow, as plain typography (no dark glass panel over the film).
        self.assertLess(section.index('<div class="reel-frame">'), section.index('<div class="reel-panel"><ol class="chapters"'))
        self.assertNotIn('lg-dark', section)
        for selector in ('.reel-panel', '.chapters', '.chapters button'):
            for body in rules_for(css, selector):  # every block, every screen size
                with self.subTest(selector=selector):
                    self.assertNotRegex(body, r'position:(?:absolute|fixed)')
        # The glass chip sits in the top corner, clear of the film's own subtitles along its foot.
        toggle = rules_for(base_rules(css), '.reel-toggle')[0]
        self.assertIn('top:10%', toggle)
        self.assertNotIn('bottom:', toggle)
        # No ghost device frame: no laptop selector or element anywhere around the reel.
        self.assertNotIn('laptop', section.replace('on a laptop and a phone', ''))
        self.assertNotRegex(re.sub(r'/\*.*?\*/', '', css, flags=re.S), r'\.[\w-]*laptop')

    def test_about_film_control_sits_below_the_film_never_over_its_text(self):
        film = re.search(r'<figure class="film-fig" data-reel>(.*?)</figure>', self.about, re.S).group(1)
        frame = re.search(r'<div class="film-frame">(.*?)</div>', film, re.S).group(1)
        self.assertNotIn('film-ui', frame)
        self.assertIn('</video></div>\n<div class="film-ui" data-reel-ui hidden>', film)
        for body in rules_for(self.css['about.css'], '.film-ui'):
            self.assertNotRegex(body, r'position:(?:absolute|fixed)|(?:^|;)(?:bottom|top|left|right):')
        self.assertIn('margin:16px auto 0', rules_for(base_rules(self.css['about.css']), '.film-ui')[0])

    def test_atmosphere_is_a_calm_warm_white(self):
        css = base_rules(self.css['glass.css'])
        base = float(re.search(r'opacity:([\d.]+)', rules_for(css, '.atmos i')[0]).group(1))
        for n in range(1, 5):
            rule = rules_for(css, f'.atmos i:nth-child({n})')[0]
            with self.subTest(field=n):
                own = re.search(r'opacity:([\d.]+)', rule)
                opacity = float(own.group(1)) if own else base
                colours = re.findall(r'#[0-9A-Fa-f]{6}', rule)
                self.assertTrue(colours)
                for colour in colours:
                    self.assertTrue(hsl_saturation(colour) <= 0.30 or opacity <= 0.25, (colour, opacity))


class CleanPanesWhiteTypeAndWordExitTests(unittest.TestCase):
    """Task 45 (owner-mandated): the Services panes are clean white glass with no photo inside or behind them, fanned so each
    title reads, with a static CSS version for phones and fallbacks; the homepage marquee type is white frosted glass with a
    separate rim, its pills ride centred on their photo tiles in one strip; the hero's CENDAVO name leaves early in the exit.
    paneLayout and heroPose's word are checked numerically in tests/test_demo_js.py."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.page = (OUT / 'assets/glass-page.js').read_text()
        cls.scene = (OUT / 'assets/glass-scene.js').read_text()
        cls.services_css = (OUT / 'assets/services.css').read_text()
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.home = main_of((OUT / 'index.html').read_text())
        cls.services = main_of((OUT / 'services/index.html').read_text())

    def test_scene_panes_load_no_photo(self):
        branch = self.page.split("} else if (kind === 'panes') {", 1)[1].split("} else if (kind === 'sheets') {", 1)[0]
        for banned in ('barber-chair', 'img(', 'TextureLoader', 'back.add', '.jpg'):
            self.assertNotIn(banned, branch)
        self.assertNotIn('barber-chair', self.page)

    def test_css_panes_are_clean_fanned_and_fit_a_phone(self):
        self.assertNotIn('barber-chair', self.services)
        self.assertNotIn('fetchpriority', self.services)  # no hero photo left to prioritise; the H1 leads
        base = base_rules(self.services_css)
        narrow = media_blocks(self.services_css, 'max-width:1023px')
        for css in (base, narrow):
            for selector in ('.sv-pane', '.sv-pane:nth-child(2)', '.sv-pane:nth-child(3)'):
                for rule in rules_for(css, selector):
                    self.assertNotRegex(rule, r'url\(|background-image|gradient')  # white glass only, never a photo
        pane = rules_for(base, '.sv-pane')[0]
        self.assertIn('position:absolute', pane)
        self.assertIn('aspect-ratio:16/10', pane)
        self.assertIn('overflow:hidden', pane)

        def geometry(css, fallback=None):
            def pct(selector, prop):
                rule = ''.join(rules_for(css, selector))
                found = re.search(rf'(?:^|;){prop}:([\d.]+)%', rule)
                return float(found.group(1)) if found else (fallback(selector, prop) if fallback else 0.0)
            return pct

        desk = geometry(base)
        phone = geometry(narrow, desk)
        # Container aspect (height / width): 4/5 on desktop, 4/3 below 1024px; a pane is 16/10.
        self.assertIn('aspect-ratio:4/5', rules_for(base, '.sv-hero-media')[0])
        self.assertIn('aspect-ratio:4/3', ''.join(rules_for(narrow, '.sv-hero-media')))
        for name, pct, box in (('desktop', desk, 5 / 4), ('phone', phone, 3 / 4)):
            with self.subTest(layout=name):
                width = pct('.sv-pane', 'width')
                height = width * 10 / 16 / box  # pane height as a % of the container's height
                tops = [pct(s, 'top') for s in ('.sv-pane', '.sv-pane:nth-child(2)', '.sv-pane:nth-child(3)')]
                lefts = [pct(s, 'left') for s in ('.sv-pane', '.sv-pane:nth-child(2)', '.sv-pane:nth-child(3)')]
                self.assertTrue(tops[0] < tops[1] < tops[2])
                self.assertTrue(lefts[0] < lefts[1] < lefts[2])
                for i in (0, 1):
                    self.assertGreaterEqual(tops[i + 1] - tops[i], 0.4 * height)  # 40%+ of each covered pane shows
                self.assertLessEqual(tops[2] + height, 100)
                self.assertLessEqual(lefts[2] + width, 100)  # never wider than its box: no sideways scroll
        # At 390px nothing in the narrow rules is wider than the phone.
        for px in re.findall(r'(?<![-\w])(?:min-)?width:(\d+)px', narrow):
            self.assertLessEqual(int(px), 390)
        self.assertIn('max-width:600px', ''.join(rules_for(narrow, '.sv-hero-media')))
        # No new motion: the panes only take part in the existing guarded opening (.ph-wait, data-ph-media).
        self.assertNotIn('animation', self.services_css)
        self.assertNotIn('transition', ''.join(rules_for(base, '.sv-pane')))
        reduced = media_blocks(self.services_css, 'prefers-reduced-transparency:reduce')
        self.assertIn('.sv-pane{background-color:#FBFAF7;-webkit-backdrop-filter:none;backdrop-filter:none}', reduced)

    def test_marquee_type_is_white_frosted_glass_with_a_separate_rim(self):
        base = base_rules(self.home_css)
        fill = [rule for rule in rules_for(base, '.mq-type') if 'background' in rule]
        self.assertEqual(len(fill), 1)
        gradient = re.search(r'background:linear-gradient\(([^;]*)\)(?:;|$)', fill[0]).group(1)
        self.assertNotIn('var(--ink)', gradient)
        self.assertNotIn('#3A3530', gradient.upper())
        colours = re.findall(r'#[0-9A-Fa-f]{6}', gradient)
        self.assertGreaterEqual(len(colours), 2)
        self.assertNotIn('rgba(', gradient)
        for colour in colours:
            self.assertGreaterEqual(luminance(colour), 0.8, colour)
        video = ''.join(rules_for(base, '.mq-video'))
        self.assertLessEqual(float(re.search(r'(?:^|;)opacity:([\d.]+)', video).group(1)), 0.25)
        # The rim is its own masked layer on the same --mqx (set once on the wrapper both inherit from).
        rim = ''.join(rules_for(base, '.mq-rim'))
        for prop in ('-webkit-mask', 'mask'):
            self.assertIn(f'{prop}:url("/assets/glass/marquee-type-rim.svg") var(--mqx) ', rim)
            self.assertIn(f'{prop}:url("/assets/glass/marquee-type.svg") var(--mqx) 50%/auto 100% repeat-x', fill[0])
        self.assertIn('--mqx:0px', rules_for(base, '.mq-word')[0])
        self.assertTrue((OUT / 'assets/glass/marquee-type-rim.svg').is_file())
        rim_svg = (OUT / 'assets/glass/marquee-type-rim.svg').read_text()
        self.assertIn('fill="none" stroke="#000"', rim_svg)
        self.assertEqual(re.search(r'viewBox="[^"]+"', rim_svg).group(0),
                         re.search(r'viewBox="[^"]+"', (OUT / 'assets/glass/marquee-type.svg').read_text()).group(0))
        # No filter on the moving type or its parent: nothing repaints a blur every frame.
        for selector in ('.mq-type', '.mq-word', '.mq-rim'):
            for rule in rules_for(self.home_css, selector):
                self.assertNotRegex(rule, r'(?:^|;)(?:-webkit-)?(?:backdrop-)?filter:', selector)
        self.assertIn('<div class="mq-word" aria-hidden="true"><div class="mq-rim"></div><div class="mq-type"><video class="mq-video"', self.home)
        js = (OUT / 'assets/home.js').read_text()
        self.assertIn("type = $('.mq-word')", js)
        self.assertIn("type.style.setProperty('--mqx'", js)

    def test_marquee_pills_ride_centred_on_their_tiles_in_one_strip(self):
        section = re.search(r'<section class="marq" aria-label="What we make">(.*?)</section>', self.home, re.S).group(1)
        self.assertIn('<p class="sr-only">New websites, redesigns and care plans.</p>', section)  # the words, once, for screen readers
        self.assertEqual(section.count('data-marquee'), 1)
        self.assertNotIn('mq-pills', section)
        self.assertNotIn('mq-pills', self.home_css)
        strip = re.search(r'<div class="mq-photos" data-marquee>(.*?)</div>', section, re.S).group(1)
        tiles = re.findall(r'<span class="mq-tile">(.*?)</span></span>', strip, re.S)
        self.assertEqual(len(tiles), 12)  # two identical runs of six, so the loop is seamless
        self.assertEqual(tiles[:6], tiles[6:])
        for tile in tiles:
            self.assertRegex(tile, r'^(?:<picture>.*?</picture>|<img [^>]*>)<span class="mq-pill lg">[^<]+$')
        self.assertEqual(section.count('class="mq-pill'), 12)
        base = base_rules(self.home_css)
        self.assertIn('position:relative', rules_for(base, '.mq-tile')[0])
        pill = rules_for(base, '.mq-tile .mq-pill')[0]
        for needle in ('position:absolute', 'left:50%', 'top:50%', 'transform:translate(-50%,-50%)', 'max-width:calc(100% - 24px)'):
            self.assertIn(needle, pill)

    def test_hero_name_leaves_cleanly(self):
        self.assertIn('export function heroPose(', self.scene)
        self.assertIn('wordOut(pose.word);', self.scene)
        out = self.scene.split('function wordOut(v) {', 1)[1].split('\n  }', 1)[0]
        for needle in ('wordPivot.visible = v > 0.001;', 'wordPivot.scale.setScalar(v);', 'wordBack.hm.material.opacity = v;', 'wordBack.sm.material.opacity = v;'):
            self.assertIn(needle, out)
        # The glass is never faded by opacity or switched to transparent (no recompile, no flicker).
        self.assertNotIn('transparent', out)
        self.assertNotIn('wordGlass', out)
        frame = self.scene.split('function frame(dt) {', 1)[1].split('\n  }', 1)[0]
        self.assertNotIn('transparent', frame)
        self.assertNotRegex(self.scene, r'wordGlass\.(?:transparent|opacity)\s*=')


class HeroFitPauseGripTests(unittest.TestCase):
    """Task 46 (owner-mandated): the hero tag never takes a click meant for a hero button and sits in the flow up to 1023px;
    short screens (150% zoom, landscape phones) and small phones get height-aware hero rules; the before/after picture is
    draggable, with the range input still the control, and its grip shows whole at both ends. These check that the rules
    exist, not how they render: the screenshots at the plan's viewports are an owner follow-up."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.home_js = (OUT / 'assets/home.js').read_text()
        cls.home = (OUT / 'index.html').read_text()

    def test_hero_tag_never_takes_clicks_and_follows_the_copy_up_to_1023px(self):
        self.assertIn('pointer-events:none', rules_for(base_rules(self.home_css), '.hero-cap')[0])
        tablet = media_blocks(self.home_css, 'max-width:1023px')
        self.assertIn('position:relative', rules_for(tablet, '.hero-cap')[0])
        # The pin is a column and grows to hold the tag, instead of clipping it at a fixed screen height.
        pin = rules_for(base_rules(self.home_css), '.hero-pin')[0]
        self.assertIn('display:flex', pin)
        self.assertIn('flex-direction:column', pin)
        self.assertIn('flex:1 0 auto', rules_for(base_rules(self.home_css), '.hero-in')[0])
        self.assertIn('height:auto', rules_for(tablet, '.hero-pin')[0])
        self.assertIn('min-height:100svh', rules_for(tablet, '.hero-pin')[0])
        hero = re.search(r'<section class="hero".*?</section>', self.home, re.S).group(0)
        self.assertLess(hero.index('See concept projects'), hero.index('<p class="hero-cap lg">'))

    def test_short_screens_size_the_hero_by_height(self):
        for query, top in (('min-width:761px) and (max-height:720px', 96), ('max-height:500px', 84)):
            with self.subTest(query=query):
                block = media_blocks(self.home_css, query)
                self.assertTrue(block)
                self.assertIn('height:auto', rules_for(block, '.hero-pin')[0])
                self.assertIn(f'padding-top:{top}px', rules_for(block, '.hero-in')[0])  # less than the 120px default
                size = rules_for(block, '.hero-h')[0]
                self.assertRegex(size, r'font-size:clamp\([\d.]+rem,[\d.]+svh,[\d.]+rem\)')  # scales with the height
                self.assertTrue(rules_for(block, '.hero .actions'))
        # Height rules come after the width rules, so they win where both apply.
        self.assertLess(self.home_css.index('@media(max-width:640px)'), self.home_css.index('@media(min-width:761px) and (max-height:720px)'))
        self.assertLess(self.home_css.index('@media(min-width:761px) and (max-height:720px)'), self.home_css.index('@media(max-height:500px)'))
        # Landscape phones use the wide poster (a real file) behind the copy.
        landscape = rules_for(media_blocks(self.home_css, 'max-height:500px'), '.hero-gl')[0]
        self.assertIn('url("/assets/glass/hero-glass-poster.jpg")', landscape)

    def test_small_phones_tighten_the_hero_so_both_buttons_fit(self):
        phone = media_blocks(self.home_css, 'max-width:640px')
        self.assertIn('padding-top:min(52svh,', rules_for(phone, '.hero-in')[0])  # never lower than before
        self.assertRegex(rules_for(phone, '.hero-h')[0], r'font-size:clamp\(2\.25rem,')
        self.assertIn('margin-top:18px', rules_for(phone, '.hero .actions')[0])

    def test_before_after_picture_is_draggable_and_its_grip_stays_whole(self):
        stage = rules_for(base_rules(self.home_css), '.compare-stage')[0]
        for needle in ('touch-action:pan-y', 'cursor:ew-resize', 'user-select:none'):
            self.assertIn(needle, stage)
        self.assertIn('pointer-events:none', rules_for(base_rules(self.home_css), '.compare-seam')[0])
        self.assertIn('left:var(--pos)', rules_for(base_rules(self.home_css), '.compare-seam')[0])  # the true seam
        grip = rules_for(base_rules(self.home_css), '.compare-stage::after')[0]
        self.assertIn('left:clamp(18px,var(--pos),calc(100% - 18px))', grip)
        self.assertIn('width:36px', grip)
        self.assertIn('pointer-events:none', grip)
        self.assertNotIn('.compare-seam::after', self.home_css)
        self.assertIn('pointer-events:none', rules_for(base_rules(self.home_css), '.mock')[0])  # no image drag, no selection
        # The range input is still the control: the drag writes its value and fires its input event.
        for needle in ("figure.querySelector('.compare-stage')", "range.dispatchEvent(new Event('input', { bubbles: true }))",
                       "stage.addEventListener('pointercancel', letGo)", 'setPointerCapture', 'releasePointerCapture'):
            self.assertIn(needle, self.home_js)
        self.assertIn('<input', main_of(self.home)[main_of(self.home).index('data-compare-controls'):])


class EnquiryRobustnessAndAccessTests(unittest.TestCase):
    """Task 47 (owner-mandated): the enquiry form never loses input silently, and six small accessibility fixes."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.contact = (OUT / 'contact/index.html').read_text()
        cls.site_css = (OUT / 'assets/site.css').read_text()
        cls.home_css = (OUT / 'assets/home.css').read_text()
        cls.pages_css = (OUT / 'assets/pages.css').read_text()

    def test_without_javascript_the_form_cannot_send_and_the_page_offers_email(self):
        main = main_of(self.contact)
        form = re.search(r'<form [^>]*data-enquiry[^>]*>', main).group(0)
        # POST stays (a native GET would put personal details in the URL); the button ships disabled, so neither a click
        # nor Enter in a field (implicit submission) can send the form until enquiry.js has attached its handler.
        self.assertIn('method="post"', form)
        self.assertNotIn('action=', form)
        self.assertEqual(re.findall(r'<button [^>]*type="submit"[^>]*>', main), ['<button class="button large" type="submit" disabled>'])
        notice = re.search(r'<noscript>(.*?)</noscript>', main, re.S)
        self.assertIsNotNone(notice)
        self.assertLess(main.index('<noscript>'), main.index('<form '))
        self.assertIn(MAIL_LINK, notice.group(1))
        self.assertIn('cannot send', notice.group(1))
        self.assertEqual(main.count('<noscript>'), 1)
        self.assertTrue(rules_for(base_rules(self.pages_css), '.ct-noscript'))
        # The disabled button only shows a "busy" cursor while a send is actually in progress.
        self.assertIn('cursor:not-allowed', rules_for(base_rules(self.site_css), '.button[disabled]')[0])
        self.assertIn('cursor:progress', rules_for(base_rules(self.site_css), '.form[aria-busy="true"] .button[disabled]')[0])

    def test_enquiry_script_enables_the_button_only_after_its_submit_handler(self):
        script = (ROOT / 'assets/enquiry.js').read_text()
        self.assertEqual(script.count('button.disabled = false;'), 2)  # after a send, and once at start-up
        self.assertLess(script.index("form.addEventListener('submit'"), script.rindex('if (button) button.disabled = false;'))
        self.assertNotIn('innerHTML', script)

    def test_export_button_has_solid_colours_with_enough_contrast(self):
        for selector in ('#export-demo', '#export-demo:hover'):
            with self.subTest(selector=selector):
                rule = rules_for(base_rules(self.site_css), selector)
                self.assertEqual(len(rule), 1)
                background = re.search(r'background:(#[0-9A-Fa-f]{6})(?:;|$)', rule[0])
                colour = re.search(r'(?:^|;)color:(#[0-9A-Fa-f]{6})(?:;|$)', rule[0])
                self.assertIsNotNone(background)
                self.assertIsNotNone(colour)
                self.assertGreaterEqual(contrast(background.group(1), colour.group(1)), 4.5)
        self.assertIn('backdrop-filter:none', rules_for(base_rules(self.site_css), '#export-demo')[0])
        self.assertIn('id="export-demo"', (OUT / 'demo/index.html').read_text())

    def test_date_input_keeps_a_visible_focus_ring_including_its_calendar_button(self):
        base = base_rules(self.site_css)
        for selector in ('input[type="date"]:focus-visible', 'input[type="date"]:focus-within',
                         'input[type="date"]::-webkit-calendar-picker-indicator:focus-visible'):
            with self.subTest(selector=selector):
                rule = rules_for(base, selector)
                self.assertEqual(len(rule), 1)
                self.assertRegex(rule[0], r'outline:2px solid var\(--ink\)')
        # The vendor pseudo-element sits in a rule of its own, so browsers that do not know it keep the other one.
        self.assertNotRegex(base, r'focus-within,input\[type="date"\]::-webkit')
        self.assertIn('<input name="date" type="date" required>', (OUT / 'demo/index.html').read_text())

    def test_home_project_titles_are_big_enough_to_tap_on_phones(self):
        phone = media_blocks(self.home_css, 'max-width:860px')
        rule = rules_for(phone, '.teaser-card h3 a')
        self.assertEqual(len(rule), 1)
        self.assertIn('display:inline-block', rule[0])
        self.assertGreaterEqual(int(re.search(r'min-height:(\d+)px', rule[0]).group(1)), 24)
        home = main_of((OUT / 'index.html').read_text())
        self.assertEqual(len(re.findall(r'<article class="teaser-card"[^>]*>.*?<h3 id="t\d-title"><a href="/work/#', home, re.S)), 3)

    def test_every_work_region_has_a_unique_name_that_includes_its_project(self):
        main = main_of((OUT / 'work/index.html').read_text())
        texts = {}
        for ident, body in re.findall(r'<h[1-6][^>]*\bid="([^"]+)"[^>]*>(.*?)</h[1-6]>', main, re.S):
            texts[ident] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', body)).replace('&amp;', '&').strip()
        names = []
        for tag, ids in re.findall(r'<(section|article|aside|nav|div)\b[^>]*\baria-labelledby="([^"]+)"', main):
            parts = ids.split()
            for ident in parts:
                with self.subTest(id=ident):
                    self.assertIn(f'id="{ident}"', main)
                    self.assertIn(ident, texts)
            names.append(' '.join(texts.get(ident, '') for ident in parts))
        self.assertGreaterEqual(len(names), 9)
        self.assertEqual(len(names), len(set(names)), names)
        for short, project in (('hb', 'Harbourside Mobile Detailing'), ('gl', 'Greenline Landscapes'), ('fc', 'Fade & Co')):
            for part in ('screens', 'brief', 'does'):
                with self.subTest(region=f'{short}-{part}'):
                    self.assertIn(f'aria-labelledby="{short}-title {short}-{part}"', main)
                    self.assertTrue(texts[f'{short}-title'].startswith(project))

    def test_menu_scroll_lock_applies_only_in_the_mobile_layout(self):
        css = re.sub(r'/\*.*?\*/', '', self.site_css, flags=re.S)
        self.assertNotIn('menu-lock', base_rules(css))
        mobile = media_blocks(css, 'max-width:1080px')
        self.assertIn('overflow:hidden', rules_for(mobile, 'html.menu-lock')[0])
        self.assertIn('overflow:hidden', rules_for(mobile, 'html.menu-lock body')[0])
        # The open menu scrolls inside itself, so short landscape screens can still reach its last link.
        self.assertIn('overflow-y:auto', rules_for(mobile, 'html.menu-lock .site-header .nav')[0])
        self.assertEqual(css.count('menu-lock'), 3)

    def test_reel_heading_and_paragraph_share_one_reveal_group(self):
        home = main_of((OUT / 'index.html').read_text())
        self.assertRegex(home, r'<div class="reel-head" data-rise-group><h2 id="reel-title" data-rise>[^<]+</h2><p id="reel-desc" data-rise>')
        self.assertRegex(home, r'<div class="work-head" data-rise-group><h2 id="work-title" data-rise>')


class PerformanceTask48Tests(unittest.TestCase):
    """Task 48 (performance): hero copy paints with the headline (never held at opacity 0), the /work/ Play button's space is
    kept before scripts run, the inner pages' WebGL never fetches the homepage scene or three's SVG helpers, and the glass
    nav pill's blur is never cut off by an ancestor. Behaviour (video timing, the WebGL test context, GSAP's ticker under
    Pause motion and reduced motion) is in tests/test_demo_js.py."""

    COPY = ('.pg-sub', '.hero-sub', '.hero .actions', '.pr-hero .pg-actions', '.wk-clip', '.chap-nav')
    # What makes an element a backdrop root (or its own composited layer) and so stops a descendant's backdrop-filter
    # from reaching the page behind it.
    BACKDROP_ROOT = re.compile(r'(?<![-\w])(?:filter|mask|mask-image|mask-border|-webkit-mask|will-change|contain|clip-path|'
                               r'mix-blend-mode|view-transition-name):|(?<![-\w])opacity:(?:0?\.\d+|0)(?![.\d])')

    @classmethod
    def setUpClass(cls):
        build()
        cls.css = {name: (OUT / 'assets' / name).read_text() for name in SHEETS}

    @staticmethod
    def rules(css):
        """(selector, body) for every rule, inside @media blocks too; comments removed."""
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
        return [(sel.strip(), body) for sel, body in re.findall(r'([^{}@]+)\{([^{}]*)\}', css)]

    def test_hero_copy_is_never_held_at_opacity_zero(self):
        for name in ('pages.css', 'home.css'):
            for selectors, body in self.rules(self.css[name]):
                if '.ph-wait' not in selectors or not any(part in selectors for part in self.COPY):
                    continue
                with self.subTest(css=name, selectors=selectors):
                    self.assertNotRegex(body, r'opacity:0(?![.\d])')
                    self.assertIn('transform:translateY(18px)', body)  # it still rises 18px into place
        for script in ('motion.js', 'home.js'):
            js = (OUT / 'assets' / script).read_text()
            with self.subTest(script=script):
                self.assertIn("tl.fromTo(fades, { y: 18 }, { y: 0, duration: 0.7, stagger: 0.08, clearProps: 'transform' }", js)
                self.assertNotIn('{ y: 18, opacity: 0 }', js)

    def test_work_play_button_space_is_kept_before_scripts_run(self):
        kit = self.css['kit.css']
        rules = dict(self.rules(kit))
        # An empty placeholder exactly the button's size (16px gap + 44px), only while scripts are on and the button hidden.
        self.assertEqual(rules['.js .clip-side:has(>.vt[hidden])::after'], 'content:"";display:block;height:44px;margin-top:16px')
        self.assertEqual(rules['.clip-side .vt'], 'display:flex;width:fit-content')  # block-level: no line box adds height
        vt = rules['.vt']
        self.assertIn('min-height:44px', vt)
        self.assertIn('margin-top:16px', vt)
        self.assertIn('*,*::before,*::after{box-sizing:border-box}', self.css['site.css'])
        work = main_of((OUT / 'work/index.html').read_text())
        self.assertRegex(work, r'<div class="clip-side">.*<button class="vt" type="button" data-reel-toggle hidden>Play three signs video</button></div>')
        for route in MOTION_ROUTES:
            with self.subTest(route=route):  # .js is set in <head>, before the first paint
                html = (OUT / route).read_text()
                self.assertLess(html.index('/assets/motion-boot.js'), html.index('</head>'))
        self.assertIn("c.add('js');", (OUT / 'assets/motion-boot.js').read_text())

    def test_inner_page_webgl_never_fetches_the_homepage_scene_or_svg_helpers(self):
        page = OUT / 'assets/glass-page.js'
        graph = [path.name for path in module_graph(page)]
        self.assertEqual(sorted(graph), ['glass-page.js', 'glass-shapes.js', 'three.module.min.js'])
        for name in ('glass-page.js', 'glass-shapes.js'):
            code = re.sub(r'/\*.*?\*/|^\s*//.*$', '', (OUT / 'assets' / name).read_text(), flags=re.S | re.M)  # code, not comments
            for banned in ('SVGLoader', 'BufferGeometryUtils', 'glass-scene', 'mergeGeometries', 'extrude('):
                with self.subTest(module=name, banned=banned):
                    self.assertNotIn(banned, code)
        self.assertNotIn('import(', page.read_text())  # nothing loaded later either
        boot = (OUT / 'assets/glass-boot.js').read_text()
        for kind in ('slab', 'panes', 'sheets', 'photos', 'mark'):
            self.assertIn(f"{kind}: '/assets/glass-page.js'", boot)
        # The homepage scene still has its wordmark helpers.
        self.assertIn('SVGLoader.js', [path.name for path in module_graph(OUT / 'assets/glass-scene.js')])

    def test_nav_backdrop_blur_is_plain_and_no_ancestor_cuts_it_off(self):
        glass_js = (OUT / 'assets/glass.js').read_text()
        # The edge refraction (an SVG url() filter) never reaches the nav pill: glass.js only maps .lg panels.
        self.assertIn("const REFRACT = '.lg';", glass_js)
        self.assertIn('const apply = () => $$(REFRACT).forEach(el => {', glass_js)
        self.assertEqual(glass_js.count('--lg-filter'), 1)
        self.assertNotIn('url(', rules_for(base_rules(self.css['glass.css']), '.site-header .nav')[0])
        # The nav's ancestors (.site-header, body, html) never become a backdrop root in any stylesheet, at any width.
        ancestor = re.compile(r'^(?:html|body|:root)(?:[.:\[][^\s>+~]*)?$|^\.site-header(?:[.:\[][^\s>+~]*)?$')
        checked = 0
        for name, css in self.css.items():
            for selectors, body in self.rules(css):
                for selector in [part.strip() for part in re.sub(r'\([^()]*\)', '()', selectors).split(',')]:
                    if '::' in selector or not ancestor.match(re.split(r'[\s>+~]+', selector)[-1]):
                        continue
                    checked += 1
                    with self.subTest(css=name, selector=selector):
                        self.assertNotRegex(body, self.BACKDROP_ROOT)
                        if name != 'site.css':  # site.css's old header blur is overridden by glass.css (loaded after it)
                            self.assertNotRegex(body, r'backdrop-filter:(?!none)')
        self.assertGreaterEqual(checked, 5)
        header = rules_for(base_rules(self.css['glass.css']), '.site-header')[0]
        self.assertIn('-webkit-backdrop-filter:none;backdrop-filter:none', header)
        # The page transition names the pill itself, never the header around it.
        self.assertIn('.site-header .nav{view-transition-name:site-header}', self.css['site.css'])
        self.assertNotIn('.site-header{view-transition-name', self.css['site.css'])
