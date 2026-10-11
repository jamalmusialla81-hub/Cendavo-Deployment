// Homepage behaviour. Progressive enhancement throughout: without this script (or without GSAP)
// every word and photo is visible, and the comparison shows both states split at 50%.
(() => {
  const still = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  // Before/after comparison: a labelled range input plus Before/After buttons.
  const figure = document.querySelector('[data-compare]');
  const controls = figure?.querySelector('[data-compare-controls]');
  const range = controls?.querySelector('input[type="range"]');
  if (range) {
    const buttons = controls.querySelectorAll('[data-compare-set]');
    const state = { v: Number(range.value) || 50 };
    let tween = null;
    const update = () => {
      const value = Math.min(100, Math.max(0, Number(range.value) || 0));
      figure.style.setProperty('--pos', value + '%');
      range.setAttribute('aria-valuetext', value === 0 ? 'Before only' : value === 100 ? 'After only' : value + ' of 100 showing the redesign');
      buttons.forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.compareSet) === value)));
    };
    range.addEventListener('input', () => {
      tween?.kill();
      state.v = Number(range.value);
      update();
    });
    buttons.forEach(button => button.addEventListener('click', () => {
      const target = Number(button.dataset.compareSet);
      tween?.kill();
      if (window.gsap && !still()) {
        // Glide the divider to the chosen side; the range value follows so it stays the source of truth.
        tween = window.gsap.to(state, { v: target, duration: 0.6, ease: 'power2.inOut', onUpdate: () => { range.value = Math.round(state.v); update(); } });
      } else {
        state.v = target;
        range.value = target;
        update();
      }
    }));
    controls.hidden = false;
    update();
  }

  // Motion: GSAP is optional. Initial states are set from JS only, inside the reduced-motion guard,
  // and only transform/opacity are animated. Nothing is pinned, scroll is never taken over and there is no parallax.
  const gsap = window.gsap;
  if (!gsap) return;
  const ScrollTrigger = window.ScrollTrigger;
  if (ScrollTrigger) gsap.registerPlugin(ScrollTrigger);
  const mm = gsap.matchMedia();
  mm.add('(prefers-reduced-motion: no-preference)', () => {
    gsap.from('.hero-h .ln > span', { yPercent: 108, duration: 1.1, stagger: 0.08, ease: 'power4.out' });
    gsap.from('[data-hero-fade]', { y: 18, autoAlpha: 0, duration: 0.9, stagger: 0.1, delay: 0.45, ease: 'power3.out' });
    if (!ScrollTrigger) return;
    gsap.utils.toArray('[data-rise]').forEach(element => {
      gsap.from(element, { y: 28, autoAlpha: 0, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: element, start: 'top 88%', once: true } });
    });
  });
})();
