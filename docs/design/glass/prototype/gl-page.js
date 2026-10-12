/* Inner-page glass centrepiece. Same white frosted glass family as the homepage C.
   The object is placed on an anchor element of the hero (data-gl-anchor), so it sits in open space on every screen size;
   with data-gl-hide the anchor's own DOM media steps back (the scene shows it instead, behind the glass).
   Kinds:
     slab   — Work: a frosted glass slab at an angle, the concept-site loop playing behind / through it (the DOM phone stays in front)
     photos — About: a big glass C refracting the studio photographs, which float behind it in depth
     panes  — Services: three stacked glass panes (New website / Redesign / Care plan) that fan out in 3D
     sheets — Pricing: frosted sheets in depth behind the 3D quote card
     mark   — Contact: a small glass C beside the glass form */
import * as THREE from 'three';
import { MARK, extrude, roundedRect, silhouette } from '/gl-scene.js';

const easeOut = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
const damp = (a, b, l, dt) => a + (b - a) * (1 - Math.exp(-l * dt));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const blendMat = (map, opacity = 1) => new THREE.MeshBasicMaterial({ map, opacity, transparent: false, depthWrite: false, toneMapped: false,
  blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneMinusSrcAlphaFactor });

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
function labelTexture(num, title, sub) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 640; const x = c.getContext('2d');
  x.fillStyle = '#8C5A1C'; x.font = '700 54px Archivo, Arial, sans-serif'; x.fillText(num, 70, 130);
  x.fillStyle = '#0E0E0D'; x.font = '800 132px Archivo, Arial, sans-serif'; x.fillText(title, 64, 300);
  x.fillStyle = 'rgba(14,14,13,0.66)'; x.font = '400 46px "Atkinson Hyperlegible", Arial, sans-serif'; x.fillText(sub, 70, 390);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}

export function start(host) {
  const G = window.__glass || (window.__glass = { paused: false, pointer: { x: 0, y: 0 } });
  const kind = host.dataset.glKind || 'mark', vname = host.dataset.glVideo || 'loop-gl-desktop';
  const section = host.parentElement;
  const anchorEl = host.dataset.glAnchor ? section.querySelector(host.dataset.glAnchor) : null;
  const narrow = window.matchMedia('(max-width: 760px)').matches;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, narrow ? 1.5 : 1.75));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  host.appendChild(renderer.domElement);

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

  /* daylight colour field */
  const fieldMat = new THREE.ShaderMaterial({ toneMapped: false, depthWrite: false,
    uniforms: { uTime: { value: 0 }, uPaper: { value: paper.clone() }, uA: { value: new THREE.Color('#EDBF72') }, uB: { value: new THREE.Color('#A3C4DE') }, uC: { value: new THREE.Color('#B2CB9C') } },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: `precision mediump float; varying vec2 vUv; uniform float uTime; uniform vec3 uPaper,uA,uB,uC;
      float blob(vec2 p, vec2 c, float r){ vec2 d = p - c; return exp(-dot(d,d)/(r*r)); }
      void main(){ vec2 p = vUv * vec2(1.6,1.0); float t = uTime*0.05; vec3 col = uPaper;
        col = mix(col, uA, 0.8*blob(p, vec2(1.3+0.1*sin(t), 0.72), 0.3));
        col = mix(col, uB, 0.7*blob(p, vec2(0.6+0.12*cos(t*0.8), 0.35), 0.3));
        col = mix(col, uC, 0.6*blob(p, vec2(1.0+0.1*sin(t*1.2), 0.15), 0.25));
        gl_FragColor = vec4(col,1.0);
        #include <colorspace_fragment>
      }` });
  const field = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), fieldMat); field.position.z = -12; scene.add(field);

  const loader = new THREE.TextureLoader();
  const img = (src) => { const t = loader.load(src); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t; };
  const glass = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.12, transmission: 1, thickness: 2.0, ior: 1.5,
    clearcoat: 1, clearcoatRoughness: 0.04, sheen: 0.25, sheenColor: new THREE.Color(0xffffff), sheenRoughness: 0.35,
    attenuationColor: new THREE.Color('#eef2f4'), attenuationDistance: 3, envMapIntensity: 1.2 });

  /* the page's concept-site loop: poster until the video has a frame */
  const videos = [];
  function loopMaterial(name) {
    const m = new THREE.MeshBasicMaterial({ map: img(`/assets/video/${name}-poster.jpg`), toneMapped: false });
    const v = document.createElement('video');
    v.src = `/assets/video/${name}.mp4`; v.muted = true; v.loop = true; v.playsInline = true; v.preload = 'auto'; v.setAttribute('muted', '');
    const vt = new THREE.VideoTexture(v); vt.colorSpace = THREE.SRGBColorSpace;
    v.addEventListener('playing', () => { m.map = vt; m.needsUpdate = true; }, { once: true });
    videos.push(v); return m;
  }
  function photoCard(src, w, h) {
    const g = new THREE.Group();
    const p = new THREE.Mesh(roundedRect(w, h, 0.12), new THREE.MeshBasicMaterial({ map: img(src), toneMapped: false }));
    g.add(p); return g;
  }

  const obj = new THREE.Group(); scene.add(obj);   // the glass centrepiece
  const back = new THREE.Group(); scene.add(back); // what it refracts
  let unitH = 3;                                   // the centrepiece's own height, for fitting it to the anchor
  const parts = [];

  if (kind === 'slab') {
    obj.add(new THREE.Mesh(slabGeo(4.4, 2.75, 0.26, 0.16, 0.12), glass));
    const scr = new THREE.Mesh(roundedRect(4.1, 2.56, 0.14), loopMaterial(vname)); scr.position.set(0.55, 0.4, -0.75); obj.add(scr);
    const bez = new THREE.Mesh(roundedRect(4.24, 2.7, 0.2), new THREE.MeshBasicMaterial({ color: 0x1b1a17, toneMapped: false })); bez.position.set(0.55, 0.4, -0.76); obj.add(bez);
    unitH = 3.4;
  } else if (kind === 'panes') {
    const data = [['01', 'New website', 'Planned, written and built'], ['02', 'Redesign', 'Same name, a better first impression'], ['03', 'Care plan', 'Updates, backups and small changes']];
    data.forEach((d, i) => {
      const g = new THREE.Group();
      g.add(new THREE.Mesh(slabGeo(3.2, 2.0, 0.2, 0.08, 0.07), glass));
      /* the label sits just in front of its pane as a normal transparent layer (drawn after the glass), so it stays crisp */
      const lab = new THREE.Mesh(new THREE.PlaneGeometry(3.0, 1.875), new THREE.MeshBasicMaterial({ map: labelTexture(...d), transparent: true, depthWrite: false, toneMapped: false }));
      lab.position.z = 0.13; g.add(lab);
      obj.add(g); parts.push(g);
    });
    const ph = photoCard('/assets/images/barber-chair-800.jpg', 3.4, 2.26); ph.position.set(1.6, 1.0, -6.5); back.add(ph);
    unitH = 3.6;
  } else if (kind === 'sheets') {
    [[1.3, 0.9, -1.4, 0.22], [-1.1, -0.7, -2.6, -0.16]].forEach(([x, y, z, r]) => {
      const s = new THREE.Mesh(slabGeo(3.0, 3.8, 0.24, 0.1, 0.08), glass); s.position.set(x, y, z); s.rotation.set(0.1, r, r * 0.4); obj.add(s); parts.push(s);
    });
    const sun = new THREE.Mesh(new THREE.CircleGeometry(1.5, 48), new THREE.MeshBasicMaterial({ color: new THREE.Color('#E8B45C'), toneMapped: false })); sun.position.set(1.9, 1.5, -4); back.add(sun);
    unitH = 4.2;
  } else {
    /* the C: big for About (photos float behind), small for Contact */
    const g = extrude(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">${MARK.map((d) => `<path d="${d}"/>`).join('')}</svg>`,
      { depth: 40, bevelEnabled: true, bevelThickness: 14, bevelSize: 8, bevelSegments: narrow ? 8 : 14, curveSegments: narrow ? 28 : 48 });
    const s = 3.2 / 152; g.scale(s, s, s);
    obj.add(new THREE.Mesh(g, glass));
    const sh = silhouette(MARK, [24, 24, 135, 152], { pad: 0.22, blur: 12, color: 'rgba(52,40,24,0.4)' });
    const w = 3.2 * 135 / 152 * sh.scaleW;
    const shm = new THREE.Mesh(new THREE.PlaneGeometry(w, w / sh.aspect), blendMat(sh.tex)); shm.position.set(0.08, -0.16, -0.7); shm.renderOrder = 10; obj.add(shm);
    unitH = 3.4;
    if (kind === 'photos') {
      [['/assets/images/barber-shave-800.jpg', -1.2, 0.9, -2.6, 0.12], ['/assets/images/detail-wax-800.jpg', 1.5, 1.2, -3.8, -0.1], ['/assets/images/garden-wall-800.jpg', 0.6, -1.1, -3.0, -0.06]]
        .forEach(([src, x, y, z, r], i) => { const p = photoCard(src, 2.7, 1.8); p.position.set(x, y, z); p.rotation.set(0, r, r * 0.3); back.add(p); parts.push(p); });
      unitH = 3.9;
    } else {
      const ph = photoCard('/assets/images/detail-headlight-800.jpg', 2.6, 1.75); ph.position.set(0.9, 0.5, -3.2); ph.rotation.y = 0.15; back.add(ph);
    }
  }
  const key = new THREE.DirectionalLight(0xffffff, 1.5); key.position.set(-3, 5, 6); scene.add(key);
  const rimL = new THREE.DirectionalLight(0xffffff, 2.2); rimL.position.set(-1, 5, -7); scene.add(rimL);
  const sweep = new THREE.DirectionalLight(0xffffff, 1.8); scene.add(sweep);

  /* fit to the anchor: centre and scale from its rectangle, relative to the canvas */
  const P = { x: 0, y: 0, s: 1 };
  const wideFit = { slab: [0.02, -0.06, 0.66], panes: [-0.08, 0.05, 1.1], sheets: [0, 0, 1.0], photos: [0, 0, 1.0], mark: [-0.5, -0.5, 0.3] };
  const narrowFit = { slab: [0.02, -0.3, 0.6], panes: [0, 0, 0.95], sheets: [0, 0, 1.0], photos: [0, 0, 1.0], mark: [-0.42, -0.5, 0.45] };
  const fit = (window.matchMedia('(max-width: 1023px)').matches ? narrowFit : wideFit)[kind] || [0, 0, 1];
  function layout() {
    const w = host.clientWidth, h = host.clientHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    const halfH = Math.tan(THREE.MathUtils.degToRad(15)) * 14, halfW = halfH * camera.aspect;
    const visH = Math.tan(THREE.MathUtils.degToRad(15)) * 26 * 2;
    field.scale.set(visH * camera.aspect * 1.4, visH * 1.4, 1);
    const hr = host.getBoundingClientRect();
    const ar = anchorEl ? anchorEl.getBoundingClientRect() : { left: hr.left + w * 0.55, top: hr.top + h * 0.15, width: w * 0.4, height: h * 0.6 };
    const cx = ar.left + ar.width * (0.5 + fit[0]) - hr.left, cy = ar.top + ar.height * (0.5 + fit[1]) - hr.top;
    P.x = (cx / w * 2 - 1) * halfW; P.y = (1 - cy / h * 2) * halfH;
    const worldH = Math.min(ar.height, ar.width * 0.85) / h * 2 * halfH;
    P.s = clamp(worldH / unitH * fit[2], 0.25, 1.6);
  }
  layout();
  window.addEventListener('resize', () => { layout(); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => setTimeout(layout, 50));
  setTimeout(layout, 1200);

  const clock = new THREE.Clock(); let t = 0, intro = 0, running = false, inView = true;
  const sm = { px: 0, py: 0, p: 0 };
  function frame(dt) {
    t += dt; intro += dt;
    sm.px = damp(sm.px, G.pointer.x || 0, 2.5, dt); sm.py = damp(sm.py, G.pointer.y || 0, 2.5, dt);
    const r = host.getBoundingClientRect(), p = clamp(-r.top / Math.max(1, r.height), 0, 1);
    sm.p = damp(sm.p, p, 6, dt);
    const k = easeOut(clamp(intro / 2.2, 0, 1));
    fieldMat.uniforms.uTime.value = t;
    obj.position.set(P.x, P.y - (1 - k) * 1.0 + Math.sin(t * 0.6) * 0.05 + sm.p * 0.6, -sm.p * 1.5);
    obj.scale.setScalar(P.s * (0.86 + 0.14 * k));
    back.position.set(P.x, P.y + sm.p * 0.3, -(1 - k) * 6);
    back.scale.setScalar(P.s);
    const yaw = { slab: -0.42, panes: -0.36, sheets: -0.2, photos: -0.26, mark: -0.3 }[kind] || -0.3;
    obj.rotation.set(0.1 + Math.sin(t * 0.21) * 0.035 + sm.py * 0.1 + sm.p * 0.3, yaw * k - 0.5 * (1 - k) + Math.sin(t * 0.28) * 0.07 + sm.px * 0.16, kind === 'mark' || kind === 'photos' ? -0.06 : 0);
    if (kind === 'panes') parts.forEach((g, i) => {
      const f = easeOut(clamp((intro - 0.3 - i * 0.18) / 2, 0, 1));
      g.position.set((i - 1) * 0.8 * f, (1 - i) * 0.95 * f, (i - 1) * 0.75 * f); // upper panes sit further back, so every title stays clear
      g.rotation.set(0, (i - 1) * 0.1 * f + Math.sin(t * 0.3 + i) * 0.03, 0);
    });
    if (kind === 'photos') parts.forEach((g, i) => { g.position.z += Math.sin(t * 0.4 + i * 2) * 0.0015; });
    sweep.position.set(Math.cos(t * 0.45) * 6, 3 + Math.sin(t * 0.3) * 2, 4 + Math.sin(t * 0.45) * 3);
    camera.position.x = damp(camera.position.x, sm.px * 0.25, 3, dt);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }
  function loop() { frame(Math.min(clock.getDelta(), 1 / 20)); }
  function set(on) {
    on = on && inView && !G.paused && !document.hidden;
    if (on === running) return; running = on;
    if (on) { clock.getDelta(); renderer.setAnimationLoop(loop); videos.forEach((v) => { const pr = v.play(); if (pr && pr.catch) pr.catch(() => {}); }); }
    else { renderer.setAnimationLoop(null); videos.forEach((v) => v.pause()); }
  }
  new IntersectionObserver((es) => { inView = es[es.length - 1].isIntersecting; set(true); }).observe(host);
  document.addEventListener('visibilitychange', () => set(true));
  G.onPauseChange = () => set(true);
  const go = () => {
    frame(0); host.classList.add('is-live');
    if (host.hasAttribute('data-gl-hide')) section.classList.add('gl-lead'); // the anchor's DOM media steps back; the scene shows it
    set(true);
  };
  renderer.compileAsync ? renderer.compileAsync(scene, camera).then(go, go) : go();
}
