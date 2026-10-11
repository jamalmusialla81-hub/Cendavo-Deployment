// Homepage behaviour: before/after comparison, first-visit intro, hero choreography and the concept-project sequence.
// Progressive enhancement throughout: without this script (or without GSAP) every word and photo is visible, the intro
// panel is never shown and the comparison shows both states split at 50%. Shared reveals live in motion.js.
(() => {
  const doc = document;
  const root = doc.documentElement;
  const $$ = (selector, scope) => Array.from((scope || doc).querySelectorAll(selector));
  const still = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const INTRO_FLAG = 'cendavo-intro';
  // Start the 1.75 s intro only if it can finish before motion-boot.js's 2.5 s failsafe removes the panel.
  const INTRO_LATEST_START_MS = 700;
  const SKIP_EVENTS = ['keydown', 'pointerdown', 'wheel', 'touchstart'];
  // The pinned project sequence: large screens only, and never longer than two viewport heights of scrolling.
  const PIN_VIEWPORTS = 2;
  const MOTION = '(prefers-reduced-motion: no-preference)';
  const PIN_QUERY = MOTION + ' and (min-width: 1081px) and (min-height: 620px)';
  const STACK_QUERY = MOTION + ' and (max-width: 1080px), ' + MOTION + ' and (max-height: 619px)';

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

  // Intro bookkeeping. The skip handler never cancels the event: the key, click or scroll still does what it would have.
  let onSkip = null;
  const endIntro = () => {
    root.classList.remove('ns-intro');
    try { window.sessionStorage.setItem(INTRO_FLAG, '1'); } catch (error) { /* storage blocked: the intro is just not remembered */ }
    if (onSkip) SKIP_EVENTS.forEach(type => window.removeEventListener(type, onSkip));
    onSkip = null;
  };

  // Motion: GSAP is optional. Initial states are set from JS only, inside the reduced-motion guard, and only
  // transform, opacity and clip-path are animated. Content is faded with opacity (never visibility), so it stays
  // readable by assistive technology and clickable throughout.
  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) { endIntro(); return; }
  gsap.registerPlugin(ScrollTrigger);
  const mm = gsap.matchMedia();

  // Hero: headline lines rise through their masks, the photo un-masks and settles, copy and phone follow. 1.2 s in total.
  const heroTimeline = () => {
    const tl = gsap.timeline({ paused: true, defaults: { ease: 'power4.out' } });
    const lines = $$('.hero-h .ln > span');
    const photo = $$('.hero-photo');
    const fades = $$('[data-hero-fade]');
    const device = $$('.hero-device');
    if (lines.length) tl.from(lines, { yPercent: 108, duration: 0.8, stagger: 0.08 }, 0);
    if (photo.length) {
      tl.fromTo(photo, { clipPath: 'inset(0 0 0 100%)' }, { clipPath: 'inset(0 0 0 0%)', duration: 1, ease: 'expo.inOut', clearProps: 'clipPath' }, 0)
        .from($$('img', photo[0]), { scale: 1.08, duration: 1.2, ease: 'power3.out' }, 0);
    }
    if (fades.length) tl.from(fades, { y: 18, opacity: 0, duration: 0.6, stagger: 0.1 }, 0.35);
    if (device.length) tl.from(device, { y: 70, opacity: 0, duration: 0.75, ease: 'power3.out' }, 0.4);
    return tl;
  };

  // Intro: the C-mark assembles from its three arcs, the wordmark resolves, the panel wipes up. Ends by 1.75 s.
  const playIntro = (panel, hero) => {
    const tl = gsap.timeline({ onComplete: endIntro });
    tl.from($$('.intro-mark path', panel), { rotation: index => [-70, 60, -60][index % 3], svgOrigin: '100 100', opacity: 0, duration: 0.7, stagger: 0.1, ease: 'power4.out' }, 0.05)
      .from($$('.intro-word > span', panel), { yPercent: 110, duration: 0.55, ease: 'power4.out' }, 0.45)
      .fromTo(panel, { clipPath: 'inset(0 0 0% 0)' }, { clipPath: 'inset(0 0 100% 0)', duration: 0.7, ease: 'power4.inOut' }, 1.05)
      .add(() => hero.play(0), 1.3);
    onSkip = () => {
      tl.progress(1);
      hero.progress(1);
      endIntro();
    };
    SKIP_EVENTS.forEach(type => window.addEventListener(type, onSkip, { passive: true }));
    return tl;
  };

  mm.add('(prefers-reduced-motion: reduce)', endIntro);
  mm.add(MOTION, () => {
    const hero = heroTimeline();
    const panel = doc.querySelector('.intro');
    const onTime = !window.performance || window.performance.now() <= INTRO_LATEST_START_MS;
    if (panel && onTime && root.classList.contains('ns-intro')) playIntro(panel, hero);
    else {
      endIntro();
      hero.play(0);
    }
    return endIntro;
  });

  // Concept projects, large screens: one capped pinned sequence. Each photo wipes up, the caption swaps quickly mid-wipe
  // and the devices hand over and rise into place; a 1-3 counter tracks the project. The visitor's scroll is never moved for them.
  mm.add(PIN_QUERY, () => {
    const stage = doc.querySelector('[data-work]');
    const projects = stage ? $$('.proj', stage) : [];
    const count = projects.length;
    if (count < 2) return undefined;
    const counter = stage.querySelector('.work-count-n');
    const bar = stage.querySelector('.work-count-bar i');
    let shown = 0;
    const show = index => {
      if (index === shown) return;
      shown = index;
      if (counter) counter.textContent = String(index + 1);
      if (bar) gsap.set(bar, { scaleX: (index + 1) / count });
    };
    stage.classList.add('is-pinned');
    if (bar) gsap.set(bar, { scaleX: 1 / count, transformOrigin: '0 50%' });
    const tl = gsap.timeline({
      defaults: { ease: 'power3.inOut' },
      scrollTrigger: {
        trigger: stage, pin: true, start: 'top top', scrub: 0.6, invalidateOnRefresh: true,
        end: () => '+=' + Math.round(window.innerHeight * PIN_VIEWPORTS),
        onUpdate: self => show(Math.min(count - 1, Math.round(self.progress * (count - 1)))),
      },
    });
    tl.addLabel('p0', 0);
    for (let index = 1; index < count; index++) {
      const previous = projects[index - 1];
      const current = projects[index];
      const at = (index - 1) * 1.2;
      const copy = $$('.proj-copy > *', current);
      const devices = $$('.proj-devices', current);
      gsap.set($$('.proj-media', current), { clipPath: 'inset(100% 0 0 0)' });
      gsap.set(copy, { opacity: 0, y: 16 });
      gsap.set(devices, { opacity: 0, y: 140, rotation: 2.5, transformOrigin: '50% 100%' });
      // One quick text swap mid-wipe (each side 0.18 units, a 0.02 overlap) so one project's text is always on screen,
      // and the devices hand over back to back, so two laptops never share the frame.
      tl.to($$('.proj-copy > *', previous), { opacity: 0, y: -16, stagger: 0.02, duration: 0.12, ease: 'power2.in' }, at + 0.3)
        .to($$('.proj-devices', previous), { opacity: 0, y: -110, duration: 0.35, ease: 'power2.in' }, at + 0.05)
        .to($$('.proj-media', current), { clipPath: 'inset(0% 0 0 0)', duration: 0.8 }, at + 0.1)
        .fromTo($$('.proj-media img', current), { scale: 1.1 }, { scale: 1, duration: 0.9, ease: 'power2.out' }, at + 0.1)
        .to(copy, { opacity: 1, y: 0, stagger: 0.02, duration: 0.12, ease: 'power2.out' }, at + 0.46)
        .to(devices, { opacity: 1, y: 0, rotation: 0, duration: 0.55, ease: 'power3.out' }, at + 0.4)
        .addLabel('p' + index, at + 1);
    }
    tl.to({}, { duration: 0.3 });
    // Keyboard focus entering a project scrolls the page to the point where that project is fully shown.
    const onFocus = event => {
      const index = projects.findIndex(project => project.contains(event.target));
      const trigger = tl.scrollTrigger;
      if (index < 0 || !trigger) return;
      const at = tl.labels['p' + index] / tl.duration();
      window.scrollTo(0, Math.round(trigger.start + (trigger.end - trigger.start) * at));
    };
    stage.addEventListener('focusin', onFocus);
    return () => {
      stage.removeEventListener('focusin', onFocus);
      stage.classList.remove('is-pinned');
    };
  });

  // Concept projects, smaller screens: stacked, each photo un-masks and its devices rise once as it scrolls in.
  mm.add(STACK_QUERY, () => {
    $$('.proj').forEach(project => {
      const tl = gsap.timeline({ scrollTrigger: { trigger: project, start: 'top 80%', once: true } });
      const media = $$('.proj-media', project);
      const devices = $$('.proj-devices', project);
      if (media.length) tl.fromTo(media, { clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0% 0)', duration: 1, ease: 'expo.inOut', clearProps: 'clipPath' }, 0);
      if (devices.length) tl.from(devices, { y: 60, opacity: 0, duration: 0.8, ease: 'power3.out' }, 0.4);
    });
  });
})();
