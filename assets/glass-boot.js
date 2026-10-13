// Liquid Glass hero boot (homepage and the inner pages; deferred). The hero ships a still render of the glass logo (CSS poster on
// [data-gl]); this decides whether the live WebGL version replaces it. Never with reduced motion, Save-Data, low-end
// desktops (under 4 GB memory or 4 cores or fewer) or without WebGL: those visitors keep the still. Task 57: at 760px and
// below only the homepage loads, in lite mode (G.lite, read by glass-scene.js), and only on a capable phone: at least 4
// cores, at least 4 GB memory if the browser reports it (iPhones do not), and not on a 2g or 3g connection. Inner pages
// keep the still on phones. Otherwise the scene module (three.js r170, about 800 KB) is imported only after the page has loaded and gone
// idle, so it never competes with the headline or the first paint. A failed import or start leaves the still in place.
// Which module loads comes from a fixed list: no data-gl-kind is the homepage scene; slab (Work), panes (Services), sheets
// (Pricing), photos (About) and mark (Contact) the inner-page scene; any other kind imports nothing. No path is ever read from the page.
// Task 48: the WebGL test is the scene's own context: a WebGL2 context (three.js r170 needs WebGL2) made with the renderer's
// attributes and handed to start(), which draws with it. If the import or start fails, or start does not take it, it is
// released at once (WEBGL_lose_context), so no throwaway context is ever left behind.
(() => {
  const win = window, doc = document;
  const MODULES = { home: '/assets/glass-scene.js', slab: '/assets/glass-page.js', panes: '/assets/glass-page.js', sheets: '/assets/glass-page.js',
    photos: '/assets/glass-page.js', mark: '/assets/glass-page.js' };
  const wantsGL = env => !env.reduce && !env.saveData && !env.narrow && !env.lowEnd && env.webgl;
  // site.js (always first) makes the shared state with its fields; every reader defaults paused, heroP and pointer itself
  const G = win.__glass = win.__glass || {};
  G.wantsGL = wantsGL;
  const host = doc.querySelector('[data-gl]');
  if (!host) return;
  const kind = host.getAttribute('data-gl-kind') || 'home';
  // own keys only: an Object.prototype name such as "constructor" imports nothing
  const SCENE = Object.hasOwn(MODULES, kind) && MODULES[kind];
  if (!SCENE) return;
  const mq = q => !!win.matchMedia?.(q).matches;
  const nav = win.navigator || {}, cores = nav.hardwareConcurrency;
  // Task 57: a phone-sized screen (760px and below) is the homepage scene's lite mode, if anything loads
  const lite = mq('(max-width: 760px)');
  const env = {
    reduce: !mq('(prefers-reduced-motion: no-preference)'),
    saveData: !!nav.connection?.saveData,
    // a phone keeps the still unless this is the homepage, it reports at least 4 cores (undefined > 3 is false) and its
    // connection is not slow-2g, 2g or 3g (no 800 KB download on a slow link; unreported is fine)
    narrow: lite && (kind != 'home' || !(cores > 3) || /[23]g/.test(nav.connection?.effectiveType)),
    // low-end: under 4 GB memory, or 4 cores or fewer (on a phone 3 or fewer: 4 - true is 3, and narrow above already needs
    // 4+). A browser that does not report memory (iPhones) or cores is not low-end here (undefined < 4 is false).
    lowEnd: nav.deviceMemory < 4 || cores <= 4 - lite,
    webgl: true,
  };
  if (!wantsGL(env)) return;
  // alpha and powerPreference as the renderer asks for them; antialias is on by default
  const probe = () => {
    try {
      const canvas = doc.createElement('canvas'), context = canvas.getContext('webgl2', { alpha: false, powerPreference: 'high-performance' });
      return context && { canvas, context };
      // no context: undefined, so no WebGL
    } catch {}
  };
  const lose = gl => gl.context.getExtension?.('WEBGL_lose_context')?.loseContext();
  const start = () => {
    const gl = probe();
    // G.lite (Task 57) tells glass-scene.js to run its phone budget; it is set only as the scene is imported
    if (wantsGL({ ...env, webgl: !!gl })) (G.lite = lite, import(SCENE)).then(m => m.start(host, G, gl) || lose(gl)).catch(() => { host.classList.remove('is-live'); lose(gl); });
  };
  const later = () => (win.requestIdleCallback ? win.requestIdleCallback(start, { timeout: 1500 }) : win.setTimeout(start, 300));
  if (doc.readyState === 'complete') later(); else win.addEventListener('load', later, { once: true });
})();
