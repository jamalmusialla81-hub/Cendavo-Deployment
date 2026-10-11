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
                self.assertIn('<a class="button small dark" href="/contact/">Request a consultation</a>', html)
        contact = (OUT / 'contact/index.html').read_text()
        self.assertIn('content="Request a website design, redesign or maintenance consultation with Cendavo in Sydney."', contact)

    def test_sitemap_points_at_real_project(self):
        sitemap = (OUT / 'sitemap.xml').read_text()
        self.assertIn('https://cendavo-deployment.pages.dev/demo/', sitemap)
        self.assertNotIn('https://cendavo.pages.dev', sitemap)


if __name__ == '__main__':
    unittest.main()
