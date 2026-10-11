/* Cendavo motion boot: loaded in <head> without defer on pages that use GSAP (external file, CSP script-src 'self').
   Adds .js, adds .motion unless reduced motion is requested, and adds .ns-intro for the homepage intro only when the
   script tag opts in with data-intro, the URL has no #hash and the intro has not run in this browser session.
   A timer removes .ns-intro after 2.5 s whatever happens later, so the panel can never stay over the page. */
(function (d, w) {
  var c = d.documentElement.classList, me = d.currentScript, seen = true;
  c.add('js');
  if (!w.matchMedia || w.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  c.add('motion');
  if (!me || !me.hasAttribute('data-intro') || w.location.hash) return;
  try { seen = !!w.sessionStorage.getItem('cendavo-intro'); w.sessionStorage.setItem('cendavo-intro', '1'); } catch (e) { seen = true; }
  if (seen) return;
  c.add('ns-intro');
  w.setTimeout(function () { c.remove('ns-intro'); }, 2500);
})(document, window);
