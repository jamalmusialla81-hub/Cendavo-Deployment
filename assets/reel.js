// The one silent-video controller: plays only at 40% in view with the tab visible, never by itself under reduced motion or
// Save-Data. [data-reel]: a large video with a Pause/Play button (one at a time; Task 34 adds the film's progress and time);
// [data-loop]: a small loop, after load ("wide": not at <=640px), held by Pause motion; [data-hover-src]: a Work tile that
// cross-fades to its loop on hover or focus (fine pointers) or when centred (touch). No file loads before its first play.
(() => {
  const win = window, doc = document;
  const still = win.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const saveData = win.navigator?.connection?.saveData;
  const NARROW = '(max-width: 640px)'; // as home.css and about.css
  const narrowNow = Boolean(win.matchMedia?.(NARROW).matches);
  const fine = Boolean(win.matchMedia?.('(hover: hover) and (pointer: fine)').matches);
  const items = [], previews = [];
  let loaded = doc.readyState === 'complete';
  let held = Boolean(still || saveData); // Pause motion pressed
  const motion = doc.querySelector('[data-motion-toggle]');
  const fab = Boolean(motion?.classList?.contains('motion-fab')); // the fixed button shows only while a loop is on screen
  const showFab = () => { if (fab && doc.activeElement !== motion) motion.hidden = !items.some(it => it.loop && it.inView); };
  const playing = it => !it.video.paused;
  const attempt = it => {
    const video = it.video, source = video.querySelector('source');
    // data-src: no download before play
    if (source?.dataset?.src && !source.getAttribute('src')) { source.setAttribute('src', source.dataset.src); video.load(); }
    try { video.play()?.then?.(it.label, it.label); } catch (error) {}
    if (!it.loop) items.forEach(other => { if (other !== it && !other.loop && playing(other)) other.video.pause(); });
    it.label();
  };
  const sync = it => {
    const busy = !it.loop && items.some(other => other !== it && !other.loop && playing(other)); // one large video at a time
    const go = it.wanted && it.inView && !doc.hidden && (loaded || !it.loop);
    if (go && !busy && it.video.paused) attempt(it);
    else if (!go && playing(it)) it.video.pause();
  };
  const add = (video, loop, label = () => {}) => {
    const it = { video, loop, label, wanted: !still && !saveData };
    video.muted = true;
    if (win.IntersectionObserver) new win.IntersectionObserver(e => { it.inView = e[e.length - 1].isIntersecting; sync(it); showFab(); }, { threshold: 0.4 }).observe(video);
    // Liquid Glass (Task 37): a loop far down the page may carry data-poster instead of poster, so its still is fetched only
    // when it comes near the screen (not with the first load).
    if (video.dataset?.poster && win.IntersectionObserver) {
      const near = new win.IntersectionObserver(e => {
        if (!e[e.length - 1].isIntersecting) return;
        video.setAttribute('poster', video.dataset.poster);
        near.disconnect?.();
      }, { rootMargin: '50% 0px' });
      near.observe(video);
    }
    // When a large video stops, another one in view may take its turn.
    if (!loop) video.addEventListener('pause', () => items.forEach(other => { if (other !== it && !other.loop) sync(other); }));
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
  // The film's progress bar (aria-hidden, scaled with transform) and elapsed time, redrawn every frame while it plays.
  const clock = t => Math.floor(t / 60) + ':' + String(Math.floor(t % 60)).padStart(2, '0');
  const progress = (reel, video) => {
    const bar = reel.querySelector('[data-progress]'), time = reel.querySelector('[data-time]');
    if (!bar && !time) return;
    let frame = 0;
    const paint = () => {
      const length = video.duration || 0, now = Math.min(video.currentTime || 0, length);
      if (bar) bar.style.transform = 'scaleX(' + (length ? now / length : 0) + ')';
      if (time && length) time.textContent = clock(now) + ' / ' + clock(length);
    };
    const tick = () => { paint(); if (!video.paused && win.requestAnimationFrame) frame = win.requestAnimationFrame(tick); };
    video.addEventListener('play', () => { win.cancelAnimationFrame?.(frame); tick(); });
    ['pause', 'seeked', 'loadedmetadata'].forEach(type => video.addEventListener(type, paint));
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
    const it = add(video, false, () => {
      toggle.textContent = (video.paused ? 'Play ' : 'Pause ') + noun;
      toggle.classList?.toggle('is-playing', !video.paused);
    });
    video.removeAttribute('controls');
    ['play', 'pause'].forEach(type => video.addEventListener(type, it.label));
    toggle.addEventListener('click', () => { it.wanted = video.paused; if (it.wanted) attempt(it); else video.pause(); it.label(); });
    toggle.hidden = false;
    const ui = reel.querySelector('[data-reel-ui]');
    if (ui) ui.hidden = false;
    it.label();
    progress(reel, video);
    const list = video.id && !narrow && doc.querySelector('[data-chapters="' + video.id + '"]');
    if (list) chapters(it, list);
  });
  // Work tiles: a silent preview of the project's desktop loop, made only when first wanted (no file before that), faded in
  // over the photo once frames arrive and out again on leave. One at a time; never with reduced motion, Save-Data or
  // Pause motion pressed.
  const fade = (video, to) => (video.animate
    ? video.animate([{ opacity: 1 - to }, { opacity: to }], { duration: 200, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'forwards' })
    : (video.style.opacity = String(to)));
  doc.querySelectorAll('[data-hover-src]').forEach(frame => {
    let video = null, on = false;
    const stop = () => {
      on = false;
      if (video && !video.paused) { video.pause(); fade(video, 0); }
    };
    const start = () => {
      if (held || still || saveData || doc.hidden) return;
      previews.forEach(other => { if (other !== stop) other(); });
      on = true;
      if (!video) {
        video = doc.createElement('video');
        video.className = 'hover-video';
        ['muted', 'loop', 'playsinline'].forEach(name => video.setAttribute(name, ''));
        video.setAttribute('preload', 'none');
        video.setAttribute('aria-hidden', 'true');
        video.setAttribute('width', '1280');
        video.setAttribute('height', '800');
        video.muted = true;
        video.style.opacity = '0';
        video.addEventListener('playing', () => { if (on) fade(video, 1); });
        video.src = frame.dataset.hoverSrc;
        frame.appendChild(video);
      }
      try { video.play()?.catch?.(() => {}); } catch (error) {}
    };
    previews.push(stop);
    // Work tiles sit inside their link; the homepage's concept cards are articles whose title link covers the card.
    const target = frame.closest?.('a') || frame.closest?.('article') || frame;
    if (fine) {
      target.addEventListener('pointerenter', start);
      target.addEventListener('pointerleave', stop);
      target.addEventListener('focus', start);
      target.addEventListener('blur', stop);
    } else if (win.IntersectionObserver) {
      new win.IntersectionObserver(e => (e[e.length - 1].isIntersecting ? start() : stop()), { rootMargin: '-35% 0px -35% 0px' }).observe(frame);
    }
  });
  const loops = Array.from(doc.querySelectorAll('video[data-loop]')).filter(v => !(narrowNow && v.dataset.loop === 'wide')).map(v => add(v, true));
  // Liquid Glass (Task 37): the same state is shared with the glass shell and the WebGL hero, so Pause motion also stops the
  // drifting atmosphere and the 3D render loop (window.__glass.onPauseChange).
  const glass = win.__glass = win.__glass || { paused: false, heroP: 0, pointer: { x: 0, y: 0 } };
  if (motion && loops.length) {
    const show = () => motion.setAttribute('aria-pressed', String(held));
    glass.paused = held;
    motion.addEventListener('click', () => {
      held = !held;
      glass.paused = held;
      glass.onPauseChange?.(held);
      items.forEach(it => { it.wanted = !held; sync(it); it.label(); });
      if (held) previews.forEach(stop => stop());
      show();
    });
    motion.addEventListener('blur', showFab);
    show();
    if (!fab) motion.hidden = false;
  }
  const start = () => { loaded = true; items.forEach(sync); };
  if (!loaded) win.addEventListener('load', () => (win.requestIdleCallback ? win.requestIdleCallback(start, { timeout: 2000 }) : win.setTimeout(start, 200)));
  doc.addEventListener('visibilitychange', () => { items.forEach(sync); if (doc.hidden) previews.forEach(stop => stop()); });
})();
