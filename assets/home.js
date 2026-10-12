// Homepage: before/after comparison and its demo sweep, showreel entrance, first-visit intro and hero. Without it (or GSAP)
// everything is visible, the intro never shows and the comparison sits at 50%. Video playback is in reel.js.
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
  // Demo sweep, once: 50 -> 82 -> 18 -> 50 over 1.6 s. Any press, key, touch or use of the controls stops it.
  const SWEEP = [[82, 0.5], [18, 0.7], [50, 0.4]];
  const SWEEP_STOP = ['pointerdown', 'keydown', 'touchstart'];

  // Before/after comparison: a labelled range input plus Before/After buttons.
  const figure = doc.querySelector('[data-compare]');
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

  // Only the visual --pos moves: the range value, its aria-valuetext and the buttons never change (nothing is announced).
  const demoSweep = () => {
    if (!update) return;
    const at = { p: Number(range.value) || 50 };
    const draw = () => figure.style.setProperty('--pos', at.p + '%');
    ScrollTrigger.create({ trigger: figure, start: 'top 65%', once: true, onEnter: () => {
      if (swept) return;
      swept = true;
      sweep = gsap.timeline({ onComplete: stopSweep });
      SWEEP.forEach(([p, duration]) => sweep.to(at, { p, duration, ease: 'power2.inOut', onUpdate: draw }));
      SWEEP_STOP.forEach(type => window.addEventListener(type, stopSweep, { passive: true }));
    } });
  };

  // Showreel entrance, if below the fold: the video opens from an inset window as it scrolls in (scrubbed, no pin); the
  // caption and Pause button rise as it starts to play.
  const reelEntrance = () => {
    const reel = doc.querySelector('[data-reel]');
    const video = reel?.querySelector('video');
    if (!video || reel.getBoundingClientRect().top < window.innerHeight) return;
    gsap.fromTo(video, { clipPath: 'inset(9% 11% 9% 11%)', scale: 1.08 }, { clipPath: 'inset(0% 0% 0% 0%)', scale: 1, ease: 'none', scrollTrigger: { trigger: reel, start: 'top bottom', end: 'top 35%', scrub: 0.6 } });
    gsap.fromTo($$('.reel-cap, [data-reel-toggle]', reel), { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.6, stagger: 0.08, ease: 'power3.out', clearProps: 'opacity,transform', scrollTrigger: { trigger: reel, start: 'top 90%', once: true } });
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
    reelEntrance();
    demoSweep();
    return () => { endIntro(); stopSweep(); };
  });
})();
