// Silent videos (showreel, Services and Work clips; no GSAP needed). Each [data-reel] plays only while in view, never by
// itself with reduced motion or Save-Data, and swaps its native controls for one Pause/Play button (WCAG 2.2.2) named
// from its markup ("Play showreel" / "Pause showreel"). A press of Pause is remembered. Without JS the controls stay.
(() => {
  const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const saveData = window.navigator?.connection?.saveData;
  const NARROW = '(max-width: 640px)'; // the showreel's vertical cut; home.css turns its frame 9:16 at the same width

  document.querySelectorAll('[data-reel]').forEach(reel => {
    const video = reel.querySelector('video');
    const toggle = reel.querySelector('[data-reel-toggle]');
    if (!video || !toggle) return;
    if (video.dataset.narrowSrc && window.matchMedia?.(NARROW).matches) {
      const source = video.querySelector('source');
      if (source) source.setAttribute('src', video.dataset.narrowSrc);
      if (video.dataset.narrowPoster) video.setAttribute('poster', video.dataset.narrowPoster);
      video.load(); // preload="none": this picks up the new source without downloading it yet
    }
    const noun = String(toggle.textContent).trim().replace(/^Play\s+/, '') || 'video';
    let wanted = !still && !saveData; // the visitor's choice once they press the button
    let inView = false;
    const label = () => { toggle.textContent = (video.paused ? 'Play ' : 'Pause ') + noun; };
    const play = () => {
      let attempt;
      try { attempt = video.play(); } catch (error) { attempt = null; }
      if (attempt && typeof attempt.then === 'function') attempt.then(label, label); // refused (e.g. Low Power Mode): shows Play
      label();
    };
    video.muted = true;
    video.removeAttribute('controls');
    video.addEventListener('play', label);
    video.addEventListener('pause', label);
    toggle.addEventListener('click', () => {
      wanted = video.paused;
      if (wanted) play();
      else video.pause();
      label();
    });
    if (window.IntersectionObserver) {
      new window.IntersectionObserver(entries => {
        inView = entries[entries.length - 1].isIntersecting;
        if (inView && wanted && video.paused) play();
        else if (!inView && !video.paused) video.pause();
      }, { threshold: 0.25 }).observe(video);
    }
    toggle.hidden = false;
    label();
  });
})();
