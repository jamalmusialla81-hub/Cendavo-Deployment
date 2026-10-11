import json
import shutil
import subprocess
import unittest
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / 'assets' / 'demo.js'
HOME = Path(__file__).resolve().parents[1] / 'assets' / 'home.js'

BOOT = Path(__file__).resolve().parents[1] / 'assets' / 'motion-boot.js'
MOTION = Path(__file__).resolve().parents[1] / 'assets' / 'motion.js'

# Shared Node harness: a tiny DOM stub, a media-query evaluator and a recording GSAP stub. The GSAP stub records each
# tween's position and end (position + duration + stagger * (targets - 1)) so timeline lengths can be checked.
HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
function classList(initial) {
  const set = new Set(initial || []);
  return { set, add: c => set.add(c), remove: c => set.delete(c), contains: c => set.has(c), toggle: (c, on) => (on ? set.add(c) : set.delete(c)) };
}
function element(name, parts) {
  const el = { name, parts: parts || {}, attrs: {}, dataset: {}, listeners: {}, hidden: false, value: '50', children: [],
    classList: classList(), textContent: '', open: false, tagName: 'DIV',
    style: { props: {}, setProperty(key, value) { this.props[key] = value; } },
    setAttribute(key, value) { this.attrs[key] = String(value); },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter(f => f !== fn); },
    querySelectorAll(selector) { return el.parts[selector] || []; },
    querySelector(selector) { return (el.parts[selector] || [])[0] || null; },
    contains(other) { return other === el || Object.values(el.parts).some(list => list.some(child => child === other || (child.contains && child !== el && child.contains(other)))); },
    getBoundingClientRect() { return { left: 100, top: 100, width: 200, height: 52 }; },
  };
  return el;
}
const many = (name, count) => Array.from({ length: count }, (_, i) => element(name + i));
function media(query, env) {
  return query.split(', ').some(alternative => alternative.split(' and ').every(feature => {
    const m = feature.match(/^\((.+?): (.+)\)$/);
    if (!m) throw new Error('unparsed media feature ' + feature);
    const [, key, value] = m;
    const n = parseFloat(value);
    switch (key) {
      case 'prefers-reduced-motion': return value === 'reduce' ? env.reduce : !env.reduce;
      case 'min-width': return env.width >= n;
      case 'max-width': return env.width <= n;
      case 'min-height': return env.height >= n;
      case 'max-height': return env.height <= n;
      case 'hover': return env.fine;
      case 'pointer': return env.fine;
      default: throw new Error('unknown media feature ' + key);
    }
  }));
}
function makeGsap(env) {
  const log = { queries: [], timelines: [], tweens: [], sets: [], quick: [], plugins: 0, batches: 0, varsSeen: [] };
  const count = targets => (Array.isArray(targets) ? targets.length : 1);
  const record = (owner, kind, targets, vars, position) => {
    log.varsSeen.push(vars);
    const at = position === undefined ? owner.cursor : position;
    const end = at + (vars.duration === undefined ? 0.5 : vars.duration) + (vars.stagger || 0) * (count(targets) - 1);
    const tween = { kind, at, end, n: count(targets), vars };
    owner.tweens.push(tween);
    owner.cursor = end;
    return tween;
  };
  const gsap = {
    registerPlugin() { log.plugins++; },
    matchMedia() { return { add(query, fn) { log.queries.push(query); if (media(query, env)) fn(); } }; },
    timeline(vars) {
      const tl = { vars: vars || {}, tweens: [], labels: {}, cursor: 0, callbacks: [], played: [], progressed: [],
        scrollTrigger: vars && vars.scrollTrigger ? { start: 1000, end: 1000 + 2 * env.height } : undefined,
        from(t, v, p) { record(tl, 'from', t, v, p); return tl; },
        to(t, v, p) { record(tl, 'to', t, v, p); return tl; },
        fromTo(t, a, v, p) { log.varsSeen.push(a); record(tl, 'fromTo', t, v, p); return tl; },
        add(fn, p) { tl.callbacks.push({ fn, at: p }); tl.cursor = Math.max(tl.cursor, p); return tl; },
        addLabel(name, p) { tl.labels[name] = p; return tl; },
        play(at) { tl.played.push(at); return tl; },
        progress(v) { tl.progressed.push(v); if (v === 1) { tl.callbacks.forEach(c => c.fn()); if (tl.vars.onComplete) tl.vars.onComplete(); } return tl; },
        duration() { return Math.max(0, ...tl.tweens.map(t => t.end), ...tl.callbacks.map(c => c.at)); },
      };
      if (vars) log.varsSeen.push(vars);
      log.timelines.push(tl);
      return tl;
    },
    from(t, v) { log.varsSeen.push(v); log.tweens.push({ kind: 'from', vars: v }); },
    fromTo(t, a, v) { log.varsSeen.push(a, v); log.tweens.push({ kind: 'fromTo', vars: v }); },
    to(state, v) { log.varsSeen.push(v); log.tweens.push({ kind: 'to', vars: v }); if ('v' in v) { state.v = v.v; v.onUpdate(); } return { kill() {} }; },
    set(t, v) { log.varsSeen.push(v); log.sets.push(v); },
    quickTo(target, prop) { return value => log.quick.push([prop, value]); },
  };
  const ScrollTrigger = { batch() { log.batches++; } };
  return { gsap, ScrollTrigger, log };
}
function makeWindow(env, extra) {
  const listeners = {};
  const store = env.storage || {};
  const win = Object.assign({
    innerHeight: env.height, innerWidth: env.width, scrolled: [],
    matchMedia: query => ({ matches: media(query, env) }),
    addEventListener(type, fn, options) { (listeners[type] = listeners[type] || []).push({ fn, options }); },
    removeEventListener(type, fn) { listeners[type] = (listeners[type] || []).filter(l => l.fn !== fn); },
    scrollTo(x, y) { win.scrolled.push(y); },
    performance: { now: () => env.now || 0 },
    sessionStorage: env.storageThrows
      ? { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } }
      : { getItem: key => (key in store ? store[key] : null), setItem: (key, value) => { store[key] = String(value); } },
    location: { hash: env.hash || '' },
  }, extra || {});
  return { win, listeners, store };
}
"""

# Runs assets/home.js against the stub DOM: without GSAP (it must still work and end the intro) and with the recording
# GSAP stub in several situations (first visit, skipped intro, late scripts, no intro, reduced motion, small screens).
HOME_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const range = element('range'), before = element('before'), after = element('after'), controls = element('controls');
  const figure = element('figure');
  before.dataset.compareSet = '0'; after.dataset.compareSet = '100'; controls.hidden = true;
  controls.parts = { 'input[type="range"]': [range], '[data-compare-set]': [before, after] };
  figure.parts = { '[data-compare-controls]': [controls] };
  const intro = element('intro', { '.intro-mark path': many('arc', 3), '.intro-word > span': many('word', 1) });
  const photo = element('photo', { img: many('img', 1) });
  const projects = [0, 1, 2].map(i => element('proj' + i, { '.proj-copy > *': many('copy', 4), '.proj-devices': many('devices', 1), '.proj-media': many('media', 1), '.proj-media img': many('mimg', 1) }));
  const counter = element('counter'), bar = element('bar');
  const stage = element('stage', { '.proj': projects, '.work-count-n': [counter], '.work-count-bar i': [bar] });
  const root = element('html'); root.classList = classList(env.introClass ? ['js', 'motion', 'ns-intro'] : ['js']);
  const parts = { '[data-compare]': [figure], '.intro': env.noPanel ? [] : [intro], '.hero-h .ln > span': many('line', 4), '.hero-photo': [photo],
    '[data-hero-fade]': many('fade', 2), '.hero-device': many('device', 1), '[data-work]': [stage], '.proj': projects };
  const doc = { documentElement: root, querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const { win, listeners, store } = makeWindow(env);
  let log = null;
  if (env.gsap) { const stub = makeGsap(env); win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; log = stub.log; }
  vm.runInNewContext(source, { window: win, document: doc });
  const snap = () => ({ pos: figure.style.props['--pos'], before: before.attrs['aria-pressed'], after: after.attrs['aria-pressed'], text: range.attrs['aria-valuetext'] });
  const out = { shown: controls.hidden === false, initial: snap(), classes: Array.from(root.classList.set).sort(), flag: store['cendavo-intro'] || null };
  out.skipListeners = Object.fromEntries(['keydown', 'pointerdown', 'wheel', 'touchstart'].map(t => [t, (listeners[t] || []).map(l => Boolean(l.options && l.options.passive))]));
  if (log) {
    const [first] = log.timelines;
    const introTl = log.timelines.find(tl => tl.vars.onComplete);
    const hero = log.timelines.find(tl => tl.vars.paused);
    const pin = log.timelines.find(tl => tl.vars.scrollTrigger && tl.vars.scrollTrigger.pin);
    out.queries = log.queries;
    out.plugins = log.plugins;
    out.introEnd = introTl ? introTl.duration() : null;
    out.heroAt = introTl ? introTl.callbacks.map(c => c.at) : [];
    out.heroEnd = hero ? hero.duration() : null;
    out.heroPlayed = hero ? hero.played.slice() : null;
    out.heroOpacityOnly = hero ? hero.tweens.every(t => !('autoAlpha' in t.vars) && !('visibility' in t.vars)) : null;
    out.autoAlpha = log.varsSeen.some(v => v && ('autoAlpha' in v || 'visibility' in v));
    out.snap = log.varsSeen.some(v => v && v.scrollTrigger && 'snap' in v.scrollTrigger);
    out.pinned = stage.classList.contains('is-pinned');
    out.stackTimelines = log.timelines.filter(tl => tl.vars.scrollTrigger && tl.vars.scrollTrigger.once).length;
    if (pin) {
      out.pinEnd = pin.vars.scrollTrigger.end();
      out.pinScrub = pin.vars.scrollTrigger.scrub;
      out.focusListeners = (stage.listeners.focusin || []).length;
      const target = many('link', 1)[0];
      projects[2].parts.link = [target];
      stage.listeners.focusin[0]({ target });
      out.focusScroll = win.scrolled.slice();
      pin.vars.scrollTrigger.onUpdate({ progress: 1 });
      out.counter = counter.textContent;
    }
    if (env.skipWith) {
      let prevented = false;
      const event = { type: env.skipWith, key: 'a', preventDefault() { prevented = true; } };
      (listeners[env.skipWith] || []).slice().forEach(l => l.fn(event));
      out.afterSkip = { prevented, classes: Array.from(root.classList.set).sort(), flag: store['cendavo-intro'] || null,
        introProgress: introTl ? introTl.progressed : null, heroProgress: hero ? hero.progressed : null,
        listenersLeft: ['keydown', 'pointerdown', 'wheel', 'touchstart'].reduce((n, t) => n + (listeners[t] || []).length, 0) };
    }
  }
  range.value = '0'; range.listeners.input[0](); out.input = snap();
  after.listeners.click[0](); out.click = { ...snap(), value: String(range.value) };
  out.tweensTo = log ? log.tweens.filter(t => t.kind === 'to').length : 0;
  return out;
}
const desktop = { width: 1440, height: 900, fine: true, reduce: false };
console.log(JSON.stringify({
  plain: run({ ...desktop, introClass: true }),
  first: run({ ...desktop, gsap: true, introClass: true, now: 120, skipWith: 'keydown' }),
  pointer: run({ ...desktop, gsap: true, introClass: true, now: 120, skipWith: 'pointerdown' }),
  late: run({ ...desktop, gsap: true, introClass: true, now: 1500 }),
  noIntro: run({ ...desktop, gsap: true, introClass: false }),
  reduced: run({ ...desktop, gsap: true, introClass: true, reduce: true }),
  phone: run({ width: 390, height: 844, fine: false, reduce: false, gsap: true, introClass: false }),
}));
"""

# Runs assets/motion-boot.js with stubbed document, matchMedia, location, sessionStorage and setTimeout.
BOOT_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function boot(env) {
  const root = element('html'); root.classList = classList();
  const timers = [];
  const script = { hasAttribute: name => (env.attrs || []).includes(name) };
  const { win, store } = makeWindow(env, { setTimeout: (fn, ms) => timers.push({ fn, ms }) });
  if (env.noMatchMedia) delete win.matchMedia;
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: { documentElement: root, currentScript: script } }); } catch (e) { error = String(e); }
  const out = { error, classes: Array.from(root.classList.set).sort(), timers: timers.map(t => t.ms), flag: store['cendavo-intro'] || null };
  timers.forEach(t => t.fn());
  out.afterTimers = Array.from(root.classList.set).sort();
  return out;
}
const home = { width: 1440, height: 900, reduce: false, attrs: ['data-intro'] };
console.log(JSON.stringify({
  first: boot(home),
  reduced: boot({ ...home, reduce: true }),
  hash: boot({ ...home, hash: '#work' }),
  seen: boot({ ...home, storage: { 'cendavo-intro': '1' } }),
  throws: boot({ ...home, storageThrows: true }),
  inner: boot({ ...home, attrs: [] }),
  noMatchMedia: boot({ ...home, noMatchMedia: true }),
}));
"""

# Runs assets/motion.js: the services highlight works without GSAP; with GSAP the magnetic pull is clamped, the FAQ
# answer fade never cancels the native toggle and nothing hides content with visibility.
MOTION_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const list = element('list');
  const rows = many('svc', 3).map(row => { row.parentNode = list; return row; });
  const button = element('go');
  const summary = element('summary'); summary.tagName = 'SUMMARY';
  const answer = element('answer'); answer.tagName = 'P';
  const details = element('details'); details.children = [summary, answer];
  const parts = { '.svc': rows, '.button.go': [button], details: [details], '[data-rise]': many('rise', 2), '[data-reveal]': many('reveal', 2),
    '[data-parallax]': [element('frame', { img: many('pimg', 1) })], '[data-ph]': [element('head', { h1: many('h1', 1), '[data-ph-fade]': many('phf', 2), '[data-ph-media]': [element('phm', { img: many('phmimg', 1) })] })],
    '[data-devices]': many('dev', 1) };
  const doc = { querySelectorAll: s => parts[s] || [], querySelector: s => (parts[s] || [])[0] || null };
  const { win } = makeWindow(env);
  let log = null;
  if (env.gsap) { const stub = makeGsap(env); win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; log = stub.log; }
  vm.runInNewContext(source, { window: win, document: doc });
  const out = { live: list.classList.contains('is-live'), active: rows.map(r => r.classList.contains('is-active')) };
  rows[2].listeners.mouseenter[0](); out.afterHover = rows.map(r => r.classList.contains('is-active'));
  rows[1].listeners.focusin[0](); out.afterFocus = rows.map(r => r.classList.contains('is-active'));
  if (log) {
    out.queries = log.queries;
    out.batches = log.batches;
    out.visibility = log.varsSeen.some(v => v && ('autoAlpha' in v || 'visibility' in v));
    (button.listeners.pointermove || []).forEach(fn => fn({ clientX: 5000, clientY: -5000 }));
    out.pull = log.quick.map(([, value]) => value);
    let prevented = false;
    details.open = true;
    (details.listeners.toggle || []).forEach(fn => fn({ currentTarget: details, preventDefault() { prevented = true; } }));
    out.faq = { prevented, tweens: log.tweens.filter(t => t.kind === 'fromTo' && 'opacity' in t.vars).length };
  }
  return out;
}
console.log(JSON.stringify({
  plain: run({ width: 1440, height: 900, fine: true, reduce: false }),
  desktop: run({ width: 1440, height: 900, fine: true, reduce: false, gsap: true }),
  touch: run({ width: 390, height: 844, fine: false, reduce: false, gsap: true }),
  reduced: run({ width: 1440, height: 900, fine: true, reduce: true, gsap: true }),
}));
"""

SCRIPT = r"""
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

    def node_json(self, script, path):
        out = subprocess.run(['node', '-e', script, str(path)], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_home_js_compare_works_without_gsap_and_guards_motion(self):
        r = self.node_json(HOME_SCRIPT, HOME)
        plain = r['plain']
        self.assertTrue(plain['shown'])  # controls are revealed by JS
        self.assertEqual(plain['initial'], {'pos': '50%', 'before': 'false', 'after': 'false', 'text': '50 of 100 showing the redesign'})
        self.assertEqual(plain['input'], {'pos': '0%', 'before': 'true', 'after': 'false', 'text': 'Before only'})
        self.assertEqual(plain['click'], {'pos': '100%', 'before': 'false', 'after': 'true', 'text': 'After only', 'value': '100'})
        # Without GSAP the intro ends at once and is remembered for the session; no skip listeners are left behind.
        self.assertNotIn('ns-intro', plain['classes'])
        self.assertEqual(plain['flag'], '1')
        self.assertEqual(plain['skipListeners'], {'keydown': [], 'pointerdown': [], 'wheel': [], 'touchstart': []})
        # With GSAP the buttons glide via a tween but end in the same state.
        for name in ('first', 'noIntro', 'reduced', 'phone'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['click'], plain['click'])
                self.assertFalse(r[name]['autoAlpha'])
                self.assertFalse(r[name]['snap'])
        self.assertEqual(r['noIntro']['tweensTo'], 1)
        self.assertEqual(r['reduced']['tweensTo'], 0)  # reduced motion: the divider jumps
        self.assertEqual(r['first']['plugins'], 1)
        # Every motion query sits behind the reduced-motion guard (or is the reduced-motion branch itself).
        queries = r['first']['queries']
        self.assertIn('(prefers-reduced-motion: no-preference)', queries)
        for query in queries:
            with self.subTest(query=query):
                self.assertTrue(all('prefers-reduced-motion' in part for part in query.split(', ')))
        # Reduced motion: nothing is animated, the intro ends and nothing is pinned.
        reduced = r['reduced']
        self.assertIsNone(reduced['heroEnd'])
        self.assertIsNone(reduced['introEnd'])
        self.assertNotIn('ns-intro', reduced['classes'])
        self.assertFalse(reduced['pinned'])

    def test_home_intro_and_hero_stay_within_their_time_limits(self):
        r = self.node_json(HOME_SCRIPT, HOME)
        first = r['first']
        self.assertIsNotNone(first['introEnd'])
        self.assertLessEqual(first['introEnd'], 1.8)
        self.assertLessEqual(first['heroEnd'], 1.2)
        self.assertTrue(first['heroOpacityOnly'])
        # The hero starts while the panel is still wiping away, before the intro ends.
        self.assertEqual(len(first['heroAt']), 1)
        self.assertLess(first['heroAt'][0], first['introEnd'])
        self.assertEqual(first['heroPlayed'], [])
        # No intro: the hero plays at once (and still within 1.2 s).
        for name in ('noIntro', 'late'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['heroPlayed'], [0])
                self.assertLessEqual(r[name]['heroEnd'], 1.2)
                self.assertIsNone(r[name]['introEnd'])
                self.assertNotIn('ns-intro', r[name]['classes'])
        # Scripts that arrive late skip the intro instead of starting one the 2.5 s failsafe would cut off.
        self.assertEqual(r['late']['skipListeners'], {'keydown': [], 'pointerdown': [], 'wheel': [], 'touchstart': []})

    def test_home_intro_is_skipped_by_any_input_without_swallowing_it(self):
        r = self.node_json(HOME_SCRIPT, HOME)
        first = r['first']
        # One passive listener per kind of input while the intro runs.
        self.assertEqual(first['skipListeners'], {'keydown': [True], 'pointerdown': [True], 'wheel': [True], 'touchstart': [True]})
        self.assertIn('ns-intro', first['classes'])
        for name in ('first', 'pointer'):
            with self.subTest(case=name):
                after = r[name]['afterSkip']
                self.assertFalse(after['prevented'])  # the key or click still reaches the page
                self.assertNotIn('ns-intro', after['classes'])
                self.assertEqual(after['flag'], '1')
                self.assertIn(1, after['introProgress'])
                self.assertIn(1, after['heroProgress'])  # the hero jumps to its final state
                self.assertEqual(after['listenersLeft'], 0)

    def test_home_projects_pin_is_capped_and_follows_focus(self):
        r = self.node_json(HOME_SCRIPT, HOME)
        first = r['first']
        self.assertTrue(first['pinned'])
        self.assertEqual(first['pinEnd'], '+=' + str(900 * 2))  # two viewport heights at most
        self.assertIsInstance(first['pinScrub'], (int, float))
        self.assertEqual(first['focusListeners'], 1)
        # Focus inside the third project scrolls to where that project is fully shown, within the pinned range.
        self.assertEqual(len(first['focusScroll']), 1)
        self.assertGreater(first['focusScroll'][0], 1000)
        self.assertLessEqual(first['focusScroll'][0], 1000 + 2 * 900)
        self.assertEqual(first['counter'], '3')
        # Phones: no pin, stacked reveals that run once per project.
        phone = r['phone']
        self.assertFalse(phone['pinned'])
        self.assertIsNone(phone.get('pinEnd'))
        self.assertEqual(phone['stackTimelines'], 3)

    def test_motion_boot_only_starts_the_intro_on_a_first_plain_visit(self):
        r = self.node_json(BOOT_SCRIPT, BOOT)
        for name, result in r.items():
            with self.subTest(case=name):
                self.assertIsNone(result['error'])
                self.assertIn('js', result['classes'])
        first = r['first']
        self.assertEqual(first['classes'], ['js', 'motion', 'ns-intro'])
        self.assertEqual(len(first['timers']), 1)
        self.assertLessEqual(first['timers'][0], 2500)
        self.assertEqual(first['afterTimers'], ['js', 'motion'])  # the failsafe removes the panel
        self.assertEqual(first['flag'], '1')
        self.assertEqual(r['reduced']['classes'], ['js'])
        self.assertEqual(r['noMatchMedia']['classes'], ['js'])
        for name in ('hash', 'seen', 'throws', 'inner'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['classes'], ['js', 'motion'])
                self.assertEqual(r[name]['timers'], [])
        for name in ('reduced', 'hash', 'inner'):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['flag'])

    def test_motion_js_keeps_services_working_and_clamps_the_magnetic_pull(self):
        r = self.node_json(MOTION_SCRIPT, MOTION)
        for name in ('plain', 'desktop', 'touch', 'reduced'):
            with self.subTest(case=name):
                result = r[name]
                self.assertTrue(result['live'])
                self.assertEqual(result['active'], [True, False, False])
                self.assertEqual(result['afterHover'], [False, False, True])
                self.assertEqual(result['afterFocus'], [False, True, False])
        desktop = r['desktop']
        self.assertFalse(desktop['visibility'])
        self.assertTrue(desktop['pull'])
        for value in desktop['pull']:
            self.assertLessEqual(abs(value), 6)
        self.assertEqual(max(abs(v) for v in desktop['pull']), 6)
        self.assertFalse(desktop['faq']['prevented'])
        self.assertEqual(desktop['faq']['tweens'], 1)
        self.assertEqual(desktop['batches'], 2)
        for query in desktop['queries']:
            with self.subTest(query=query):
                self.assertIn('(prefers-reduced-motion: no-preference)', query)
        # Touch screens get no magnetic pull; reduced motion gets no motion at all.
        self.assertEqual(r['touch']['pull'], [])
        self.assertEqual(r['reduced']['pull'], [])
        self.assertEqual(r['reduced']['batches'], 0)
        self.assertEqual(r['reduced']['faq']['tweens'], 0)

    def test_demo_js_makes_no_network_requests(self):
        js = DEMO.read_text(encoding='utf-8')
        for token in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'EventSource', 'http://', 'https://'):
            self.assertNotIn(token, js)


if __name__ == '__main__':
    unittest.main()
