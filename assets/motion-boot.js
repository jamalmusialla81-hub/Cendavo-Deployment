/* Cendavo motion boot, in <head> without defer on GSAP pages. Adds .js; unless reduced motion is requested, adds .motion and
   .ph-wait (CSS holds page openings at their start state; motion.js or home.js removes it). A timer drops .ph-wait after
   2.5 s whatever happens, so nothing stays hidden. (Daylight, Task 33: there is no first-visit intro any more.) */
(function (d, w) {
  var c = d.documentElement.classList;
  c.add('js');
  if (!w.matchMedia || w.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  c.add('motion');
  c.add('ph-wait');
  w.setTimeout(function () { c.remove('ph-wait'); }, 2500);
})(document, window);
