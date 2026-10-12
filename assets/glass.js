// Liquid Glass shell for the motion pages (Task 37), after GSAP and Lenis: the pointer light on glass panels, the edge
// refraction filter (Chromium only), Lenis smooth scrolling and the slow drift of the colour-field atmosphere. Nothing
// here hides or moves content: without it every panel is plain frosted glass and scrolling is native. Under reduced
// motion there is no Lenis, no drift and no moving light; under Save-Data no refraction maps are drawn.
(() => {
  const win = window, doc = document, root = doc.documentElement;
  const motionOK = Boolean(win.matchMedia?.('(prefers-reduced-motion: no-preference)').matches);
  const saveData = Boolean(win.navigator?.connection?.saveData);
  // Shared with reel.js (Pause motion), home.js (hero scroll) and the WebGL hero (glass-scene.js).
  const G = win.__glass = win.__glass || { paused: false, heroP: 0, pointer: { x: 0, y: 0 } };
  G.pointer = G.pointer || { x: 0, y: 0 };
  const pauseFns = G.pauseFns = G.pauseFns || [];
  G.onPauseChange = paused => pauseFns.forEach(fn => fn(paused));
  const $$ = selector => Array.from(doc.querySelectorAll(selector));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const GLASS = '.lg, .site-header .nav';

  // Pointer light: each visible panel's highlight sits where the pointer is (a virtual sun above the page otherwise).
  const visible = new Set();
  let px = null, py = null, raf = 0;
  const paint = () => {
    raf = 0;
    const lx = px === null ? win.innerWidth * 0.3 : px, ly = py === null ? -win.innerHeight * 0.2 : py;
    visible.forEach(el => {
      const r = el.getBoundingClientRect();
      if (!r.width) return;
      el.style.setProperty('--mx', clamp((lx - r.left) / r.width * 100, -30, 130).toFixed(1) + '%');
      el.style.setProperty('--my', clamp((ly - r.top) / r.height * 100, -40, 140).toFixed(1) + '%');
    });
  };
  const schedule = () => { if (!raf) raf = win.requestAnimationFrame(paint); };
  if (motionOK && win.IntersectionObserver) {
    const io = new win.IntersectionObserver(entries => {
      entries.forEach(e => (e.isIntersecting ? visible.add(e.target) : visible.delete(e.target)));
      schedule();
    }, { rootMargin: '80px' });
    $$(GLASS).forEach(el => io.observe(el));
    win.addEventListener('pointermove', e => {
      if (e.pointerType === 'touch') return;
      px = e.clientX; py = e.clientY;
      G.pointer.x = e.clientX / win.innerWidth * 2 - 1;
      G.pointer.y = e.clientY / win.innerHeight * 2 - 1;
      schedule();
    }, { passive: true });
    win.addEventListener('scroll', schedule, { passive: true });
  }

  // Edge refraction (Chromium: backdrop-filter accepts an SVG filter). One displacement map per panel size: the backdrop
  // bends inward along a band at the rounded edge, flat in the middle so text behind stays steady.
  const brands = win.navigator?.userAgentData?.brands || [];
  const defs = doc.querySelector('[data-lg-defs]');
  if (defs && motionOK && !saveData && brands.some(b => /Chromium/.test(b.brand))) {
    root.classList.add('lg-refract');
    const NS = defs.namespaceURI, cache = {}; // the SVG namespace, read from the page's own <defs>
    let n = 0;
    const map = (w, h, r, band) => {
      const cw = Math.max(2, Math.round(w / 2)), ch = Math.max(2, Math.round(h / 2));
      const c = doc.createElement('canvas');
      c.width = cw; c.height = ch;
      const ctx = c.getContext('2d'), img = ctx.createImageData(cw, ch), d = img.data, hw = w / 2, hh = h / 2;
      r = Math.min(r, hw, hh);
      for (let j = 0; j < ch; j++) for (let i = 0; i < cw; i++) {
        const x = i * 2 + 1 - hw, y = j * 2 + 1 - hh, qx = Math.abs(x) - (hw - r), qy = Math.abs(y) - (hh - r);
        const depth = r - Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) - Math.min(Math.max(qx, qy), 0);
        let nx = 0, ny = 0, mag = 0;
        if (depth > 0 && depth < band) {
          if (qx > 0 && qy > 0) { const l = Math.hypot(qx, qy) || 1; nx = qx / l * Math.sign(x); ny = qy / l * Math.sign(y); }
          else if (qx > qy) nx = Math.sign(x); else ny = Math.sign(y);
          const t = 1 - depth / band; mag = t * t * (3 - 2 * t);
        }
        const k = (j * cw + i) * 4;
        d[k] = 128 - nx * mag * 127; d[k + 1] = 128 - ny * mag * 127; d[k + 2] = 128; d[k + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
      return c.toDataURL('image/png');
    };
    const make = (tag, attrs) => { const el = doc.createElementNS(NS, tag); Object.keys(attrs).forEach(k => el.setAttribute(k, attrs[k])); return el; };
    const filterFor = (w, h, r) => {
      const key = w + 'x' + h + 'r' + r;
      if (cache[key]) return cache[key];
      const band = Math.max(8, Math.min(30, Math.min(w, h) * 0.32)), id = 'lgf' + n++, box = { x: 0, y: 0, width: w, height: h };
      const f = make('filter', { id, filterUnits: 'userSpaceOnUse', primitiveUnits: 'userSpaceOnUse', 'color-interpolation-filters': 'sRGB', ...box });
      f.appendChild(make('feImage', { href: map(w, h, r, band), preserveAspectRatio: 'none', result: 'm', ...box }));
      f.appendChild(make('feDisplacementMap', { in: 'SourceGraphic', in2: 'm', scale: Math.round(Math.min(band * 1.1, 34)), xChannelSelector: 'R', yChannelSelector: 'G' }));
      defs.appendChild(f);
      return (cache[key] = id);
    };
    const apply = () => $$(GLASS).forEach(el => {
      const w = Math.round(el.offsetWidth), h = Math.round(el.offsetHeight);
      if (!w || !h || w * h > 1400 * 900) return;
      const radius = getComputedStyle(el).borderTopLeftRadius;
      const r = /%/.test(radius) ? Math.min(w, h) / 2 : parseFloat(radius) || 0;
      el.style.setProperty('--lg-filter', 'blur(10px) url(#' + filterFor(w, h, Math.round(r)) + ') saturate(1.8) brightness(1.05)');
    });
    let timer = 0;
    win.addEventListener('resize', () => { win.clearTimeout(timer); timer = win.setTimeout(apply, 300); });
    (doc.fonts?.ready || Promise.resolve()).then(apply);
    G.reapplyRefraction = apply;
  }
  if (!motionOK) return;

  // Lenis smooth scrolling, driven by GSAP's ticker so ScrollTrigger stays in step. Touch scrolling stays native.
  const gsap = win.gsap, ScrollTrigger = win.ScrollTrigger;
  if (win.Lenis) {
    const lenis = G.lenis = new win.Lenis({ lerp: 0.1, smoothWheel: true });
    if (gsap && ScrollTrigger) {
      lenis.on('scroll', ScrollTrigger.update);
      gsap.ticker.add(t => lenis.raf(t * 1000));
    } else {
      const tick = t => { lenis.raf(t); win.requestAnimationFrame(tick); };
      win.requestAnimationFrame(tick);
    }
  }

  // The atmosphere drifts on slow, separate sine paths (40 to 70 s), transform only; held by Pause motion and a hidden tab.
  const fields = $$('.atmos i');
  let drift = 0, t0 = 0;
  const step = now => {
    t0 = t0 || now;
    const t = (now - t0) / 1000;
    fields.forEach((el, i) => {
      const s = 0.09 + i * 0.025;
      el.style.transform = 'translate3d(' + (Math.sin(t * s + i * 1.7) * 5).toFixed(2) + 'vmax,' + (Math.cos(t * s * 0.8 + i) * 4).toFixed(2) + 'vmax,0)';
    });
    drift = win.requestAnimationFrame(step);
  };
  const run = () => {
    const on = !G.paused && !doc.hidden;
    if (on && !drift) drift = win.requestAnimationFrame(step);
    else if (!on && drift) { win.cancelAnimationFrame(drift); drift = 0; }
  };
  if (fields.length) {
    pauseFns.push(run);
    doc.addEventListener('visibilitychange', run);
    run();
  }
})();
