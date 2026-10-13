// Shared motion for Home, Work, Services, Pricing and About (never Contact, Demo or 404). Everything is visible without
// it: start states come from JS inside the reduced-motion guard, openings are also held by CSS while .ph-wait is on <html>
// (motion-boot.js). Only transform, opacity and clip-path animate. Daylight (Task 34): the plan's two curves and four
// durations. The inner pages' scroll scenes (benches, drawn lines, vignettes) are in scenes.js, which Home does not load.
(() => {
  const doc = document;
  const root = doc.documentElement;
  const $$ = (selector, scope) => Array.from((scope || doc).querySelectorAll(selector));
  const MOTION = '(prefers-reduced-motion: no-preference)';
  // magnetic button: never more than 6px from its place
  const MAX_PULL = 6;
  // inactive "What we do" headings: bone at this opacity on ink stays above 3:1 (tested)
  const DIM = 0.45;
  // home.js opens the homepage hero and releases .ph-wait itself
  const ownsOpening = !doc.querySelector('.hero-h');
  const release = () => root.classList.remove('ph-wait');
  // The two Daylight curves (CSS cubic-bezier): entrances, and changes of state.
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
  const IN = bezier(0.2, 0.8, 0.2, 1);
  const IO = bezier(0.7, 0, 0.2, 1);
  // Task 56: shared with scenes.js (loaded after this file), so the inner pages ship the curves once.
  window.__ease = { IN, IO };
  const SHOWN = 'opacity,transform';
  // Task 48: while Pause motion is pressed GSAP's ticker sleeps (glass.js), so nothing here starts a new tween then.
  const paused = () => Boolean(window.__glass?.paused);
  // fromTo pair: rise y px into place.
  const up = (y, duration, stagger) => [{ opacity: 0, y }, { opacity: 1, y: 0, duration, stagger: stagger || 0, clearProps: SHOWN }];

  // "What we do" rows: row n (hovered, focused or, on large screens, crossing mid-viewport) shows photo n. Without this
  // script the first photo shows; without GSAP the swap is the guarded CSS crossfade.
  const rows = $$('.svc');
  const panel = doc.querySelector('.svc-panel');
  const photos = $$('.svc-photo');
  const heads = rows.map(row => row.querySelector('h3'));
  let current = -1;
  // GSAP motion only: wipes the photo in, dims the other headings
  let swap = null;
  const activate = active => {
    const index = rows.indexOf(active);
    if (index === current) return;
    const previous = current;
    current = index;
    rows.forEach(row => row.classList.toggle('is-active', row === active));
    photos.forEach((photo, at) => {
      photo.classList.toggle('is-active', at === index);
      photo.classList.toggle('is-prev', at === previous);
    });
    if (swap) swap(index, previous);
  };
  if (rows.length) {
    rows.forEach(row => {
      row.addEventListener('mouseenter', () => activate(row));
      row.addEventListener('focusin', () => activate(row));
    });
    activate(rows[0]);
    if (panel) panel.classList.add('is-live');
  }

  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) { release(); return; }
  gsap.registerPlugin(ScrollTrigger);
  const mm = gsap.matchMedia();
  // Scroll reveals only below the fold: hiding what is already on screen would make it blink.
  const later = list => list.filter(item => item.getBoundingClientRect().top >= window.innerHeight);
  // Task 43: every reveal starts as its trigger's top crosses 85% of the viewport.
  const START = 'top 85%';
  const once = (trigger, start) => ({ trigger, start: start || START, once: true });

  mm.add(MOTION, () => {
    // Openings, only while CSS holds them (after the 2.5 s failsafe they stay shown): lines rise through their masks, frames
    // un-mask in turn, copy follows. fromTo applies the CSS start states before .ph-wait goes, so nothing flashes.
    if (ownsOpening && root.classList.contains('ph-wait')) {
      $$('[data-ph]').forEach(head => {
        const tl = gsap.timeline({ defaults: { ease: IN } });
        const lines = $$('h1 .ln > span', head);
        const media = $$('[data-ph-media]', head);
        const fades = $$('[data-ph-fade]', head);
        if (lines.length) tl.fromTo(lines, { yPercent: 108, y: 0 }, { yPercent: 0, y: 0, duration: 1, stagger: 0.08, clearProps: 'transform' }, 0);
        if (media.length) tl.fromTo(media, { clipPath: 'inset(0 0 0 100%)' }, { clipPath: 'inset(0 0 0 0%)', duration: 1, stagger: 0.08, ease: IO, clearProps: 'clipPath' }, 0.05);
        // Task 48: the copy only rises (never opacity 0), so it paints with the headline (LCP).
        if (fades.length) tl.fromTo(fades, { y: 18 }, { y: 0, duration: 0.7, stagger: 0.08, clearProps: 'transform' }, 0.3);
      });
      // Pricing: the quote sheet fills in line by line, then its fixed-price line is set, within 1.2 s.
      const sheet = doc.querySelector('[data-sheet]');
      if (sheet) {
        gsap.timeline({ defaults: { ease: IN } })
          .fromTo($$('.q-lines li', sheet), ...up(8, 0.4, 0.06), 0.4)
          .fromTo($$('.q-total', sheet), { clipPath: 'inset(0% 100% 0% 0% round 12px)' }, { clipPath: 'inset(0% 0% 0% 0% round 12px)', duration: 0.4, ease: IO, clearProps: 'clipPath' }, 0.8);
      }
    }

    // Section headings and short copy rise once as they scroll in; image frames un-mask once.
    const rises = later($$('[data-rise]'));
    const reveals = later($$('[data-reveal]'));
    if (rises.length) {
      gsap.set(rises, { opacity: 0, y: 28 });
      ScrollTrigger.batch(rises, { start: START, once: true, onEnter: batch => gsap.to(batch, { opacity: 1, y: 0, duration: 0.7, stagger: 0.08, ease: IN, clearProps: SHOWN }) });
    }
    if (reveals.length) {
      gsap.set(reveals, { clipPath: 'inset(0 0 100% 0)' });
      ScrollTrigger.batch(reveals, { start: START, once: true, onEnter: batch => gsap.to(batch, { clipPath: 'inset(0 0 0% 0)', duration: 1, stagger: 0.08, ease: IO, clearProps: 'clipPath' }) });
    }

    // Device and document mockups slide up into place once.
    later($$('[data-devices]')).forEach(item => {
      gsap.from(item, { y: 40, opacity: 0, duration: 1, ease: IN, clearProps: SHOWN, scrollTrigger: once(item) });
    });

    // Lists arrive in reading order. A list inside a rising or un-masking card is triggered by that card, at the same
    // line, so its items never arrive after the card and leave it standing empty (Task 43).
    later($$('[data-stagger]')).forEach(list => {
      const host = list.parentElement?.closest?.('[data-rise], [data-reveal]') || list;
      gsap.fromTo(Array.from(list.children), { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.7, stagger: 0.06, ease: IN, clearProps: SHOWN, scrollTrigger: once(host) });
    });

    // The incoming photo wipes up over the outgoing one; other headings dim.
    if (rows.length && panel) {
      panel.classList.add('is-wipe');
      gsap.set(heads, { opacity: at => (at === current ? 1 : DIM) });
      swap = (index, previous) => {
        gsap.killTweensOf(photos);
        if (paused()) {
          photos.forEach(photo => { photo.style.clipPath = ''; });
          gsap.killTweensOf(heads);
          heads.forEach((head, at) => { head.style.opacity = String(at === index ? 1 : DIM); });
          return;
        }
        if (photos[previous]) gsap.set(photos[previous], { clearProps: 'clipPath' });
        if (photos[index]) gsap.fromTo(photos[index], { clipPath: 'inset(100% 0 0 0)' }, { clipPath: 'inset(0% 0 0 0)', duration: 0.7, ease: IO, clearProps: 'clipPath' });
        gsap.to(heads, { opacity: at => (at === index ? 1 : DIM), duration: 0.4, ease: IN, overwrite: true });
      };
    }

    // FAQ: the native <details> opens as usual, then its answer fades up.
    const faqs = $$('details');
    const onToggle = event => {
      const details = event.currentTarget;
      if (!details.open || paused()) return;
      const answer = Array.from(details.children).filter(child => child.tagName !== 'SUMMARY');
      gsap.fromTo(answer, { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.4, ease: IN, clearProps: SHOWN });
    };
    faqs.forEach(details => details.addEventListener('toggle', onToggle));
    return () => {
      faqs.forEach(details => details.removeEventListener('toggle', onToggle));
      swap = null;
      if (panel) panel.classList.remove('is-wipe');
      gsap.killTweensOf(photos.concat(heads));
      gsap.set(photos.concat(heads), { clearProps: 'clipPath,opacity' });
    };
  });

  // Large screens: photo parallax (yPercent +/-6, scrubbed); "What we do" rows activate as they cross mid-viewport.
  mm.add(MOTION + ' and (min-width: 1081px)', () => {
    $$('[data-parallax]').forEach(frame => {
      gsap.fromTo($$('img', frame), { yPercent: -6, scale: 1.14 }, { yPercent: 6, ease: 'none', scrollTrigger: { trigger: frame, start: 'top bottom', end: 'bottom top', scrub: 0.5 } });
    });
    rows.forEach(row => ScrollTrigger.create({ trigger: row, start: 'top center', end: 'bottom center', onToggle: self => { if (self.isActive) activate(row); } }));
  });

  // Magnetic primary buttons: fine pointers only, offset clamped to MAX_PULL.
  mm.add(MOTION + ' and (hover: hover) and (pointer: fine)', () => {
    const clamp = value => Math.max(-MAX_PULL, Math.min(MAX_PULL, value));
    const cleanups = $$('.button.go').map(button => {
      const toX = gsap.quickTo(button, 'x', { duration: 0.4, ease: IN });
      const toY = gsap.quickTo(button, 'y', { duration: 0.4, ease: IN });
      const move = event => {
        if (paused()) return;
        const box = button.getBoundingClientRect();
        toX(clamp((event.clientX - box.left - box.width / 2) * 0.2));
        toY(clamp((event.clientY - box.top - box.height / 2) * 0.3));
      };
      const leave = () => { if (!paused()) { toX(0); toY(0); } };
      button.addEventListener('pointermove', move);
      button.addEventListener('pointerleave', leave);
      return () => {
        button.removeEventListener('pointermove', move);
        button.removeEventListener('pointerleave', leave);
      };
    });
    return () => cleanups.forEach(cleanup => cleanup());
  });

  // GSAP now holds the start states (or nothing animates): let go of the CSS hold.
  if (ownsOpening) release();
})();
