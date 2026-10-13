// Daylight inner-page scroll scenes (Task 34, from docs/design/daylight/prototype/pages.js), loaded after motion.js on Work,
// Services, Pricing and About only (the homepage does not need them). Each scene plays once as it scrolls in, only for
// people who have not asked for reduced motion, and only below the fold; without this script, GSAP or motion everything
// shows in its final state. Only transform, opacity and clip-path animate, with the plan's two curves and durations.
(() => {
  // Task 55: kept compact. The inner pages carry at most 30 KB of first-party script, and they sit right at that limit.
  const { gsap, ScrollTrigger } = window;
  if (!gsap || !ScrollTrigger) return;
  const $$ = (selector, scope) => Array.from((scope || document).querySelectorAll(selector));
  // The two Daylight curves (CSS cubic-bezier, x solved by bisection): entrances, and changes of state.
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
  const SHOWN = 'opacity,transform';
  // fromTo pairs: rise y px into place; un-mask a clip-path to the full frame.
  const up = (y, duration, stagger) => [{ opacity: 0, y }, { opacity: 1, y: 0, duration, stagger: stagger || 0, clearProps: SHOWN }];
  const unmask = (from, duration) => [{ clipPath: from }, { clipPath: 'inset(0% 0% 0% 0%)', duration, ease: IO, clearProps: 'clipPath' }];
  // ...and draw a line from nothing (scaleX: 0, or scaleY: 0 for an upright one) to full size.
  const grow = (from, duration, stagger) => [from, { scaleX: 1, scaleY: 1, duration, stagger, ease: IO, clearProps: 'transform' }];
  const later = list => list.filter(item => item.getBoundingClientRect().top >= window.innerHeight);
  // Task 43: every scene starts as its trigger's top crosses 85% of the viewport, like the reveals in motion.js. Each plays
  // once (Pause motion, in glass.js, ends any such scene at once); "more" adds trigger options, such as a scrub.
  const START = 'top 85%';
  const tl = (trigger, more) => gsap.timeline({ defaults: { ease: IN }, scrollTrigger: { trigger, start: START, once: true, ...more } });
  gsap.registerPlugin(ScrollTrigger);

  gsap.matchMedia().add('(prefers-reduced-motion: no-preference)', () => {
    const restore = [];
    // Work benches: the plinth opens, the devices arrive, the cards assemble, then each card shows its state change (a
    // suburb picked, a booking confirmed, a time booked). The cards end as they ship.
    later($$('[data-bench]')).forEach(bench => {
      const cues = $$('[data-cue]', bench);
      const states = cues.map(cue => ['on', 'done'].filter(name => cue.classList.contains(name)));
      const set = (cue, at) => states[at].forEach(name => cue.classList.add(name));
      cues.forEach((cue, at) => states[at].forEach(name => cue.classList.remove(name)));
      restore.push(() => cues.forEach(set));
      const t = tl(bench)
        .fromTo($$('.bench-plinth', bench), ...unmask('inset(0% 0% 0% 100%)', 1), 0)
        .fromTo($$('.d-lap', bench), ...up(32, 1), 0.15)
        .fromTo($$('.d-ph', bench), ...up(40, 1), 0.25)
        .fromTo($$('.ui', bench), ...up(8, 0.4, 0.08), 0.8);
      cues.forEach((cue, at) => {
        const when = 1.3 + at * 0.4;
        t.add(() => set(cue, at), when)
          .fromTo(cue, { opacity: 0.4, scale: 0.96 }, { opacity: 1, scale: 1, duration: 0.4, clearProps: SHOWN }, when);
      });
    });

    // Sequences draw their line once (Services steps, Pricing timeline), then the steps follow.
    later($$('[data-line]')).forEach(wrap => {
      const fill = $$('[data-line-fill]', wrap);
      const box = fill[0]?.getBoundingClientRect();
      tl(wrap)
        .fromTo(fill, ...grow(box?.height > box?.width ? { scaleY: 0 } : { scaleX: 0 }, 1), 0)
        .fromTo($$('li', wrap), ...up(12, 0.7, 0.08), 0.1);
    });

    // Pricing: what-affects scales draw from the left.
    later($$('.scale i')).forEach(line => tl(line).fromTo(line, ...grow({ scaleX: 0 }, 1), 0));

    // Services, Task 55: the New website page builds up as the vignette crosses the screen, scrubbed by scroll (nothing
    // pinned): step N's layers (data-step-layer="N": plan, type, photo, service line, button, then the cream page and the
    // phone) rise in over the Nth sixth. It plays once, so Pause motion ends it built, and reduced motion reverts it to
    // the finished page the stylesheet draws. The visible list after it names the six steps; the one being built is
    // aria-current="step" (services.css underlines it), none once it is built or reverted.
    later($$('[data-build]')).forEach(vig => {
      const steps = $$('li', vig.nextElementSibling);
      const t = tl(vig, { end: 'bottom 40%', scrub: 0.5 }).eventCallback('onUpdate', () => steps.forEach((li, i) => {
        li.ariaCurrent = i === Math.floor(t.progress() * 6) ? 'step' : null;
      }));
      $$('[data-step-layer]', vig).forEach(layer => t.fromTo(layer, ...up(16, 1), layer.dataset.stepLayer - 1));
      restore.push(() => steps.forEach(li => { li.ariaCurrent = null; }));
    });
    // Task 43: the white card itself rises with its rows, so it never stands empty below them while it scrolls in.
    later($$('[data-month]')).forEach(card => {
      tl(card)
        .fromTo(card, ...up(24, 0.6), 0)
        .fromTo($$('li', card), ...up(8, 0.4, 0.08), 0.1)
        .fromTo($$('.box', card), { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.4, stagger: 0.08, clearProps: SHOWN }, 0.4);
    });
    later($$('[data-redir]')).forEach(map => {
      tl(map)
        .fromTo(map, ...up(24, 0.6), 0)
        .fromTo($$('li', map), ...up(8, 0.4, 0.08), 0.1)
        .fromTo($$('.arr', map), ...grow({ scaleX: 0 }, 0.7, 0.08), 0.4);
    });

    // Work: the illustrated queue fills, one request is picked up and its reply draft appears (classes only).
    later($$('[data-queue]')).forEach(queue => {
      const cue = $$('[data-cue]', queue);
      tl(queue)
        .fromTo($$('.q-card', queue), ...up(8, 0.4, 0.06), 0)
        .add(() => cue.forEach(card => card.classList.add('is-cued')), 0.9)
        .fromTo($$('.q-draft', queue), ...up(8, 0.4), 1.3)
        .add(() => cue.forEach(card => card.classList.remove('is-cued')), 2.3);
    });

    // About: the film frame opens from a slightly inset window.
    later($$('.film-frame')).forEach(frame => tl(frame).fromTo(frame, ...unmask('inset(3% 3% 3% 3%)', 1), 0));

    // Reduced motion switched on mid-visit: GSAP reverts the tweens; the cards get their finished states back.
    return () => restore.forEach(fn => fn());
  });

  // Task 54 (owner): Work tiles lean toward a fine pointer, at most 6 degrees each way. Only --rx/--ry are set here; work.css
  // draws the lean (perspective 900px) under the same query. Never on keyboard focus or touch; flat on leave, on any move
  // while Pause motion is pressed, and when the query stops matching.
  const tiles = $$('.wk-tile');
  if (tiles.length) gsap.matchMedia().add('(prefers-reduced-motion: no-preference) and (hover: hover) and (pointer: fine)', () => {
    const deg = v => Math.max(-6, Math.min(6, v)) + 'deg';
    const clear = t => ['--rx', '--ry'].forEach(v => t.style.removeProperty(v));
    const leave = e => clear(e.currentTarget);
    const move = e => {
      const t = e.currentTarget, r = t.getBoundingClientRect();
      if (window.__glass?.paused) return clear(t);
      t.style.setProperty('--rx', deg(((e.clientY - r.top) / r.height - .5) * -8));
      t.style.setProperty('--ry', deg(((e.clientX - r.left) / r.width - .5) * 10));
    };
    const listen = m => tiles.forEach(t => { t[m]('pointermove', move); t[m]('pointerleave', leave); });
    listen('addEventListener');
    return () => { listen('removeEventListener'); tiles.forEach(clear); };
  });
})();
