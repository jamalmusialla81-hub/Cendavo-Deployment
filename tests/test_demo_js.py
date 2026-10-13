import json
import math
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
        eventCallback(type, fn) { tl.vars[type] = fn; return tl; },
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
  // Task 48: glass.js asks ScrollTrigger for its triggers and refresh events, and GSAP for its running animations.
  gsap.globalTimeline = { getChildren() { return []; } };
  const ScrollTrigger = { batch() { log.batches++; }, create(v) { log.creates.push(v); }, getAll() { return []; }, refresh() {}, addEventListener() {} };
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
    '.band': [element('band')], '.gp-1': [element('phone1')], '.marq': [element('marq')], '.mq-word': [element('mqWord')], '[data-marquee]': many('track', 1) };
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
  // Task 48: these cases describe a page that has finished loading (before that nothing starts by itself: runEarly).
  const doc = makeDoc(parts, root, { complete: true, ...env });
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
  const motion = element('motion'); motion.hidden = true; motion.attrs['aria-pressed'] = 'false'; motion.textContent = 'Pause motion';
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
// Task 48: the /work/ hero clip, on screen while the page is still loading. Nothing plays (so nothing downloads) until the
// load event and idle; a press of its button plays it at once, and the controller never pauses that press for not being
// loaded yet.
async function runEarly(env) {
  const { reel, video, toggle } = makeReel(env, 'three signs video', false);
  const root = element('html'); root.classList = classList(['js']);
  const doc = makeDoc({ '[data-reel]': [reel] }, root, env);
  const observers = [], idle = [];
  class FakeObserver { constructor(callback) { this.callback = callback; this.targets = []; observers.push(this); } observe(target) { this.targets.push(target); } }
  const { win, listeners } = makeWindow(env, { IntersectionObserver: FakeObserver, requestIdleCallback: fn => idle.push(fn), navigator: { connection: {} } });
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: doc, setImmediate }); } catch (e) { error = String(e); }
  const view = async on => { observers.filter(o => o.targets.includes(video)).forEach(o => o.callback([{ isIntersecting: on, target: video }])); await settle(); };
  const steps = [];
  const step = name => steps.push([name, { playing: !video.paused, plays: video.plays, label: toggle.textContent }]);
  await view(true); step('in view, loading');
  if (env.press) { (toggle.listeners.click || []).forEach(fn => fn({ type: 'click' })); await settle(); step('press'); await view(true); step('observer again'); }
  (listeners.load || []).forEach(l => l.fn({ type: 'load' })); await settle(); step('load');
  idle.splice(0).forEach(fn => fn()); await settle(); step('idle');
  await view(false); step('out of view');
  return { error, steps, hidden: toggle.hidden };
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
  out.early = await runEarly(desktop);
  out.earlyPress = await runEarly({ ...desktop, press: true });
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
  const motion = element('motion'); motion.hidden = true; motion.attrs['aria-pressed'] = 'false'; motion.textContent = 'Pause motion';
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

# Task 54: scenes.js leans the /work/ index tiles toward a fine pointer by setting --rx/--ry (work.css draws the lean). Runs
# with motion on a fine pointer, on touch, with reduced motion and with Pause motion pressed from the start; the matchMedia
# stub keeps each branch's teardown so the query stopping to match can be checked too.
WORK_TILT_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
const snap = el => Object.assign({}, el.style.props);
function run(env, paused) {
  const tiles = many('tile', 2);
  tiles.forEach(t => { t.style.removeProperty = function (key) { delete this.props[key]; }; });
  const parts = { '.wk-tile': tiles };
  const doc = { documentElement: element('html'), querySelectorAll: s => parts[s] || [], querySelector: s => (parts[s] || [])[0] || null };
  const { win } = makeWindow(env, { __glass: { paused: Boolean(paused) } });
  const stub = makeGsap(env);
  const teardowns = [];
  stub.gsap.matchMedia = () => ({ add(query, fn) { stub.log.queries.push(query); if (media(query, env)) { const off = fn(); if (off) teardowns.push(off); } } });
  win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger;
  vm.runInNewContext(source, { window: win, document: doc });
  // Each tile's box is left 100, top 100, 200 wide and 52 high (the harness default).
  const fire = (tile, type, x, y) => (tile.listeners[type] || []).forEach(fn => fn({ currentTarget: tile, clientX: x, clientY: y }));
  const out = { queries: stub.log.queries, types: Object.keys(tiles[0].listeners).filter(type => tiles[0].listeners[type].length) };
  fire(tiles[0], 'pointermove', 300, 152); out.corner = snap(tiles[0]);
  fire(tiles[0], 'pointermove', 100000, -100000); out.far = snap(tiles[0]);
  fire(tiles[0], 'pointermove', -100000, 100000); out.farOther = snap(tiles[0]);
  fire(tiles[0], 'pointerleave'); out.left = snap(tiles[0]);
  fire(tiles[1], 'pointermove', 100, 100); out.beforePause = snap(tiles[1]);
  win.__glass.paused = true;
  fire(tiles[1], 'pointermove', 300, 152); out.whilePaused = snap(tiles[1]);
  win.__glass.paused = Boolean(paused);
  fire(tiles[1], 'pointermove', 300, 152);
  teardowns.forEach(fn => fn());
  out.teardowns = teardowns.length;
  out.afterTeardown = tiles.map(snap);
  out.listenersAfter = tiles.map(t => Object.values(t.listeners).reduce((n, list) => n + list.length, 0));
  fire(tiles[0], 'pointermove', 300, 152); out.moveAfterTeardown = snap(tiles[0]);
  out.gsapWork = stub.log.tweens.length + stub.log.sets.length + stub.log.quick.length + stub.log.timelines.length;
  return out;
}
console.log(JSON.stringify({
  motion: run({ width: 1440, height: 900, fine: true, reduce: false }),
  touch: run({ width: 390, height: 844, fine: false, reduce: false }),
  reduced: run({ width: 1440, height: 900, fine: true, reduce: true }),
  paused: run({ width: 1440, height: 900, fine: true, reduce: false }, true),
}));
"""

# Task 55 (owner): scenes.js builds the Services "New website" vignette up in six steps, scrubbed by scroll. Each element
# marked data-step-layer="N" rises in over the Nth sixth of one timeline. Runs with motion (desktop and phone), with
# reduced motion and with the vignette already on screen at load; the list after it marks the step being built.
BUILD_SEQUENCE_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env, inView) {
  // Source order in services.html: plan, cream page, type, photo, service line, button, phone.
  const layers = ['1', '6', '2', '3', '4', '5', '6'].map((n, i) => { const el = element('layer' + i); el.dataset.stepLayer = n; return el; });
  const vig = element('vig', { '[data-step-layer]': layers });
  vig.getBoundingClientRect = () => ({ left: 0, top: inView ? 300 : 2000, width: 400, height: 330 });
  const parts = { '[data-build]': [vig] };
  const doc = { documentElement: element('html'), querySelectorAll: s => parts[s] || [], querySelector: s => (parts[s] || [])[0] || null };
  const items = many('item', 6);
  vig.nextElementSibling = element('steps', { li: items });
  const { win } = makeWindow(env);
  const stub = makeGsap(env);
  const teardowns = [];
  stub.gsap.matchMedia = () => ({ add(query, fn) { if (media(query, env)) { const off = fn(); if (off) teardowns.push(off); } } });
  win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger;
  vm.runInNewContext(source, { window: win, document: doc });
  const current = () => items.map((item, i) => item.ariaCurrent === 'step' ? i + 1 : 0).filter(Boolean);
  const out = stub.log.timelines.filter(tl => tl.vars.scrollTrigger && tl.vars.scrollTrigger.trigger === vig).map(tl => {
    const { trigger, ...rest } = tl.vars.scrollTrigger;
    // Drive the timeline's playhead (scrubbed by scroll, or sent to 1 by Pause motion) and read the list after each update.
    let at = 0;
    tl.progress = () => at;
    const marks = [0, 0.1, 1 / 6, 0.34, 0.5, 0.7, 0.84, 0.999, 1, 0.3].map(p => { at = p; tl.vars.onUpdate(); return current(); });
    return { scrollTrigger: rest, duration: tl.duration(), creates: stub.log.creates.length, marks,
      tweens: tl.tweens.map(t => ({ names: t.names, at: t.at, end: t.end, kind: t.kind, from: t.from, to: t.vars })) };
  });
  teardowns.forEach(fn => fn());
  return { scenes: out, afterTeardown: current(), cleared: items.every(item => item.ariaCurrent === null || item.ariaCurrent === undefined) };
}
console.log(JSON.stringify({
  motion: run({ width: 1440, height: 900, fine: true, reduce: false }),
  phone: run({ width: 390, height: 844, fine: false, reduce: false }),
  reduced: run({ width: 1440, height: 900, fine: true, reduce: true }),
  inView: run({ width: 1440, height: 900, fine: true, reduce: false }, true),
}));
"""

# Task 56 (owner): scenes.js wipes the Services Redesign figure from the dated page to the redesign, scrubbed by scroll, and
# the four-item list after it marks the improvement being shown. Runs with motion, with reduced motion and with the figure
# already on screen at load.
REDESIGN_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env, inView) {
  const after = element('after');
  const fig = element('fig', { '.rd-after': [after] });
  fig.getBoundingClientRect = () => ({ left: 0, top: inView ? 300 : 2000, width: 400, height: 330 });
  const parts = { '[data-redesign]': [fig] };
  const doc = { documentElement: element('html'), querySelectorAll: s => parts[s] || [], querySelector: s => (parts[s] || [])[0] || null };
  const items = many('item', 4);
  fig.nextElementSibling = element('steps', { li: items });
  const { win } = makeWindow(env);
  const stub = makeGsap(env);
  const teardowns = [];
  stub.gsap.matchMedia = () => ({ add(query, fn) { if (media(query, env)) { const off = fn(); if (off) teardowns.push(off); } } });
  win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger;
  vm.runInNewContext(source, { window: win, document: doc });
  const current = () => items.map((item, i) => item.ariaCurrent === 'step' ? i + 1 : 0).filter(Boolean);
  const out = stub.log.timelines.filter(tl => tl.vars.scrollTrigger && tl.vars.scrollTrigger.trigger === fig).map(tl => {
    const { trigger, ...rest } = tl.vars.scrollTrigger;
    let at = 0;
    tl.progress = () => at;
    const marks = [0, 0.2, 0.25, 0.5, 0.74, 0.8, 0.999, 1].map(p => { at = p; tl.vars.onUpdate(); return current(); });
    return { scrollTrigger: rest, creates: stub.log.creates.length, marks,
      tweens: tl.tweens.map(t => ({ names: t.names, at: t.at, kind: t.kind, from: t.from, to: t.vars })) };
  });
  const tweens = stub.log.tweens.length + stub.log.timelines.length;
  teardowns.forEach(fn => fn());
  return { scenes: out, tweens, afterTeardown: current(), cleared: items.every(item => item.ariaCurrent === null || item.ariaCurrent === undefined) };
}
console.log(JSON.stringify({
  motion: run({ width: 1440, height: 900, fine: true, reduce: false }),
  phone: run({ width: 390, height: 844, fine: false, reduce: false }),
  reduced: run({ width: 1440, height: 900, fine: true, reduce: true }),
  inView: run({ width: 1440, height: 900, fine: true, reduce: false }, true),
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
            if 'multi' in result or name.startswith(('hero', 'early')):
                continue  # clips: test_every_reel_on_a_page_plays_and_pauses_on_its_own; the homepage: the hero loop tests;
                # early: test_large_videos_wait_for_load_and_idle_but_a_press_plays_at_once
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
        # hidden and resume when it is back. Task 48: so does the showreel (it used to start before load). Order: laptop,
        # phone, showreel.
        r = self.node_json(REEL_SCRIPT, REEL)
        hero = r['heroDesktop']
        self.assertIsNone(hero['error'])
        self.assertEqual(hero['muted'], [True, True, True])
        self.assertEqual(hero['observed'], [1, 1, 1])
        self.assertEqual(hero['loadListeners'], 1)
        self.assertFalse(hero['motionHidden'])
        self.assertEqual(hero['pressed'], 'false')
        steps = [(name, playing) for name, playing, _ in hero['steps']]
        self.assertEqual(steps[:5], [('in view', [False, False, False]), ('loaded', [False, False, False]), ('idle', [True, True, True]),
                                     ('tab hidden', [False, False, False]), ('tab visible', [True, True, True])])
        # Already loaded when the script runs: no wait, no load listener.
        complete = r['heroComplete']
        self.assertEqual(complete['loadListeners'], 0)
        self.assertEqual(complete['steps'][0][1], [True, True, True])

    def test_large_videos_wait_for_load_and_idle_but_a_press_plays_at_once(self):
        # Task 48: the /work/ hero clip is on screen at load. Nothing calls play() (so its file is never fetched) until the
        # load event and idle; then it plays in view. A press before load plays it at once, and the observer (or the load
        # wait) never pauses that press while it stays in view.
        r = self.node_json(REEL_SCRIPT, REEL)
        early = r['early']
        self.assertIsNone(early['error'])
        self.assertFalse(early['hidden'])
        self.assertEqual([(name, state['playing'], state['plays']) for name, state in early['steps']],
                         [('in view, loading', False, 0), ('load', False, 0), ('idle', True, 1), ('out of view', False, 1)])
        press = r['earlyPress']
        self.assertIsNone(press['error'])
        self.assertEqual([(name, state['playing'], state['plays']) for name, state in press['steps']],
                         [('in view, loading', False, 0), ('press', True, 1), ('observer again', True, 1), ('load', True, 1),
                          ('idle', True, 1), ('out of view', False, 1)])
        self.assertEqual(press['steps'][1][1]['label'], 'Pause three signs video')
        js = REEL.read_text(encoding='utf-8')
        self.assertIn('const go = it.wanted && it.inView && !doc.hidden && (loaded || it.pressed);', js)

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
                self.assertEqual(frame['to']['clipPath'], 'inset(0% 0% 0% 0% round 0px)')  # Task 44: no box, square-edged
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

    def test_work_tiles_lean_only_for_a_fine_pointer_within_six_degrees(self):
        # Task 54 (owner): at most 6 degrees each way, set as two CSS variables (work.css draws them with perspective 900px);
        # flat on leave, on a move while Pause motion is pressed and after the query stops matching; nothing on touch, with
        # reduced motion, on keyboard focus, and no GSAP tween (so the ticker never wakes for it).
        r = self.node_json(WORK_TILT_SCRIPT, SCENES)
        query = '(prefers-reduced-motion: no-preference) and (hover: hover) and (pointer: fine)'
        motion = r['motion']
        self.assertIn(query, motion['queries'])
        self.assertEqual(sorted(motion['types']), ['pointerleave', 'pointermove'])  # no focus or touch handlers
        self.assertEqual(motion['corner'], {'--rx': '-4deg', '--ry': '5deg'})
        self.assertEqual(motion['far'], {'--rx': '6deg', '--ry': '6deg'})
        self.assertEqual(motion['farOther'], {'--rx': '-6deg', '--ry': '-6deg'})
        for snap in (motion['corner'], motion['far'], motion['farOther']):
            for value in snap.values():
                self.assertLessEqual(abs(float(value.removesuffix('deg'))), 6)
        self.assertEqual(motion['left'], {})
        self.assertTrue(motion['beforePause'])
        self.assertEqual(motion['whilePaused'], {})
        self.assertEqual(motion['teardowns'], 2)  # the scenes branch and the tilt branch
        self.assertEqual(motion['afterTeardown'], [{}, {}])
        self.assertEqual(motion['listenersAfter'], [0, 0])
        self.assertEqual(motion['moveAfterTeardown'], {})
        self.assertEqual(motion['gsapWork'], 0)
        for name in ('touch', 'reduced'):
            with self.subTest(env=name):
                run = r[name]
                self.assertEqual(run['types'], [])
                for key in ('corner', 'far', 'farOther', 'beforePause', 'whilePaused', 'moveAfterTeardown'):
                    self.assertEqual(run[key], {})
        paused = r['paused']
        for key in ('corner', 'far', 'farOther', 'beforePause', 'whilePaused'):
            with self.subTest(paused=key):
                self.assertEqual(paused[key], {})
        source = SCENES.read_text(encoding='utf-8')
        before, tilt = source.split('// Task 54 (owner)', 1)
        self.assertNotIn('--rx', before)  # set and cleared inside the tilt block only
        tilt = '\n'.join(line for line in tilt.splitlines() if not line.strip().startswith('//'))
        self.assertNotIn('focus', tilt)
        self.assertNotIn('gsap.to', tilt)
        self.assertNotIn('quickTo', tilt)

    def test_new_website_build_sequence_is_scrubbed_once_in_six_steps(self):
        # Task 55 (owner): one timeline on the vignette, scrubbed by scroll from the shared 85% line until its bottom
        # crosses 40% of the viewport. Nothing is pinned, and it plays once: glass.js ends every once-scene when Pause motion
        # is pressed, so the page shows built. Step N's layers rise 16px into place between N-1 and N (of 6); only opacity
        # and transform animate, and they are cleared at the end so services.css draws the finished page. Reduced motion,
        # or a vignette already on screen, gets no timeline at all.
        r = self.node_json(BUILD_SEQUENCE_SCRIPT, SCENES)
        for name in ('motion', 'phone'):
            with self.subTest(env=name):
                self.assertEqual(len(r[name]['scenes']), 1)
                scene = r[name]['scenes'][0]
                # The step being built is the list's aria-current="step"; none once built (Pause motion sends the
                # timeline to 1) or after the branch is torn down (reduced motion switched on mid-visit).
                self.assertEqual(scene['marks'], [[1], [1], [2], [3], [4], [5], [6], [6], [], [2]])
                self.assertEqual(r[name]['afterTeardown'], [])
                self.assertTrue(r[name]['cleared'])
                self.assertEqual(scene['scrollTrigger'], {'start': 'top 85%', 'once': True, 'end': 'bottom 40%', 'scrub': 0.5})
                self.assertEqual(scene['creates'], 0)
                self.assertEqual(scene['duration'], 6)
                steps = {(t['names'][0], t['at'], t['end']) for t in scene['tweens']}
                self.assertEqual(steps, {('layer0', 0, 1), ('layer1', 5, 6), ('layer2', 1, 2), ('layer3', 2, 3), ('layer4', 3, 4),
                                         ('layer5', 4, 5), ('layer6', 5, 6)})
                for tween in scene['tweens']:
                    self.assertEqual(tween['kind'], 'fromTo')
                    self.assertEqual(tween['from'], {'opacity': 0, 'y': 16})
                    self.assertEqual(tween['to']['clearProps'], 'opacity,transform')
                    self.assertLessEqual(set(tween['from']) | set(tween['to']), {'opacity', 'y', 'duration', 'stagger', 'clearProps'})
        for name in ('reduced', 'inView'):
            with self.subTest(env=name):
                self.assertEqual(r[name]['scenes'], [])
                self.assertEqual(r[name]['afterTeardown'], [])  # the list is never marked
        source = SCENES.read_text(encoding='utf-8')
        block = source.split("later($$('[data-build]'))", 1)[1].split('later(', 1)[0]
        for banned in ('pin', 'snap', 'style', 'innerHTML'):
            self.assertNotIn(banned, block)

    def test_redesign_figure_is_wiped_in_by_scroll_and_marks_four_steps(self):
        # Task 56 (owner): one timeline on the figure, scrubbed by scroll from the shared 85% line to bottom 40%, played once
        # (Pause motion ends it fully shown). Only the after layer's clip-path animates, cleared at the end so services.css
        # draws the redesign. The list item for the stage reached is aria-current="step"; none when finished or torn down.
        r = self.node_json(REDESIGN_SCRIPT, SCENES)
        for name in ('motion', 'phone'):
            with self.subTest(env=name):
                self.assertEqual(len(r[name]['scenes']), 1)
                scene = r[name]['scenes'][0]
                self.assertEqual(scene['scrollTrigger'], {'start': 'top 85%', 'once': True, 'end': 'bottom 40%', 'scrub': 0.5})
                self.assertEqual(scene['creates'], 0)
                self.assertEqual(scene['marks'], [[1], [1], [2], [3], [3], [4], [4], []])
                self.assertEqual(len(scene['tweens']), 1)
                tween = scene['tweens'][0]
                self.assertEqual((tween['names'], tween['at'], tween['kind']), (['after'], 0, 'fromTo'))
                self.assertEqual(tween['from'], {'clipPath': 'inset(0% 100% 0% 0%)'})
                self.assertEqual(tween['to']['clipPath'], 'inset(0% 0% 0% 0%)')
                self.assertEqual(tween['to']['clearProps'], 'clipPath')
                self.assertLessEqual(set(tween['from']) | set(tween['to']), {'clipPath', 'duration', 'ease', 'clearProps'})
                self.assertEqual(r[name]['afterTeardown'], [])
                self.assertTrue(r[name]['cleared'])
        for name in ('reduced', 'inView'):
            with self.subTest(env=name):
                self.assertEqual(r[name]['scenes'], [])
                self.assertEqual(r[name]['tweens'], 0)
                self.assertEqual(r[name]['afterTeardown'], [])
                self.assertTrue(r[name]['cleared'])
        source = SCENES.read_text(encoding='utf-8')
        block = source.split("later($$('[data-redesign]'))", 1)[1].split('later(', 1)[0]
        for banned in ('pin', 'snap', 'style', 'innerHTML'):
            self.assertNotIn(banned, block)

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
GLASS_SCENE = Path(__file__).resolve().parents[1] / 'assets' / 'glass-scene.js'

# glass-boot.js: which environments import the scene, and when. import() is replaced by a recording stub (vm scripts have
# no module loader); everything else runs as shipped.
GLASS_BOOT_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8').replace('import(SCENE)', '__import(SCENE)');
const settle = () => new Promise(resolve => setImmediate(resolve));
async function run(env) {
  const host = element('host');
  if (env.kind) host.setAttribute('data-gl-kind', env.kind);
  const imports = [], idle = [], timers = [], contexts = [], attrs = [], made = [];
  let lost = 0;
  // Task 48: the test canvas's context is the scene's own; WEBGL_lose_context releases it when nothing takes it.
  const doc = { readyState: env.complete ? 'complete' : 'interactive', querySelector: s => (s === '[data-gl]' && !env.noHost ? host : null),
    createElement: tag => { const canvas = { tag, getContext: (kind, a) => { contexts.push(kind); attrs.push(a); if (env.noWebGL) return null;
      const context = { getExtension: name => (name === 'WEBGL_lose_context' ? { loseContext() { lost++; } } : null) }; made.push({ canvas, context }); return context; } };
      return canvas; } };
  const nav = { connection: { saveData: Boolean(env.saveData) } };
  if (env.memory !== undefined) nav.deviceMemory = env.memory;
  if (env.cores !== undefined) nav.hardwareConcurrency = env.cores;
  const { win, listeners } = makeWindow(env, { navigator: nav, requestIdleCallback: (fn, o) => idle.push([fn, o]), setTimeout: (fn, ms) => timers.push([fn, ms]) });
  let started = null, handed = null;
  const __import = url => { imports.push(url); return env.fail ? Promise.reject(new Error('offline')) : Promise.resolve({ start: (h, g, gl) => {
    if (env.startThrows) throw new Error('no GPU');
    started = { host: h.name, shared: g === win.__glass };
    handed = Boolean(gl && made.length === 1 && gl.canvas === made[0].canvas && gl.context === made[0].context);
    return !env.declines; } }); };
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
  out.attrs = attrs;
  out.started = started;
  out.handed = handed;
  out.lost = lost;
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
    sheetsNoWebGL: { ...desktop, kind: 'sheets', noWebGL: true }, photosNoWebGL: { ...desktop, kind: 'photos', noWebGL: true },
    declines: { ...desktop, kind: 'slab', declines: true }, startThrows: { ...desktop, startThrows: true } };
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
  const motion = element('motion'); motion.hidden = true; motion.attrs['aria-pressed'] = 'false'; motion.textContent = 'Pause motion';
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
  const out = { initial: win.__glass.paused, hidden: motion.hidden, state: motion.attrs['aria-pressed'], name: motion.textContent, pausedAttr: 'data-paused' in motion.attrs, playing: videos.map(v => !v.paused) };
  if (env.offScreen) observers.forEach(o => o.targets.forEach(t => o.cb([{ isIntersecting: false, target: t }])));
  else observers.forEach(o => o.targets.forEach(t => o.cb([{ isIntersecting: true, target: t }])));
  out.hiddenAfterScroll = motion.hidden;
  out.playing = videos.map(v => !v.paused);
  (motion.listeners.click || []).forEach(fn => fn({ type: 'click' }));
  out.pressed = { paused: win.__glass.paused, state: motion.attrs['aria-pressed'], name: motion.textContent, playing: videos.map(v => !v.paused) };
  (motion.listeners.click || []).forEach(fn => fn({ type: 'click' }));
  out.released = { paused: win.__glass.paused, state: motion.attrs['aria-pressed'], name: motion.textContent, playing: videos.map(v => !v.paused) };
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
  let lenis = 0, ticks = 0, sleeps = 0, wakes = 0, removed = 0, destroyed = 0;
  class Lenis { constructor(o) { lenis++; this.options = o; } on() {} raf() {} destroy() { destroyed++; } }
  const { win } = makeWindow(env, { Lenis, requestAnimationFrame: fn => { frames.push(fn); return frames.length; }, cancelAnimationFrame: id => cancelled.push(id),
    navigator: { connection: { saveData: Boolean(env.saveData) }, userAgentData: { brands: env.chromium ? [{ brand: 'Chromium' }] : [{ brand: 'Firefox' }] } } });
  if (env.gsap) { const stub = makeGsap(env); stub.gsap.ticker = { add(fn) { ticks++; return fn; }, remove() { removed++; }, sleep() { sleeps++; }, wake() { wakes++; } };
    win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; }
  let error = null;
  try { vm.runInNewContext(source, { window: win, document: doc, getComputedStyle: () => ({ borderTopLeftRadius: '20px' }), Promise }); } catch (e) { error = String(e); }
  const out = { error, lenis, ticks, sleeps, refract: root.classList.contains('lg-refract'), driftFrames: frames.length };
  if (frames.length) { frames.shift()(1000); }
  out.moved = fields[0].style.transform || null;
  const before = cancelled.length;
  win.__glass.paused = true; win.__glass.onPauseChange(true);
  out.cancelledOnPause = cancelled.length - before;
  out.paused = { sleeps, wakes, removed, destroyed, lenis: Boolean(win.__glass.lenis) };
  const queued = frames.length;
  win.__glass.paused = false; win.__glass.onPauseChange(false);
  out.resumed = frames.length - queued;
  out.released = { sleeps, wakes, lenisMade: lenis, ticks, lenis: Boolean(win.__glass.lenis) };
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

    def test_hero_exit_pose_ends_facing_the_camera_and_larger(self):
        # Task 44: glass-scene.js's heroPose, imported as the real module (pure, no GPU). Over the whole exit (e 0..1 in
        # 0.05 steps), a range of times and pointer positions, the C never turns toward edge-on, the lockup never tilts back
        # far, the name never reads backwards, and at the end the C faces the camera and is larger than at rest.
        script = r'''
const { pathToFileURL } = require('url');
(async () => {
  const m = await import(pathToFileURL(process.argv[1]).href);
  const out = { cYaw: 0, tilt: 0, yaw: 0, endCYaw: 0, introCYaw: 0, YAW: m.YAW };
  for (let i = 0; i <= 20; i++) {
    const e = i / 20;
    for (let t = 0; t <= 90; t += 0.25) for (let px = -1; px <= 1.0001; px += 0.5) for (let py = -1; py <= 1.0001; py += 0.5) {
      const p = m.heroPose(e, t, px, py);
      out.cYaw = Math.max(out.cYaw, Math.abs(p.yaw + p.markYaw));
      out.tilt = Math.max(out.tilt, Math.abs(p.tilt));
      out.yaw = Math.max(out.yaw, Math.abs(p.yaw));
      if (i === 20) out.endCYaw = Math.max(out.endCYaw, Math.abs(p.yaw + p.markYaw));
      for (const k of [0, 0.5]) {  // during the intro too
        const q = m.heroPose(e, t, px, py, k);
        out.introCYaw = Math.max(out.introCYaw, Math.abs(q.yaw + q.markYaw));
        out.yaw = Math.max(out.yaw, Math.abs(q.yaw));
      }
    }
  }
  out.scaleRest = m.heroPose(0, 0, 0, 0).scale; out.scaleEnd = m.heroPose(1, 0, 0, 0).scale;
  console.log(JSON.stringify(out));
})();
'''
        r = self.node_json(script, GLASS_SCENE)
        self.assertLessEqual(r['cYaw'], 0.45)
        self.assertLessEqual(r['introCYaw'], 0.45)
        self.assertLessEqual(r['endCYaw'], 0.12)
        self.assertLessEqual(r['tilt'], 0.22)
        self.assertLessEqual(r['YAW'], 0.56)
        self.assertLessEqual(r['yaw'], r['YAW'] + 1e-9)
        self.assertGreaterEqual(r['scaleEnd'], 1.15 * r['scaleRest'])

    def test_hero_exit_takes_the_name_away_before_it_ghosts(self):
        # Task 45: heroPose's word (the CENDAVO name's share, 1..0) is whole until e = 0.2, gone from e = 0.5, never grows back
        # in between and never leaves 0..1, at any time, pointer position or intro state.
        script = r'''
const { pathToFileURL } = require('url');
(async () => {
  const m = await import(pathToFileURL(process.argv[1]).href);
  const out = { min: 1, max: 0, early: 1, late: 0, rises: 0, typed: true };
  for (let t = 0; t <= 60; t += 0.5) for (const px of [-1, 0, 1]) for (const k of [0, 0.5, 1]) {
    let prev = Infinity;
    for (let i = 0; i <= 200; i++) {
      const e = i / 200, w = m.heroPose(e, t, px, -px, k).word;
      if (typeof w !== 'number' || Number.isNaN(w)) out.typed = false;
      out.min = Math.min(out.min, w); out.max = Math.max(out.max, w);
      if (e <= 0.2) out.early = Math.min(out.early, w);
      if (e >= 0.5) out.late = Math.max(out.late, w);
      if (w > prev + 1e-12) out.rises++;
      prev = w;
    }
  }
  console.log(JSON.stringify(out));
})();
'''
        r = self.node_json(script, GLASS_SCENE)
        self.assertTrue(r['typed'])
        self.assertGreaterEqual(r['min'], 0)
        self.assertLessEqual(r['max'], 1)
        self.assertEqual(r['early'], 1)
        self.assertEqual(r['late'], 0)
        self.assertEqual(r['rises'], 0)

    def test_services_panes_fan_so_every_title_reads(self):
        # Task 45: glass-page.js's paneLayout, imported as the real module (pure, no GPU). Fanned out (f = 1), in pane units:
        # pane 1 is highest and furthest left, pane 3 lowest, furthest right and nearest; each pane the next one covers
        # keeps at least 40% of its height, its top 40% (the number and title) clear. Folded (f = 0) they stack.
        script = r'''
const { pathToFileURL } = require('url');
(async () => {
  const m = await import(pathToFileURL(process.argv[1]).href);
  console.log(JSON.stringify({ pane: m.PANE, open: [0, 1, 2].map(i => m.paneLayout(i, 1)), shut: [0, 1, 2].map(i => m.paneLayout(i, 0)) }));
})();
'''
        r = self.node_json(script, GLASS_PAGE)
        h, w = r['pane']['h'], r['pane']['w']
        self.assertEqual((w, h), (3.2, 2.0))
        p = r['open']
        self.assertTrue(p[0]['y'] > p[1]['y'] > p[2]['y'])
        self.assertTrue(p[0]['x'] < p[1]['x'] < p[2]['x'])
        self.assertTrue(p[0]['z'] < p[1]['z'] < p[2]['z'])
        for i in (0, 1):
            with self.subTest(pane=i + 1):
                top, next_top = p[i]['y'] + h / 2, p[i + 1]['y'] + h / 2
                shown = top - next_top  # the next pane is in front and lower: this much of pane i stays clear
                self.assertGreaterEqual(shown, 0.4 * h)
                self.assertLessEqual(next_top, top - 0.4 * h)  # its title strip is never under the next pane
                self.assertLess(abs(p[i + 1]['x'] - p[i]['x']), w)  # still a stack: the panes overlap sideways
        for q in r['shut']:
            self.assertEqual((q['x'], q['y'], q['z']), (0, 0, 0))
        source = GLASS_PAGE.read_text()
        self.assertIn('const L = paneLayout(i, f);', source)
        self.assertIn('g.position.set(L.x, L.y, L.z);', source)

    def test_hero_screens_are_sharp_and_the_dark_one_stays_clear_of_the_name(self):
        # Task 44: the screens' mip bias is low (refracted content, not mush); the name is milky white frosted glass; and in
        # every layout the dark hb screen sits at least one wordmark-width from the name and, as the camera sees it, never
        # overlaps it.
        script = r'''
const { pathToFileURL } = require('url');
(async () => {
  const m = await import(pathToFileURL(process.argv[1]).href);
  const aspects = [0.5, 0.7, 0.84, 0.86, 1.0, 1.2, 1.45, 1.6, 1.78, 2.13, 2.4];
  console.log(JSON.stringify({ screens: m.SCREENS, word: m.WORD, glass: m.WORD_GLASS, markY: m.MARK_Y,
    layouts: aspects.map(a => ({ aspect: a, ...m.heroLayout(a) })) }));
})();
'''
        r = self.node_json(script, GLASS_SCENE)
        for name in ('gl', 'hb'):
            self.assertLessEqual(r['screens'][name]['bias'], 0.8)
        glass = r['glass']
        rgb = [int(glass['attenuationColor'][i:i + 2], 16) / 255 for i in (1, 3, 5)]
        self.assertLessEqual(abs(rgb[0] - rgb[1]), 0.02)
        self.assertLessEqual(abs(rgb[1] - rgb[2]), 0.02)
        self.assertTrue(all(c >= 0.95 for c in rgb), rgb)
        self.assertGreaterEqual(glass['roughness'], 0.2)
        self.assertNotEqual(glass['attenuationColor'].lower(), '#d9e1e6')
        word, hb = r['word'], r['screens']['hb']
        camera = 14  # the camera's distance; a point at depth z appears scaled by 14 / (14 - z)
        for lay in r['layouts']:
            with self.subTest(aspect=lay['aspect']):
                s = lay['logo']['s']
                wx, wy = lay['logo']['x'], lay['logo']['y'] + word['y'] * s
                x, y, z = lay['hb'][:3]
                self.assertGreaterEqual(math.hypot(x - wx, y - wy), word['w'])  # one wordmark-width away (unscaled)
                f = camera / (camera - z)
                screen = (x * f - hb['w'] / 2 * f, x * f + hb['w'] / 2 * f, y * f - hb['h'] / 2 * f, y * f + hb['h'] / 2 * f)
                name = (wx - word['w'] / 2 * s, wx + word['w'] / 2 * s, wy - word['h'] * s, wy + word['h'] * s)
                apart = screen[1] < name[0] or screen[0] > name[1] or screen[3] < name[2] or screen[2] > name[3]
                self.assertTrue(apart, (screen, name))

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

    def test_webgl_test_context_is_the_scenes_own_or_is_released(self):
        # Task 48: glass-boot.js tests for WebGL2 once, with the renderer's attributes, and hands that canvas and context to
        # start(), which draws with them: no throwaway context. If the import fails, start throws or start does not take
        # it, the context is released at once (WEBGL_lose_context) and the still stays (the host is never made live).
        r = self.node_json(GLASS_BOOT_SCRIPT, GLASS_BOOT)
        for name in ('desktop', 'complete', 'slab', 'panes', 'sheets', 'photos', 'mark'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['contexts'], ['webgl2'])  # one test, WebGL2 only (three.js r170 needs it)
                self.assertEqual(r[name]['attrs'], [{'alpha': False, 'powerPreference': 'high-performance'}])
                self.assertTrue(r[name]['handed'])
                self.assertEqual(r[name]['lost'], 0)
        for name in ('fail', 'startThrows', 'declines'):
            with self.subTest(case=name):
                self.assertEqual(r[name]['contexts'], ['webgl2'])
                self.assertEqual(r[name]['lost'], 1)
                self.assertTrue(r[name]['liveRemoved'])
        self.assertIsNone(r['startThrows']['started'])
        self.assertEqual(r['declines']['started'], {'host': 'host', 'shared': True})
        self.assertEqual(r['noWebGL']['lost'], 0)  # nothing was made, nothing to release
        self.assertEqual(r['noWebGL']['imports'], [])
        # Both scenes pass the handed context to three.js and report that they took it.
        shapes = (GLASS_BOOT.parent / 'glass-shapes.js').read_text(encoding='utf-8')
        self.assertIn('return gl && gl.canvas && gl.context ? { ...base, canvas: gl.canvas, context: gl.context } : base;', shapes)
        self.assertIn("const base = { antialias: true, alpha: false, powerPreference: 'high-performance' };", shapes)
        for module in (GLASS_PAGE, GLASS_SCENE):
            with self.subTest(module=module.name):
                code = module.read_text(encoding='utf-8')
                self.assertIn('export function start(host, shared, gl) {', code)
                self.assertIn('const renderer = new THREE.WebGLRenderer(rendererOptions(gl));', code)
                self.assertIn('return true;\n}', code)

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
        self.assertEqual(shared['pressed'], {'paused': True, 'state': 'true', 'name': 'Play motion', 'playing': [False, False]})
        self.assertEqual(shared['released'], {'paused': False, 'state': 'false', 'name': 'Pause motion', 'playing': [True, True]})
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
                # Task 59: aria-pressed and the visible name follow the state together (no second state attribute).
                self.assertEqual((case['state'], case['name'], case['pausedAttr']), ('false', 'Pause motion', False))
                self.assertEqual((case['pressed']['state'], case['pressed']['name']), ('true', 'Play motion'))
                self.assertTrue(case['pressed']['paused'])
                self.assertEqual((case['released']['state'], case['released']['name']), ('false', 'Pause motion'))
                self.assertFalse(case['released']['paused'])
                self.assertEqual(case['calls'], [True, False])  # the WebGL pause hook fired once each way
                self.assertEqual(case['listeners'], 1)  # one owner: reel.js adds no second click handler
        self.assertEqual(r['offScreen']['playing'], [False, False])  # nothing on screen plays, the button stays
        reduced = r['reducedNoLoops']
        self.assertTrue(reduced['initial'])  # reduced motion: starts pressed
        self.assertEqual((reduced['state'], reduced['name'], reduced['hidden']), ('true', 'Play motion', False))
        self.assertEqual((reduced['pressed']['state'], reduced['pressed']['name']), ('false', 'Pause motion'))  # a press releases it

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
        # Task 48: reduced motion puts GSAP's ticker to sleep and adds nothing to it. Pause motion ends Lenis (native
        # scrolling) and sleeps the ticker; releasing it wakes the ticker and builds Lenis again on it.
        self.assertEqual(motion['sleeps'], 0)
        self.assertEqual(reduced['sleeps'], 1)
        self.assertEqual(reduced['released']['ticks'], 0)
        self.assertEqual(motion['paused'], {'sleeps': 1, 'wakes': 0, 'removed': 1, 'destroyed': 1, 'lenis': False})
        self.assertEqual(motion['released'], {'sleeps': 1, 'wakes': 1, 'lenisMade': 2, 'ticks': 2, 'lenis': True})
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


# Task 46: site.js's Pause motion toggle on its own (it now sits in the header): its initial state from reduced motion and
# Save-Data, and a press flipping aria-pressed, window.__glass.paused and every pauseFns listener. Task 59 (owner-mandated):
# the visible name follows the state too ("Pause motion" while motion runs, "Play motion" once paused).
SITE_TOGGLE_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  // As build_site.py ships it.
  const toggle = element('toggle'); toggle.hidden = true; toggle.attrs['aria-pressed'] = 'false'; toggle.textContent = 'Pause motion';
  const parts = { '[data-motion-toggle]': [toggle] };
  const doc = { documentElement: element('html'), listeners: {}, addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const { win } = makeWindow(env, { scrollY: 0, location: { pathname: '/' }, navigator: { connection: { saveData: Boolean(env.saveData) } } });
  const calls = [];
  win.__glass = { paused: false, heroP: 0, pointer: { x: 0, y: 0 }, pauseFns: [p => calls.push(['a', p]), p => calls.push(['b', p])] };
  vm.runInNewContext(source, { window: win, document: doc, getComputedStyle: () => ({}) });
  const snap = () => ({ aria: toggle.getAttribute('aria-pressed'), paused: win.__glass.paused, name: toggle.textContent, label: toggle.getAttribute('aria-label'), other: toggle.getAttribute('data-paused') });
  const out = { hidden: toggle.hidden, load: snap() };
  (toggle.listeners.click || []).forEach(fn => fn({ type: 'click' })); out.first = snap();
  (toggle.listeners.click || []).forEach(fn => fn({ type: 'click' })); out.second = snap();
  out.calls = calls;
  return out;
}
const desktop = { width: 1440, height: 900, fine: true, reduce: false };
console.log(JSON.stringify({ plain: run(desktop), reduced: run({ ...desktop, reduce: true }), saveData: run({ ...desktop, saveData: true }) }));
"""

# Task 46: the before/after picture is draggable. Pointer events on .compare-stage drive the range input (value, then its
# input event), which stays the source of truth: --pos, aria-valuetext and the Before/After buttons follow from it.
DRAG_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
class Event { constructor(type, options) { this.type = type; Object.assign(this, options || {}); } }
function run(env) {
  const range = element('range'), before = element('before'), after = element('after'), controls = element('controls');
  const figure = element('figure'), stage = element('stage');
  before.dataset.compareSet = '0'; after.dataset.compareSet = '100'; controls.hidden = true;
  controls.parts = { 'input[type="range"]': [range], '[data-compare-set]': [before, after] };
  figure.parts = { '[data-compare-controls]': [controls], '.compare-stage': [stage] };
  stage.getBoundingClientRect = () => ({ left: 100, top: 0, width: 400, height: 250 });
  const captured = new Set(), captures = [], releases = [];
  stage.setPointerCapture = id => { captured.add(id); captures.push(id); };
  stage.releasePointerCapture = id => { captured.delete(id); releases.push(id); };
  stage.hasPointerCapture = id => captured.has(id);
  let inputs = 0;
  range.dispatchEvent = e => { if (e.type === 'input') inputs++; (range.listeners[e.type] || []).forEach(fn => fn(e)); return true; };
  const root = element('html'); root.classList = classList(['js', 'motion']);
  const parts = { '[data-compare]': [figure] };
  const doc = { documentElement: root, querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const { win } = makeWindow(env, { requestAnimationFrame: () => 1, cancelAnimationFrame() {} });
  let log = null;
  if (env.gsap) { const stub = makeGsap(env); win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger; log = stub.log; }
  vm.runInNewContext(source, { window: win, document: doc, Event });
  const fire = (type, e) => (stage.listeners[type] || []).forEach(fn => fn({ type, pointerId: 1, button: 0, pointerType: 'mouse', ...e }));
  const snap = () => ({ value: String(range.value), pos: figure.style.props['--pos'], text: range.attrs['aria-valuetext'],
    before: before.attrs['aria-pressed'], after: after.attrs['aria-pressed'], inputs, captured: captured.size });
  const out = { listens: Object.keys(stage.listeners).sort(), start: snap(), steps: [] };
  const step = (name, act) => { act(); out.steps.push([name, snap()]); };
  step('mouse down at 25%', () => fire('pointerdown', { clientX: 200 }));
  step('drag to 60%', () => fire('pointermove', { clientX: 340 }));
  step('drag past the right edge', () => fire('pointermove', { clientX: 900 }));
  step('drag past the left edge', () => fire('pointermove', { clientX: -50 }));
  step('mouse up', () => fire('pointerup', { clientX: -50 }));
  step('hover after release', () => fire('pointermove', { clientX: 300 }));
  step('right button', () => fire('pointerdown', { clientX: 300, button: 2 }));
  step('touch down', () => fire('pointerdown', { pointerId: 7, pointerType: 'touch', clientX: 400 }));
  step('touch scrolls the page', () => fire('pointercancel', { pointerId: 7, pointerType: 'touch' }));
  step('touch tap', () => { fire('pointerdown', { pointerId: 8, pointerType: 'touch', clientX: 400 }); fire('pointerup', { pointerId: 8, pointerType: 'touch', clientX: 400 }); });
  step('touch drag', () => { fire('pointerdown', { pointerId: 9, pointerType: 'touch', clientX: 400 }); fire('pointermove', { pointerId: 9, pointerType: 'touch', clientX: 140 }); });
  step('touch lifts after the drag', () => fire('pointerup', { pointerId: 9, pointerType: 'touch', clientX: 400 }));
  out.captures = captures; out.releases = releases;
  if (log) {
    // A drag before the comparison scrolls into view means the demonstration sweep never runs on top of it.
    const trigger = log.creates.find(c => c.trigger === figure);
    const timelines = log.timelines.length;
    if (trigger) trigger.onEnter();
    out.sweepAfterDrag = log.timelines.length > timelines;
    out.hadTrigger = Boolean(trigger);
  }
  return out;
}
const desktop = { width: 1440, height: 900, fine: true, reduce: false };
console.log(JSON.stringify({ plain: run(desktop), motion: run({ ...desktop, gsap: true }) }));
"""


class HeaderPauseAndDragScriptTests(unittest.TestCase):
    def node_json(self, script, path):
        out = subprocess.run(['node', '-e', script, str(path)], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_site_js_pause_toggle_starts_from_the_visitors_settings_and_flips_everything(self):
        r = self.node_json(SITE_TOGGLE_SCRIPT, SITE)
        for case, start in (('plain', False), ('reduced', True), ('saveData', True)):
            with self.subTest(case=case):
                out = r[case]
                self.assertFalse(out['hidden'])  # revealed once site.js runs
                # Task 59 (owner-mandated): aria-pressed is "true" while paused and "false" while running, and the visible
                # name follows the same state; no aria-label overrides the name and no second attribute holds the state.
                state = lambda paused: {'aria': str(paused).lower(), 'paused': paused, 'label': None, 'other': None,
                                        'name': 'Play motion' if paused else 'Pause motion'}
                self.assertEqual(out['load'], state(start))
                self.assertEqual(out['first'], state(not start))
                self.assertEqual(out['second'], state(start))  # two presses return to the start
                # Every listener in the fan-out hears each press, in order.
                self.assertEqual(out['calls'], [['a', not start], ['b', not start], ['a', start], ['b', start]])

    def test_dragging_the_picture_moves_the_range_which_stays_the_source_of_truth(self):
        r = self.node_json(DRAG_SCRIPT, HOME)
        for case in ('plain', 'motion'):
            with self.subTest(case=case):
                out = r[case]
                self.assertEqual(out['listens'], ['pointercancel', 'pointerdown', 'pointermove', 'pointerup'])
                steps = dict(out['steps'])
                at25 = steps['mouse down at 25%']
                self.assertEqual((at25['value'], at25['pos'], at25['text']), ('25', '25%', '25 of 100 showing the redesign'))
                self.assertEqual((at25['inputs'], at25['captured']), (1, 1))  # through the input event, with capture
                self.assertEqual((steps['drag to 60%']['value'], steps['drag to 60%']['pos']), ('60', '60%'))
                right = steps['drag past the right edge']
                self.assertEqual((right['value'], right['pos'], right['text'], right['after']), ('100', '100%', 'After only', 'true'))
                left = steps['drag past the left edge']
                self.assertEqual((left['value'], left['text'], left['before'], left['after']), ('0', 'Before only', 'true', 'false'))
                self.assertEqual(steps['mouse up']['captured'], 0)  # released
                self.assertEqual(steps['hover after release'], steps['mouse up'])  # moving without a press does nothing
                self.assertEqual(steps['right button'], steps['mouse up'])  # only the main button drags
                # Touch: nothing moves on contact (the page may be scrolling); a scroll ends in pointercancel and lets go.
                self.assertEqual(steps['touch down']['value'], '0')
                self.assertEqual(steps['touch scrolls the page']['value'], '0')
                self.assertEqual(steps['touch scrolls the page']['captured'], 0)
                self.assertEqual(steps['touch tap']['value'], '75')  # a tap jumps there
                self.assertEqual(steps['touch drag']['value'], '10')
                self.assertEqual(steps['touch lifts after the drag']['value'], '10')  # lifting does not jump back
                self.assertEqual(steps['touch lifts after the drag']['captured'], 0)
                self.assertEqual(out['captures'], [1, 7, 8, 9])
                self.assertEqual(out['releases'], [1, 7, 8, 9])
        self.assertTrue(r['motion']['hadTrigger'])
        self.assertFalse(r['motion']['sweepAfterDrag'])  # the visitor's choice is never swept over



# Task 47 (owner-mandated): the enquiry form's page script in a stub DOM (start-up order, live re-checks, the honeypot's
# payload key) and makeKey without a working crypto; site.js's mobile-menu scroll lock; the homepage's grouped reveals.
ENQUIRY = Path(__file__).resolve().parents[1] / 'assets' / 'enquiry.js'

ENQUIRY_PAGE_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
const FIELDS = ['name', 'email', 'phone', 'business', 'website', 'service', 'message'];
function page(env) {
  const log = [], sent = [];
  const controls = {};
  FIELDS.concat('hp_xq').forEach(name => {
    const el = element(name); el.name = name; el.value = '';
    el.focus = () => log.push('focus:' + name);
    controls[name] = el;
  });
  const slots = {}; FIELDS.forEach(name => { slots[name] = element('slot-' + name); });
  const button = element('button'); button.textContent = 'Send enquiry';
  let disabled = true;  // as the HTML ships it
  Object.defineProperty(button, 'disabled', { get: () => disabled, set: v => { disabled = v; log.push('disabled=' + v); } });
  const status = element('status');
  const form = element('form');
  form.elements = controls;
  form.reset = () => FIELDS.concat('hp_xq').forEach(name => { controls[name].value = ''; });
  form.querySelector = s => {
    if (s === '[type="submit"]') return button;
    const m = s.match(/^\[data-error-for="(\w+)"\]$/);
    return m ? slots[m[1]] || null : null;
  };
  const add = form.addEventListener;
  form.addEventListener = (type, fn) => { log.push('listen:' + type); add.call(form, type, fn); };
  const doc = { querySelector: s => (s === '[data-enquiry]' ? form : s === '[data-enquiry-status]' ? status : null) };
  const sandbox = { document: doc, window: {}, requestAnimationFrame: fn => fn(), performance: { now: () => 5000 }, setTimeout, clearTimeout, URL,
    fetch: async (url, init) => { sent.push(JSON.parse(init.body)); return { status: 201, json: async () => ({ ok: true, id: 1 }) }; } };
  if (env.crypto) sandbox.crypto = require('crypto').webcrypto;
  let error = null;
  try { vm.runInNewContext(source, sandbox); } catch (e) { error = String(e); }
  const fire = (type, el) => (form.listeners[type] || []).map(fn => fn({ type, target: el, preventDefault() {} }));
  const submit = () => Promise.all(fire('submit', form));
  const view = () => Object.fromEntries(FIELDS.map(name => [name, { error: slots[name].textContent, invalid: controls[name].getAttribute('aria-invalid') }]));
  return { log, sent, controls, button, status, form, fire, submit, view, error, disabled: () => disabled };
}
(async () => {
  const out = {};
  for (const [label, env] of [['withCrypto', { crypto: true }], ['noCrypto', { crypto: false }]]) {
    const p = page(env);
    out[label] = { error: p.error, log: p.log.slice(), disabled: p.disabled() };
  }
  // Live re-checks.
  const p = page({ crypto: true });
  p.controls.email.value = 'bad';
  p.fire('focusout', p.controls.email);  // never marked invalid: leaving it does not check it early
  p.fire('input', p.controls.email);
  out.beforeSubmit = p.view();
  await p.submit();  // everything empty: the required fields are marked and the first one is focused
  out.afterSubmit = p.view();
  out.statusAfterSubmit = p.status.textContent;
  const mark = p.log.length;
  p.controls.name.value = 'Sam';
  p.fire('input', p.controls.name);
  out.nameFixed = p.view().name;
  p.controls.email.value = 'sam@';
  p.fire('input', p.controls.email);
  out.emailStillWrong = p.view().email;
  p.controls.email.value = 'sam@example.com';
  p.fire('input', p.controls.email);
  out.emailTypedRight = p.view().email;
  p.controls.message.value = 'too short';
  p.fire('focusout', p.controls.message);
  out.messageStillShort = p.view().message;
  p.controls.message.value = 'Hello there, a website please.';
  p.fire('focusout', p.controls.message);
  out.messageFixed = p.view().message;
  p.controls.service.value = 'not-sure';
  p.fire('change', p.controls.service);
  out.serviceFixed = p.view().service;
  p.controls.phone.value = 'abc';  // never marked invalid, so typing in it does not check it
  p.fire('input', p.controls.phone);
  out.phoneUntouched = p.view().phone;
  p.controls.name.value = '';  // cleared once fixed: no longer invalid, so it is not checked until the next submit
  p.fire('input', p.controls.name);
  out.nameClearedAfterFix = p.view().name;
  out.sideEffects = p.log.slice(mark);
  out.statusAfterRechecks = p.status.textContent;
  // The honeypot travels to the server as company_url; the page's own name for it is never sent.
  const q = page({ crypto: true });
  q.controls.name.value = 'Sam'; q.controls.email.value = 'sam@example.com'; q.controls.service.value = 'not-sure';
  q.controls.message.value = 'Hello there, a website please.'; q.controls.hp_xq.value = 'https://spam.example';
  await q.submit();
  out.payload = q.sent[0];
  console.log(JSON.stringify(out));
})();
"""

MAKE_KEY_SCRIPT = r"""
const vm = require('vm');
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const real = require('crypto').webcrypto;
const cases = {
  none: undefined,
  nullCrypto: null,
  empty: {},
  throwingRandomUUID: { randomUUID() { throw new Error('insecure context'); } },
  badRandomUUID: { randomUUID: () => 'not-a-uuid' },
  throwingGetRandomValues: { getRandomValues() { throw new Error('quota'); } },
  shortGetRandomValues: { getRandomValues: () => new Uint8Array(4) },
  getRandomValuesOnly: { getRandomValues: b => real.getRandomValues(b) },
  full: real,
};
const out = {};
for (const [name, crypto] of Object.entries(cases)) {
  const module = { exports: {} };
  const sandbox = { module, URL };
  if (name !== 'none') sandbox.crypto = crypto;
  vm.runInNewContext(source, sandbox);
  const keys = [];
  let error = null;
  try { for (let i = 0; i < 50; i++) keys.push(module.exports.makeKey()); } catch (e) { error = String(e); }
  out[name] = { error, keys, unique: new Set(keys).size };
}
const module = { exports: {} };
vm.runInNewContext(source, { module, URL });
const api = module.exports;
out.fieldError = {
  emailBad: api.fieldError('email', 'bad'), emailGood: api.fieldError('email', 'sam@example.com'), nameEmpty: api.fieldError('name', '  '),
  phoneEmpty: api.fieldError('phone', ''), phoneBad: api.fieldError('phone', 'abc'), websiteBad: api.fieldError('website', 'nope'),
  serviceBad: api.fieldError('service', 'gold'), messageShort: api.fieldError('message', 'short'), unknown: api.fieldError('idempotencyKey', ''),
  proto: api.fieldError('constructor', 'x'),
};
out.messages = api.MESSAGES;
out.honeypot = api.HONEYPOT;
console.log(JSON.stringify(out));
"""

SHELL_LOCK_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const header = element('header'), menu = element('menu'), nav = element('nav');
  menu.attrs['aria-expanded'] = 'false';
  menu.focus = () => {};
  const root = element('html');
  const parts = { '[data-menu]': [menu], '[data-nav]': [nav], '.site-header': [header] };
  const doc = { documentElement: root, listeners: {}, addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const queries = {};
  const lenis = { stops: 0, starts: 0, stop() { this.stops++; }, start() { this.starts++; } };
  const { win } = makeWindow({ width: 390, height: 844, fine: false, reduce: false }, {
    scrollY: 0, location: { pathname: '/' },
    matchMedia: query => ({ matches: query === '(max-width: 1080px)', addEventListener(type, fn) { (queries[query] = queries[query] || []).push([type, fn]); } }),
  });
  vm.runInNewContext(source, { window: win, document: doc, getComputedStyle: () => ({ display: 'inline-flex' }) });
  if (env.lenis) win.__glass = Object.assign(win.__glass || {}, { lenis });  // glass.js creates it after site.js has run
  const steps = [];
  const state = () => ({ lock: root.classList.contains('menu-lock'), open: nav.classList.contains('open'), expanded: menu.attrs['aria-expanded'],
    stops: lenis.stops, starts: lenis.starts });
  const step = (name, act) => { act(); steps.push([name, state()]); };
  const click = () => (menu.listeners.click || []).forEach(fn => fn({ type: 'click' }));
  const layout = matches => (queries['(max-width: 1080px)'] || []).forEach(([type, fn]) => type === 'change' && fn({ matches }));
  step('start', () => {});
  step('open', click);
  step('close', click);
  step('open again', click);
  step('Escape', () => (doc.listeners.keydown || []).forEach(fn => fn({ key: 'Escape' })));
  step('open once more', click);
  step('still a phone layout', () => layout(true));
  step('widen to the desktop layout', () => layout(false));
  step('desktop layout with the menu closed', () => layout(false));
  return { steps, watchers: (queries['(max-width: 1080px)'] || []).map(([type]) => type) };
}
console.log(JSON.stringify({ lenis: run({ lenis: true }), plain: run({ lenis: false }) }));
"""

HOME_GROUP_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const below = name => { const el = element(name); el.getBoundingClientRect = () => ({ left: 0, top: 3000, width: 400, height: 300 }); return el; };
  const head = below('reelHead');
  const title = below('reelTitle'), desc = element('reelDesc');  // on a wide screen the paragraph can sit higher than its heading
  desc.getBoundingClientRect = () => ({ left: 600, top: 2900, width: 400, height: 300 });
  title.previousElementSibling = null; desc.previousElementSibling = title;
  title.closest = desc.closest = s => (s === '[data-rise-group]' ? head : null);
  const shown = element('shownHead'), shownTitle = element('shownTitle'), shownText = below('shownText');
  shownTitle.previousElementSibling = null; shownText.previousElementSibling = shownTitle;
  shownTitle.closest = shownText.closest = s => (s === '[data-rise-group]' ? shown : null);
  const lone = below('lone'); lone.closest = () => null; lone.previousElementSibling = element('before');
  const parts = { '[data-rise]': [title, desc, shownTitle, shownText, lone] };
  const root = element('html'); root.classList = classList(['js'].concat(env.reduce ? [] : ['motion']));
  const doc = { documentElement: root, querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const { win } = makeWindow(env, { requestAnimationFrame: () => 1, cancelAnimationFrame() {} });
  const stub = makeGsap(env); win.gsap = stub.gsap; win.ScrollTrigger = stub.ScrollTrigger;
  vm.runInNewContext(source, { window: win, document: doc });
  return stub.log.tweens.filter(t => t.vars && t.vars.scrollTrigger).map(t => ({ name: t.names[0], trigger: t.vars.scrollTrigger.trigger.name,
    start: t.vars.scrollTrigger.start, once: t.vars.scrollTrigger.once, delay: t.vars.delay || 0, from: t.from }));
}
console.log(JSON.stringify({ wide: run({ width: 1440, height: 900, fine: true, reduce: false }), phone: run({ width: 390, height: 844, fine: false, reduce: false }),
  reduced: run({ width: 1440, height: 900, fine: true, reduce: true }) }));
"""

UUID_V4 = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'


class EnquiryRobustnessScriptTests(unittest.TestCase):
    def node_json(self, script, path):
        out = subprocess.run(['node', '-e', script, str(path)], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    @classmethod
    def setUpClass(cls):
        if not shutil.which('node'):
            return
        run = lambda script, path: json.loads(subprocess.run(['node', '-e', script, str(path)], capture_output=True, text=True, check=True).stdout)
        cls.page = run(ENQUIRY_PAGE_SCRIPT, ENQUIRY)
        cls.keys = run(MAKE_KEY_SCRIPT, ENQUIRY)

    def test_button_is_enabled_only_after_the_submit_handler_is_attached(self):
        for label in ('withCrypto', 'noCrypto'):
            with self.subTest(label=label):
                r = self.page[label]
                self.assertIsNone(r['error'])
                self.assertIn('listen:submit', r['log'])
                self.assertEqual(r['log'].count('disabled=false'), 1)
                self.assertLess(r['log'].index('listen:submit'), r['log'].index('disabled=false'))
                self.assertNotIn('disabled=true', r['log'])
                self.assertFalse(r['disabled'])

    def test_make_key_never_throws_and_always_returns_a_uuid_v4(self):
        for name in ('none', 'nullCrypto', 'empty', 'throwingRandomUUID', 'badRandomUUID', 'throwingGetRandomValues',
                     'shortGetRandomValues', 'getRandomValuesOnly', 'full'):
            with self.subTest(crypto=name):
                r = self.keys[name]
                self.assertIsNone(r['error'])
                self.assertEqual(len(r['keys']), 50)
                for key in r['keys']:
                    self.assertRegex(key, UUID_V4)
                self.assertEqual(r['unique'], 50)

    def test_field_error_reuses_the_validation_rules_and_messages(self):
        f, m = self.keys['fieldError'], self.keys['messages']
        self.assertEqual(f['emailBad'], m['email'])
        self.assertEqual(f['emailGood'], '')
        self.assertEqual(f['nameEmpty'], m['name'])
        self.assertEqual(f['phoneEmpty'], '')  # optional
        self.assertEqual(f['phoneBad'], m['phone'])
        self.assertEqual(f['websiteBad'], m['website'])
        self.assertEqual(f['serviceBad'], m['service'])
        self.assertEqual(f['messageShort'], m['message'])
        self.assertEqual(f['unknown'], '')  # only the visible fields
        self.assertEqual(f['proto'], '')

    def test_a_field_is_rechecked_live_only_after_it_has_shown_an_error(self):
        r, m = self.page, self.keys['messages']
        empty = {'error': '', 'invalid': None}
        # Before any submit nothing is checked, not even a wrong email that was typed and left.
        self.assertEqual(r['beforeSubmit'], {name: empty for name in r['beforeSubmit']})
        for name in ('name', 'email', 'service', 'message'):
            self.assertEqual(r['afterSubmit'][name], {'error': m[name], 'invalid': 'true'})
        self.assertEqual(r['afterSubmit']['phone'], empty)
        self.assertEqual(r['nameFixed'], empty)
        self.assertEqual(r['emailStillWrong'], {'error': m['email'], 'invalid': 'true'})
        self.assertEqual(r['emailTypedRight'], empty)
        self.assertEqual(r['messageStillShort'], {'error': m['message'], 'invalid': 'true'})
        self.assertEqual(r['messageFixed'], empty)
        self.assertEqual(r['serviceFixed'], empty)
        self.assertEqual(r['phoneUntouched'], empty)
        self.assertEqual(r['nameClearedAfterFix'], empty)
        # Re-checks never move focus, never touch the button and never change the status line.
        self.assertEqual(r['sideEffects'], [])
        self.assertTrue(r['statusAfterSubmit'])
        self.assertEqual(r['statusAfterRechecks'], r['statusAfterSubmit'])

    def test_honeypot_is_sent_as_company_url(self):
        payload = self.page['payload']
        self.assertEqual(self.keys['honeypot'], 'hp_xq')
        self.assertEqual(payload['company_url'], 'https://spam.example')
        self.assertNotIn('hp_xq', payload)
        self.assertEqual(sorted(payload), sorted(['name', 'email', 'phone', 'business', 'website', 'service', 'message',
                                                  'company_url', 'idempotencyKey', 'elapsedMs']))
        self.assertRegex(payload['idempotencyKey'], UUID_V4)

    def test_open_mobile_menu_locks_the_page_and_every_way_out_releases_it(self):
        r = self.node_json(SHELL_LOCK_SCRIPT, SITE)
        for case in ('lenis', 'plain'):
            with self.subTest(case=case):
                steps = dict((name, s) for name, s in r[case]['steps'])
                self.assertEqual(r[case]['watchers'], ['change'])
                self.assertFalse(steps['start']['lock'])
                for name, locked in (('open', True), ('close', False), ('open again', True), ('Escape', False), ('open once more', True),
                                     ('still a phone layout', True), ('widen to the desktop layout', False),
                                     ('desktop layout with the menu closed', False)):
                    with self.subTest(step=name):
                        self.assertEqual(steps[name]['lock'], locked)
                        self.assertEqual(steps[name]['open'], locked)
                        self.assertEqual(steps[name]['expanded'], str(locked).lower())
        lenis = dict((name, s) for name, s in r['lenis']['steps'])
        # Lenis scrolls on its own, so it is stopped while the menu is open and started again on every way out.
        self.assertEqual((lenis['open']['stops'], lenis['open']['starts']), (1, 0))
        self.assertEqual((lenis['close']['stops'], lenis['close']['starts']), (1, 1))
        self.assertEqual((lenis['Escape']['stops'], lenis['Escape']['starts']), (2, 2))
        self.assertEqual((lenis['still a phone layout']['stops'], lenis['still a phone layout']['starts']), (3, 2))
        self.assertEqual(lenis['widen to the desktop layout']['starts'], 3)
        plain = dict((name, s) for name, s in r['plain']['steps'])
        self.assertEqual((plain['open']['stops'], plain['open']['starts']), (0, 0))

    def test_reel_heading_and_paragraph_rise_from_one_trigger_heading_first(self):
        r = self.node_json(HOME_GROUP_SCRIPT, HOME)
        for case in ('wide', 'phone'):
            with self.subTest(case=case):
                by = {t['name']: t for t in r[case]}
                # The pair on screen at load is never hidden; the group below the fold rises from its own trigger.
                self.assertEqual(sorted(by), ['lone', 'reelDesc', 'reelTitle'])
                title, desc = by['reelTitle'], by['reelDesc']
                self.assertEqual((title['trigger'], desc['trigger']), ('reelHead', 'reelHead'))
                self.assertEqual(title['start'], desc['start'])
                self.assertTrue(title['once'] and desc['once'])
                self.assertEqual(title['delay'], 0)
                self.assertGreater(desc['delay'], title['delay'])
                self.assertLessEqual(desc['delay'], 0.2)
                self.assertEqual(title['from'], desc['from'])
                # A heading outside any group keeps its own trigger and no delay.
                self.assertEqual((by['lone']['trigger'], by['lone']['delay']), ('lone', 0))
        self.assertEqual(r['reduced'], [])  # reduced motion: nothing is hidden or animated


# Task 48: Pause motion puts GSAP's ticker to sleep. A small live model of GSAP (it applies each tween's start state at once
# and its end state on progress(1), clears props, wakes the ticker on every new animation as GSAP does, and kills a tween
# with its ScrollTrigger as the vendored ScrollTrigger does) runs the real site.js, motion.js, scenes.js, home.js and
# glass.js. After a press of Pause motion nothing they hid may stay hidden, and the ticker must be left asleep.
LIVE_PAUSE_SCRIPT = HARNESS + r"""
const path = require('path');
const dir = path.dirname(process.argv[1]);
const read = name => fs.readFileSync(path.join(dir, name), 'utf8');
const SKIP = ['duration', 'stagger', 'ease', 'clearProps', 'scrollTrigger', 'delay', 'overwrite', 'immediateRender', 'onComplete',
  'onUpdate', 'paused', 'defaults', 'transformPerspective', 'transformOrigin'];
const TRANSFORM = ['x', 'y', 'xPercent', 'yPercent', 'scale', 'rotationX', 'rotationY', 'rotationZ', 'z'];
function liveGsap(env, resolve) {
  // Task 59: st models ScrollTrigger's own state: enabled (its requestAnimationFrame loop and listeners run) and every
  // disable/enable call with its arguments.
  const triggers = [], top = [], log = { order: [], sleeps: 0, wakes: 0, awake: true, refreshes: 0, listeners: {}, st: { enabled: true, calls: [], loops: 1 } };
  const wake = () => { if (!log.awake) { log.awake = true; log.wakes++; log.order.push('woken'); } };
  const list = t => [].concat(resolve(t)).filter(Boolean);
  const apply = (targets, vars) => list(targets).forEach((el, i) => {
    const gs = el.style ? (el.gs = el.gs || {}) : el;  // a plain state object (the comparison) takes the values itself
    Object.keys(vars).forEach(k => { if (!SKIP.includes(k)) gs[k] = typeof vars[k] === 'function' ? vars[k](i) : vars[k]; });
    if (vars.clearProps) vars.clearProps.split(',').forEach(p => (p === 'transform' ? TRANSFORM.forEach(k => delete gs[k]) : delete gs[p]));
  });
  const ends = vars => { const out = {}; Object.keys(vars).forEach(k => { if (!SKIP.includes(k)) out[k] = k === 'opacity' || k === 'scale' ? 1 : 0; }); out.clearProps = vars.clearProps; return out; };
  function trigger(vars, animation) {
    const t = { vars, animation, trigger: vars.trigger, dur: vars.scrub,
      kill() { const i = triggers.indexOf(t); if (i >= 0) triggers.splice(i, 1); if (animation) animation.kill(); },
      scrubDuration(d) { t.dur = d; } };
    if (animation) animation.scrollTrigger = t;
    triggers.push(t);
    return t;
  }
  function Anim(targets, from, to, child) {
    wake();
    Object.assign(this, { targets, end: to || {}, children: [], calls: [], done: false, killed: false });
    this.running = !this.end.scrollTrigger && !this.end.paused && !child;
    if (from && this.end.immediateRender !== false) apply(targets, from);
    if (this.end.scrollTrigger) trigger(this.end.scrollTrigger, this);
    if (!child) top.push(this);
  }
  Anim.prototype.progress = function (v) {
    if (v !== 1 || this.done || this.killed) return this;
    this.done = true; this.running = false;
    this.children.forEach(c => c.progress(1));
    this.calls.forEach(c => c());
    if (this.targets !== undefined) apply(this.targets, this.end);
    if (this.end.onUpdate) this.end.onUpdate();
    if (this.end.onComplete) this.end.onComplete();
    return this;
  };
  Anim.prototype.isActive = function () { return this.running && !this.done && !this.killed; };
  Anim.prototype.kill = function () { this.killed = true; this.running = false; return this; };
  Anim.prototype.play = function () { this.running = true; return this; };
  ['fromTo', 'from', 'to'].forEach(kind => {
    Anim.prototype[kind] = function (t, a, b) {
      const [from, to] = kind === 'fromTo' ? [a, b] : kind === 'from' ? [a, ends(a)] : [null, a];
      this.children.push(new Anim(t, from, to, true));
      return this;
    };
  });
  Anim.prototype.add = function (fn) { this.calls.push(fn); return this; };
  const gsap = {
    registerPlugin() {},
    matchMedia() { return { add(q, fn) { if (media(q, env)) fn(); }, revert() {} }; },
    timeline: vars => new Anim(undefined, null, vars || {}, false),
    fromTo: (t, a, b) => new Anim(t, a, b, false),
    from: (t, v) => new Anim(t, v, Object.assign(ends(v), { scrollTrigger: v.scrollTrigger }), false),
    to: (t, v) => new Anim(t, null, v, false),
    set(t, v) { wake(); apply(t, v); },
    killTweensOf(t) { const set = new Set(list(t)); const walk = a => { if (list(a.targets || []).some(x => set.has(x))) a.kill(); a.children.forEach(walk); }; top.forEach(walk); },
    quickTo: (t, prop) => value => { wake(); apply(t, { [prop]: value }); },
    globalTimeline: { getChildren: () => top.filter(a => !a.done && !a.killed) },
    ticker: { add(fn) { wake(); log.order.push('ticker.add'); return fn; }, remove() { log.order.push('ticker.remove'); },
      sleep() { log.awake = false; log.sleeps++; log.order.push('sleep'); }, wake() { log.order.push('wake'); wake(); } },
  };
  const ScrollTrigger = { getAll: () => triggers.slice(), batch: (targets, vars) => targets.map(el => trigger(Object.assign({}, vars, { trigger: el }), null)),
    create: v => trigger(v, null), update() {}, refresh() { log.refreshes++; log.order.push('refresh'); (log.listeners.refresh || []).forEach(fn => fn()); },
    addEventListener(type, fn) { (log.listeners[type] = log.listeners[type] || []).push(fn); },
    // As the vendored ScrollTrigger 3.13: disable ends its frame loop (and listeners); disable(false) keeps each animation
    // where it is. enable starts a new loop every time it is called (twice would leave two running) and makes delayed calls.
    disable(revert) { log.st.calls.push(['disable', revert === undefined ? 'default' : revert]); log.st.enabled = false; log.st.loops = 0; log.order.push('st.disable'); },
    enable() { log.st.calls.push(['enable']); log.st.enabled = true; log.st.loops++; log.order.push('st.enable'); wake(); } };
  return { gsap, ScrollTrigger, log, triggers, top };
}
const low = el => { el.getBoundingClientRect = () => ({ left: 0, top: 3000, width: 400, height: 300 }); return el; };
const closing = clip => Boolean(clip) && (clip.replace(/round [^)]*/, '').match(/-?[\d.]+/g) || []).some(n => Number(n) > 0);
const hiddenOf = els => els.filter(el => el.gs && ((el.gs.opacity !== undefined && el.gs.opacity < 1) || (el.gs.y || 0) !== 0 ||
  (el.gs.yPercent || 0) !== 0 || closing(el.gs.clipPath))).map(el => el.name);
function run(page, env) {
  const toggle = element('toggle'); toggle.hidden = true; toggle.attrs['aria-pressed'] = 'false';
  const root = element('html'); root.classList = classList(['js', 'motion', 'ph-wait']);
  let parts, tracked, scripts;
  if (page === 'inner') {
    const lines = many('line', 2), fades = many('fade', 2), media = many('frame', 1);
    const rises = [low(element('rise0')), low(element('rise1'))], reveals = [low(element('reveal0'))], devices = [low(element('devices0'))];
    const list = low(element('list')); list.children = many('item', 3);
    const cue = element('cue'); cue.classList = classList(['on']);
    const benchParts = { plinth: many('plinth', 1), lap: many('lap', 1), ph: many('ph', 1), ui: many('ui', 2) };
    const bench = low(element('bench', { '.bench-plinth': benchParts.plinth, '.d-lap': benchParts.lap, '.d-ph': benchParts.ph, '.ui': benchParts.ui, '[data-cue]': [cue] }));
    parts = { '[data-motion-toggle]': [toggle], '[data-ph]': [element('head', { 'h1 .ln > span': lines, '[data-ph-fade]': fades, '[data-ph-media]': media })],
      '[data-rise]': rises, '[data-reveal]': reveals, '[data-devices]': devices, '[data-stagger]': [list], '[data-bench]': [bench],
      '[data-parallax]': [element('para', { img: many('pimg', 1) })] };
    tracked = [...lines, ...fades, ...media, ...rises, ...reveals, ...devices, ...list.children, cue, ...Object.values(benchParts).flat()];
    scripts = ['site.js', 'motion.js', 'scenes.js', 'glass.js'];
    parts.cue = [cue];
  } else {
    const lines = many('line', 2), fades = many('fade', 2), cards = many('gcard', 2), deck = element('deck');
    const rises = [low(element('rise0')), low(element('rise1'))], teasers = [0, 1, 2].map(i => low(element('teaser' + i, { '.teaser-img': [element('shine' + i)] })));
    const panel = low(element('reelPanel')), frame = low(element('glassFrame')), band = low(element('bandPanel'));
    parts = { '[data-motion-toggle]': [toggle], '.hero-h .ln > span': lines, '[data-hero-fade]': fades, '.hero-cards': [deck], '.gcard': cards,
      '.c-book': [element('book')], '.slot-pick': [element('slot')], '.hero': [element('hero')], '.hero-copy': [element('heroCopy')], '.hero-cap': [element('heroCap')],
      '[data-rise]': rises, '.reel-frame': [low(element('reelFrame'))], '.reel-panel': [panel], '.teaser-card': teasers, '.compare-frame': [frame],
      '.band-panel': [band], '.band': [element('band')], '.gp-1': [element('phone1')], '.gp-2': [element('phone2')] };
    tracked = [...lines, ...fades, ...cards, deck, ...rises, ...teasers, panel, frame, band];
    scripts = ['site.js', 'home.js', 'glass.js'];
  }
  const doc = { documentElement: root, hidden: false, listeners: {}, addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const resolve = t => (typeof t === 'string' ? doc.querySelectorAll(t) : t);
  const live = liveGsap(env, resolve);
  let lenisMade = 0;
  class Lenis { constructor() { lenisMade++; } on() {} raf() {} destroy() { live.log.order.push('lenis.destroy'); } }
  const { win } = makeWindow(env, { gsap: live.gsap, ScrollTrigger: live.ScrollTrigger, Lenis, requestAnimationFrame: () => 1, cancelAnimationFrame() {},
    navigator: { connection: { saveData: Boolean(env.saveData) }, userAgentData: { brands: [{ brand: 'Firefox' }] } }, scrollY: 0, location: { pathname: '/' } });
  const errors = [];
  scripts.forEach(name => { try { vm.runInNewContext(read(name), { window: win, document: doc, getComputedStyle: () => ({ display: 'none' }), Event: class {} }); } catch (e) { errors.push(name + ': ' + e); } });
  const out = { errors, before: hiddenOf(tracked), awake: live.log.awake, sleeps: live.log.sleeps, lenisMade, lenis: Boolean(win.__glass.lenis),
    st: { enabled: live.log.st.enabled, loops: live.log.st.loops, calls: live.log.st.calls.slice() } };
  if (env.midReveal) {
    // a reveal whose line was just crossed: its trigger fired (and, being once, went) and its tween is under way
    const t = live.triggers.find(x => x.vars.once && !x.animation);
    if (t) { t.kill(); t.vars.onEnter([t.trigger]); }
    out.midReveal = Boolean(t);
  }
  live.log.order.length = 0;
  (toggle.listeners.click || []).forEach(fn => fn({ type: 'click' }));
  out.pressed = { paused: win.__glass.paused, hidden: hiddenOf(tracked), awake: live.log.awake, order: live.log.order.slice(), lenis: Boolean(win.__glass.lenis),
    once: live.triggers.filter(t => t.vars.once).length, scrubs: live.triggers.filter(t => t.vars.scrub).map(t => t.dur),
    running: live.top.filter(a => a.isActive()).length, cue: parts.cue ? parts.cue[0].classList.contains('on') : null,
    st: { enabled: live.log.st.enabled, loops: live.log.st.loops, calls: live.log.st.calls.slice() } };
  live.log.order.length = 0;
  (toggle.listeners.click || []).forEach(fn => fn({ type: 'click' }));
  out.released = { paused: win.__glass.paused, hidden: hiddenOf(tracked), awake: live.log.awake, order: live.log.order.slice(), refreshes: live.log.refreshes,
    lenis: Boolean(win.__glass.lenis), lenisMade, scrubs: live.triggers.filter(t => t.vars.scrub).map(t => t.dur),
    st: { enabled: live.log.st.enabled, loops: live.log.st.loops, calls: live.log.st.calls.slice() } };
  // a resize while paused again: ScrollTrigger refreshes (its delayed call woke the ticker); it settles and sleeps again
  (toggle.listeners.click || []).forEach(fn => fn({ type: 'click' }));
  live.gsap.set([], {});
  live.ScrollTrigger.refresh();
  out.refreshedWhilePaused = { awake: live.log.awake, st: { enabled: live.log.st.enabled, loops: live.log.st.loops } };
  return out;
}
const desktop = { width: 1440, height: 900, fine: true, reduce: false };
console.log(JSON.stringify({ inner: run('inner', desktop), innerMid: run('inner', { ...desktop, midReveal: true }), home: run('home', desktop),
  homePhone: run('home', { width: 390, height: 844, fine: false, reduce: false }), saveData: run('inner', { ...desktop, saveData: true }),
  reduced: run('inner', { ...desktop, reduce: true }) }));
"""


class PauseMotionSleepsGsapTests(unittest.TestCase):
    def test_pause_shows_everything_held_then_sleeps_the_ticker_and_release_wakes_it(self):
        out = subprocess.run(['node', '-e', LIVE_PAUSE_SCRIPT, str(GLASS)], capture_output=True, text=True, check=True)
        r = json.loads(out.stdout)
        for name in ('inner', 'innerMid', 'home', 'homePhone'):
            with self.subTest(case=name):
                case = r[name]
                self.assertEqual(case['errors'], [])
                self.assertTrue(case['before'])  # the model really hides what the scripts hold (openings and reveals)
                self.assertTrue(case['awake'])
                self.assertTrue(case['lenis'])
                pressed = case['pressed']
                self.assertTrue(pressed['paused'])
                self.assertEqual(pressed['hidden'], [])  # no opacity below 1, no vertical offset, no closing clip-path
                self.assertEqual(pressed['once'], 0)  # every one-time trigger is gone
                self.assertEqual(pressed['running'], 0)  # nothing is left part-way
                self.assertTrue(all(d == 0 for d in pressed['scrubs']), pressed['scrubs'])  # scrubs follow the scroll directly
                self.assertFalse(pressed['awake'])  # the ticker is left asleep
                self.assertFalse(pressed['lenis'])  # native scrolling
                order = pressed['order']
                self.assertEqual(order[-1], 'sleep')
                self.assertLess(order.index('lenis.destroy'), order.index('sleep'))
                # Task 59: ScrollTrigger is switched off before the ticker sleeps, so its own frame loop ends too (no
                # animation frame is requested while paused), and with revert false, so nothing on the page jumps.
                self.assertTrue(case['st']['enabled'])
                self.assertEqual(case['st']['calls'], [])
                self.assertEqual(pressed['st'], {'enabled': False, 'loops': 0, 'calls': [['disable', False]]})
                self.assertLess(order.index('st.disable'), order.index('sleep'))
                released = case['released']
                self.assertFalse(released['paused'])
                self.assertEqual(released['hidden'], [])  # what was shown stays shown
                self.assertTrue(released['awake'])
                self.assertEqual(released['order'][0], 'wake')
                self.assertEqual(released['refreshes'], 1)
                # Task 59: released, ScrollTrigger is back (one loop, not two) after the ticker wakes, then re-measures.
                self.assertEqual(released['st'], {'enabled': True, 'loops': 1, 'calls': [['disable', False], ['enable']]})
                self.assertLess(released['order'].index('wake'), released['order'].index('st.enable'))
                self.assertLess(released['order'].index('st.enable'), released['order'].index('refresh'))
                self.assertTrue(released['lenis'])
                self.assertEqual(released['lenisMade'], 2)
                self.assertTrue(all(d not in (0, None) for d in released['scrubs']), released['scrubs'])  # easing again
                self.assertFalse(case['refreshedWhilePaused']['awake'])
                self.assertEqual(case['refreshedWhilePaused']['st'], {'enabled': False, 'loops': 0})  # paused again: off again
        self.assertTrue(r['innerMid']['midReveal'])
        self.assertTrue(r['inner']['pressed']['cue'])  # scenes finish in their shipped state (the card's cue class is back)
        self.assertTrue(r['inner']['released']['scrubs'])
        # Save-Data: Pause motion starts pressed, so everything is shown and the ticker sleeps from the start, with no Lenis.
        save = r['saveData']
        self.assertEqual(save['errors'], [])
        self.assertEqual(save['before'], [])
        self.assertFalse(save['awake'])
        self.assertFalse(save['lenis'])
        # Task 59: and ScrollTrigger is off from the start (never enabled again until a press releases it).
        self.assertEqual(save['st'], {'enabled': False, 'loops': 0, 'calls': [['disable', False]]})
        # Reduced motion: nothing is held, the ticker sleeps at once and nothing is added to it.
        reduced = r['reduced']
        self.assertEqual(reduced['errors'], [])
        self.assertEqual(reduced['before'], [])
        self.assertFalse(reduced['awake'])
        self.assertEqual(reduced['sleeps'], 1)
        self.assertEqual(reduced['lenisMade'], 0)
        # Task 59: reduced motion switches ScrollTrigger off at once (its frame loop used to run all the time) and never
        # back on, whatever the Pause motion button does (glass.js joins no pause listener under reduced motion).
        self.assertEqual(reduced['st'], {'enabled': False, 'loops': 0, 'calls': [['disable', False]]})
        self.assertEqual(reduced['released']['st'], reduced['st'])
        self.assertEqual(reduced['refreshedWhilePaused']['st'], {'enabled': False, 'loops': 0})



# Task 59 (owner-mandated performance follow-up): reel.js gives every video whose still waits in data-poster its poster only
# when it comes near the screen, including a "wide" loop that phones never play but still show (Work's laptop screens),
# and on phones the showreel's phone still replaces its wide one before either is fetched.
LAZY_POSTER_SCRIPT = HARNESS + r"""
const source = fs.readFileSync(process.argv[1], 'utf8');
function run(env) {
  const observers = [];
  class FakeObserver { constructor(cb, options) { this.cb = cb; this.options = options || {}; this.targets = []; this.off = false; observers.push(this); }
    observe(t) { this.targets.push(t); } disconnect() { this.off = true; } }
  const video = (name, data, src) => {
    const s = element('source'); if (src) s.attrs.src = src; else s.dataset.src = '/assets/video/' + name + '.mp4';
    const v = element(name, { source: [s] });
    Object.assign(v, { paused: true, loads: 0, load() { v.loads++; }, play() { v.paused = false; return Promise.resolve(); }, pause() { v.paused = true; } });
    Object.assign(v.dataset, data);
    return v;
  };
  // As pages/index.html and pages/work.html ship them: stills in data-poster, the showreel's file in src (preload="none").
  const reelVideo = video('reel', { poster: '/assets/glass/glass-reel-poster.jpg', narrowSrc: '/assets/glass/glass-reel-vertical-720.mp4',
    narrowPoster: '/assets/glass/glass-reel-vertical-poster.jpg' }, '/assets/glass/glass-reel-1600.mp4');
  const laptop = video('laptop', { loop: 'wide', poster: '/assets/video/loop-hb-desktop-poster-800.jpg' });
  const phone = video('phone', { loop: '', poster: '/assets/video/loop-hb-phone-poster-390.jpg' });
  const toggle = element('toggle'); toggle.textContent = 'Play showreel';
  const reel = element('reel', { video: [reelVideo], '[data-reel-toggle]': [toggle] });
  const all = [reelVideo, laptop, phone];
  const parts = { '[data-reel]': [reel], 'video[data-loop]': [laptop, phone], 'video[data-poster]': all };
  const doc = { documentElement: element('html'), readyState: 'complete', hidden: false, listeners: {},
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    querySelector: s => (parts[s] || [])[0] || null, querySelectorAll: s => parts[s] || [] };
  const extra = { navigator: { connection: {} }, requestAnimationFrame: () => 1, cancelAnimationFrame() {} };
  if (!env.noObserver) extra.IntersectionObserver = FakeObserver;
  const { win } = makeWindow(env, extra);
  vm.runInNewContext(source, { window: win, document: doc, setImmediate });
  const posters = () => all.map(v => v.getAttribute('poster'));
  const near = observers.filter(o => o.options.rootMargin);
  const fire = on => near.forEach(o => o.targets.forEach(t => o.cb([{ isIntersecting: on, target: t }])));
  const out = { start: posters(), nearObservers: near.map(o => [o.targets.map(t => t.name), o.options.rootMargin]) };
  fire(false); out.far = posters();
  fire(true); out.near = posters();
  out.disconnected = near.every(o => o.off);
  out.reelSource = reelVideo.parts.source[0].attrs.src;
  out.loopSources = [laptop, phone].map(v => v.parts.source[0].attrs.src || null);
  return out;
}
console.log(JSON.stringify({ phone: run({ width: 390, height: 844, fine: false, reduce: false }),
  desktop: run({ width: 1440, height: 900, fine: true, reduce: false }),
  noObserver: run({ width: 1440, height: 900, fine: true, reduce: false, noObserver: true }) }));
"""


class LazyPosterScriptTests(unittest.TestCase):
    def test_stills_wait_until_near_the_screen_on_every_width_and_phones_fetch_only_their_own(self):
        out = subprocess.run(['node', '-e', LAZY_POSTER_SCRIPT, str(REEL)], capture_output=True, text=True, check=True)
        r = json.loads(out.stdout)
        wide = ['/assets/glass/glass-reel-poster.jpg', '/assets/video/loop-hb-desktop-poster-800.jpg', '/assets/video/loop-hb-phone-poster-390.jpg']
        phone = ['/assets/glass/glass-reel-vertical-poster.jpg'] + wide[1:]
        for name, expected in (('phone', phone), ('desktop', wide)):
            with self.subTest(width=name):
                case = r[name]
                self.assertEqual(case['start'], [None, None, None])  # nothing is fetched with the first load
                self.assertEqual(case['far'], [None, None, None])
                # Near the screen (half a screen ahead) each gets its still, including the laptop loop phones never play.
                self.assertEqual(case['near'], expected)
                self.assertEqual(case['nearObservers'], [[['reel'], '50% 0px'], [['laptop'], '50% 0px'], [['phone'], '50% 0px']])
                self.assertTrue(case['disconnected'])
                self.assertEqual(case['loopSources'], [None, None])  # no loop file before it plays
        self.assertEqual(r['phone']['reelSource'], '/assets/glass/glass-reel-vertical-720.mp4')
        self.assertEqual(r['desktop']['reelSource'], '/assets/glass/glass-reel-1600.mp4')
        # Without IntersectionObserver every still is set at once (nothing stays blank).
        self.assertEqual(r['noObserver']['start'], wide)


if __name__ == '__main__':
    unittest.main()
