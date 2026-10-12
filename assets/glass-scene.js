/* Cendavo Liquid Glass hero (Task 37), ported from docs/design/glass/prototype/gl-scene.js. An ES module imported by
   glass-boot.js only after load and idle, only on capable desktops, never with reduced motion or Save-Data. Three.js r170
   and its two helpers are vendored and imported by relative path, so no import map and no inline script are needed.
   The C mark and the CENDAVO wordmark (Archivo outlines) are white transmission glass (MeshPhysicalMaterial) refracting a
   slow daylight colour field and two concept-site screens far behind. Yaw is clamped to about 32 degrees so the name never
   reads backwards. Task 44: the scroll exit (heroPose, pure and tested in Node) settles the C facing the camera and larger,
   never edge-on; the name is milky frosted glass over light content only (heroLayout keeps the dark screen away). The
   loop runs only while the hero is on screen, the tab is visible and Pause motion is off; otherwise
   setAnimationLoop(null) stops it and the screen videos pause. The canvas is aria-hidden: the host's role="img" label
   describes the hero, and the CSS poster underneath stays in place if anything here fails. */
import * as THREE from './vendor/three/three.module.min.js';
import { SVGLoader } from './vendor/three/jsm/SVGLoader.js';
import { mergeGeometries } from './vendor/three/jsm/BufferGeometryUtils.js';

export const MARK = [
  'M55.67 43.26C86.24 19.38 130.22 24.01 155.16 53.72L135.24 70.43C119.31 51.45 91.21 48.5 71.68 63.75Z',
  'M48.21 150.02C21.26 122.11 21.26 77.89 48.21 49.98L66.91 68.05C49.7 85.87 49.7 114.13 66.91 131.95Z',
  'M155.16 146.28C130.22 175.99 86.24 180.62 55.67 156.74L71.68 136.25C91.21 151.5 119.31 148.55 135.24 129.57Z'
];
const WORD_PATH = 'M435.8 12Q309.9 12 224.1 -27.3Q138.4 -66.6 94.8 -145.7Q51.2 -224.8 51.2 -343.7Q51.2 -518.5 150.3 -608.8Q249.5 -699.1 435.9 -699.1Q539.8 -699.1 619.6 -666.3Q699.5 -633.6 744.9 -570.9Q790.2 -508.2 790.2 -418.1H614.7Q614.7 -463.1 592.2 -494.9Q569.8 -526.6 529.5 -543.5Q489.1 -560.4 434.6 -560.4Q368.5 -560.4 324 -536.3Q279.4 -512.2 257.2 -467.3Q234.9 -422.4 234.9 -360.2V-327.7Q234.9 -265.2 257.3 -220.1Q279.6 -175 323.8 -150.9Q367.9 -126.7 433.5 -126.7Q491.8 -126.7 533.5 -142.9Q575.2 -159.1 597.7 -190.5Q620.2 -222 620.2 -266.5H790.5Q790.5 -178 746.5 -115.6Q702.4 -53.3 622.8 -20.6Q543.2 12 435.8 12Z M981.7 0V-687.1H1614.3V-548.1H1160.9V-417.1H1559.1V-281.3H1160.9V-139H1621.5V0Z M1816.1 0V-687.1H1977.2L2286 -351.8Q2294.3 -343.8 2306.9 -329.1Q2319.5 -314.5 2332.5 -299.5Q2345.6 -284.4 2353.8 -273.7L2360.7 -274.1Q2360.2 -293.4 2359.7 -316.8Q2359.3 -340.2 2359.3 -357.2V-687.1H2527.8V0H2368.4L2056.6 -340.2Q2038.8 -358.8 2020 -380.7Q2001.3 -402.7 1989.8 -415.9L1983.5 -415.5Q1984 -401 1984.3 -378.6Q1984.5 -356.2 1984.5 -333V0Z M2750.1 0V-687.1H3080.4Q3198.4 -687.1 3282.1 -648.8Q3365.8 -610.5 3410.5 -534.3Q3455.2 -458.1 3455.2 -343.4Q3455.2 -229.5 3410.5 -153Q3365.8 -76.6 3282.1 -38.3Q3198.4 0 3080.4 0ZM2929 -139H3074.4Q3120.4 -139 3156.8 -151.5Q3193.2 -163.9 3218.8 -187.8Q3244.4 -211.8 3257.8 -247.1Q3271.2 -282.5 3271.2 -328.3V-358.9Q3271.2 -405 3257.8 -440.3Q3244.4 -475.5 3218.8 -499.5Q3193.2 -523.4 3156.8 -535.7Q3120.4 -548.1 3074.4 -548.1H2929Z M3578 0 3876.4 -687.1H4084L4382.6 0H4189.8L4140.3 -120.9H3811.2L3762 0ZM3865.4 -256.1H4086.1L4025.8 -406.8Q4021.8 -417.2 4015.3 -434.3Q4008.9 -451.4 4002.2 -470.8Q3995.4 -490.3 3989.3 -508.1Q3983.2 -525.8 3979.5 -536.5H3972.6Q3966.2 -517.5 3957.4 -493Q3948.6 -468.4 3940.2 -445.2Q3931.8 -422 3925.6 -406.6Z M4754.9 0 4467.4 -687.1H4663.3L4808.9 -308.1Q4815.7 -292.3 4824 -269.2Q4832.3 -246.2 4840.8 -223.1Q4849.3 -200 4855.3 -182.1H4862.2Q4867.9 -198.4 4875.9 -220.7Q4883.8 -243 4892.4 -266.1Q4901.1 -289.2 4908.3 -307.5L5054.5 -687.1H5241.7L4954.4 0Z M5766.8 12Q5642.9 12 5552.8 -28.6Q5462.8 -69.1 5414.5 -148.5Q5366.2 -227.8 5366.2 -343.5Q5366.2 -460.1 5414.5 -539.1Q5462.8 -618.2 5552.8 -658.6Q5642.9 -699.1 5766.8 -699.1Q5892.1 -699.1 5981.8 -658.6Q6071.5 -618.2 6119.8 -539.1Q6168 -460.1 6168 -343.5Q6168 -227.8 6119.8 -148.5Q6071.5 -69.1 5981.8 -28.6Q5892.1 12 5766.8 12ZM5767 -126.7Q5817.4 -126.7 5857.6 -140.2Q5897.7 -153.6 5926.1 -179.4Q5954.5 -205.2 5969.6 -242.7Q5984.6 -280.3 5984.6 -327.9V-359.6Q5984.6 -407.4 5969.6 -444.9Q5954.5 -482.4 5926.1 -508.1Q5897.7 -533.8 5857.6 -547.1Q5817.4 -560.4 5767 -560.4Q5716.6 -560.4 5676.5 -547.1Q5636.3 -533.8 5608 -508.1Q5579.7 -482.4 5565 -444.9Q5550.2 -407.4 5550.2 -359.6V-327.9Q5550.2 -280.3 5565 -242.7Q5579.7 -205.2 5608 -179.4Q5636.3 -153.6 5676.5 -140.2Q5716.6 -126.7 5767 -126.7Z';
const WORD_VB = [0, -686, 6219, 686];

const easeOut = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)); // expo out, no overshoot
const damp = (a, b, lambda, dt) => a + (b - a) * (1 - Math.exp(-lambda * dt));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = (p) => p * p * (3 - 2 * p);
export const YAW = 0.56; // about 32 degrees
export const C_YAW = 0.45; // the C's own total yaw: never edge-on, never a grey sliver

/* Task 44: the numbers the hero is built from, exported so tests can check them without a GPU. The two concept-site screens
   are only slightly defocused (low mip bias), so they read as refracted content, not mush. */
export const SCREENS = {
  gl: { name: 'gl-desktop', w: 6.6, h: 4.125, r: 0.2, bezel: 0.1, bias: 0.5 },
  hb: { name: 'hb-desktop', w: 5.6, h: 3.5, r: 0.18, bezel: 0.09, bias: 0.8 }
};
/* the name: milky white frosted glass (neutral warm-white body, rough enough to read frosted), never a blue-grey gunmetal */
export const WORD_GLASS = { roughness: 0.3, thickness: 1.1, attenuationColor: '#f6f5f3', attenuationDistance: 2.6,
  sheen: 0.5, sheenRoughness: 0.45, envMapIntensity: 1.3 };
export const WORD = { w: 5.4, h: 5.4 * 686 / 6219, y: -1.75, rx: 0.12, ry: -0.05 }; // width, height, offset and rest tilt
export const MARK_Y = 0.85;

/* Where the lockup and the two screens sit, per aspect ratio: [x, y, z, yaw, pitch] for each screen. The dark hb screen
   sits up and away (top right, far back, partly behind gl), so the letters always sit over light content. */
export function heroLayout(aspect) {
  return aspect >= 0.85
    ? { logo: { x: 2.85, y: 0.35, s: 0.92 * Math.min(1, aspect / 1.45) }, gl: [2.6, 1.2, -7.5, -0.24, 0.03], hb: [8.6, 4.4, -12.5, -0.42, 0.05] }
    : { logo: { x: 0, y: 1.3, s: clamp(aspect * 1.2, 0.45, 0.62) }, gl: [0.9, 3.9, -9, -0.15, 0.04], hb: [-3.2, 6.2, -13, 0.3, 0.05] };
}

/* The lockup's pose: e is the hero's eased exit progress (0..1), t the time, px/py the pointer (-1..1), k the eased intro
   (1 once it has arrived). On exit the idle sway and the pointer fade out, so the C settles square to the camera and grows
   while the reel section rises over it: no tilt back, no edge-on turn, no smear. Task 45: word (1..0) takes the CENDAVO name
   away early in the exit (whole until e = 0.2, gone by e = 0.5), before it grows into the hero's feathered foot and turns
   into a ghost over the next heading. Pure (no three.js), so it is tested in Node. */
export const WORD_OUT = [0.2, 0.5];
export function heroPose(e, t, px, py, k = 1) {
  const calm = 1 - e;
  const w = clamp((e - WORD_OUT[0]) / (WORD_OUT[1] - WORD_OUT[0]), 0, 1);
  const yaw = clamp(-0.5 * (1 - k) + (Math.sin(t * 0.28) * 0.1 + px * 0.2) * calm, -YAW, YAW);
  const markYaw = clamp(yaw + Math.sin(t * 0.33 + 1) * 0.08 * calm, -C_YAW, C_YAW) - yaw; // relative to the lockup
  return {
    yaw, markYaw,
    tilt: (Math.sin(t * 0.21) * 0.04 + py * 0.12) * calm + e * 0.03,
    scale: (0.84 + 0.16 * k) * (1 + 0.22 * e),
    x: 1 - e * 0.45, // a share of the layout's x: the lockup drifts toward the centre
    y: -(1 - k) * 1.3 + Math.sin(t * 0.6) * 0.05 * calm - e * 0.1,
    z: e * 0.8,
    word: 1 - w * w * (3 - 2 * w)
  };
}

export function extrude(svg, opts) {
  const data = new SVGLoader().parse(svg);
  const geos = [];
  data.paths.forEach((p) => SVGLoader.createShapes(p).forEach((s) => geos.push(new THREE.ExtrudeGeometry(s, opts))));
  const g = mergeGeometries(geos);
  geos.forEach((x) => x.dispose());
  g.rotateX(Math.PI); // SVG is y-down
  g.computeBoundingBox();
  const c = new THREE.Vector3(); g.boundingBox.getCenter(c); g.translate(-c.x, -c.y, -c.z);
  g.computeVertexNormals();
  return g;
}

export function roundedRect(w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  const g = new THREE.ShapeGeometry(s, 10);
  const uv = g.attributes.uv, pos = g.attributes.position;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, (pos.getX(i) - x) / w, (pos.getY(i) - y) / h);
  return g;
}

/* a blurred silhouette of an SVG path, drawn on a canvas: used for the halo and the cast shadow */
export function silhouette(paths, vb, { px = 1024, pad = 0.35, blur = 24, color = '#fff' } = {}) {
  const [vx, vy, vw, vh] = vb, padU = Math.max(vw, vh) * pad;
  const W = vw + padU * 2, H = vh + padU * 2, s = px / Math.max(W, H);
  const c = document.createElement('canvas'); c.width = Math.ceil(W * s); c.height = Math.ceil(H * s);
  const x = c.getContext('2d');
  x.filter = `blur(${blur}px)`; x.fillStyle = color;
  x.setTransform(s, 0, 0, s, (padU - vx) * s, (padU - vy) * s);
  paths.forEach((d) => x.fill(new Path2D(d)));
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return { tex: t, aspect: W / H, scaleW: W / vw };
}

export function shadowTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const x = c.getContext('2d');
  const g = x.createRadialGradient(64, 64, 8, 64, 64, 64);
  g.addColorStop(0, 'rgba(40,28,12,0.5)'); g.addColorStop(0.6, 'rgba(40,28,12,0.16)'); g.addColorStop(1, 'rgba(40,28,12,0)');
  x.fillStyle = g; x.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

const svgOf = (paths, vb) => `<svg viewBox="${vb.join(' ')}">${paths.map((d) => `<path d="${d}"/>`).join('')}</svg>`;
const blendMat = (tex) => new THREE.MeshBasicMaterial({ map: tex, transparent: false, depthWrite: false, toneMapped: false,
  blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneMinusSrcAlphaFactor });

export function start(host, shared) {
  const G = shared || window.__glass || (window.__glass = { paused: false, heroP: 0, pointer: { x: 0, y: 0 } });
  G.pointer = G.pointer || { x: 0, y: 0 };
  const DPR_CAP = window.matchMedia('(max-width: 760px)').matches ? 1.5 : 1.75;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, DPR_CAP));
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.setAttribute('aria-hidden', 'true');
  canvas.className = 'hero-canvas';
  /* a lost GPU context hides the canvas again: the poster underneath shows */
  canvas.addEventListener('webglcontextlost', () => { host.classList.remove('is-live'); setRunning(false); });

  const scene = new THREE.Scene();
  const paper = new THREE.Color('#F6F5F1');
  scene.background = paper;
  scene.fog = new THREE.Fog(paper, 14, 40);
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
  camera.position.set(0, 0, 14);

  /* a bright daylight studio for reflections, so the glass reads white and never chrome */
  const pmrem = new THREE.PMREMGenerator(renderer);
  const studio = new THREE.Scene();
  studio.add(new THREE.Mesh(new THREE.SphereGeometry(20, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide,
    vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: 'varying vec3 vP; void main(){ float h = vP.y*0.5+0.5; vec3 c = mix(vec3(0.84,0.82,0.79), vec3(1.0,0.995,0.98), smoothstep(0.05,0.85,h)); gl_FragColor = vec4(c,1.0); }'
  })));
  const panel = (w, h, x, y, z, i) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(i, i, i * 0.98), side: THREE.DoubleSide })); m.position.set(x, y, z); m.lookAt(0, 0, 0); studio.add(m); };
  panel(16, 5, 0, 12, 4, 3.4); panel(5, 12, -12, 2, 5, 2.6); panel(5, 12, 12, 1, -3, 2.2); panel(12, 3, 0, -5, 12, 1.8); panel(8, 8, 0, 2, -14, 1.6);
  scene.environment = pmrem.fromScene(studio, 0.03).texture;
  pmrem.dispose();

  /* the daylight colour field the glass bends: a warm-white base with only a faint tint (Task 44), so most colour comes
     from the screens seen through the glass */
  const fieldMat = new THREE.ShaderMaterial({
    toneMapped: false, depthWrite: false,
    uniforms: {
      uTime: { value: 0 }, uPaper: { value: paper.clone() },
      uA: { value: new THREE.Color('#EDBF72') }, uB: { value: new THREE.Color('#A3C4DE') },
      uC: { value: new THREE.Color('#B2CB9C') }, uD: { value: new THREE.Color('#E9BB9E') }
    },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: `precision mediump float;
      varying vec2 vUv; uniform float uTime; uniform vec3 uPaper,uA,uB,uC,uD;
      float blob(vec2 p, vec2 c, float r){ vec2 d = p - c; return exp(-dot(d,d)/(r*r)); }
      void main(){
        vec2 p = vUv * vec2(1.6, 1.0); float t = uTime * 0.05;
        vec3 col = uPaper;
        col = mix(col, uA, 0.42 * blob(p, vec2(1.25 + 0.12*sin(t*1.3), 0.78 + 0.08*cos(t)), 0.32));
        col = mix(col, uB, 0.32 * blob(p, vec2(0.95 + 0.15*cos(t*0.9), 0.30 + 0.07*sin(t*1.1)), 0.30));
        col = mix(col, uC, 0.28 * blob(p, vec2(1.42 + 0.08*sin(t*0.7+1.0), 0.22 + 0.06*cos(t*1.4)), 0.24));
        col = mix(col, uD, 0.26 * blob(p, vec2(0.62 + 0.10*sin(t*1.2+2.0), 0.86 + 0.05*cos(t*0.8)), 0.22));
        gl_FragColor = vec4(col, 1.0);
        #include <colorspace_fragment>
      }`
  });
  const field = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), fieldMat);
  field.position.z = -12;
  scene.add(field);

  /* two concept-site screens, far back and lightly defocused (mip bias): the small poster first, then the live loop,
     whose file is requested only when the scene first runs */
  const loader = new THREE.TextureLoader();
  const shadowTex = shadowTexture();
  const videos = [];
  const mip = (t) => { t.colorSpace = THREE.SRGBColorSpace; t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter; return t; };
  function screen({ name, w, h, r, bezel, bias }) {
    const grp = new THREE.Group();
    const mat = new THREE.MeshBasicMaterial({ map: mip(loader.load(`/assets/video/loop-${name}-poster-800.jpg`)), toneMapped: false });
    mat.onBeforeCompile = (sh) => {
      sh.uniforms.uBias = { value: bias };
      sh.fragmentShader = 'uniform float uBias;\n' + sh.fragmentShader.replace('#include <map_fragment>',
        THREE.ShaderChunk.map_fragment.replace('texture2D( map, vMapUv )', 'texture2D( map, vMapUv, uBias )'));
    };
    const scr = new THREE.Mesh(roundedRect(w, h, r), mat);
    const frame = new THREE.Mesh(roundedRect(w + bezel * 2, h + bezel * 2, r + bezel), new THREE.MeshBasicMaterial({ color: 0x1b1a17, toneMapped: false }));
    frame.position.z = -0.01;
    const sh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false, toneMapped: false, opacity: 0.5 }));
    sh.scale.set(w * 1.5, h * 1.3, 1); sh.position.set(0.3, -0.45, -0.8);
    grp.add(sh, frame, scr);
    const v = document.createElement('video');
    v.muted = true; v.loop = true; v.playsInline = true; v.preload = 'none';
    v.setAttribute('muted', ''); v.setAttribute('playsinline', '');
    v.dataset.src = `/assets/video/loop-${name}.mp4`;
    v.addEventListener('playing', () => { mat.map = mip(new THREE.VideoTexture(v)); mat.needsUpdate = true; }, { once: true });
    videos.push(v);
    return grp;
  }
  const screens = { gl: screen(SCREENS.gl), hb: screen(SCREENS.hb) };
  Object.values(screens).forEach((s) => scene.add(s));

  /* the glass */
  const glass = new THREE.MeshPhysicalMaterial({
    color: 0xffffff, metalness: 0, roughness: 0.12, transmission: 1, thickness: 2.4, ior: 1.5,
    clearcoat: 1, clearcoatRoughness: 0.04, specularIntensity: 1, specularColor: 0xffffff,
    sheen: 0.25, sheenColor: new THREE.Color(0xffffff), sheenRoughness: 0.35,
    attenuationColor: new THREE.Color('#ffffff'), attenuationDistance: 12, envMapIntensity: 1.15
  });
  const markGeo = extrude(svgOf(MARK, [0, 0, 200, 200]), { depth: 40, bevelEnabled: true, bevelThickness: 14, bevelSize: 8, bevelSegments: 16, curveSegments: 56 });
  const markS = 3.5 / 152; markGeo.scale(markS, markS, markS);
  const wordGeo = extrude(svgOf([WORD_PATH], WORD_VB), { depth: 380, bevelEnabled: true, bevelThickness: 100, bevelSize: 30, bevelSegments: 10, curveSegments: 12 });
  const wordW = WORD.w, wordS = wordW / WORD_VB[2]; wordGeo.scale(wordS, wordS, wordS);
  /* the name: milky white frosted glass (WORD_GLASS), its edges kept by the white halo and the soft contact shadow */
  const wordGlass = glass.clone();
  const { attenuationColor: wordTint, ...wordProps } = WORD_GLASS;
  Object.assign(wordGlass, wordProps);
  wordGlass.attenuationColor = new THREE.Color(wordTint);
  const logo = new THREE.Group();
  const markPivot = new THREE.Group(); markPivot.add(new THREE.Mesh(markGeo, glass));
  const wordPivot = new THREE.Group(); wordPivot.add(new THREE.Mesh(wordGeo, wordGlass));
  logo.add(markPivot, wordPivot);
  scene.add(logo);

  /* a soft white halo and a cast shadow behind each part, so the letters read white and crisp (transmission samples only
     opaque objects, so these blend as "opaque" materials drawn last) */
  function backing(paths, vb, w, pivot, haloA, shadeA) {
    const halo = silhouette(paths, vb, { px: 1024, pad: 0.22, blur: 46, color: `rgba(255,255,255,${haloA})` });
    const shade = silhouette(paths, vb, { px: 1024, pad: 0.22, blur: 10, color: `rgba(52,40,24,${shadeA})` });
    const hw = w * halo.scaleW, sw = w * shade.scaleW;
    const hm = new THREE.Mesh(new THREE.PlaneGeometry(hw, hw / halo.aspect), blendMat(halo.tex));
    const sm = new THREE.Mesh(new THREE.PlaneGeometry(sw, sw / shade.aspect), blendMat(shade.tex));
    hm.position.z = -1.1; sm.position.set(0.07, -0.13, -0.5);
    hm.renderOrder = 10; sm.renderOrder = 11;
    pivot.add(hm, sm);
    return { hm, sm };
  }
  backing(MARK, [24, 24, 135, 152], 3.5 * 135 / 152, markPivot, 0.5, 0.45);
  const wordBack = backing([WORD_PATH], WORD_VB, wordW, wordPivot, 0.3, 0.5);
  /* Task 45: the name leaves by shrinking back into the depth while its halo and shadow fade (their blend materials honour
     opacity); the glass itself is never made transparent, so it neither recompiles nor flickers. Hidden at 0. */
  function wordOut(v) {
    wordPivot.visible = v > 0.001;
    wordPivot.scale.setScalar(v);
    wordPivot.position.z = -(1 - v) * 1.5;
    wordBack.hm.material.opacity = v; wordBack.sm.material.opacity = v;
  }
  /* the name's shadow is a soft contact shadow below the letters, not a glow around them */
  wordBack.sm.position.set(0.04, -0.42, -0.35); wordBack.sm.scale.set(1.02, 0.55, 1);
  wordPivot.rotation.set(WORD.rx, WORD.ry, 0); // only a slight tilt, so the letters never smear

  const key = new THREE.DirectionalLight(0xffffff, 1.5); key.position.set(-3, 5, 6); scene.add(key);
  const rim = new THREE.DirectionalLight(0xfff4e4, 1.1); rim.position.set(5, -2, -3); scene.add(rim);
  const back = new THREE.DirectionalLight(0xffffff, 2.6); back.position.set(-1, 5, -7); scene.add(back);
  /* a slow sweeping light: gliding highlights along the bevels */
  const sweep = new THREE.DirectionalLight(0xffffff, 2.0); scene.add(sweep);

  /* layout per aspect */
  let L = null;
  function layout() {
    const w = host.clientWidth || 1, h = host.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    const visH = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * (camera.position.z + 12);
    field.scale.set(visH * camera.aspect * 1.5, visH * 1.5, 1);
    L = heroLayout(camera.aspect);
    markPivot.position.y = MARK_Y; wordPivot.position.y = WORD.y;
  }
  layout();
  window.addEventListener('resize', () => { layout(); if (!running) frame(0); });

  /* motion: frame-rate independent (damped toward the pointer and the hero's scroll progress) */
  const clock = new THREE.Clock();
  let elapsed = 0, introT = 0, running = false, inView = true;
  const sm = { px: 0, py: 0, p: 0 };
  function placeScreen(name, p, t, i) {
    const s = screens[name], c = L[name];
    const k = easeOut(clamp((introT - 0.25 - i * 0.15) / 1.8, 0, 1));
    const e = smooth(p), side = i ? 1 : -1;
    /* on exit the screens drift forward and apart, up and away from the name */
    s.position.set(c[0] + side * e * 1.6, c[1] + Math.sin(t * 0.35 + i * 1.7) * 0.06 + e * (i ? 0.6 : 0.9), c[2] - (1 - k) * 12 + e * (4.5 + i));
    s.rotation.set(c[4] + (1 - k) * 0.2 + e * 0.18, c[3] - (1 - k) * 0.4 + side * e * 0.3, 0);
  }
  function frame(dt) {
    elapsed += dt; introT += dt;
    const t = elapsed;
    sm.px = damp(sm.px, G.pointer.x || 0, 2.5, dt);
    sm.py = damp(sm.py, G.pointer.y || 0, 2.5, dt);
    sm.p = damp(sm.p, G.heroP || 0, 6, dt);
    const e = smooth(sm.p);
    fieldMat.uniforms.uTime.value = t;
    const k = easeOut(clamp(introT / 2.6, 0, 1));
    /* exit (heroPose): the C settles facing the camera and grows; yaw stays within YAW so the name never reads backwards */
    const pose = heroPose(e, t, sm.px, sm.py, k);
    logo.scale.setScalar(L.logo.s * pose.scale);
    logo.position.set(L.logo.x * pose.x, L.logo.y + pose.y, pose.z);
    logo.rotation.set(pose.tilt, pose.yaw, 0);
    markPivot.rotation.y = pose.markYaw;
    wordOut(pose.word);
    sweep.position.set(Math.cos(t * 0.45) * 6, 3 + Math.sin(t * 0.3) * 2, 4 + Math.sin(t * 0.45) * 3);
    placeScreen('gl', sm.p, t, 0);
    placeScreen('hb', sm.p, t, 1);
    camera.position.x = damp(camera.position.x, sm.px * 0.3, 3, dt);
    camera.position.y = damp(camera.position.y, -sm.py * 0.18, 3, dt);
    camera.position.z = 14 - e * 1.2;
    camera.lookAt(e * L.logo.x * 0.5, 0, 0);
    renderer.render(scene, camera);
  }
  const loop = () => frame(Math.min(clock.getDelta(), 1 / 20));
  const play = (v) => {
    if (!v.src) { v.src = v.dataset.src; v.load(); }
    const r = v.play(); if (r && r.catch) r.catch(() => {});
  };
  /* runs only while on screen, with the tab visible and Pause motion off */
  function setRunning(want) {
    const on = Boolean(want) && inView && !G.paused && !document.hidden && host.classList.contains('is-live');
    if (on === running) return;
    running = on;
    if (on) { clock.getDelta(); renderer.setAnimationLoop(loop); videos.forEach(play); }
    else { renderer.setAnimationLoop(null); videos.forEach((v) => v.pause()); }
  }
  new IntersectionObserver((es) => { inView = es[es.length - 1].isIntersecting; setRunning(true); }).observe(host);
  document.addEventListener('visibilitychange', () => setRunning(true));
  (G.pauseFns = G.pauseFns || []).push(() => setRunning(true));
  if (!G.onPauseChange) G.onPauseChange = (p) => G.pauseFns.forEach((fn) => fn(p));

  /* the canvas joins the page only once its first frame is drawn, fading in over the still */
  const go = () => {
    frame(0);
    host.appendChild(canvas);
    if (canvas.animate && !G.paused) canvas.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 700, easing: 'cubic-bezier(.2,.8,.2,1)' });
    host.classList.add('is-live');
    setRunning(true);
  };
  (renderer.compileAsync ? renderer.compileAsync(scene, camera) : Promise.resolve()).then(go, go);
}
