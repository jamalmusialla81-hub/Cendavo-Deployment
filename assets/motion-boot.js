/* Cendavo motion boot, in <head> without defer on GSAP pages. Adds .js; unless reduced motion is requested, adds .motion and
   .ph-wait (CSS holds page openings at their start state; motion.js or home.js removes it), plus .ns-intro on a first
   visit to / without a #hash. Timers drop both classes after 2.5 s whatever happens, so nothing stays hidden. */
(function (d, w) {
  var c = d.documentElement.classList, me = d.currentScript, seen = true;
  c.add('js');
  if (!w.matchMedia || w.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  c.add('motion');
  c.add('ph-wait');
  w.setTimeout(function () { c.remove('ph-wait'); }, 2500);
  if (!me || !me.hasAttribute('data-intro') || w.location.hash) return;
  try { seen = !!w.sessionStorage.getItem('cendavo-intro'); w.sessionStorage.setItem('cendavo-intro', '1'); } catch (e) { seen = true; }
  if (seen) return;
  c.add('ns-intro');
  w.setTimeout(function () { c.remove('ns-intro'); }, 2500);
})(document, window);
