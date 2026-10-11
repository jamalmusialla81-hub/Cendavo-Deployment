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
  const log = { queries: [], timelines: [], tweens: [], sets: [], setNames: [], creates: [], quick: [], plugins: 0, batches: 0, varsSeen: [] };
  const count = targets => (Array.isArray(targets) ? targets.length : 1);
  const nameOf = targets => (Array.isArray(targets) ? targets : [targets]).map(t => (t && t.name) || null);
  const record = (owner, kind, targets, vars, position) => {
    log.varsSeen.push(vars);
    const at = position === undefined ? owner.cursor : position;
    const end = at + (vars.duration === undefined ? 0.5 : vars.duration) + (vars.stagger || 0) * (count(targets) - 1);
    const tween = { kind, at, end, n: count(targets), names: nameOf(targets), vars };
    owner.tweens.push(tween);
    owner.cursor = end;
    return tween;
  };
  const gsap = {
    registerPlugin() { log.plugins++; },
    matchMedia() { return { add(query, fn) { log.queries.push(query); if (media(query, env)) fn(); } }; },
    timeline(vars) {
      const tl = { vars: vars || {}, tweens: [], labels: {}, cursor: 0, callbacks: [], played: [], progressed: [], now: 0,
        scrollTrigger: vars && vars.scrollTrigger ? { start: 1000, end: 1000 + 2 * env.height } : undefined,
        from(t, v, p) { record(tl, 'from', t, v, p); return tl; },
        to(t, v, p) { record(tl, 'to', t, v, p); return tl; },
        fromTo(t, a, v, p) { log.varsSeen.push(a); record(tl, 'fromTo', t, v, p).from = a; return tl; },
        add(fn, p) { tl.callbacks.push({ fn, at: p }); tl.cursor = Math.max(tl.cursor, p); return tl; },
        addLabel(name, p) { tl.labels[name] = p; return tl; },
        play(at) { tl.played.push(at); return tl; },
        progress(v) { tl.progressed.push(v); if (v === 1) { tl.callbacks.forEach(c => c.fn()); if (tl.vars.onComplete) tl.vars.onComplete(); } return tl; },
        duration() { return Math.max(0, ...tl.tweens.map(t => t.end), ...tl.callbacks.map(c => c.at)); },
        time() { return tl.now; },
      };
      if (vars) log.varsSeen.push(vars);
      log.timelines.push(tl);
      return tl;
    },
    from(t, v) { log.varsSeen.push(v); log.tweens.push({ kind: 'from', vars: v, names: nameOf(t) }); },
    fromTo(t, a, v) { log.varsSeen.push(a, v); log.tweens.push({ kind: 'fromTo', vars: v, from: a, names: nameOf(t) }); },
    to(state, v) { log.varsSeen.push(v); log.tweens.push({ kind: 'to', vars: v, names: nameOf(state) }); if ('v' in v) { state.v = v.v; v.onUpdate(); } return { kill() {} }; },
    set(t, v) { log.varsSeen.push(v); log.sets.push(v); log.setNames.push(...nameOf(t)); },
    killTweensOf() {},
    quickTo(target, prop) { return value => log.quick.push([prop, value]); },
  };
  const ScrollTrigger = { batch() { log.batches++; }, create(v) { log.creates.push(v); } };
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
  const projects = [0, 1, 2].map(i => element('proj' + i, { '.proj-mask > *': many('copy', 3), '.proj-devices': many('devices', 1), '.proj-media': many('media', 1), '.proj-media img': many('mimg', 1) }));
  const counter = element('counter'), bar = element('bar');
  const stage = element('stage', { '.proj': projects, '.work-count-n': [counter], '.work-count-bar i': [bar], '.work-exit': [element('exit')] });
  // Classes motion-boot.js would have set: .ph-wait (openings held by CSS) and, on a first visit, .ns-intro.
  const root = element('html'); root.classList = classList(['js'].concat(env.introClass || env.wait ? ['motion'] : [], env.introClass ? ['ns-intro'] : [], env.wait ? ['ph-wait'] : []));
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
    out.heroPhotoClip = hero ? hero.tweens.filter(t => t.names[0] === 'photo' && ((t.from && 'clipPath' in t.from) || 'clipPath' in t.vars)).map(t => t.from.clipPath) : null;
    out.heroPhotoScale = hero ? hero.tweens.filter(t => t.names[0].startsWith('img') && t.from && t.from.scale === 1.08 && t.vars.scale === 1).length : null;
    out.heroOpacityOnly = hero ? hero.tweens.every(t => !('autoAlpha' in t.vars) && !('visibility' in t.vars)) : null;
    out.openingKinds = [hero, introTl].filter(Boolean).flatMap(tl => tl.tweens.map(t => t.kind));
    out.introWipeAt = introTl ? introTl.tweens.find(t => t.names[0] === 'intro').at : null;
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
      // Move the pinned timeline's playhead (what is on screen) to a share of its length and read the counter.
      const counterAt = progress => { pin.now = progress * pin.duration(); pin.vars.onUpdate(); return counter.textContent; };
      out.counter = counterAt(1);
      out.pinDuration = pin.duration();
      out.counterSamples = [0, 0.2, 0.3, 0.6, 0.8, 1].map(progress => [progress, counterAt(progress)]);
      out.pinScrollUpdate = 'onUpdate' in pin.vars.scrollTrigger;
      const value = v => (typeof v === 'function' ? v(0, null) : v);
      out.pinTweens = pin.tweens.map(t => ({ at: t.at, end: t.end, n: t.n, names: t.names, opacity: t.vars.opacity, fromOpacity: t.from && t.from.opacity,
        yPercent: t.vars.yPercent, fromYPercent: t.from && t.from.yPercent, y: value(t.vars.y), fromY: t.from && value(t.from.y), clipPath: t.vars.clipPath }));
      out.pinLabels = pin.labels;
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
  plain: run({ ...desktop, introClass: true, wait: true }),
  first: run({ ...desktop, gsap: true, introClass: true, wait: true, now: 120, skipWith: 'keydown' }),
  pointer: run({ ...desktop, gsap: true, introClass: true, wait: true, now: 120, skipWith: 'pointerdown' }),
  late: run({ ...desktop, gsap: true, introClass: true, wait: true, now: 1500 }),
  noIntro: run({ ...desktop, gsap: true, introClass: false, wait: true }),
  released: run({ ...desktop, gsap: true, introClass: false, wait: false }),
  reduced: run({ ...desktop, gsap: true, introClass: true, reduce: true }),
  phone: run({ width: 390, height: 844, fine: false, reduce: false, gsap: true, introClass: false, wait: true }),
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
  const heads = many('head', 3);
  const rows = many('svc', 3).map((row, at) => { row.parentNode = list; row.parts = { h3: [heads[at]] }; return row; });
  // Scroll-reveal targets below the fold, plus one of each already on screen (which must be left alone).
  const below = (name, count) => many(name, count).map(item => { item.getBoundingClientRect = () => ({ left: 0, top: 2000, width: 100, height: 100 }); return item; });
  const root = element('html'); root.classList = classList(env.reduce ? ['js'] : ['js', 'motion', 'ph-wait']);
  const panel = element('panel');
  const photos = many('photo', 3);
  const button = element('go');
  const summary = element('summary'); summary.tagName = 'SUMMARY';
  const answer = element('answer'); answer.tagName = 'P';
  const details = element('details'); details.children = [summary, answer];
  const parts = { '.svc': rows, '.svc-panel': [panel], '.svc-photo': photos, '.button.go': [button], details: [details],
    '[data-rise]': below('rise', 2).concat(element('riseOnScreen')), '[data-reveal]': below('reveal', 2).concat(element('revealOnScreen')),
    '[data-parallax]': [element('frame', { img: many('pimg', 1) })], '[data-ph]': [element('head', { 'h1 .ln > span': many('line', 2), '[data-ph-fade]': many('phf', 2), '[data-ph-media]': many('phm', 3) })],
    '[data-devices]': below('dev', 1).concat(element('devOnScreen')) };
  const doc = { documentElement: root, querySelectorAll: s => parts[s] || [], querySelector: s => (parts[s] || [])[0] || null };
  const { win } = makeWindow(env);
  let log = null;
  if (env.gsap) { const stub = makeGsap(env); win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; log = stub.log; }
  vm.runInNewContext(source, { window: win, document: doc });
  const shown = () => photos.map(p => p.classList.contains('is-active'));
  const out = { live: panel.classList.contains('is-live'), wipe: panel.classList.contains('is-wipe'), wait: root.classList.contains('ph-wait'),
    active: rows.map(r => r.classList.contains('is-active')), photos: shown() };
  const wipes = () => (log ? log.tweens.filter(t => t.from && t.from.clipPath === 'inset(100% 0 0 0)' && t.names[0].startsWith('photo')).map(t => t.names[0]) : []);
  const dims = () => (log ? log.tweens.filter(t => t.kind === 'to' && t.names[0] === 'head0').map(t => [0, 1, 2].map(at => t.vars.opacity(at))) : []);
  if (log) {
    const opening = log.timelines.flatMap(tl => tl.tweens);
    out.openingKinds = opening.map(t => t.kind);
    out.openingNames = opening.map(t => t.names[0]);
    out.lineFrom = (opening.find(t => t.names[0] === 'line0') || {}).from || null;
    out.mediaStagger = (opening.find(t => t.names[0] === 'phm0') || {}).vars?.stagger || 0;
    out.setNames = log.setNames.slice();
    out.revealNames = log.tweens.filter(t => t.kind === 'from').flatMap(t => t.names);
    out.creates = log.creates.length;
    out.initialDim = log.sets.filter(v => typeof v.opacity === 'function').map(v => [0, 1, 2].map(at => v.opacity(at)));
  }
  rows[2].listeners.mouseenter[0](); out.afterHover = rows.map(r => r.classList.contains('is-active')); out.photosAfterHover = shown();
  rows[1].listeners.focusin[0](); out.afterFocus = rows.map(r => r.classList.contains('is-active')); out.photosAfterFocus = shown();
  out.prevAfterFocus = photos.map(p => p.classList.contains('is-prev'));
  out.wipes = wipes();
  out.dims = dims();
  if (log && log.creates.length) { log.creates[2].onToggle({ isActive: true }); out.afterScroll = rows.map(r => r.classList.contains('is-active')); }
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
        self.assertNotIn('ph-wait', plain['classes'])  # Task 23: without GSAP the CSS hold on the hero is released at once
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
        # Night Shift Task 23: a shorter intro, so the headline reads by about 1.7 s.
        self.assertLessEqual(first['introEnd'], 1.4)
        self.assertLessEqual(first['introWipeAt'], 0.8)
        self.assertLessEqual(first['heroAt'][0], 1.0)
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

    def test_home_hero_takes_over_the_css_hold_without_a_flash(self):
        # Night Shift Task 23: the hero and intro use fromTo (start states applied at once, matching the CSS held under
        # .ph-wait), then home.js removes .ph-wait. If the 2.5 s failsafe already removed it, the hero is not hidden again.
        r = self.node_json(HOME_SCRIPT, HOME)
        for name in ('first', 'late', 'noIntro', 'phone'):
            with self.subTest(case=name):
                self.assertNotIn('ph-wait', r[name]['classes'])
                self.assertTrue(r[name]['openingKinds'])
                self.assertNotIn('from', r[name]['openingKinds'])
        released = r['released']
        self.assertIsNone(released['heroEnd'])
        self.assertIsNone(released['heroPlayed'])
        self.assertNotIn('ph-wait', released['classes'])

    def test_home_hero_photo_paints_under_the_first_visit_intro(self):
        # Night Shift Task 26: with the intro the photo is never clipped (it paints beneath the panel and stays the LCP
        # element) and only settles in scale; without the intro, or when scripts arrive late, it still wipes in.
        r = self.node_json(HOME_SCRIPT, HOME)
        first = r['first']
        self.assertEqual(first['heroPhotoClip'], [])
        self.assertEqual(first['heroPhotoScale'], 1)
        self.assertEqual(first['heroAt'], [0.95])
        self.assertLessEqual(first['introEnd'], 1.4)
        self.assertLessEqual(first['heroEnd'], 1.2)
        for name in ('noIntro', 'late', 'phone'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['heroPhotoClip'], ['inset(0 0 0 100%)'])
                self.assertEqual(r[name]['heroPhotoScale'], 1)
                self.assertEqual(r[name]['heroPlayed'], [0])
        # Late scripts: the intro class goes in the same synchronous run, so the CSS no-intro clip and the JS clip agree.
        self.assertNotIn('ns-intro', r['late']['classes'])
        self.assertNotIn('ph-wait', r['late']['classes'])

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
        self.assertEqual(first['pinEnd'], '+=' + str(int(900 * 2.5)))  # two and a half viewport heights at most (Task 23)
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

    def test_home_projects_swap_text_quickly_and_never_show_two_device_sets(self):
        # Night Shift Task 17 (design critique): one project's text is always readable and the devices hand over back to back.
        # Task 23: no opacity at all (no grey ghosts): copy moves through its masks, devices travel a full viewport.
        r = self.node_json(HOME_SCRIPT, HOME)
        tweens = r['first']['pinTweens']
        text = [t for t in tweens if t['n'] == 3]  # each project's three copy masks
        devices = [t for t in tweens if (t['names'][0] or '').startswith('devices')]
        self.assertEqual(len(text), 4)
        self.assertEqual(len(devices), 4)
        for tween in tweens:
            with self.subTest(tween=tween['names'][0], at=tween['at']):
                self.assertIsNone(tween.get('opacity'))
                self.assertIsNone(tween.get('fromOpacity'))
        # Outgoing copy leaves up out of its mask; incoming copy rises in from below it.
        self.assertEqual([(t.get('fromYPercent'), t.get('yPercent')) for t in text], [(None, -110), (110, 0), (None, -110), (110, 0)])
        # Outgoing devices leave a full viewport up; incoming ones arrive from a full viewport below (always off-frame).
        self.assertEqual([(t.get('fromY'), t.get('y')) for t in devices], [(None, -900), (900, 0), (None, -900), (900, 0)])
        labels = r['first']['pinLabels']
        for index in (1, 2):
            text_out, text_in = text[2 * index - 2:2 * index]
            dev_out, dev_in = devices[2 * index - 2:2 * index]
            with self.subTest(transition=index):
                self.assertLessEqual(text_out['end'] - text_out['at'], 0.25 + 1e-9)
                self.assertLessEqual(text_in['end'] - text_in['at'], 0.25 + 1e-9)
                # No gap longer than 0.1 and no overlap longer than 0.1 between outgoing and incoming text.
                self.assertLessEqual(abs(text_in['at'] - text_out['end']), 0.1 + 1e-9)
                # Incoming devices start at most 0.1 before the outgoing ones are gone.
                self.assertGreaterEqual(dev_in['at'], dev_out['end'] - 0.1 - 1e-9)
                # Everything has settled by the project's focus-scroll label.
                self.assertLessEqual(max(t['end'] for t in (text_in, dev_in)), labels['p%d' % index] + 1e-9)
                self.assertGreaterEqual(text_out['at'], labels['p%d' % (index - 1)])

    def test_home_projects_counter_matches_the_title_on_screen(self):
        # Night Shift Task 21: the counter changes at the middle of each text swap (outgoing text gone, incoming arriving),
        # measured on the timeline's own playhead, not at equal slices of the scroll and not ahead of the scrubbed visuals.
        r = self.node_json(HOME_SCRIPT, HOME)
        first = r['first']
        self.assertFalse(first['pinScrollUpdate'])  # scroll progress runs ahead of the scrubbed timeline, so it is not used
        text = [t for t in first['pinTweens'] if t['n'] == 3]
        swaps = [(text[i]['end'] + text[i + 1]['at']) / 2 for i in (0, 2)]
        samples = first['counterSamples']
        self.assertEqual([p for p, _ in samples], [0, 0.2, 0.3, 0.6, 0.8, 1])
        for progress, shown in samples:
            with self.subTest(progress=progress):
                time = progress * first['pinDuration']
                expected = 1 + sum(1 for swap in swaps if time >= swap)
                self.assertEqual(shown, str(expected))
        # 0.2 is past the first swap but would still round to project 1 with equal slices.
        self.assertEqual([shown for _, shown in samples], ['1', '2', '2', '2', '3', '3'])
        for index, swap in enumerate(swaps):
            with self.subTest(transition=index + 1):
                text_out, text_in = text[2 * index], text[2 * index + 1]
                self.assertGreaterEqual(swap, text_in['at'] - 1e-9)  # the new title has started to appear
                self.assertLessEqual(swap, text_out['end'] + 1e-9)  # and the old one is on its way out

    def test_home_pin_release_layer_rises_after_the_last_project(self):
        # Night Shift Task 23: a decorative bone layer rises over the lower stage after the last project's label, so focus
        # never lands under it and the release meets the bone section that follows.
        r = self.node_json(HOME_SCRIPT, HOME)
        first = r['first']
        exits = [t for t in first['pinTweens'] if t['names'] == ['exit']]
        self.assertEqual(len(exits), 1)
        self.assertGreaterEqual(exits[0]['at'], first['pinLabels']['p2'])
        self.assertTrue(exits[0].get('clipPath', '').startswith('inset('))
        self.assertAlmostEqual(exits[0]['end'], first['pinDuration'])

    def test_motion_boot_only_starts_the_intro_on_a_first_plain_visit(self):
        r = self.node_json(BOOT_SCRIPT, BOOT)
        for name, result in r.items():
            with self.subTest(case=name):
                self.assertIsNone(result['error'])
                self.assertIn('js', result['classes'])
        first = r['first']
        self.assertEqual(first['classes'], ['js', 'motion', 'ns-intro', 'ph-wait'])
        self.assertEqual(len(first['timers']), 2)
        for delay in first['timers']:
            self.assertLessEqual(delay, 2500)
        self.assertEqual(first['afterTimers'], ['js', 'motion'])  # the failsafes remove the panel and the opening hold
        self.assertEqual(first['flag'], '1')
        # Reduced motion or no matchMedia: nothing is held hidden and no timer is needed.
        for name in ('reduced', 'noMatchMedia'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['classes'], ['js'])
                self.assertEqual(r[name]['timers'], [])
        # No intro: the opening hold is still set, with its own failsafe.
        for name in ('hash', 'seen', 'throws', 'inner'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['classes'], ['js', 'motion', 'ph-wait'])
                self.assertEqual(len(r[name]['timers']), 1)
                self.assertLessEqual(r[name]['timers'][0], 2500)
                self.assertEqual(r[name]['afterTimers'], ['js', 'motion'])
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
                # The photo panel shows the photo for the active row: the first one at first, then the hovered or focused row's.
                self.assertEqual(result['photos'], [True, False, False])
                self.assertEqual(result['photosAfterHover'], [False, False, True])
                self.assertEqual(result['photosAfterFocus'], [False, True, False])
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

    def test_motion_js_openings_take_over_the_css_hold_without_a_flash(self):
        # Night Shift Task 23: inner-page openings use fromTo (headline lines rise via yPercent through their masks, head
        # photos un-mask in turn), then .ph-wait is removed, also when GSAP is missing. Reveals skip what is already on screen.
        r = self.node_json(MOTION_SCRIPT, MOTION)
        for name in ('plain', 'desktop', 'touch', 'reduced'):
            with self.subTest(case=name):
                self.assertFalse(r[name]['wait'])
        for name in ('desktop', 'touch'):
            with self.subTest(case=name):
                result = r[name]
                self.assertTrue(result['openingKinds'])
                self.assertEqual(set(result['openingKinds']), {'fromTo'})
                self.assertIn('line0', result['openingNames'])
                self.assertEqual(result['lineFrom'], {'yPercent': 108})
                self.assertGreater(result['mediaStagger'], 0)
                hidden = result['setNames'] + result['revealNames']
                for name_on_screen in ('riseOnScreen', 'revealOnScreen', 'devOnScreen'):
                    self.assertNotIn(name_on_screen, hidden)
                for name_below in ('rise0', 'reveal0', 'dev0'):
                    self.assertIn(name_below, hidden)
        self.assertEqual(r['reduced']['openingKinds'], [])

    def test_motion_js_services_rows_wipe_dim_and_follow_scroll(self):
        # Night Shift Task 23: with GSAP motion the photo swap is a clip-path wipe (the outgoing photo waits beneath as
        # .is-prev), inactive headings dim with opacity, and on large screens each row activates as it crosses mid-viewport.
        r = self.node_json(MOTION_SCRIPT, MOTION)
        desktop = r['desktop']
        self.assertTrue(desktop['wipe'])
        self.assertEqual(desktop['wipes'], ['photo2', 'photo1'])  # hover row 3, then focus row 2
        self.assertEqual(desktop['prevAfterFocus'], [False, False, True])
        dim = desktop['initialDim'][0][1]
        self.assertLess(dim, 1)
        self.assertEqual(desktop['initialDim'], [[1, dim, dim]])
        self.assertEqual(desktop['dims'][-1], [dim, 1, dim])
        self.assertEqual(desktop['creates'], 3)
        self.assertEqual(desktop['afterScroll'], [False, False, True])
        # Touch: hover and focus still wipe, but no scroll activation. Reduced motion or no GSAP: CSS swap only, no dimming.
        self.assertEqual(r['touch']['creates'], 0)
        self.assertEqual(r['touch']['wipes'], ['photo2', 'photo1'])
        for name in ('plain', 'reduced'):
            with self.subTest(case=name):
                self.assertFalse(r[name]['wipe'])
                self.assertEqual(r[name]['wipes'], [])
                self.assertEqual(r[name]['dims'], [])

    def test_demo_js_makes_no_network_requests(self):
        js = DEMO.read_text(encoding='utf-8')
        for token in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'EventSource', 'http://', 'https://'):
            self.assertNotIn(token, js)


if __name__ == '__main__':
    unittest.main()
