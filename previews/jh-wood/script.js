/* Cendavo concept preview — shared behaviour. No network requests. */
(function () {
  'use strict';
  var root = document.documentElement;
  root.classList.add('js');
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Hero entrance */
  window.requestAnimationFrame(function () {
    window.requestAnimationFrame(function () { root.classList.add('is-loaded'); });
  });

  /* Scroll reveals */
  var revealEls = document.querySelectorAll('[data-reveal]');
  if ('IntersectionObserver' in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add('is-in'); });
  }

  /* Sydney time helper */
  function sydneyParts() {
    try {
      var f = new Intl.DateTimeFormat('en-AU', {
        timeZone: 'Australia/Sydney', hour: 'numeric', minute: 'numeric', second: 'numeric',
        weekday: 'short', hour12: false
      });
      var o = {};
      f.formatToParts(new Date()).forEach(function (p) { o[p.type] = p.value; });
      var days = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
      return { h: parseInt(o.hour, 10) % 24, m: parseInt(o.minute, 10), s: parseInt(o.second, 10), d: days[o.weekday] };
    } catch (err) {
      var n = new Date();
      return { h: n.getHours(), m: n.getMinutes(), s: n.getSeconds(), d: n.getDay() };
    }
  }

  /* Live clock dials */
  var clocks = document.querySelectorAll('[data-live-clock]');
  function tick() {
    var t = sydneyParts();
    clocks.forEach(function (c) {
      var h = c.querySelector('.hand-h'), m = c.querySelector('.hand-m'), s = c.querySelector('.hand-s');
      if (h) h.style.setProperty('--deg', ((t.h % 12) * 30 + t.m * 0.5) + 'deg');
      if (m) m.style.setProperty('--deg', (t.m * 6 + t.s * 0.1) + 'deg');
      if (s) s.style.setProperty('--deg', (t.s * 6) + 'deg');
      var label = c.querySelector('[data-clock-text]');
      if (label) {
        var hh = t.h % 12 === 0 ? 12 : t.h % 12;
        label.textContent = hh + ':' + (t.m < 10 ? '0' : '') + t.m + (t.h < 12 ? ' am' : ' pm');
      }
    });
  }
  if (clocks.length) { tick(); window.setInterval(tick, 1000); }

  /* Open / closed status (hours given in data attributes, Sydney time) */
  document.querySelectorAll('[data-open-status]').forEach(function (el) {
    var days = (el.getAttribute('data-days') || '').split(',').map(Number);
    var open = parseFloat(el.getAttribute('data-open'));
    var close = parseFloat(el.getAttribute('data-close'));
    var names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    function fmt(x) { var h = Math.floor(x); var ap = h < 12 ? 'AM' : 'PM'; var hh = h % 12 === 0 ? 12 : h % 12; return hh + ' ' + ap; }
    function update() {
      var t = sydneyParts();
      var now = t.h + t.m / 60;
      var isOpen = days.indexOf(t.d) > -1 && now >= open && now < close;
      var text;
      if (isOpen) {
        text = 'Open now · until ' + fmt(close);
      } else {
        var next = null;
        for (var i = 0; i < 8; i++) {
          var d = (t.d + i) % 7;
          if (days.indexOf(d) > -1 && (i > 0 || now < open)) { next = { d: d, i: i }; break; }
        }
        var when = next ? (next.i === 0 ? 'today' : next.i === 1 ? 'tomorrow' : names[next.d]) : '';
        text = 'Closed now · opens ' + when + ' ' + fmt(open);
      }
      el.textContent = text;
      el.classList.toggle('is-open', isOpen);
      var host = el.closest('[data-status-host]');
      if (host) host.classList.toggle('is-open', isOpen);
      document.querySelectorAll('[data-today-row]').forEach(function (r) {
        r.classList.toggle('is-today', parseInt(r.getAttribute('data-today-row'), 10) === t.d);
      });
    }
    update(); window.setInterval(update, 30000);
  });

  /* Photo previews (FileReader -> data: URLs, nothing leaves the device) */
  document.querySelectorAll('input[type="file"][data-preview]').forEach(function (input) {
    var target = document.getElementById(input.getAttribute('data-preview'));
    var max = parseInt(input.getAttribute('data-max') || '4', 10);
    input.addEventListener('change', function () {
      if (!target) return;
      target.innerHTML = '';
      var files = Array.prototype.slice.call(input.files || [], 0, max);
      files.forEach(function (file) {
        if (!/^image\//.test(file.type)) return;
        var fig = document.createElement('figure');
        fig.className = 'thumb';
        var img = document.createElement('img');
        img.alt = 'Preview of ' + file.name;
        fig.appendChild(img);
        target.appendChild(fig);
        var r = new FileReader();
        r.onload = function () { img.src = r.result; };
        r.readAsDataURL(file);
      });
      var drop = input.closest('.drop, .big-cam');
      if (drop) {
        drop.classList.toggle('has-files', files.length > 0);
        var c = drop.querySelector('[data-file-count]');
        if (c) c.textContent = files.length ? files.length + (files.length === 1 ? ' photo added' : ' photos added') : '';
      }
    });
  });

  /* Multi-step forms */
  document.querySelectorAll('form[data-steps]').forEach(function (form) {
    var steps = Array.prototype.slice.call(form.querySelectorAll('[data-step]'));
    var dots = Array.prototype.slice.call(form.querySelectorAll('[data-step-dot]'));
    var idx = 0;
    function show(i, focus) {
      idx = Math.max(0, Math.min(steps.length - 1, i));
      steps.forEach(function (s, n) { s.hidden = n !== idx; });
      dots.forEach(function (d, n) {
        d.classList.toggle('is-done', n < idx);
        d.classList.toggle('is-current', n === idx);
        if (n === idx) d.setAttribute('aria-current', 'step'); else d.removeAttribute('aria-current');
      });
      var counter = form.querySelector('[data-step-count]');
      if (counter) counter.textContent = 'Step ' + (idx + 1) + ' of ' + steps.length;
      if (focus) {
        var h = steps[idx].querySelector('legend, h3, [data-step-title]');
        if (h) { h.setAttribute('tabindex', '-1'); h.focus({ preventScroll: true }); }
        var top = form.getBoundingClientRect().top + window.pageYOffset - 90;
        if (window.pageYOffset > top) window.scrollTo({ top: top, behavior: reduce ? 'auto' : 'smooth' });
      }
    }
    function valid(step) {
      var fields = step.querySelectorAll('input, select, textarea');
      for (var i = 0; i < fields.length; i++) {
        if (!fields[i].checkValidity()) { fields[i].reportValidity(); return false; }
      }
      return true;
    }
    form.addEventListener('click', function (e) {
      var nx = e.target.closest('[data-next]');
      var pv = e.target.closest('[data-prev]');
      if (nx) { e.preventDefault(); if (valid(steps[idx])) show(idx + 1, true); }
      if (pv) { e.preventDefault(); show(idx - 1, true); }
    });
    form.addEventListener('preview:reset', function () { show(0, false); });
    show(0, false);
  });

  /* Preview-only submit: never sends anything */
  document.querySelectorAll('form[data-preview-form]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!form.checkValidity()) { form.reportValidity(); return; }
      var out = document.getElementById(form.getAttribute('data-preview-form'));
      if (out) {
        out.hidden = false;
        out.classList.remove('is-shown');
        void out.offsetWidth;
        out.classList.add('is-shown');
        out.setAttribute('tabindex', '-1');
        out.focus({ preventScroll: true });
        out.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
      }
    });
  });

  /* Prefill from repair guide / service cards */
  document.querySelectorAll('[data-prefill]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-prefill');
      var input = document.getElementById(id);
      if (input) {
        if (input.type === 'checkbox' || input.type === 'radio') input.checked = true;
        else input.value = btn.getAttribute('data-value') || input.value;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        btn.classList.add('is-added');
        var t = btn.lastChild;
        if (t && t.nodeType === 3) t.data = 'Added to your quote';
      }
    });
  });

  /* Decorative ticket number */
  var ticketNo = String(1000 + Math.floor(Math.random() * 8999));
  document.querySelectorAll('[data-ticket-no]').forEach(function (el) { el.textContent = ticketNo; });

  /* Header shadow on scroll */
  var header = document.querySelector('.site-header');
  if (header) {
    var onScroll = function () { header.classList.toggle('is-scrolled', window.pageYOffset > 40); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }


  /* Mobile menu */
  var menuBtn = document.querySelector('.menu-btn');
  var nav = document.getElementById('site-nav');
  if (menuBtn && nav) {
    var setMenu = function (open) {
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      nav.classList.toggle('is-open', open);
      var lbl = menuBtn.querySelector('.menu-label');
      if (lbl) lbl.textContent = open ? 'Close' : 'Menu';
    };
    menuBtn.addEventListener('click', function () { setMenu(menuBtn.getAttribute('aria-expanded') !== 'true'); });
    nav.addEventListener('click', function (e) { if (e.target.closest('a')) setMenu(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { setMenu(false); } });
    document.addEventListener('click', function (e) { if (!e.target.closest('.site-header')) setMenu(false); });
  }

  /* Picker (tabs) */
  document.querySelectorAll('[data-picker]').forEach(function (root) {
    var tabs = Array.prototype.slice.call(root.querySelectorAll('[data-pick]'));
    var panels = Array.prototype.slice.call(root.querySelectorAll('[data-panel]'));
    function select(key, focus) {
      tabs.forEach(function (t) {
        var on = t.getAttribute('data-pick') === key;
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.setAttribute('tabindex', on ? '0' : '-1');
        if (on && focus) t.focus();
      });
      panels.forEach(function (p) {
        var on = p.getAttribute('data-panel') === key;
        p.hidden = !on;
        p.classList.toggle('is-active', on);
      });
      root.setAttribute('data-current', key);
    }
    tabs.forEach(function (t, i) {
      t.addEventListener('click', function () { select(t.getAttribute('data-pick'), false); });
      t.addEventListener('keydown', function (e) {
        var d = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : (e.key === 'ArrowLeft' || e.key === 'ArrowUp') ? -1 : 0;
        if (!d) return;
        e.preventDefault();
        var n = tabs[(i + d + tabs.length) % tabs.length];
        select(n.getAttribute('data-pick'), true);
      });
    });
    var first = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0] || tabs[0];
    if (first) select(first.getAttribute('data-pick'), false);
  });

  /* Prefill forms from the URL (e.g. quote.html?repair=Heels) */
  try {
    var params = new URLSearchParams(window.location.search);
    params.forEach(function (value, key) {
      var fields = document.querySelectorAll('form [name="' + key.replace(/"/g, '') + '"]');
      fields.forEach(function (f) {
        if (f.type === 'checkbox' || f.type === 'radio') { if (f.value === value) f.checked = true; }
        else if (f.tagName === 'SELECT') {
          for (var i = 0; i < f.options.length; i++) { if ((f.options[i].value || f.options[i].text) === value) f.selectedIndex = i; }
        }
      });
    });
  } catch (err) { /* no-op */ }

  /* Year */
  document.querySelectorAll('[data-year]').forEach(function (el) { el.textContent = new Date().getFullYear(); });
})();
