// Shared motion for Home, Work, Services, Pricing and About (never Contact or Demo). Everything is visible without it. Start
// states come from JS inside the reduced-motion guard; openings are also held by CSS while .ph-wait is on <html> (see
// motion-boot.js). Only transform, opacity and clip-path animate (never visibility).
(() => {
  const doc = document;
  const root = doc.documentElement;
  const $$ = (selector, scope) => Array.from((scope || doc).querySelectorAll(selector));
  const MOTION = '(prefers-reduced-motion: no-preference)';
  const MAX_PULL = 6; // magnetic button: never more than 6px from its place
  const DIM = 0.45; // inactive "What we do" headings: bone at this opacity on ink stays above 3:1 (tested)
  const ownsOpening = !doc.querySelector('.hero-h'); // home.js opens the homepage hero and releases .ph-wait itself
  const release = () => root.classList.remove('ph-wait');

  // Home "What we do": row n (hovered, focused or, on large screens, crossing mid-viewport) shows photo n. Without this
  // script the first photo shows; without GSAP the swap is the guarded CSS crossfade.
  const rows = $$('.svc');
  const panel = doc.querySelector('.svc-panel');
  const photos = $$('.svc-photo');
  const heads = rows.map(row => row.querySelector('h3'));
  let current = -1;
  let swap = null; // GSAP motion only: wipes the photo in, dims the other headings
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

  mm.add(MOTION, () => {
    // Openings, only while CSS holds them (after the 2.5 s failsafe they stay shown): lines rise through their masks, photos
    // un-mask in turn, copy follows. fromTo applies the CSS start states before .ph-wait goes, so nothing flashes.
    if (ownsOpening && root.classList.contains('ph-wait')) {
      $$('[data-ph]').forEach(head => {
        const tl = gsap.timeline({ defaults: { ease: 'power4.out' } });
        const lines = $$('h1 .ln > span', head);
        const media = $$('[data-ph-media]', head);
        const fades = $$('[data-ph-fade]', head);
        if (lines.length) tl.fromTo(lines, { yPercent: 108, y: 0 }, { yPercent: 0, y: 0, duration: 0.9, stagger: 0.08, clearProps: 'transform' }, 0);
        if (media.length) tl.fromTo(media, { clipPath: 'inset(0 0 0 100%)' }, { clipPath: 'inset(0 0 0 0%)', duration: 1, stagger: 0.12, ease: 'expo.inOut', clearProps: 'clipPath' }, 0.05);
        if (fades.length) tl.fromTo(fades, { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, stagger: 0.08, clearProps: 'opacity,transform' }, 0.3);
      });
    }

    // Section headings and short copy rise once as they scroll in; image frames un-mask once.
    const rises = later($$('[data-rise]'));
    const reveals = later($$('[data-reveal]'));
    if (rises.length) {
      gsap.set(rises, { opacity: 0, y: 28 });
      ScrollTrigger.batch(rises, { start: 'top 88%', once: true, onEnter: batch => gsap.to(batch, { opacity: 1, y: 0, duration: 0.8, stagger: 0.08, ease: 'power3.out', clearProps: 'opacity,transform' }) });
    }
    if (reveals.length) {
      gsap.set(reveals, { clipPath: 'inset(0 0 100% 0)' });
      ScrollTrigger.batch(reveals, { start: 'top 85%', once: true, onEnter: batch => gsap.to(batch, { clipPath: 'inset(0 0 0% 0)', duration: 1, stagger: 0.09, ease: 'expo.inOut', clearProps: 'clipPath' }) });
    }

    // Device and document mockups slide up into place once.
    later($$('[data-devices]')).forEach(item => {
      gsap.from(item, { y: 70, rotation: 3, opacity: 0, duration: 1, ease: 'power3.out', clearProps: 'transform,opacity', scrollTrigger: { trigger: item, start: 'top 85%', once: true } });
    });

    // The incoming photo wipes up over the outgoing one; other headings dim.
    if (rows.length && panel) {
      panel.classList.add('is-wipe');
      gsap.set(heads, { opacity: at => (at === current ? 1 : DIM) });
      swap = (index, previous) => {
        gsap.killTweensOf(photos);
        if (photos[previous]) gsap.set(photos[previous], { clearProps: 'clipPath' });
        if (photos[index]) gsap.fromTo(photos[index], { clipPath: 'inset(100% 0 0 0)' }, { clipPath: 'inset(0% 0 0 0)', duration: 0.8, ease: 'expo.inOut', clearProps: 'clipPath' });
        gsap.to(heads, { opacity: at => (at === index ? 1 : DIM), duration: 0.4, ease: 'power2.out', overwrite: true });
      };
    }

    // FAQ: the native <details> opens as usual, then its answer fades up.
    const faqs = $$('details');
    const onToggle = event => {
      const details = event.currentTarget;
      if (!details.open) return;
      const answer = Array.from(details.children).filter(child => child.tagName !== 'SUMMARY');
      gsap.fromTo(answer, { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out', clearProps: 'opacity,transform' });
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
      const toX = gsap.quickTo(button, 'x', { duration: 0.4, ease: 'power3.out' });
      const toY = gsap.quickTo(button, 'y', { duration: 0.4, ease: 'power3.out' });
      const move = event => {
        const box = button.getBoundingClientRect();
        toX(clamp((event.clientX - box.left - box.width / 2) * 0.2));
        toY(clamp((event.clientY - box.top - box.height / 2) * 0.3));
      };
      const leave = () => { toX(0); toY(0); };
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
