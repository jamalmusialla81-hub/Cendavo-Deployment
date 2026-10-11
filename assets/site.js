// Re-announce identical messages: clear the live region, then set text next frame.
const announce = (node, message) => {
  if (!node) return;
  node.textContent = '';
  requestAnimationFrame(() => { node.textContent = message; });
};
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
const brief = document.querySelector('[data-brief]');
const briefStatus = document.querySelector('[data-brief-status]');
brief?.addEventListener('submit', event => {
  event.preventDefault();
  const data = new FormData(brief);
  const lines = [
    'CENDAVO PROJECT BRIEF',
    'Business type: ' + data.get('business'),
    'Main admin challenge: ' + data.get('challenge'),
    'Useful first step: ' + data.get('priority'),
    'Preferred contact method: ' + data.get('contact'),
    '',
    'This brief stays on your device until you choose to share it.'
  ];
  const output = document.querySelector('[data-brief-output]');
  output.value = lines.join('\n');
  document.querySelector('[data-brief-result]').hidden = false;
  output.focus();
  announce(briefStatus, 'Your brief is ready. Copy it to share when you choose.');
});
document.querySelector('[data-brief-copy]')?.addEventListener('click', async () => {
  const output = document.querySelector('[data-brief-output]');
  try {
    await navigator.clipboard.writeText(output.value);
    announce(briefStatus, 'Copied to clipboard.');
  } catch {
    output.focus();
    output.select();
    announce(briefStatus, 'Could not copy automatically. The brief is selected: copy it by hand.');
  }
});
