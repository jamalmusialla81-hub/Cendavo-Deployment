import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / 'assets' / 'demo.js'
HOME = Path(__file__).resolve().parents[1] / 'assets' / 'home.js'
REEL = Path(__file__).resolve().parents[1] / 'assets' / 'reel.js'
DETAILS = Path(__file__).resolve().parents[1] / 'assets' / 'details.js'

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
    getAttribute(key) { return key in this.attrs ? this.attrs[key] : null; },
    removeAttribute(key) { delete this.attrs[key]; },
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

# Runs assets/home.js against the stub DOM (Liquid Glass, Task 37, over Daylight): without GSAP (everything stays in its final
# state) and with the recording GSAP stub (hero opening and the glass cards' booking, the hero's scroll exit, the showreel
# lens, the Pause motion button, reduced motion, small screens).
HOME_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const range = element('range'), before = element('before'), after = element('after'), controls = element('controls');
  const figure = element('figure');
  before.dataset.compareSet = '0'; after.dataset.compareSet = '100'; controls.hidden = true;
  controls.parts = { 'input[type="range"]': [range], '[data-compare-set]': [before, after] };
  figure.parts = { '[data-compare-controls]': [controls] };
  // The glass booking card as the HTML ships it: its final state (10:30 picked and booked).
  const book = element('book'); book.classList = classList(['booked']);
  const slot = element('slot'); slot.classList = classList(['on']);
  // site.js (loaded first, Task 41) has already set aria-pressed: "true" when Save-Data or reduced motion holds the motion.
  const toggle = element('toggle'); toggle.attrs['aria-pressed'] = env.held ? 'true' : 'false';
  // The class motion-boot.js would have set: .ph-wait (openings held by CSS) unless its failsafe already removed it.
  const root = element('html'); root.classList = classList(['js'].concat(env.reduce ? [] : ['motion'], env.wait ? ['ph-wait'] : []));
  // Below-the-fold pieces (headings, cards, the glass frame and panel) and the showreel frame.
  const below = name => { const el = element(name); el.getBoundingClientRect = () => ({ left: 0, top: 3000, width: 400, height: 300 }); return el; };
  const parts = { '[data-compare]': [figure], '.hero-h .ln > span': many('line', 4), '[data-hero-fade]': many('fade', 2), '.hero-cards': [element('deck')],
    '.gcard': many('card', 2), '.c-book': [book], '.slot-pick': [slot], '.hero': [element('hero')], '[data-motion-toggle]': [toggle],
    '[data-rise]': [below('rise0'), element('riseOnScreen')], '.reel-frame': [element('reelFrame')], '.reel-panel': [below('reelPanel')],
    '.teaser-card': [below('teaser0'), below('teaser1'), below('teaser2')], '.compare-frame': [below('glassFrame')], '.band-panel': [below('bandPanel')],
    '.band': [element('band')], '.gp-1': [element('phone1')], '.marq': [element('marq')], '.mq-type': [element('mqType')], '[data-marquee]': many('track', 2) };
  const doc = { documentElement: root, querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const { win } = makeWindow(env, { requestAnimationFrame: () => 1, cancelAnimationFrame() {} });
  let log = null;
  if (env.gsap) { const stub = makeGsap(env); win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; log = stub.log; }
  vm.runInNewContext(source, { window: win, document: doc });
  const snap = () => ({ pos: figure.style.props['--pos'], before: before.attrs['aria-pressed'], after: after.attrs['aria-pressed'], text: range.attrs['aria-valuetext'] });
  const stage = () => ({ booked: book.classList.contains('booked'), picked: slot.classList.contains('on') });
  const out = { shown: controls.hidden === false, initial: snap(), classes: Array.from(root.classList.set).sort(), stage: stage() };
  if (log) {
    const hero = log.timelines.find(tl => tl.vars.paused);
    out.queries = log.queries;
    out.plugins = log.plugins;
    out.heroEnd = hero ? hero.duration() : null;
    out.heroPlayed = hero ? hero.played.slice() : null;
    out.openingKinds = hero ? hero.tweens.map(t => t.kind) : [];
    out.openingNames = hero ? hero.tweens.map(t => t.names[0]) : [];
    out.callbacks = hero ? hero.callbacks.map(c => c.at) : [];
    const shape = t => ({ kind: t.kind, from: t.from || null, yPercent: t.vars.yPercent, y: t.vars.y, clearProps: t.vars.clearProps || null });
    out.heroLines = hero ? hero.tweens.filter(t => (t.names[0] || '').startsWith('line')).map(shape) : null;
    out.cursor = hero ? hero.tweens.filter(t => t.names[0] === 'cursor').map(t => ({ from: t.from || null, xPercent: t.vars.xPercent, yPercent: t.vars.yPercent, clearProps: t.vars.clearProps || null })) : null;
    // Eases: the timeline default and every tween's own ease must be one of home.js's two curves (functions).
    out.defaultEase = hero ? typeof hero.vars.defaults.ease : null;
    out.tweenEases = hero ? Array.from(new Set(hero.tweens.map(t => typeof t.vars.ease))) : [];
    if (hero) {
      // OUT: the opening's default; IO: the comparison's glide (the before/after buttons), tested below.
      out.curvesFrom = hero.vars.defaults.ease;
    }
    out.autoAlpha = log.varsSeen.some(v => v && ('autoAlpha' in v || 'visibility' in v));
    out.snap = log.varsSeen.some(v => v && v.scrollTrigger && 'snap' in v.scrollTrigger);
    out.pins = log.varsSeen.filter(v => v && v.scrollTrigger && v.scrollTrigger.pin).length;
    out.scrollTimelines = log.timelines.filter(tl => tl.vars.scrollTrigger).map(tl => ({ scrub: tl.vars.scrollTrigger.scrub, pin: 'pin' in tl.vars.scrollTrigger,
      tweens: tl.tweens.map(t => ({ names: t.names, ease: t.vars.ease, props: Object.keys(t.vars).concat(Object.keys(t.from || {})) })) }));
    out.scrubs = log.tweens.filter(t => t.vars && t.vars.scrollTrigger && t.vars.scrollTrigger.scrub)
      .map(t => ({ names: t.names, props: Object.keys(t.vars).concat(Object.keys(t.from || {})).filter(k => k !== 'scrollTrigger' && k !== 'ease').sort(), scrub: t.vars.scrollTrigger.scrub, ease: t.vars.ease }));
    out.reveals = log.tweens.filter(t => t.kind === 'fromTo' && t.vars.scrollTrigger && t.vars.scrollTrigger.once).map(t => t.names[0]);
    out.heroP = (() => { const tl = log.timelines.find(t => t.vars.scrollTrigger && t.vars.scrollTrigger.trigger && t.vars.scrollTrigger.trigger.name === 'hero');
      if (!tl) return null; tl.vars.scrollTrigger.onUpdate({ progress: 0.4 }); return win.__glass.heroP; })();
    out.marquee = log.creates.filter(c => c.trigger && c.trigger.name === 'marq').length;
    out.notOnce = log.creates.filter(c => !c.once).length;
    if (hero && env.press) {
      toggle.attrs['aria-pressed'] = 'true';  // site.js flips it first (it is loaded first)
      (toggle.listeners.click || []).forEach(fn => fn({ type: 'click' }));
      out.afterPress = { progressed: hero.progressed.slice(), stage: stage() };
      toggle.attrs['aria-pressed'] = 'false';
      const before = hero.progressed.length;
      (toggle.listeners.click || []).forEach(fn => fn({ type: 'click' }));
      out.resumeProgressCalls = hero.progressed.length - before;  // pressing again (play) never replays the choreography
    } else if (hero) {
      out.atStart = stage();
      out.progressedAtStart = hero.progressed.slice();
      hero.progress(1);  // the timeline reaches its end: every call fires
      out.atEnd = stage();
    }
  }
  range.value = '0'; range.listeners.input[0](); out.input = snap();
  after.listeners.click[0](); out.click = { ...snap(), value: String(range.value) };
  const glides = log ? log.tweens.filter(t => t.kind === 'to' && t.vars && 'v' in t.vars) : [];
  out.glides = glides.length;
  if (log && out.curvesFrom && glides.length) {
    const xs = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1];
    out.curves = { out: xs.map(out.curvesFrom), io: xs.map(glides[0].vars.ease) };
  }
  delete out.curvesFrom;
  return out;
}
const desktop = { width: 1440, height: 900, fine: true, reduce: false };
console.log(JSON.stringify({
  plain: run({ ...desktop, wait: true }),
  first: run({ ...desktop, gsap: true, wait: true }),
  released: run({ ...desktop, gsap: true, wait: false }),
  held: run({ ...desktop, gsap: true, wait: true, held: true }),
  press: run({ ...desktop, gsap: true, wait: true, press: true }),
  reduced: run({ ...desktop, gsap: true, reduce: true }),
  phone: run({ width: 390, height: 844, fine: false, reduce: false, gsap: true, wait: true }),
}));
"""

# Night Shift Task 28: runs the showreel controller (assets/reel.js since Task 29) with a fake <video> (play() resolves, or
# rejects like iOS Low Power Mode), a fake IntersectionObserver the test drives by hand, matchMedia, Save-Data and optional
# GSAP. Task 29: several reels on one page (the Services clips) must work independently, each with its own button name.
REEL_SCRIPT = HARNESS + r"""
// Task 41: site.js owns the Pause motion button and runs first on every page (deferred, in order), so it runs first here.
const source = fs.readFileSync(require('path').join(require('path').dirname(process.argv[1]), 'site.js'), 'utf8') + '\n' + fs.readFileSync(process.argv[1], 'utf8');
const WIDE = { src: '/assets/glass/glass-reel-1600.mp4', poster: '/assets/glass/glass-reel-poster.jpg' };
const NARROW = { src: '/assets/glass/glass-reel-vertical-720.mp4', poster: '/assets/glass/glass-reel-vertical-poster.jpg' };
const settle = () => new Promise(resolve => setImmediate(resolve));
function makeVideo(env, name, src) {
  const video = element(name, { source: [src || element('source')] });
  Object.assign(video, { paused: true, muted: false, plays: 0, pauses: 0, loads: 0 });
  const fire = type => (video.listeners[type] || []).forEach(fn => fn({ type }));
  video.load = () => { video.loads++; };
  video.play = () => {
    video.plays++;
    if (env.refuse) return Promise.reject(new Error('NotAllowedError'));  // the browser keeps the video paused
    if (env.throws) throw new Error('old browser');
    video.paused = false; fire('play');
    return Promise.resolve();
  };
  video.pause = () => { video.pauses++; if (!video.paused) { video.paused = true; fire('pause'); } };
  return video;
}
function makeDoc(parts, root, env) {
  return { documentElement: root, readyState: env.complete ? 'complete' : 'interactive', hidden: false, listeners: {},
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
}
function makeReel(env, name, narrow) {
  const src = element('source'); src.attrs.src = narrow ? WIDE.src : '/assets/video/' + name + '.mp4';
  const video = makeVideo(env, 'video', src);
  video.attrs = { controls: '', poster: narrow ? WIDE.poster : '/assets/video/' + name + '.jpg', muted: '' };
  video.dataset = narrow ? { narrowSrc: NARROW.src, narrowPoster: NARROW.poster } : {};
  const toggle = element('toggle'); toggle.hidden = true; toggle.textContent = 'Play ' + name; toggle.attrs.type = 'button';
  const reel = element('reel', { video: [video], '[data-reel-toggle]': [toggle] });
  return { reel, video, toggle, src };
}
async function run(env) {
  const names = env.names || ['showreel'];
  const reels = names.map((name, i) => makeReel(env, name, i === 0 && !env.names));
  const { video, toggle, src } = reels[0];
  const root = element('html'); root.classList = classList(['js']);
  const parts = { '[data-reel]': reels.map(r => r.reel) };
  const doc = makeDoc(parts, root, env);
  const observers = [];
  class FakeObserver { constructor(callback, options) { this.callback = callback; this.options = options; this.targets = []; observers.push(this); } observe(target) { this.targets.push(target); } }
  const { win } = makeWindow(env, {
    IntersectionObserver: env.noObserver ? undefined : FakeObserver,
    navigator: env.saveData ? { connection: { saveData: true } } : { connection: {} },
  });
  if (env.gsap) { const stub = makeGsap(env); win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; }
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: doc, setImmediate }); } catch (e) { error = String(e); }
  const stateOf = r => ({ playing: !r.video.paused, label: r.toggle.textContent, plays: r.video.plays });
  const state = () => stateOf(reels[0]);
  const viewOf = async (r, on) => { observers.filter(o => o.targets.includes(r.video)).forEach(o => o.callback([{ isIntersecting: on, target: r.video }])); await settle(); };
  const view = async on => { for (const r of reels) await viewOf(r, on); return state(); };
  const pressOf = async r => { (r.toggle.listeners.click || []).forEach(fn => fn({ type: 'click' })); await settle(); };
  const press = async () => { await pressOf(reels[0]); return state(); };
  await settle();
  const out = { error, controls: 'controls' in video.attrs, muted: video.muted, hidden: toggle.hidden, type: toggle.attrs.type,
    src: src.attrs.src, poster: video.attrs.poster, loads: video.loads, observed: observers.flatMap(o => o.targets).filter(t => t === video).length,
    threshold: observers.length ? observers[0].options.threshold : null, initial: state(),
    all: reels.map(r => ({ controls: 'controls' in r.video.attrs, hidden: r.toggle.hidden, muted: r.video.muted, loads: r.video.loads, src: r.src.attrs.src,
      observed: observers.filter(o => o.targets.includes(r.video)).length, ...stateOf(r) })) };
  if (env.names) {
    // Independent instances: only the first clip scrolls into view, then the second; a press pauses only its own video.
    const snap = () => reels.map(stateOf);
    out.multi = [];
    await viewOf(reels[0], true); out.multi.push(['first in view', snap()]);
    await viewOf(reels[1], true); out.multi.push(['second in view', snap()]);
    await pressOf(reels[1]); out.multi.push(['press second', snap()]);
    await pressOf(reels[1]); out.multi.push(['press second again', snap()]);
    await viewOf(reels[0], false); out.multi.push(['first out of view', snap()]);
    await viewOf(reels[1], false); await viewOf(reels[1], true); out.multi.push(['second back in view', snap()]);
    return out;
  }
  out.steps = [];
  out.steps.push(['in view', await view(true)]);
  out.steps.push(['out of view', await view(false)]);
  out.steps.push(['back in view', await view(true)]);
  out.steps.push(['press', await press()]);
  out.steps.push(['out of view', await view(false)]);
  out.steps.push(['back in view', await view(true)]);
  out.steps.push(['press', await press()]);
  out.steps.push(['out of view', await view(false)]);
  return out;
}
// Daylight (Task 33): the homepage's two hero loops, the showreel with chapters and the Pause motion button on one page.
async function runHero(env) {
  const reel = makeReel(env, 'showreel', Boolean(env.narrow));
  reel.video.id = 'reel-video';
  // As in pages/index.html: the sources carry data-src only, and the laptop plays only above 640px (data-loop="wide").
  const loopSource = name => { const s = element('source'); s.dataset.src = '/assets/video/loop-hb-' + name + '.mp4'; return s; };
  const laptop = makeVideo(env, 'laptop', loopSource('desktop')), phone = makeVideo(env, 'phone', loopSource('phone'));
  laptop.dataset.loop = 'wide'; phone.dataset.loop = '';
  const motion = element('motion'); motion.hidden = true; motion.attrs['aria-pressed'] = 'false';
  const buttons = [0, 6.5, 8].map((t, i) => { const b = element('chapter' + i); b.dataset.t = String(t); return b; });
  const list = element('chapters', { 'button[data-t]': buttons }); list.hidden = true;
  const root = element('html'); root.classList = classList(['js']);
  const parts = { '[data-reel]': [reel.reel], 'video[data-loop]': [laptop, phone], '[data-motion-toggle]': [motion], '[data-chapters="reel-video"]': [list] };
  const doc = makeDoc(parts, root, env);
  const observers = [], idle = [];
  class FakeObserver { constructor(callback) { this.callback = callback; this.targets = []; observers.push(this); } observe(target) { this.targets.push(target); } }
  const { win, listeners } = makeWindow(env, { IntersectionObserver: FakeObserver, requestIdleCallback: fn => idle.push(fn),
    navigator: env.saveData ? { connection: { saveData: true } } : { connection: {} } });
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: doc, setImmediate }); } catch (e) { error = String(e); }
  const videos = [laptop, phone, reel.video];
  const view = async (list, on) => { for (const v of list) observers.filter(o => o.targets.includes(v)).forEach(o => o.callback([{ isIntersecting: on, target: v }])); await settle(); };
  const out = { error, motionHidden: motion.hidden, pressed: motion.attrs['aria-pressed'], chaptersHidden: list.hidden,
    muted: videos.map(v => v.muted), observed: videos.map(v => observers.filter(o => o.targets.includes(v)).length),
    loadListeners: (listeners.load || []).length, steps: [] };
  const step = name => out.steps.push([name, videos.map(v => !v.paused), motion.attrs['aria-pressed']]);
  const press = async () => { (motion.listeners.click || []).forEach(fn => fn({ type: 'click' })); await settle(); };
  await view(videos, true); step('in view');
  (listeners.load || []).forEach(l => l.fn({ type: 'load' })); await settle(); step('loaded');
  idle.splice(0).forEach(fn => fn()); await settle(); step('idle');
  doc.hidden = true; (doc.listeners.visibilitychange || []).forEach(fn => fn()); await settle(); step('tab hidden');
  doc.hidden = false; (doc.listeners.visibilitychange || []).forEach(fn => fn()); await settle(); step('tab visible');
  await press(); step('pause motion');
  await view(videos, false); await view(videos, true); step('back in view, paused');
  await press(); step('play motion');
  await view([laptop, phone], false); step('hero out of view');
  // A chapter seeks the showreel (before its metadata loads the browser keeps the time as the start position) and plays it.
  (buttons[1].listeners.click || []).forEach(fn => fn({ type: 'click' })); await settle();
  out.chapter = { time: reel.video.currentTime === undefined ? null : reel.video.currentTime, playing: !reel.video.paused, current: buttons.map(b => b.attrs['aria-current'] || null) };
  reel.video.currentTime = 8.4; (reel.video.listeners.timeupdate || []).forEach(fn => fn({ type: 'timeupdate' }));
  out.afterTimeupdate = buttons.map(b => b.attrs['aria-current'] || null);
  // After every step above (including Pause motion released): which loop ever asked for its file, loaded or played.
  out.loops = [laptop, phone].map(v => ({ src: v.parts.source[0].attrs.src || null, loads: v.loads, plays: v.plays,
    observed: observers.filter(o => o.targets.includes(v)).length }));
  return out;
}
(async () => {
  const desktop = { width: 1440, height: 900, fine: true, reduce: false };
  const phone = { width: 390, height: 844, fine: false, reduce: false };
  const clips = ['redesign video', 'care plan video'];
  const cases = { desktop, phone, edge: { ...desktop, width: 640 }, wide: { ...desktop, width: 641 }, reduced: { ...desktop, reduce: true },
    saveData: { ...phone, saveData: true }, refuse: { ...phone, refuse: true }, throws: { ...desktop, throws: true },
    noObserver: { ...desktop, noObserver: true }, gsap: { ...desktop, gsap: true },
    clips: { ...phone, names: clips }, clipsReduced: { ...desktop, reduce: true, names: clips }, clipsSaveData: { ...phone, saveData: true, names: clips } };
  const out = {};
  for (const [name, env] of Object.entries(cases)) out[name] = await run(env);
  const heroes = { heroDesktop: desktop, heroComplete: { ...desktop, complete: true }, heroReduced: { ...desktop, reduce: true },
    heroSaveData: { ...phone, saveData: true }, heroPhone: { ...phone, narrow: true } };
  for (const [name, env] of Object.entries(heroes)) out[name] = await runHero(env);
  console.log(JSON.stringify(out));
})();
"""

# Daylight (Task 34): reel.js's Work tile previews and the About film's progress, against the stub DOM. A tile makes its
# silent preview <video> only when first wanted (hover or focus on fine pointers, centred on touch), plays one at a time,
# stops on leave, blur, a hidden tab or Pause motion, and never starts under reduced motion or Save-Data. The film's bar
# and time follow the video while it plays.
PREVIEW_SCRIPT = HARNESS + r"""
// Task 41: site.js owns the Pause motion button and runs first on every page (deferred, in order), so it runs first here.
const source = fs.readFileSync(require('path').join(require('path').dirname(process.argv[1]), 'site.js'), 'utf8') + '\n' + fs.readFileSync(process.argv[1], 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));
function makeVideo(name) {
  const video = element(name, { source: [element('source')] });
  Object.assign(video, { paused: true, muted: false, plays: 0, loads: 0, currentTime: 0, duration: NaN, style: {} });
  const fire = type => (video.listeners[type] || []).forEach(fn => fn({ type }));
  video.fire = fire;
  video.load = () => { video.loads++; };
  video.play = () => { video.plays++; video.paused = false; fire('play'); fire('playing'); return Promise.resolve(); };
  video.pause = () => { if (!video.paused) { video.paused = true; fire('pause'); } };
  return video;
}
async function run(env) {
  const created = [];
  const tiles = ['hb', 'gl', 'fc'].map(name => {
    const a = element('a-' + name);
    const frame = element('frame-' + name);
    frame.dataset.hoverSrc = '/assets/video/loop-' + name + '-desktop.mp4';
    frame.closest = selector => (selector === 'a' ? a : null);
    frame.appended = [];
    frame.appendChild = child => { frame.appended.push(child); };
    return { a, frame };
  });
  // Work also has device loops, so Pause motion is wired; one stands in for them.
  const loop = makeVideo('loop'); loop.dataset.loop = '';
  const motion = element('motion'); motion.hidden = true; motion.attrs['aria-pressed'] = 'false';
  motion.classList = classList(['motion-btn', 'motion-fab']);
  // The About film: a large reel with its button, progress bar and time.
  const film = makeVideo('film'); film.parts.source[0].attrs.src = '/assets/video/cendavo-launch-1600.mp4'; film.attrs.controls = '';
  const toggle = element('toggle'); toggle.hidden = true; toggle.textContent = 'Play film';
  const ui = element('ui'); ui.hidden = true;
  const bar = element('bar'); const time = element('time'); time.textContent = '0:00 / 0:20';
  const reel = element('reel', { video: [film], '[data-reel-toggle]': [toggle], '[data-reel-ui]': [ui], '[data-progress]': [bar], '[data-time]': [time] });
  const parts = { '[data-reel]': env.film ? [reel] : [], '[data-hover-src]': tiles.map(t => t.frame), 'video[data-loop]': [loop], '[data-motion-toggle]': [motion] };
  const doc = { documentElement: element('html'), readyState: 'complete', hidden: false, listeners: {}, activeElement: null,
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [],
    createElement: tag => { const v = makeVideo('preview' + created.length); v.tagName = tag; created.push(v); return v; } };
  const observers = [], frames = [];
  class FakeObserver { constructor(callback, options) { this.callback = callback; this.options = options; this.targets = []; observers.push(this); } observe(target) { this.targets.push(target); } }
  const { win } = makeWindow(env, { IntersectionObserver: FakeObserver, navigator: env.saveData ? { connection: { saveData: true } } : { connection: {} },
    requestAnimationFrame: fn => frames.push(fn), cancelAnimationFrame: () => {} });
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: doc, setImmediate }); } catch (e) { error = String(e); }
  const fire = (el, type) => (el.listeners[type] || []).forEach(fn => fn({ type }));
  const state = () => tiles.map(t => { const v = t.frame.appended[0]; return v ? (v.paused ? 'paused' : 'playing') : 'none'; });
  const out = { error, steps: [], tileObservers: observers.filter(o => tiles.some(t => o.targets.includes(t.frame))).map(o => o.options) };
  const step = async (name, act) => { act(); await settle(); out.steps.push([name, state()]); };
  out.steps.push(['loaded', state()]);
  if (env.fine) {
    await step('hover first', () => fire(tiles[0].a, 'pointerenter'));
    await step('hover second', () => fire(tiles[1].a, 'pointerenter'));
    await step('leave second', () => fire(tiles[1].a, 'pointerleave'));
    await step('focus third', () => fire(tiles[2].a, 'focus'));
    await step('blur third', () => fire(tiles[2].a, 'blur'));
    await step('hover first again', () => fire(tiles[0].a, 'pointerenter'));
    await step('tab hidden', () => { doc.hidden = true; (doc.listeners.visibilitychange || []).forEach(fn => fn()); });
    await step('hover while hidden', () => { fire(tiles[1].a, 'pointerleave'); fire(tiles[1].a, 'pointerenter'); });
    doc.hidden = false; (doc.listeners.visibilitychange || []).forEach(fn => fn());
    await step('pause motion', () => fire(motion, 'click'));
    await step('hover while held', () => fire(tiles[2].a, 'pointerenter'));
  } else {
    const centre = async (i, on) => { observers.filter(o => o.targets.includes(tiles[i].frame)).forEach(o => o.callback([{ isIntersecting: on, target: tiles[i].frame }])); await settle(); };
    await centre(0, true); out.steps.push(['first centred', state()]);
    await centre(1, true); out.steps.push(['second centred', state()]);
    await centre(1, false); out.steps.push(['second off centre', state()]);
  }
  out.created = created.map(v => ({ tag: v.tagName, src: v.src || null, attrs: v.attrs, muted: v.muted, className: v.className }));
  out.listened = tiles.map(t => Object.keys(t.a.listeners).sort());
  if (env.film) {
    film.duration = 20; film.currentTime = 5;
    fire(toggle, 'click'); await settle();
    frames.splice(0).forEach(fn => fn());
    out.film = { ui: ui.hidden, button: toggle.hidden, label: toggle.textContent, transform: bar.style.transform || null, time: time.textContent };
    film.currentTime = 15; film.pause(); await settle();
    out.filmPaused = { label: toggle.textContent, transform: bar.style.transform, time: time.textContent };
  }
  return out;
}
(async () => {
  const desktop = { width: 1440, height: 900, fine: true, reduce: false };
  const phone = { width: 390, height: 844, fine: false, reduce: false };
  const out = {};
  for (const [name, env] of Object.entries({ desktop: { ...desktop, film: true }, phone, reduced: { ...desktop, reduce: true },
    saveData: { ...desktop, saveData: true }, phoneReduced: { ...phone, reduce: true } })) out[name] = await run(env);
  console.log(JSON.stringify(out));
})();
"""

# Night Shift Task 29: runs assets/home.js's one-time before/after demo sweep and the showreel entrance with the recording
# GSAP stub. The sweep timeline is driven step by step by hand; writes to the range value and its attributes are counted.
SWEEP_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const range = element('range'), before = element('before'), after = element('after'), controls = element('controls');
  const figure = element('figure');
  before.dataset.compareSet = '0'; after.dataset.compareSet = '100'; controls.hidden = true;
  controls.parts = { 'input[type="range"]': [range], '[data-compare-set]': [before, after] };
  figure.parts = { '[data-compare-controls]': [controls] };
  let value = '50', valueWrites = 0;
  Object.defineProperty(range, 'value', { get: () => value, set: v => { valueWrites++; value = String(v); } });
  const attrWrites = [];
  range.setAttribute = (key, v) => { attrWrites.push(key); range.attrs[key] = String(v); };
  const pressed = [];
  [before, after].forEach(b => { b.setAttribute = (key, v) => { pressed.push(key); b.attrs[key] = String(v); }; });
  const video = element('video'), cap = element('cap'), toggle = element('toggle'), frame = element('frame');
  const reel = element('reel', { video: [video], '.reel-frame': [frame], '.reel-cap, [data-reel-toggle]': [cap, toggle] });
  reel.getBoundingClientRect = () => ({ left: 0, top: env.reelTop === undefined ? 2000 : env.reelTop, width: 1200, height: 675 });
  const root = element('html'); root.classList = classList(['js', 'motion']);
  // Liquid Glass (Task 37): the showreel's lens is the frame; the chapter panel stands in at the reel's position.
  const parts = { '[data-compare]': [figure], '[data-reel]': [reel], '.reel-frame': [frame], '.reel-panel': [reel] };
  const doc = { documentElement: root, querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const { win, listeners } = makeWindow(env, { requestAnimationFrame: () => 1, cancelAnimationFrame() {} });
  let log = null;
  if (env.gsap) {
    const stub = makeGsap(env);
    const base = stub.gsap.timeline;
    stub.gsap.timeline = vars => {
      const tl = base(vars);
      tl.killed = 0; tl.targets = [];
      tl.kill = () => { tl.killed++; };
      const to = tl.to;
      tl.to = (t, v, p) => { tl.targets.push(t); return to(t, v, p); };
      return tl;
    };
    win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; log = stub.log;
  }
  vm.runInNewContext(source, { window: win, document: doc });
  const pos = () => figure.style.props['--pos'];
  const stopCount = () => ['pointerdown', 'keydown', 'touchstart'].reduce((n, t) => n + (listeners[t] || []).length, 0);
  const out = { initialPos: pos(), creates: log ? log.creates.length : 0 };
  if (log) {
    const entrance = log.tweens.filter(t => t.kind === 'fromTo');
    out.entrance = entrance.map(t => ({ names: t.names, from: t.from, to: { ...t.vars, scrollTrigger: undefined },
      trigger: t.vars.scrollTrigger ? { scrub: t.vars.scrollTrigger.scrub || null, once: Boolean(t.vars.scrollTrigger.once), pin: 'pin' in t.vars.scrollTrigger } : null }))
      .filter(t => t.names[0] === 'frame' || t.names[0] === 'reel');
  }
  if (env.touchFirst) { value = '30'; range.listeners.input[0](); }
  const sweepTrigger = log ? log.creates.find(c => c.trigger === figure) : null;
  out.trigger = sweepTrigger ? { start: sweepTrigger.start, once: sweepTrigger.once } : null;
  const valueWritesBefore = valueWrites, attrWritesBefore = attrWrites.length, pressedBefore = pressed.length;
  const timelinesBefore = log ? log.timelines.length : 0;
  if (sweepTrigger) sweepTrigger.onEnter();
  const sweep = log && log.timelines.length > timelinesBefore ? log.timelines[log.timelines.length - 1] : null;
  out.started = Boolean(sweep);
  out.positions = [];
  out.stopListeners = stopCount();
  out.passive = ['pointerdown', 'keydown', 'touchstart'].map(t => (listeners[t] || []).every(l => l.options && l.options.passive));
  if (sweep) {
    out.duration = sweep.duration();
    sweep.tweens.forEach((tween, i) => {
      if (sweep.killed || (env.stopAfter !== undefined && i > env.stopAfter)) return;
      sweep.targets[i].p = tween.vars.p; tween.vars.onUpdate(); out.positions.push(pos());
      if (i === env.stopAfter) {
        let prevented = false;
        if (env.stopWith === 'input') { value = '30'; range.listeners.input[0](); }
        else (listeners[env.stopWith] || []).slice().forEach(l => l.fn({ type: env.stopWith, preventDefault() { prevented = true; } }));
        out.prevented = prevented;
      }
    });
    if (!sweep.killed && env.stopAfter === undefined) sweep.vars.onComplete();
    out.killed = sweep.killed;
  }
  out.sweepValueWrites = valueWrites - valueWritesBefore;
  out.sweepAttrWrites = attrWrites.slice(attrWritesBefore);
  out.sweepPressedWrites = pressed.length - pressedBefore;
  out.finalPos = pos();
  out.value = value;
  out.stopListenersAfter = stopCount();
  // A second entry into view (or a reload of the trigger) never starts another sweep.
  const timelinesNow = log ? log.timelines.length : 0;
  if (sweepTrigger) sweepTrigger.onEnter();
  out.secondStart = log ? log.timelines.length > timelinesNow : false;
  return out;
}
const desktop = { width: 1440, height: 900, fine: true, reduce: false, gsap: true };
console.log(JSON.stringify({
  complete: run(desktop),
  key: run({ ...desktop, stopAfter: 0, stopWith: 'keydown' }),
  pointer: run({ ...desktop, stopAfter: 1, stopWith: 'pointerdown' }),
  touch: run({ ...desktop, stopAfter: 0, stopWith: 'touchstart' }),
  input: run({ ...desktop, stopAfter: 0, stopWith: 'input' }),
  touchedFirst: run({ ...desktop, touchFirst: true }),
  phone: run({ width: 390, height: 844, fine: false, reduce: false, gsap: true }),
  onScreen: run({ ...desktop, reelTop: 300 }),
  reduced: run({ ...desktop, reduce: true }),
  plain: run({ ...desktop, gsap: false }),
}));
"""

# Night Shift Task 29: runs assets/details.js (step count-up, card tilt, cursor ring) with the recording GSAP stub.
DETAILS_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const below = (name, text) => { const el = element(name); el.textContent = text; el.getBoundingClientRect = () => ({ left: 0, top: 2000, width: 80, height: 40 }); return el; };
  const steps = ['01', '02', '03', '04', '05'].map((n, i) => below('step' + i, n));
  const onScreen = element('stepOnScreen'); onScreen.textContent = '01';
  const cards = many('card', 3);
  const body = element('body');
  const created = [];
  body.appendChild = child => { body.children.push(child); };
  const make = tag => {
    const el = element(tag + created.length);
    el.appendChild = child => { el.children.push(child); };
    el.remove = () => { body.children = body.children.filter(c => c !== el); };
    created.push(el);
    return el;
  };
  const root = element('html'); root.classList = classList(['js', 'motion']);
  const parts = { '.step-n': steps.concat(onScreen), '.teaser-card, .wk-tile': cards };
  const doc = { documentElement: root, body, createElement: make, querySelectorAll: s => parts[s] || [], querySelector: s => (parts[s] || [])[0] || null,
    listeners: {}, addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }, removeEventListener() {} };
  const { win, listeners } = makeWindow(env);
  let log = null;
  if (env.gsap) { const stub = makeGsap(env); win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; log = stub.log; }
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: doc }); } catch (e) { error = String(e); }
  const out = { error, queries: log ? log.queries : [], ring: body.children.map(el => ({ className: el.className, attrs: el.attrs, children: el.children.length })),
    textsAtStart: steps.map(el => el.textContent), onScreenText: onScreen.textContent };
  out.stepAttrWrites = steps.reduce((n, el) => n + Object.keys(el.attrs).length, 0);
  if (!log) return out;
  const counts = log.tweens.filter(t => t.kind === 'to' && t.vars && 'n' in t.vars);
  out.counts = counts.map(t => ({ n: t.vars.n, once: Boolean(t.vars.scrollTrigger && t.vars.scrollTrigger.once), start: t.vars.scrollTrigger && t.vars.scrollTrigger.start }));
  counts.forEach(t => { t.vars.onUpdate(); t.vars.onComplete(); });
  out.textsAfter = steps.map(el => el.textContent);
  out.perspective = log.sets.filter(v => 'transformPerspective' in v).map(v => v.transformPerspective);
  // Tilt: the pointer far outside the card in every direction stays clamped.
  log.quick.length = 0;
  cards.forEach(card => (card.listeners.pointermove || []).forEach(fn => { fn({ clientX: -5000, clientY: 9000 }); fn({ clientX: 9000, clientY: -5000 }); }));
  out.tilt = log.quick.filter(([prop]) => prop === 'rotationX' || prop === 'rotationY').map(([, v]) => v);
  log.quick.length = 0;
  cards.forEach(card => (card.listeners.pointerleave || []).forEach(fn => fn({})));
  out.leave = log.quick.map(([, v]) => v);
  // Cursor ring: follows a mouse, grows over links, steps aside over form fields, ignores touch and pen-less taps.
  const ring = body.children[0];
  const target = matches => ({ closest: sel => (matches.some(m => sel.split(', ').includes(m)) ? {} : null) });
  const move = (event) => { log.quick.length = 0; log.tweens.length = 0; (listeners.pointermove || []).forEach(l => l.fn(event)); };
  if (ring) {
    out.passiveMove = (listeners.pointermove || []).every(l => l.options && l.options.passive);
    move({ pointerType: 'touch', clientX: 10, clientY: 10, target: target([]) });
    out.touchMoves = log.quick.length;
    move({ pointerType: 'mouse', clientX: 300, clientY: 200, target: target([]) });
    out.follow = log.quick.slice();
    out.shown = log.tweens.filter(t => t.names[0] === ring.name).map(t => t.vars.opacity);
    move({ pointerType: 'mouse', clientX: 310, clientY: 210, target: target(['a']) });
    out.overLink = ring.classList.contains('is-link');
    move({ pointerType: 'mouse', clientX: 320, clientY: 220, target: target(['input']) });
    out.overField = { link: ring.classList.contains('is-link'), opacity: log.tweens.filter(t => t.names[0] === ring.name).map(t => t.vars.opacity) };
    move({ pointerType: 'mouse', clientX: 330, clientY: 230, target: target(['p']) });
    out.backOverText = log.tweens.filter(t => t.names[0] === ring.name).map(t => t.vars.opacity);
    log.tweens.length = 0;
    (doc.listeners.pointerout || []).forEach(fn => fn({ relatedTarget: null }));
    out.leftWindow = log.tweens.filter(t => t.names[0] === ring.name).map(t => t.vars.opacity);
  }
  return out;
}
console.log(JSON.stringify({
  desktop: run({ width: 1440, height: 900, fine: true, reduce: false, gsap: true }),
  touch: run({ width: 390, height: 844, fine: false, reduce: false, gsap: true }),
  reduced: run({ width: 1440, height: 900, fine: true, reduce: true, gsap: true }),
  plain: run({ width: 1440, height: 900, fine: true, reduce: false, gsap: false }),
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
    const lineTo = (opening.find(t => t.names[0] === 'line0') || {}).vars || null;
    out.lineTo = lineTo ? { yPercent: lineTo.yPercent, y: lineTo.y, clearProps: lineTo.clearProps || null } : null;
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

# Task 43: motion.js with a [data-stagger] list inside a [data-rise] card and one list on its own, all below the fold.
# The batch is recorded with its options, so the card's line and the nested list's trigger can be compared.
MOTION_STAGGER_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
const low = el => { el.getBoundingClientRect = () => ({ left: 0, top: 2000, width: 100, height: 100 }); return el; };
const card = low(element('card')), nested = low(element('nested')), alone = low(element('alone'));
nested.children = many('n', 3); alone.children = many('a', 2);
card.closest = s => (s.split(', ').includes('[data-rise]') ? card : null);
nested.parentElement = card;
alone.parentElement = { closest: () => null };
const root = element('html'); root.classList = classList(['js', 'motion']);
const parts = { '[data-rise]': [card], '[data-stagger]': [nested, alone] };
const doc = { documentElement: root, querySelectorAll: s => parts[s] || [], querySelector: s => (parts[s] || [])[0] || null };
const env = { width: 1440, height: 900, fine: true, reduce: false };
const { win } = makeWindow(env);
const stub = makeGsap(env);
const batches = [];
stub.ScrollTrigger.batch = (targets, vars) => batches.push({ names: targets.map(t => t.name), start: vars.start, once: vars.once });
win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger;
vm.runInNewContext(source, { window: win, document: doc });
const lists = stub.log.tweens.filter(t => t.kind === 'fromTo' && t.vars.scrollTrigger && t.vars.stagger === 0.06)
  .map(t => ({ first: t.names[0], trigger: t.vars.scrollTrigger.trigger.name, start: t.vars.scrollTrigger.start, once: t.vars.scrollTrigger.once }));
console.log(JSON.stringify({ batches, lists }));
"""

# Task 43: scenes.js's Services cards ("Every month", "Old addresses, redirected") below the fold, with and without motion.
SCENES_CARDS_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const low = el => { el.getBoundingClientRect = () => ({ left: 0, top: 2000, width: 100, height: 100 }); return el; };
  const month = low(element('month', { li: many('mli', 3), '.box': many('box', 3) }));
  const redir = low(element('redir', { li: many('rli', 2), '.arr': many('arr', 2) }));
  const parts = { '[data-month]': [month], '[data-redir]': [redir] };
  const doc = { documentElement: element('html'), querySelectorAll: s => parts[s] || [], querySelector: s => (parts[s] || [])[0] || null };
  const { win } = makeWindow(env);
  const stub = makeGsap(env);
  win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger;
  vm.runInNewContext(source, { window: win, document: doc });
  return stub.log.timelines.map(tl => ({ trigger: tl.vars.scrollTrigger.trigger.name, start: tl.vars.scrollTrigger.start, once: tl.vars.scrollTrigger.once,
    steps: tl.tweens.map(t => ({ first: t.names[0], at: t.at, from: t.from || null })) }));
}
console.log(JSON.stringify({ motion: run({ width: 1440, height: 900, fine: true, reduce: false }), reduced: run({ width: 1440, height: 900, fine: true, reduce: true }) }));
"""
SCENES = Path(__file__).resolve().parents[1] / 'assets' / 'scenes.js'

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
        # Without GSAP the CSS hold on the hero is released at once and the booking card keeps its final, static state.
        self.assertNotIn('ph-wait', plain['classes'])
        self.assertEqual(plain['stage'], {'booked': True, 'picked': True})
        # With GSAP the buttons glide via a tween but end in the same state.
        for name in ('first', 'released', 'reduced', 'phone'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['click'], plain['click'])
                self.assertFalse(r[name]['autoAlpha'])
                self.assertFalse(r[name]['snap'])
        self.assertEqual(r['first']['glides'], 1)
        self.assertEqual(r['reduced']['glides'], 0)  # reduced motion: the divider jumps
        self.assertEqual(r['first']['plugins'], 1)
        # Every motion query sits behind the reduced-motion guard.
        for query in r['first']['queries']:
            with self.subTest(query=query):
                self.assertTrue(all('prefers-reduced-motion' in part for part in query.split(', ')))
        # Reduced motion: nothing is animated, nothing is pinned or scrubbed, no marquee runs, the card stays final.
        reduced = r['reduced']
        self.assertIsNone(reduced['heroEnd'])
        self.assertEqual((reduced['pins'], reduced['scrubs'], reduced['scrollTimelines'], reduced['marquee'], reduced['reveals']), (0, [], [], 0, []))
        self.assertEqual(reduced['stage'], plain['stage'])

    def test_home_hero_plays_once_within_five_seconds(self):
        # The opening (headline, copy, the two glass cards from depth, then the booking) is one timeline that plays once, at
        # load, and is over by 5 s (WCAG 2.2.2: everything that keeps moving has the Pause motion button). It only plays while
        # CSS still holds the hero; after the failsafe has let go nothing is hidden again.
        r = self.node_json(HOME_SCRIPT, HOME)
        for name in ('first', 'phone'):
            with self.subTest(case=name):
                result = r[name]
                self.assertEqual(result['heroPlayed'], [0])
                self.assertGreater(result['heroEnd'], 3)
                self.assertLessEqual(result['heroEnd'], 5)
                self.assertNotIn('ph-wait', result['classes'])
                self.assertEqual(result['notOnce'], 1)  # only the marquee's in-view trigger repeats; the sweep runs once
                self.assertEqual(result['marquee'], 1)
        released = r['released']
        self.assertIsNone(released['heroEnd'])
        self.assertIsNone(released['heroPlayed'])
        self.assertNotIn('ph-wait', released['classes'])
        self.assertEqual(released['stage'], {'booked': True, 'picked': True})

    def test_home_hero_takes_over_the_css_hold_without_a_flash(self):
        # Night Shift Task 23: fromTo applies the start states at once (matching the CSS held under .ph-wait), then home.js
        # removes .ph-wait. Liquid Glass (Task 37): the lines, the copy, the card layer, then the cards themselves.
        r = self.node_json(HOME_SCRIPT, HOME)
        for name in ('first', 'phone'):
            with self.subTest(case=name):
                kinds, names = r[name]['openingKinds'], r[name]['openingNames']
                self.assertTrue(kinds)
                self.assertEqual(set(kinds), {'fromTo'})
                self.assertEqual(names, ['line0', 'fade0', 'deck', 'card0'])

    def test_home_stage_starts_unbooked_and_ends_in_the_static_state(self):
        # The booking starts from the "before" state (set while the cards are still held hidden) and finishes in exactly the
        # state the static page shows: 10:30 picked at 2.6 s, booked at 3.3 s.
        r = self.node_json(HOME_SCRIPT, HOME)
        first = r['first']
        self.assertEqual(first['atStart'], {'booked': False, 'picked': False})
        self.assertEqual(first['progressedAtStart'], [])
        self.assertEqual(first['callbacks'], [2.6, 3.3])
        self.assertEqual(first['atEnd'], {'booked': True, 'picked': True})

    def test_home_motion_uses_exactly_the_two_css_curves(self):
        # Entrances on cubic-bezier(.2,.8,.2,1), changes of state on cubic-bezier(.7,0,.2,1). home.js solves them like CSS
        # does; compare against an independent solver. Scroll-linked tweens use 'none' (the scroll is the easing).
        def css_bezier(x1, y1, x2, y2, x):
            at = lambda t, a, b: 3 * a * t * (1 - t) ** 2 + 3 * b * t * t * (1 - t) + t ** 3
            low, high = 0.0, 1.0
            for _ in range(60):
                mid = (low + high) / 2
                if at(mid, x1, x2) < x:
                    low = mid
                else:
                    high = mid
            return at((low + high) / 2, y1, y2)
        r = self.node_json(HOME_SCRIPT, HOME)
        first = r['first']
        self.assertEqual(first['defaultEase'], 'function')
        self.assertTrue(set(first['tweenEases']) <= {'function', 'undefined'})  # undefined: the timeline default (OUT)
        xs = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]
        for name, curve in (('out', (0.2, 0.8, 0.2, 1)), ('io', (0.7, 0, 0.2, 1))):
            for x, y in zip(xs, first['curves'][name]):
                with self.subTest(curve=name, x=x):
                    self.assertAlmostEqual(y, css_bezier(*curve, x), places=4)
        for timeline in first['scrollTimelines']:
            for tween in timeline['tweens']:
                self.assertEqual(tween['ease'], 'none')
        for scrub in first['scrubs']:
            self.assertEqual(scrub['ease'], 'none')

    def test_pause_motion_jumps_the_choreography_to_its_end(self):
        # The Pause motion button (owned by site.js since Task 41, which flips aria-pressed first) also ends the opening at once in its
        # final state; pressing it again never replays it. With Save-Data the button starts pressed, so the opening is skipped
        # straight to its end.
        r = self.node_json(HOME_SCRIPT, HOME)
        press = r['press']['afterPress']
        self.assertIn(1, press['progressed'])
        self.assertEqual(press['stage'], {'booked': True, 'picked': True})
        self.assertEqual(r['press']['resumeProgressCalls'], 0)
        held = r['held']
        self.assertEqual(held['heroPlayed'], [])
        self.assertEqual(held['progressedAtStart'], [1])
        self.assertEqual(held['atStart'], {'booked': True, 'picked': True})
        self.assertNotIn('ph-wait', held['classes'])

    def test_home_has_no_pin_and_scroll_motion_is_transform_opacity_or_clip_only(self):
        # Liquid Glass (Task 37): the owner asked for bolder, scroll-linked 3D motion. Still nothing is pinned by script (the
        # hero stage is CSS sticky) and every scroll-linked tween moves transform, opacity or clip-path only, with one shared
        # smoothing. Wide screens: the hero exit (which also feeds the WebGL scene's progress) and the phones' fly-in; every
        # screen: the showreel lens. Below-the-fold pieces reveal once; what is already on screen is left alone.
        r = self.node_json(HOME_SCRIPT, HOME)
        allowed = {'x', 'y', 'z', 'xPercent', 'yPercent', 'scale', 'rotationX', 'rotationY', 'rotationZ', 'opacity', 'clipPath',
                   'transformPerspective', 'transformOrigin', 'duration', 'ease', 'immediateRender', 'stagger', 'delay', 'clearProps'}
        for name in ('first', 'released', 'held', 'phone'):
            with self.subTest(case=name):
                result = r[name]
                self.assertEqual(result['pins'], 0)
                self.assertEqual([s['names'] for s in result['scrubs']], [['reelFrame']])
                timelines = result['scrollTimelines']
                self.assertEqual(len(timelines), 0 if name == 'phone' else 2)
                for scrub in [s['scrub'] for s in result['scrubs']] + [t['scrub'] for t in timelines]:
                    self.assertEqual(scrub, 0.6)
                for timeline in timelines:
                    self.assertFalse(timeline['pin'])
                    for tween in timeline['tweens']:
                        self.assertTrue(set(tween['props']) <= allowed, tween['props'])
                for scrub in result['scrubs']:
                    self.assertTrue(set(scrub['props']) <= allowed, scrub['props'])
                self.assertEqual(sorted(result['reveals']), ['bandPanel', 'glassFrame', 'reelPanel', 'rise0', 'teaser0', 'teaser1', 'teaser2'])
        self.assertEqual(r['first']['heroP'], 0.4)  # the hero's scroll progress reaches the WebGL scene
        self.assertIsNone(r['phone']['heroP'])
        js = HOME.read_text(encoding='utf-8')
        for gone in ('pin:', 'PIN_', 'STACK_QUERY', 'work-exit', 'work-count', 'is-pinned', '[data-work]', '.proj', "--w'", "--sw'", 'repeat:', 'yoyo'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, js)

    def test_showreel_picks_the_cut_for_the_screen(self):
        # (a) At 640px and below the vertical cut and poster; above it the 1600 ones (home.css switches the frame at the same width).
        r = self.node_json(REEL_SCRIPT, REEL)
        wide = ('/assets/glass/glass-reel-1600.mp4', '/assets/glass/glass-reel-poster.jpg')
        narrow = ('/assets/glass/glass-reel-vertical-720.mp4', '/assets/glass/glass-reel-vertical-poster.jpg')
        for name, expected in (('desktop', wide), ('wide', wide), ('phone', narrow), ('edge', narrow)):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['error'])
                self.assertEqual((r[name]['src'], r[name]['poster']), expected)
        self.assertEqual(r['phone']['loads'], 1)  # load() picks up the new source; preload="none" means nothing downloads yet
        self.assertEqual(r['desktop']['loads'], 0)
        for path in wide + narrow:
            self.assertTrue((HOME.parents[1] / path.lstrip('/')).is_file(), path)

    def test_showreel_swaps_native_controls_for_one_labelled_button(self):
        # (b) JS removes the native controls and shows a type="button" toggle whose label follows the real playback state.
        r = self.node_json(REEL_SCRIPT, REEL)
        for name, result in r.items():
            if 'multi' in result or name.startswith('hero'):
                continue  # clips: test_every_reel_on_a_page_plays_and_pauses_on_its_own; the homepage: the hero loop tests
            with self.subTest(case=name):
                self.assertIsNone(result['error'])
                self.assertFalse(result['controls'])
                self.assertFalse(result['hidden'])
                self.assertEqual(result['type'], 'button')
                self.assertTrue(result['muted'])
                self.assertEqual(result['initial'], {'playing': False, 'label': 'Play showreel', 'plays': 0})  # nothing before it is seen
                for step, state in result['steps']:
                    self.assertEqual(state['label'], 'Pause showreel' if state['playing'] else 'Play showreel', step)

    def test_showreel_plays_in_view_and_remembers_a_pause(self):
        # (c) Plays when in view, pauses when it leaves; (d) after Pause, coming back into view does not resume it.
        r = self.node_json(REEL_SCRIPT, REEL)
        for name in ('desktop', 'phone', 'gsap'):
            with self.subTest(case=name):
                result = r[name]
                self.assertEqual(result['observed'], 1)
                self.assertGreater(result['threshold'], 0)
                self.assertEqual([(step, state['playing']) for step, state in result['steps']],
                                 [('in view', True), ('out of view', False), ('back in view', True), ('press', False),
                                  ('out of view', False), ('back in view', False), ('press', True), ('out of view', False)])
                self.assertEqual(result['steps'][5][1]['label'], 'Play showreel')

    def test_showreel_never_starts_itself_with_reduced_motion_or_save_data(self):
        # (e) Reduced motion and (g) Save-Data: no play() call until the visitor presses Play; the button offers "Play showreel".
        r = self.node_json(REEL_SCRIPT, REEL)
        for name in ('reduced', 'saveData'):
            with self.subTest(case=name):
                steps = r[name]['steps']
                for step, state in steps[:3]:
                    self.assertEqual(state, {'playing': False, 'label': 'Play showreel', 'plays': 0}, step)
                self.assertEqual(steps[3], ['press', {'playing': True, 'label': 'Pause showreel', 'plays': 1}])
                self.assertFalse(steps[4][1]['playing'])  # leaving the view still pauses it

    def test_showreel_survives_refused_playback_and_missing_apis(self):
        # (f) A refused play() (iOS Low Power Mode) or a throwing one leaves "Play showreel" and throws nothing; without
        # IntersectionObserver nothing autoplays but the button still works; (h) it needs no GSAP.
        r = self.node_json(REEL_SCRIPT, REEL)
        for name in ('refuse', 'throws'):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['error'])
                self.assertGreater(r[name]['steps'][0][1]['plays'], 0)  # it tried
                for step, state in r[name]['steps']:
                    self.assertEqual((state['playing'], state['label']), (False, 'Play showreel'), step)
        no_observer = r['noObserver']
        self.assertEqual(no_observer['observed'], 0)
        self.assertEqual(no_observer['steps'][2][1], {'playing': False, 'label': 'Play showreel', 'plays': 0})
        self.assertEqual(no_observer['steps'][3][1], {'playing': True, 'label': 'Pause showreel', 'plays': 1})
        self.assertEqual(r['desktop']['steps'], r['gsap']['steps'])  # the same with or without GSAP
        # Task 29: the controller lives in reel.js, which never touches GSAP, so a missing GSAP never stops it; home.js no
        # longer plays or pauses anything.
        js = REEL.read_text(encoding='utf-8')
        for needle in ('window.gsap', 'gsap.', 'ScrollTrigger'):
            self.assertNotIn(needle, js)
        home = HOME.read_text(encoding='utf-8')
        for needle in ('video.play(', 'video.pause(', 'IntersectionObserver', "removeAttribute('controls')"):
            self.assertNotIn(needle, home)

    def test_hero_loops_start_only_after_load_and_idle_and_follow_the_tab(self):
        # Daylight (Task 33): the hero's laptop and phone loops share reel.js with the showreel. They are muted, observed and
        # start only once the page has loaded and gone idle (so they never compete with first paint), pause with the tab
        # hidden and resume when it is back. The showreel needs no load wait. Order: laptop, phone, showreel.
        r = self.node_json(REEL_SCRIPT, REEL)
        hero = r['heroDesktop']
        self.assertIsNone(hero['error'])
        self.assertEqual(hero['muted'], [True, True, True])
        self.assertEqual(hero['observed'], [1, 1, 1])
        self.assertEqual(hero['loadListeners'], 1)
        self.assertFalse(hero['motionHidden'])
        self.assertEqual(hero['pressed'], 'false')
        steps = [(name, playing) for name, playing, _ in hero['steps']]
        self.assertEqual(steps[:5], [('in view', [False, False, True]), ('loaded', [False, False, True]), ('idle', [True, True, True]),
                                     ('tab hidden', [False, False, False]), ('tab visible', [True, True, True])])
        # Already loaded when the script runs: no wait, no load listener.
        complete = r['heroComplete']
        self.assertEqual(complete['loadListeners'], 0)
        self.assertEqual(complete['steps'][0][1], [True, True, True])

    def test_pause_motion_holds_every_video_until_pressed_again(self):
        r = self.node_json(REEL_SCRIPT, REEL)
        steps = {name: (playing, pressed) for name, playing, pressed in r['heroDesktop']['steps']}
        self.assertEqual(steps['pause motion'], ([False, False, False], 'true'))
        self.assertEqual(steps['back in view, paused'], ([False, False, False], 'true'))  # coming back into view does not resume
        self.assertEqual(steps['play motion'], ([True, True, True], 'false'))
        self.assertEqual(steps['hero out of view'], ([False, False, True], 'false'))  # still only plays in view
        # Reduced motion or Save-Data: the button starts pressed (motion paused) and nothing plays by itself, even after
        # load; pressing it plays what is in view.
        # (heroSaveData runs at phone width, so its laptop never plays: see the narrow-width test below.)
        for name, released in (('heroReduced', [True, True, True]), ('heroSaveData', [False, True, True])):
            with self.subTest(case=name):
                result = dict((n, (p, a)) for n, p, a in r[name]['steps'])
                self.assertEqual(r[name]['pressed'], 'true')
                for step in ('in view', 'loaded', 'idle', 'tab visible'):
                    self.assertEqual(result[step], ([False, False, False], 'true'), step)
                self.assertEqual(result['pause motion'], (released, 'false'))

    def test_hero_loop_files_are_requested_only_on_first_play(self):
        # Daylight (Task 33): the hero sources ship as data-src. reel.js sets src and calls load() once, right before the
        # first play(); without a play (reduced motion, Save-Data, never in view) no file is ever requested.
        r = self.node_json(REEL_SCRIPT, REEL)
        for name in ('heroDesktop', 'heroComplete'):
            with self.subTest(case=name):
                for loop, file in zip(r[name]['loops'], ('loop-hb-desktop', 'loop-hb-phone')):
                    self.assertEqual(loop['src'], f'/assets/video/{file}.mp4')
                    self.assertEqual(loop['loads'], 1)  # once, however often it is paused and resumed
                    self.assertGreaterEqual(loop['plays'], 2)

    def test_phones_never_play_or_load_the_laptop_loop(self):
        # Strategist brief 33a item 6: at 640px and below only the phone loop plays (about half the hero video data). The
        # laptop video is never observed, played or loaded, and its source never gets a src, even after Pause motion is
        # released; it keeps its CSS poster. Above 640px both play (heroDesktop, 1440px).
        r = self.node_json(REEL_SCRIPT, REEL)
        for name in ('heroPhone', 'heroSaveData'):
            with self.subTest(case=name):
                laptop, phone = r[name]['loops']
                self.assertIsNone(r[name]['error'])
                self.assertEqual(laptop, {'src': None, 'loads': 0, 'plays': 0, 'observed': 0})
                self.assertEqual((phone['src'], phone['loads'], phone['observed']), ('/assets/video/loop-hb-phone.mp4', 1, 1))
                self.assertGreaterEqual(phone['plays'], 1)
                self.assertFalse(r[name]['motionHidden'])  # the phone loop still has its Pause motion button
                self.assertTrue(all(not playing[0] for _, playing, _ in r[name]['steps']))
        steps = {name: playing for name, playing, _ in r['heroPhone']['steps']}
        self.assertEqual(steps['idle'], [False, True, True])
        self.assertEqual(steps['play motion'], [False, True, True])
        self.assertEqual(r['heroDesktop']['loops'][0]['observed'], 1)

    def test_showreel_chapters_seek_play_and_mark_the_current_one(self):
        r = self.node_json(REEL_SCRIPT, REEL)
        hero = r['heroDesktop']
        self.assertFalse(hero['chaptersHidden'])
        self.assertEqual(hero['chapter'], {'time': 6.5, 'playing': True, 'current': [None, 'true', None]})
        self.assertEqual(hero['afterTimeupdate'], [None, None, 'true'])
        # The phone's vertical cut has its own timing, so the chapter list stays hidden there.
        self.assertTrue(r['heroPhone']['chaptersHidden'])
        self.assertIsNone(r['heroPhone']['error'])

    def test_every_reel_on_a_page_plays_and_pauses_on_its_own(self):
        # Task 29: Services has two clips. Each gets its own observer and button (named from its markup), plays only while it
        # is in view, and a press of Pause on one never touches the other.
        r = self.node_json(REEL_SCRIPT, REEL)
        clips = r['clips']
        self.assertIsNone(clips['error'])
        for index, (state, name) in enumerate(zip(clips['all'], ('redesign video', 'care plan video'))):
            with self.subTest(clip=name):
                self.assertFalse(state['controls'])
                self.assertFalse(state['hidden'])
                self.assertTrue(state['muted'])
                self.assertEqual(state['observed'], 1)
                self.assertEqual(state['loads'], 0)  # no narrow cut: the source is left alone
                self.assertEqual(state['src'], f'/assets/video/{name}.mp4')
                self.assertEqual((state['playing'], state['label'], state['plays']), (False, f'Play {name}', 0))
        # Daylight (Task 34): one large video at a time. The second clip waits while the first plays; pressing Play on it
        # hands over (the first pauses); pressing Pause on it touches only its own video, and the first, still in view and
        # never paused by the visitor, takes its turn again.
        expected = [('first in view', [(True, 'Pause redesign video'), (False, 'Play care plan video')]),
                    ('second in view', [(True, 'Pause redesign video'), (False, 'Play care plan video')]),
                    ('press second', [(False, 'Play redesign video'), (True, 'Pause care plan video')]),
                    ('press second again', [(True, 'Pause redesign video'), (False, 'Play care plan video')]),
                    ('first out of view', [(False, 'Play redesign video'), (False, 'Play care plan video')]),
                    ('second back in view', [(False, 'Play redesign video'), (False, 'Play care plan video')])]
        self.assertEqual([(step, [(s['playing'], s['label']) for s in states]) for step, states in clips['multi']], expected)
        # Reduced motion or Save-Data: no clip calls play() by itself. Only the press on the second clip starts it; the first,
        # never pressed, stays still throughout.
        for name in ('clipsReduced', 'clipsSaveData'):
            with self.subTest(case=name):
                steps = r[name]['multi']
                for step, states in steps[:2]:
                    for state in states:
                        self.assertEqual((state['playing'], state['plays']), (False, 0), step)
                        self.assertTrue(state['label'].startswith('Play '))
                self.assertEqual(steps[2][1][1], {'playing': True, 'label': 'Pause care plan video', 'plays': 1})
                for step, states in steps:
                    self.assertEqual((states[0]['playing'], states[0]['plays']), (False, 0), step)

    def test_work_tile_previews_load_only_when_wanted_and_play_one_at_a_time(self):
        # Daylight (Task 34): fine pointers preview on hover and keyboard focus; nothing is created before that.
        r = self.node_json(PREVIEW_SCRIPT, REEL)
        desktop = r['desktop']
        self.assertIsNone(desktop['error'])
        self.assertEqual(desktop['steps'], [
            ['loaded', ['none', 'none', 'none']],
            ['hover first', ['playing', 'none', 'none']],
            ['hover second', ['paused', 'playing', 'none']],  # one at a time
            ['leave second', ['paused', 'paused', 'none']],
            ['focus third', ['paused', 'paused', 'playing']],  # keyboard focus previews too
            ['blur third', ['paused', 'paused', 'paused']],
            ['hover first again', ['playing', 'paused', 'paused']],  # the same video, no second file
            ['tab hidden', ['paused', 'paused', 'paused']],
            ['hover while hidden', ['paused', 'paused', 'paused']],
            ['pause motion', ['paused', 'paused', 'paused']],
            ['hover while held', ['paused', 'paused', 'paused']],  # Pause motion holds the previews as well
        ])
        self.assertEqual(len(desktop['created']), 3)
        for video, name in zip(desktop['created'], ('hb', 'gl', 'fc')):
            with self.subTest(preview=name):
                self.assertEqual(video['tag'], 'video')
                self.assertEqual(video['src'], f'/assets/video/loop-{name}-desktop.mp4')  # same origin, from data-hover-src
                self.assertTrue(video['muted'])
                self.assertEqual(video['className'], 'hover-video')
                for attr, value in (('muted', ''), ('loop', ''), ('playsinline', ''), ('preload', 'none'), ('aria-hidden', 'true'),
                                    ('width', '1280'), ('height', '800')):
                    self.assertEqual(video['attrs'].get(attr), value)
                self.assertNotIn('autoplay', video['attrs'])
                self.assertNotIn('controls', video['attrs'])
        self.assertEqual(desktop['listened'], [['blur', 'focus', 'pointerenter', 'pointerleave']] * 3)
        self.assertEqual(desktop['tileObservers'], [])

    def test_work_tile_previews_play_when_centred_on_touch_and_never_by_themselves_when_asked_not_to(self):
        r = self.node_json(PREVIEW_SCRIPT, REEL)
        phone = r['phone']
        self.assertEqual(phone['steps'], [['loaded', ['none', 'none', 'none']], ['first centred', ['playing', 'none', 'none']],
                                          ['second centred', ['paused', 'playing', 'none']], ['second off centre', ['paused', 'paused', 'none']]])
        self.assertEqual(phone['tileObservers'], [{'rootMargin': '-35% 0px -35% 0px'}] * 3)  # the middle 30% of the screen
        self.assertEqual(phone['listened'], [[], [], []])  # no hover or focus previews without a fine pointer
        # Reduced motion or Save-Data: no preview video is ever created, so no file is requested.
        for name in ('reduced', 'saveData', 'phoneReduced'):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['error'])
                self.assertEqual(r[name]['created'], [])
                self.assertTrue(all(states == ['none', 'none', 'none'] for _, states in r[name]['steps']))

    def test_film_shows_its_button_progress_and_time(self):
        # Daylight (Task 34): the About film. reel.js reveals the button bar, plays on press and scales the progress bar
        # (transform only) and writes the elapsed time while it plays; both stay put when it pauses.
        film = self.node_json(PREVIEW_SCRIPT, REEL)['desktop']
        self.assertEqual(film['film'], {'ui': False, 'button': False, 'label': 'Pause film', 'transform': 'scaleX(0.25)', 'time': '0:05 / 0:20'})
        self.assertEqual(film['filmPaused'], {'label': 'Play film', 'transform': 'scaleX(0.75)', 'time': '0:15 / 0:20'})

    def test_demo_sweep_runs_once_and_moves_only_the_divider(self):
        # Task 29: the first time the comparison is well in view, the divider sweeps 50 -> 82 -> 18 -> 50, once. Daylight
        # (Task 33): in 1.5 s (0.4 + 0.7 + 0.4, the plan's durations) on the state-change curve.
        # Only the visual --pos changes: the range value, its aria-valuetext and the buttons' aria-pressed are never
        # written, so assistive technology hears nothing extra.
        r = self.node_json(SWEEP_SCRIPT, HOME)
        for name in ('complete', 'phone', 'onScreen'):
            with self.subTest(case=name):
                result = r[name]
                self.assertEqual(result['trigger'], {'start': 'top 65%', 'once': True})
                self.assertTrue(result['started'])
                self.assertEqual(result['positions'], ['82%', '18%', '50%'])
                self.assertAlmostEqual(result['duration'], 1.5)
                self.assertEqual((result['sweepValueWrites'], result['sweepAttrWrites'], result['sweepPressedWrites']), (0, [], 0))
                self.assertEqual((result['finalPos'], result['value']), ('50%', '50'))
                self.assertEqual(result['stopListeners'], 3)  # pointerdown, keydown, touchstart while it runs ...
                self.assertEqual(result['passive'], [True, True, True])
                self.assertEqual(result['stopListenersAfter'], 0)  # ... and none once it is over
                self.assertFalse(result['secondStart'])  # at most once per page load

    def test_demo_sweep_stops_on_any_input_and_returns_to_the_range_value(self):
        r = self.node_json(SWEEP_SCRIPT, HOME)
        for name, stopped_at in (('key', ['82%']), ('pointer', ['82%', '18%']), ('touch', ['82%'])):
            with self.subTest(case=name):
                result = r[name]
                self.assertEqual(result['positions'], stopped_at)
                self.assertEqual(result['killed'], 1)
                self.assertFalse(result['prevented'])  # the key, click or touch still reaches the page
                self.assertEqual(result['finalPos'], '50%')  # back to the range value, which never moved
                self.assertEqual((result['sweepValueWrites'], result['sweepAttrWrites'], result['sweepPressedWrites']), (0, [], 0))
                self.assertEqual(result['stopListenersAfter'], 0)
                self.assertFalse(result['secondStart'])
        # Moving the slider mid-sweep stops it; the divider follows the visitor's value (announced as usual for an input).
        moved = r['input']
        self.assertEqual(moved['killed'], 1)
        self.assertEqual((moved['finalPos'], moved['value']), ('30%', '30'))
        self.assertEqual(moved['stopListenersAfter'], 0)

    def test_demo_sweep_never_runs_with_reduced_motion_without_gsap_or_after_use(self):
        r = self.node_json(SWEEP_SCRIPT, HOME)
        for name in ('reduced', 'plain'):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['trigger'])
                self.assertFalse(r[name]['started'])
                self.assertEqual(r[name]['finalPos'], '50%')
        # Someone who already moved the slider never gets a demonstration on top of their choice.
        touched = r['touchedFirst']
        self.assertFalse(touched['started'])
        self.assertEqual((touched['finalPos'], touched['value']), ('30%', '30'))

    def test_showreel_lens_opens_with_the_scroll_and_the_chapters_arrive_once(self):
        # Liquid Glass (Task 37): the frame opens from a rounded glass lens to its full size and tilts flat, linked to the
        # scroll (clip-path and transform only, never pinned); the chapter panel rises once, only if it starts below the
        # fold. Never under reduced motion.
        r = self.node_json(SWEEP_SCRIPT, HOME)
        for name in ('complete', 'phone'):
            with self.subTest(case=name):
                frame, panel = r[name]['entrance']
                self.assertEqual(frame['names'], ['frame'])
                self.assertEqual(frame['from']['clipPath'], 'inset(9% 16% 9% 16% round 48px)')
                self.assertEqual(frame['to']['clipPath'], 'inset(0% 0% 0% 0% round 18px)')
                self.assertEqual((frame['to']['rotationX'], frame['to']['scale'], frame['to']['ease']), (0, 1, 'none'))
                self.assertEqual(frame['trigger'], {'scrub': 0.6, 'once': False, 'pin': False})
                self.assertTrue(set(frame['from']) <= {'clipPath', 'rotationX', 'scale', 'transformPerspective'})
                self.assertEqual(panel['names'], ['reel'])
                self.assertEqual(panel['from'], {'y': 40, 'opacity': 0})
                self.assertIn('opacity', panel['to']['clearProps'])
                self.assertEqual(panel['trigger'], {'scrub': None, 'once': True, 'pin': False})
        self.assertEqual([t['names'] for t in r['onScreen']['entrance']], [['frame']])  # the panel is already on screen
        self.assertEqual(r['reduced']['entrance'], [])

    def test_step_numerals_count_up_once_and_keep_their_final_text(self):
        # Task 29: Services step numerals (aria-hidden, final in the HTML) count up once as they scroll in. Only below the
        # fold and only with motion allowed; nothing else about them changes.
        r = self.node_json(DETAILS_SCRIPT, DETAILS)
        for name in ('desktop', 'touch'):
            with self.subTest(case=name):
                result = r[name]
                self.assertIsNone(result['error'])
                self.assertEqual(result['textsAtStart'], ['00'] * 5)
                self.assertEqual(result['counts'], [{'n': n, 'once': True, 'start': 'top 85%'} for n in range(1, 6)])  # Task 43: one reveal line
                self.assertEqual(result['textsAfter'], ['01', '02', '03', '04', '05'])
                self.assertEqual(result['onScreenText'], '01')  # already visible: left alone
                self.assertEqual(result['stepAttrWrites'], 0)
        for name in ('reduced', 'plain'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['textsAtStart'], ['01', '02', '03', '04', '05'])
                self.assertEqual(r[name].get('counts', []), [])

    def test_cards_tilt_only_for_fine_pointers_and_never_past_six_degrees(self):
        r = self.node_json(DETAILS_SCRIPT, DETAILS)
        desktop = r['desktop']
        self.assertEqual(desktop['perspective'], [900, 900, 900])
        self.assertTrue(desktop['tilt'])
        self.assertEqual(max(abs(v) for v in desktop['tilt']), 6)
        self.assertEqual(desktop['leave'], [0] * 6)  # eases back flat when the pointer leaves
        for name in ('touch', 'reduced'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['tilt'], [])
                self.assertEqual(r[name]['perspective'], [])
        for query in desktop['queries']:
            self.assertIn('(prefers-reduced-motion: no-preference)', query)

    def test_cursor_ring_is_extra_decorative_and_only_on_fine_pointers(self):
        r = self.node_json(DETAILS_SCRIPT, DETAILS)
        desktop = r['desktop']
        self.assertEqual(desktop['ring'], [{'className': 'cursor-ring', 'attrs': {'aria-hidden': 'true'}, 'children': 1}])
        self.assertTrue(desktop['passiveMove'])
        self.assertEqual(desktop['touchMoves'], 0)  # touch and pen moves are ignored
        self.assertEqual(desktop['follow'], [['x', 300], ['y', 200]])
        self.assertEqual(desktop['shown'], [1])
        self.assertTrue(desktop['overLink'])  # grows over links and buttons
        self.assertEqual(desktop['overField'], {'link': False, 'opacity': [0]})  # steps aside over form fields
        self.assertEqual(desktop['backOverText'], [1])
        self.assertEqual(desktop['leftWindow'], [0])
        # A coarse pointer, reduced motion or no GSAP: no element is ever created.
        for name in ('touch', 'reduced', 'plain'):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['error'])
                self.assertEqual(r[name]['ring'], [])

    def test_motion_boot_holds_openings_with_a_failsafe_and_no_intro(self):
        # Daylight (Task 33): no first-visit intro. On every motion page (with or without data-intro, a hash or a previous
        # visit) the boot sets the opening hold and a single failsafe timer of at most 2.5 s drops it; nothing is stored.
        r = self.node_json(BOOT_SCRIPT, BOOT)
        for name, result in r.items():
            with self.subTest(case=name):
                self.assertIsNone(result['error'])
                self.assertIn('js', result['classes'])
                self.assertNotIn('ns-intro', result['classes'])
                self.assertEqual(result['flag'], '1' if name == 'seen' else None)  # only the value the case stored itself
        for name in ('first', 'hash', 'seen', 'throws', 'inner'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['classes'], ['js', 'motion', 'ph-wait'])
                self.assertEqual(len(r[name]['timers']), 1)
                self.assertLessEqual(r[name]['timers'][0], 2500)
                self.assertEqual(r[name]['afterTimers'], ['js', 'motion'])
        # Reduced motion or no matchMedia: nothing is held hidden and no timer is needed.
        for name in ('reduced', 'noMatchMedia'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['classes'], ['js'])
                self.assertEqual(r[name]['timers'], [])

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
                self.assertEqual(result['lineFrom'], {'yPercent': 108, 'y': 0})
                self.assertGreater(result['mediaStagger'], 0)
                hidden = result['setNames'] + result['revealNames']
                for name_on_screen in ('riseOnScreen', 'revealOnScreen', 'devOnScreen'):
                    self.assertNotIn(name_on_screen, hidden)
                for name_below in ('rise0', 'reveal0', 'dev0'):
                    self.assertIn(name_below, hidden)
        self.assertEqual(r['reduced']['openingKinds'], [])

    def test_percentage_openings_reset_the_pixel_y_gsap_reads_from_css(self):
        # Night Shift Task 27: GSAP turns a CSS translateY(108%) into a pixel y. A tween that only animates yPercent keeps
        # that y, so the homepage H1 stayed below its mask. Every such tween pins y to 0 at both ends; the headlines also
        # clear the transform once they land.
        home = self.node_json(HOME_SCRIPT, HOME)
        for name in ('first', 'phone'):
            with self.subTest(case=name):
                lines = home[name]['heroLines']
                self.assertEqual(len(lines), 1)
                self.assertEqual(lines[0]['kind'], 'fromTo')
                self.assertEqual(lines[0]['from'], {'yPercent': 108, 'y': 0})
                self.assertEqual((lines[0]['yPercent'], lines[0]['y']), (0, 0))
                self.assertIn('transform', lines[0]['clearProps'].split(','))
        motion = self.node_json(MOTION_SCRIPT, MOTION)
        for name in ('desktop', 'touch'):
            with self.subTest(case=name):
                self.assertEqual(motion[name]['lineFrom'], {'yPercent': 108, 'y': 0})
                self.assertEqual(motion[name]['lineTo']['yPercent'], 0)
                self.assertEqual(motion[name]['lineTo']['y'], 0)
                self.assertIn('transform', motion[name]['lineTo']['clearProps'].split(','))

    def test_every_css_percentage_hold_has_a_js_takeover_that_resets_y(self):
        # Static guard for Task 27: each .ph-wait rule that starts at translateY(<n>%) needs a fromTo starting at
        # { yPercent: <n>, y: 0 }, or GSAP would keep the CSS offset as pixels on top of the percentage tween.
        import re
        assets = HOME.parent
        js = '\n'.join(path.read_text(encoding='utf-8') for path in sorted(assets.glob('*.js')))
        holds = []
        for css in sorted(assets.glob('*.css')):
            for rule in re.findall(r'[^{}]*\.ph-wait[^{}]*\{[^}]*\}', css.read_text(encoding='utf-8')):
                holds += [(css.name, rule.strip(), n) for n in re.findall(r'translateY\((-?\d+(?:\.\d+)?)%\)', rule)]
        self.assertGreaterEqual(len(holds), 2)  # hero lines and inner-page lines (Daylight, Task 33, removed the intro word)
        for name, rule, n in holds:
            with self.subTest(css=name, rule=rule):
                pattern = r'fromTo\([^;]*?\{\s*yPercent:\s*%s,\s*y:\s*0\s*\}' % re.escape(n)
                self.assertRegex(js, pattern)

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

    def test_nested_list_reveals_with_its_card_never_after_it(self):
        # Task 43: a [data-stagger] list inside a [data-rise] card is triggered by the card, at the card's own line, so
        # the card never stands empty waiting for its items; a list on its own keeps its own trigger at the same line.
        r = self.node_json(MOTION_STAGGER_SCRIPT, MOTION)
        self.assertEqual(r['batches'], [{'names': ['card'], 'start': 'top 85%', 'once': True}])
        lists = {item['first']: item for item in r['lists']}
        self.assertEqual(lists['n0'], {'first': 'n0', 'trigger': 'card', 'start': 'top 85%', 'once': True})
        self.assertEqual(lists['a0'], {'first': 'a0', 'trigger': 'alone', 'start': 'top 85%', 'once': True})

    def test_services_cards_rise_with_their_rows_at_the_reveal_line(self):
        # Task 43: the white "Every month" and "Old addresses" cards were painted while their rows waited for 78-80%,
        # so they scrolled in empty. Now the card itself rises first in the same timeline, from 85%.
        r = self.node_json(SCENES_CARDS_SCRIPT, SCENES)
        self.assertEqual([(t['trigger'], t['start'], t['once']) for t in r['motion']], [('month', 'top 85%', True), ('redir', 'top 85%', True)])
        for scene, rows in zip(r['motion'], ('mli0', 'rli0')):
            with self.subTest(card=scene['trigger']):
                first = scene['steps'][0]
                self.assertEqual((first['first'], first['at']), (scene['trigger'], 0))  # the card leads
                self.assertEqual(first['from'], {'opacity': 0, 'y': 24})
                row = next(step for step in scene['steps'] if step['first'] == rows)
                self.assertGreater(row['at'], 0)  # its rows follow inside the same timeline, never on a later trigger
        self.assertEqual(r['reduced'], [])  # reduced motion: nothing is hidden or moved
        source = SCENES.read_text(encoding='utf-8')
        self.assertIn("const START = 'top 85%';", source)
        self.assertEqual(re.findall(r"'top \d+%'", source), ["'top 85%'"])  # one line for every scene

    def test_every_reveal_starts_at_the_same_line(self):
        # Task 43: reveals (anything hidden until it scrolls in) start as their trigger's top crosses 85% of the viewport.
        # Left alone on purpose: scrubbed effects (they never hide content) and the before/after sweep at 65%, which is a
        # demonstration that should play with the frame well in view, not a reveal.
        motion = MOTION.read_text(encoding='utf-8')
        self.assertIn("const START = 'top 85%';", motion)
        self.assertEqual(re.findall(r"'top \d+%'", motion), ["'top 85%'"])
        self.assertIn("const host = list.parentElement?.closest?.('[data-rise], [data-reveal]') || list;", motion)
        self.assertEqual(re.findall(r"'top \d+%'", DETAILS.read_text(encoding='utf-8')), ["'top 85%'"])
        home = HOME.read_text(encoding='utf-8')
        self.assertIn("start: start || 'top 85%'", home)
        for gone in ("once(el, 'top 88%')", "once(frame, 'top 40%')", "once(panel, 'top 80%')"):
            self.assertNotIn(gone, home)
        self.assertEqual(sorted(set(re.findall(r"'top \d+%'", home))), ["'top 25%'", "'top 65%'", "'top 85%'", "'top 92%'"])
        # Photo parallax stays small (yPercent +/-6) and only on screens wider than 1080px.
        self.assertIn("mm.add(MOTION + ' and (min-width: 1081px)', () => {\n    $$('[data-parallax]').forEach(frame => {\n      gsap.fromTo($$('img', frame), { yPercent: -6, scale: 1.14 }, { yPercent: 6,", motion)

    def test_demo_js_makes_no_network_requests(self):
        js = DEMO.read_text(encoding='utf-8')
        for token in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', 'EventSource', 'http://', 'https://'):
            self.assertNotIn(token, js)


# Liquid Glass (Task 37): the shell (site.js), the glass layer (glass.js), the WebGL boot (glass-boot.js) and the pause
# hand-off from reel.js, run in Node against the same stub DOM.
SITE = Path(__file__).resolve().parents[1] / 'assets' / 'site.js'
GLASS = Path(__file__).resolve().parents[1] / 'assets' / 'glass.js'
GLASS_BOOT = Path(__file__).resolve().parents[1] / 'assets' / 'glass-boot.js'
GLASS_PAGE = Path(__file__).resolve().parents[1] / 'assets' / 'glass-page.js'

# glass-boot.js: which environments import the scene, and when. import() is replaced by a recording stub (vm scripts have
# no module loader); everything else runs as shipped.
GLASS_BOOT_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8').replace('import(SCENE)', '__import(SCENE)');
const settle = () => new Promise(resolve => setImmediate(resolve));
async function run(env) {
  const host = element('host');
  if (env.kind) host.setAttribute('data-gl-kind', env.kind);
  const imports = [], idle = [], timers = [], contexts = [];
  const doc = { readyState: env.complete ? 'complete' : 'interactive', querySelector: s => (s === '[data-gl]' && !env.noHost ? host : null),
    createElement: tag => ({ tag, getContext: kind => { contexts.push(kind); return env.noWebGL ? null : {}; } }) };
  const nav = { connection: { saveData: Boolean(env.saveData) } };
  if (env.memory !== undefined) nav.deviceMemory = env.memory;
  if (env.cores !== undefined) nav.hardwareConcurrency = env.cores;
  const { win, listeners } = makeWindow(env, { navigator: nav, requestIdleCallback: (fn, o) => idle.push([fn, o]), setTimeout: (fn, ms) => timers.push([fn, ms]) });
  let started = null;
  const __import = url => { imports.push(url); return env.fail ? Promise.reject(new Error('offline')) : Promise.resolve({ start: (h, g) => { started = { host: h.name, shared: g === win.__glass }; } }); };
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: doc, __import }); } catch (e) { error = String(e); }
  const out = { error, beforeLoad: imports.length, loadListeners: (listeners.load || []).length };
  (listeners.load || []).forEach(l => l.fn({ type: 'load' }));
  out.afterLoad = imports.length;
  out.idleTimeout = idle.length ? idle[0][1].timeout : null;
  idle.splice(0).forEach(([fn]) => fn());
  await settle();
  out.imports = imports;
  out.contexts = contexts;
  out.started = started;
  out.liveRemoved = host.classList.set.size === 0;
  out.decide = win.__glass && win.__glass.wantsGL ? [
    win.__glass.wantsGL({ reduce: false, saveData: false, narrow: false, lowEnd: false, webgl: true }),
    win.__glass.wantsGL({ reduce: true, saveData: false, narrow: false, lowEnd: false, webgl: true }),
    win.__glass.wantsGL({ reduce: false, saveData: true, narrow: false, lowEnd: false, webgl: true }),
    win.__glass.wantsGL({ reduce: false, saveData: false, narrow: true, lowEnd: false, webgl: true }),
    win.__glass.wantsGL({ reduce: false, saveData: false, narrow: false, lowEnd: true, webgl: true }),
    win.__glass.wantsGL({ reduce: false, saveData: false, narrow: false, lowEnd: false, webgl: false })] : null;
  return out;
}
(async () => {
  const desktop = { width: 1440, height: 900, fine: true, reduce: false, memory: 8, cores: 8 };
  const cases = { desktop, complete: { ...desktop, complete: true }, unknownDevice: { width: 1440, height: 900, fine: true, reduce: false },
    reduced: { ...desktop, reduce: true }, saveData: { ...desktop, saveData: true }, narrow: { ...desktop, width: 760 },
    lowMemory: { ...desktop, memory: 2 }, fourCores: { ...desktop, cores: 4 }, noWebGL: { ...desktop, noWebGL: true },
    noHost: { ...desktop, noHost: true }, fail: { ...desktop, fail: true },
    slab: { ...desktop, kind: 'slab' }, panes: { ...desktop, kind: 'panes', complete: true }, unknownKind: { ...desktop, kind: 'orbit' },
    pathKind: { ...desktop, kind: '/evil.js' }, protoKind: { ...desktop, kind: 'constructor' },
    slabReduced: { ...desktop, kind: 'slab', reduce: true }, panesSaveData: { ...desktop, kind: 'panes', saveData: true },
    slabNarrow: { ...desktop, kind: 'slab', width: 760 }, panesLowMemory: { ...desktop, kind: 'panes', memory: 2 },
    slabFourCores: { ...desktop, kind: 'slab', cores: 4 }, panesNoWebGL: { ...desktop, kind: 'panes', noWebGL: true },
    sheets: { ...desktop, kind: 'sheets' }, photos: { ...desktop, kind: 'photos', complete: true }, mark: { ...desktop, kind: 'mark' },
    sheetsReduced: { ...desktop, kind: 'sheets', reduce: true }, photosSaveData: { ...desktop, kind: 'photos', saveData: true },
    markNoWebGL: { ...desktop, kind: 'mark', noWebGL: true }, markReduced: { ...desktop, kind: 'mark', reduce: true },
    markSaveData: { ...desktop, kind: 'mark', saveData: true }, photosNarrow: { ...desktop, kind: 'photos', width: 760 },
    sheetsNoWebGL: { ...desktop, kind: 'sheets', noWebGL: true }, photosNoWebGL: { ...desktop, kind: 'photos', noWebGL: true } };
  const out = {};
  for (const [name, env] of Object.entries(cases)) out[name] = await run(env);
  console.log(JSON.stringify(out));
})();
"""

# site.js: the menu and the glass nav pill hiding on scroll down and coming back on scroll up, near the top, with the menu
# open, or on keyboard focus inside it.
SHELL_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
const header = element('header'), menu = element('menu'), nav = element('nav');
menu.attrs['aria-expanded'] = 'false';
let focused = null;
menu.focus = () => { focused = 'menu'; };
const root = element('html');
const parts = { '[data-menu]': [menu], '[data-nav]': [nav], '.site-header': [header] };
const doc = { documentElement: root, listeners: {}, addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
  querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
const { win, listeners } = makeWindow({ width: 390, height: 844, fine: false, reduce: false }, { scrollY: 0, location: { pathname: '/' } });
vm.runInNewContext(source, { window: win, document: doc, getComputedStyle: () => ({ display: 'inline-flex' }) });
const steps = [];
const state = () => ({ hidden: header.classList.contains('is-hidden'), expanded: menu.attrs['aria-expanded'], open: nav.classList.contains('open') });
const scroll = y => { win.scrollY = y; (listeners.scroll || []).forEach(l => l.fn({ type: 'scroll' })); };
const step = (name, act) => { act(); steps.push([name, state()]); };
step('start', () => {});
step('down a little, near the top', () => scroll(80));
step('down past the first screen', () => scroll(600));
step('a jitter of 3px up', () => scroll(597));
step('up', () => scroll(400));
step('down again', () => scroll(900));
step('focus inside the header', () => (header.listeners.focusin || []).forEach(fn => fn({ type: 'focusin' })));
step('down after focus', () => scroll(1300));
step('open the menu', () => (menu.listeners.click || []).forEach(fn => fn({ type: 'click' })));
step('down with the menu open', () => scroll(1800));
step('Escape', () => (doc.listeners.keydown || []).forEach(fn => fn({ key: 'Escape' })));
step('back to the top', () => scroll(40));
console.log(JSON.stringify({ steps, focused, passive: (listeners.scroll || []).every(l => l.options && l.options.passive), js: root.classList.contains('js') }));
"""

# The Pause motion button (site.js since Task 41; reel.js follows it) also pauses the glass layer and the WebGL loop (window.__glass), and every video.
PAUSE_SCRIPT = HARNESS + r"""
// Task 41: site.js owns the Pause motion button and runs first on every page (deferred, in order), so it runs first here.
const source = fs.readFileSync(require('path').join(require('path').dirname(process.argv[1]), 'site.js'), 'utf8') + '\n// Task 41 reel.js\n' + fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const videos = ['loop', 'phone'].map(name => {
    const src = element('source'); src.dataset.src = '/assets/video/' + name + '.mp4';
    const v = element(name, { source: [src] }); v.dataset.loop = '';
    Object.assign(v, { paused: true, load() {}, play() { v.paused = false; return Promise.resolve(); }, pause() { v.paused = true; } });
    return v;
  });
  const motion = element('motion'); motion.hidden = true; motion.attrs['aria-pressed'] = 'false';
  const parts = { 'video[data-loop]': env.noLoops ? [] : videos, '[data-motion-toggle]': [motion] };
  const doc = { documentElement: element('html'), readyState: 'complete', hidden: false, listeners: {}, addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const observers = [];
  class FakeObserver { constructor(cb) { this.cb = cb; this.targets = []; observers.push(this); } observe(t) { this.targets.push(t); } }
  const { win } = makeWindow(env, { IntersectionObserver: FakeObserver, navigator: { connection: { saveData: Boolean(env.saveData) } } });
  const calls = [];
  // The WebGL scene (or the glass layer) as it joins the shared state: a listener on the pauseFns fan-out. With shared, the
  // fan-out is already installed, as glass-scene.js / glass-page.js / glass.js do.
  if (env.shared) { const G = win.__glass = { paused: false, pauseFns: [p => calls.push(p)] }; G.onPauseChange = p => G.pauseFns.forEach(fn => fn(p)); }
  // Task 41: Pricing and Contact have WebGL but no video loops, and only Pricing loads reel.js; neither hides the button.
  vm.runInNewContext(env.noReel ? source.split('\n// Task 41 reel.js\n')[0] : source, { window: win, document: doc, getComputedStyle: () => ({}) });
  if (env.lateScene) (win.__glass.pauseFns = win.__glass.pauseFns || []).push(p => calls.push(p));  // a scene imported after idle
  const out = { initial: win.__glass.paused, hidden: motion.hidden, aria: motion.attrs['aria-pressed'], playing: videos.map(v => !v.paused) };
  if (env.offScreen) observers.forEach(o => o.targets.forEach(t => o.cb([{ isIntersecting: false, target: t }])));
  else observers.forEach(o => o.targets.forEach(t => o.cb([{ isIntersecting: true, target: t }])));
  out.hiddenAfterScroll = motion.hidden;
  out.playing = videos.map(v => !v.paused);
  (motion.listeners.click || []).forEach(fn => fn({ type: 'click' }));
  out.pressed = { paused: win.__glass.paused, aria: motion.attrs['aria-pressed'], playing: videos.map(v => !v.paused) };
  (motion.listeners.click || []).forEach(fn => fn({ type: 'click' }));
  out.released = { paused: win.__glass.paused, aria: motion.attrs['aria-pressed'], playing: videos.map(v => !v.paused) };
  out.calls = calls;
  out.listeners = (motion.listeners.click || []).length;
  return out;
}
const desktop = { width: 1440, height: 900, fine: true, reduce: false };
console.log(JSON.stringify({ shared: run({ ...desktop, shared: true }), alone: run(desktop), saveData: run({ ...desktop, saveData: true, shared: true }),
  noLoops: run({ ...desktop, noLoops: true, noReel: true, lateScene: true }), noLoopsReel: run({ ...desktop, noLoops: true, shared: true }),
  offScreen: run({ ...desktop, offScreen: true, shared: true }), reducedNoLoops: run({ ...desktop, reduce: true, noLoops: true, noReel: true, shared: true }) }));
"""

# glass.js: Lenis only with motion allowed, the drift held by Pause motion, refraction only in Chromium.
GLASS_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const fields = many('field', 4).map(f => { f.style.transform = ''; return f; });
  const defs = element('defs'); defs.namespaceURI = 'svg-namespace';
  const parts = { '.atmos i': fields, '[data-lg-defs]': [defs], '.lg, .site-header .nav': [] };
  const root = element('html');
  const doc = { documentElement: root, hidden: false, listeners: {}, addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [], fonts: { ready: { then() {} } } };
  const frames = [], cancelled = [];
  let lenis = 0, ticks = 0;
  class Lenis { constructor(o) { lenis++; this.options = o; } on() {} raf() {} }
  const { win } = makeWindow(env, { Lenis, requestAnimationFrame: fn => { frames.push(fn); return frames.length; }, cancelAnimationFrame: id => cancelled.push(id),
    navigator: { connection: { saveData: Boolean(env.saveData) }, userAgentData: { brands: env.chromium ? [{ brand: 'Chromium' }] : [{ brand: 'Firefox' }] } } });
  if (env.gsap) { const stub = makeGsap(env); stub.gsap.ticker = { add() { ticks++; } }; win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; }
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: doc, getComputedStyle: () => ({ borderTopLeftRadius: '20px' }), Promise }); } catch (e) { error = String(e); }
  const out = { error, lenis, ticks, refract: root.classList.contains('lg-refract'), driftFrames: frames.length };
  if (frames.length) { frames.shift()(1000); }
  out.moved = fields[0].style.transform || null;
  const before = cancelled.length;
  win.__glass.paused = true; win.__glass.onPauseChange(true);
  out.cancelledOnPause = cancelled.length - before;
  const queued = frames.length;
  win.__glass.paused = false; win.__glass.onPauseChange(false);
  out.resumed = frames.length - queued;
  return out;
}
const desktop = { width: 1440, height: 900, fine: true, reduce: false };
console.log(JSON.stringify({ motion: run({ ...desktop, gsap: true, chromium: true }), safari: run({ ...desktop, gsap: true }),
  reduced: run({ ...desktop, reduce: true, gsap: true, chromium: true }), saveData: run({ ...desktop, saveData: true, gsap: true, chromium: true }) }));
"""


class GlassShellScriptTests(unittest.TestCase):
    def node_json(self, script, path):
        out = subprocess.run(['node', '-e', script, str(path)], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_webgl_loads_only_on_capable_desktops_after_load_and_idle(self):
        r = self.node_json(GLASS_BOOT_SCRIPT, GLASS_BOOT)
        desktop = r['desktop']
        self.assertIsNone(desktop['error'])
        self.assertEqual((desktop['beforeLoad'], desktop['afterLoad'], desktop['loadListeners']), (0, 0, 1))  # never before load and idle
        self.assertEqual(desktop['idleTimeout'], 1500)
        self.assertEqual(desktop['imports'], ['/assets/glass-scene.js'])
        self.assertEqual(desktop['started'], {'host': 'host', 'shared': True})
        self.assertEqual(r['complete']['loadListeners'], 0)  # already loaded: straight to idle
        self.assertEqual(r['complete']['imports'], ['/assets/glass-scene.js'])
        self.assertEqual(r['unknownDevice']['imports'], ['/assets/glass-scene.js'])  # browsers that do not report memory or cores
        # Reduced motion, Save-Data, 760px or less, under 4 GB, 4 cores or fewer, no WebGL, no hero: the scene is never
        # imported (and, except without WebGL, no WebGL context is ever created to find out).
        for name in ('reduced', 'saveData', 'narrow', 'lowMemory', 'fourCores', 'noWebGL', 'noHost'):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['error'])
                self.assertEqual(r[name]['imports'], [])
                self.assertIsNone(r[name]['started'])
                if name != 'noWebGL':
                    self.assertEqual(r[name]['contexts'], [])
        self.assertEqual(desktop['decide'], [True, False, False, False, False, False])
        # A failed import leaves the still in place (the host only loses a live flag it never had).
        self.assertEqual(r['fail']['imports'], ['/assets/glass-scene.js'])
        self.assertIsNone(r['fail']['started'])
        self.assertTrue(r['fail']['liveRemoved'])
        js = GLASS_BOOT.read_text(encoding='utf-8')
        for banned in ('URLSearchParams', 'location', '?poster', 'http', 'importmap'):
            self.assertNotIn(banned, js)
        self.assertIn("const MODULES = { home: '/assets/glass-scene.js', slab: '/assets/glass-page.js', panes: '/assets/glass-page.js', sheets: '/assets/glass-page.js',\n    photos: '/assets/glass-page.js', mark: '/assets/glass-page.js' };", js)

    def test_inner_page_scenes_come_from_a_fixed_list_and_respect_the_same_guards(self):
        # Task 39: Work (slab) and Services (panes) import the inner-page scene after load and idle; any other kind, including
        # a path or an Object.prototype key, imports nothing. Reduced motion, Save-Data, narrow, low-end and no WebGL never do.
        r = self.node_json(GLASS_BOOT_SCRIPT, GLASS_BOOT)
        # Task 40 adds sheets (Pricing), photos (About) and mark (Contact) to the same list and the same guards.
        for name in ('slab', 'panes', 'sheets', 'photos', 'mark'):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['error'])
                self.assertEqual(r[name]['beforeLoad'], 0)
                self.assertEqual(r[name]['imports'], ['/assets/glass-page.js'])
                self.assertEqual(r[name]['started'], {'host': 'host', 'shared': True})
        for name in ('unknownKind', 'pathKind', 'protoKind', 'slabReduced', 'panesSaveData', 'slabNarrow', 'panesLowMemory',
                     'slabFourCores', 'panesNoWebGL', 'sheetsReduced', 'photosSaveData', 'markNoWebGL', 'markReduced', 'markSaveData',
                     'photosNarrow', 'sheetsNoWebGL', 'photosNoWebGL'):
            with self.subTest(case=name):
                self.assertIsNone(r[name]['error'])
                self.assertEqual(r[name]['imports'], [])
                self.assertIsNone(r[name]['started'])
                if not name.endswith('NoWebGL'):
                    self.assertEqual(r[name]['contexts'], [])

    def test_inner_page_scene_joins_the_shared_pause_motion_fan_out(self):
        # Task 39: glass-page.js's lifecycle, imported as the real module (three.js loads in Node without a DOM). With
        # glass.js's fan-out installed first, Pause motion still reaches the other listener and stops the scene; the tab
        # hidden or the hero off screen stop it too; and it never replaces an onPauseChange that is already there.
        script = r'''
const { pathToFileURL } = require('url');
(async () => {
  const m = await import(pathToFileURL(process.argv[1]).href);
  const listeners = {};
  const doc = { hidden: false, addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); } };
  const other = [];
  const G = { paused: false, pauseFns: [p => other.push(p)] };
  const glassHandler = p => G.pauseFns.forEach(fn => fn(p));
  G.onPauseChange = glassHandler;   // as glass.js installs it
  const runs = [];
  const life = m.lifecycle(G, doc, on => runs.push(on));
  const steps = [];
  const step = name => steps.push([name, life.running, runs.slice()]);
  step('before first frame');
  life.ready(); step('ready');
  G.paused = true; G.onPauseChange(true); step('paused');
  G.paused = false; G.onPauseChange(false); step('resumed');
  doc.hidden = true; listeners.visibilitychange.forEach(fn => fn()); step('tab hidden');
  doc.hidden = false; listeners.visibilitychange.forEach(fn => fn()); step('tab visible');
  life.view(false); step('off screen');
  life.view(true); step('on screen');
  const alone = { paused: false };
  m.lifecycle(alone, doc, () => {});
  console.log(JSON.stringify({ steps, other, kept: G.onPauseChange === glassHandler, fns: G.pauseFns.length,
    aloneFanOut: typeof alone.onPauseChange === 'function' && alone.pauseFns.length === 1, kinds: m.KINDS, panes: m.PANES.map(p => p[1]) }));
})();
'''
        r = self.node_json(script, GLASS_PAGE)
        self.assertEqual(r['steps'], [
            ['before first frame', False, []], ['ready', True, [True]], ['paused', False, [True, False]],
            ['resumed', True, [True, False, True]], ['tab hidden', False, [True, False, True, False]],
            ['tab visible', True, [True, False, True, False, True]], ['off screen', False, [True, False, True, False, True, False]],
            ['on screen', True, [True, False, True, False, True, False, True]]])
        self.assertEqual(r['other'], [True, False])
        self.assertTrue(r['kept'])
        self.assertEqual(r['fns'], 2)
        self.assertTrue(r['aloneFanOut'])
        self.assertEqual(r['kinds'], ['slab', 'panes', 'sheets', 'photos', 'mark'])
        self.assertEqual(r['panes'], ['New website', 'Redesign', 'Care plan'])

    def test_nav_pill_hides_on_scroll_down_and_returns_on_up_focus_and_menu(self):
        r = self.node_json(SHELL_SCRIPT, SITE)
        self.assertTrue(r['js'])
        self.assertTrue(r['passive'])
        self.assertEqual(r['steps'], [
            ['start', {'hidden': False, 'expanded': 'false', 'open': False}],
            ['down a little, near the top', {'hidden': False, 'expanded': 'false', 'open': False}],
            ['down past the first screen', {'hidden': True, 'expanded': 'false', 'open': False}],
            ['a jitter of 3px up', {'hidden': True, 'expanded': 'false', 'open': False}],
            ['up', {'hidden': False, 'expanded': 'false', 'open': False}],
            ['down again', {'hidden': True, 'expanded': 'false', 'open': False}],
            ['focus inside the header', {'hidden': False, 'expanded': 'false', 'open': False}],
            ['down after focus', {'hidden': True, 'expanded': 'false', 'open': False}],
            ['open the menu', {'hidden': False, 'expanded': 'true', 'open': True}],
            ['down with the menu open', {'hidden': False, 'expanded': 'true', 'open': True}],
            ['Escape', {'hidden': False, 'expanded': 'false', 'open': False}],
            ['back to the top', {'hidden': False, 'expanded': 'false', 'open': False}],
        ])
        self.assertEqual(r['focused'], 'menu')  # Escape returns focus to the menu button

    def test_pause_motion_also_pauses_the_glass_layer_and_the_webgl_loop(self):
        r = self.node_json(PAUSE_SCRIPT, REEL)
        shared = r['shared']
        self.assertFalse(shared['initial'])
        self.assertEqual(shared['playing'], [True, True])
        self.assertEqual(shared['pressed'], {'paused': True, 'aria': 'true', 'playing': [False, False]})
        self.assertEqual(shared['released'], {'paused': False, 'aria': 'false', 'playing': [True, True]})
        self.assertEqual(shared['calls'], [True, False])  # window.__glass.onPauseChange, which the scene and glass.js listen to
        self.assertEqual(r['alone']['pressed']['paused'], True)  # the shared state exists even before glass.js loads
        save = r['saveData']
        self.assertTrue(save['initial'])  # Save-Data: held from the start, so WebGL never runs
        self.assertEqual(save['playing'], [False, False])

    def test_pause_motion_works_on_every_page_that_moves_with_or_without_video(self):
        # Task 41 (WCAG 2.2.2): site.js owns the button, so Pricing and Contact (WebGL and the drift, no video loops; Contact
        # has no reel.js at all) get a working, visible control too. It is shown once site.js runs and never hides again when
        # no loop is on screen; a press reaches the WebGL scene through the shared fan-out, even one imported later.
        r = self.node_json(PAUSE_SCRIPT, REEL)
        for name in ('noLoops', 'noLoopsReel', 'shared', 'offScreen'):
            with self.subTest(case=name):
                case = r[name]
                self.assertFalse(case['hidden'])
                self.assertFalse(case['hiddenAfterScroll'])
                self.assertEqual(case['aria'], 'false')
                self.assertEqual(case['pressed']['aria'], 'true')
                self.assertTrue(case['pressed']['paused'])
                self.assertEqual(case['released']['aria'], 'false')
                self.assertFalse(case['released']['paused'])
                self.assertEqual(case['calls'], [True, False])  # the WebGL pause hook fired once each way
                self.assertEqual(case['listeners'], 1)  # one owner: reel.js adds no second click handler
        self.assertEqual(r['offScreen']['playing'], [False, False])  # nothing on screen plays, the button stays
        reduced = r['reducedNoLoops']
        self.assertTrue(reduced['initial'])  # reduced motion: starts pressed
        self.assertEqual((reduced['aria'], reduced['hidden']), ('true', False))
        self.assertEqual(reduced['pressed']['aria'], 'false')  # a press releases it

    def test_glass_layer_keeps_lenis_drift_and_refraction_to_where_they_belong(self):
        r = self.node_json(GLASS_SCRIPT, GLASS)
        motion = r['motion']
        self.assertIsNone(motion['error'])
        self.assertEqual((motion['lenis'], motion['ticks']), (1, 1))  # Lenis, driven by GSAP's ticker (ScrollTrigger in step)
        self.assertTrue(motion['refract'])
        self.assertEqual(motion['driftFrames'], 1)
        self.assertRegex(motion['moved'], r'^translate3d\(-?[\d.]+vmax,-?[\d.]+vmax,0\)$')  # transform only
        self.assertEqual(motion['cancelledOnPause'], 1)
        self.assertEqual(motion['resumed'], 1)
        self.assertFalse(r['safari']['refract'])  # no SVG backdrop filters outside Chromium: plain blur
        self.assertEqual(r['safari']['lenis'], 1)
        reduced = r['reduced']
        self.assertEqual((reduced['lenis'], reduced['ticks'], reduced['driftFrames'], reduced['refract']), (0, 0, 0, False))
        self.assertIsNone(reduced['moved'])
        self.assertFalse(r['saveData']['refract'])  # Save-Data: no displacement maps are drawn

    def test_real_lenis_handles_wheel_events_with_the_options_glass_js_passes(self):
        # Vendored Lenis 1.1.0 defaults `prevent` to `false`, then calls `this.options.prevent(el)` for every element
        # on a wheel event's path, which threw on every wheel tick. Run glass.js against the real file, not a stub.
        source = GLASS.read_text(encoding='utf-8')
        self.assertRegex(source, r'new win\.Lenis\(\{[^}]*prevent:\s*\(\)\s*=>\s*false')
        out = subprocess.run(['node', '-e', REAL_LENIS_SCRIPT, str(GLASS), str(LENIS)], capture_output=True, text=True, check=True)
        r = json.loads(out.stdout)
        self.assertIsNone(r['error'])
        self.assertEqual(r['version'], '1.1.0')
        self.assertTrue(r['built'])
        self.assertEqual(r['preventType'], 'function')
        self.assertEqual(r['wheelListeners'], 1)
        self.assertIsNone(r['wheelError'])
        self.assertTrue(r['defaultPrevented'])  # Lenis took the wheel: smooth scrolling, not a native fallback
        self.assertEqual(r['target'], 120)
        self.assertTrue(r['optOutHonoured'])  # data-lenis-prevent still leaves inner scrollers native
        # The unpatched default really does throw: the regression this test guards against.
        self.assertIn('prevent is not a function', r['defaultError'])


LENIS = Path(__file__).resolve().parents[1] / 'assets' / 'vendor' / 'lenis' / 'lenis.min.js'

# Real vendored Lenis inside a fake window: glass.js builds it, then a wheel event whose path holds an element is sent.
REAL_LENIS_SCRIPT = r"""
const fs = require('fs'), vm = require('vm');
const glassSource = fs.readFileSync(process.argv[1], 'utf8'), lenisSource = fs.readFileSync(process.argv[2], 'utf8');
function el(tag, attrs) {
  const a = attrs || {}, classes = new Set();
  return { tagName: tag, nodeType: 1, className: '', style: {}, scrollTop: 0, scrollLeft: 0, scrollHeight: 5000, scrollWidth: 1440, clientHeight: 900, clientWidth: 1440,
    hasAttribute: n => n in a, getAttribute: n => (n in a ? a[n] : null),
    classList: { add: (...c) => c.forEach(x => classes.add(x)), remove: (...c) => c.forEach(x => classes.delete(x)), contains: c => classes.has(c), toggle() {} },
    addEventListener() {}, removeEventListener() {}, getBoundingClientRect: () => ({ top: 0, left: 0, width: 1440, height: 900 }) };
}
function world() {
  const html = el('html'), body = el('body');
  const listeners = {};
  const doc = { documentElement: html, body, hidden: false, addEventListener() {}, querySelector: () => null, querySelectorAll: () => [], fonts: { ready: { then() {} } } };
  const win = { innerWidth: 1440, innerHeight: 900, document: doc, __glass: {},
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); }, removeEventListener() {},
    matchMedia: q => ({ matches: /no-preference|min-width|pointer: fine/.test(q), addEventListener() {} }),
    navigator: { connection: { saveData: false }, userAgentData: { brands: [{ brand: 'Firefox' }] } },
    requestAnimationFrame: () => 1, cancelAnimationFrame() {}, setTimeout: () => 1, clearTimeout() {}, scrollTo() {} };
  class ResizeObserver { observe() {} disconnect() {} }
  const ctx = vm.createContext({ window: win, document: doc, ResizeObserver, setTimeout: () => 1, clearTimeout() {}, Math, Object, Promise,
    getComputedStyle: () => ({ borderTopLeftRadius: '20px' }) });
  ctx.self = ctx.globalThis;
  vm.runInContext(lenisSource, ctx);
  win.Lenis = ctx.Lenis;
  return { win, doc, html, body, listeners, ctx };
}
function wheel(path) {
  const ev = { type: 'wheel', deltaX: 0, deltaY: 120, deltaMode: 0, ctrlKey: false, defaultPrevented: false,
    composedPath: () => path, preventDefault() { this.defaultPrevented = true; } };
  return ev;
}
const out = { error: null };
try {
  const w = world();
  vm.runInContext(glassSource, w.ctx);
  const lenis = w.win.__glass.lenis;
  out.version = w.win.lenisVersion;
  out.built = Boolean(lenis);
  out.preventType = typeof lenis.options.prevent;
  out.wheelListeners = (w.listeners.wheel || []).length;
  const card = el('div'), ev = wheel([card, w.body, w.html, w.doc, w.win]);
  out.wheelError = null;
  try { w.listeners.wheel.forEach(fn => fn(ev)); } catch (e) { out.wheelError = String(e); }
  out.defaultPrevented = ev.defaultPrevented;
  out.target = lenis.targetScroll;
  const inner = el('div', { 'data-lenis-prevent': '' }), ev2 = wheel([inner, w.body, w.html, w.doc, w.win]);
  w.listeners.wheel.forEach(fn => fn(ev2));
  out.optOutHonoured = !ev2.defaultPrevented;
  // The same wheel against Lenis built with its own default `prevent` (what glass.js did before).
  const d = world();
  new d.win.Lenis({ lerp: 0.1, smoothWheel: true });
  out.defaultError = '';
  try { d.listeners.wheel.forEach(fn => fn(wheel([el('div'), d.body, d.html, d.doc, d.win]))); } catch (e) { out.defaultError = String(e); }
} catch (e) { out.error = String(e); }
console.log(JSON.stringify(out));
"""


if __name__ == '__main__':
    unittest.main()
