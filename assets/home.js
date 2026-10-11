// Homepage before/after comparison. Progressive enhancement: without this script the
// illustration shows both states split at 50% and the controls stay hidden.
(() => {
  const figure = document.querySelector('[data-compare]');
  const controls = figure?.querySelector('[data-compare-controls]');
  const range = controls?.querySelector('input[type="range"]');
  if (!range) return;
  const buttons = controls.querySelectorAll('[data-compare-set]');
  const update = () => {
    const value = Math.min(100, Math.max(0, Number(range.value) || 0));
    figure.style.setProperty('--pos', value + '%');
    buttons.forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.compareSet) === value)));
  };
  range.addEventListener('input', update);
  buttons.forEach(button => button.addEventListener('click', () => {
    range.value = button.dataset.compareSet;
    update();
  }));
  controls.hidden = false;
  update();
})();
