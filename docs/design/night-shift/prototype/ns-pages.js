/* Cendavo — Night Shift inner pages (ns-pages.js)
   Page-head motion, scroll reveals and the contact form's prototype behaviour.
   All content is visible without this file; motion runs only without reduced motion. */
(function () {
  'use strict';
  var d = document, root = d.documentElement;
  var $$ = function (s, r) { return Array.prototype.slice.call((r || d).querySelectorAll(s)); };
  function ready() { root.classList.add('ns-pready'); }

  /* ---------- Contact form (prototype: validates, never sends) ----------
     Production replaces this with /assets/enquiry.js, which uses the same hooks. */
  var form = d.querySelector('[data-enquiry]');
  if (form) {
    var status = d.querySelector('[data-enquiry-status]');
    var FIELDS = ['name', 'email', 'phone', 'business', 'website', 'service', 'message'];
    var MSG = {
      name: 'Enter your name (up to 100 characters).',
      email: 'Enter a valid email address, like name@example.com.',
      phone: 'Enter a phone number using digits, spaces and + ( ) - only (up to 30 characters).',
      business: 'Keep the business name to 120 characters or fewer.',
      website: 'Enter a website address, like example.com.au (up to 200 characters).',
      service: 'Choose the service you are interested in.',
      message: 'Tell us a little about your project (10 to 2000 characters).'
    };
    var check = function (f, v) {
      v = (v || '').trim();
      switch (f) {
        case 'name': return v && v.length <= 100;
        case 'email': return v.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
        case 'phone': return !v || (v.length <= 30 && /^[0-9+() -]+$/.test(v) && /[0-9]/.test(v));
        case 'business': return v.length <= 120;
        case 'website': return !v || (v.length <= 200 && /^[^\s.]+(\.[^\s.]+)+/.test(v.replace(/^https?:\/\//i, '')));
        case 'service': return ['website-design', 'website-redesign', 'maintenance', 'not-sure'].indexOf(v) > -1;
        case 'message': return v.length >= 10 && v.length <= 2000;
      }
      return true;
    };
    var announce = function (text, tone) {
      if (!status) return;
      status.textContent = '';
      status.setAttribute('data-tone', tone);
      requestAnimationFrame(function () { status.textContent = text; });
    };
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var first = null;
      FIELDS.forEach(function (f) {
        var c = form.elements[f], slot = form.querySelector('[data-error-for="' + f + '"]');
        var ok = !c || check(f, c.value);
        if (slot) slot.textContent = ok ? '' : MSG[f];
        if (!c) return;
        if (ok) c.removeAttribute('aria-invalid');
        else { c.setAttribute('aria-invalid', 'true'); if (!first) first = c; }
      });
      if (first) { first.focus(); announce('Please check the highlighted fields.', 'error'); return; }
      form.reset();
      announce('Prototype only: nothing was sent. On the live site, your enquiry goes to Cendavo and we reply by email to arrange a free 20-minute call.', 'success');
    });
  }

  /* ---------- Motion ---------- */
  if (!window.gsap || !window.ScrollTrigger) { ready(); return; }
  gsap.registerPlugin(ScrollTrigger);
  var mm = gsap.matchMedia();
  mm.add('(prefers-reduced-motion: reduce)', ready);

  mm.add('(prefers-reduced-motion: no-preference)', function () {
    /* Page head: one orchestrated entrance */
    var tl = gsap.timeline({ defaults: { ease: 'power4.out' } });
    var lines = $$('[data-ph] .ln > span');
    if (lines.length) tl.from(lines, { yPercent: 108, duration: 1.1, stagger: .08 }, .05);
    $$('[data-ph-media]').forEach(function (m) {
      tl.fromTo(m, { clipPath: 'inset(0 0 0 100%)' }, { clipPath: 'inset(0 0 0 0%)', duration: 1.4, ease: 'expo.inOut', clearProps: 'clipPath' }, 0);
      var img = m.querySelector('img');
      if (img) tl.from(img, { scale: 1.08, duration: 2, ease: 'power3.out' }, 0);
    });
    var fades = $$('[data-ph-fade]');
    if (fades.length) tl.from(fades, { y: 18, autoAlpha: 0, duration: .9, stagger: .1 }, .45);
    var tiles = $$('.wk-tile');
    if (tiles.length) tl.fromTo(tiles, { clipPath: 'inset(100% 0 0 0)' }, { clipPath: 'inset(0% 0 0 0)', duration: 1.2, stagger: .09, ease: 'expo.inOut', clearProps: 'clipPath' }, .35);
    var quote = d.querySelector('[data-quote]');
    if (quote) {
      tl.from(quote.querySelector('.quote-paper'), { y: 80, rotation: 5, autoAlpha: 0, duration: 1.3 }, .3)
        .from($$('.quote-for, .quote-lines li, .quote-total', quote), { autoAlpha: 0, x: -14, duration: .6, stagger: .07, ease: 'power3.out' }, .85)
        .from(quote.querySelector('figcaption'), { autoAlpha: 0, duration: .6 }, 1.4);
    }
    ready();

    /* Image frames un-mask once as they enter */
    $$('[data-reveal]').forEach(function (el) {
      var img = el.querySelector('img');
      var t = gsap.timeline({ scrollTrigger: { trigger: el, start: 'top 85%', once: true } });
      t.fromTo(el, { clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0% 0)', duration: 1.2, ease: 'expo.inOut', clearProps: 'clipPath' });
      if (img) t.from(img, { scale: 1.1, duration: 1.8, ease: 'power2.out' }, 0);
    });

    /* Device mockups slide into place */
    $$('[data-devices]').forEach(function (el) {
      var items = el.matches('.scr') ? [el] : $$('.scr, .re-frame', el);
      gsap.from(items, { y: 70, autoAlpha: 0, duration: 1.1, stagger: .12, ease: 'power3.out', scrollTrigger: { trigger: el, start: 'top 82%', once: true } });
    });

    /* Gentle parallax (±6%) */
    $$('[data-parallax] img').forEach(function (img) {
      gsap.fromTo(img, { yPercent: -6, scale: 1.14 }, { yPercent: 6, ease: 'none', scrollTrigger: { trigger: img.parentNode, start: 'top bottom', end: 'bottom top', scrub: true } });
    });

    /* Pricing scales draw from the lighter end */
    $$('.scale i').forEach(function (i) {
      gsap.from(i, { scaleX: 0, transformOrigin: '0 50%', duration: 1.1, ease: 'power3.inOut', scrollTrigger: { trigger: i, start: 'top 90%', once: true } });
    });
  });
})();
