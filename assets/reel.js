// The one silent-video controller: in view, tab visible, never by itself under reduced motion or Save-Data.
// [data-loop]: after load ("wide": not at <=640px). Pause motion holds all.
(() => {
  const win = window, doc = document;
  const still = win.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const saveData = win.navigator?.connection?.saveData;
  const NARROW = '(max-width: 640px)'; // as home.css
  const narrowNow = Boolean(win.matchMedia?.(NARROW).matches);
  const items = [];
  let loaded = doc.readyState === 'complete';
  const attempt = it => {
    const video = it.video, source = video.querySelector('source');
    // data-src: no download before play
    if (source?.dataset?.src && !source.getAttribute('src')) { source.setAttribute('src', source.dataset.src); video.load(); }
    try { video.play()?.then?.(it.label, it.label); } catch (error) {}
    it.label();
  };
  const sync = it => {
    const go = it.wanted && it.inView && !doc.hidden && (loaded || !it.loop);
    if (go && it.video.paused) attempt(it);
    else if (!go && !it.video.paused) it.video.pause();
  };
  const add = (video, loop, label = () => {}) => {
    const it = { video, loop, label, wanted: !still && !saveData };
    video.muted = true;
    if (win.IntersectionObserver) new win.IntersectionObserver(e => { it.inView = e[e.length - 1].isIntersecting; sync(it); }, { threshold: 0.25 }).observe(video);
    return items.push(it) && it;
  };
  const chapters = (it, list) => {
    const video = it.video, buttons = Array.from(list.querySelectorAll('button[data-t]')), at = b => Number(b.dataset.t);
    const mark = () => {
      const now = (video.currentTime || 0) + 0.05;
      buttons.forEach((b, i) => {
        if (now >= at(b) && !(buttons[i + 1] && now >= at(buttons[i + 1]))) b.setAttribute('aria-current', 'true');
        else b.removeAttribute('aria-current');
      });
    };
    video.addEventListener('timeupdate', mark);
    buttons.forEach(b => b.addEventListener('click', () => { video.currentTime = at(b); it.wanted = true; attempt(it); mark(); }));
    list.hidden = false;
    mark();
  };
  doc.querySelectorAll('[data-reel]').forEach(reel => {
    const video = reel.querySelector('video'), toggle = reel.querySelector('[data-reel-toggle]');
    if (!video || !toggle) return;
    const narrow = Boolean(video.dataset.narrowSrc && narrowNow);
    if (narrow) {
      video.querySelector('source')?.setAttribute('src', video.dataset.narrowSrc);
      if (video.dataset.narrowPoster) video.setAttribute('poster', video.dataset.narrowPoster);
      video.load();
    }
    const noun = String(toggle.textContent).trim().replace(/^Play\s+/, '') || 'video';
    const it = add(video, false, () => { toggle.textContent = (video.paused ? 'Play ' : 'Pause ') + noun; });
    video.removeAttribute('controls');
    ['play', 'pause'].forEach(type => video.addEventListener(type, it.label));
    toggle.addEventListener('click', () => { it.wanted = video.paused; if (it.wanted) attempt(it); else video.pause(); it.label(); });
    toggle.hidden = false;
    it.label();
    const list = video.id && !narrow && doc.querySelector('[data-chapters="' + video.id + '"]');
    if (list) chapters(it, list);
  });
  const loops = Array.from(doc.querySelectorAll('video[data-loop]')).filter(v => !(narrowNow && v.dataset.loop === 'wide')).map(v => add(v, true));
  const motion = doc.querySelector('[data-motion-toggle]');
  if (motion && loops.length) {
    let held = Boolean(still || saveData); // pressed: paused
    const show = () => motion.setAttribute('aria-pressed', String(held));
    motion.addEventListener('click', () => { held = !held; items.forEach(it => { it.wanted = !held; sync(it); it.label(); }); show(); });
    show();
    motion.hidden = false;
  }
  const start = () => { loaded = true; items.forEach(sync); };
  if (!loaded) win.addEventListener('load', () => (win.requestIdleCallback ? win.requestIdleCallback(start, { timeout: 2000 }) : win.setTimeout(start, 200)));
  doc.addEventListener('visibilitychange', () => items.forEach(sync));
})();
