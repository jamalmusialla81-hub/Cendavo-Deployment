// The site shell, on every page. The collapsed mobile menu is CSS-scoped to .js, so the navigation stays visible if this
// script never runs.
document.documentElement.classList.add('js');
const menu = document.querySelector('[data-menu]');
const nav = document.querySelector('[data-nav]');
const header = document.querySelector('.site-header');
const setMenu = open => {
  nav.classList.toggle('open', open);
  menu.setAttribute('aria-expanded', String(open));
  if (open) showHeader();
};
menu?.addEventListener('click', () => setMenu(!nav.classList.contains('open')));
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
    const next = navHidden(hidden, lastY, y, Boolean(nav?.classList.contains('open')));
    if (Math.abs(y - lastY) > NAV_STEP || y <= NAV_TOP) lastY = y;
    if (next === hidden) return;
    hidden = next;
    header.classList.toggle('is-hidden', hidden);
  }, { passive: true });
  header.addEventListener('focusin', showHeader);
}
// 404 (Task 34): the browser window on the page names the address that was asked for, as text only (never markup).
const asked = document.querySelector('[data-nf-path]');
if (asked) {
  const path = window.location.pathname || '/';
  asked.textContent = path.length > 42 ? path.slice(0, 41) + '…' : path;
}
