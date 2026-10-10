// Material anime (toon + outline) dan tekstur prosedural — tanpa aset eksternal.
import * as THREE from 'three';

const gradCanvas = document.createElement('canvas');
gradCanvas.width = 4; gradCanvas.height = 1;
{
  const g = gradCanvas.getContext('2d');
  ['#8a86a0', '#bdb9d0', '#e8e4f2', '#ffffff'].forEach((c, i) => { g.fillStyle = c; g.fillRect(i, 0, 1, 1); });
}
const GRAD = new THREE.CanvasTexture(gradCanvas);
GRAD.minFilter = GRAD.magFilter = THREE.NearestFilter;
GRAD.generateMipmaps = false;

export const toon = (color, extra = {}) => new THREE.MeshToonMaterial({ color, gradientMap: GRAD, ...extra });
export const glow = (color, k = 1) => new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(k) });
const OUT = new THREE.MeshBasicMaterial({ color: 0x2b2238, side: THREE.BackSide });

export function mesh(geo, color, o = {}) {
  const m = new THREE.Mesh(geo, o.mat || toon(color, o.mx));
  if (o.pos) m.position.set(...o.pos);
  if (o.rot) m.rotation.set(...o.rot);
  if (o.scl) m.scale.set(...o.scl);
  if (o.cast !== false) m.castShadow = true;
  if (o.recv !== false) m.receiveShadow = true;
  if (o.out) {
    const ol = new THREE.Mesh(geo, OUT);
    ol.scale.setScalar(o.out === true ? 1.06 : o.out);
    ol.userData.outline = true;
    m.add(ol);
  }
  if (o.parent) o.parent.add(m);
  return m;
}
export const sphere = (r, c, o = {}) => mesh(new THREE.SphereGeometry(r, o.seg || 20, o.seg ? o.seg - 4 : 16), c, o);
export const box = (w, h, d, c, o = {}) => mesh(new THREE.BoxGeometry(w, h, d), c, o);
export const cyl = (rt, rb, h, c, o = {}) => mesh(new THREE.CylinderGeometry(rt, rb, h, o.seg || 18), c, o);
export const cone = (r, h, c, o = {}) => mesh(new THREE.ConeGeometry(r, h, o.seg || 14), c, o);
export const torus = (r, t, c, o = {}) => mesh(new THREE.TorusGeometry(r, t, 8, 24), c, o);

// ---------- tekstur kanvas ----------
function canvas(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
export const texWood = (a = '#e2bd8f', b = '#d8ad7c') => canvas(256, 256, (g, w, h) => {
  g.fillStyle = a; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 8; i++) { g.fillStyle = i % 2 ? a : b; g.fillRect(0, i * 32, w, 32); g.fillStyle = 'rgba(80,50,30,.22)'; g.fillRect(0, i * 32, w, 2); }
  for (let i = 0; i < 40; i++) { g.fillStyle = 'rgba(90,60,30,.08)'; g.fillRect(Math.random() * w, Math.random() * h, 30 + Math.random() * 60, 1.5); }
});
export const texChecker = (a, b, n = 8) => canvas(256, 256, (g, w, h) => {
  const s = w / n;
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) { g.fillStyle = (x + y) % 2 ? a : b; g.fillRect(x * s, y * s, s, s); }
});
export const texStripe = (a, b, n = 6) => canvas(128, 128, (g, w, h) => {
  const s = h / n; for (let i = 0; i < n; i++) { g.fillStyle = i % 2 ? a : b; g.fillRect(0, i * s, w, s); }
});
export const texTatami = () => canvas(256, 256, (g, w, h) => {
  g.fillStyle = '#c9d6a0'; g.fillRect(0, 0, w, h);
  for (let y = 0; y < h; y += 4) { g.fillStyle = y % 8 ? 'rgba(120,140,70,.18)' : 'rgba(255,255,255,.12)'; g.fillRect(0, y, w, 2); }
  g.fillStyle = '#5b6b3a'; g.fillRect(0, 126, w, 4); g.fillRect(126, 0, 4, h);
});
export const texGrass = () => canvas(256, 256, (g, w, h) => {
  g.fillStyle = '#a7d98f'; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 260; i++) { g.fillStyle = `rgba(${70 + Math.random() * 50},${150 + Math.random() * 60},${70},.35)`; g.fillRect(Math.random() * w, Math.random() * h, 2, 6 + Math.random() * 6); }
});
export const texBatik = () => canvas(128, 128, (g, w, h) => {
  g.fillStyle = '#7a4a2a'; g.fillRect(0, 0, w, h);
  g.strokeStyle = '#e6b85c'; g.lineWidth = 3;
  for (let y = 16; y < h; y += 32) for (let x = 16; x < w; x += 32) {
    g.beginPath(); g.arc(x, y, 10, 0, 7); g.stroke();
    g.beginPath(); g.arc(x + 16, y + 16, 6, 0, 7); g.stroke();
  }
});
export const texRugPattern = (base, line) => canvas(256, 256, (g, w, h) => {
  g.fillStyle = base; g.fillRect(0, 0, w, h);
  g.strokeStyle = line; g.lineWidth = 6; g.strokeRect(14, 14, w - 28, h - 28);
  g.lineWidth = 3; g.strokeRect(34, 34, w - 68, h - 68);
  g.fillStyle = line; g.globalAlpha = 0.35;
  for (let i = 0; i < 5; i++) { g.beginPath(); g.arc(w / 2, h / 2, 14 + i * 14, 0, 7); g.stroke(); }
});
export function texLabel(text, { fg = '#f3f1ff', bg = 'rgba(28,24,48,.82)', sub = '', w = 512, h = 128, accent = null } = {}) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d');
  const r = 28; g.fillStyle = bg;
  g.beginPath(); g.moveTo(r, 6); g.arcTo(w - 6, 6, w - 6, h - 6, r); g.arcTo(w - 6, h - 6, 6, h - 6, r);
  g.arcTo(6, h - 6, 6, 6, r); g.arcTo(6, 6, w - 6, 6, r); g.fill();
  if (accent) { g.fillStyle = accent; g.fillRect(24, 22, 8, h - 44); }
  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.font = '700 46px system-ui,sans-serif'; g.fillStyle = fg;
  g.fillText(text, w / 2 + (accent ? 8 : 0), sub ? h * 0.40 : h / 2);
  if (sub) { g.font = '500 28px system-ui,sans-serif'; g.fillStyle = 'rgba(243,241,255,.7)'; g.fillText(sub, w / 2 + (accent ? 8 : 0), h * 0.74); }
  const t = new THREE.CanvasTexture(c); t.anisotropy = 4; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
export function sprite(tex, sx, sy, o = {}) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: o.depthTest ?? true, fog: false }));
  s.scale.set(sx, sy, 1); return s;
}
export function radialTex(color = '#fff2c9') {
  return canvas(128, 128, (g, w, h) => {
    const gr = g.createRadialGradient(w / 2, h / 2, 2, w / 2, h / 2, w / 2);
    gr.addColorStop(0, color); gr.addColorStop(0.35, color.replace(')', ',0.35)').replace('rgb', 'rgba').replace('#', '#')); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
  });
}
export function glowSprite(hex, size = 2.2, opacity = 0.65) {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'); const col = new THREE.Color(hex);
  const rgb = `${(col.r * 255) | 0},${(col.g * 255) | 0},${(col.b * 255) | 0}`;
  const gr = g.createRadialGradient(64, 64, 2, 64, 64, 64);
  gr.addColorStop(0, `rgba(${rgb},0.95)`); gr.addColorStop(0.4, `rgba(${rgb},0.35)`); gr.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity }));
  s.scale.set(size, size, 1); return s;
}
