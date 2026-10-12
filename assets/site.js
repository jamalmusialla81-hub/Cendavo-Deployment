// The site shell, on every page. The collapsed mobile menu is CSS-scoped to .js, so the navigation stays visible if this
// script never runs.
document.documentElement.classList.add('js');
const menu = document.querySelector('[data-menu]');
const nav = document.querySelector('[data-nav]');
const header = document.querySelector('.site-header');
// Task 47: while the mobile menu is open the page behind it does not scroll. html.menu-lock sets overflow:hidden only inside
// the mobile breakpoint (site.css), and Lenis (motion pages, window.__glass.lenis, created later by glass.js) is stopped
// too, since it scrolls on its own. Closing, Escape and widening to the desktop layout all release it.
const setMenu = open => {
  nav.classList.toggle('open', open);
  menu.setAttribute('aria-expanded', String(open));
  document.documentElement.classList.toggle('menu-lock', open);
  window.__glass?.lenis?.[open ? 'stop' : 'start']();
  if (open) showHeader();
};
menu?.addEventListener('click', () => setMenu(!nav.classList.contains('open')));
// Widening to the desktop layout closes the menu (Lenis.start is a no-op when it is not stopped).
if (menu) window.matchMedia?.('(max-width: 1080px)').addEventListener?.('change', e => e.matches || setMenu(false));
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || !menu || !nav?.classList.contains('open')) return;
  setMenu(false);
  // Only move focus when the toggle is actually visible (narrow layouts).
  if (getComputedStyle(menu).display !== 'none') menu.focus();
});
// Liquid Glass (Task 37): the glass nav pill steps aside while the visitor scrolls down past the first screenful and comes
// back on any scroll up, near the top, while the menu is open, or as soon as anything in it takes keyboard focus.
// navHidden is the whole decision: (was it hidden, last scroll position it acted on, scroll position now, menu open).
const NAV_TOP = 120, NAV_STEP = 6;
const navHidden = (hidden, last, y, open) => {
  if (open || y <= NAV_TOP) return false;
  if (y > last + NAV_STEP) return true;
  if (y < last - NAV_STEP) return false;
  return hidden;
};
let hidden = false, lastY = window.scrollY || 0;
function showHeader() {
  hidden = false;
  header?.classList.remove('is-hidden');
}
if (header) {
  window.addEventListener('scroll', () => {
    const y = window.scrollY || 0;
    const next = navHidden(hidden, lastY, y, nav?.classList.contains('open'));
    if (Math.abs(y - lastY) > NAV_STEP || y <= NAV_TOP) lastY = y;
    if (next === hidden) return;
    hidden = next;
    header.classList.toggle('is-hidden', hidden);
  }, { passive: true });
  header.addEventListener('focusin', showHeader);
}
// Pause motion (Task 41, WCAG 2.2.2): build_site.py puts one button in the header (Task 46) on every page with ongoing
// motion (WebGL, the drifting atmosphere, the marquee, video loops). Its name stays "Pause motion"; aria-pressed is the
// state, and glass.css swaps its icon from it. It works on its own, video or not: it holds the shared state
// window.__glass.paused and tells every listener through __glass.onPauseChange (the pauseFns fan-out, which glass.js,
// reel.js and the WebGL scenes join). It is shown once this runs and stays put; reduced motion or Save-Data start it pressed.
{
  const toggle = document.querySelector('[data-motion-toggle]');
  if (toggle) {
    const G = window.__glass = window.__glass || { paused: false, heroP: 0, pointer: { x: 0, y: 0 } };
    const fns = G.pauseFns = G.pauseFns || [];
    if (!G.onPauseChange) G.onPauseChange = paused => fns.forEach(fn => fn(paused));
    const still = Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
    G.paused = still || Boolean(window.navigator?.connection?.saveData);
    const show = () => toggle.setAttribute('aria-pressed', String(G.paused));
    toggle.addEventListener('click', () => {
      G.paused = !G.paused;
      show();
      G.onPauseChange?.(G.paused);
    });
    show();
    toggle.hidden = false;
  }
}
// 404 (Task 34): the browser window on the page names the address that was asked for, as text only (never markup).
const asked = document.querySelector('[data-nf-path]');
if (asked) {
  const path = window.location.pathname || '/';
  asked.textContent = path.length > 42 ? path.slice(0, 41) + '…' : path;
}
