/* Cendavo Night Shift boot flag (loaded synchronously in <head>, CSP-safe).
   Adds .js and .ns-motion; the first-visit intro only on pages that opt in with <html data-intro>.
   Content stays visible if anything later fails (CSS failsafes). */
(function (d) {
  var r = d.documentElement, c = r.classList; c.add('js');
  var still = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still) return;
  c.add('ns-motion');
  if (!r.hasAttribute('data-intro')) return;
  try { if (!sessionStorage.getItem('ns-intro')) c.add('ns-intro'); } catch (e) {}
})(document);
