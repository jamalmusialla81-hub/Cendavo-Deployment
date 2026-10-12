/* Cendavo — Liquid Glass inner pages: 3D fan-in reveals, the About film opening from a glass lens, the close drift,
   and the global pause reaching the WebGL moment and the colour fields. Motion only with no-preference. */
(function () {
  'use strict';
  function $$(s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); }
  document.addEventListener('DOMContentLoaded', function () {
    var G = window.__glass || {};
    var btn = document.querySelector('[data-motion-global]');
    if (btn) btn.addEventListener('click', function () {
      G.paused = btn.getAttribute('aria-pressed') === 'true';
      document.documentElement.classList.toggle('is-paused', !!G.paused);
      if (G.onPauseChange) G.onPauseChange(G.paused);
    });
    /* posters stay painted until the video has a frame (no black screens in a fast scroll) */
    $$('video[poster]').forEach(function (v) { v.style.backgroundImage = 'url("' + v.getAttribute('poster') + '")'; });
    var gsap = window.gsap, ST = window.ScrollTrigger;
    if (!gsap || !ST || !window.matchMedia('(prefers-reduced-motion: no-preference)').matches) return;
    var wide = window.matchMedia('(min-width: 761px)').matches;

    /* panels and media fan in from depth, alternating their angle, then settle flat */
    var sel = '.queue, .redir, .month, .quote-paper, .promise, .ct-form, .vig, .bench, .photo, .cs-screens figure, .mount, .tl li, .inc-card, .who-card';
    var els = $$(sel).filter(function (el) { return !el.closest('.pg-hero') && !el.closest('[data-stagger]') && !el.closest('.close') && !el.parentElement.closest(sel); });
    els.forEach(function (el, i) {
      var side = i % 2 ? 1 : -1;
      gsap.fromTo(el, { opacity: 0, y: 90, z: -320, rotationX: 14, rotationY: wide ? side * 16 : 0, transformPerspective: 1400, transformOrigin: '50% 100%' },
        { opacity: 1, y: 0, z: 0, rotationX: 0, rotationY: 0, duration: 1.6, ease: 'expo.out', clearProps: 'transform', scrollTrigger: { trigger: el, start: 'top 92%', once: true } });
    });

    /* About: the launch film opens from a glass lens into its full frame */
    var lens = document.querySelector('[data-film-lens]');
    if (lens) {
      /* at rest the whole film frame is shown, scaled down inside the lens (never cropped); it grows to full size */
      gsap.fromTo(lens, { '--lr': wide ? '40px' : '24px', '--lrx': '9deg', '--ls': wide ? 0.68 : 0.86, '--lo': 1 },
        { '--lr': '0px', '--lrx': '0deg', '--ls': 1, '--lo': 0, ease: 'none', scrollTrigger: { trigger: lens, start: 'top 95%', end: 'top 12%', scrub: 0.6 } });
    }

    /* Pricing: the glass quote card tilts toward the pointer */
    var qp = document.querySelector('.quote-paper');
    if (qp && window.matchMedia('(pointer: fine)').matches) {
      var qy = { v: -14 }, qx = { v: 6 };
      document.querySelector('.pg-hero').addEventListener('pointermove', function (e) {
        var r = qp.getBoundingClientRect(), nx = (e.clientX - r.left) / r.width - 0.5, ny = (e.clientY - r.top) / r.height - 0.5;
        gsap.to(qy, { v: -14 + nx * 10, duration: 1, ease: 'power3.out', overwrite: true, onUpdate: function () { qp.style.setProperty('--qy', qy.v + 'deg'); } });
        gsap.to(qx, { v: 6 - ny * 8, duration: 1, ease: 'power3.out', overwrite: true, onUpdate: function () { qp.style.setProperty('--qx', qx.v + 'deg'); } });
      });
    }

    /* closing band: the photograph drifts under the glass panel, the panel lifts out of depth */
    $$('.close').forEach(function (c) {
      gsap.fromTo(c, { '--cy': '-50px' }, { '--cy': '50px', ease: 'none', scrollTrigger: { trigger: c, start: 'top bottom', end: 'bottom top', scrub: true } });
      var panel = c.querySelector('.close-panel');
      if (panel) gsap.fromTo(panel, { y: 80, opacity: 0, scale: 0.95, rotationX: 10, transformPerspective: 1400 }, { y: 0, opacity: 1, scale: 1, rotationX: 0, duration: 1.6, ease: 'expo.out', scrollTrigger: { trigger: c, start: 'top 70%', once: true } });
    });
  });
})();
