// Homepage: showreel playback, before/after comparison, first-visit intro and hero. Without this script (or GSAP)
// everything is visible, the intro never shows, the comparison sits at 50% and the showreel keeps its native controls.
// Shared reveals live in motion.js.
(() => {
  const doc = document;
  const root = doc.documentElement;
  const $$ = (selector, scope) => Array.from((scope || doc).querySelectorAll(selector));
  const still = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const INTRO_FLAG = 'cendavo-intro';
  // Start the 1.35 s intro only if it can finish before motion-boot.js's 2.5 s failsafe removes the panel.
  const INTRO_LATEST_START_MS = 700;
  const SKIP_EVENTS = ['keydown', 'pointerdown', 'wheel', 'touchstart'];
  const MOTION = '(prefers-reduced-motion: no-preference)';
  // Phones get the vertical cut; home.css switches the frame to 9:16 at the same width.
  const NARROW = '(max-width: 640px)';

  // Showreel (no GSAP needed): a silent video that plays only while in view, and never on its own with reduced motion or
  // Save-Data. The native controls give way to one Pause/Play button (WCAG 2.2.2); a press of Pause is remembered.
  const reel = doc.querySelector('[data-reel]');
  const video = reel?.querySelector('video');
  const toggle = reel?.querySelector('[data-reel-toggle]');
  if (video && toggle) {
    if (window.matchMedia?.(NARROW).matches && video.dataset.narrowSrc) {
      const source = video.querySelector('source');
      if (source) source.setAttribute('src', video.dataset.narrowSrc);
      if (video.dataset.narrowPoster) video.setAttribute('poster', video.dataset.narrowPoster);
      video.load(); // preload="none": this picks up the new source without downloading it yet
    }
    const saveData = Boolean(window.navigator?.connection?.saveData);
    let wanted = !still() && !saveData; // the visitor's choice once they press the button
    let inView = false;
    const label = () => { toggle.textContent = video.paused ? 'Play showreel' : 'Pause showreel'; };
    const play = () => {
      let attempt;
      try { attempt = video.play(); } catch (error) { attempt = null; }
      if (attempt && typeof attempt.then === 'function') attempt.then(label, label); // refused (e.g. Low Power Mode): shows Play
      label();
    };
    video.muted = true;
    video.removeAttribute('controls');
    video.addEventListener('play', label);
    video.addEventListener('pause', label);
    toggle.addEventListener('click', () => {
      wanted = video.paused;
      if (wanted) play();
      else video.pause();
      label();
    });
    if (window.IntersectionObserver) {
      new window.IntersectionObserver(entries => {
        inView = entries[entries.length - 1].isIntersecting;
        if (inView && wanted && video.paused) play();
        else if (!inView && !video.paused) video.pause();
      }, { threshold: 0.25 }).observe(video);
    }
    toggle.hidden = false;
    label();
  }

  // Before/after comparison: a labelled range input plus Before/After buttons.
  const figure = doc.querySelector('[data-compare]');
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

  // Skipping the intro never cancels the key, click or scroll.
  let onSkip = null;
  const endIntro = () => {
    root.classList.remove('ns-intro');
    try { window.sessionStorage.setItem(INTRO_FLAG, '1'); } catch (error) { /* storage blocked: the intro is just not remembered */ }
    if (onSkip) SKIP_EVENTS.forEach(type => window.removeEventListener(type, onSkip));
    onSkip = null;
  };

  // GSAP is optional; motion stays inside the reduced-motion guard and animates transform, opacity and clip-path only.
  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) root.classList.remove('ph-wait'); // no GSAP: show the hero at once
  if (!gsap || !ScrollTrigger) { endIntro(); return; }
  gsap.registerPlugin(ScrollTrigger);
  const mm = gsap.matchMedia();

  // Hero (1.2 s): lines rise, photo un-masks (not under the intro: LCP), copy, phone. fromTo takes over .ph-wait (y: 0: GSAP reads its % as px).
  const heroTimeline = underIntro => {
    const tl = gsap.timeline({ paused: true, defaults: { ease: 'power4.out' } });
    const lines = $$('.hero-h .ln > span');
    const photo = $$('.hero-photo');
    const fades = $$('[data-hero-fade]');
    const device = $$('.hero-device');
    if (lines.length) tl.fromTo(lines, { yPercent: 108, y: 0 }, { yPercent: 0, y: 0, duration: 0.8, stagger: 0.08, clearProps: 'transform' }, 0);
    if (photo.length) {
      if (!underIntro) tl.fromTo(photo, { clipPath: 'inset(0 0 0 100%)' }, { clipPath: 'inset(0 0 0 0%)', duration: 1, ease: 'expo.inOut', clearProps: 'clipPath' }, 0);
      tl.fromTo($$('img', photo[0]), { scale: 1.08 }, { scale: 1, duration: 1.2, ease: 'power3.out' }, 0);
    }
    if (fades.length) tl.fromTo(fades, { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, stagger: 0.1 }, 0.35);
    if (device.length) tl.fromTo(device, { y: 70, opacity: 0 }, { y: 0, opacity: 1, duration: 0.75, ease: 'power3.out' }, 0.4);
    return tl;
  };

  // Intro: the C-mark assembles, the wordmark resolves, the panel wipes up by 1.35 s; the hero starts at 0.95 s.
  const playIntro = (panel, hero) => {
    const tl = gsap.timeline({ onComplete: endIntro });
    tl.fromTo($$('.intro-mark path', panel), { rotation: index => [-70, 60, -60][index % 3], svgOrigin: '100 100', opacity: 0 }, { rotation: 0, svgOrigin: '100 100', opacity: 1, duration: 0.55, stagger: 0.08, ease: 'power4.out' }, 0.05)
      .fromTo($$('.intro-word > span', panel), { yPercent: 110, y: 0 }, { yPercent: 0, y: 0, duration: 0.45, ease: 'power4.out' }, 0.3)
      .fromTo(panel, { clipPath: 'inset(0 0 0% 0)' }, { clipPath: 'inset(0 0 100% 0)', duration: 0.6, ease: 'power4.inOut' }, 0.75)
      .add(() => hero.play(0), 0.95);
    onSkip = () => {
      tl.progress(1);
      hero.progress(1);
      endIntro();
    };
    SKIP_EVENTS.forEach(type => window.addEventListener(type, onSkip, { passive: true }));
    return tl;
  };

  mm.add('(prefers-reduced-motion: reduce)', endIntro);
  // The hero opens only under the intro or while CSS holds it; after the 2.5 s failsafe it stays shown.
  mm.add(MOTION, () => {
    const panel = doc.querySelector('.intro');
    const onTime = !window.performance || window.performance.now() <= INTRO_LATEST_START_MS;
    const intro = panel && onTime && root.classList.contains('ns-intro');
    if (intro || root.classList.contains('ph-wait')) {
      const hero = heroTimeline(intro);
      if (intro) playIntro(panel, hero);
      else {
        endIntro();
        hero.play(0);
      }
    } else endIntro();
    root.classList.remove('ph-wait');
    return endIntro;
  });
})();
