// Liquid Glass hero boot (homepage and the inner pages; deferred). The hero ships a still render of the glass logo (CSS poster on
// [data-gl]); this decides whether the live WebGL version replaces it. Never with reduced motion, Save-Data, small screens
// (760px and below), low-end devices (under 4 GB memory or 4 cores or fewer) or without WebGL: those visitors keep the
// still. Otherwise the scene module (three.js r170, about 800 KB) is imported only after the page has loaded and gone
// idle, so it never competes with the headline or the first paint. A failed import or start leaves the still in place.
// Which module loads comes from a fixed list: no data-gl-kind is the homepage scene; slab (Work), panes (Services), sheets
// (Pricing), photos (About) and mark (Contact) the inner-page scene; any other kind imports nothing. No path is ever read from the page.
(() => {
  const win = window, doc = document;
  const MODULES = { home: '/assets/glass-scene.js', slab: '/assets/glass-page.js', panes: '/assets/glass-page.js', sheets: '/assets/glass-page.js',
    photos: '/assets/glass-page.js', mark: '/assets/glass-page.js' };
  const wantsGL = env => !env.reduce && !env.saveData && !env.narrow && !env.lowEnd && env.webgl;
  const G = win.__glass = win.__glass || { paused: false, heroP: 0, pointer: { x: 0, y: 0 } };
  G.wantsGL = wantsGL;
  const host = doc.querySelector('[data-gl]');
  if (!host) return;
  const kind = host.getAttribute('data-gl-kind') || 'home';
  const SCENE = Object.prototype.hasOwnProperty.call(MODULES, kind) ? MODULES[kind] : null;
  if (!SCENE) return;
  const mq = query => Boolean(win.matchMedia?.(query).matches);
  const nav = win.navigator || {};
  const env = {
    reduce: !mq('(prefers-reduced-motion: no-preference)'),
    saveData: Boolean(nav.connection?.saveData),
    narrow: mq('(max-width: 760px)'),
    lowEnd: (typeof nav.deviceMemory === 'number' && nav.deviceMemory < 4) || (typeof nav.hardwareConcurrency === 'number' && nav.hardwareConcurrency <= 4),
    webgl: true,
  };
  if (!wantsGL(env)) return;
  const hasWebGL = () => {
    try { const c = doc.createElement('canvas'); return Boolean(c.getContext('webgl2') || c.getContext('webgl')); } catch (error) { return false; }
  };
  const start = () => {
    if (!wantsGL({ ...env, webgl: hasWebGL() })) return;
    import(SCENE).then(m => m.start(host, G)).catch(() => host.classList.remove('is-live'));
  };
  const later = () => (win.requestIdleCallback ? win.requestIdleCallback(start, { timeout: 1500 }) : win.setTimeout(start, 300));
  if (doc.readyState === 'complete') later(); else win.addEventListener('load', later, { once: true });
})();
