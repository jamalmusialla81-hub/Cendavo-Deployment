/* Decides whether the WebGL glass hero runs. It never runs for reduced motion, Save-Data or without WebGL:
   those visitors keep the still render (assets/hero-glass-poster*.jpg) that is already in the page. */
const G = (window.__glass = window.__glass || { heroP: 0, paused: false, pointer: { x: 0, y: 0 } });
const host = document.querySelector('[data-gl]');
const poster = new URLSearchParams(location.search).has('poster');

function webglOK() {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; }
}
const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const saveData = !!(navigator.connection && navigator.connection.saveData);

if (host && webglOK() && (poster || (!reduce && !saveData))) {
  const mod = host.hasAttribute('data-gl-kind') ? '/gl-page.js' : '/gl-scene.js';
  const start = () => import(mod).then((m) => m.start(host, { poster })).catch((e) => console.warn('glass hero unavailable', e));
  /* after first paint: let the headline and poster land first */
  const later = () => (window.requestIdleCallback ? requestIdleCallback(start, { timeout: 600 }) : setTimeout(start, 200));
  if (document.readyState === 'complete') later(); else window.addEventListener('load', later, { once: true });
}
