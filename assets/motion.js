// Shared motion for the homepage, Work, Services and Pricing (never Contact or Demo). Everything is visible without this
// file: initial states are set from JS only, inside the reduced-motion guard, and only transform, opacity and clip-path
// are animated (opacity, never visibility, so content stays readable by assistive technology and clickable).
(() => {
  const doc = document;
  const $$ = (selector, scope) => Array.from((scope || doc).querySelectorAll(selector));
  const MOTION = '(prefers-reduced-motion: no-preference)';
  const MAX_PULL = 6; // magnetic button: never more than 6px from its place

  // Services (homepage): the photo panel follows the hovered or focused row and stays on the last one. Row n shows photo n.
  // Without this script the panel shows the first photo; the crossfade is CSS inside the reduced-motion guard.
  const rows = $$('.svc');
  const panel = doc.querySelector('.svc-panel');
  const photos = $$('.svc-photo');
  if (rows.length) {
    const activate = active => {
      const index = rows.indexOf(active);
      rows.forEach(row => row.classList.toggle('is-active', row === active));
      photos.forEach((photo, at) => photo.classList.toggle('is-active', at === index));
    };
    rows.forEach(row => {
      row.addEventListener('mouseenter', () => activate(row));
      row.addEventListener('focusin', () => activate(row));
    });
    activate(rows[0]);
    if (panel) panel.classList.add('is-live');
  }

  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);
  const mm = gsap.matchMedia();

  mm.add(MOTION, () => {
    // Inner-page openings: the headline rises, the head photo un-masks and settles, supporting copy follows.
    $$('[data-ph]').forEach(head => {
      const tl = gsap.timeline({ defaults: { ease: 'power4.out' } });
      const title = $$('h1', head);
      const fades = $$('[data-ph-fade]', head);
      if (title.length) tl.from(title, { y: 48, opacity: 0, duration: 0.9 }, 0);
      $$('[data-ph-media]', head).forEach(media => {
        tl.fromTo(media, { clipPath: 'inset(0 0 0 100%)' }, { clipPath: 'inset(0 0 0 0%)', duration: 1, ease: 'expo.inOut', clearProps: 'clipPath' }, 0)
          .from($$('img', media), { scale: 1.08, duration: 1.2, ease: 'power3.out' }, 0);
      });
      if (fades.length) tl.from(fades, { y: 18, opacity: 0, duration: 0.6, stagger: 0.08 }, 0.3);
    });

    // Section headings and short copy rise once as they scroll in; image frames un-mask once.
    const rises = $$('[data-rise]');
    const reveals = $$('[data-reveal]');
    if (rises.length) {
      gsap.set(rises, { opacity: 0, y: 28 });
      ScrollTrigger.batch(rises, { start: 'top 88%', once: true, onEnter: batch => gsap.to(batch, { opacity: 1, y: 0, duration: 0.8, stagger: 0.08, ease: 'power3.out', clearProps: 'opacity,transform' }) });
    }
    if (reveals.length) {
      gsap.set(reveals, { clipPath: 'inset(0 0 100% 0)' });
      ScrollTrigger.batch(reveals, { start: 'top 85%', once: true, onEnter: batch => gsap.to(batch, { clipPath: 'inset(0 0 0% 0)', duration: 1, stagger: 0.09, ease: 'expo.inOut', clearProps: 'clipPath' }) });
    }

    // Device and document mockups slide up into place once.
    $$('[data-devices]').forEach(item => {
      gsap.from(item, { y: 70, rotation: 3, opacity: 0, duration: 1, ease: 'power3.out', clearProps: 'transform,opacity', scrollTrigger: { trigger: item, start: 'top 85%', once: true } });
    });

    // FAQ: the native <details> opens as usual; its answer then fades up. Nothing is cancelled or measured.
    const faqs = $$('details');
    const onToggle = event => {
      const details = event.currentTarget;
      if (!details.open) return;
      const answer = Array.from(details.children).filter(child => child.tagName !== 'SUMMARY');
      gsap.fromTo(answer, { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out', clearProps: 'opacity,transform' });
    };
    faqs.forEach(details => details.addEventListener('toggle', onToggle));
    return () => faqs.forEach(details => details.removeEventListener('toggle', onToggle));
  });

  // Gentle photo parallax (yPercent +/-6, scrubbed): large screens only, to spare phones the work.
  mm.add(MOTION + ' and (min-width: 1081px)', () => {
    $$('[data-parallax]').forEach(frame => {
      gsap.fromTo($$('img', frame), { yPercent: -6, scale: 1.14 }, { yPercent: 6, ease: 'none', scrollTrigger: { trigger: frame, start: 'top bottom', end: 'bottom top', scrub: 0.5 } });
    });
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
})();
