/* Cendavo — Liquid Glass. Loaded in <head> without defer:
   1) sets .js / .js-motion before first paint (3 s failsafe), 2) on DOMContentLoaded wires everything.
   Without JS, or with reduced motion, every section is complete and static. Motion: expo/power3 out only. */
(function () {
  'use strict';
  var root = document.documentElement;
  var mq = function (q) { return window.matchMedia ? window.matchMedia(q).matches : false; };
  var motionOK = mq('(prefers-reduced-motion: no-preference)');
  var saveData = !!(navigator.connection && navigator.connection.saveData);
  root.classList.add('js');
  if (motionOK) root.classList.add('js-motion');
  var failsafe = setTimeout(function () { root.classList.remove('js-motion'); }, 3000);

  /* shared state read by the WebGL hero (gl-scene.js) */
  var G = window.__glass = window.__glass || { heroP: 0, paused: false, pointer: { x: 0, y: 0 }, motionOK: motionOK, saveData: saveData };

  function $(s, c) { return (c || document).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  function fmt(t) { t = Math.max(0, Math.floor(t || 0)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  document.addEventListener('DOMContentLoaded', function () {
    initMenu();
    initButtons();
    initGlassLight();
    initRefraction();
    initReel();
    initCompare();
    initVideos();
    initMotionToggle();
    /* inner pages: pages.js (the Daylight page motion) runs on these shared curves; it releases the failsafe itself */
    if (document.body && document.body.hasAttribute('data-page')) {
      window.Daylight = { IN: 'expo.out', IO: 'power3.inOut', D: { xs: 0.3, s: 0.5, m: 0.8, l: 1.2 }, motionOK: motionOK, release: function () { clearTimeout(failsafe); } };
      if (motionOK && window.gsap && window.ScrollTrigger) { window.gsap.registerPlugin(window.ScrollTrigger); initShell(window.gsap, window.ScrollTrigger); }
      else initHeaderStatic();
      return;
    }
    if (motionOK && window.gsap && window.ScrollTrigger) {
      clearTimeout(failsafe);
      initMotion();
    } else {
      clearTimeout(failsafe);
      root.classList.remove('js-motion');
      initHeaderStatic();
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
      if (open) { var first = $('a', nav); if (first) first.focus(); }
    }
    btn.addEventListener('click', function () { set(btn.getAttribute('aria-expanded') !== 'true'); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && btn.getAttribute('aria-expanded') === 'true') { set(false); btn.focus(); } });
    $$('a', nav).forEach(function (a) { a.addEventListener('click', function () { set(false); }); });
    window.addEventListener('resize', function () { if (window.innerWidth > 900 && nav.classList.contains('open')) set(false); });
  }
  function initHeaderStatic() {
    var hdr = $('[data-hdr]');
    var on = function () { hdr.classList.toggle('is-condensed', window.scrollY > 80); };
    window.addEventListener('scroll', on, { passive: true }); on();
  }

  /* ---------------- buttons: press light + magnetic pull ---------------- */
  function initButtons() {
    var fine = mq('(pointer: fine)');
    $$('.btn').forEach(function (b) {
      var p = document.createElement('i'); p.className = 'press'; p.setAttribute('aria-hidden', 'true'); b.insertBefore(p, b.firstChild);
      b.addEventListener('pointermove', function (e) {
        var r = b.getBoundingClientRect();
        b.style.setProperty('--bx', (e.clientX - r.left) + 'px'); b.style.setProperty('--by', (e.clientY - r.top) + 'px');
      });
    });
    if (!fine || !motionOK) return;
    $$('[data-magnetic]').forEach(function (b) {
      var x = 0, y = 0, tx = 0, ty = 0, raf = 0;
      function tick() { x += (tx - x) * 0.16; y += (ty - y) * 0.16; b.style.translate = x.toFixed(2) + 'px ' + y.toFixed(2) + 'px'; if (Math.abs(tx - x) + Math.abs(ty - y) > 0.05) raf = requestAnimationFrame(tick); else raf = 0; }
      function go() { if (!raf) raf = requestAnimationFrame(tick); }
      b.addEventListener('pointermove', function (e) { var r = b.getBoundingClientRect(); tx = (e.clientX - r.left - r.width / 2) * 0.22; ty = (e.clientY - r.top - r.height / 2) * 0.3; go(); });
      b.addEventListener('pointerleave', function () { tx = 0; ty = 0; go(); });
    });
  }

  /* ---------------- glass light: specular + rim follow the pointer (or a virtual sun when there is none) ---------------- */
  var visibleGlass = new Set();
  function initGlassLight() {
    var all = $$('.lg');
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) visibleGlass.add(e.target); else visibleGlass.delete(e.target); }); schedule(); }, { rootMargin: '80px' });
      all.forEach(function (el) { io.observe(el); });
    } else all.forEach(function (el) { visibleGlass.add(el); });
    var px = null, py = null, raf = 0;
    function paint() {
      raf = 0;
      var lx = px === null ? window.innerWidth * 0.3 : px, ly = py === null ? -window.innerHeight * 0.15 : py;
      visibleGlass.forEach(function (el) {
        var r = el.getBoundingClientRect(); if (!r.width) return;
        var mx = clamp((lx - r.left) / r.width * 100, -30, 130), my = clamp((ly - r.top) / r.height * 100, -40, 140);
        var ang = Math.atan2((r.left + r.width / 2) - lx, -((r.top + r.height / 2) - ly)) * 180 / Math.PI;
        el.style.setProperty('--mx', mx.toFixed(1) + '%'); el.style.setProperty('--my', my.toFixed(1) + '%'); el.style.setProperty('--ang', ang.toFixed(1) + 'deg');
      });
    }
    function schedule() { if (!raf) raf = requestAnimationFrame(paint); }
    window.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      px = e.clientX; py = e.clientY;
      G.pointer.x = e.clientX / window.innerWidth * 2 - 1; G.pointer.y = e.clientY / window.innerHeight * 2 - 1;
      schedule();
    }, { passive: true });
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    G.repaintGlass = schedule;
    schedule();
  }

  /* ---------------- refraction (Chromium): a displacement map per glass size, bending the backdrop at the edges ---------------- */
  function initRefraction() {
    var chromium = !!(navigator.userAgentData && navigator.userAgentData.brands && navigator.userAgentData.brands.some(function (b) { return /Chromium/.test(b.brand); }));
    if (!chromium || !motionOK || saveData) return;
    var defs = $('[data-lg-defs]'); if (!defs) return;
    root.classList.add('lg-refract');
    var cache = {}, n = 0, NS = 'http://www.w3.org/2000/svg';
    function map(w, h, r, band) {
      var s = 0.5, cw = Math.max(2, Math.round(w * s)), ch = Math.max(2, Math.round(h * s));
      var c = document.createElement('canvas'); c.width = cw; c.height = ch;
      var ctx = c.getContext('2d'), img = ctx.createImageData(cw, ch), d = img.data;
      var hw = w / 2, hh = h / 2; r = Math.min(r, hw, hh);
      for (var j = 0; j < ch; j++) for (var i = 0; i < cw; i++) {
        var x = (i + 0.5) / s - hw, y = (j + 0.5) / s - hh;
        var qx = Math.abs(x) - (hw - r), qy = Math.abs(y) - (hh - r);
        var ox = Math.max(qx, 0), oy = Math.max(qy, 0);
        var sdf = Math.sqrt(ox * ox + oy * oy) + Math.min(Math.max(qx, qy), 0) - r;
        var depth = -sdf, nx = 0, ny = 0, mag = 0;
        if (depth > 0 && depth < band) {
          if (qx > 0 && qy > 0) { var l = Math.sqrt(qx * qx + qy * qy) || 1; nx = qx / l * Math.sign(x); ny = qy / l * Math.sign(y); }
          else if (qx > qy) nx = Math.sign(x); else ny = Math.sign(y);
          var t = 1 - depth / band; mag = t * t * (3 - 2 * t);
        }
        var k = (j * cw + i) * 4;
        d[k] = 128 - nx * mag * 127; d[k + 1] = 128 - ny * mag * 127; d[k + 2] = 128; d[k + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
      return c.toDataURL('image/png');
    }
    function filterFor(w, h, r) {
      var band = Math.max(8, Math.min(30, Math.min(w, h) * 0.32));
      var key = w + 'x' + h + 'r' + r;
      if (cache[key]) return cache[key];
      var id = 'lgf' + (n++);
      var f = document.createElementNS(NS, 'filter');
      f.setAttribute('id', id); f.setAttribute('filterUnits', 'userSpaceOnUse'); f.setAttribute('primitiveUnits', 'userSpaceOnUse');
      f.setAttribute('x', 0); f.setAttribute('y', 0); f.setAttribute('width', w); f.setAttribute('height', h);
      f.setAttribute('color-interpolation-filters', 'sRGB');
      var im = document.createElementNS(NS, 'feImage');
      im.setAttribute('href', map(w, h, r, band)); im.setAttribute('x', 0); im.setAttribute('y', 0); im.setAttribute('width', w); im.setAttribute('height', h);
      im.setAttribute('preserveAspectRatio', 'none'); im.setAttribute('result', 'm');
      var dm = document.createElementNS(NS, 'feDisplacementMap');
      dm.setAttribute('in', 'SourceGraphic'); dm.setAttribute('in2', 'm'); dm.setAttribute('scale', Math.round(Math.min(band * 1.1, 34)));
      dm.setAttribute('xChannelSelector', 'R'); dm.setAttribute('yChannelSelector', 'G');
      f.appendChild(im); f.appendChild(dm); defs.appendChild(f);
      return (cache[key] = id);
    }
    function apply() {
      $$('.lg').forEach(function (el) {
        var w = Math.round(el.offsetWidth), h = Math.round(el.offsetHeight);
        if (!w || !h || w * h > 1400 * 900) return;
        var cs = getComputedStyle(el);
        var r = parseFloat(cs.borderTopLeftRadius) || 0; if (/%/.test(cs.borderTopLeftRadius)) r = Math.min(w, h) / 2;
        var blur = parseFloat(cs.getPropertyValue('--blur')) || 16, sat = parseFloat(cs.getPropertyValue('--sat')) || 1.9;
        var id = filterFor(w, h, Math.round(r));
        el.style.setProperty('--lg-filter', 'blur(' + Math.round(blur * 0.55) + 'px) url(#' + id + ') saturate(' + sat + ') brightness(1.05)');
      });
    }
    var t = 0;
    window.addEventListener('resize', function () { clearTimeout(t); t = setTimeout(apply, 300); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(apply); else apply();
    G.reapplyRefraction = apply;
  }

  /* ---------------- showreel with chapters ---------------- */
  var reelApi = null;
  function initReel() {
    var fig = $('[data-reel]'); if (!fig) return;
    var video = $('video', fig), ui = $('[data-reel-ui]', fig), play = $('[data-reel-play]', fig), time = $('.reel-time', fig);
    var chapters = $$('[data-chapters] button');
    var marks = chapters.map(function (b) { return parseFloat(b.dataset.t); });
    if (mq('(max-width: 760px)')) {
      var src = $('source', video);
      src.setAttribute('src', 'assets/video/cendavo-showreel-vertical-720.mp4');
      video.setAttribute('poster', 'assets/video/cendavo-showreel-vertical-poster-720.jpg');
      video.load();
    }
    video.muted = true; ui.hidden = false;
    var wanted = motionOK && !saveData, inView = false, pendingSeek = null, raf = 0;
    function label() { var p = !video.paused; play.textContent = (p ? 'Pause' : 'Play') + ' showreel'; }
    function doPlay() { var r; try { r = video.play(); } catch (e) { r = null; } if (r && r.then) r.then(label, label); label(); }
    function paint() {
      var d = video.duration || 20, t = video.currentTime || 0;
      time.textContent = fmt(t) + ' / ' + fmt(d);
      var idx = 0; for (var i = 0; i < marks.length; i++) if (t >= marks[i] - 0.05) idx = i;
      chapters.forEach(function (b, i) {
        var on = i === idx; if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
        var end = marks[i + 1] || d, p = on ? clamp((t - marks[i]) / (end - marks[i]), 0, 1) : 0;
        b.querySelector('.ch-bar').style.transform = 'scaleX(' + p + ')';
      });
    }
    function loop() { paint(); if (!video.paused) raf = requestAnimationFrame(loop); }
    video.addEventListener('play', function () { label(); cancelAnimationFrame(raf); raf = requestAnimationFrame(loop); });
    video.addEventListener('pause', function () { label(); paint(); });
    video.addEventListener('seeked', paint);
    video.addEventListener('loadedmetadata', function () { if (pendingSeek !== null) { video.currentTime = pendingSeek; pendingSeek = null; } paint(); });
    play.addEventListener('click', function () { wanted = video.paused; if (wanted) doPlay(); else video.pause(); });
    chapters.forEach(function (b) {
      b.addEventListener('click', function () {
        var t = parseFloat(b.dataset.t);
        if (video.readyState < 1) pendingSeek = t; else video.currentTime = t;
        wanted = true; doPlay(); paint();
      });
    });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) {
        inView = es[es.length - 1].isIntersecting;
        if (inView && wanted && !G.paused && video.paused) doPlay();
        else if (!inView && !video.paused) video.pause();
      }, { threshold: 0.3 }).observe(video);
    }
    chapters[0].setAttribute('aria-current', 'true');
    label();
    reelApi = { pause: function () { video.pause(); }, resume: function () { if (inView && wanted) doPlay(); } };
  }

  /* ---------------- before / after ---------------- */
  var compareApi = null;
  function initCompare() {
    var fig = $('[data-compare]'); if (!fig) return;
    var range = $('[data-compare-range]', fig), stage = $('.cmp-stage', fig), controls = $('[data-compare-controls]', fig);
    controls.hidden = false;
    var touched = false, dragging = false;
    function set(v) { v = clamp(v, 0, 100); fig.style.setProperty('--pos', v + '%'); range.value = Math.round(v); }
    range.addEventListener('input', function () { touched = true; set(+range.value); });
    function fromEvent(e) { var r = stage.getBoundingClientRect(); set(((e.clientX - r.left) / r.width) * 100); }
    stage.addEventListener('pointerdown', function (e) { touched = true; dragging = true; stage.setPointerCapture(e.pointerId); fromEvent(e); });
    stage.addEventListener('pointermove', function (e) { if (dragging) fromEvent(e); });
    stage.addEventListener('pointerup', function () { dragging = false; });
    stage.addEventListener('pointercancel', function () { dragging = false; });
    compareApi = { set: set, touched: function () { return touched; }, fig: fig };
  }

  /* ---------------- living footage: loads near the viewport, plays only in view and only when motion is welcome ---------------- */
  var ambientVideos = [];
  function load(v) { if (!v.src && v.dataset.src) { v.src = v.dataset.src; v.load(); } }
  function tryPlay(v) { if (G.paused || !motionOK || saveData) return; load(v); var p = v.play(); if (p && p.catch) p.catch(function () {}); }
  function initVideos() {
    var fine = mq('(hover: hover) and (pointer: fine)');
    $$('.mq-video, .close-video, .gphone video').forEach(function (v) {
      v.muted = true; ambientVideos.push(v);
      if (!('IntersectionObserver' in window)) return;
      new IntersectionObserver(function (es) { es.forEach(function (e) { v._in = e.isIntersecting; if (e.isIntersecting) tryPlay(v); else v.pause(); }); }, { rootMargin: '200px 0px' }).observe(v);
    });
    /* project cards: the photo comes alive as the concept site on hover (or when centred on touch screens) */
    $$('.card').forEach(function (card) {
      var v = $('.card-video', card); if (!v) return; v.muted = true;
      function on() { if (!motionOK || saveData || G.paused) return; load(v); var p = v.play(); if (p && p.then) p.then(function () { card.classList.add('is-live'); }, function () {}); else card.classList.add('is-live'); }
      function off() { card.classList.remove('is-live'); setTimeout(function () { if (!card.classList.contains('is-live')) v.pause(); }, 800); }
      if (fine) { card.addEventListener('pointerenter', on); card.addEventListener('pointerleave', off); }
      else if ('IntersectionObserver' in window) new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.intersectionRatio > 0.6) on(); else off(); }); }, { threshold: [0, 0.6] }).observe(card);
    });
  }

  /* ---------------- one pause control for all motion (WCAG 2.2.2) ---------------- */
  var marqueeTweens = [];
  function initMotionToggle() {
    var btn = $('[data-motion-toggle]'); if (!btn || !motionOK) return;
    btn.hidden = false;
    var label = $('.mb-label', btn);
    btn.addEventListener('click', function () {
      G.paused = !G.paused;
      root.classList.toggle('is-paused', G.paused);
      btn.setAttribute('aria-pressed', String(G.paused));
      label.textContent = G.paused ? 'Play motion' : 'Pause motion';
      ambientVideos.forEach(function (v) { if (G.paused) v.pause(); else if (v._in) tryPlay(v); });
      $$('.card-video').forEach(function (v) { if (G.paused) v.pause(); });
      if (reelApi) { if (G.paused) reelApi.pause(); else reelApi.resume(); }
      marqueeTweens.forEach(function (t) { if (G.paused) t.pause(); else t.resume(); });
      if (G.onPauseChange) G.onPauseChange(G.paused);
    });
  }

  /* shared by every page: Lenis smooth scroll driving ScrollTrigger, and the header pill that condenses / steps aside */
  function initShell(gsap, ST) {
    /* smooth scroll (Lenis) driving ScrollTrigger */
    var lenis = null;
    if (window.Lenis) {
      lenis = new window.Lenis({ lerp: 0.09, smoothWheel: true });
      lenis.on('scroll', ST.update);
      gsap.ticker.add(function (t) { lenis.raf(t * 1000); });
      gsap.ticker.lagSmoothing(0);
      G.lenis = lenis;
      $$('a[href^="#"]').forEach(function (a) {
        a.addEventListener('click', function (e) { var id = a.getAttribute('href'); if (id.length < 2) return; var t = $(id); if (!t) return; e.preventDefault(); lenis.scrollTo(t, { offset: -20, duration: 1.4 }); });
      });
    }

    /* header pill condenses */
    var hdr = $('[data-hdr]');
    ST.create({ start: 80, end: 'max', onToggle: function (s) { hdr.classList.toggle('is-condensed', s.isActive); setTimeout(function () { if (G.reapplyRefraction) G.reapplyRefraction(); }, 750); },
      onUpdate: function (s) { var y = s.scroll(); if (s.direction > 0 && y > 80) hdr.classList.add('is-hidden'); else if (s.direction < 0 || y <= 80) hdr.classList.remove('is-hidden'); } });

  }

  /* ---------------- motion ---------------- */
  function initMotion() {
    var gsap = window.gsap, ST = window.ScrollTrigger;
    gsap.registerPlugin(ST);
    gsap.defaults({ ease: 'expo.out', duration: 1 });
    var wide = mq('(min-width: 761px)'), fine = mq('(pointer: fine)');

    initShell(gsap, ST);

    /* ---- HERO INTRO: the glass assembles, the headline rises through its masks ---- */
    var lines = $$('.kin .lt'), fades = $$('[data-hero-fade]'), cards = $$('.gcard');
    var book = $('.c-book'), slot = $('.slot-pick');
    gsap.set(lines, { y: 0, yPercent: 105, '--w': 70 });
    gsap.set(fades, { opacity: 0, y: 16 });
    gsap.set(cards, { opacity: 0, transformPerspective: 900, z: -420, rotationX: 18, rotationY: -14, filter: 'blur(10px)' });
    book.classList.remove('booked'); slot.classList.remove('on');
    root.classList.remove('js-motion');

    var counter = { v: 0 };
    var intro = gsap.timeline({ delay: 0.25 });
    intro
      .to(lines, { yPercent: 0, duration: 1.3, stagger: 0.09 }, 0)
      .to(lines, { '--w': 84, duration: 1.6, stagger: 0.09, ease: 'power3.out' }, 0.05)
      .to(fades, { opacity: 1, y: 0, duration: 1.1, stagger: 0.1 }, 0.7)
      .to(cards, { opacity: 1, z: 0, rotationX: 0, rotationY: 0, filter: 'blur(0px)', duration: 1.6, stagger: 0.14, ease: 'expo.out', clearProps: 'filter' }, 1.0)
      .call(function () { slot.classList.add('on'); }, null, 2.6)
      .call(function () { book.classList.add('booked'); }, null, 3.3)
      .call(function () { if (G.repaintGlass) G.repaintGlass(); if (G.reapplyRefraction) G.reapplyRefraction(); }, null, 2.8);

    /* idle float: the cards breathe on slow sine paths (no overshoot) */
    cards.forEach(function (c, i) {
      gsap.to(c, { yPercent: i % 2 ? 7 : -7, duration: 3.2 + i * 0.6, ease: 'sine.inOut', repeat: -1, yoyo: true, delay: 2.4 });
    });

    /* pointer: cards drift in depth toward the pointer */
    if (fine) {
      var qx = cards.map(function (c) { return gsap.quickTo(c, 'x', { duration: 1.2, ease: 'power3.out' }); });
      var qy = cards.map(function (c) { return gsap.quickTo(c, 'y', { duration: 1.2, ease: 'power3.out' }); });
      $('.hero').addEventListener('pointermove', function (e) {
        var nx = e.clientX / window.innerWidth - 0.5, ny = e.clientY / window.innerHeight - 0.5;
        cards.forEach(function (c, i) { var d = parseFloat(c.dataset.depth) || 1; qx[i](nx * 34 * d); qy[i](ny * 22 * d); });
      });
    }

    /* ---- HERO SCROLL: one short pin. The camera dollies through the glass, cards fly past in depth ---- */
    var heroTl = gsap.timeline({
      scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom bottom', scrub: 0.8,
        onUpdate: function (s) { G.heroP = s.progress; } }
    });
    heroTl
      .to('.hero-copy', { yPercent: -14, opacity: 0, filter: 'blur(8px)', ease: 'power1.in', duration: 0.42 }, 0)
      .to('.hero-cap, .scroll-cue', { opacity: 0, duration: 0.4 }, 0)
      .to('.hero-veil', { opacity: 0.3, duration: 1 }, 0);
    cards.forEach(function (c, i) {
      var d = parseFloat(c.dataset.depth) || 1;
      heroTl.to(c, { z: 260 * d, rotationX: -10, rotationY: i % 2 ? 12 : -12, opacity: 0, ease: 'power2.in', duration: 0.45 }, 0.04 * i);
    });

    /* ---- section headings rise through a mask ---- */
    $$('.h2').forEach(function (h) {
      gsap.fromTo(h, { clipPath: 'inset(0% 0% 100% 0%)', yPercent: 30 }, { clipPath: 'inset(0% 0% -12% 0%)', yPercent: 0, duration: 1.3, scrollTrigger: { trigger: h, start: 'top 88%', once: true } });
    });

    /* ---- SHOWREEL: a glass lens that opens into full bleed, tilting flat as it arrives ---- */
    var stage = $('.reel-stage');
    gsap.fromTo(stage, { '--lx': wide ? '17%' : '6%', '--li': wide ? '7%' : '5%', '--lr': wide ? '48px' : '32px', '--lrx': '10deg', '--ls': 0.97, '--lo': 1 },
      { '--lx': '0%', '--li': '0%', '--lr': '0px', '--lrx': '0deg', '--ls': 1, '--lo': 0, ease: 'none',
        scrollTrigger: { trigger: stage, start: 'top 85%', end: wide ? 'top 8%' : 'top 30%', scrub: 0.6 } });
    gsap.from('.reel-panel', { y: 60, opacity: 0, duration: 1.2, scrollTrigger: { trigger: stage, start: 'top 30%', once: true } });
    gsap.from('.chapters li', { x: -16, opacity: 0, duration: 0.9, stagger: 0.05, scrollTrigger: { trigger: stage, start: 'top 30%', once: true } });

    /* ---- MARQUEE: endless, and it leans into the scroll ---- */
    $$('[data-marquee]').forEach(function (track) {
      var dir = parseFloat(track.dataset.marquee) || -1;
      var t = gsap.fromTo(track, { xPercent: dir < 0 ? 0 : -50 }, { xPercent: dir < 0 ? -50 : 0, duration: 46, ease: 'none', repeat: -1 });
      marqueeTweens.push(t);
    });
    marqueeTweens.push(gsap.fromTo('[data-mq-type]', { '--mqp': 0 }, { '--mqp': 1, duration: 34, ease: 'none', repeat: -1 }));
    var boost = { v: 1 };
    ST.create({ trigger: '.marq', start: 'top bottom', end: 'bottom top', onUpdate: function (s) {
      var v = clamp(Math.abs(s.getVelocity()) / 500, 0, 5);
      gsap.to(boost, { v: 1 + v, duration: 0.2, overwrite: true, onUpdate: function () { marqueeTweens.forEach(function (t) { t.timeScale(boost.v); }); } });
      gsap.to(boost, { v: 1, duration: 1.4, delay: 0.25, ease: 'power3.out', onUpdate: function () { marqueeTweens.forEach(function (t) { t.timeScale(boost.v); }); } });
    } });
    gsap.fromTo('.mq-type', { scale: 0.86, rotationX: 24, transformPerspective: 1200 }, { scale: 1, rotationX: 0, ease: 'none', scrollTrigger: { trigger: '.marq', start: 'top bottom', end: 'top 30%', scrub: 0.6 } });

    /* ---- WORK: cards arrive tilted back in 3D, settle flat ---- */
    $$('.card').forEach(function (card, i) {
      /* cards fan in from depth: each arrives on its own 3D angle, then settles flat */
      var fan = [{ x: -160, rY: 32, rZ: -4 }, { x: 220, rY: -38, rZ: 5 }, { x: 260, rY: -30, rZ: -3 }][i % 3];
      gsap.fromTo(card, { opacity: 0, y: 160, x: wide ? fan.x : 0, z: -500, rotationX: 22, rotationY: wide ? fan.rY : 0, rotationZ: wide ? fan.rZ : 0, transformPerspective: 1400, transformOrigin: '50% 100%' },
        { opacity: 1, y: 0, x: 0, z: 0, rotationX: 0, rotationY: 0, rotationZ: 0, duration: 1.9, ease: 'expo.out', delay: (i % 3) * 0.14, scrollTrigger: { trigger: card, start: 'top 94%', once: true } });
      gsap.fromTo($('.card-body', card), { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 1.2, delay: 0.35 + (i % 3) * 0.12, clearProps: 'transform', scrollTrigger: { trigger: card, start: 'top 92%', once: true } });
      var img = $('.card-photo', card);
      gsap.fromTo(img, { yPercent: -6, scale: 1.12 }, { yPercent: 6, scale: 1.12, ease: 'none', scrollTrigger: { trigger: card, start: 'top bottom', end: 'bottom top', scrub: true } });
    });

    /* 3D tilt + light sweep on pointer */
    if (fine) {
      $$('[data-tilt]').forEach(function (el) {
        var rx = gsap.quickTo(el, 'rotationX', { duration: 0.9, ease: 'power3.out' }), ry = gsap.quickTo(el, 'rotationY', { duration: 0.9, ease: 'power3.out' });
        var sw = $('.sweep', el);
        gsap.set(el, { transformPerspective: 1200 });
        el.addEventListener('pointermove', function (e) {
          var r = el.getBoundingClientRect(), nx = (e.clientX - r.left) / r.width - 0.5, ny = (e.clientY - r.top) / r.height - 0.5;
          rx(-ny * 7); ry(nx * 9);
          if (sw) sw.style.setProperty('--sw', (nx * 120) + '%');
        });
        el.addEventListener('pointerleave', function () { rx(0); ry(0); if (sw) sw.style.setProperty('--sw', '-80%'); });
      });
    }

    /* ---- BEFORE / AFTER: the frame swings in, then one demonstration sweep ---- */
    gsap.fromTo('.cmp-frame', { rotationY: -18, rotationX: 6, y: 60, opacity: 0, transformPerspective: 1600 }, { rotationY: 0, rotationX: 0, y: 0, opacity: 1, duration: 1.8, scrollTrigger: { trigger: '.compare', start: 'top 85%', once: true } });
    if (compareApi) {
      var pos = { v: 50 };
      ST.create({ trigger: compareApi.fig, start: 'top 60%', once: true, onEnter: function () {
        if (compareApi.touched()) return;
        gsap.timeline({ delay: 0.7, onUpdate: function () { if (!compareApi.touched()) compareApi.set(pos.v); } })
          .to(pos, { v: 84, duration: 1.2, ease: 'power3.inOut' })
          .to(pos, { v: 16, duration: 1.4, ease: 'power3.inOut' }, '+=0.2')
          .to(pos, { v: 50, duration: 1, ease: 'power3.inOut' }, '+=0.2');
      } });
    }

    /* ---- SERVICES ---- */
    $$('.svc-card').forEach(function (row, i) {
      var v = row.dataset.vig, media = $('.svc-media', row);
      var tl = gsap.timeline({ scrollTrigger: { trigger: '.svc-list', start: 'top 80%', once: true }, delay: i * 0.14 });
      tl.fromTo(row, { opacity: 0, y: 120, z: -420, rotationX: 18, rotationY: wide ? (i - 1) * -28 : 0, transformPerspective: 1400 }, { opacity: 1, y: 0, z: 0, rotationX: 0, rotationY: 0, duration: 1.8, ease: 'expo.out' }, 0);
      if (v === 'build') tl.call(function () { $('.vb', media).classList.add('is-done'); }, null, 1.6)
        .fromTo($('.vb', media), { z: -120, opacity: 0, transformPerspective: 900 }, { z: 0, opacity: 1, duration: 1.4 }, 0.3);
      if (v === 'redo') tl.fromTo($('.vr-old', media), { x: 0, rotation: -4, opacity: 1 }, { x: -40, y: -10, rotation: -10, opacity: 0.55, duration: 1.4, ease: 'power3.out' }, 0.8)
        .fromTo($('.vr-new', media), { z: -200, y: 40, opacity: 0, transformPerspective: 900 }, { z: 0, y: 0, opacity: 1, duration: 1.4 }, 1.0);
      if (v === 'care') tl.fromTo($('.log', media), { z: -120, opacity: 0, transformPerspective: 900 }, { z: 0, opacity: 1, duration: 1.4 }, 0.3)
        .fromTo($$('.log-list li', media), { opacity: 0, x: -14 }, { opacity: 1, x: 0, duration: 0.8, stagger: 0.12 }, 0.8);
    });

    /* ---- CLOSING: footage drifts under the glass, the panel lifts out of depth ---- */
    gsap.fromTo('.close', { '--cy': '-60px', '--cs': 1.12 }, { '--cy': '60px', '--cs': 1, ease: 'none', scrollTrigger: { trigger: '.close', start: 'top bottom', end: 'bottom top', scrub: true } });
    gsap.fromTo('.close-panel', { y: 90, opacity: 0, scale: 0.94, rotationX: 10, transformPerspective: 1400 }, { y: 0, opacity: 1, scale: 1, rotationX: 0, duration: 1.6, scrollTrigger: { trigger: '.close', start: 'top 70%', once: true } });
    gsap.fromTo('.close-h .cl', { yPercent: 60, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 1.3, stagger: 0.1, scrollTrigger: { trigger: '.close', start: 'top 62%', once: true } });

    if (wide) {
      gsap.timeline({ scrollTrigger: { trigger: '.close', start: 'top bottom', end: 'center center', scrub: 1 } })
        .fromTo('.gp-1', { x: 520, y: 380, z: -900, rotationY: -70, rotationX: 28, rotationZ: 12 }, { x: 120, y: 80, z: -200, rotationY: -40, rotationX: 10, rotationZ: 4, ease: 'none', duration: 0.5 })
        .to('.gp-1', { x: 0, y: 0, z: 0, rotationY: -16, rotationX: 4, rotationZ: 0, ease: 'power2.out', duration: 0.5 })
        .fromTo('.gp-2', { x: 400, y: -420, z: -1100, rotationY: -80, rotationX: -30, rotationZ: -10 }, { x: 90, y: -60, z: -260, rotationY: -36, rotationX: -8, rotationZ: -3, ease: 'none', duration: 0.55 }, 0.05)
        .to('.gp-2', { x: 0, y: 0, z: 60, rotationY: -22, rotationX: -2, rotationZ: 0, ease: 'power2.out', duration: 0.45 });
      gsap.to('.gp-1', { yPercent: -6, duration: 3.6, ease: 'sine.inOut', repeat: -1, yoyo: true });
      gsap.to('.gp-2', { yPercent: 5, duration: 4.2, ease: 'sine.inOut', repeat: -1, yoyo: true });
    }

    /* footer wordmark widens to the edges */
    gsap.fromTo('[data-word]', { '--w': 80 }, { '--w': 112, ease: 'none', scrollTrigger: { trigger: '.ftr', start: 'top bottom', end: 'bottom bottom', scrub: 0.5 } });

    window.addEventListener('load', function () { ST.refresh(); });
  }
})();
