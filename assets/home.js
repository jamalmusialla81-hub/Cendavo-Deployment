// Homepage (Liquid Glass, Task 37, over the Daylight content): the before/after comparison and its one demonstration sweep,
// the hero opening (headline lines, copy, the glass cards arriving from depth and the booking), the hero's scroll exit
// (it also feeds the WebGL scene's progress), heading reveals, the showreel lens, the marquee, the concept cards fanning in
// with a small tilt and light sweep, the glass browser frame swinging in, and the closing panel and phones. Without it
// (or GSAP, or with reduced motion) everything shows in its final state and the comparison sits at 50%. Video playback
// and the Pause motion button belong to reel.js (loaded first); a press of Pause motion here ends the opening at once and
// stops the marquee.
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
  // What most reveals hand back to CSS when they end.
  const OT = 'opacity,transform';
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
  // once per page load, and never after the visitor has used the comparison
  let swept = false;
  const stopSweep = () => {
    swept = true;
    SWEEP_STOP.forEach(type => window.removeEventListener(type, stopSweep));
    if (!sweep) return;
    sweep.kill();
    sweep = null;
    // back to the range value; no attribute changes
    figure.style.setProperty('--pos', (Number(range.value) || 0) + '%');
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
      if (window.gsap && !still() && !window.__glass?.paused) {
        // Glide the divider to the chosen side; the range value follows so it stays the source of truth.
        tween = window.gsap.to(state, { v: target, duration: 0.4, ease: IO, onUpdate: () => { range.value = Math.round(state.v); update(); } });
      } else {
        state.v = target;
        range.value = target;
        update();
      }
    }));
    // Task 46: the picture is draggable too. A mouse or pen press, a drag, or a touch that ends without scrolling sets the
    // range and fires its input event, so the range stays the one source of truth and the accessible control. Touch
    // moves only once the browser has ruled out a vertical scroll (touch-action: pan-y); a scroll ends in pointercancel.
    const stage = figure.querySelector('.compare-stage');
    if (stage) {
      let id = null, moved = false;
      const seek = e => {
        const box = stage.getBoundingClientRect();
        if (!box.width) return;
        range.value = Math.round(Math.min(100, Math.max(0, (e.clientX - box.left) / box.width * 100)));
        range.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const letGo = e => {
        if (id !== e.pointerId) return;
        id = null;
        if (stage.hasPointerCapture?.(e.pointerId)) stage.releasePointerCapture(e.pointerId);
      };
      stage.addEventListener('pointerdown', e => {
        if (e.button > 0) return;
        id = e.pointerId;
        moved = false;
        stage.setPointerCapture?.(e.pointerId);
        stopSweep();
        if (e.pointerType !== 'touch') seek(e);
      });
      stage.addEventListener('pointermove', e => {
        if (id !== e.pointerId) return;
        moved = true;
        seek(e);
      });
      stage.addEventListener('pointerup', e => {
        if (id === e.pointerId && e.pointerType === 'touch' && !moved) seek(e);
        letGo(e);
      });
      stage.addEventListener('pointercancel', letGo);
    }
    controls.hidden = false;
    update();
  }

  // GSAP is optional; motion stays inside the reduced-motion guard and animates transform, opacity and clip-path (plus the
  // marquee mask's position, a CSS variable on one short strip).
  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;
  const release = () => root.classList.remove('ph-wait');
  if (!gsap || !ScrollTrigger) { release(); return; }
  gsap.registerPlugin(ScrollTrigger);
  const mm = gsap.matchMedia();
  const motionToggle = $('[data-motion-toggle]');
  const held = () => motionToggle?.getAttribute('aria-pressed') === 'true';
  const glass = window.__glass = window.__glass || { paused: false, heroP: 0, pointer: { x: 0, y: 0 } };
  // Every scroll-linked tween shares this one definition (smoothing in seconds); none pins anything.
  const SCRUB = { scrub: 0.6 };
  // concept cards: never more than 6 degrees, fine pointers only
  const MAX_TILT = 6;
  const tiltOf = value => Math.max(-MAX_TILT, Math.min(MAX_TILT, value));
  // Scroll reveals only below the fold: hiding what is already on screen would make it blink.
  const below = el => el.getBoundingClientRect().top >= window.innerHeight;
  const once = (trigger, start) => ({ trigger, start: start || 'top 85%', once: true });

  // Hero, once (about 3.5 s): the headline lines rise through their masks, the copy follows, the two glass cards arrive
  // from depth, then 10:30 is picked and booked. fromTo takes over the .ph-wait start states (y: 0, as GSAP reads the CSS
  // percentage as pixels). Every piece ends in the state the static page shows, which end() also sets directly.
  const heroTimeline = () => {
    const tl = gsap.timeline({ paused: true, defaults: { ease: OUT } });
    const lines = $$('.hero-h .ln > span');
    const fades = $$('[data-hero-fade]');
    const cards = $$('.gcard');
    const book = $('.c-book'), slot = $('.slot-pick');
    const end = () => {
      tl.progress(1);
      slot?.classList.add('on');
      book?.classList.add('booked');
    };
    if (lines.length) tl.fromTo(lines, { yPercent: 108, y: 0 }, { yPercent: 0, y: 0, duration: 1, stagger: 0.08, clearProps: 'transform' }, 0);
    // Task 48: the copy and buttons only rise (never opacity 0), so they paint with the headline (LCP).
    if (fades.length) tl.fromTo(fades, { y: 18 }, { y: 0, duration: 0.7, stagger: 0.08, clearProps: 'transform' }, 0.4);
    const deck = $('.hero-cards');
    if (deck) tl.fromTo(deck, { opacity: 0 }, { opacity: 1, duration: 0.2, clearProps: 'opacity' }, 0.6);
    if (cards.length) {
      tl.fromTo(cards, { opacity: 0, z: -420, rotationX: 18, rotationY: -14, transformPerspective: 900 },
        { opacity: 1, z: 0, rotationX: 0, rotationY: 0, duration: 1.4, stagger: 0.14, ease: OUT, clearProps: OT }, 0.6);
    }
    if (book && slot) {
      book.classList.remove('booked');
      slot.classList.remove('on');
      tl.add(() => slot.classList.add('on'), 2.6).add(() => book.classList.add('booked'), 3.3);
    }
    return { tl, end };
  };

  // The hero's scroll exit (wide screens; the stage is pinned by CSS sticky): the copy rises and fades, the cards fly past
  // in depth, and the scene's progress (window.__glass.heroP) tilts the 3D logo away.
  const heroExit = () => {
    const hero = $('.hero');
    if (!hero) return;
    const tl = gsap.timeline({ scrollTrigger: { trigger: hero, start: 'top top', end: 'bottom bottom', ...SCRUB, onUpdate: self => { glass.heroP = self.progress; } } });
    tl.to('.hero-copy', { yPercent: -14, opacity: 0, ease: 'none', duration: 0.42 }, 0)
      .to('.hero-cap', { opacity: 0, ease: 'none', duration: 0.4 }, 0);
    // fromTo with explicit start values: the opening may still hold the cards at opacity 0 when this is created.
    $$('.gcard').forEach((card, i) => tl.fromTo(card, { z: 0, rotationX: 0, rotationY: 0, opacity: 1 },
      { z: 260, rotationX: -10, rotationY: i % 2 ? 12 : -12, opacity: 0, ease: 'none', duration: 0.45, transformPerspective: 900, immediateRender: false }, 0.04 * i));
  };

  // Section headings rise through a mask, once, as they come into view. Task 47: inside a [data-rise-group] (a heading
  // beside its paragraph) both share the group's trigger and the later sibling follows 0.12 s after the first, so the
  // paragraph (which can sit higher on a wide screen) never rises before its heading.
  const headings = () => $$('[data-rise]').forEach(el => {
    const g = el.closest?.('[data-rise-group]') || el;
    if (below(g)) gsap.fromTo(el, { clipPath: 'inset(0% 0% 100% 0%)', yPercent: 30 }, { clipPath: 'inset(0% 0% -12% 0%)', yPercent: 0, duration: 1, delay: g !== el && el.previousElementSibling ? .12 : 0, ease: OUT, clearProps: 'clipPath,transform', scrollTrigger: once(g) });
  });

  // Showreel: a rounded glass lens that opens to the full, square-edged frame (Task 44: no box) and tilts flat as it
  // scrolls in; the chapters below it follow once.
  const reelLens = () => {
    const frame = $('.reel-frame');
    if (!frame) return;
    gsap.fromTo(frame, { clipPath: 'inset(9% 16% 9% 16% round 48px)', rotationX: 10, scale: 0.97, transformPerspective: 1600 },
      { clipPath: 'inset(0% 0% 0% 0% round 0px)', rotationX: 0, scale: 1, ease: 'none', scrollTrigger: { trigger: frame, start: 'top 92%', end: 'top 25%', ...SCRUB } });
    const panel = $('.reel-panel');
    if (panel && below(panel)) gsap.fromTo(panel, { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 1, ease: OUT, clearProps: OT, scrollTrigger: once(panel) });
  };

  // Marquee: the photo strip (each pill rides on its tile) and the type's masks glide continuously (a transform, and one
  // --mqx offset shared by the white type and its rim), faster for a moment while the page scrolls quickly; only while
  // the strip is on screen and Pause motion is off.
  const marquee = () => {
    const strip = $('.marq'), type = $('.mq-word');
    if (!strip) return () => {};
    const tracks = $$('[data-marquee]').map(el => ({ el, dir: Number(el.dataset.marquee) || 1, x: 0 }));
    let inView = false, boost = 0, frame = 0, last = 0, mx = 0;
    const tick = now => {
      const dt = Math.min(0.05, (now - (last || now)) / 1000);
      last = now;
      boost *= 0.94;
      const speed = 38 * (1 + boost) * dt;
      tracks.forEach(t => {
        const half = t.el.scrollWidth / 2 || 1;
        t.x = (t.x - speed * t.dir) % half;
        if (t.x > 0) t.x -= half;
        t.el.style.transform = 'translate3d(' + t.x.toFixed(1) + 'px,0,0)';
      });
      if (type) {
        mx = (mx - speed * 1.4) % (type.offsetHeight * 15.85 || 1);
        type.style.setProperty('--mqx', mx.toFixed(1) + 'px');
      }
      frame = window.requestAnimationFrame(tick);
    };
    const run = () => {
      const on = inView && !glass.paused && !held();
      if (on && !frame) { last = 0; frame = window.requestAnimationFrame(tick); }
      else if (!on && frame) { window.cancelAnimationFrame(frame); frame = 0; }
    };
    ScrollTrigger.create({ trigger: strip, start: 'top bottom', end: 'bottom top', onToggle: self => { inView = self.isActive; run(); },
      onUpdate: self => { boost = Math.min(4, Math.abs(self.getVelocity()) / 500); } });
    return run;
  };

  // Concept cards fan in from depth once, each on its own angle (wide screens), and settle flat. Task 60: the trigger is
  // the grid (.teaser, the card's parent), which never moves; a card's own box starts 160px lower and pushed back, so on
  // short screens it met its line about a screen late and left the space under the intro empty.
  const cardsIn = wide => $$('.teaser-card').filter(below).forEach((card, i) => {
    const fan = [{ x: -160, rY: 32, rZ: -4 }, { x: 220, rY: -38, rZ: 5 }, { x: 260, rY: -30, rZ: -3 }][i % 3];
    gsap.fromTo(card, { opacity: 0, y: 160, x: wide ? fan.x : 0, z: -500, rotationX: 22, rotationY: wide ? fan.rY : 0, rotationZ: wide ? fan.rZ : 0, transformPerspective: 1400, transformOrigin: '50% 100%' },
      { opacity: 1, y: 0, x: 0, z: 0, rotationX: 0, rotationY: 0, rotationZ: 0, duration: 1.6, delay: (i % 3) * 0.12, ease: OUT, clearProps: OT, scrollTrigger: once(card.parentNode || card) });
  });

  // Fine pointers: a small tilt toward the pointer and a light sweep across the photo (keyboard focus gets neither).
  const tilt = () => $$('.teaser-card').forEach(card => {
    const rx = gsap.quickTo(card, 'rotationX', { duration: 0.6, ease: OUT }), ry = gsap.quickTo(card, 'rotationY', { duration: 0.6, ease: OUT });
    const shine = $('.teaser-img', card);
    // Task 48: no new tween (it would wake GSAP's ticker) while Pause motion is pressed.
    card.addEventListener('pointermove', e => {
      if (glass.paused) return;
      const r = card.getBoundingClientRect(), nx = (e.clientX - r.left) / r.width - 0.5, ny = (e.clientY - r.top) / r.height - 0.5;
      gsap.set(card, { transformPerspective: 1200 });
      rx(tiltOf(-ny * 8)); ry(tiltOf(nx * 10));
      shine?.style.setProperty('--sweep', Math.round(nx * 120) + '%');
    });
    card.addEventListener('pointerleave', () => { if (!glass.paused) { rx(0); ry(0); } shine?.style.setProperty('--sweep', '-120%'); });
  });

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

  // The glass browser frame swings in once before the sweep; the closing panel lifts out of depth once.
  const arrivals = () => {
    const frame = $('.compare-frame');
    if (frame && below(frame)) gsap.fromTo(frame, { rotationY: -18, rotationX: 6, y: 60, opacity: 0, transformPerspective: 1600 }, { rotationY: 0, rotationX: 0, y: 0, opacity: 1, duration: 1.4, ease: OUT, clearProps: OT, scrollTrigger: once(frame) });
    const panel = $('.band-panel');
    if (panel && below(panel)) gsap.fromTo(panel, { y: 90, opacity: 0, scale: 0.94, rotationX: 10, transformPerspective: 1400 }, { y: 0, opacity: 1, scale: 1, rotationX: 0, duration: 1.4, ease: OUT, clearProps: OT, scrollTrigger: once(panel) });
  };

  // Wide screens: the two glass phones fly in from depth as the closing band scrolls up (scrubbed, transform only).
  const phones = () => {
    const band = $('.band');
    if (!band || !$('.gp-1')) return;
    gsap.timeline({ scrollTrigger: { trigger: band, start: 'top bottom', end: 'center center', ...SCRUB } })
      .fromTo('.gp-1', { x: 420, y: 300, z: -900, rotationY: -60, rotationX: 24, rotationZ: 10, transformPerspective: 1400 }, { x: 0, y: 0, z: 0, rotationY: -16, rotationX: 4, rotationZ: 0, ease: 'none', duration: 1 }, 0)
      .fromTo('.gp-2', { x: 360, y: -340, z: -1100, rotationY: -70, rotationX: -26, rotationZ: -8, transformPerspective: 1400 }, { x: 0, y: 0, z: 60, rotationY: -22, rotationX: -2, rotationZ: 0, ease: 'none', duration: 1 }, 0.05);
  };

  mm.add(MOTION, () => {
    let hero = null;
    if (root.classList.contains('ph-wait')) {
      hero = heroTimeline();
      // Save-Data: the Pause motion button starts paused
      if (held()) hero.end();
      else hero.tl.play(0);
    }
    release();
    headings();
    reelLens();
    demoSweep();
    arrivals();
    const runMarquee = marquee();
    const onHold = () => { if (hero && held()) hero.end(); runMarquee(); };
    motionToggle?.addEventListener('click', onHold);
    return () => {
      hero?.end();
      stopSweep();
      motionToggle?.removeEventListener('click', onHold);
    };
  });
  mm.add(MOTION + ' and (min-width: 761px)', () => { heroExit(); cardsIn(true); phones(); });
  mm.add(MOTION + ' and (max-width: 760px)', () => cardsIn(false));
  mm.add(MOTION + ' and (hover: hover) and (pointer: fine)', tilt);
  release();
})();
