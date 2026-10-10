const menu = document.querySelector('[data-menu]');
menu?.addEventListener('click', () => {
  const nav = document.querySelector('[data-nav]');
  const open = nav.classList.toggle('open');
  menu.setAttribute('aria-expanded', String(open));
});
const brief = document.querySelector('[data-brief]');
brief?.addEventListener('submit', async event => {
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
  const text = lines.join('\n');
  const output = document.querySelector('[data-brief-output]');
  output.value = text;
  output.hidden = false;
  document.querySelector('[data-brief-copy]').hidden = false;
  document.querySelector('[data-brief-status]').textContent = 'Your brief is ready. Copy it to share when you choose.';
});
document.querySelector('[data-brief-copy]')?.addEventListener('click', async () => {
  const output = document.querySelector('[data-brief-output]');
  await navigator.clipboard.writeText(output.value);
  document.querySelector('[data-brief-status]').textContent = 'Copied to clipboard.';
});
