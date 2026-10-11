/* Cendavo — Night Shift shared behaviour + motion (ns.js)
   Everything works without GSAP; motion is layered on inside gsap.matchMedia(). */
(function () {
  'use strict';
  var d = document, root = d.documentElement;
  var $ = function (s, r) { return (r || d).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || d).querySelectorAll(s)); };
  var still = function () { return window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches; };

  /* ---------- Header: solid on scroll ---------- */
  var header = $('.site-header');
  var solidAlways = header && header.hasAttribute('data-solid');
  function onScroll() { if (header) header.classList.toggle('is-solid', solidAlways || window.scrollY > 24); }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* ---------- Mobile menu ---------- */
  var btn = $('.menu-btn'), menu = $('#menu');
  if (btn && menu) {
    var label = $('.menu-btn-label', btn);
    var setOpen = function (open, returnFocus) {
      btn.setAttribute('aria-expanded', String(open));
      if (label) label.textContent = open ? 'Close' : 'Menu';
      menu.hidden = !open;
      header.classList.toggle('is-open', open);
      d.body.classList.toggle('menu-open', open);
      if (open) { var first = $('a', menu); if (first) first.focus(); }
      else if (returnFocus) btn.focus();
    };
    btn.addEventListener('click', function () { setOpen(btn.getAttribute('aria-expanded') !== 'true', true); });
    menu.addEventListener('click', function (e) { if (e.target.closest('a')) setOpen(false, false); });
    d.addEventListener('keydown', function (e) {
      if (menu.hidden) return;
      if (e.key === 'Escape') { setOpen(false, true); return; }
      if (e.key === 'Tab') {
        var f = [btn].concat($$('a, button', menu));
        var i = f.indexOf(d.activeElement);
        if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
      }
    });
    window.addEventListener('resize', function () { if (window.innerWidth > 1080 && !menu.hidden) setOpen(false, false); });
  }

  /* ---------- Before / after comparison ---------- */
  var view = $('.cmp-view'), range = $('#cmp'), segs = $$('[data-cmp]');
  var cmpState = { v: 50 }, cmpTween = null;
  function setV(v) {
    v = Math.max(0, Math.min(100, v)); cmpState.v = v;
    view.style.setProperty('--v', v.toFixed(2));
    var r = Math.round(v);
    if (+range.value !== r) range.value = r;
    range.setAttribute('aria-valuetext', r + '% before shown on the left, ' + (100 - r) + '% after on the right');
    segs.forEach(function (b) { var t = +b.getAttribute('data-cmp'); b.setAttribute('aria-pressed', String(t === 100 ? v >= 99.5 : v <= .5)); });
  }
  function goTo(t) {
    if (cmpTween) cmpTween.kill();
    if (window.gsap && !still()) cmpTween = gsap.to(cmpState, { v: t, duration: .8, ease: 'expo.inOut', onUpdate: function () { setV(cmpState.v); } });
    else setV(t);
  }
  if (view && range) {
    range.addEventListener('input', function () { if (cmpTween) cmpTween.kill(); setV(+range.value); });
    segs.forEach(function (b) { b.addEventListener('click', function () { goTo(+b.getAttribute('data-cmp')); }); });
    setV(50);
  }

  /* ---------- Services: photo follows hovered / focused row ---------- */
  var svcs = $$('.svc'), svcImgs = $$('.svc-img');
  function setSvc(i) {
    svcs.forEach(function (s, k) { s.classList.toggle('is-active', k === i); });
    svcImgs.forEach(function (s, k) { s.classList.toggle('is-active', k === i); });
  }
  svcs.forEach(function (s, i) {
    s.addEventListener('mouseenter', function () { setSvc(i); });
    s.addEventListener('focusin', function () { setSvc(i); });
  });

  /* ---------- Process rail state ---------- */
  var steps = $$('.rail-step');
  function railTo(p) { steps.forEach(function (s, i) { s.classList.toggle('is-on', p >= i / (steps.length - 1) - .02); }); }

  /* ---------- Intro bookkeeping ---------- */
  var intro = $('#intro');
  function endIntro() {
    root.classList.remove('ns-intro');
    try { sessionStorage.setItem('ns-intro', '1'); } catch (e) {}
  }

  /* ================= Motion (GSAP) ================= */
  if (!window.gsap || !window.ScrollTrigger) {
    endIntro(); root.classList.add('ns-ready'); railTo(1);
    return;
  }
  gsap.registerPlugin(ScrollTrigger);
  gsap.defaults({ ease: 'power3.out', duration: .9 });
  var mm = gsap.matchMedia();

  mm.add('(prefers-reduced-motion: reduce)', function () { endIntro(); railTo(1); });

  mm.add('(prefers-reduced-motion: no-preference)', function () {
    /* --- Hero (homepage only; inner pages animate their own heads in ns-pages.js) --- */
    var hero = gsap.timeline({ paused: true, defaults: { ease: 'power4.out' } });
    if ($('.hero-h')) hero.from('.hero-h .ln > span', { yPercent: 108, duration: 1.1, stagger: .08 }, 0)
        .fromTo('.hero-photo', { clipPath: 'inset(0 0 0 100%)' }, { clipPath: 'inset(0 0 0 0%)', duration: 1.4, ease: 'expo.inOut', clearProps: 'clipPath' }, 0)
        .from('.hero-photo img', { scale: 1.08, duration: 2, ease: 'power3.out' }, 0)
        .from('[data-hero-fade]', { y: 18, autoAlpha: 0, duration: .9, stagger: .1 }, .45)
        .from('[data-hero-device]', { y: 70, autoAlpha: 0, duration: 1.2 }, .6);
    root.classList.add('ns-ready');

    /* --- Intro (first visit per session) --- */
    if (root.classList.contains('ns-intro') && intro) {
      var skipBtn = $('.intro-skip', intro);
      var tl = gsap.timeline({ onComplete: function () { endIntro(); cleanup(); } });
      tl.from('.intro-mark .arc', { rotation: function (i) { return [-70, 60, -60][i]; }, svgOrigin: '100 100', autoAlpha: 0, duration: .9, stagger: .12, ease: 'power4.out' }, .1)
        .from('.intro-word span', { yPercent: 110, duration: .7, ease: 'power4.out' }, .55)
        .fromTo(intro, { clipPath: 'inset(0 0 0% 0)' }, { clipPath: 'inset(0 0 100% 0)', duration: .85, ease: 'power4.inOut' }, 1.5)
        .add(function () { hero.play(0); }, 1.75);
      var skip = function (e) { if (tl.progress() < 1) { if (e && e.type === 'keydown' && e.key !== 'Tab') e.preventDefault(); tl.progress(1); hero.progress(1); } };
      var cleanup = function () { ['keydown', 'pointerdown', 'wheel', 'touchstart'].forEach(function (t) { window.removeEventListener(t, skip); }); };
      ['keydown', 'pointerdown', 'wheel', 'touchstart'].forEach(function (t) { window.addEventListener(t, skip, { passive: t !== 'keydown' }); });
      if (skipBtn) skipBtn.addEventListener('click', skip);
    } else {
      endIntro();
      hero.play(0);
    }

    /* --- Section headings / paragraphs rise once --- */
    $$('[data-rise]').forEach(function (el) {
      gsap.from(el, { y: 28, autoAlpha: 0, duration: 1, scrollTrigger: { trigger: el, start: 'top 88%', once: true } });
    });

    /* --- Gentle photo parallax (±6%) --- */
    $$('.closing-media img, .who-img img').forEach(function (img) {
      gsap.fromTo(img, { yPercent: -6, scale: 1.14 }, { yPercent: 6, ease: 'none', scrollTrigger: { trigger: img.parentNode, start: 'top bottom', end: 'bottom top', scrub: true } });
    });

    /* --- Before/after: one hint sweep when it scrolls in --- */
    if (view) ScrollTrigger.create({ trigger: view, start: 'top 70%', once: true, onEnter: function () {
      if (cmpTween) cmpTween.kill();
      cmpTween = gsap.timeline({ onUpdate: function () { setV(cmpState.v); } })
        .to(cmpState, { v: 28, duration: .9, ease: 'power2.inOut', onUpdate: function () { setV(cmpState.v); } })
        .to(cmpState, { v: 50, duration: .9, ease: 'power2.inOut', onUpdate: function () { setV(cmpState.v); } });
    } });
  });

  /* --- Work: pinned sequence on large screens --- */
  mm.add('(prefers-reduced-motion: no-preference) and (min-width: 1081px) and (min-height: 620px)', function () {
    var stage = $('[data-work]'); if (!stage) return;
    var projs = $$('.proj', stage), n = projs.length;
    var countN = $('.work-count-n', stage), countBar = $('.work-count-bar i', stage);
    stage.classList.add('is-pinned');
    projs.forEach(function (p, i) { p.style.zIndex = i + 1; });

    var tl = gsap.timeline({
      defaults: { ease: 'power3.inOut', duration: 1 },
      scrollTrigger: {
        trigger: stage, pin: true, start: 'top top', end: function () { return '+=' + window.innerHeight * (n - 1) * 1.25; },
        scrub: .8, invalidateOnRefresh: true,
        snap: { snapTo: 'labelsDirectional', duration: { min: .3, max: .8 }, delay: .1, ease: 'power2.inOut' },
        onUpdate: function (self) {
          var i = Math.min(n - 1, Math.round(self.progress * (n - 1)));
          if (countN) countN.textContent = i + 1;
          if (countBar) countBar.style.transform = 'scaleX(' + ((i + 1) / n) + ')';
        }
      }
    });
    tl.addLabel('p0', 0);
    for (var i = 1; i < n; i++) {
      var prev = projs[i - 1], cur = projs[i], at = (i - 1) * 1.6 + .2;
      gsap.set($('.proj-media', cur), { clipPath: 'inset(100% 0 0 0)' });
      gsap.set($$('.proj-copy > *', cur), { autoAlpha: 0, y: 40 });
      gsap.set($('.proj-devices', cur), { autoAlpha: 0, y: 140, rotation: 2.5, transformOrigin: '50% 100%' });
      tl.to($$('.proj-copy > *', prev), { autoAlpha: 0, y: -30, stagger: .04, duration: .5 }, at)
        .to($('.proj-devices', prev), { autoAlpha: 0, y: -110, duration: .7 }, at)
        .to($('.proj-media', cur), { clipPath: 'inset(0% 0 0 0)', duration: 1 }, at + .1)
        .fromTo($('.proj-media img', cur), { scale: 1.1 }, { scale: 1, duration: 1.2, ease: 'power2.out' }, at + .1)
        .to($$('.proj-copy > *', cur), { autoAlpha: 1, y: 0, stagger: .05, duration: .6, ease: 'power3.out' }, at + .6)
        .to($('.proj-devices', cur), { autoAlpha: 1, y: 0, rotation: 0, duration: .9, ease: 'power3.out' }, at + .55)
        .addLabel('p' + i, at + 1.4);
    }
    tl.to({}, { duration: .3 });
    return function () { stage.classList.remove('is-pinned'); projs.forEach(function (p) { p.style.zIndex = ''; }); };
  });

  /* --- Work: stacked reveals on smaller screens --- */
  mm.add('(prefers-reduced-motion: no-preference) and (max-width: 1080px), (prefers-reduced-motion: no-preference) and (max-height: 619px)', function () {
    $$('.proj').forEach(function (p) {
      var t = gsap.timeline({ scrollTrigger: { trigger: p, start: 'top 80%', once: true } });
      t.fromTo($('.proj-media', p), { clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0% 0)', duration: 1.1, ease: 'expo.inOut' })
       .from($('.proj-devices', p), { y: 60, autoAlpha: 0, duration: 1 }, .45);
    });
  });

  /* --- Process rail fills on scroll (axis handled in CSS via --p) --- */
  mm.add('(prefers-reduced-motion: no-preference)', function () {
    var rail = $('[data-rail]'), line = $('.rail-line'); if (!rail || !line) return;
    var set = function (p) { line.style.setProperty('--p', p.toFixed(4)); railTo(p); };
    set(0);
    ScrollTrigger.create({ trigger: rail, start: 'top 72%', end: 'bottom 58%', scrub: true, onUpdate: function (st) { set(st.progress); }, onRefresh: function (st) { set(st.progress); } });
    return function () { line.style.removeProperty('--p'); railTo(1); };
  });

  window.addEventListener('load', function () { ScrollTrigger.refresh(); });
})();
