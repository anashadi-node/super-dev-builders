// Dunia 3D SDB Workspace: kantor isometrik pastel, 15 ruangan, basement, taman, rute jalan.
import * as THREE from 'three';
import { OrbitControls } from '../vendor/OrbitControls.js';
import { toon, mesh, sphere, box, cyl, cone, torus, glow, texWood, texChecker, texStripe, texTatami, texGrass, texBatik, texRugPattern, texLabel, sprite, glowSprite } from './toon.js';
import { CAST, BARISTA, buildCharacter, animate } from './chars.js';

const COLX = [-18, -9, 0, 9, 18], ROWZ = [-14, -4, 6], RW = 7.6, RD = 8;
const CORR = [-9, 1, 11.8];                  // z koridor: antar baris 0-1, antar baris 1-2, taman
const AISLES = [-13.5, -4.5, 4.5, 13.5];

export const ROOMS = [
  { id: 'owner', name: 'Kantor Owner', col: 0, row: 0, floor: '#f6dcc6', wall: '#f2c9b0', accent: '#e8483f' },
  { id: 'arch', name: 'Studio Arsitek', col: 1, row: 0, floor: '#d3e6f6', wall: '#bcd8f0', accent: '#4a9ad8' },
  { id: 'front', name: 'Studio Seni UI', col: 2, row: 0, floor: '#fbe4ef', wall: '#f6c9dd', accent: '#e74a8a' },
  { id: 'build', name: 'Bengkel Backend', col: 3, row: 0, floor: '#d9ecd7', wall: '#bfe0bd', accent: '#1f9fa8' },
  { id: 'rec', name: 'Ruang Pengintai', col: 4, row: 0, floor: '#e4dcef', wall: '#cfc2e4', accent: '#4a5a9a' },
  { id: 'qa', name: 'Dojo QA', col: 0, row: 1, floor: '#cfdcae', wall: '#e6dcc0', accent: '#4fae4f' },
  { id: 'sec', name: 'Brankas & Arsip', col: 1, row: 1, floor: '#dccdee', wall: '#c4aee0', accent: '#7a4aa8' },
  { id: 'aud', name: 'Ruang Sidang Audit', col: 2, row: 1, floor: '#e8ecf4', wall: '#d4dcec', accent: '#2b4a8a' },
  { id: 'ops', name: 'Dapur DevOps', col: 3, row: 1, floor: '#f8e8c0', wall: '#f3d9a0', accent: '#f08a35' },
  { id: 'grd', name: 'Pos Gerbang', col: 4, row: 1, floor: '#efdcb8', wall: '#e0c898', accent: '#c4412f' },
  { id: 'villa', name: 'Proyek: Villa Agency', col: 0, row: 2, floor: '#d8efe8', wall: '#bfe3d8', accent: '#2fa38a', project: 'villa-agency' },
  { id: 'rtrw', name: 'Proyek: RT-RW Portal', col: 1, row: 2, floor: '#f0e8d2', wall: '#e6d8b0', accent: '#c78a2f', project: 'rt-rw-portal' },
  { id: 'contoh', name: 'Proyek: CONTOH', col: 2, row: 2, floor: '#eeeef2', wall: '#e2e2ea', accent: '#9a9ab0', project: null, ghost: true },
  { id: 'lib', name: 'Perpustakaan Pengetahuan', col: 3, row: 2, floor: '#efd9c0', wall: '#dcb894', accent: '#8a5a3a' },
  { id: 'lounge', name: 'Kafe & Arcade', col: 4, row: 2, floor: '#fbe0d6', wall: '#f4c4b4', accent: '#e8786a' },
];
ROOMS.forEach((r) => { r.cx = COLX[r.col]; r.cz = ROWZ[r.row]; r.doorBack = r.row === 2; r.level = r.row === 0 ? 0 : 1; });
const roomById = Object.fromEntries(ROOMS.map((r) => [r.id, r]));
const doorIn = (r) => new THREE.Vector3(r.cx, 0, r.row === 0 ? r.cz + 3.2 : r.row === 1 ? r.cz + 3.2 : r.cz - 3.2);
const seatOf = (r) => new THREE.Vector3(r.cx, 0, r.cz - 1.5);

export function createWorld(host, opts = {}) {
  const coarse = matchMedia('(pointer:coarse)').matches || innerWidth < 800;
  const renderer = new THREE.WebGLRenderer({ antialias: !coarse, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, coarse ? 1.5 : 2));
  renderer.shadowMap.enabled = !coarse; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  host.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0xf6e7d4, 90, 200);

  // kamera
  let aspect = 1, frustum = 30;
  const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, -200, 400);
  const persp = new THREE.PerspectiveCamera(62, 1, 0.1, 300);
  let cam = ortho;
  ortho.position.set(30, 37, 30);
  const controls = new OrbitControls(ortho, renderer.domElement);
  controls.target.set(0, 0, -2); controls.enableDamping = true; controls.dampingFactor = 0.09;
  controls.minZoom = 0.55; controls.maxZoom = 3.6; controls.maxPolarAngle = Math.PI * 0.49; controls.minPolarAngle = 0.25;
  controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
  controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
  ortho.zoom = innerWidth < 800 && innerHeight > innerWidth ? 0.78 : 1.16; controls.screenSpacePanning = true; controls.update();
  let shiftPx = 0;
  function applyFrame() {
    const half = frustum * aspect, w = host.clientWidth || 1, sh = (shiftPx / w) * 2 * half;
    ortho.left = -half + sh; ortho.right = half + sh; ortho.top = frustum; ortho.bottom = -frustum; ortho.updateProjectionMatrix();
  }
  const resize = () => {
    const w = host.clientWidth, h = host.clientHeight; aspect = w / h;
    renderer.setSize(w, h);
    frustum = aspect < 1 ? 46 : 30;
    applyFrame();
    persp.aspect = aspect; persp.updateProjectionMatrix();
  };
  addEventListener('resize', resize); resize();

  // cahaya hangat
  scene.add(new THREE.HemisphereLight(0xfff0dc, 0xb7c3e6, 1.15));
  const sun = new THREE.DirectionalLight(0xffe0b4, 2.0);
  sun.position.set(26, 44, 20); sun.castShadow = !coarse;
  sun.shadow.mapSize.set(2048, 2048); const sc = sun.shadow.camera; sc.left = -40; sc.right = 40; sc.top = 40; sc.bottom = -40; sc.near = 5; sc.far = 120; sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.04;
  scene.add(sun);
  scene.add(new THREE.DirectionalLight(0xbfd2ff, 0.5).translateX(-20).translateY(18).translateZ(-10));

  // ---------------- lantai
  const groundG = new THREE.Group(); scene.add(groundG);
  const fadeTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d'); const gr = g.createRadialGradient(128, 128, 40, 128, 128, 128); gr.addColorStop(0, '#fff'); gr.addColorStop(0.72, '#fff'); gr.addColorStop(1, '#000'); g.fillStyle = gr; g.fillRect(0, 0, 256, 256); return new THREE.CanvasTexture(c); })();
  const lawn = mesh(new THREE.CircleGeometry(40, 48), '#cfe6b4', { mat: new THREE.MeshBasicMaterial({ color: 0xcfe8b6, transparent: true, alphaMap: fadeTex, depthWrite: false }), parent: scene, cast: false });
  lawn.rotation.x = -Math.PI / 2; lawn.position.set(0, -1.52, -2); lawn.renderOrder = -1;
  const slab = box(46, 1.5, 31, '#e3c9a4', { parent: groundG }); slab.position.set(0, -0.75, -4);
  const plaza = box(45.6, 0.04, 30.6, '#f1dcc0', { parent: groundG, mat: toon('#ffffff', { map: (() => { const t = texWood('#ecd3b0', '#e2c59e'); t.repeat.set(7, 5); return t; })() }) }); plaza.position.set(0, 0.02, -4); plaza.receiveShadow = true;
  const slabEdge = box(46.6, 0.4, 31.6, '#c8a67a', { parent: groundG }); slabEdge.position.set(0, -1.1, -4);

  // ---------------- helper
  const pickables = [];
  const spinners = [], rockers = [], steams = [], lanterns = [], swayers = [], denTiles = [];
  let projectsData = [];
  const add = (m, p) => { (p || scene).add(m); return m; };
  const P = (parent, geo, c, pos, o = {}) => { const m = mesh(geo, c, { parent, ...o }); m.position.set(...pos); m.castShadow = o.cast !== false; m.receiveShadow = true; return m; };
  function deskAt(g, x, z, col = '#c89a68', w = 2.8, d = 1.2) {
    P(g, new THREE.BoxGeometry(w, 0.14, d), col, [x, 0.95, z], { out: 1.0 });
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => P(g, new THREE.BoxGeometry(0.12, 0.9, 0.12), '#a67a4a', [x + a * (w / 2 - 0.15), 0.47, z + b * (d / 2 - 0.15)]));
  }
  function monitorAt(g, x, z, hue = '#9ad7ff') {
    P(g, new THREE.BoxGeometry(1.0, 0.7, 0.08), '#3a3550', [x, 1.5, z], { out: 1.0 });
    P(g, new THREE.BoxGeometry(0.9, 0.6, 0.02), hue, [x, 1.5, z + 0.05], { mat: glow(hue, 0.9), cast: false });
    P(g, new THREE.BoxGeometry(0.12, 0.2, 0.12), '#3a3550', [x, 1.1, z]);
  }
  function plant(g, x, z, s = 1, col = '#5bb36a') {
    P(g, new THREE.CylinderGeometry(0.28 * s, 0.22 * s, 0.4 * s, 14), '#d98b64', [x, 0.2 * s, z], { out: 1.05 });
    for (let i = 0; i < 6; i++) { const a = i * 1.05; const l = P(g, new THREE.SphereGeometry(0.3 * s, 10, 8), i % 2 ? col : '#74c880', [x + Math.sin(a) * 0.22 * s, (0.65 + (i % 3) * 0.14) * s, z + Math.cos(a) * 0.22 * s], { out: 1.06 }); l.scale.set(1, 1.2, 1); }
  }
  function chair(g, x, z, col = '#e87a6a') {
    P(g, new THREE.BoxGeometry(0.9, 0.12, 0.9), col, [x, 0.5, z], { out: 1.04 });
    P(g, new THREE.BoxGeometry(0.9, 0.9, 0.12), col, [x, 0.98, z - 0.44], { out: 1.04 });
    P(g, new THREE.CylinderGeometry(0.06, 0.06, 0.5, 8), '#6a5a4a', [x, 0.25, z]);
  }
  function lamp(g, x, z, col = '#ffe3a8') {
    P(g, new THREE.CylinderGeometry(0.05, 0.05, 1.5, 8), '#6a5a4a', [x, 0.75, z]);
    P(g, new THREE.ConeGeometry(0.4, 0.4, 14, 1, true), col, [x, 1.65, z], { out: 1.0, mx: { side: THREE.DoubleSide } });
    const gl = glowSprite(col, 2.4, 0.5); gl.position.set(x, 1.55, z); g.add(gl); return gl;
  }
  function shelf(g, x, z, w = 2.4, h = 2.6, rot = 0, books = 14) {
    const s = new THREE.Group(); s.position.set(x, 0, z); s.rotation.y = rot; g.add(s);
    P(s, new THREE.BoxGeometry(w, h, 0.5), '#b88556', [0, h / 2, 0], { out: 1.0 });
    const rows = Math.floor(h / 0.65);
    const cols = ['#e8786a', '#f2c14e', '#6ab4d8', '#8fcf8a', '#b58ae0', '#f4a6c1', '#7a9ae0'];
    for (let r = 0; r < rows; r++) {
      P(s, new THREE.BoxGeometry(w - 0.1, 0.06, 0.52), '#8a5f38', [0, 0.18 + r * 0.62, 0.02]);
      let xx = -w / 2 + 0.2;
      while (xx < w / 2 - 0.2) { const bw = 0.12 + Math.random() * 0.1, bh = 0.35 + Math.random() * 0.15; P(s, new THREE.BoxGeometry(bw, bh, 0.36), cols[(Math.random() * cols.length) | 0], [xx, 0.22 + bh / 2 + r * 0.62, 0.1]); xx += bw + 0.02; }
    }
    return s;
  }
  function phoneBooth(g, x, z, rot = 0, col = '#c98d5e') { // booth kayu (airbnb style)
    const b = new THREE.Group(); g.add(b); b.position.set(x, 0, z); b.rotation.y = rot;
    P(b, new THREE.BoxGeometry(1.3, 2.6, 1.3), col, [0, 1.3, 0]);
    P(b, new THREE.BoxGeometry(1.5, 0.18, 1.5), '#8a6238', [0, 2.66, 0]);
    P(b, new THREE.BoxGeometry(0.8, 1.7, 0.05), '#bfe3e8', [0, 1.35, 0.66], { mat: toon('#ffffff', { transparent: true, opacity: 0.55 }) });
    P(b, new THREE.BoxGeometry(0.9, 0.1, 0.5), '#7a5a3a', [0, 1.0, 0.35]);
    const gl = glowSprite('#ffe0b0', 1.8, 0.5); gl.position.set(0, 2.2, 0); b.add(gl); steams.push(gl); b.userData.prop='booth'; return b; }
  function commTable(g, x, z, rot = 0) { // meja komunal panjang (timber)
    const t = new THREE.Group(); t.userData.prop='commtable'; g.add(t); t.position.set(x, 0, z); t.rotation.y = rot;
    P(t, new THREE.BoxGeometry(7.2, 0.16, 1.7), '#c89a68', [0, 0.95, 0]);
    [-2.9, 2.9].forEach((px) => P(t, new THREE.BoxGeometry(0.3, 0.9, 1.4), '#9a7a52', [px, 0.45, 0]));
    [-2.4, -0.8, 0.8, 2.4].forEach((px) => { const c = new THREE.Group(); c.userData.prop='chair'; t.add(c); c.position.set(px, 0, 1.35); c.rotation.y = Math.PI; chair(c, 0, 0, '#e0b090'); });
    [-2.4, 0.8].forEach((px) => { const c = new THREE.Group(); c.userData.prop='chair'; t.add(c); c.position.set(px, 0, -1.35); chair(c, 0, 0, '#a8c8e0'); });
    return t; }
  function bigTree(g, x, z, s = 1) { // tanaman indoor besar (Google biophilic)
    const t = new THREE.Group(); g.add(t); t.position.set(x, 0, z); t.scale.setScalar(s);
    P(t, new THREE.CylinderGeometry(0.42, 0.52, 0.6, 12), '#b98a5e', [0, 0.3, 0]);
    P(t, new THREE.CylinderGeometry(0.09, 0.13, 2.6, 8), '#8a6a48', [0, 1.7, 0]);
    for (let i = 0; i < 7; i++) { const leaf = sphere(0.55, i % 2 ? '#4f9e5e' : '#63b573', { parent: t, cast: false, scl: [1, 0.55, 1] });
      leaf.position.set(Math.sin(i * 2.4) * 0.75, 2.6 + Math.cos(i * 1.7) * 0.7, Math.cos(i * 2.1) * 0.75); }
    t.userData.prop='tree'; return t; }
  function pendantLamp(g, x, z, y = 2.9, col = '#ffd9a0') { // lampu gantung warm
    const t = new THREE.Group(); g.add(t); t.position.set(x, 0, z);
    P(t, new THREE.CylinderGeometry(0.015, 0.015, 1.3, 6), '#5a5048', [0, y + 0.65, 0]);
    t.userData.prop='pendant'; const shade = P(t, new THREE.ConeGeometry(0.55, 0.5, 14, 1, true), '#e8b06a', [0, y, 0], { cast: false, out: 1.02 });
    shade.rotation.x = Math.PI; const gl = glowSprite(col, 1.9, 0.55); gl.position.set(0, y - 0.25, 0); t.add(gl); steams.push(gl); return t; }
  function rug(g, x, z, w, d, col, line) { const r = P(g, new THREE.BoxGeometry(w, 0.05, d), col, [x, 0.07, z], { mat: toon('#ffffff', { map: texRugPattern(col, line) }), cast: false }); return r; }
  function banner(g, x, z, col, rot = 0) { const b = P(g, new THREE.BoxGeometry(1.2, 1.8, 0.06), col, [x, 2.5, z], { out: 1.0 }); b.rotation.y = rot; P(g, new THREE.BoxGeometry(1.5, 0.08, 0.1), '#8a6a3a', [x, 3.45, z]); return b; }
  function board16(g, x, y, z, states) { // papan keputusan 16 tahap
    P(g, new THREE.BoxGeometry(3.2, 2.0, 0.1), '#7a5a3a', [x, y, z], { out: 1.0 });
    P(g, new THREE.BoxGeometry(3.0, 1.8, 0.04), '#f4ead2', [x, y, z + 0.06], { cast: false });
    const tiles = [];
    for (let i = 0; i < 16; i++) { const cx = x - 1.25 + (i % 8) * 0.36, cy = y + 0.4 - Math.floor(i / 8) * 0.55;
      const t = P(g, new THREE.BoxGeometry(0.3, 0.4, 0.03), '#c9c3b0', [cx, cy, z + 0.1], { mat: new THREE.MeshBasicMaterial({ color: 0xc9c3b0 }), cast: false }); tiles.push(t); }
    return tiles;
  }
  const LEVEL = { done: 0x47d17a, brief: 0xf2b84a, todo: 0xc9c3b0, ghost: 0xe2e2ea };

  // ---------------- ruangan
  const roomGroups = {}, boards = {};
  ROOMS.forEach((r) => {
    const g = new THREE.Group(); g.position.set(r.cx, 0, r.cz); scene.add(g); roomGroups[r.id] = g; r.group = g;
    const fl = P(groundG, new THREE.BoxGeometry(RW, 0.1, RD), r.floor, [r.cx, 0.06, r.cz], { cast: false, mat: (() => { const tx = floorTex(r); return tx ? toon('#ffffff', { map: tx }) : toon(r.floor); })() });
    fl.userData.room = r.id; pickables.push(fl); r.floorMesh = fl;
    const wallM = toon(r.ghost ? '#e8e8f0' : r.wall, r.ghost ? { transparent: true, opacity: 0.75 } : {});
    const H = 3.0, T = 0.28;
    const W = (w, h, d, x, y, z) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wallM); m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; g.add(m);
      const ol = new THREE.Mesh(m.geometry, new THREE.MeshBasicMaterial({ color: 0x2b2238, side: THREE.BackSide })); ol.scale.setScalar(1.01); m.add(ol); return m; };
    // belakang (-z) & kiri (-x) tinggi; depan (+z) & kanan (+x) rendah (cutaway)
    if (r.doorBack) { W(RW / 2 - 1.1, H, T, -(RW / 4 + 0.55), H / 2, -RD / 2); W(RW / 2 - 1.1, H, T, (RW / 4 + 0.55), H / 2, -RD / 2); P(g, new THREE.BoxGeometry(2.2, 0.5, T), r.accent, [0, H - 0.25, -RD / 2]); }
    else W(RW, H, T, 0, H / 2, -RD / 2);
    W(T, H, RD, -RW / 2, H / 2, 0);
    W(T, 0.7, RD, RW / 2, 0.35, 0);
    if (r.doorBack) W(RW, 0.7, T, 0, 0.35, RD / 2);
    else { W(RW / 2 - 1.1, 0.7, T, -(RW / 4 + 0.55), 0.35, RD / 2); W(RW / 2 - 1.1, 0.7, T, (RW / 4 + 0.55), 0.35, RD / 2); }
    // plakat nama
    const lab = sprite(texLabel(r.name, { w: 640, h: 128, accent: r.accent, sub: r.ghost ? 'CONTOH · bukan proyek nyata' : (r.project ? 'proyek nyata' : '') }), 5.2, 1.04, { depthTest: false });
    lab.position.set(0, H + 0.9, -RD / 2 + 0.2); lab.renderOrder = 10; g.add(lab); r.label = lab;
    buildRoom(r, g);
  });
  function floorTex(r) {
    if (r.id === 'qa') return texTatami();
    if (r.id === 'ops') { const t = texChecker('#fbf0d4', '#f4d79a', 8); t.repeat.set(2, 2); return t; }
    if (r.id === 'grd') return null;
    if (r.id === 'lib') { const t = texWood('#e4c5a0', '#d6b088'); return t; }
    if (r.id === 'aud') { const t = texChecker('#eef0f6', '#d5dae8', 8); t.repeat.set(2, 2); return t; }
    return null;
  }

  function buildRoom(r, g) {
    const a = r.accent;
    const desk = (c) => { deskAt(g, 0, -0.6, c); chair(g, 0, -1.8, a); };
    switch (r.id) {
      case 'owner':
        desk('#c89a68'); monitorAt(g, 0, -0.9, '#ffe3a8'); rug(g, 0, 1.2, 4.2, 3, '#f1b8a8', '#e8483f');
        banner(g, -3.5, -3.8, '#e8483f', 0);
        P(g, new THREE.CylinderGeometry(0.4, 0.4, 0.07, 16), '#f1d17a', [-3.5, 2.4, -3.72], { rot: [Math.PI / 2, 0, 0] });
        board16(g, 2.2, 2.3, -3.8, []); // papan keputusan (dekoratif di Owner)
        shelf(g, 3.1, -2.0, 1.6, 2.2, -Math.PI / 2, 8);
        P(g, new THREE.CylinderGeometry(0.25, 0.3, 0.5, 12), '#f2c14e', [-2.8, 0.25, -1.4], { out: 1.05 }); plant(g, -3.2, 0.8, 1.1); plant(g, 3.2, 3, 0.9); lamp(g, 3.2, -3.2);
        break;
      case 'arch': {
        const tb = P(g, new THREE.BoxGeometry(3, 0.12, 1.8), '#d9bd90', [0, 1.05, -0.4], { out: 1.0, rot: [-0.18, 0, 0] });
        [-1, 1].forEach((s) => P(g, new THREE.BoxGeometry(0.12, 1.0, 0.12), '#9a7a4a', [s * 1.3, 0.5, -0.4]));
        P(g, new THREE.BoxGeometry(2.7, 0.03, 1.5), '#4a9ad8', [0, 1.14, -0.4], { rot: [-0.18, 0, 0], mat: new THREE.MeshBasicMaterial({ color: 0x4a9ad8 }) });
        for (let i = 0; i < 4; i++) P(g, new THREE.BoxGeometry(2.0 - i * 0.3, 0.02, 0.04), '#ffffff', [0, 1.16 + i * 0.0, -0.8 + i * 0.3], { rot: [-0.18, 0, 0], mat: new THREE.MeshBasicMaterial({ color: 0xffffff }), cast: false });
        chair(g, 0, -1.8, a);
        P(g, new THREE.CylinderGeometry(0.12, 0.2, 0.5, 10), '#b88556', [2.6, 0.25, -2.6]);
        const gl = P(g, new THREE.SphereGeometry(0.7, 20, 16), '#5aa8e0', [2.6, 1.25, -2.6], { out: 1.04 }); gl.userData.spin = 0.4; spinners.push(gl);
        P(g, new THREE.TorusGeometry(0.85, 0.04, 8, 28), '#d4b24a', [2.6, 1.25, -2.6], { rot: [0.3, 0, 0.4] });
        P(g, new THREE.BoxGeometry(0.4, 0.4, 1.6), '#bf9a6a', [-3.1, 0.25, -2.4]);
        for (let i = 0; i < 4; i++) P(g, new THREE.CylinderGeometry(0.12, 0.12, 1.5, 10), ['#f8f4ea', '#bde0f6', '#f6dca8', '#f6c0d0'][i], [-3.1 + (i % 2) * 0.3, 0.9, -2.4 + (i - 1.5) * 0.35], { rot: [Math.PI / 2, 0, 0.3], out: 1.04 });
        rug(g, 0, 1.6, 4, 2.6, '#cfe3f5', a); plant(g, 3.1, 0.6, 1.0); lamp(g, -3.2, 1.2); break; }
      case 'front': {
        // easel + kanvas warna-warni
        P(g, new THREE.BoxGeometry(0.12, 2.6, 0.12), '#a9794a', [-1.0, 1.3, -1.0], { rot: [0, 0, 0.12] }); P(g, new THREE.BoxGeometry(0.12, 2.6, 0.12), '#a9794a', [1.0, 1.3, -1.0], { rot: [0, 0, -0.12] });
        P(g, new THREE.BoxGeometry(2.4, 1.7, 0.1), '#fffdf8', [0, 1.9, -0.9], { out: 1.0 });
        const cols = ['#f2c14e', '#e74a8a', '#6ab4d8', '#8fcf8a', '#b58ae0', '#ee8a3a'];
        for (let i = 0; i < 6; i++) P(g, new THREE.BoxGeometry(0.7, 0.45, 0.04), cols[i], [-0.8 + (i % 3) * 0.8, 2.2 - Math.floor(i / 3) * 0.6, -0.82], { mat: new THREE.MeshBasicMaterial({ color: cols[i] }), cast: false });
        P(g, new THREE.CylinderGeometry(0.5, 0.5, 0.06, 20), '#d9b280', [-2.4, 0.95, 0.4], { out: 1.04 });
        cols.forEach((c, i) => P(g, new THREE.SphereGeometry(0.1, 8, 6), c, [-2.4 + Math.sin(i) * 0.3, 1.0, 0.4 + Math.cos(i) * 0.3]));
        [['#e74a8a', 2.4, 0.2], ['#6ab4d8', 2.6, 1.0], ['#f2c14e', 2.1, 1.4]].forEach(([c, x, z]) => P(g, new THREE.CylinderGeometry(0.28, 0.24, 0.5, 12), c, [x, 0.25, z], { out: 1.05 }));
        chair(g, 0, -1.9 + 0.9, a); monitorAt(g, 2.5, -3.2, '#ffd0e8'); plant(g, -3.1, -3.0, 1.1); rug(g, 0, 2, 4.2, 2.2, '#fbe4ef', a); break; }
      case 'build': {
        desk('#b08a5a');
        P(g, new THREE.BoxGeometry(1.0, 0.6, 0.8), '#6a6f7a', [2.4, 0.3, -1.2], { out: 1.03 }); P(g, new THREE.BoxGeometry(1.4, 0.25, 0.7), '#8a8f9a', [2.4, 0.72, -1.2], { out: 1.03 });
        for (let i = 0; i < 3; i++) { const gr = P(g, new THREE.CylinderGeometry(0.5 - i * 0.1, 0.5 - i * 0.1, 0.12, 8), ['#e8b04a', '#d96b6b', '#6ab4d8'][i], [-2.6 + i * 0.5, 0.2 + i * 0.12, 1.2 - i * 0.3], { out: 1.04 }); gr.userData.spin = 0.5 * (i % 2 ? -1 : 1); spinners.push(gr); }
        P(g, new THREE.BoxGeometry(3.3, 1.6, 0.1), '#c9a56a', [-1.0, 2.4, -3.82]); for (let i = 0; i < 5; i++) P(g, new THREE.BoxGeometry(0.1, 0.9 - (i % 2) * 0.3, 0.06), '#c9d0de', [-2.2 + i * 0.6, 2.4, -3.72]);
        [[3, 2.6, 0.7], [2.5, 2.9, 1.0]].forEach(([x, z, s]) => P(g, new THREE.BoxGeometry(s, s * 0.8, s), '#c28a4a', [x, s * 0.4, z], { out: 1.04 }));
        // rak server mini (data)
        P(g, new THREE.BoxGeometry(0.9, 2.0, 0.8), '#3a4a5a', [3.2, 1.0, -3.0], { out: 1.03 }); for (let i = 0; i < 5; i++) P(g, new THREE.BoxGeometry(0.7, 0.05, 0.04), i % 2 ? '#47d17a' : '#f2b84a', [3.2, 0.5 + i * 0.3, -2.58], { mat: new THREE.MeshBasicMaterial({ color: i % 2 ? 0x47d17a : 0xf2b84a }), cast: false });
        monitorAt(g, 0, -0.9, '#9ae0b0'); break; }
      case 'rec': {
        P(g, new THREE.BoxGeometry(2.6, 0.12, 1.2), '#8a6a4a', [0, 0.55, -0.6], { out: 1.0 }); [-1.1, 1.1].forEach((x) => P(g, new THREE.BoxGeometry(0.15, 0.5, 0.9), '#6a4a3a', [x, 0.25, -0.6]));
        for (let i = 0; i < 7; i++) P(g, new THREE.CylinderGeometry(0.1, 0.1, 0.5, 8), ['#f1e2b8', '#e8d6a0'][i % 2], [-3.2 + i * 0.5, 0.55 + 0.1 * (i % 3), -3.2], { rot: [0, 0, Math.PI / 2], out: 1.04 });
        // dinding gulungan
        for (let i = 0; i < 9; i++) P(g, new THREE.BoxGeometry(0.34, 1.4 + (i % 3) * 0.3, 0.03), ['#f1e2b8', '#e6d1a0'][i % 2], [-3.2 + i * 0.8, 2.2, -3.82], { cast: false, mat: new THREE.MeshBasicMaterial({ color: i % 2 ? 0xe6d1a0 : 0xf1e2b8 }) });
        const ln = P(g, new THREE.SphereGeometry(0.28, 12, 10), '#e8786a', [2.6, 1.4, 0.4], { out: 1.05, mat: glow('#ff9a8a', 1) }); P(g, new THREE.CylinderGeometry(0.03, 0.03, 0.9, 6), '#6a5a4a', [2.6, 1.9, 0.4]); lanterns.push(ln);
        const glw = glowSprite('#ff9a8a', 2.2, 0.5); glw.position.set(2.6, 1.4, 0.4); g.add(glw);
        [-1, 1].forEach((s) => P(g, new THREE.CylinderGeometry(0.22, 0.22, 0.1, 16), '#c9a56a', [s * 1.6, 0.1, 1.5], { out: 1.04 }));
        rug(g, 0, 1.4, 4.4, 2.8, '#e4dcef', a); plant(g, -3.1, 2.6, 1.0); break; }
      case 'qa': {
        P(g, new THREE.BoxGeometry(2.4, 0.14, 0.4), '#a67a4a', [3.0, 1.0, -2.0], { rot: [0, Math.PI / 2, 0] }); for (let i = 0; i < 3; i++) P(g, new THREE.BoxGeometry(0.05, 1.6, 0.05), '#d8dde8', [3.3, 1.15, -2.9 + i * 0.8], { out: 1.1, rot: [0, 0, 0.35] });
        // dummy latihan
        P(g, new THREE.CylinderGeometry(0.28, 0.32, 1.4, 12), '#c89a68', [-2.4, 0.7, 0.8], { out: 1.05 }); P(g, new THREE.BoxGeometry(1.2, 0.14, 0.14), '#c89a68', [-2.4, 1.15, 0.8]); P(g, new THREE.SphereGeometry(0.3, 14, 12), '#e8c89a', [-2.4, 1.7, 0.8], { out: 1.05 });
        P(g, new THREE.BoxGeometry(1.4, 2.0, 0.05), '#f4ead2', [-1.4, 2.4, -3.82], { cast: false }); P(g, new THREE.BoxGeometry(0.5, 1.2, 0.03), '#2b2238', [-1.4, 2.4, -3.78], { mat: new THREE.MeshBasicMaterial({ color: 0x2b2238 }), cast: false });
        for (let i = 0; i < 4; i++) P(g, new THREE.BoxGeometry(0.08, 1.2, 0.5), '#8a5f38', [-3.4 + i * 0.7, 0.6, -3.4]);
        // target uji (lingkaran bullseye)
        P(g, new THREE.CylinderGeometry(0.6, 0.6, 0.08, 20), '#fffdf8', [1.6, 1.8, -3.78], { rot: [Math.PI / 2, 0, 0], out: 1.04 }); P(g, new THREE.CylinderGeometry(0.38, 0.38, 0.1, 20), '#e8483f', [1.6, 1.8, -3.76], { rot: [Math.PI / 2, 0, 0] }); P(g, new THREE.CylinderGeometry(0.16, 0.16, 0.12, 20), '#fffdf8', [1.6, 1.8, -3.74], { rot: [Math.PI / 2, 0, 0] });
        chair(g, 0, -1.8, '#6a8a5a'); deskAt(g, 0, -0.6, '#9a7a52', 2.2, 1.0); monitorAt(g, 0, -0.9, '#bde8c0'); plant(g, 3.0, 2.8, 1.0, '#74c880'); break; }
      case 'sec': {
        const vd = P(g, new THREE.CylinderGeometry(1.5, 1.5, 0.3, 28), '#8e92a4', [1.9, 1.9, -3.75], { rot: [Math.PI / 2, 0, 0], out: 1.03 }); P(g, new THREE.TorusGeometry(1.2, 0.08, 8, 30), '#d4b24a', [1.9, 1.9, -3.58]); P(g, new THREE.CylinderGeometry(0.28, 0.28, 0.2, 12), '#d4b24a', [1.9, 1.9, -3.5], { rot: [Math.PI / 2, 0, 0] });
        for (let i = 0; i < 6; i++) P(g, new THREE.BoxGeometry(0.12, 0.5, 0.1), '#c9ccd8', [1.9 + Math.cos(i * 1.05) * 0.8, 1.9 + Math.sin(i * 1.05) * 0.8, -3.55], { rot: [0, 0, i * 1.05] });
        shelf(g, -2.9, -3.2, 2.2, 3.0, 0, 18); deskAt(g, 0, -0.5, '#6a4a82', 2.4, 1.0); chair(g, 0, -1.8, '#7a4aa8'); lamp(g, 1.0, -0.5, '#d6b8ff'); P(g, new THREE.BoxGeometry(0.5, 0.08, 0.7), '#fff4dc', [-0.5, 1.05, -0.45], { rot: [0, 0.2, 0] });
        rug(g, 0, 1.7, 4.4, 2.6, '#dccdee', a); P(g, new THREE.BoxGeometry(0.9, 1.5, 0.9), '#5a5f72', [3.0, 0.75, 0.6], { out: 1.03 }); break; }
      case 'aud': {
        P(g, new THREE.BoxGeometry(4.0, 0.9, 1.4), '#8a6a4a', [0, 0.45, -2.8], { out: 1.03 }); for (let i = 0; i < 2; i++) P(g, new THREE.BoxGeometry(4.4 - i * 0.2, 0.2, 1.8 - i * 0.2), '#a98a62', [0, 0.1 + i * 0.1, -2.8]);
        P(g, new THREE.BoxGeometry(4.2, 0.12, 1.6), '#6a4a32', [0, 1.4, -2.8], { out: 1.03 });
        // neraca
        P(g, new THREE.CylinderGeometry(0.05, 0.08, 1.2, 8), '#d4b24a', [-1.4, 1.95, -2.7]); const beam = P(g, new THREE.BoxGeometry(1.6, 0.06, 0.06), '#d4b24a', [-1.4, 2.55, -2.7]); beam.userData.rock = 1; rockers.push(beam);
        [-0.7, 0.7].forEach((x) => P(g, new THREE.CylinderGeometry(0.28, 0.22, 0.08, 12), '#d4b24a', [-1.4 + x, 2.0, -2.7], { out: 1.04 }));
        P(g, new THREE.CylinderGeometry(0.15, 0.15, 0.06, 12), '#5a3a22', [1.4, 1.5, -2.7], { out: 1.04 });
        [-2, 0, 2].forEach((x) => P(g, new THREE.BoxGeometry(1.8, 0.4, 0.5), '#9a7a52', [x * 0.9, 0.3, 2.0], { out: 1.03 }));
        banner(g, 3.2, -3.7, '#2b4a8a', 0); P(g, new THREE.CylinderGeometry(0.35, 0.35, 0.06, 6), '#f6f7fb', [3.2, 2.5, -3.62], { rot: [Math.PI / 2, 0, 0] });
        chair(g, 0, -1.9 + 0.2, '#2b4a8a'); plant(g, -3.2, 2.6, 1.0); break; }
      case 'ops': {
        P(g, new THREE.BoxGeometry(4.2, 1.0, 1.1), '#d8dde8', [0, 0.5, -3.2], { out: 1.03 }); P(g, new THREE.BoxGeometry(4.3, 0.1, 1.2), '#f4efe8', [0, 1.05, -3.2]);
        [-1.2, 0, 1.2].forEach((x, i) => { P(g, new THREE.CylinderGeometry(0.4, 0.4, 0.06, 16), '#3a3a46', [x * 0.6 - 0.8, 1.14, -3.2], { out: 1.04 }); });
        const pot = P(g, new THREE.CylinderGeometry(0.4, 0.34, 0.5, 16), '#9aa0ae', [-0.8, 1.45, -3.2], { out: 1.05 });
        const steam = glowSprite('#ffffff', 1.4, 0.4); steam.position.set(-0.8, 2.1, -3.2); g.add(steam); steams.push(steam);
        for (let i = 0; i < 4; i++) P(g, new THREE.CylinderGeometry(0.24, 0.2, 0.06, 14), '#8a8f9a', [-2.8 + i * 0.5, 3.0, -3.7], { rot: [Math.PI / 2, 0, 0], out: 1.04 });
        // kontainer (biru, bergaris) sebagai peti deploy
        [[2.6, 0.4, 0.8, 0], [2.6, 1.15, 0.8, 0.2], [2.9, 0.4, 2.2, 0]].forEach(([x, y, z, r]) => P(g, new THREE.BoxGeometry(1.6, 0.7, 0.9), '#4a9ad8', [x, y, z], { rot: [0, r, 0], out: 1.03, mat: toon('#ffffff', { map: (() => { const t = texStripe('#4a9ad8', '#5aaae8', 6); return t; })() }) }));
        P(g, new THREE.BoxGeometry(1.7, 1.0, 0.04), '#2b3a3a', [-2.8, 2.0, -3.82]); // papan menu
        P(g, new THREE.BoxGeometry(1.6, 0.9, 0.02), '#2b3a3a', [-2.8, 2.0, -3.78], { mat: new THREE.MeshBasicMaterial({ color: 0x2f4a3f }), cast: false });
        deskAt(g, 0, 0.6, '#d9c08a', 2.0, 1.0); chair(g, 0, 1.9, a); plant(g, -3.1, 2.8, 1.0); break; }
      case 'grd': {
        const sand = P(g, new THREE.BoxGeometry(5.6, 0.06, 4.2), '#f1e0b4', [-0.3, 0.1, 0.4], { cast: false });
        for (let i = 0; i < 8; i++) P(g, new THREE.BoxGeometry(5.2, 0.015, 0.05), '#d9c590', [-0.3, 0.14, -1.4 + i * 0.5], { cast: false });
        [-1, 1].forEach((s) => P(g, new THREE.CylinderGeometry(0.2, 0.2, 3.0, 10), '#c4412f', [s * 1.7, 1.5, -2.6], { out: 1.03 }));
        P(g, new THREE.BoxGeometry(4.6, 0.3, 0.45), '#c4412f', [0, 3.0, -2.6], { out: 1.03 }); P(g, new THREE.BoxGeometry(5.0, 0.2, 0.55), '#2b2238', [0, 3.3, -2.6]); P(g, new THREE.BoxGeometry(4.2, 0.14, 0.3), '#c4412f', [0, 2.55, -2.6]);
        [[-0.9, 0.6], [1.3, -0.6]].forEach(([x, z]) => P(g, new THREE.DodecahedronGeometry(0.4, 0), '#a7a7b2', [x, 0.3, z], { out: 1.05 }));
        P(g, new THREE.CylinderGeometry(0.9, 0.9, 0.1, 6), '#6a8aaa', [-2.8, 1.6, -3.7], { rot: [Math.PI / 2, 0, 0], out: 1.04 }); P(g, new THREE.CylinderGeometry(0.7, 0.7, 0.12, 6), '#c4412f', [-2.8, 1.6, -3.66], { rot: [Math.PI / 2, 0, 0] });
        const ln = P(g, new THREE.SphereGeometry(0.3, 12, 10), '#ff9a6a', [2.8, 1.3, -1.0], { mat: glow('#ffb48a', 1) }); lanterns.push(ln); P(g, new THREE.CylinderGeometry(0.05, 0.05, 1.3, 6), '#4a3a2a', [2.8, 0.65, -1.0]);
        const glw = glowSprite('#ffb48a', 2.2, 0.5); glw.position.set(2.8, 1.3, -1.0); g.add(glw); break; }
      case 'villa': case 'rtrw': case 'contoh': {
        const ghost = r.ghost, tint = ghost ? '#d4d4de' : null;
        const gm = (c) => (ghost ? { mat: toon('#d9d9e4', { transparent: true, opacity: 0.8 }) } : {});
        // maket bangunan
        const base = P(g, new THREE.BoxGeometry(3.4, 0.15, 2.6), '#a9d6a0', [0, 0.12, -0.4], { out: 1.0, ...(ghost ? { mat: toon('#e2e2ea') } : {}) });
        if (r.id === 'villa') {
          P(g, new THREE.BoxGeometry(1.8, 0.9, 1.2), '#fbf4e8', [-0.4, 0.65, -0.5], { out: 1.03 }); P(g, new THREE.ConeGeometry(1.4, 0.8, 4), '#d9693f', [-0.4, 1.5, -0.5], { rot: [0, Math.PI / 4, 0], out: 1.03 });
          P(g, new THREE.BoxGeometry(1.2, 0.04, 0.8), '#6ac8e8', [1.0, 0.22, 0.4], { mat: glow('#6ac8e8', 0.95), cast: false });
        } else if (r.id === 'rtrw') {
          P(g, new THREE.BoxGeometry(2.2, 0.8, 1.2), '#f6e6c0', [0, 0.6, -0.5], { out: 1.03 }); P(g, new THREE.BoxGeometry(2.5, 0.1, 1.5), '#c78a2f', [0, 1.05, -0.5], { out: 1.03 }); P(g, new THREE.ConeGeometry(1.5, 0.7, 4), '#c78a2f', [0, 1.45, -0.5], { rot: [0, Math.PI / 4, 0], out: 1.03 });
          P(g, new THREE.CylinderGeometry(0.03, 0.03, 1.4, 6), '#8a8a8a', [1.4, 0.8, 0.3]); P(g, new THREE.BoxGeometry(0.5, 0.3, 0.02), '#e8483f', [1.65, 1.35, 0.3]);
        } else { P(g, new THREE.BoxGeometry(1.6, 0.9, 1.1), '#e2e2ea', [0, 0.65, -0.5], { mat: toon('#e6e6ee', { transparent: true, opacity: 0.6 }) }); }
        // papan 16 tahap (diisi dari data nyata, lihat setProjects)
        const t = board16(g, 0, 2.5, -3.8, []); boards[r.id] = t;
        t.forEach((m) => { if (ghost) m.material.color.set(LEVEL.ghost); });
        shelf(g, -3.1, -1.0, 1.8, 2.2, Math.PI / 2, 10); shelf(g, 3.1, -1.0, 1.8, 1.6, -Math.PI / 2, 8);
        // layar hasil tinjauan
        P(g, new THREE.BoxGeometry(1.6, 1.0, 0.08), '#3a3550', [2.4, 1.9, -3.8], { out: 1.0 }); P(g, new THREE.BoxGeometry(1.5, 0.9, 0.02), ghost ? '#b9b9c9' : '#9ad7ff', [2.4, 1.9, -3.74], { mat: glow(ghost ? '#b9b9c9' : '#9ad7ff', 0.85), cast: false });
        plant(g, 3.0, 2.8, 1.0); rug(g, 0, 2.0, 3.8, 2.2, ghost ? '#e6e6ee' : r.floor, a);
        if (ghost) { const q = sprite(texLabel('? CONTOH', { w: 400, h: 120, bg: 'rgba(120,120,150,.85)' }), 2.8, 0.84, { depthTest: false }); q.position.set(0, 3.0, 1); g.add(q); }
        break; }
      case 'lib': {
        shelf(g, -2.2, -3.5, 3.4, 3.2, 0, 24); shelf(g, 2.0, -3.5, 3.4, 3.2, 0, 24); shelf(g, -3.4, -0.5, 3.2, 3.0, Math.PI / 2, 22);
        deskAt(g, 0.6, 0.6, '#b88556', 2.6, 1.3); chair(g, 0.6, 1.9 - 0.2, '#c26a4a'); lamp(g, 1.6, 0.6, '#ffe3a8'); P(g, new THREE.BoxGeometry(0.6, 0.08, 0.8), '#fff4dc', [0.0, 1.05, 0.6], { rot: [0, 0.15, 0] });
        const lad = P(g, new THREE.BoxGeometry(0.1, 3.0, 0.1), '#a67a4a', [-0.4, 1.5, -3.1], { rot: [0.12, 0, 0] }); for (let i = 0; i < 6; i++) P(g, new THREE.BoxGeometry(0.7, 0.06, 0.06), '#a67a4a', [-0.4, 0.4 + i * 0.5, -3.0 + i * -0.02]);
        rug(g, 0.6, 1.0, 4.0, 2.6, '#efd9c0', a); plant(g, 3.1, 2.8, 1.1); break; }
      case 'lounge': {
        // kafe: meja bar + barista
        P(g, new THREE.BoxGeometry(3.6, 1.1, 0.9), '#c26a4a', [-1.2, 0.55, -2.6], { out: 1.03 }); P(g, new THREE.BoxGeometry(3.8, 0.12, 1.0), '#f4efe8', [-1.2, 1.15, -2.6]);
        P(g, new THREE.BoxGeometry(0.8, 0.7, 0.6), '#8a8f9a', [-2.2, 1.55, -2.6], { out: 1.03 }); steams.push((() => { const s = glowSprite('#ffffff', 1.0, 0.35); s.position.set(-2.2, 2.1, -2.6); g.add(s); return s; })());
        [-2.4, -1.4, -0.4].forEach((x) => { P(g, new THREE.CylinderGeometry(0.28, 0.28, 0.1, 14), '#f4a6a0', [x, 0.7, -1.4], { out: 1.04 }); P(g, new THREE.CylinderGeometry(0.06, 0.06, 0.7, 8), '#8a8f9a', [x, 0.35, -1.4]); });
        // arcade
        P(g, new THREE.BoxGeometry(1.2, 2.4, 1.0), '#3a3a7a', [2.8, 1.2, -2.6], { out: 1.03 }); P(g, new THREE.BoxGeometry(0.9, 0.7, 0.04), '#9affd0', [2.8, 1.8, -2.08], { mat: glow('#9affd0', 1), cast: false }); P(g, new THREE.CylinderGeometry(0.07, 0.07, 0.3, 8), '#e8483f', [2.65, 1.2, -2.0]);
        const ag = glowSprite('#7affc8', 3, 0.5); ag.position.set(2.8, 1.8, -1.9); g.add(ag);
        // beanbag
        [['#f2c14e', 2.2, 1.6], ['#8fcf8a', 0.9, 2.6], ['#b58ae0', -2.4, 2.2]].forEach(([c, x, z]) => { const bb = P(g, new THREE.SphereGeometry(0.75, 14, 12), c, [x, 0.4, z], { out: 1.05 }); bb.scale.set(1, 0.6, 1); });
        P(g, new THREE.CylinderGeometry(0.7, 0.7, 0.8, 16), '#f4efe8', [-0.4, 0.4, 1.2], { out: 1.03 });
        lamp(g, -3.2, -3.2, '#ffb8a0'); plant(g, 3.2, 3.0, 1.1); break; }
    }
  }

  // objek yang beranimasi (dekoratif)

  // ---------------- paket biophilic koridor (Google/Airbnb vibe)
  { const g = new THREE.Group(); scene.add(g);
    phoneBooth(g, -16, -9, 0); phoneBooth(g, 16, -9, Math.PI); phoneBooth(g, -16, 1, 0); phoneBooth(g, 16, 1, Math.PI);
    bigTree(g, -20, 11.6, 1.15); bigTree(g, -13, 12.6, 1.05); bigTree(g, -2.5, 12.2, 1.0); bigTree(g, 3, 11.4, 1.2); bigTree(g, 14.5, 12.8, 1.1); bigTree(g, 20, 11.6, 1.0);
    pendantLamp(g, -8, -9); pendantLamp(g, 0, -9, 3.1); pendantLamp(g, 8, -9); pendantLamp(g, -8, 1); pendantLamp(g, 8, 1);
    [[-24, -9, 0], [24, -9, 0], [-24, 1, 0], [24, 1, 0]].forEach(([x, z]) => { const la = lamp(g, x, z); la.position.y = 0; });
  }

  // ---------------- garis tengah: plaza, taman, air mancur
  { const g = new THREE.Group(); scene.add(g);
    // taman depan
    const garden = P(g, new THREE.BoxGeometry(46, 0.2, 7.5), '#b6dc9e', [0, -0.1, 14.3], { cast: false, mat: toon('#ffffff', { map: (() => { const t = texGrass(); t.repeat.set(8, 2); return t; })() }) });
    const pond = P(g, new THREE.CylinderGeometry(2.4, 2.4, 0.3, 28), '#bfe6f6', [-8, 0.1, 14.5], { mat: glow('#9ad7f6', 0.9), cast: false });
    P(g, new THREE.TorusGeometry(2.45, 0.2, 8, 30), '#d6c6b0', [-8, 0.2, 14.5], { rot: [Math.PI / 2, 0, 0], out: 1.04 });
    P(g, new THREE.CylinderGeometry(0.3, 0.45, 1.1, 12), '#d6c6b0', [-8, 0.7, 14.5], { out: 1.04 }); const fn = glowSprite('#cfeeff', 2.6, 0.55); fn.position.set(-8, 1.5, 14.5); g.add(fn); steams.push(fn);
    for (let i = 0; i < 9; i++) { const tx = -20 + i * 5 + (i % 2) * 1.2, tz = 15 + (i % 3) * 0.9;
      P(g, new THREE.CylinderGeometry(0.22, 0.3, 1.4, 10), '#a9794a', [tx, 0.7, tz], { out: 1.04 });
      const cr = P(g, new THREE.SphereGeometry(1.0 + (i % 3) * 0.2, 14, 12), ['#7fcf8a', '#a8dc7f', '#f4b6c8'][i % 3], [tx, 2.1, tz], { out: 1.04 }); cr.userData.sway = i; swayers.push(cr); }
    for (let i = 0; i < 36; i++) { const fx = -21 + Math.random() * 42, fz = 11.4 + Math.random() * 6; P(g, new THREE.SphereGeometry(0.1, 6, 6), ['#f4b6c8', '#f2c14e', '#ffffff', '#b58ae0'][i % 4], [fx, 0.2, fz]); }
    P(g, new THREE.BoxGeometry(2.4, 0.15, 0.7), '#c89a68', [6, 0.7, 14.2], { out: 1.03 }); P(g, new THREE.BoxGeometry(2.4, 0.6, 0.1), '#c89a68', [6, 1.1, 13.9]);
    [-1, 1].forEach((s) => P(g, new THREE.BoxGeometry(0.12, 0.65, 0.5), '#a67a4a', [6 + s * 1.1, 0.35, 14.2]));
    commTable(g, 8, 12.6, 0); pendantLamp(g, 8, 12.6, 3.0);
    bigTree(g, -16, 12.6, 1.2); bigTree(g, 0, 12.9, 1.15); bigTree(g, 18, 12.2, 1.1);
    // jalur lampion sepanjang taman
    for (let i = 0; i < 7; i++) { const lx = -18 + i * 6; P(g, new THREE.CylinderGeometry(0.05, 0.05, 1.4, 6), '#6a5a4a', [lx, 0.7, 11.4]); const lb = P(g, new THREE.SphereGeometry(0.2, 10, 8), '#ffe3a8', [lx, 1.5, 11.4], { mat: glow('#ffe3a8', 1) }); const gs = glowSprite('#ffe3a8', 1.8, 0.45); gs.position.set(lx, 1.5, 11.4); g.add(gs); }
  }

  { const hg = new THREE.Group(); scene.add(hg); // celah kaca: intip ke basement dari lantai utama
    P(hg, new THREE.BoxGeometry(5.4, 0.1, 1.5), '#2b2248', [0, 0.1, 10.7], { out: 1.0 });
    P(hg, new THREE.BoxGeometry(5.0, 0.05, 1.1), '#9a86ff', [0, 0.17, 10.7], { mat: glow('#9a86ff', 0.95), cast: false });
    for (let i = -2; i <= 2; i++) P(hg, new THREE.BoxGeometry(0.07, 0.08, 1.2), '#d4b24a', [i * 1, 0.2, 10.7], { cast: false });
    const gl = glowSprite('#9a86ff', 6, 0.55); gl.position.set(0, 0.6, 10.7); hg.add(gl); steams.push(gl);
    const tl = sprite(texLabel('↓ Ruang Koordinasi', { w: 420, h: 96, bg: 'rgba(60,40,110,.85)' }), 2.6, 0.6, { depthTest: false }); tl.position.set(0, 1.6, 10.7); tl.renderOrder = 9; hg.add(tl); }

  // ---------------- basement (Ruang Koordinasi)
  const den = new THREE.Group(); den.position.set(0, -5.2, -4); scene.add(den);
  let denLabel = null;
  const denLight = new THREE.PointLight(0xb9a0ff, 0.8, 24, 1.6); denLight.position.set(0, 2, 0); den.add(denLight);
  { const dm = toon('#4a3a72');
    const f = P(den, new THREE.BoxGeometry(18, 0.3, 13), '#3a2f5c', [0, 0, 0], { cast: false });
    [[0, 1.5, -6.5, 18, 3.2, 0.3], [-9, 1.5, 0, 0.3, 3.2, 13]].forEach(([x, y, z, w, h, d]) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), dm); m.position.set(x, y, z); m.receiveShadow = true; den.add(m); });
    P(den, new THREE.BoxGeometry(6, 0.14, 3), '#5a4a8a', [0, 1.0, -1], { out: 1.0 }); [-2.6, 2.6].forEach((x) => P(den, new THREE.BoxGeometry(0.2, 0.9, 0.2), '#2b2248', [x, 0.5, -1]));
    // tabel 16 tahap menyala
    for (let i = 0; i < 16; i++) { const t = P(den, new THREE.BoxGeometry(0.55, 0.05, 0.55), '#7a6ad0', [-2.4 + (i % 8) * 0.68, 1.1, -1.4 + Math.floor(i / 8) * 0.8], { mat: glow('#9a86ff', 0.85 + (i % 3) * 0.1), cast: false }); denTiles.push(t); }
    for (let i = 0; i < 6; i++) P(den, new THREE.CylinderGeometry(0.12, 0.12, 2.8, 8), '#2b2248', [-8 + i * 1.5, 1.5, -6.2], { out: 1.0 });
    [-6, 6].forEach((x) => { const cr = glowSprite('#9a86ff', 3.2, 0.5); cr.position.set(x, 2.2, -5); den.add(cr); });
    shelf(den, -7.9, 2.5, 3, 2.6, Math.PI / 2, 12);
    const lab = sprite(texLabel('Ruang Koordinasi', { w: 640, h: 128, accent: '#9a86ff', sub: 'basement · Kapten Orka' }), 5.4, 1.08, { depthTest: false }); lab.position.set(0, 4.3, -3); lab.renderOrder = 10; den.add(lab); denLabel = lab;
    const dz = new THREE.Mesh(new THREE.BoxGeometry(18, 3.6, 13), new THREE.MeshBasicMaterial({ visible: false })); dz.position.set(0, 1.6, 0); dz.userData.room = 'den'; den.add(dz); pickables.push(dz);
  }

  // ---------------- karakter
  const actors = [];
  const labelDot = (ok) => (ok === true ? '#47d17a' : ok === false ? '#e8786a' : '#9a9ab0');
  function nameplate(spec, ok) {
    return texLabel(spec.name, { w: 512, h: 128, sub: spec.title.split('·')[0].trim(), accent: spec.profile ? labelDot(ok) : '#f2c14e' });
  }
  function makeActor(spec, i) {
    const g = buildCharacter(spec, 11 + i * 17); scene.add(g);
    const lab = sprite(nameplate(spec, null), 3.5, 0.88, { depthTest: false }); lab.position.set(0, 3.55, 0); lab.renderOrder = 12; g.add(lab);
    const ring = mesh(new THREE.RingGeometry(0.8, 1.0, 32), '#ffe3a8', { mat: new THREE.MeshBasicMaterial({ color: 0xffe3a8, transparent: true, opacity: 0, side: THREE.DoubleSide }), cast: false, parent: g }); ring.rotation.x = -Math.PI / 2; ring.position.y = 0.06;
    const a = { spec, g, lab, ring, mode: 'idle', path: [], act: null, timer: 4 + Math.random() * 6, t0: Math.random() * 10, home: roomById[spec.home], loc: spec.home, yaw: 0, y: 0 };
    g.userData.actor = a; g.traverse((o) => { if (o.isMesh) { o.userData.actor = a; } });
    actors.push(a); return a;
  }
  CAST.forEach((c, i) => makeActor(c, i));
  const barista = makeActor({ ...BARISTA, home: 'lounge', profile: null }, 99);
  barista.g.position.set(roomById.lounge.cx - 1.6, 0, roomById.lounge.cz - 3.2); barista.g.rotation.y = 0; barista.fixed = true; barista.mode = 'work'; barista.lab.material.map = texLabel('Mimi', { w: 512, h: 128, sub: 'barista · dekoratif', accent: '#b9b9c9' });
  const A = Object.fromEntries(actors.map((a) => [a.spec.id, a]));

  // posisi awal
  function placeAtSeat(a) {
    const r = a.home;
    if (a.spec.id === 'orch') { a.g.position.set(0, -4.95, -4 + 2.6); a.g.rotation.y = Math.PI; a.mode = 'work'; a.fixed = true; return; }
    const p = seatOf(r);
    a.g.position.set(p.x, 0, p.z); a.g.rotation.y = 0; a.yaw = 0; a.mode = 'work'; a.loc = r.id; a.at = 'seat';
  }
  actors.forEach((a) => { if (!a.fixed) placeAtSeat(a); });
  placeAtSeat(A.orch); A.orch.g.rotation.y = 0; A.orch.g.position.set(0, -5.05, -2.5); A.orch.denMode = 0;

  // ---------------- rute (graf koridor + lorong)
  function levelOf(room) { return room.level; } // 0: koridor C1 (z=-9), 1: koridor C2 (z=1), 2: taman (z=11.8)
  function spotRoute(fromX, fromZ, fromLevel, toX, toZ, toLevel) {
    const pts = []; let x = fromX, lv = fromLevel;
    const aisle = (x1, x2) => AISLES.reduce((b, a) => (Math.abs(x1 - a) + Math.abs(a - x2) < Math.abs(x1 - b) + Math.abs(b - x2) ? a : b), AISLES[0]);
    while (lv !== toLevel) {
      const next = lv + Math.sign(toLevel - lv);
      const ax = aisle(x, toX);
      pts.push([ax, CORR[lv]]); pts.push([ax, CORR[next]]); x = ax; lv = next;
    }
    pts.push([toX, CORR[toLevel]]);
    return pts;
  }
  function routeBetween(from, to) { // from/to: {room?, x,z, level, inside?}
    const pts = [];
    if (from.roomIn) pts.push([from.roomIn.x, from.roomIn.z]);
    pts.push(...spotRoute(from.x, from.z, from.level, to.x, to.z, to.level).map((p, i, arr) => p));
    // pastikan segmen pertama dari koridor asal
    return pts;
  }
  const SPOTS = {
    cafe: { roomId: 'lounge', pos: [roomById.lounge.cx - 1.2, roomById.lounge.cz - 1.2], face: Math.PI, act: 'rest' },
    arcade: { roomId: 'lounge', pos: [roomById.lounge.cx + 2.6, roomById.lounge.cz - 1.4], face: 0, act: 'pose' },
    beanbag: { roomId: 'lounge', pos: [roomById.lounge.cx + 2.2, roomById.lounge.cz + 1.4], face: 0.3, act: 'rest' },
    library: { roomId: 'lib', pos: [roomById.lib.cx - 1.0, roomById.lib.cz - 1.8], face: 0, act: 'read' },
    garden: { level: 2, pos: [-8 + 3.2, 13.3], face: 0.4, act: 'idle' },
    bench: { level: 2, pos: [6, 13.2], face: 0, act: 'rest' },
    villa: { roomId: 'villa', pos: [roomById.villa.cx, roomById.villa.cz + 0.6], face: 0, act: 'read' },
    rtrw: { roomId: 'rtrw', pos: [roomById.rtrw.cx, roomById.rtrw.cz + 0.6], face: 0, act: 'read' },
  };
  function buildPath(a, spot) {
    // titik awal = lokasi sekarang; tentukan level & pintu
    const cur = a.g.position, curRoom = a.loc && roomById[a.loc], pts = [];
    let level, x;
    if (curRoom) { const d = doorIn(curRoom); pts.push([d.x, d.z]); level = curRoom.row === 0 ? 0 : 1; pts.push([curRoom.cx, CORR[level]]); x = curRoom.cx; }
    else { level = a.level ?? 2; x = cur.x; pts.push([cur.x, CORR[level]]); }
    const tr = spot.roomId ? roomById[spot.roomId] : null;
    const toLevel = tr ? (tr.row === 0 ? 0 : 1) : spot.level;
    const sr = spotRoute(x, CORR[level], level, tr ? tr.cx : spot.pos[0], 0, toLevel); pts.push(...sr);
    if (tr) { const d = doorIn(tr); pts.push([d.x, d.z]); }
    pts.push(spot.pos);
    a.level = toLevel; return pts.map((p) => new THREE.Vector3(p[0], 0, p[1]));
  }
  function sendTo(a, spotKey, face, act) {
    const spot = SPOTS[spotKey] || spotKey;
    a.path = buildPath(a, spot); a.dest = { face: spot.face ?? face, act: spot.act ?? act, room: spot.roomId || null };
    a.mode = 'walk'; a.at = null;
  }
  function sendHome(a) {
    const r = a.home, s = seatOf(r);
    const pts = buildPath(a, { roomId: r.id, pos: [s.x, s.z], face: 0, act: 'work' });
    a.path = pts; a.dest = { face: 0, act: 'work', room: r.id, home: true }; a.mode = 'walk';
  }
  const ACTIVITIES = ['cafe', 'library', 'garden', 'arcade', 'beanbag', 'bench', 'villa', 'rtrw'];

  // ---------------- interaksi
  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
  let selected = null; const listeners = {};
  const emit = (ev, d) => (listeners[ev] || []).forEach((f) => f(d));
  host.addEventListener('pointerdown', (e) => { downAt = [e.clientX, e.clientY, performance.now()]; });
  let downAt = null;
  host.addEventListener('pointerup', (e) => {
    if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 6 || e.button !== 0) return;
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    ray.setFromCamera(mouse, cam);
    const hits = ray.intersectObjects(actors.map((a) => a.g).concat(pickables), true);
    for (const h of hits) {
      let o = h.object; while (o && !o.userData.actor && !o.userData.room) o = o.parent;
      if (!o) continue;
      if (o.userData.actor) return select('actor', o.userData.actor.spec.id);
      if (o.userData.room) return select('room', o.userData.room);
    }
  });
  function select(kind, id) {
    selected = { kind, id };
    actors.forEach((a) => (a.ring.material.opacity = 0));
    let tgt = null;
    if (kind === 'actor') { const a = A[id]; a.ring.material.opacity = 0.9; tgt = a.g.position.clone(); if (a.spec.home === 'den') setDen(true); else setDen(false); }
    else if (kind === 'room') { if (id === 'den') { setDen(true); tgt = new THREE.Vector3(0, -3, -4); } else { setDen(false); const r = roomById[id]; tgt = new THREE.Vector3(r.cx, 1, r.cz); } }
    if (tgt) flyTo(tgt);
    emit('select', selected);
  }
  let fly = null;
  function flyTo(t) { fly = { from: controls.target.clone(), to: t.clone(), off: ortho.position.clone().sub(controls.target), t: 0 }; }
  function applyFly(k) { controls.target.lerpVectors(fly.from, fly.to, k); ortho.position.copy(controls.target).add(fly.off); }
  let denOn = false;
  function setDen(on) { denOn = on; emit('den', on); }

  // ---------------- state dari server
  function setState(state) {
    const byProf = Object.fromEntries((state.profiles || []).map((p) => [p.id, p]));
    actors.forEach((a) => { const p = a.spec.profile && byProf[a.spec.profile]; a.health = p || null;
      if (a.spec.profile) a.lab.material.map = nameplate(a.spec, p ? p.health === 'ok' : null); a.lab.material.needsUpdate = true; });
  }
  function setProjects(list) {
    list.forEach((p) => {
      const rid = Object.keys(boards).find((k) => roomById[k].project === p.id); if (!rid) return;
      boards[rid].forEach((m, i) => { const st = p.stages[i]; m.material.color.set(st ? LEVEL[st.state] : LEVEL.todo); });
    });
    projectsData = list;
  }

  // ---------------- masuk ke dalam (orang pertama)
  let inside = false, yaw = Math.PI * 0.25, pitch = 0, keys = {}, joy = { x: 0, y: 0 }, fp = new THREE.Vector3(0, 1.9, 12);
  addEventListener('keydown', (e) => { keys[e.code] = true; }); addEventListener('keyup', (e) => { keys[e.code] = false; });
  let drag = null;
  host.addEventListener('pointerdown', (e) => { if (inside) drag = [e.clientX, e.clientY]; });
  addEventListener('pointerup', () => (drag = null));
  addEventListener('pointermove', (e) => { if (inside && drag) { yaw -= (e.clientX - drag[0]) * 0.006; pitch = Math.max(-0.9, Math.min(0.7, pitch - (e.clientY - drag[1]) * 0.004)); drag = [e.clientX, e.clientY]; } });
  function setInside(on) { inside = on; cam = on ? persp : ortho; controls.enabled = !on; emit('inside', on); }

  // ---------------- debu halus (dekoratif)
  const pn = 90, pgeo = new THREE.BufferGeometry(), ppos = new Float32Array(pn * 3);
  for (let i = 0; i < pn; i++) { ppos[i * 3] = (Math.random() - 0.5) * 50; ppos[i * 3 + 1] = Math.random() * 9; ppos[i * 3 + 2] = (Math.random() - 0.5) * 36 - 3; }
  pgeo.setAttribute('position', new THREE.BufferAttribute(ppos, 3));
  const motes = new THREE.Points(pgeo, new THREE.PointsMaterial({ color: 0xffe9b8, size: 0.22, transparent: true, opacity: 0.55, depthWrite: false })); scene.add(motes);

  // ---------------- loop
  const clock = new THREE.Clock(); let T = 0, ready = false, frames = 0;
  function tick() {
    requestAnimationFrame(tick);
    const dt = Math.min(clock.getDelta(), 0.1); T += dt; frames++;
    if (frames % 10 === 0) { const d = document.documentElement.dataset; d.frames = frames; d.fade = fadeOp.toFixed(2); d.den = denOn ? 1 : 0; d.cam = ortho.position.y.toFixed(1); }
    actors.forEach((a) => stepActor(a, dt));
    spinners.forEach((s) => (s.rotation.y += s.userData.spin * dt)); rockers.forEach((r) => (r.rotation.z = Math.sin(T * 0.8) * 0.06));
    steams.forEach((s, i) => { s.position.y += Math.sin(T * 1.3 + i) * 0.0015; s.material.opacity = 0.25 + (Math.sin(T * 1.7 + i) + 1) * 0.12; });
    lanterns.forEach((l, i) => (l.scale.setScalar(1 + Math.sin(T * 3 + i) * 0.04)));
    swayers.forEach((s) => (s.rotation.z = Math.sin(T * 0.9 + s.userData.sway) * 0.03));
    denTiles.forEach((t, i) => (t.material.color.setScalar(0.65 + 0.35 * Math.max(0, Math.sin(T * 1.6 + i * 0.5)))));
    const pa = pgeo.attributes.position; for (let i = 0; i < pn; i++) { pa.array[i * 3 + 1] += dt * 0.25; pa.array[i * 3] += Math.sin(T + i) * dt * 0.1; if (pa.array[i * 3 + 1] > 9) pa.array[i * 3 + 1] = 0; } pa.needsUpdate = true;
    // fade lantai untuk basement
    lawn.material.opacity = 0.05 + 0.95 * fadeOp; lawn.visible = fadeOp > 0.2;
    const targetOp = denOn ? 0.14 : 1; fadeOp += (targetOp - fadeOp) * Math.min(1, dt * 5); applyFade();
    if (denLabel) denLabel.visible = denOn; if (A.orch) A.orch.lab.visible = denOn;
    denLight.intensity += ((denOn ? 3.2 : 0.8) - denLight.intensity) * Math.min(1, dt * 4);
    if (inside) walk(dt); else {
      if (fly) { fly.t = Math.min(1, fly.t + dt * 2.2); applyFly(1 - Math.pow(1 - fly.t, 3)); if (fly.t >= 1) fly = null; }
      controls.update();
    }
    renderer.render(scene, cam);
    if (!ready) { ready = true; setTimeout(() => emit('ready', true), 0); }
  }
  let fadeOp = 1;
  function applyFade() {
    lawn.material.opacity = 0.05 + 0.95 * fadeOp; lawn.visible = fadeOp > 0.2;
    groundG.traverse((o) => { if (o.material && o.material.opacity !== undefined && !o.material.isMeshBasicMaterial) { { const tr = fadeOp < 0.99; if (o.material.transparent !== tr) { o.material.transparent = tr; o.material.needsUpdate = true; } o.material.opacity = fadeOp; o.material.depthWrite = fadeOp > 0.9; } } });
  }
  function stepActor(a, dt) {
    const t = T + a.t0;
    if (a.spec.id === 'orch') { // Kapten tinggal di basement (dekoratif)
      a.timer -= dt; if (a.timer <= 0) { a.denMode = (a.denMode + 1) % 4; a.timer = 6 + Math.random() * 6; }
      a.mode = ['work', 'read', 'pose', 'idle'][a.denMode];
      a.g.position.x = Math.sin(t * 0.25) * (a.denMode === 3 ? 1.6 : 0); a.g.rotation.y = a.denMode === 3 ? Math.sin(t * 0.25 + 1.6) * 0.5 : 0;
      animate(a.g, { mode: a.mode }, t, dt); return;
    }
    if (a.fixed) { animate(a.g, { mode: a.mode }, t, dt); return; }
    if (a.mode === 'walk' && a.path.length) {
      const tgt = a.path[0], pos = a.g.position, d = tgt.clone().sub(pos); d.y = 0; const dist = d.length();
      if (dist < 0.12) { a.path.shift(); if (!a.path.length) { // tiba
        a.mode = a.dest.act; a.g.rotation.y = a.dest.face; a.loc = a.dest.room || a.loc; if (!a.dest.room) a.loc = null; a.timer = 9 + Math.random() * 10; if (a.dest.home) a.timer = 16 + Math.random() * 14; } }
      else { d.normalize(); pos.addScaledVector(d, 3.4 * dt); let ty = Math.atan2(d.x, d.z); let dy = ty - a.g.rotation.y; dy = Math.atan2(Math.sin(dy), Math.cos(dy)); a.g.rotation.y += dy * Math.min(1, dt * 9); }
    } else {
      a.timer -= dt;
      if (a.timer <= 0) {
        if (a.dest && a.dest.home) { const k = ACTIVITIES[(Math.random() * ACTIVITIES.length) | 0]; sendTo(a, k); a.dest.home = false; }
        else sendHome(a);
      }
    }
    animate(a.g, { mode: a.mode }, t, dt);
  }
  function walk(dt) {
    const sp = 6 * dt; let fx = 0, fz = 0;
    if (keys.KeyW || keys.ArrowUp) fz += 1; if (keys.KeyS || keys.ArrowDown) fz -= 1; if (keys.KeyA || keys.ArrowLeft) fx -= 1; if (keys.KeyD || keys.ArrowRight) fx += 1;
    fx += joy.x; fz += joy.y;
    const dx = Math.sin(yaw), dz = Math.cos(yaw);
    fp.x += (-dx * fz + dz * fx * 1) * sp * -1 * -1 * -1; fp.z += (-dz * fz - dx * fx) * sp * -1 * -1 * -1;
    fp.x = Math.max(-22, Math.min(22, fp.x)); fp.z = Math.max(-18, Math.min(17, fp.z));
    persp.position.copy(fp); persp.rotation.order = 'YXZ'; persp.rotation.set(pitch, yaw, 0);
  }
  tick();

  return {
    scene, renderer, actors, A, ROOMS, roomById, SPOTS, groundG, den, lawn,
    on: (ev, f) => (listeners[ev] = (listeners[ev] || []).concat(f)),
    select, setState, setProjects, setDen: (on) => { setDen(on); if (on) flyTo(new THREE.Vector3(0, -3, -4)); },
    toggleDen: () => { setDen(!denOn); if (denOn) flyTo(new THREE.Vector3(0, -3, -4)); return denOn; },
    setInside: (on) => { if (on) { fp.set(0, 1.9, 12.5); yaw = Math.PI; pitch = 0; } setInside(on); },
    setJoy: (x, y) => { joy.x = x; joy.y = y; },
    snap: () => { if (fly) { applyFly(1); fly = null; } fadeOp = denOn ? 0.14 : 1; applyFade(); if (denLabel) denLabel.visible = denOn; if (A.orch) A.orch.lab.visible = denOn; denLight.intensity = denOn ? 3.2 : 0.8; controls.update(); },
    setPanelShift: (px) => { shiftPx = px; applyFrame(); },
    focusOn: (x, y, z, zoom) => { const off = ortho.position.clone().sub(controls.target); controls.target.set(x, y, z); ortho.position.set(x, y, z).add(off); ortho.zoom = zoom; ortho.updateProjectionMatrix(); controls.update(); },
    reset: () => { setDen(false); setInside(false); ortho.zoom = innerWidth < 800 && innerHeight > innerWidth ? 0.78 : 1.16; ortho.position.set(30, 37, 30); controls.target.set(0, 0, -2); ortho.updateProjectionMatrix(); controls.update(); selected = null; actors.forEach((a) => (a.ring.material.opacity = 0)); },
    get selected() { return selected; }, get inside() { return inside; }, get denOn() { return denOn; },
    get projects() { return projectsData; },
    fitProbe: () => { const b = new THREE.Box3(); Object.values(roomGroups).forEach((g) => b.expandByObject(g)); const v = new THREE.Vector3(); const c = [{x:b.min.x,y:0,z:b.min.z},{x:b.max.x,y:0,z:b.min.z},{x:b.min.x,y:0,z:b.max.z},{x:b.max.x,y:0,z:b.max.z},{x:b.min.x,y:4,z:b.min.z},{x:b.max.x,y:4,z:b.min.z},{x:b.min.x,y:4,z:b.max.z},{x:b.max.x,y:4,z:b.max.z}]; let mnx=1e9,mxx=-1e9,mny=1e9,mxy=-1e9; c.forEach(p => { v.set(p.x,p.y,p.z).project(ortho); mnx=Math.min(mnx,v.x); mxx=Math.max(mxx,v.x); mny=Math.min(mny,v.y); mxy=Math.max(mxy,v.y); }); return { ndc:[mnx.toFixed(2),mxx.toFixed(2),mny.toFixed(2),mxy.toFixed(2)], zoom:ortho.zoom, port:innerWidth<800 }; },
    stats: () => { let m = 0; scene.traverse((o) => { if (o.isMesh) m++; }); return { meshes: m, actors: actors.length, rooms: ROOMS.length }; },
  };
}
