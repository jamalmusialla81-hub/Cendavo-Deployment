/* Cendavo — Daylight inner pages. Deferred, after GSAP. daylight.js has already set .js / .js-motion and wired the menu.
   This file owns, for <body data-page>:
     - video: muted loops play only in view, pause out of view; no autoplay with reduced motion or Save-Data;
       a global Pause motion control (remembered per browser) and per-video play buttons for the social clips and film,
     - the launch film chapters (about), the contact form demo notice, and
     - all page motion, inside gsap.matchMedia('(prefers-reduced-motion: no-preference)').
   Content is only ever hidden behind .js-motion (CSS) or by GSAP inside that guard; without JS, without GSAP or with
   reduced motion everything is visible in its end state. */
(function () {
  'use strict';
  var root = document.documentElement;
  function $(s, c) { return (c || document).querySelector(s); }
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  function fmt(t) { t = Math.max(0, Math.floor(t || 0)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); }
  var KEY = 'cendavo-motion';
  function getPref() { try { return window.localStorage.getItem(KEY); } catch (e) { return null; } }
  function setPref(v) { try { if (v) window.localStorage.setItem(KEY, v); else window.localStorage.removeItem(KEY); } catch (e) { /* storage blocked */ } }

  var DL, motionOK, saveData, paused;
  var vids = [];          // { v, inView, user: null | true | false, btn }
  var ambient = [];       // GSAP timelines that loop; paused with the global control

  document.addEventListener('DOMContentLoaded', function () {
    DL = window.Daylight || {};
    motionOK = !!DL.motionOK;
    saveData = !!(navigator.connection && navigator.connection.saveData);
    paused = getPref() === 'paused' || !motionOK;

    initFilmSource();
    initVideos();
    initFilm();
    initGlobal();
    initContact();
    initNotFound();

    if (DL.release) DL.release();
    if (motionOK && window.gsap && window.ScrollTrigger && DL.IN) {
      try { initMotion(); } catch (e) { root.classList.remove('js-motion'); throw e; }
    } else {
      root.classList.remove('js-motion');
    }
  });

  /* ---------------- video ---------------- */
  function want(o) {
    if (!o.inView) return false;
    if (o.user === false) return false;
    if (o.user === true) return true;
    return !paused && !saveData;
  }
  function sync(o) {
    var v = o.v;
    if (want(o)) {
      if (v.paused) { var p; try { p = v.play(); } catch (e) { p = null; } if (p && p.catch) p.catch(function () {}); }
    } else if (!v.paused) v.pause();
  }
  function syncAll() { vids.forEach(sync); }
  function label(o) {
    if (!o.btn) return;
    var playing = !o.v.paused;
    o.btn.textContent = (playing ? 'Pause ' : 'Play ') + o.name;
    o.btn.classList.toggle('is-playing', playing);
  }
  function initVideos() {
    $$('video[data-auto]').forEach(function (v) {
      var o = { v: v, inView: false, user: null, btn: null, name: v.getAttribute('data-vname') || 'video' };
      v.muted = true;
      v.removeAttribute('controls');
      var scope = v.closest('[data-vscope]') || v.closest('.wk-clip, .chap-media, .film');
      var btn = scope ? $('[data-vtoggle]', scope) : null;
      if (btn) {
        o.btn = btn; btn.hidden = false;
        btn.addEventListener('click', function () {
          if (v.paused) { o.user = true; o.inView = true; } else { o.user = false; }
          sync(o);
        });
        v.addEventListener('play', function () { label(o); });
        v.addEventListener('pause', function () { label(o); });
        label(o);
      }
      vids.push(o);
    });
    if (!('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        var o = null;
        for (var i = 0; i < vids.length; i++) if (vids[i].v === e.target) o = vids[i];
        if (!o) return;
        o.inView = e.isIntersecting;
        if (!o.inView && o.user === true) o.user = null; // a manual play ends when it scrolls away
        sync(o);
      });
      showGlobal();
    }, { threshold: 0.3 });
    vids.forEach(function (o) { io.observe(o.v); });
  }

  /* global Pause motion: videos + ambient loops. It shows while a moving video is on screen, so it never sits over
     plain reading content; it stays put while it has focus. */
  var globalBtn = null;
  function showGlobal() {
    if (!globalBtn) return;
    var any = vids.some(function (o) { return o.inView; });
    if (!any && document.activeElement === globalBtn) return;
    globalBtn.classList.toggle('is-off', !any);
  }
  function initGlobal() {
    var btn = $('[data-motion-global]');
    if (!btn) return;
    globalBtn = btn;
    btn.hidden = false;
    showGlobal();
    function paint() {
      btn.setAttribute('aria-pressed', String(paused));
      btn.textContent = paused ? 'Play motion' : 'Pause motion';
    }
    btn.addEventListener('click', function () {
      paused = !paused;
      setPref(paused ? 'paused' : (motionOK ? null : 'playing'));
      vids.forEach(function (o) { o.user = null; });
      syncAll();
      ambient.forEach(function (t) { if (paused) t.pause(); else t.resume(); });
      paint();
    });
    paint();
  }

  /* launch film: vertical cut on small screens (swapped before anything loads) */
  function initFilmSource() {
    var film = $('[data-film]');
    if (!film || !window.matchMedia || !window.matchMedia('(max-width: 640px)').matches) return;
    var v = $('video', film), src = $('source', v);
    if (v.dataset.vsrc) { src.setAttribute('src', v.dataset.vsrc); v.setAttribute('poster', v.dataset.vposter); v.setAttribute('width', '720'); v.setAttribute('height', '1280'); v.load(); }
  }
  function initFilm() {
    var film = $('[data-film]');
    if (!film) return;
    var v = $('video', film), ui = $('[data-film-ui]', film), play = $('[data-film-play]', film);
    var fill = $('.reel-fill', film), time = $('.reel-time', film);
    var chapters = $$('[data-chapters] button', film);
    var marks = chapters.map(function (b) { return parseFloat(b.dataset.t); });
    var o = null;
    for (var i = 0; i < vids.length; i++) if (vids[i].v === v) o = vids[i];
    ui.hidden = false;
    if (o) { o.btn = null; }
    function lab() { var p = !v.paused; play.textContent = (p ? 'Pause' : 'Play') + ' film'; play.classList.toggle('is-playing', p); }
    var raf = 0, pending = null;
    function paintFilm() {
      var d = v.duration || 20, t = v.currentTime || 0;
      fill.style.transform = 'scaleX(' + (t / d) + ')';
      if (time) time.textContent = fmt(t) + ' / ' + fmt(d);
      var idx = 0;
      for (var j = 0; j < marks.length; j++) if (t >= marks[j] - 0.05) idx = j;
      chapters.forEach(function (b, k) {
        var on = k === idx, start = marks[k], end = marks[k + 1] || d;
        if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
        var p = k < idx ? 1 : on ? Math.min(1, Math.max(0, (t - start) / (end - start))) : 0;
        $('.bar i', b).style.transform = 'scaleX(' + p + ')';
      });
    }
    function loop() { paintFilm(); if (!v.paused) raf = requestAnimationFrame(loop); }
    v.addEventListener('play', function () { lab(); cancelAnimationFrame(raf); raf = requestAnimationFrame(loop); });
    v.addEventListener('pause', function () { lab(); paintFilm(); });
    v.addEventListener('seeked', paintFilm);
    v.addEventListener('loadedmetadata', function () { if (pending !== null) { v.currentTime = pending; pending = null; } paintFilm(); });
    play.addEventListener('click', function () {
      if (!o) return;
      if (v.paused) { o.user = true; o.inView = true; } else { o.user = false; }
      sync(o);
    });
    chapters.forEach(function (b) {
      b.addEventListener('click', function () {
        var t = parseFloat(b.dataset.t);
        if (v.readyState < 1) pending = t; else v.currentTime = t;
        if (o) { o.user = true; o.inView = true; sync(o); }
        paintFilm();
      });
    });
    chapters[0].setAttribute('aria-current', 'true');
    lab();
  }

  /* contact: the prototype never submits */
  function initContact() {
    var form = $('form[data-enquiry]');
    if (!form) return;
    var status = $('[data-enquiry-status]');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      status.classList.add('is-demo');
      status.textContent = 'This is a design prototype, so nothing was sent. On the live site this form sends your enquiry to Cendavo, or you can email cendavo.au@gmail.com.';
    });
  }

  /* 404: show the address that was actually requested (text only) */
  function initNotFound() {
    var p = $('[data-nf-path]'), h = $('[data-nf-host]');
    if (!p) return;
    var path = location.pathname || '/';
    p.textContent = path.length > 42 ? path.slice(0, 41) + '…' : path;
    if (h && location.host) h.textContent = location.host;
  }

  /* ---------------- motion ----------------
     Same system as the homepage: IN (.2,.8,.2,1) for entrances, IO (.7,0,.2,1) between states;
     0.2 / 0.4 / 0.7 / 1.0 s; stagger 40–80 ms; travel 8–40 px; masks over flies; nothing elastic, nothing rotates. */
  function initMotion() {
    var gsap = window.gsap, ST = window.ScrollTrigger, IN = DL.IN, IO = DL.IO, D = DL.D;
    gsap.registerPlugin(ST);
    gsap.defaults({ ease: IN, duration: D.m });
    var mm = gsap.matchMedia();

    mm.add('(prefers-reduced-motion: no-preference)', function () {
      var wide = window.matchMedia('(min-width: 641px)').matches;
      var once = function (trigger, start) { return { trigger: trigger, start: start || 'top 84%', once: true }; };

      /* 1. hero: masked lines rise while the width axis settles; supporting copy follows */
      var lines = $$('.pk .lt'), fades = $$('[data-hero-fade]'), gates = $$('[data-gate]');
      if (lines.length) gsap.set(lines, { y: 0, yPercent: 104, '--w': 72 });
      if (fades.length) gsap.set(fades, { opacity: 0, y: 12 });
      if (gates.length) gsap.set(gates, { opacity: 0, y: 24 });
      root.classList.remove('js-motion');
      var intro = gsap.timeline({ delay: 0.1 });
      if (lines.length) intro.to(lines, { yPercent: 0, duration: D.l, stagger: 0.08 }, 0).to(lines, { '--w': 84, duration: D.l, stagger: 0.08, ease: IO }, 0.1);
      if (fades.length) intro.to(fades, { opacity: 1, y: 0, duration: D.m, stagger: 0.08 }, 0.5);
      if (gates.length) intro.to(gates, { opacity: 1, y: 0, duration: D.l, stagger: 0.08 }, 0.4);

      /* 2. headings unmask as they arrive (not the hero h1) */
      $$('main .h2, main [data-rise]').forEach(function (h) {
        gsap.fromTo(h, { clipPath: 'inset(0% 0% 100% 0%)', y: 16 }, { clipPath: 'inset(0% 0% -12% 0%)', y: 0, duration: D.l, scrollTrigger: once(h, 'top 88%') });
      });

      /* 3. photographs open from a small inset */
      $$('[data-clip]').forEach(function (f) {
        var img = $('img', f);
        gsap.timeline({ scrollTrigger: once(f, 'top 86%') })
          .fromTo(f, { clipPath: 'inset(6% 6% 6% 6% round 18px)' }, { clipPath: 'inset(0% 0% 0% 0% round 18px)', duration: D.l, ease: IO })
          .fromTo(img, { scale: 1.06 }, { scale: 1, duration: D.l, clearProps: 'transform' }, 0);
      });
      /* the one dark cover drifts a little as it passes (single depth layer) */
      $$('[data-drift] img').forEach(function (img) {
        gsap.fromTo(img, { yPercent: -4, scale: 1.08 }, { yPercent: 4, scale: 1.08, ease: 'none', scrollTrigger: { trigger: img.parentNode, start: 'top bottom', end: 'bottom top', scrub: 0.4 } });
      });

      /* 4. lists arrive in reading order */
      $$('[data-stagger]').forEach(function (list) {
        gsap.fromTo(list.children, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: D.m, stagger: 0.06, scrollTrigger: once(list) });
      });

      /* 5. benches: devices arrive, screens unmask, fragments assemble, then the fragment shows its state change */
      var demos = { hb: demoConfirm, gl: demoAttach, fc: demoBooked };
      $$('[data-bench]').forEach(function (b) {
        var lap = $('.d-lap', b), ph = $('.d-ph', b), plinth = $('.bench-plinth', b), frags = $$('.ui', b);
        var scr = $$('.d-scr, .d-ph-scr', b);
        var demo = demos[b.dataset.bench] ? demos[b.dataset.bench](b) : null;
        gsap.set(frags, { opacity: 0 });
        var tl = gsap.timeline({ scrollTrigger: once(b, 'top 78%') });
        tl.fromTo(plinth, { clipPath: 'inset(0% 0% 0% 100% round 2.6cqw)' }, { clipPath: 'inset(0% 0% 0% 0% round 2.6cqw)', duration: D.l, ease: IO }, 0)
          .fromTo(lap, { opacity: 0, y: 32 }, { opacity: 1, y: 0, duration: D.l }, 0.15)
          .fromTo(ph, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: D.l }, 0.25)
          /* screens are never masked: the poster shows until the loop has a frame */
          .fromTo(frags, { opacity: 0, scale: 0.96, y: 8 }, { opacity: 1, scale: 1, y: 0, duration: D.s, stagger: 0.08 }, 0.9);
        if (demo) tl.add(demo, 1.3);
      });

      function swapTo(el, toB) {
        var a = $('.s-a', el), b = $('.s-b', el);
        return gsap.timeline()
          .to(toB ? a : b, { opacity: 0, y: -6, duration: D.xs, ease: IO })
          .fromTo(toB ? b : a, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: D.s }, '<0.08');
      }
      function demoConfirm(b) {
        var card = $('[data-confirm]', b), btn = $('.ui-btn', card), chip = $('.ui-chips .on', b);
        btn.classList.remove('done'); if (chip) chip.classList.remove('on');
        $$('.swap', card).forEach(function (s) { gsap.set($('.s-a', s), { opacity: 1 }); gsap.set($('.s-b', s), { opacity: 0 }); });
        return gsap.timeline()
          .call(function () { if (chip) chip.classList.add('on'); }, null, 0.2)
          .fromTo(btn, { scale: 0.97 }, { scale: 1, duration: D.xs }, 0.9)
          .call(function () { btn.classList.add('done'); }, null, 0.9)
          .add(swapTo($('.ui-btn .swap', card), true), 0.95)
          .add(swapTo($('b.swap', card), true), 1.05);
      }
      function demoAttach(b) {
        var card = $('[data-attach]', b), imgs = $$('.ui-thumbs img', card), lab = $('[data-count-label]', card);
        gsap.set(imgs, { opacity: 0, scale: 0.9 });
        lab.textContent = 'Attach photos of the space';
        var tl = gsap.timeline();
        imgs.forEach(function (img, i) {
          tl.to(img, { opacity: 1, scale: 1, duration: D.s }, i * 0.45)
            .call(function () { lab.textContent = (i + 1) + (i ? ' photos attached' : ' photo attached'); }, null, i * 0.45 + 0.1);
        });
        return tl;
      }
      function demoBooked(b) {
        var card = $('[data-booked]', b), slot = $('.ui-slots .on', card), sw = $('b.swap', card);
        slot.classList.remove('on');
        gsap.set($('.s-a', sw), { opacity: 1 }); gsap.set($('.s-b', sw), { opacity: 0 });
        return gsap.timeline()
          .fromTo(slot, { scale: 0.96 }, { scale: 1, duration: D.xs }, 0.5)
          .call(function () { slot.classList.add('on'); }, null, 0.5)
          .add(swapTo(sw, true), 0.9);
      }

      /* 6. work: the request queue moves one card along and the reply draft appears */
      var q = $('[data-queue]');
      if (q) {
        var mover = $('[data-mover]', q), newCol = $('[data-col="new"]', q), followCol = $('[data-col="follow"]', q), draft = $('.q-draft', q);
        var counts = $$('.q-col > span em', q);
        newCol.appendChild(mover); counts[0].textContent = '2'; counts[1].textContent = '1';
        gsap.set(draft, { opacity: 0, y: 8 });
        gsap.timeline({ scrollTrigger: once(q, 'top 75%') })
          .fromTo(q, { clipPath: 'inset(4% 4% 4% 4% round 22px)' }, { clipPath: 'inset(0% 0% 0% 0% round 22px)', duration: D.l, ease: IO })
          .fromTo($$('.q-card', q), { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: D.s, stagger: 0.06 }, 0.3)
          .call(function () { mover.classList.add('is-moving'); }, null, 1.2)
          .call(function () {
            // FLIP: measure, move in the DOM, then animate from the old position
            var first = mover.getBoundingClientRect();
            followCol.insertBefore(mover, followCol.children[1]);
            counts[0].textContent = '1'; counts[1].textContent = '2';
            var last = mover.getBoundingClientRect();
            gsap.fromTo(mover, { x: first.left - last.left, y: first.top - last.top }, { x: 0, y: 0, duration: D.m, ease: IO, onComplete: function () { mover.classList.remove('is-moving'); } });
          }, null, 1.6)
          .to(draft, { opacity: 1, y: 0, duration: D.s }, 2.4);
      }

      /* 7. sequences draw their connecting line once (services process, pricing timeline) */
      $$('[data-line]').forEach(function (wrap) {
        var kind = wrap.getAttribute('data-line'), line = $('[data-line-fill]', wrap);
        var vertical = !window.matchMedia(kind === 'tl' ? '(min-width: 861px)' : '(min-width: 961px)').matches;
        var items = $$('li', wrap);
        var tl = gsap.timeline({ scrollTrigger: once(wrap, 'top 78%') });
        tl.fromTo(line, vertical ? { scaleY: 0 } : { scaleX: 0 }, vertical ? { scaleY: 1, duration: D.l * 1.4, ease: IO } : { scaleX: 1, duration: D.l * 1.4, ease: IO }, 0)
          .fromTo(items, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: D.m, stagger: 0.08 }, 0.1);
      });

      /* 8. pricing: the quote sheet fills in, line by line, then the fixed price is set */
      var quote = $('[data-quote]');
      if (quote) {
        var qLines = $$('.q-lines li', quote), ticks = $$('.q-lines path', quote), total = $('.q-total', quote), forB = $('.q-for b', quote);
        gsap.set(qLines, { opacity: 0, y: 8 });
        gsap.set(ticks, { strokeDasharray: 16, strokeDashoffset: 16 });
        gsap.set(total, { clipPath: 'inset(0% 100% 0% 0% round 12px)' });
        gsap.set(forB, { clipPath: 'inset(0% 100% 0% 0%)' });
        var qt = gsap.timeline({ delay: 0.7 });
        qt.to(forB, { clipPath: 'inset(0% 0% 0% 0%)', duration: D.m, ease: IO }, 0.4);
        qLines.forEach(function (li, i) {
          var at = 0.8 + i * 0.32;
          qt.to(li, { opacity: 1, y: 0, duration: D.s }, at)
            .to(ticks[i], { strokeDashoffset: 0, duration: D.s, ease: IO }, at + 0.15);
        });
        qt.to(total, { clipPath: 'inset(0% 0% 0% 0% round 12px)', duration: D.l, ease: IO }, 0.8 + qLines.length * 0.32 + 0.2);
      }

      /* 9. pricing: what-affects scales draw from the left */
      $$('.scale i').forEach(function (i) {
        gsap.fromTo(i, { scaleX: 0 }, { scaleX: 1, duration: D.l, ease: IO, scrollTrigger: once(i, 'top 90%') });
      });

      /* 10. services vignettes: reuse the homepage build vignette; month checklist ticks in; redirects connect */
      var vb = $('.vig-build');
      if (vb) {
        var page = $('.vb-page', vb);
        gsap.timeline({ scrollTrigger: once(vb, 'top 78%') })
          .set($('.vb-done', vb), { clipPath: 'inset(0% 100% 0% 0%)' })
          .set($('.vb-scan', vb), { x: 0, opacity: 0 })
          .fromTo($$('.w', vb), { opacity: 0, scale: 0.96 }, { opacity: 1, scale: 1, duration: D.s, stagger: 0.06 })
          .to($('.vb-scan', vb), { opacity: 1, duration: D.xs }, '+=0.2')
          .to($('.vb-scan', vb), { x: function () { return page.offsetWidth - 2; }, duration: D.l, ease: IO }, '<')
          .to($('.vb-done', vb), { clipPath: 'inset(0% 0% 0% 0%)', duration: D.l, ease: IO }, '<')
          .to($('.vb-scan', vb), { opacity: 0, duration: D.xs });
      }
      $$('[data-month]').forEach(function (m) {
        var rows = $$('li', m), boxes = $$('.box path', m);
        gsap.set(boxes, { strokeDasharray: 16, strokeDashoffset: 16 });
        gsap.timeline({ scrollTrigger: once(m, 'top 78%') })
          .fromTo(rows, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: D.s, stagger: 0.08 })
          .to(boxes, { strokeDashoffset: 0, duration: D.s, ease: IO, stagger: 0.24 }, 0.4);
      });
      $$('[data-redir]').forEach(function (r) {
        var rows = $$('li', r);
        gsap.timeline({ scrollTrigger: once(r, 'top 80%') })
          .fromTo(rows, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: D.s, stagger: 0.08 })
          .fromTo($$('.arr', r), { scaleX: 0 }, { scaleX: 1, duration: D.m, ease: IO, stagger: 0.12 }, 0.3)
          .fromTo($$('.ok', r), { opacity: 0, scale: 0.96 }, { opacity: 1, scale: 1, duration: D.xs, stagger: 0.12 }, 0.8);
      });

      /* 11. about: hero photos open in turn; trades row in reading order */
      var abp = $$('.ab-photos .photo');
      if (abp.length) {
        abp.forEach(function (p, i) {
          gsap.fromTo(p, { clipPath: 'inset(0% 0% 100% 0% round 16px)' }, { clipPath: 'inset(0% 0% 0% 0% round 16px)', duration: D.l, ease: IO, delay: 0.4 + i * 0.08 });
          gsap.fromTo($('img', p), { scale: 1.06 }, { scale: 1, duration: D.l, delay: 0.4 + i * 0.08, clearProps: 'transform' });
        });
      }
      var film = $('.film-frame');
      /* the film's opening is owned by glass-pages.js (glass lens) */

      /* 12. contact: the panel opens; the steps follow */
      var ctf = $('.ct-form');
      if (ctf) {
        gsap.fromTo(ctf, { clipPath: 'inset(3% 3% 3% 3% round 28px)', opacity: 0 }, { clipPath: 'inset(0% 0% 0% 0% round 28px)', opacity: 1, duration: D.l, ease: IO, delay: 0.4, clearProps: 'clipPath' });
        gsap.fromTo($$('.ct-steps li, .ct-mail'), { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: D.m, stagger: 0.08, delay: 0.7 });
      }

      /* 13. 404: the address bar is wrong, the page says so, the cursor offers the way out */
      var nf = $('[data-nf]');
      if (nf) nfMoment(nf);
      function nfMoment(win) {
        var big = $$('.nf-big span', win), sug = $$('.nf-sug li', win), cur = $('.nf-cursor', win), target = $('.nf-sug a[href="/work/"]', win);
        var urlB = $('.nf-url b', win), full = urlB.textContent;
        urlB.textContent = '';
        gsap.set(big, { yPercent: 100, opacity: 0 });
        gsap.set(sug, { opacity: 0, y: 8 });
        var typed = { n: 0 };
        var tl = gsap.timeline({ delay: 0.6 });
        tl.fromTo(win, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: D.l }, 0)
          .to(typed, { n: full.length, duration: Math.min(1, 0.04 * full.length), ease: 'none', onUpdate: function () { urlB.textContent = full.slice(0, Math.round(typed.n)); } }, 0.4)
          .to(big, { yPercent: 0, opacity: 1, duration: D.m, stagger: 0.06 }, '+=0.2')
          .to(sug, { opacity: 1, y: 0, duration: D.s, stagger: 0.08 }, '-=0.2');
        if (cur && target && wide) {
          var rel = function (fx, fy) { var r = target.getBoundingClientRect(), o = win.getBoundingClientRect(); return { x: r.left - o.left + r.width * fx, y: r.top - o.top + r.height * fy }; };
          tl.set(cur, { x: function () { return win.offsetWidth * 0.9; }, y: function () { return win.offsetHeight * 0.95; } }, '+=0.3')
            .to(cur, { opacity: 1, duration: D.xs })
            .to(cur, { x: function () { return rel(0.42, 0.5).x; }, duration: D.l, ease: IO }, '<')
            .to(cur, { y: function () { return rel(0.42, 0.5).y; }, duration: D.l, ease: IN }, '<')
            .call(function () { target.classList.add('is-hover'); })
            .to(cur, { scale: 0.88, duration: D.xs / 2, ease: IO })
            .to(cur, { scale: 1, duration: D.xs })
            .to(cur, { opacity: 0, x: '+=20', y: '+=16', duration: D.s, ease: IO }, '+=0.5')
            .call(function () { target.classList.remove('is-hover'); });
        }
      }

      /* closing statement and footer wordmark: same scrubbed width axis as the homepage */
      if ($('.close-h .cl')) gsap.fromTo('.close-h .cl', { '--w': 78 }, { '--w': 96, ease: 'none', stagger: 0.04, scrollTrigger: { trigger: '.close', start: 'top 85%', end: 'center 60%', scrub: 0.4 } });
      if ($('[data-word]')) gsap.fromTo('[data-word]', { '--w': 84 }, { '--w': 116, ease: 'none', scrollTrigger: { trigger: '.ftr', start: 'top bottom', end: 'bottom bottom', scrub: 0.4 } });

      return function () { ambient.length = 0; };
    });
  }
})();
