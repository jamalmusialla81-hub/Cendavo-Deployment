/* Cendavo Liquid Glass inner-page centrepiece (Tasks 39 and 40), ported from docs/design/glass/prototype/gl-page.js. An ES module
   imported by glass-boot.js only after load and idle, only on capable desktops, never with reduced motion, Save-Data or
   without WebGL. Same white frosted glass family as the homepage C, imported by relative path (no import map).
   The host ([data-gl], aria-hidden) sits behind its hero; the object is fitted to a hero element named by data-gl-anchor.
   With data-gl-hide the hero adds .gl-lead and CSS fades that element's media, which stays in the DOM and the
   accessibility tree. Kinds (anything else draws nothing):
     slab  - Work: a frosted glass slab at an angle, the Greenline concept loop playing behind it; the DOM phone stays in front
     panes - Services: three stacked clean white glass panes (New website / Redesign / Care plan) fanning out, upper panes
             further back (paneLayout); nothing behind them but the colour field, never a photo (Task 45)
     sheets - Pricing: two frosted sheets and a warm disc behind the HTML quote card, which stays in front as text
     photos - About: a big glass C with the three studio photos floating behind it, feathered to soft ovals (Task 44; the
              DOM collage steps back)
     mark   - Contact: a small glass C in its own fixed box (.ct-gl-spot) at the hero's top-right, above the form panel and
              never behind it (Task 41), a light photo (white kitchen) behind it, so the C refracts light, never a dark
              plane (Task 42); the form is untouched
   The loop runs only while the hero is on screen, the tab is visible and Pause motion is off (registered on the shared
   G.pauseFns fan-out, never by replacing G.onPauseChange); otherwise setAnimationLoop(null) stops it and videos pause.
   Task 48: the shared helpers come from glass-shapes.js, so these pages never fetch the homepage scene (glass-scene.js) or
   three's SVGLoader and BufferGeometryUtils; the C is extruded straight from its paths (markGeometry). The scene draws with
   the WebGL2 context glass-boot.js tested (gl) and returns true once it has taken it (false: glass-boot.js releases it). */
import * as THREE from './vendor/three/three.module.min.js';
import { roundedRect, MARK, markGeometry, silhouette, rendererOptions } from './glass-shapes.js';

const easeOut = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)); // expo out, no overshoot
const damp = (a, b, lambda, dt) => a + (b - a) * (1 - Math.exp(-lambda * dt));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

export const KINDS = ['slab', 'panes', 'sheets', 'photos', 'mark'];
export const PANES = [['01', 'New website', 'Planned, written and built'], ['02', 'Redesign', 'Same name, a better first impression'],
  ['03', 'Care plan', 'Updates, backups and small changes']];
/* Task 45: where pane i (0..2) sits at fan-out f (0..1), in pane units (a pane is 3.2 x 2.0). Pane 1 is highest, furthest
   left and furthest back; pane 3 lowest, furthest right and nearest. Each step down is 1.2 (60% of a pane's height), so a
   covered pane always shows its top strip, where its number, title and line sit. Pure, so it is tested in Node. */
export const PANE = { w: 3.2, h: 2.0 };
export function paneLayout(i, f) {
  const d = i - 1;
  return { x: d * 1.0 * f, y: -d * 1.2 * f, z: d * 0.6 * f, ry: d * 0.1 * f };
}
const LOOP = { 'loop-gl-desktop': '/assets/video/loop-gl-desktop' }; // the only video a page can ask for
/* the only photos the About and Contact scenes draw: [src, x, y, z, yaw]; never read from the page */
export const PHOTOS = { photos: [['/assets/images/barber-shave-800.jpg', -1.2, 0.9, -2.6, 0.12], ['/assets/images/detail-wax-800.jpg', 1.5, 1.2, -3.8, -0.1],
  ['/assets/images/garden-wall-800.jpg', 0.6, -1.1, -3.0, -0.06]], mark: [['/assets/images/clean-kitchen-800.jpg', 0.9, 0.5, -3.2, 0.15]] };

/* Runs `run(on)` whenever the scene should start or stop: on screen, tab visible, Pause motion off. Joins the shared
   pause fan-out from glass.js (or starts it, without replacing an existing one). */
export function lifecycle(G, doc, run) {
  let running = false, inView = true, ready = false;
  const set = () => {
    const on = ready && inView && !G.paused && !doc.hidden;
    if (on === running) return;
    running = on;
    run(on);
  };
  (G.pauseFns = G.pauseFns || []).push(set);
  if (!G.onPauseChange) G.onPauseChange = (p) => G.pauseFns.forEach((fn) => fn(p));
  doc.addEventListener('visibilitychange', set);
  return { view(v) { inView = v; set(); }, ready() { ready = true; set(); }, get running() { return running; } };
}

function rrShape(w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r); s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h); s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y); return s;
}
function slabGeo(w, h, r, d, bevel) {
  const g = new THREE.ExtrudeGeometry(rrShape(w, h, r), { depth: d, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel * 0.8, bevelSegments: 10, curveSegments: 24 });
  g.center(); return g;
}
/* the pane titles repeat the visible HTML headings and chapter links; the canvas is aria-hidden */
function labelTexture(num, title, sub) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 640; const x = c.getContext('2d');
  /* all text sits in the top half of the label, so it stays readable on a pane covered by the next one */
  x.fillStyle = '#8C5A1C'; x.font = '700 50px Archivo, Arial, sans-serif'; x.fillText(num, 70, 96);
  x.fillStyle = '#0E0E0D'; x.font = '800 124px Archivo, Arial, sans-serif'; x.fillText(title, 64, 222);
  x.fillStyle = 'rgba(14,14,13,0.66)'; x.font = '400 44px "Atkinson Hyperlegible", Arial, sans-serif'; x.fillText(sub, 70, 296);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}

/* a radial falloff (white centre to black edge; alphaMap reads green): the photo's corners and edges melt into the page */
function featherTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d');
  const g = x.createRadialGradient(64, 64, 18, 64, 64, 64);
  g.addColorStop(0, '#fff'); g.addColorStop(0.5, '#fff'); g.addColorStop(1, '#000');
  x.fillStyle = g; x.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

export function start(host, shared, gl) {
  const G = shared || window.__glass || (window.__glass = { paused: false, pointer: { x: 0, y: 0 } });
  G.pointer = G.pointer || { x: 0, y: 0 };
  const kind = host.dataset.glKind;
  if (!KINDS.includes(kind)) return false;
  const section = host.closest('section') || host.parentElement;
  const anchorEl = host.dataset.glAnchor ? section.querySelector(host.dataset.glAnchor) : null;
  const renderer = new THREE.WebGLRenderer(rendererOptions(gl));
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.setAttribute('aria-hidden', 'true');

  const scene = new THREE.Scene();
  const paper = new THREE.Color('#F4F2ED');
  scene.background = paper;
  scene.fog = new THREE.Fog(paper, 16, 42);
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
  camera.position.set(0, 0, 14);

  /* bright studio reflections (same recipe as the homepage) */
  const pmrem = new THREE.PMREMGenerator(renderer), studio = new THREE.Scene();
  studio.add(new THREE.Mesh(new THREE.SphereGeometry(20, 32, 16), new THREE.ShaderMaterial({ side: THREE.BackSide,
    vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: 'varying vec3 vP; void main(){ float h = vP.y*0.5+0.5; gl_FragColor = vec4(mix(vec3(0.84,0.82,0.79), vec3(1.0,0.995,0.98), smoothstep(0.05,0.85,h)),1.0); }' })));
  [[16, 5, 0, 12, 4, 3.4], [5, 12, -12, 2, 5, 2.6], [5, 12, 12, 1, -3, 2.2], [12, 3, 0, -5, 12, 1.8]].forEach(([w, h, x, y, z, i]) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(i, i, i * 0.98), side: THREE.DoubleSide }));
    m.position.set(x, y, z); m.lookAt(0, 0, 0); studio.add(m);
  });
  scene.environment = pmrem.fromScene(studio, 0.03).texture;
  pmrem.dispose();

  /* daylight colour field: a warm-white base with a faint tint (Task 44) */
  const fieldMat = new THREE.ShaderMaterial({ toneMapped: false, depthWrite: false,
    uniforms: { uTime: { value: 0 }, uPaper: { value: paper.clone() }, uA: { value: new THREE.Color('#EDBF72') }, uB: { value: new THREE.Color('#A3C4DE') }, uC: { value: new THREE.Color('#B2CB9C') } },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: 'precision mediump float; varying vec2 vUv; uniform float uTime; uniform vec3 uPaper,uA,uB,uC;\n'
      + 'float blob(vec2 p, vec2 c, float r){ vec2 d = p - c; return exp(-dot(d,d)/(r*r)); }\n'
      + 'void main(){ vec2 p = vUv * vec2(1.6,1.0); float t = uTime*0.05; vec3 col = uPaper;\n'
      + 'col = mix(col, uA, 0.42*blob(p, vec2(1.3+0.1*sin(t), 0.72), 0.3));\n'
      + 'col = mix(col, uB, 0.34*blob(p, vec2(0.6+0.12*cos(t*0.8), 0.35), 0.3));\n'
      + 'col = mix(col, uC, 0.28*blob(p, vec2(1.0+0.1*sin(t*1.2), 0.15), 0.25));\n'
      + 'gl_FragColor = vec4(col,1.0);\n#include <colorspace_fragment>\n}' });
  const field = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), fieldMat); field.position.z = -12; scene.add(field);

  const loader = new THREE.TextureLoader();
  const img = (src) => { const t = loader.load(src); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t; };
  const glass = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.12, transmission: 1, thickness: 2.0, ior: 1.5,
    clearcoat: 1, clearcoatRoughness: 0.04, sheen: 0.25, sheenColor: new THREE.Color(0xffffff), sheenRoughness: 0.35,
    attenuationColor: new THREE.Color('#eef2f4'), attenuationDistance: 3, envMapIntensity: 1.2 });

  /* the concept-site loop: its poster until the video has a frame; fetched only once the scene runs */
  const videos = [];
  function loopMaterial(base) {
    const m = new THREE.MeshBasicMaterial({ map: img(`${base}-poster.jpg`), toneMapped: false });
    const v = document.createElement('video');
    v.muted = true; v.loop = true; v.playsInline = true; v.preload = 'none'; v.setAttribute('muted', ''); v.dataset.src = `${base}.mp4`;
    const vt = new THREE.VideoTexture(v); vt.colorSpace = THREE.SRGBColorSpace;
    v.addEventListener('playing', () => { m.map = vt; m.needsUpdate = true; }, { once: true });
    videos.push(v); return m;
  }

  const obj = new THREE.Group(); scene.add(obj);   // the glass centrepiece
  const back = new THREE.Group(); scene.add(back); // what it refracts
  /* Task 44: the photos behind the C (About, Contact) fade out in a soft oval (a radial alphaMap), never a hard rectangle.
     They blend as "opaque" materials (custom blending, drawn after the colour field), because transmission refracts only
     opaque objects. */
  const feather = featherTexture();
  const photoCard = (src, w, h) => {
    const m = new THREE.Mesh(roundedRect(w, h, 0.12), new THREE.MeshBasicMaterial({ map: img(src), alphaMap: feather, toneMapped: false,
      depthWrite: false, blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneMinusSrcAlphaFactor }));
    m.renderOrder = 1; return m;
  };
  let unitH = 3.4;
  const parts = [];
  if (kind === 'slab') {
    obj.add(new THREE.Mesh(slabGeo(4.4, 2.75, 0.26, 0.16, 0.12), glass));
    const base = LOOP[host.dataset.glVideo] || LOOP['loop-gl-desktop'];
    const scr = new THREE.Mesh(roundedRect(4.1, 2.56, 0.14), loopMaterial(base)); scr.position.set(0.55, 0.4, -0.75); obj.add(scr);
    const bez = new THREE.Mesh(roundedRect(4.24, 2.7, 0.2), new THREE.MeshBasicMaterial({ color: 0x1b1a17, toneMapped: false })); bez.position.set(0.55, 0.4, -0.76); obj.add(bez);
  } else if (kind === 'panes') {
    PANES.forEach((d) => {
      const g = new THREE.Group();
      g.add(new THREE.Mesh(slabGeo(PANE.w, PANE.h, 0.2, 0.08, 0.07), glass));
      /* the label sits just in front of its pane as a normal transparent layer (drawn after the glass), so it stays crisp */
      const lab = new THREE.Mesh(new THREE.PlaneGeometry(3.0, 1.875), new THREE.MeshBasicMaterial({ map: labelTexture(...d), transparent: true, depthWrite: false, toneMapped: false }));
      lab.position.z = 0.13; g.add(lab);
      obj.add(g); parts.push(g);
    });
    unitH = 4.6; // the fanned stack: one pane plus two steps of 1.2, with room for the drift
  } else if (kind === 'sheets') {
    const sheet = slabGeo(3.0, 3.8, 0.24, 0.1, 0.08); // one geometry, one material, two meshes
    [[1.3, 0.9, -1.4, 0.22], [-1.1, -0.7, -2.6, -0.16]].forEach(([x, y, z, r]) => {
      const s = new THREE.Mesh(sheet, glass); s.position.set(x, y, z); s.rotation.set(0.1, r, r * 0.4); obj.add(s);
    });
    const sun = new THREE.Mesh(new THREE.CircleGeometry(1.5, 48), new THREE.MeshBasicMaterial({ color: new THREE.Color('#E8B45C'), toneMapped: false }));
    sun.position.set(1.9, 1.5, -4); back.add(sun);
    unitH = 4.2;
  } else {
    /* the C: big for About (the photos float behind it), small for Contact */
    const g = markGeometry({ depth: 40, bevelEnabled: true, bevelThickness: 14, bevelSize: 8, bevelSegments: 14, curveSegments: 48 });
    const s = 3.2 / 152; g.scale(s, s, s);
    obj.add(new THREE.Mesh(g, glass));
    const sh = silhouette(MARK, [24, 24, 135, 152], { pad: 0.22, blur: 12, color: 'rgba(52,40,24,0.4)' });
    const w = 3.2 * 135 / 152 * sh.scaleW;
    const shm = new THREE.Mesh(new THREE.PlaneGeometry(w, w / sh.aspect), new THREE.MeshBasicMaterial({ map: sh.tex, transparent: true, depthWrite: false, toneMapped: false }));
    shm.position.set(0.08, -0.16, -0.7); shm.renderOrder = 10; obj.add(shm);
    PHOTOS[kind].forEach(([src, x, y, z, r]) => {
      const p = kind === 'photos' ? photoCard(src, 2.7, 1.8) : photoCard(src, 2.6, 1.75);
      p.position.set(x, y, z); p.rotation.set(0, r, r * 0.3); back.add(p); if (kind === 'photos') parts.push(p);
    });
    unitH = kind === 'photos' ? 3.9 : 3.4;
  }
  const key = new THREE.DirectionalLight(0xffffff, 1.5); key.position.set(-3, 5, 6); scene.add(key);
  const rimL = new THREE.DirectionalLight(0xffffff, 2.2); rimL.position.set(-1, 5, -7); scene.add(rimL);
  const sweep = new THREE.DirectionalLight(0xffffff, 1.8); scene.add(sweep);

  /* fit to the anchor: centre and scale from its rectangle, relative to the canvas */
  const P = { x: 0, y: 0, s: 1 };
  const fit = { slab: [0.02, -0.06, 0.66], panes: [-0.08, 0.05, 1.1], sheets: [0, 0, 1.0], photos: [0, 0, 1.0], mark: [0, 0, 1.15] }[kind];
  const halfH = Math.tan(THREE.MathUtils.degToRad(15)) * 14;
  function layout() {
    const w = Math.max(1, host.clientWidth), h = Math.max(1, host.clientHeight);
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    const halfW = halfH * camera.aspect, visH = Math.tan(THREE.MathUtils.degToRad(15)) * 26 * 2;
    field.scale.set(visH * camera.aspect * 1.4, visH * 1.4, 1);
    const hr = host.getBoundingClientRect();
    const ar = anchorEl ? anchorEl.getBoundingClientRect() : { left: hr.left + w * 0.55, top: hr.top + h * 0.15, width: w * 0.4, height: h * 0.6 };
    const cx = ar.left + ar.width * (0.5 + fit[0]) - hr.left, cy = ar.top + ar.height * (0.5 + fit[1]) - hr.top;
    P.x = (cx / w * 2 - 1) * halfW; P.y = (1 - cy / h * 2) * halfH;
    P.s = clamp((Math.min(ar.height, ar.width * 0.85) / h * 2 * halfH) / unitH * fit[2], 0.25, 1.6);
  }
  layout();
  let resizeT = 0;
  window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(layout, 120); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(layout);

  const clock = new THREE.Clock(); let t = 0, intro = 0;
  const sm = { px: 0, py: 0, p: 0 };
  const yaw = { slab: -0.42, panes: -0.36, sheets: -0.2, photos: -0.26, mark: -0.3 }[kind];
  const roll = kind === 'photos' || kind === 'mark' ? -0.06 : 0;
  const rest = parts.map((g) => g.position.z);
  function frame(dt) {
    t += dt; intro += dt;
    sm.px = damp(sm.px, G.pointer.x || 0, 2.5, dt); sm.py = damp(sm.py, G.pointer.y || 0, 2.5, dt);
    const r = host.getBoundingClientRect();
    sm.p = damp(sm.p, clamp(-r.top / Math.max(1, r.height), 0, 1), 6, dt);
    const k = easeOut(clamp(intro / 2.2, 0, 1));
    fieldMat.uniforms.uTime.value = t;
    obj.position.set(P.x, P.y - (1 - k) * 1.0 + Math.sin(t * 0.6) * 0.05 + sm.p * 0.6, -sm.p * 1.5);
    obj.scale.setScalar(P.s * (0.86 + 0.14 * k));
    back.position.set(P.x, P.y + sm.p * 0.3, -(1 - k) * 6);
    back.scale.setScalar(P.s);
    obj.rotation.set(0.1 + Math.sin(t * 0.21) * 0.035 + sm.py * 0.1 + sm.p * 0.3, yaw * k - 0.5 * (1 - k) + Math.sin(t * 0.28) * 0.07 + sm.px * 0.16, roll);
    if (kind === 'photos') parts.forEach((g, i) => { g.position.z = rest[i] + Math.sin(t * 0.4 + i * 2) * 0.12; }); // a slow depth breath
    else parts.forEach((g, i) => {
      const f = easeOut(clamp((intro - 0.3 - i * 0.18) / 2, 0, 1));
      const L = paneLayout(i, f); // upper panes sit further back and higher, so every title stays clear
      g.position.set(L.x, L.y, L.z);
      g.rotation.set(0, L.ry + Math.sin(t * 0.3 + i) * 0.03, 0);
    });
    sweep.position.set(Math.cos(t * 0.45) * 6, 3 + Math.sin(t * 0.3) * 2, 4 + Math.sin(t * 0.45) * 3);
    camera.position.x = damp(camera.position.x, sm.px * 0.25, 3, dt);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }
  const loop = () => frame(Math.min(clock.getDelta(), 1 / 20));
  const play = (v) => {
    if (!v.src) { v.src = v.dataset.src; v.load(); }
    const p = v.play(); if (p && p.catch) p.catch(() => {});
  };
  const life = lifecycle(G, document, (on) => {
    if (on) { clock.getDelta(); renderer.setAnimationLoop(loop); videos.forEach(play); }
    else { renderer.setAnimationLoop(null); videos.forEach((v) => v.pause()); }
  });
  new IntersectionObserver((es) => life.view(es[es.length - 1].isIntersecting)).observe(host);

  /* the canvas joins the page only once its first frame is drawn; then the hidden media steps back */
  const fade = (el, from, to, done) => {
    if (el.animate && !G.paused) el.animate([{ opacity: from }, { opacity: to }], { duration: 900, easing: 'cubic-bezier(.2,.8,.2,1)' }).finished.then(done, done);
    else done();
  };
  const go = () => {
    frame(0);
    host.appendChild(canvas);
    host.classList.add('is-live');
    fade(canvas, 0, 1, () => {});
    /* the anchor's media fades out over the scene, then .gl-lead (pages.css, motion-guarded) holds it there */
    if (host.hasAttribute('data-gl-hide') && anchorEl) fade(anchorEl, 1, 0, () => section.classList.add('gl-lead'));
    life.ready();
  };
  (renderer.compileAsync ? renderer.compileAsync(scene, camera) : Promise.resolve()).then(go, go);
  return true;
}
