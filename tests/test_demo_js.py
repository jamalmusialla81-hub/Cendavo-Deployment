import json
import shutil
import subprocess
import unittest
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / 'assets' / 'demo.js'
HOME = Path(__file__).resolve().parents[1] / 'assets' / 'home.js'

# Runs assets/home.js against a minimal DOM stub, first without GSAP (it must still work) and then with a
# recording GSAP stub (motion must be registered only under the reduced-motion guard).
HOME_SCRIPT = r"""
const vm = require('vm');
const source = require('fs').readFileSync(process.argv[1], 'utf8');
function element() {
  return { attrs: {}, dataset: {}, listeners: {}, hidden: false, value: '50',
    style: { props: {}, setProperty(name, value) { this.props[name] = value; } },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    addEventListener(type, fn) { this.listeners[type] = fn; } };
}
function run(gsap, reduce) {
  const range = element(), before = element(), after = element(), controls = element(), figure = element();
  before.dataset.compareSet = '0'; after.dataset.compareSet = '100'; controls.hidden = true;
  controls.querySelector = s => s === 'input[type="range"]' ? range : null;
  controls.querySelectorAll = () => [before, after];
  figure.querySelector = s => s === '[data-compare-controls]' ? controls : null;
  const window = { matchMedia: () => ({ matches: reduce }) };
  if (gsap) { window.gsap = gsap; window.ScrollTrigger = {}; }
  vm.runInNewContext(source, { window, document: { querySelector: s => s === '[data-compare]' ? figure : null } });
  const snap = () => ({ pos: figure.style.props['--pos'], before: before.attrs['aria-pressed'], after: after.attrs['aria-pressed'], text: range.attrs['aria-valuetext'] });
  const out = { shown: controls.hidden === false, initial: snap() };
  range.value = '0'; range.listeners.input(); out.input = snap();
  after.listeners.click(); out.click = { ...snap(), value: String(range.value) };
  return out;
}
const calls = { queries: [], from: [], to: 0, plugins: 0 };
const gsap = {
  registerPlugin() { calls.plugins++; },
  matchMedia() { return { add(query, fn) { calls.queries.push(query); fn(); } }; },
  from(target, vars) { calls.from.push([typeof target === 'string' ? target : 'element', Boolean(vars.scrollTrigger)]); },
  to(state, vars) { calls.to++; state.v = vars.v; vars.onUpdate(); return { kill() {} }; },
  utils: { toArray: () => ['h2'] },
};
console.log(JSON.stringify({ plain: run(null, false), motion: run(gsap, false), calls }));
"""

SCRIPT = r"""
const {normaliseItems, buildDraft, friendlyDate, isIsoDate, attentionLabel, visibleItems, normaliseFilter, toCsv, seed} = require(process.argv[1]);
const good = {id:'a',name:'Pat',service:'Cleaning',date:'2026-10-14',note:'x',status:'Done',created:'2026-10-01'};
console.log(JSON.stringify({
  nonArray: normaliseItems({}).length === seed.length,
  nullInput: normaliseItems(null).length === seed.length,
  mixed: normaliseItems([null, 5, {id:'b',name:'X'}, {...good,id:'c',status:'Bogus'}, good]).map(i => i.id),
  allBad: normaliseItems([{}]).map(i => i.id),
  badDate: normaliseItems([{...good, date:'nope'}])[0].date,
  normal: buildDraft(good),
  noDate: buildDraft({...good, date:''}),
  script: buildDraft({...good, name:'<script>alert(1)</script>'}),
  empty: buildDraft(undefined),
  clauses: Object.fromEntries(['Alteration','Cleaning','Laundry','Repair','Other'].map(s => [s, buildDraft({...good, service:s})])),
  unknownService: buildDraft({...good, service:'<script>x</script>'}),
  protoService: buildDraft({...good, service:'constructor'}),
  feb31: isIsoDate('2026-02-31'),
  leapOk: isIsoDate('2028-02-29'),
  leapBad: isIsoDate('2027-02-29'),
  y1: friendlyDate('2026-10-14'),
  y2: friendlyDate('2037-10-14'),
  attn: ['2026-10-11', '2026-10-10', '2026-10-12', ''].map(d => attentionLabel({...good, status:'New', date:d}, '2026-10-11')),
  attnDone: attentionLabel({...good, date:'2026-10-01'}, '2026-10-11'),
  attnBadToday: attentionLabel({...good, status:'New'}, 'x'),
  filt: normaliseFilter('Bogus') + normaliseFilter('Done') + normaliseFilter(undefined),
  order: visibleItems([
    {...good, id:'d', status:'Done', date:'2026-10-01'},
    {...good, id:'n', status:'New', date:''},
    {...good, id:'f', status:'Follow-up', date:'2026-10-20'},
    {...good, id:'e', status:'New', date:'2026-10-12'},
  ], 'All').map(i => i.id),
  onlyDone: visibleItems([good, {...good, id:'z', status:'New'}], 'Done').map(i => i.id),
  unknownFilter: visibleItems([good, {...good, id:'z', status:'New'}], 'Bogus').length,
  notArray: visibleItems(null, 'All').length,
  seedRoundTrip: JSON.stringify(normaliseItems(JSON.parse(JSON.stringify(seed)))) === JSON.stringify(seed),
  seedStatuses: seed.map(i => i.status),
  seedPastOpen: seed.filter(i => i.status !== 'Done' && attentionLabel(i, '2026-10-11')).length,
  seedClauses: seed.map(i => buildDraft(i).includes('Could you')),
  csvSeed: toCsv(seed),
  csvSeedUnchanged: (() => { const copy = structuredClone(seed); toCsv(copy); return JSON.stringify(copy) === JSON.stringify(seed); })(),
  csvNonArray: [toCsv(null), toCsv({}), toCsv('x')],
  csvTricky: toCsv([{...good, name:'Pat "PJ" Doe', note:'Line one, with comma\nLine "two"'}]),
  csvTriggers: ['=1+1', '+61 400', '-5', '@SUM(A1)', '\tTab', '\rCR', 'Plain', 'a=b'].map(v => toCsv([{...good, note:v}]).split('\r\n')[1]),
  csvSkipsJunk: toCsv([null, 5, good]),
}));
"""


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class DemoScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(['node', '-e', SCRIPT, str(DEMO)], capture_output=True, text=True, check=True)
        cls.r = json.loads(out.stdout)

    def test_non_array_falls_back_to_seed(self):
        self.assertTrue(self.r['nonArray'])
        self.assertTrue(self.r['nullInput'])

    def test_malformed_entries_and_bad_status_dropped(self):
        self.assertEqual(self.r['mixed'], ['a'])
        self.assertEqual(self.r['allBad'], ['sample-1', 'sample-2', 'sample-3', 'sample-4'])
        self.assertEqual(self.r['badDate'], '')

    def test_draft_is_friendly_and_marked_draft(self):
        self.assertRegex(self.r['normal'], r'Wed,? 14 Oct')
        self.assertNotIn('2026-10-14', self.r['normal'])
        self.assertIn('draft only', self.r['normal'])

    def test_draft_is_service_specific(self):
        expected = {
            'Alteration': 'photo of the item',
            'Cleaning': 'bedrooms and bathrooms',
            'Laundry': 'items or bags',
            'Repair': 'photo of the damage',
            'Other': 'a little more about what you need',
        }
        for service, text in expected.items():
            draft = self.r['clauses'][service]
            self.assertIn(text, draft)
            self.assertIn('draft only', draft)
            for other, other_text in expected.items():
                if other != service:
                    self.assertNotIn(other_text, draft)

    def test_seed_is_valid_and_covers_statuses(self):
        self.assertTrue(self.r['seedRoundTrip'])
        self.assertEqual(set(self.r['seedStatuses']), {'New', 'Follow-up', 'Done'})
        self.assertGreaterEqual(self.r['seedPastOpen'], 1)
        self.assertTrue(all(self.r['seedClauses']))

    def test_other_service_option_value_matches_clause_key(self):
        html = (DEMO.parents[1] / 'pages' / 'demo.html').read_text(encoding='utf-8')
        self.assertIn('<option value="Other">Other service</option>', html)
        self.assertNotIn('<option>Other service</option>', html)

    def test_unknown_service_uses_generic_draft(self):
        for key in ('unknownService', 'protoService'):
            draft = self.r[key]
            self.assertIn('draft only', draft)
            self.assertIn('Please let us know what time works', draft)
            for text in ('photo of', 'bedrooms', 'items or bags', 'a little more'):
                self.assertNotIn(text, draft)
        self.assertIn('<script>x</script>', self.r['unknownService'])

    def test_dates_are_real_calendar_dates_and_show_year(self):
        self.assertFalse(self.r['feb31'])
        self.assertTrue(self.r['leapOk'])
        self.assertFalse(self.r['leapBad'])
        self.assertIn('2026', self.r['y1'])
        self.assertNotEqual(self.r['y1'], self.r['y2'])

    def test_draft_handles_missing_date_and_plain_text(self):
        self.assertIn('what date and time work', self.r['noDate'])
        self.assertIn('<script>alert(1)</script>', self.r['script'])
        self.assertIn('Draft reply', self.r['empty'])

    def test_attention_label_is_text_and_ignores_done(self):
        self.assertEqual(self.r['attn'], ['Due today', 'Date passed', '', ''])
        self.assertEqual(self.r['attnDone'], '')
        self.assertEqual(self.r['attnBadToday'], '')

    def test_filter_and_sort(self):
        self.assertEqual(self.r['filt'], 'AllDoneAll')
        self.assertEqual(self.r['order'], ['e', 'f', 'n', 'd'])
        self.assertEqual(self.r['onlyDone'], ['a'])
        self.assertEqual(self.r['unknownFilter'], 2)
        self.assertEqual(self.r['notArray'], 0)


    CSV_HEADER = 'Name,Service,Preferred date,Status,Request detail,Created'

    def test_csv_header_bom_and_line_endings(self):
        csv = self.r['csvSeed']
        self.assertTrue(csv.startswith('﻿' + self.CSV_HEADER + '\r\n'))
        self.assertTrue(csv.endswith('\r\n'))
        self.assertNotIn('sample-1', csv)
        self.assertNotRegex(csv.replace('\r\n', ''), '\n')

    def test_csv_exports_all_seed_items_in_stored_order(self):
        lines = self.r['csvSeed'][1:].split('\r\n')
        self.assertEqual(lines[-1], '')
        self.assertEqual(len(lines[:-1]), 5)
        self.assertEqual(lines[1], '"Alex Morgan","Alteration","2026-10-14","New","Hem two pairs of trousers","2026-10-10"')
        self.assertTrue(lines[2].startswith('"Sam Lee"'))
        self.assertTrue(lines[4].startswith('"Casey Nguyen"'))
        self.assertIn('"Done"', lines[4])
        self.assertTrue(self.r['csvSeedUnchanged'])

    def test_csv_non_array_gives_header_only(self):
        for csv in self.r['csvNonArray']:
            self.assertEqual(csv, '﻿' + self.CSV_HEADER + '\r\n')

    def test_csv_quotes_commas_quotes_and_newlines(self):
        row = self.r['csvTricky'][1:].split('\r\n', 1)[1]
        self.assertEqual(row, '"Pat ""PJ"" Doe","Cleaning","2026-10-14","Done","Line one, with comma\nLine ""two""","2026-10-01"\r\n')

    def test_csv_neutralises_formula_triggers(self):
        notes = [row.split('","')[4] for row in self.r['csvTriggers']]
        self.assertEqual(notes, ["'=1+1", "'+61 400", "'-5", "'@SUM(A1)", "'\tTab", "'\rCR", 'Plain', 'a=b'])
        for row in self.r['csvTriggers']:
            self.assertTrue(row.startswith('"Pat","Cleaning"'))

    def test_csv_skips_non_object_entries(self):
        self.assertEqual(len(self.r['csvSkipsJunk'].split('\r\n')), 3)

    def test_home_js_compare_works_without_gsap_and_guards_motion(self):
        out = subprocess.run(['node', '-e', HOME_SCRIPT, str(HOME)], capture_output=True, text=True, check=True)
        r = json.loads(out.stdout)
        plain = r['plain']
        self.assertTrue(plain['shown'])  # controls are revealed by JS
        self.assertEqual(plain['initial'], {'pos': '50%', 'before': 'false', 'after': 'false', 'text': '50 of 100 showing the redesign'})
        self.assertEqual(plain['input'], {'pos': '0%', 'before': 'true', 'after': 'false', 'text': 'Before only'})
        self.assertEqual(plain['click'], {'pos': '100%', 'before': 'false', 'after': 'true', 'text': 'After only', 'value': '100'})
        # With GSAP the buttons glide via a tween but end in the same state.
        self.assertEqual(r['motion']['click'], plain['click'])
        calls = r['calls']
        self.assertEqual(calls['to'], 1)
        self.assertEqual(calls['plugins'], 1)
        self.assertEqual(calls['queries'], ['(prefers-reduced-motion: no-preference)'])
        self.assertEqual(calls['from'], [['.hero-h .ln > span', False], ['[data-hero-fade]', False], ['h2', True]])

    def test_demo_js_makes_no_network_requests(self):
        js = DEMO.read_text(encoding='utf-8')
        for token in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'EventSource', 'http://', 'https://'):
            self.assertNotIn(token, js)


if __name__ == '__main__':
    unittest.main()
