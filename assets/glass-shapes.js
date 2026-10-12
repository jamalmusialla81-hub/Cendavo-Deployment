/* Cendavo Liquid Glass shared shapes (Task 48): the small helpers both WebGL scenes use, split out of glass-scene.js so the
   inner pages (glass-page.js) never fetch the homepage scene or three's SVGLoader and BufferGeometryUtils. An ES module,
   imported by relative path (no import map); three.js r170 is vendored. Nothing here reads the page. */
import * as THREE from './vendor/three/three.module.min.js';

/* the C mark's three arcs, in the 200 x 200 box of the inline SVG logo */
export const MARK = [
  'M55.67 43.26C86.24 19.38 130.22 24.01 155.16 53.72L135.24 70.43C119.31 51.45 91.21 48.5 71.68 63.75Z',
  'M48.21 150.02C21.26 122.11 21.26 77.89 48.21 49.98L66.91 68.05C49.7 85.87 49.7 114.13 66.91 131.95Z',
  'M155.16 146.28C130.22 175.99 86.24 180.62 55.67 156.74L71.68 136.25C91.21 151.5 119.31 148.55 135.24 129.57Z'
];

/* The C as three.js shapes. Its arcs use only absolute M, C, L and Z (tested), so no SVG parser is needed; anything else
   ends the path. */
export function markShapes(paths = MARK) {
  return paths.map((d) => {
    const t = d.match(/[MCLZ]|-?\d*\.?\d+/g) || [], s = new THREE.Shape();
    let i = 0, cmd = '';
    const n = () => parseFloat(t[i++]);
    while (i < t.length) {
      if (/^[MCLZ]$/.test(t[i])) cmd = t[i++];
      if (cmd === 'M') { s.moveTo(n(), n()); cmd = 'L'; }
      else if (cmd === 'L') s.lineTo(n(), n());
      else if (cmd === 'C') s.bezierCurveTo(n(), n(), n(), n(), n(), n());
      else break; // Z: the shape closes itself
    }
    return s;
  });
}

/* The extruded glass C, laid out as glass-scene.js's extrude() lays out an SVG: y flipped (SVG is y-down), centred, normals
   recomputed. One ExtrudeGeometry takes all three shapes, so nothing needs merging. */
export function markGeometry(opts) {
  const g = new THREE.ExtrudeGeometry(markShapes(), opts);
  g.rotateX(Math.PI);
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
  x.filter = 'blur(' + blur + 'px)'; x.fillStyle = color;
  x.setTransform(s, 0, 0, s, (padU - vx) * s, (padU - vy) * s);
  paths.forEach((d) => x.fill(new Path2D(d)));
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return { tex: t, aspect: W / H, scaleW: W / vw };
}

/* Task 48: glass-boot.js tests for WebGL2 with the renderer's own context attributes and hands that canvas and context
   over (gl), so the scene draws with them and no throwaway context is left behind. Without one, three makes its own. */
export function rendererOptions(gl) {
  const base = { antialias: true, alpha: false, powerPreference: 'high-performance' };
  return gl && gl.canvas && gl.context ? { ...base, canvas: gl.canvas, context: gl.context } : base;
}
