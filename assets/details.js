// Motion details (Task 29), GSAP pages only and behind the reduced-motion guard: Services step numerals count up once;
// with a fine pointer that can hover, project cards tilt and a cursor ring follows (drawn in addition to the native
// cursor, never instead). Card push-in and light sweep are CSS; keyboard focus gets those but no tilt.
(() => {
  const doc = document;
  const $$ = selector => Array.from(doc.querySelectorAll(selector));
  const MOTION = '(prefers-reduced-motion: no-preference)';
  const MAX_TILT = 6; // degrees
  const PERSPECTIVE = 900; // px
  const GROW = 'a, button, summary, label, [role="button"]'; // the ring grows over these
  const FIELDS = 'input, textarea, select'; // and steps aside over these
  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);
  const mm = gsap.matchMedia();
  const clamp = value => Math.max(-MAX_TILT, Math.min(MAX_TILT, value));
  const ease = { duration: 0.6, ease: 'power3.out' };

  // Numerals are aria-hidden and final in the HTML; below the fold they show 00 until they scroll in.
  mm.add(MOTION, () => {
    const steps = $$('.step-n').filter(el => el.getBoundingClientRect().top >= window.innerHeight && /^\d+$/.test(el.textContent));
    const finals = steps.map(el => el.textContent);
    steps.forEach((el, i) => {
      const at = { n: 0 };
      const show = () => { el.textContent = String(Math.round(at.n)).padStart(finals[i].length, '0'); };
      show();
      gsap.to(at, { n: Number(finals[i]), duration: 0.9, ease: 'power2.out', onUpdate: show, onComplete: () => { el.textContent = finals[i]; },
        scrollTrigger: { trigger: el, start: 'top 88%', once: true } });
    });
    return () => steps.forEach((el, i) => { el.textContent = finals[i]; });
  });

  mm.add(MOTION + ' and (hover: hover) and (pointer: fine)', () => {
    const offs = $$('.teaser-card, .wk-tile').map(card => {
      gsap.set(card, { transformPerspective: PERSPECTIVE });
      const toX = gsap.quickTo(card, 'rotationX', ease);
      const toY = gsap.quickTo(card, 'rotationY', ease);
      const move = event => {
        const box = card.getBoundingClientRect();
        toY(clamp(((event.clientX - box.left) / box.width - 0.5) * 2 * MAX_TILT));
        toX(clamp((0.5 - (event.clientY - box.top) / box.height) * 2 * MAX_TILT));
      };
      const leave = () => { toX(0); toY(0); };
      card.addEventListener('pointermove', move);
      card.addEventListener('pointerleave', leave);
      return () => {
        card.removeEventListener('pointermove', move);
        card.removeEventListener('pointerleave', leave);
        gsap.set(card, { clearProps: 'transform' });
      };
    });

    // One decorative ring, moved by transform only while the pointer moves (quickTo); CSS keeps it out of every click.
    const ring = doc.createElement('div');
    ring.className = 'cursor-ring';
    ring.setAttribute('aria-hidden', 'true');
    ring.appendChild(doc.createElement('span'));
    doc.body.appendChild(ring);
    gsap.set(ring, { opacity: 0 });
    const toLeft = gsap.quickTo(ring, 'x', { duration: 0.35, ease: 'power3.out' });
    const toTop = gsap.quickTo(ring, 'y', { duration: 0.35, ease: 'power3.out' });
    let shown = false;
    const show = on => {
      if (on !== shown) gsap.to(ring, { opacity: on ? 1 : 0, duration: 0.2, overwrite: 'auto' });
      shown = on;
    };
    const move = event => {
      if (event.pointerType && event.pointerType !== 'mouse') return;
      const target = event.target?.closest ? event.target : null;
      if (!shown) gsap.set(ring, { x: event.clientX, y: event.clientY }); // appear at the pointer rather than glide in
      toLeft(event.clientX);
      toTop(event.clientY);
      ring.classList.toggle('is-link', Boolean(target?.closest(GROW)));
      show(!target?.closest(FIELDS));
    };
    const out = event => { if (!event.relatedTarget) show(false); }; // the pointer left the window
    window.addEventListener('pointermove', move, { passive: true });
    doc.addEventListener('pointerout', out);
    return () => {
      offs.forEach(off => off());
      window.removeEventListener('pointermove', move);
      doc.removeEventListener('pointerout', out);
      ring.remove();
    };
  });
})();
