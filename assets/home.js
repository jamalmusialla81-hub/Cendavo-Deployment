// Homepage (Daylight, Task 33): the before/after comparison and its one demonstration sweep, the hero opening and its
// one-time stage choreography, two transform-only hero scroll layers and the showreel frame's entrance. Without it (or
// GSAP, or with reduced motion) everything shows in its final state and the comparison sits at 50%. Video playback and
// the Pause motion button belong to reel.js (loaded first); a press of Pause motion here jumps the choreography to its end.
(() => {
  const doc = document;
  const root = doc.documentElement;
  const $ = (selector, scope) => (scope || doc).querySelector(selector);
  const $$ = (selector, scope) => Array.from((scope || doc).querySelectorAll(selector));
  const still = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const MOTION = '(prefers-reduced-motion: no-preference)';
  // The two Daylight curves, the same as cubic-bezier() in CSS (x solved by bisection): entrances, and changes of state.
  const bezier = (x1, y1, x2, y2) => {
    const at = (t, a, b) => 3 * a * t * (1 - t) * (1 - t) + 3 * b * t * t * (1 - t) + t * t * t;
    return x => {
      if (x <= 0 || x >= 1) return x <= 0 ? 0 : 1;
      let low = 0, high = 1, t = x;
      for (let i = 0; i < 24; i++) {
        if (at(t, x1, x2) < x) low = t; else high = t;
        t = (low + high) / 2;
      }
      return at(t, y1, y2);
    };
  };
  const OUT = bezier(0.2, 0.8, 0.2, 1);
  const IO = bezier(0.7, 0, 0.2, 1);
  // Demo sweep, once: 50 -> 82 -> 18 -> 50 over 1.5 s. Any press, key, touch or use of the controls stops it.
  const SWEEP = [[82, 0.4], [18, 0.7], [50, 0.4]];
  const SWEEP_STOP = ['pointerdown', 'keydown', 'touchstart'];

  // Before/after comparison: a labelled range input plus Before/After buttons.
  const figure = $('[data-compare]');
  const controls = figure?.querySelector('[data-compare-controls]');
  const range = controls?.querySelector('input[type="range"]');
  let update = null;
  let sweep = null;
  let swept = false; // once per page load, and never after the visitor has used the comparison
  const stopSweep = () => {
    swept = true;
    SWEEP_STOP.forEach(type => window.removeEventListener(type, stopSweep));
    if (!sweep) return;
    sweep.kill();
    sweep = null;
    figure.style.setProperty('--pos', (Number(range.value) || 0) + '%'); // back to the range value; no attribute changes
  };
  if (range) {
    const buttons = controls.querySelectorAll('[data-compare-set]');
    const state = { v: Number(range.value) || 50 };
    let tween = null;
    update = () => {
      const value = Math.min(100, Math.max(0, Number(range.value) || 0));
      figure.style.setProperty('--pos', value + '%');
      range.setAttribute('aria-valuetext', value === 0 ? 'Before only' : value === 100 ? 'After only' : value + ' of 100 showing the redesign');
      buttons.forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.compareSet) === value)));
    };
    range.addEventListener('input', () => {
      stopSweep();
      tween?.kill();
      state.v = Number(range.value);
      update();
    });
    buttons.forEach(button => button.addEventListener('click', () => {
      const target = Number(button.dataset.compareSet);
      stopSweep();
      tween?.kill();
      if (window.gsap && !still()) {
        // Glide the divider to the chosen side; the range value follows so it stays the source of truth.
        tween = window.gsap.to(state, { v: target, duration: 0.4, ease: IO, onUpdate: () => { range.value = Math.round(state.v); update(); } });
      } else {
        state.v = target;
        range.value = target;
        update();
      }
    }));
    controls.hidden = false;
    update();
  }

  // GSAP is optional; motion stays inside the reduced-motion guard and animates transform, opacity and clip-path (plus the
  // SVG ring's dash offset) only.
  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;
  const release = () => root.classList.remove('ph-wait');
  if (!gsap || !ScrollTrigger) { release(); return; }
  gsap.registerPlugin(ScrollTrigger);
  const mm = gsap.matchMedia();
  const motionToggle = $('[data-motion-toggle]');
  const held = () => motionToggle?.getAttribute('aria-pressed') === 'true';

  // Hero, once (about 4.7 s): the headline lines rise through their masks, the copy follows, the stage is laid down, the
  // interface cards arrive one by one, the score is drawn, Desktop gets checked and the cursor picks 10:30 and books it.
  // fromTo takes over the .ph-wait start states (y: 0, as GSAP reads the CSS percentage as pixels). Every piece ends in
  // the same state the static page shows, which end() also sets directly.
  const heroTimeline = () => {
    const tl = gsap.timeline({ paused: true, defaults: { ease: OUT } });
    const lines = $$('.hero-h .ln > span');
    const fades = $$('[data-hero-fade]');
    const stage = $('.stage');
    const book = $('.frag-book'), slot = $('.slot-pick'), cursor = $('.cursor'), dev = $('.frag-dev'), ring = $('.ring-fg'), count = $('[data-count]');
    const end = () => {
      tl.progress(1);
      dev?.classList.add('is-desktop');
      slot?.classList.add('on');
      book?.classList.add('booked');
      if (count) count.textContent = '100';
    };
    if (lines.length) tl.fromTo(lines, { yPercent: 108, y: 0 }, { yPercent: 0, y: 0, duration: 1, stagger: 0.08, clearProps: 'transform' }, 0);
    if (fades.length) tl.fromTo(fades, { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: 0.7, stagger: 0.08, clearProps: 'opacity,transform' }, 0.4);
    if (!stage) return { tl, end };
    tl.fromTo(stage, { opacity: 0 }, { opacity: 1, duration: 0.4, clearProps: 'opacity' }, 0.2)
      .fromTo($$('.rig-plinth'), { clipPath: 'inset(0% 0% 0% 100% round 3.2em)' }, { clipPath: 'inset(0% 0% 0% 0% round 3.2em)', duration: 1, ease: IO, clearProps: 'clipPath' }, 0.2)
      .fromTo($$('.hd-laptop, .hd-phone'), { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: 1, stagger: 0.08, clearProps: 'opacity,transform' }, 0.4)
      .fromTo($$('.frag'), { opacity: 0, scale: 0.96, y: 8 }, { opacity: 1, scale: 1, y: 0, duration: 0.4, stagger: 0.08, clearProps: 'opacity,transform' }, 1.2);
    if (ring && count) {
      const score = { n: 0 };
      tl.fromTo(ring, { strokeDashoffset: 100 }, { strokeDashoffset: 0, duration: 1, ease: IO }, 1.3)
        .fromTo(score, { n: 0 }, { n: 100, duration: 1, ease: IO, onUpdate: () => { count.textContent = String(Math.round(score.n)); } }, 1.3);
    }
    if (dev) {
      dev.classList.remove('is-desktop');
      tl.add(() => dev.classList.add('is-desktop'), 2.2);
    }
    if (book && slot && cursor) {
      book.classList.remove('booked');
      slot.classList.remove('on');
      tl.fromTo(cursor, { xPercent: 160, yPercent: 220, opacity: 0 }, { opacity: 1, duration: 0.2 }, 2.4)
        .to(cursor, { xPercent: -230, yPercent: -150, duration: 1, ease: IO }, 2.6)
        .add(() => slot.classList.add('on'), 3.6)
        .to(cursor, { xPercent: 0, yPercent: 0, duration: 0.7, ease: IO, clearProps: 'transform,opacity' }, 3.8)
        .add(() => book.classList.add('booked'), 4.5);
    }
    return { tl, end };
  };

  // Two depth layers drift up as the hero scrolls away (the only scrubbed motion on the page; transform only).
  const layers = () => {
    const hero = $('.hero');
    [['.rig-devices', -16], ['.rig-cards', -40]].forEach(([selector, y]) => {
      const layer = $(selector);
      if (hero && layer) gsap.to(layer, { y, ease: 'none', scrollTrigger: { trigger: hero, start: 'top top', end: 'bottom top', scrub: 0.4 } });
    });
  };

  // Only the visual --pos moves: the range value, its aria-valuetext and the buttons never change (nothing is announced).
  const demoSweep = () => {
    if (!update) return;
    const at = { p: Number(range.value) || 50 };
    const draw = () => figure.style.setProperty('--pos', at.p + '%');
    ScrollTrigger.create({ trigger: figure, start: 'top 65%', once: true, onEnter: () => {
      if (swept) return;
      swept = true;
      sweep = gsap.timeline({ onComplete: stopSweep });
      SWEEP.forEach(([p, duration]) => sweep.to(at, { p, duration, ease: IO, onUpdate: draw }));
      SWEEP_STOP.forEach(type => window.addEventListener(type, stopSweep, { passive: true }));
    } });
  };

  // Showreel, if below the fold: the frame opens from a slightly inset window once, then the caption and button rise.
  const reelEntrance = () => {
    const reel = doc.querySelector('[data-reel]');
    const frame = reel?.querySelector('.reel-frame');
    if (!frame || reel.getBoundingClientRect().top < window.innerHeight) return;
    const once = { trigger: reel, start: 'top 85%', once: true };
    gsap.fromTo(frame, { clipPath: 'inset(4% 4% 4% 4% round 18px)' }, { clipPath: 'inset(0% 0% 0% 0% round 18px)', duration: 1, ease: IO, clearProps: 'clipPath', scrollTrigger: once });
    gsap.fromTo($$('.reel-cap, [data-reel-toggle]', reel), { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.7, stagger: 0.08, clearProps: 'opacity,transform', scrollTrigger: { ...once } });
  };

  // The hero opens only while CSS holds it; after the 2.5 s failsafe it stays shown as it is.
  mm.add(MOTION, () => {
    let hero = null;
    if (root.classList.contains('ph-wait')) {
      hero = heroTimeline();
      if (held()) hero.end(); // Save-Data: the Pause motion button starts pressed
      else hero.tl.play(0);
    }
    release();
    layers();
    reelEntrance();
    demoSweep();
    const onHold = () => { if (hero && held()) hero.end(); };
    motionToggle?.addEventListener('click', onHold);
    return () => {
      hero?.end();
      stopSweep();
      motionToggle?.removeEventListener('click', onHold);
    };
  });
  release();
})();
