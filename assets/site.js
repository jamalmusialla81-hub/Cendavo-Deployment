// The collapsed mobile menu is CSS-scoped to .js, so the navigation stays visible if this script never runs.
document.documentElement.classList.add('js');
const menu = document.querySelector('[data-menu]');
const nav = document.querySelector('[data-nav]');
menu?.addEventListener('click', () => {
  const open = nav.classList.toggle('open');
  menu.setAttribute('aria-expanded', String(open));
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || !menu || !nav?.classList.contains('open')) return;
  nav.classList.remove('open');
  menu.setAttribute('aria-expanded', 'false');
  // Only move focus when the toggle is actually visible (narrow layouts).
  if (getComputedStyle(menu).display !== 'none') menu.focus();
});
