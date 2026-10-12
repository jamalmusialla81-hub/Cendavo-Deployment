/* Cendavo — Daylight. Loaded in <head> without defer:
   1) sets .js / .js-motion before first paint (with a 3 s failsafe),
   2) on DOMContentLoaded (after the deferred GSAP files) wires the menu, showreel, compare slider and motion.
   Every hidden-for-intro state is CSS gated by .js-motion and then handed to GSAP; without JS or with reduced motion
   the page is complete and static. */
(function () {
  'use strict';
  var root = document.documentElement;
  var mqMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: no-preference)') : null;
  var motionOK = !!(mqMotion && mqMotion.matches);
  root.classList.add('js');
  if (motionOK) root.classList.add('js-motion');
  var failsafe = setTimeout(function () { root.classList.remove('js-motion'); }, 3000);

  function $(s, c) { return (c || document).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  function fmt(t) { t = Math.max(0, Math.floor(t || 0)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); }

  document.addEventListener('DOMContentLoaded', function () {
    initMenu();
    initReel();
    initCompare();
    if (motionOK && window.gsap && window.ScrollTrigger) {
      clearTimeout(failsafe);
      initMotion();
    } else {
      clearTimeout(failsafe);
      root.classList.remove('js-motion');
    }
  });

  /* ---------------- menu ---------------- */
  function initMenu() {
    var btn = $('.menu-btn'), nav = $('#site-nav');
    if (!btn || !nav) return;
    btn.hidden = false;
    var label = $('.menu-label', btn);
    function set(open) {
      nav.classList.toggle('open', open);
      btn.setAttribute('aria-expanded', String(open));
      if (label) label.textContent = open ? 'Close' : 'Menu';
      document.body.style.overflow = open ? 'hidden' : '';
      if (open) { var first = $('a', nav); if (first) first.focus(); }
    }
    btn.addEventListener('click', function () { set(btn.getAttribute('aria-expanded') !== 'true'); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && btn.getAttribute('aria-expanded') === 'true') { set(false); btn.focus(); }
    });
    $$('a', nav).forEach(function (a) { a.addEventListener('click', function () { set(false); }); });
    window.addEventListener('resize', function () { if (window.innerWidth > 900 && nav.classList.contains('open')) set(false); });
  }

  /* ---------------- showreel with chapters ---------------- */
  function initReel() {
    var fig = $('[data-reel]');
    if (!fig) return;
    var video = $('video', fig), ui = $('[data-reel-ui]', fig), play = $('[data-reel-play]', fig);
    var fill = $('.reel-fill', fig), time = $('.reel-time', fig);
    var chapters = $$('[data-chapters] button');
    var marks = chapters.map(function (b) { return parseFloat(b.dataset.t); });
    var saveData = navigator.connection && navigator.connection.saveData;

    if (window.matchMedia && window.matchMedia('(max-width: 640px)').matches) {
      var src = $('source', video);
      src.setAttribute('src', 'assets/video/cendavo-showreel-vertical-720.mp4');
      video.setAttribute('poster', 'assets/video/cendavo-showreel-vertical-poster-720.jpg');
      video.load();
    }
    video.muted = true;
    video.removeAttribute('controls');
    ui.hidden = false;

    var wanted = motionOK && !saveData; // autoplay in view only when motion is welcome
    var inView = false, pendingSeek = null, raf = 0;

    function label() {
      var p = !video.paused;
      play.textContent = (p ? 'Pause' : 'Play') + ' showreel';
      play.classList.toggle('is-playing', p);
    }
    function doPlay() { var r; try { r = video.play(); } catch (e) { r = null; } if (r && r.then) r.then(label, label); label(); }
    function paint() {
      var d = video.duration || 20, t = video.currentTime || 0;
      fill.style.transform = 'scaleX(' + (t / d) + ')';
      time.textContent = fmt(t) + ' / ' + fmt(d);
      var idx = 0;
      for (var i = 0; i < marks.length; i++) if (t >= marks[i] - 0.05) idx = i;
      chapters.forEach(function (b, i) {
        var on = i === idx;
        if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
        var start = marks[i], end = marks[i + 1] || d;
        var p = on ? Math.min(1, Math.max(0, (t - start) / (end - start))) : (i < idx ? 0 : 0);
        b.querySelector('.ch-bar').style.transform = 'scaleX(' + p + ')';
      });
    }
    function loop() { paint(); if (!video.paused) raf = requestAnimationFrame(loop); }
    video.addEventListener('play', function () { label(); cancelAnimationFrame(raf); raf = requestAnimationFrame(loop); });
    video.addEventListener('pause', function () { label(); paint(); });
    video.addEventListener('seeked', paint);
    video.addEventListener('loadedmetadata', function () {
      if (pendingSeek !== null) { video.currentTime = pendingSeek; pendingSeek = null; }
      paint();
    });
    play.addEventListener('click', function () {
      wanted = video.paused;
      if (wanted) doPlay(); else video.pause();
    });
    chapters.forEach(function (b) {
      b.addEventListener('click', function () {
        var t = parseFloat(b.dataset.t);
        if (video.readyState < 1) { pendingSeek = t; } else { video.currentTime = t; }
        wanted = true;
        doPlay();
        paint();
      });
    });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) {
        inView = es[es.length - 1].isIntersecting;
        if (inView && wanted && video.paused) doPlay();
        else if (!inView && !video.paused) video.pause();
      }, { threshold: 0.35 }).observe(video);
    }
    chapters[0].setAttribute('aria-current', 'true');
    label();
  }

  /* ---------------- before / after ---------------- */
  var compareApi = null;
  function initCompare() {
    var fig = $('[data-compare]');
    if (!fig) return;
    var range = $('[data-compare-range]', fig), stage = $('.cmp-stage', fig), controls = $('[data-compare-controls]', fig);
    controls.hidden = false;
    var touched = false;
    function set(v) { v = Math.max(0, Math.min(100, v)); fig.style.setProperty('--pos', v + '%'); range.value = Math.round(v); }
    range.addEventListener('input', function () { touched = true; set(+range.value); });
    var dragging = false;
    function fromEvent(e) { var r = stage.getBoundingClientRect(); set(((e.clientX - r.left) / r.width) * 100); }
    stage.addEventListener('pointerdown', function (e) { touched = true; dragging = true; stage.setPointerCapture(e.pointerId); fromEvent(e); });
    stage.addEventListener('pointermove', function (e) { if (dragging) fromEvent(e); });
    stage.addEventListener('pointerup', function () { dragging = false; });
    stage.addEventListener('pointercancel', function () { dragging = false; });
    compareApi = { set: set, touched: function () { return touched; }, fig: fig };
  }

  /* ---------------- motion ----------------
     Clean motion system. Two curves, four durations, short travel, masks over flies.
       IN  = cubic-bezier(.2,.8,.2,1)  entrances
       IO  = cubic-bezier(.7,0,.2,1)   transitions between states
       D   = 0.2 / 0.4 / 0.7 / 1.0 s
     Stagger 40–80 ms. Travel 8–40 px. No elastic, no bounce, no wobble, no decorative rotation.
     Depth: two layers only (devices, fragments). */
  function bezier(x1, y1, x2, y2) {
    // cubic-bezier easing (same maths as CSS); Newton–Raphson with bisection fallback
    function a(p1, p2) { return 1 - 3 * p2 + 3 * p1; }
    function b(p1, p2) { return 3 * p2 - 6 * p1; }
    function c(p1) { return 3 * p1; }
    function calc(t, p1, p2) { return ((a(p1, p2) * t + b(p1, p2)) * t + c(p1)) * t; }
    function slope(t, p1, p2) { return 3 * a(p1, p2) * t * t + 2 * b(p1, p2) * t + c(p1); }
    function tForX(x) {
      var t = x;
      for (var i = 0; i < 6; i++) { var s = slope(t, x1, x2); if (Math.abs(s) < 1e-6) break; t -= (calc(t, x1, x2) - x) / s; }
      if (t < 0 || t > 1 || Math.abs(calc(t, x1, x2) - x) > 1e-4) {
        var lo = 0, hi = 1; t = x;
        for (var j = 0; j < 20; j++) { var v = calc(t, x1, x2); if (Math.abs(v - x) < 1e-5) break; if (v < x) lo = t; else hi = t; t = (lo + hi) / 2; }
      }
      return t;
    }
    return function (x) { return x <= 0 ? 0 : x >= 1 ? 1 : calc(tForX(x), y1, y2); };
  }
  var IN = bezier(0.2, 0.8, 0.2, 1), IO = bezier(0.7, 0, 0.2, 1);
  var D = { xs: 0.2, s: 0.4, m: 0.7, l: 1.0 };

  function initMotion() {
    var gsap = window.gsap, ST = window.ScrollTrigger;
    gsap.registerPlugin(ST);
    gsap.defaults({ ease: IN, duration: D.m });
    var mm = gsap.matchMedia();

    // Only the motion preference re-runs this context; pointer type and width are read once, so a resize never replays the intro.
    mm.add('(prefers-reduced-motion: no-preference)', function () {
      var fine = window.matchMedia('(pointer: fine)').matches, wide = window.matchMedia('(min-width: 641px)').matches;

      var lines = $$('.kin .lt');
      var fades = $$('[data-hero-fade]');
      var rig = $('.rig'), laptop = $('.laptop'), phone = $('.phone'), cap = $('.rig-cap'), plinth = $('.plinth');
      var fSpeed = $('.frag-speed'), fEnq = $('.frag-enq'), fBook = $('.frag-book'), fDev = $('.frag-dev');
      var cursor = $('.cursor'), slot = $('.slot-pick'), bookBtn = $('.book-btn');
      var ringFg = $('.ring-fg'), ringNum = $('[data-count]');
      var frags = [fSpeed, fEnq, fBook, fDev];

      /* hand the hidden intro states from CSS to GSAP, then drop the CSS gate */
      gsap.set(lines, { y: 0, yPercent: 102, '--w': 72 }); // y:0 clears the px value GSAP parses from the CSS gate
      gsap.set(fades, { opacity: 0, y: 12 });
      gsap.set([laptop, phone, cap].concat(frags), { opacity: 0 });
      gsap.set(plinth, { clipPath: 'inset(0% 0% 0% 100% round 3.2em)' });
      fBook.classList.remove('booked'); slot.classList.remove('on');
      gsap.set(['.bt-b', '.bb-b'], { opacity: 0 }); gsap.set(['.bt-a', '.bb-a'], { opacity: 1 });
      gsap.set(ringFg, { strokeDashoffset: 100 });
      ringNum.textContent = '0';
      fDev.classList.remove('is-desktop');
      gsap.set('.dev svg', { opacity: 0, scale: 0.6 });
      gsap.set('.shots', { clipPath: 'inset(0% 0% 100% 0%)' });
      root.classList.remove('js-motion');

      /* 1. type composes: masked lines rise and the width axis settles from condensed to set width */
      var counter = { v: 0 };
      var intro = gsap.timeline({ delay: 0.1 });
      intro
        .to(lines, { yPercent: 0, duration: D.l, stagger: 0.08 }, 0)
        .to(lines, { '--w': 84, duration: D.l, stagger: 0.08, ease: IO }, 0.1)
        .to(fades, { opacity: 1, y: 0, duration: D.m, stagger: 0.08 }, 0.55)
      /* 2. the stage is laid down: plinth wipes in, devices arrive a short distance, the screen unmasks */
        .to(plinth, { clipPath: 'inset(0% 0% 0% 0% round 3.2em)', duration: D.l, ease: IO }, 0.2)
        .fromTo(laptop, { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: D.l }, 0.45)
        .fromTo(phone, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: D.l }, 0.55)
        .to('.shots', { clipPath: 'inset(0% 0% 0% 0%)', duration: D.m, ease: IO }, 0.9)
      /* 3. interface fragments assemble, one at a time */
        .fromTo(fSpeed, { opacity: 0, scale: 0.96, y: 8 }, { opacity: 1, scale: 1, y: 0, duration: D.s }, 1.2)
        .to(ringFg, { strokeDashoffset: 0, duration: D.l, ease: IO }, 1.3)
        .to(counter, { v: 100, duration: D.l, ease: IO, onUpdate: function () { ringNum.textContent = Math.round(counter.v); } }, 1.3)
        .fromTo(fEnq, { opacity: 0, scale: 0.96, x: 16 }, { opacity: 1, scale: 1, x: 0, duration: D.s }, 1.42)
        .fromTo(fBook, { opacity: 0, scale: 0.96, y: 8 }, { opacity: 1, scale: 1, y: 0, duration: D.s }, 1.5)
        .fromTo(fDev, { opacity: 0, scale: 0.96, y: 8 }, { opacity: 1, scale: 1, y: 0, duration: D.s }, 1.58)
        .to(cap, { opacity: 1, duration: D.s }, 1.6);

      /* 4. the toggle actually toggles: Mobile is checked, the thumb slides, Desktop is checked */
      intro
        .to('.dev-m svg', { opacity: 1, scale: 1, duration: D.xs }, 1.9)
        .call(function () { fDev.classList.add('is-desktop'); }, null, 2.25)
        .to('.dev-d svg', { opacity: 1, scale: 1, duration: D.xs }, 2.5);

      /* 5. the cursor glides on a curve (x and y on different curves), picks 10:30, books */
      function rel(el, fx, fy) {
        var r = el.getBoundingClientRect(), o = rig.getBoundingClientRect();
        return { x: r.left - o.left + r.width * fx, y: r.top - o.top + r.height * fy };
      }
      function press(target) {
        return gsap.timeline()
          .to(cursor, { scale: 0.88, duration: D.xs / 2, ease: IO })
          .to(cursor, { scale: 1, duration: D.xs, ease: IN })
          .fromTo(target, { scale: 0.96 }, { scale: 1, duration: D.xs, ease: IN }, 0);
      }
      function bookingDemo() {
        var tl = gsap.timeline();
        tl.set(cursor, { x: rig.offsetWidth * 0.86, y: rig.offsetHeight * 0.98, opacity: 0, scale: 1 })
          .to(cursor, { opacity: 1, duration: D.xs })
          .to(cursor, { x: function () { return rel(slot, 0.5, 0.6).x; }, duration: D.l, ease: IO }, '<')
          .to(cursor, { y: function () { return rel(slot, 0.5, 0.6).y; }, duration: D.l, ease: IN }, '<')
          .add(press(slot))
          .call(function () { slot.classList.add('on'); }, null, '<0.08')
          .to(cursor, { x: function () { return rel(bookBtn, 0.6, 0.62).x; }, duration: D.m, ease: IO }, '+=0.2')
          .to(cursor, { y: function () { return rel(bookBtn, 0.6, 0.62).y; }, duration: D.m, ease: IN }, '<')
          .add(press(bookBtn))
          .call(function () { fBook.classList.add('booked'); }, null, '<0.08')
          .to(['.bt-a', '.bb-a'], { opacity: 0, y: -6, duration: D.xs, ease: IO }, '<')
          .fromTo(['.bt-b', '.bb-b'], { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: D.s }, '<0.08')
          .to(cursor, { x: '+=24', y: '+=20', opacity: 0, duration: D.s, ease: IO }, '+=0.4');
        return tl;
      }
      intro.add(bookingDemo(), 2.6);

      /* ambient: the concept sites change every few seconds with a masked wipe. Pausable (WCAG 2.2.2). */
      var sites = [
        ['Harbourside Mobile Detailing', 'harbourside-detailing.example'],
        ['Greenline Landscapes', 'greenline-landscapes.example'],
        ['Fade & Co', 'fadeandco.example']
      ];
      var lapShots = $$('.screen .shot'), phShots = $$('.phone .shot');
      var urlEl = $('[data-url]'), capName = $('[data-cap-name]');
      var cur = 0;
      function swap() {
        var next = (cur + 1) % sites.length;
        var lo = lapShots[cur], ln = lapShots[next], po = phShots[cur], pn = phShots[next];
        gsap.set([ln, pn], { zIndex: 2, opacity: 1 });
        gsap.set([lo, po], { zIndex: 1 });
        return gsap.timeline()
          .fromTo(ln, { clipPath: 'inset(0% 0% 0% 100%)' }, { clipPath: 'inset(0% 0% 0% 0%)', duration: D.l, ease: IO }, 0)
          .fromTo(pn, { clipPath: 'inset(100% 0% 0% 0%)' }, { clipPath: 'inset(0% 0% 0% 0%)', duration: D.l, ease: IO }, 0.08)
          .to([capName, urlEl], { opacity: 0, y: -6, duration: D.xs, ease: IO }, 0.2)
          .call(function () { capName.textContent = sites[next][0]; urlEl.textContent = sites[next][1]; }, null, 0.42)
          .fromTo([capName, urlEl], { y: 6 }, { opacity: 1, y: 0, duration: D.s, stagger: 0.04 }, 0.44)
          .call(function () { gsap.set([lo, po], { opacity: 0, zIndex: 0 }); lo.classList.remove('is-on'); po.classList.remove('is-on'); ln.classList.add('is-on'); pn.classList.add('is-on'); cur = next; });
      }
      var cycleTimer = null, playing = false, userPaused = false, heroVisible = true;
      function scheduleSwap() { cycleTimer = gsap.delayedCall(5, function () { swap(); scheduleSwap(); }); }
      function setAmbient(on) { if (cycleTimer) { if (on) cycleTimer.resume(); else cycleTimer.pause(); } }
      intro.call(function () {
        scheduleSwap(); playing = true;
        var btn = $('[data-motion-toggle]');
        btn.hidden = false;
        gsap.fromTo(btn, { opacity: 0 }, { opacity: 1, duration: D.s });
        btn.addEventListener('click', function () {
          userPaused = !userPaused;
          btn.setAttribute('aria-pressed', String(userPaused));
          btn.textContent = userPaused ? 'Play motion' : 'Pause motion';
          setAmbient(!userPaused && heroVisible);
        });
      });

      /* scroll: two depth layers only. Devices drift up a little; fragments a little more. The headline narrows as it leaves. */
      ST.create({ trigger: '.hero', start: 'top top', end: 'bottom top', onToggle: function (s) { heroVisible = s.isActive || window.scrollY < 10; if (playing) setAmbient(heroVisible && !userPaused); } });
      var heroScrub = { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: 0.4 };
      gsap.to(rig, { '--ty': wide ? '-40px' : '-16px', ease: 'none', scrollTrigger: heroScrub });
      gsap.to(frags, { '--py': wide ? '-40px' : '-16px', ease: 'none', scrollTrigger: heroScrub });
      gsap.to(lines, { '--sw': -12, ease: 'none', scrollTrigger: heroScrub });

      /* pointer: fragments shift up to 8px toward the pointer; nothing rotates */
      if (fine) {
        var hero = $('.hero');
        var pxTo = frags.map(function (f) { return gsap.quickTo(f, '--px', { duration: D.m, ease: IN }); });
        hero.addEventListener('pointermove', function (e) {
          var r = hero.getBoundingClientRect(), nx = (e.clientX - r.left) / r.width - 0.5;
          pxTo.forEach(function (q) { q(nx * 16); });
        });
        hero.addEventListener('pointerleave', function () { pxTo.forEach(function (q) { q(0); }); });
      }

      /* the page composes as you arrive: section headings unmask, media opens from a hairline inset */
      $$('.h2').forEach(function (h) {
        gsap.fromTo(h, { clipPath: 'inset(0% 0% 100% 0%)', y: 16 }, { clipPath: 'inset(0% 0% -10% 0%)', y: 0, duration: D.l, scrollTrigger: { trigger: h, start: 'top 88%', once: true } });
      });
      $$('.card').forEach(function (card, i) {
        var media = $('.card-media', card), img = $('.card-photo', card), body = $$('.card-body > *', card);
        var tl = gsap.timeline({ scrollTrigger: { trigger: '.cards', start: 'top 82%', once: true }, delay: i * 0.08 });
        tl.fromTo(media, { clipPath: 'inset(6% 6% 6% 6% round 14px)' }, { clipPath: 'inset(0% 0% 0% 0% round 14px)', duration: D.l, ease: IO })
          .fromTo(img, { scale: 1.06 }, { scale: 1, duration: D.l, clearProps: 'transform' }, 0)
          .fromTo(body, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: D.m, stagger: 0.06 }, 0.3);
      });
      $$('.chapters li').forEach(function (li, i) {
        gsap.fromTo(li, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: D.s, delay: i * 0.05, scrollTrigger: { trigger: '.chapters', start: 'top 85%', once: true } });
      });
      gsap.fromTo('.reel-frame', { clipPath: 'inset(4% 4% 4% 4% round 18px)' }, { clipPath: 'inset(0% 0% 0% 0% round 18px)', duration: D.l, ease: IO, scrollTrigger: { trigger: '.reel-frame', start: 'top 85%', once: true } });
      gsap.fromTo('.cmp-frame', { clipPath: 'inset(4% 4% 4% 4% round 14px)' }, { clipPath: 'inset(0% 0% 0% 0% round 14px)', duration: D.l, ease: IO, scrollTrigger: { trigger: '.cmp-frame', start: 'top 85%', once: true } });

      /* before/after: one demonstration sweep the first time it is seen */
      if (compareApi) {
        var pos = { v: 50 };
        ST.create({
          trigger: compareApi.fig, start: 'top 65%', once: true,
          onEnter: function () {
            if (compareApi.touched()) return;
            gsap.timeline({ delay: 0.4, onUpdate: function () { if (!compareApi.touched()) compareApi.set(pos.v); } })
              .to(pos, { v: 82, duration: D.l, ease: IO })
              .to(pos, { v: 18, duration: D.l, ease: IO }, '+=0.2')
              .to(pos, { v: 50, duration: D.m, ease: IO }, '+=0.2');
          }
        });
      }

      /* services: each vignette plays once as its column arrives; hovering a column replays it */
      function vigBuild(v) {
        var page = $('.vb-page', v);
        return gsap.timeline({ paused: true })
          .set($('.vb-done', v), { clipPath: 'inset(0% 100% 0% 0%)' })
          .set($('.vb-scan', v), { x: 0, opacity: 0 })
          .fromTo($$('.w', v), { opacity: 0, scale: 0.96 }, { opacity: 1, scale: 1, duration: D.s, stagger: 0.06 })
          .to($('.vb-scan', v), { opacity: 1, duration: D.xs }, '+=0.2')
          .to($('.vb-scan', v), { x: function () { return page.offsetWidth - 2; }, duration: D.l, ease: IO }, '<')
          .to($('.vb-done', v), { clipPath: 'inset(0% 0% 0% 0%)', duration: D.l, ease: IO }, '<')
          .to($('.vb-scan', v), { opacity: 0, duration: D.xs });
      }
      function vigRedo(v) {
        return gsap.timeline({ paused: true })
          .fromTo($('.vr-old', v), { x: 24, filter: 'saturate(1)', opacity: 1 }, { x: 0, filter: 'saturate(0.6)', opacity: 0.9, duration: D.m, ease: IO }, 0.2)
          .fromTo($('.vr-new', v), { clipPath: 'inset(0% 100% 0% 0% round 2cqw)' }, { clipPath: 'inset(0% 0% 0% 0% round 2cqw)', duration: D.l, ease: IO }, 0.5)
          .fromTo($$('.vr-copy > *', v), { y: 8, opacity: 0 }, { y: 0, opacity: 1, duration: D.s, stagger: 0.06 }, 0.9);
      }
      function vigCare(v) {
        var rows = $$('.log-list li', v);
        return gsap.timeline({ paused: true })
          .fromTo(rows, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: D.s, stagger: 0.08 })
          .fromTo($$('.log-list svg', v), { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: D.xs, stagger: 0.08 }, 0.2)
          .fromTo($$('.log-list time', v), { opacity: 0 }, { opacity: 1, duration: D.xs, stagger: 0.08 }, 0.25);
      }
      var makers = { build: vigBuild, redo: vigRedo, care: vigCare };
      $$('.svc-row').forEach(function (row, i) {
        var v = $('.vig', row), tl = makers[row.dataset.vig](v);
        tl.progress(0).pause();
        ST.create({ trigger: '.svc-list', start: 'top 75%', once: true, onEnter: function () { gsap.delayedCall(i * 0.08, function () { tl.play(0); }); } });
        row.addEventListener('pointerenter', function () { if (!tl.isActive() && tl.progress() === 1) tl.play(0); });
      });

      /* closing statement: the width axis opens as the band arrives (scrubbed, short range) */
      gsap.fromTo('.close-h .cl', { '--w': 78 }, { '--w': 96, ease: 'none', stagger: 0.04, scrollTrigger: { trigger: '.close', start: 'top 85%', end: 'center 60%', scrub: 0.4 } });

      /* footer wordmark widens to the edges */
      gsap.fromTo('[data-word]', { '--w': 84 }, { '--w': 116, ease: 'none', scrollTrigger: { trigger: '.ftr', start: 'top bottom', end: 'bottom bottom', scrub: 0.4 } });

      return function () { if (cycleTimer) cycleTimer.kill(); };
    });
  }
})();
