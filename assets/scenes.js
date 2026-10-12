// Daylight inner-page scroll scenes (Task 34, from docs/design/daylight/prototype/pages.js), loaded after motion.js on Work,
// Services, Pricing and About only (the homepage does not need them). Each scene plays once as it scrolls in, only for
// people who have not asked for reduced motion, and only below the fold; without this script, GSAP or motion everything
// shows in its final state. Only transform, opacity and clip-path animate, with the plan's two curves and durations.
(() => {
  const gsap = window.gsap;
  const ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) return;
  const doc = document;
  const $$ = (selector, scope) => Array.from((scope || doc).querySelectorAll(selector));
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
  const later = list => list.filter(item => item.getBoundingClientRect().top >= window.innerHeight);
  // Task 43: every scene starts as its trigger's top crosses 85% of the viewport, like the reveals in motion.js.
  const START = 'top 85%';
  const tl = trigger => gsap.timeline({ defaults: { ease: IN }, scrollTrigger: { trigger, start: START, once: true } });
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
      const box = fill[0] ? fill[0].getBoundingClientRect() : null;
      tl(wrap)
        .fromTo(fill, box && box.height > box.width ? { scaleY: 0 } : { scaleX: 0 }, { scaleX: 1, scaleY: 1, duration: 1, ease: IO, clearProps: 'transform' }, 0)
        .fromTo($$('li', wrap), ...up(12, 0.7, 0.08), 0.1);
    });

    // Pricing: what-affects scales draw from the left.
    later($$('.scale i')).forEach(line => tl(line).fromTo(line, { scaleX: 0 }, { scaleX: 1, duration: 1, ease: IO, clearProps: 'transform' }, 0));

    // Services: the page plan turns into the finished page; the month list ticks in; old addresses connect to new ones.
    later($$('[data-build]')).forEach(vig => tl(vig).fromTo($$('.sb-done', vig), ...unmask('inset(0% 100% 0% 0%)', 1), 0.4));
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
        .fromTo($$('.arr', map), { scaleX: 0 }, { scaleX: 1, duration: 0.7, stagger: 0.08, ease: IO, clearProps: 'transform' }, 0.4);
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
})();
