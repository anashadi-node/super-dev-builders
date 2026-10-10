// 11 karakter anime-chibi unik (Owner + 10 agent) + barista. Tiap karakter = desain tersendiri:
// rambut, topi/ikat kepala, pakaian, aksesori, properti. Terinspirasi ARKETIPE (bukan salinan karakter berhak cipta).
import * as THREE from 'three';
import { toon, mesh, sphere, box, cyl, cone, torus } from './toon.js';

// ---------------------------------------------------------------- DATA ROSTER
// kind: 'op' = inti (gaya bajak laut/petualang) · 'nr' = pendukung (gaya shinobi)
export const CAST = [
  { id: 'owner', profile: null, name: 'Mas Anas', title: 'Owner / Founder', kind: 'op', home: 'owner',
    persona: 'Pemimpi nekat tapi hangat. Memutuskan arah, menyetujui Gate #0, dan tidak pernah menyentuh deploy tanpa bukti.',
    routine: ['Minum kopi di kafe', 'Membaca papan keputusan', 'Menengok ruang proyek', 'Tidur siang di beanbag'],
    look: { skin: '#f6d2b0', hair: '#2a2330', hairStyle: 'messy', eye: '#5a3b2e', hat: 'straw', top: '#e8483f', topStyle: 'vest', legs: '#2f5fa8', shoes: '#b98a55', extra: ['scar'], prop: null } },
  { id: 'orch', profile: 'cc-orchestrator', name: 'Kapten Orka', title: 'Orchestrator · Koordinator', kind: 'op', home: 'den',
    persona: 'Tenang, dingin, selalu dua langkah di depan. Memecah ide menjadi 16 tahap dan menugaskan awak kapal.',
    routine: ['Menyusun papan 16 tahap', 'Mengetuk peta strategi', 'Memanggil agent ke ruang koordinasi', 'Minum teh sendirian'],
    look: { skin: '#f0cfae', hair: '#1e2233', hairStyle: 'sidepart', eye: '#6f7fb0', hat: 'tricorn', top: '#26324f', topStyle: 'longcoat', legs: '#1c2236', shoes: '#14161f', extra: ['cape'], prop: 'telescope' } },
  { id: 'arch', profile: 'cc-architect', name: 'Navi', title: 'Architect · Navigator desain', kind: 'op', home: 'arch',
    persona: 'Cerewet, teliti, cinta peta dan garis. Menghitung trade-off sebelum menggambar satu kotak pun.',
    routine: ['Menggambar blueprint', 'Memutar globe', 'Membandingkan 3 opsi stack', 'Mengomel soal scope'],
    look: { skin: '#fbd9bf', hair: '#f08a35', hairStyle: 'bob', eye: '#b8793a', hat: null, top: '#fdfdfd', topStyle: 'stripe', topAlt: '#4a9ad8', legs: '#4fae7a', shoes: '#d96b6b', extra: ['bangle'], prop: 'compass' } },
  { id: 'front', profile: 'cc-frontend', name: 'Pico', title: 'Frontend · Seniman antarmuka', kind: 'op', home: 'front',
    persona: 'Pencerita yang suka melebih-lebihkan, tapi tangannya presisi. Mengubah wireframe jadi layar yang enak dipandang.',
    routine: ['Melukis di easel', 'Mencampur warna palet', 'Mengintip hasil di HP', 'Bercerita keras-keras'],
    look: { skin: '#e9bf94', hair: '#2b2118', hairStyle: 'curly', eye: '#3a2a1c', hat: 'goggles', top: '#f2b640', topStyle: 'overall', topAlt: '#ee8a3a', legs: '#ee8a3a', shoes: '#6a4a2a', extra: ['longnose', 'bandana'], prop: 'brush' } },
  { id: 'build', profile: 'cc-builder', name: 'Bolt', title: 'Backend · Tukang kapal', kind: 'op', home: 'build',
    persona: 'Berisik, berotot, bangga pada baut-bautnya. Membangun API dan database sampai semua test hijau.',
    routine: ['Memalu di bengkel', 'Menyetel roda gigi', 'Mengangkat peti data', 'Pose "SUPER!" tiap build lulus'],
    look: { skin: '#f0c9a4', hair: '#3aa6e0', hairStyle: 'pomp', eye: '#223048', hat: null, top: '#1f9fa8', topStyle: 'tank', legs: '#2c3e6b', shoes: '#c94b3a', extra: ['shades', 'tool'], prop: 'wrench' } },
  { id: 'qa', profile: 'cc-reviewer-qa', name: 'Zen', title: 'Reviewer / QA · Pendekar', kind: 'op', home: 'qa',
    persona: 'Pendiam, sering tertidur, tapi setiap bug yang lewat langsung terpotong. Tidak percaya "sudah beres" tanpa bukti.',
    routine: ['Latihan tebas di dojo', 'Menimbang kode di rak pedang', 'Tidur siang', 'Menolak PR tanpa test'],
    look: { skin: '#eac39b', hair: '#4fae4f', hairStyle: 'spiky', eye: '#2c3a2c', hat: null, top: '#f1f1ec', topStyle: 'haramaki', topAlt: '#2f6a3a', legs: '#1f2a24', shoes: '#2a2a2a', extra: ['swords', 'earring'], prop: null } },
  { id: 'sec', profile: 'cc-security-governor', name: 'Rhea', title: 'Security Governor · Arsiparis', kind: 'op', home: 'sec',
    persona: 'Anggun, misterius, membaca semua yang tersembunyi. Menemukan celah sebelum orang lain sempat menyadarinya.',
    routine: ['Membaca arsip tua', 'Memeriksa brankas', 'Menyilangkan tangan: "tidak aman"', 'Menyeruput kopi hitam'],
    look: { skin: '#f4d6c0', hair: '#14121c', hairStyle: 'long', eye: '#6a4a9a', hat: 'widebrim', top: '#7a4aa8', topStyle: 'longcoat', legs: '#2a2038', shoes: '#1a1424', extra: ['lashes'], prop: 'book' } },
  { id: 'aud', profile: 'auditor', name: 'Hakim Putih', title: 'Auditor · Pemberi vonis', kind: 'op', home: 'aud',
    persona: 'Kaku dan adil. Tidak peduli siapa yang membangun — hanya bukti segar yang ia dengarkan.',
    routine: ['Memukul palu vonis', 'Menimbang bukti di neraca', 'Mencoret klaim tanpa data', 'Meluruskan dasi'],
    look: { skin: '#f1d3b8', hair: '#ececf2', hairStyle: 'sidepart', eye: '#4a5a7a', hat: 'marine', top: '#f6f7fb', topStyle: 'longcoat', topAlt: '#2b4a8a', legs: '#2b3a5c', shoes: '#15181f', extra: ['monocle', 'cape'], prop: 'gavel' } },
  { id: 'ops', profile: 'cc-devops-docs', name: 'Sanju', title: 'DevOps / Docs · Koki kapal', kind: 'op', home: 'ops',
    persona: 'Perfeksionis dapur, galak pada kekacauan. Merilis, men-deploy, dan menulis runbook seperti resep.',
    routine: ['Mengaduk pipeline di panci', 'Menyiapkan makan siang awak', 'Menempel resep deploy', 'Membersihkan dapur'],
    look: { skin: '#f6d8bd', hair: '#f3d36a', hairStyle: 'swept', eye: '#3b5a8a', hat: null, top: '#1d1d28', topStyle: 'suit', topAlt: '#f5c542', legs: '#1d1d28', shoes: '#0f0f14', extra: ['apron', 'swirlbrow'], prop: 'pot' } },
  { id: 'rec', profile: 'cc-capture-forensics', name: 'Kaze', title: 'Research / Recon · Shinobi pengintai', kind: 'nr', home: 'rec',
    persona: 'Santai, selalu terlambat, tetapi tahu segalanya. Membaca sumber dengan skeptis dan menandai yang tidak terverifikasi.',
    routine: ['Membaca gulungan', 'Mengintai sumber data', 'Menandai klaim "TIDAK TERVERIFIKASI"', 'Menghilang lalu muncul lagi'],
    look: { skin: '#f0d3b8', hair: '#c9ccd6', hairStyle: 'spiky', eye: '#2a2a3a', hat: 'hitai', top: '#26385a', topStyle: 'vestnr', legs: '#26385a', shoes: '#1b2236', extra: ['mask', 'eyecover'], prop: 'scroll' } },
  { id: 'grd', profile: 'keamanan', name: 'Suna', title: 'Keamanan · Penjaga gerbang', kind: 'nr', home: 'grd',
    persona: 'Pendiam dan waspada. Menjaga gerbang, memeriksa kredensial, dan melindungi privasi tanpa banyak bicara.',
    routine: ['Berjaga di gerbang', 'Meratakan taman pasir', 'Memeriksa kunci', 'Berdiri diam memandang jauh'],
    look: { skin: '#f3d9c6', hair: '#c4412f', hairStyle: 'messy', eye: '#6fb7b0', hat: null, top: '#d8b98a', topStyle: 'vestnr', legs: '#7a5a3a', shoes: '#4a3a2a', extra: ['eyerings', 'gourd', 'kanji'], prop: null } },
];
export const BARISTA = { id: 'barista', name: 'Mimi', title: 'Barista (dekoratif)', kind: 'op',
  look: { skin: '#f6d8bd', hair: '#8a5a3a', hairStyle: 'bob', eye: '#5a3b2e', hat: null, top: '#f3c6d4', topStyle: 'apron2', legs: '#6a5a7a', shoes: '#3a2a2a', extra: [], prop: null } };

const C = (c) => new THREE.Color(c);
function rng(seed) { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; }

// ---------------------------------------------------------------- RAMBUT
function buildHair(head, L, seed) {
  const col = L.hair, r = rng(seed + 7), st = L.hairStyle;
  const capTheta = st === 'bob' || st === 'long' ? 0.66 : 0.56;
  const cap = mesh(new THREE.SphereGeometry(0.665, 24, 16, 0, Math.PI * 2, 0, Math.PI * capTheta), col, { out: 1.04, parent: head, rot: [-0.18, 0, 0] });
  cap.position.set(0, 0.02, -0.04);
  const add = (m) => { head.add(m); return m; };
  const spikes = (n, len, rad, yMin, yMax) => {
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + r() * 0.5, e = yMin + r() * (yMax - yMin);
      const c = cone(rad * (0.8 + r() * 0.5), len * (0.7 + r() * 0.6), col, { out: 1.08 });
      c.position.set(Math.sin(a) * 0.5 * Math.cos(e), 0.3 + Math.sin(e) * 0.5, Math.cos(a) * 0.5 * Math.cos(e) - 0.1);
      c.lookAt(c.position.clone().multiplyScalar(3)); c.rotateX(Math.PI / 2); add(c);
    }
  };
  switch (st) {
    case 'spiky': spikes(10, 0.55, 0.17, 0.2, 1.1);
      for (let i = -1; i <= 1; i++) { const f = cone(0.13, 0.4, col, { out: 1.08 }); f.position.set(i * 0.22, 0.34, 0.55); f.rotation.set(Math.PI * 0.62, 0, i * 0.35); add(f); } break;
    case 'messy': spikes(13, 0.5, 0.16, 0.0, 1.0);
      for (let i = -2; i <= 2; i++) { const f = cone(0.1, 0.34, col, { out: 1.08 }); f.position.set(i * 0.15, 0.37, 0.56); f.rotation.set(Math.PI * 0.6, 0, i * 0.25); add(f); } break;
    case 'bob': {
      const back = sphere(0.7, col, { out: 1.04, parent: head, scl: [1, 1.0, 0.85] }); back.position.set(0, -0.12, -0.2);
      [-1, 1].forEach((s) => { const sd = box(0.16, 0.7, 0.34, col, { out: 1.06 }); sd.position.set(s * 0.6, -0.18, 0.02); add(sd); });
      const fr = box(0.95, 0.2, 0.2, col, { out: 1.04 }); fr.position.set(0, 0.4, 0.5); fr.rotation.x = -0.5; add(fr); break; }
    case 'long': {
      const back = box(1.0, 1.9, 0.3, col, { out: 1.04 }); back.position.set(0, -0.7, -0.42); add(back);
      [-1, 1].forEach((s) => { const sd = box(0.14, 1.0, 0.3, col, { out: 1.05 }); sd.position.set(s * 0.6, -0.35, 0.05); add(sd); });
      const fr = box(0.95, 0.2, 0.22, col, { out: 1.04 }); fr.position.set(0, 0.4, 0.5); fr.rotation.x = -0.55; add(fr); break; }
    case 'pomp': {
      const p = sphere(0.5, col, { out: 1.05, parent: head, scl: [1.0, 0.85, 1.5] }); p.position.set(0, 0.62, 0.28);
      const p2 = sphere(0.38, col, { out: 1.05, parent: head }); p2.position.set(0, 0.78, 0.55); break; }
    case 'curly':
      for (let i = 0; i < 14; i++) { const a = (i / 14) * 6.283, p = sphere(0.22 + r() * 0.08, col, { out: 1.07 });
        p.position.set(Math.sin(a) * 0.5, 0.42 + r() * 0.2, Math.cos(a) * 0.5 - 0.05); add(p); }
      for (let i = 0; i < 5; i++) { const p = sphere(0.2, col, { out: 1.07 }); p.position.set((i - 2) * 0.17, 0.55 + (i % 2) * 0.06, 0.05); add(p); } break;
    case 'swept': {
      const fr = sphere(0.42, col, { out: 1.05, parent: head, scl: [1.3, 0.5, 0.9] }); fr.position.set(-0.12, 0.42, 0.34); fr.rotation.z = 0.35;
      const fr2 = cone(0.2, 0.55, col, { out: 1.07, parent: head }); fr2.position.set(0.12, 0.3, 0.52); fr2.rotation.set(Math.PI * 0.55, 0, 0.7);
      spikes(5, 0.3, 0.15, 0.3, 0.9); break; }
    case 'sidepart': {
      const fr = box(0.85, 0.2, 0.22, col, { out: 1.05 }); fr.position.set(0.1, 0.4, 0.5); fr.rotation.set(-0.5, 0, 0.18); add(fr);
      [-1, 1].forEach((s) => { const sd = box(0.12, 0.45, 0.28, col, { out: 1.05 }); sd.position.set(s * 0.6, -0.05, 0.05); add(sd); }); break; }
  }
}

// ---------------------------------------------------------------- WAJAH
function buildFace(head, L) {
  const wh = '#fffdf8';
  [-1, 1].forEach((s) => {
    const sc = L.extra.includes('longnose') ? 1 : 1;
    const eyeW = sphere(0.15, wh, { mat: new THREE.MeshBasicMaterial({ color: wh }), cast: false, parent: head, scl: [1, 1.3, 0.35] });
    eyeW.position.set(s * 0.22, -0.02, 0.55);
    const iris = sphere(0.105, L.eye, { mat: new THREE.MeshBasicMaterial({ color: L.eye }), cast: false, parent: head, scl: [1, 1.3, 0.35] });
    iris.position.set(s * 0.22, -0.04, 0.585);
    const pup = sphere(0.055, '#14121c', { mat: new THREE.MeshBasicMaterial({ color: 0x14121c }), cast: false, parent: head, scl: [1, 1.25, 0.3] });
    pup.position.set(s * 0.22, -0.04, 0.605);
    const hl = sphere(0.04, '#ffffff', { mat: new THREE.MeshBasicMaterial({ color: 0xffffff }), cast: false, parent: head });
    hl.position.set(s * 0.22 + 0.04, 0.03, 0.62);
    const blush = sphere(0.1, '#ff9aa8', { mat: new THREE.MeshBasicMaterial({ color: 0xff9aa8, transparent: true, opacity: 0.45 }), cast: false, parent: head, scl: [1.2, 0.7, 0.3] });
    blush.position.set(s * 0.38, -0.2, 0.46);
    if (L.extra.includes('lashes')) { const l = box(0.2, 0.025, 0.02, '#14121c', { mat: new THREE.MeshBasicMaterial({ color: 0x14121c }), cast: false, parent: head }); l.position.set(s * 0.25, 0.1, 0.6); l.rotation.z = s * -0.25; }
    if (L.extra.includes('eyerings')) { const l = sphere(0.19, '#3a2430', { mat: new THREE.MeshBasicMaterial({ color: 0x3a2430 }), cast: false, parent: head, scl: [1, 1.15, 0.2] }); l.position.set(s * 0.22, -0.03, 0.535); }
    if (L.extra.includes('swirlbrow') && s === 1) { const b = torus(0.06, 0.018, '#c9a23a', { mat: new THREE.MeshBasicMaterial({ color: 0xc9a23a }), cast: false, parent: head }); b.position.set(0.24, 0.17, 0.58); }
  });
  const mouth = new THREE.Mesh(new THREE.TorusGeometry(0.075, 0.016, 6, 14, Math.PI), new THREE.MeshBasicMaterial({ color: 0x6b2f3b }));
  mouth.position.set(0, -0.27, 0.575); mouth.rotation.z = Math.PI; head.add(mouth);
  const ear = (s) => { const e = sphere(0.1, L.skin, { parent: head, scl: [0.5, 1, 0.8] }); e.position.set(s * 0.66, -0.05, 0); };
  ear(-1); ear(1);
  if (L.extra.includes('scar')) { const s = box(0.15, 0.025, 0.02, '#b84a4a', { mat: new THREE.MeshBasicMaterial({ color: 0xb84a4a }), cast: false, parent: head }); s.position.set(-0.28, -0.16, 0.6); s.rotation.z = 0.6; }
  if (L.extra.includes('earring')) { [0, 0.09, 0.18].forEach((y) => { const e = sphere(0.04, '#ffd24a', { parent: head }); e.position.set(0.7, -0.12 - y, 0); }); }
  if (L.extra.includes('mask')) { const m = sphere(0.6, '#24304a', { parent: head, scl: [0.95, 0.55, 0.9] }); m.position.set(0, -0.36, 0.1); const nose = box(0.14, 0.12, 0.1, '#24304a', { parent: head }); nose.position.set(0, -0.13, 0.57); }
  if (L.extra.includes('shades')) {
    const bk = new THREE.MeshBasicMaterial({ color: 0x1a1d2a });
    [-1, 1].forEach((s) => { const lens = sphere(0.17, '#1a1d2a', { mat: bk, cast: false, parent: head, scl: [1.05, 0.8, 0.25] }); lens.position.set(s * 0.22, -0.02, 0.66);
      const sh = sphere(0.05, '#bfe6ff', { mat: new THREE.MeshBasicMaterial({ color: 0xbfe6ff }), cast: false, parent: head, scl: [1.6, 0.8, 0.3] }); sh.position.set(s * 0.22 - 0.06, 0.03, 0.7);
      const sd = box(0.035, 0.04, 0.5, '#1a1d2a', { parent: head }); sd.position.set(s * 0.43, 0.0, 0.4); });
    const br = box(0.12, 0.035, 0.04, '#1a1d2a', { mat: bk, cast: false, parent: head }); br.position.set(0, 0.0, 0.67); }
  if (L.extra.includes('monocle')) { const m = torus(0.13, 0.018, '#d4b24a', { parent: head }); m.position.set(0.22, -0.03, 0.62); const ch = cyl(0.008, 0.008, 0.9, '#d4b24a', { parent: head }); ch.position.set(0.36, -0.5, 0.58); ch.rotation.z = 0.2; }
  if (L.extra.includes('longnose')) { const n = cone(0.07, 0.45, L.skin, { parent: head, out: 1.07 }); n.position.set(0, -0.1, 0.78); n.rotation.x = Math.PI / 2; }
  if (L.extra.includes('eyecover')) { const e = sphere(0.19, '#26385a', { parent: head, scl: [1.2, 1.5, 0.3] }); e.position.set(-0.22, 0.0, 0.58); }
}

// ---------------------------------------------------------------- TOPI / IKAT KEPALA
function buildHat(head, L) {
  const h = L.hat; if (!h) return;
  if (h === 'straw') {
    const brim = cyl(1.0, 1.0, 0.07, '#f1d17a', { out: 1.03, parent: head }); brim.position.set(0, 0.44, 0);
    const dome = sphere(0.55, '#f1d17a', { out: 1.04, parent: head, scl: [1, 0.85, 1] }); dome.position.set(0, 0.45, 0);
    const band = cyl(0.57, 0.57, 0.16, '#d9382f', { parent: head }); band.position.set(0, 0.5, 0);
  } else if (h === 'tricorn') {
    const b = cyl(0.98, 0.98, 0.09, '#1d2438', { out: 1.04, parent: head, seg: 3 }); b.position.set(0, 0.55, 0); b.rotation.y = Math.PI / 2;
    const d = sphere(0.5, '#1d2438', { out: 1.04, parent: head, scl: [1, 0.7, 1] }); d.position.set(0, 0.56, 0);
    const trim = torus(0.9, 0.025, '#e0b94a', { parent: head }); trim.position.set(0, 0.6, 0); trim.rotation.x = Math.PI / 2; trim.scale.set(0.9, 0.9, 1);
    const sk = sphere(0.12, '#f3efe6', { parent: head, scl: [1, 1, 0.3] }); sk.position.set(0, 0.62, 0.52);
  } else if (h === 'goggles') {
    const band = cyl(0.68, 0.68, 0.08, '#4b3a28', { parent: head }); band.position.set(0, 0.34, 0);
    [-1, 1].forEach((s) => { const g = torus(0.15, 0.04, '#d4a23a', { parent: head }); g.position.set(s * 0.22, 0.38, 0.6); g.rotation.x = -0.25;
      const gl = sphere(0.13, '#bde7ff', { mat: new THREE.MeshBasicMaterial({ color: 0xbde7ff, transparent: true, opacity: 0.8 }), cast: false, parent: head, scl: [1, 1, 0.2] }); gl.position.set(s * 0.22, 0.38, 0.62); });
  } else if (h === 'widebrim') {
    const b = cyl(1.05, 1.05, 0.05, '#5a2f86', { out: 1.03, parent: head }); b.position.set(0, 0.45, 0); b.rotation.z = 0.06;
    const d = cyl(0.5, 0.56, 0.5, '#5a2f86', { out: 1.04, parent: head }); d.position.set(0, 0.7, 0);
    const band = cyl(0.57, 0.57, 0.1, '#d0a8f0', { parent: head }); band.position.set(0, 0.52, 0);
  } else if (h === 'marine') {
    const d = cyl(0.62, 0.66, 0.38, '#f6f7fb', { out: 1.04, parent: head }); d.position.set(0, 0.64, 0);
    const v = box(0.8, 0.05, 0.4, '#1b2a4a', { parent: head }); v.position.set(0, 0.5, 0.66);
    const bd = sphere(0.1, '#e0b94a', { parent: head, scl: [1, 1, 0.3] }); bd.position.set(0, 0.68, 0.7);
    const band = cyl(0.67, 0.67, 0.1, '#1b2a4a', { parent: head }); band.position.set(0, 0.52, 0);
  } else if (h === 'hitai') {
    const band = cyl(0.675, 0.675, 0.17, '#26385a', { parent: head }); band.position.set(0, 0.3, 0);
    const plate = box(0.42, 0.2, 0.05, '#c9d0de', { out: 1.1, parent: head }); plate.position.set(0.0, 0.3, 0.66);
    const ln = box(0.26, 0.025, 0.02, '#4a5675', { mat: new THREE.MeshBasicMaterial({ color: 0x4a5675 }), cast: false, parent: head }); ln.position.set(0, 0.3, 0.7);
  }
  if (L.extra.includes('bandana')) { /* tambahan ikat kepala hijau di bawah goggles */
    const bd = cyl(0.69, 0.69, 0.1, '#3a9a5a', { parent: head }); bd.position.set(0, 0.2, 0);
  }
}

// ---------------------------------------------------------------- BADAN
function buildBody(g, L, parts) {
  const skin = L.skin;
  const hip = new THREE.Group(); hip.position.y = 0.62; g.add(hip); parts.hip = hip;
  const legs = [];
  [-1, 1].forEach((s) => {
    const lg = new THREE.Group(); lg.position.set(s * 0.16, 0, 0); hip.add(lg);
    const leg = cyl(0.12, 0.11, 0.55, L.legs, { out: 1.08, parent: lg }); leg.position.y = -0.3;
    const sh = box(0.26, 0.14, 0.38, L.shoes, { out: 1.08, parent: lg }); sh.position.set(0, -0.62, 0.05);
    legs.push(lg);
  });
  parts.legL = legs[0]; parts.legR = legs[1];

  const torso = new THREE.Group(); torso.position.y = 0.0; hip.add(torso); parts.torso = torso;
  const T = L.topStyle, tc = L.top;
  const body = cyl(0.3, 0.34, 0.8, T === 'vest' || T === 'tank' || T === 'vestnr' || T === 'haramaki' ? skin : tc, { out: 1.05, parent: torso }); body.position.y = 0.42;
  if (T === 'vest') { [-1, 1].forEach((s) => { const v = box(0.2, 0.78, 0.5, tc, { out: 1.05, parent: torso }); v.position.set(s * 0.24, 0.42, 0.04); v.rotation.z = s * -0.04; });
    const bk = cyl(0.31, 0.35, 0.78, tc, { parent: torso, scl: [1, 1, 0.5] }); bk.position.set(0, 0.42, -0.1); }
  if (T === 'tank') { const tk = cyl(0.31, 0.35, 0.8, tc, { out: 1.05, parent: torso }); tk.position.y = 0.42; tk.scale.set(1, 1, 1); body.visible = false; }
  if (T === 'stripe') { for (let i = 0; i < 4; i++) { const st = cyl(0.335 - i * 0.0, 0.335, 0.1, L.topAlt, { parent: torso }); st.position.y = 0.2 + i * 0.2; st.scale.set(1.01, 1, 1.01); } }
  if (T === 'overall') { const ov = cyl(0.32, 0.36, 0.5, L.topAlt, { out: 1.05, parent: torso }); ov.position.y = 0.22;
    [-1, 1].forEach((s) => { const st = box(0.07, 0.5, 0.07, L.topAlt, { parent: torso }); st.position.set(s * 0.16, 0.65, 0.25); });
    [-1, 1].forEach((s) => { const bt = sphere(0.05, '#f6e07a', { parent: torso }); bt.position.set(s * 0.16, 0.5, 0.3); }); }
  if (T === 'haramaki') { const hr = cyl(0.345, 0.345, 0.26, L.topAlt, { out: 1.05, parent: torso }); hr.position.y = 0.2; body.visible = true; body.material = toon(skin);
    const sh = cyl(0.31, 0.34, 0.5, tc, { out: 1.05, parent: torso }); sh.position.y = 0.65; sh.scale.set(1.0, 1, 1.0); }
  if (T === 'longcoat') { const sk = cone(0.7, 1.2, tc, { out: 1.04, parent: torso, seg: 24 }); sk.position.y = -0.1; sk.scale.set(1, 1, 0.85);
    const bt = cyl(0.36, 0.36, 0.08, '#d4b24a', { parent: torso }); bt.position.y = 0.12;
    for (let i = 0; i < 3; i++) { const bt2 = sphere(0.045, '#d4b24a', { parent: torso }); bt2.position.set(0, 0.3 + i * 0.2, 0.34); }
    if (L.topAlt) { const lap = box(0.6, 0.5, 0.05, L.topAlt, { parent: torso }); lap.position.set(0, 0.55, 0.32); } }
  if (T === 'suit') { const sj = cyl(0.31, 0.35, 0.82, tc, { out: 1.05, parent: torso }); sj.position.y = 0.42;
    const sh = box(0.22, 0.55, 0.05, '#fdfdfd', { parent: torso }); sh.position.set(0, 0.55, 0.32);
    const tie = cone(0.07, 0.45, L.topAlt, { parent: torso }); tie.position.set(0, 0.55, 0.36); tie.rotation.x = Math.PI; }
  if (T === 'vestnr') { const sh = cyl(0.31, 0.35, 0.8, tc, { out: 1.05, parent: torso }); sh.position.y = 0.42;
    if (L.topStyle === 'vestnr' && L.hat === 'hitai') { const fl = box(0.5, 0.65, 0.12, '#3a4f78', { out: 1.05, parent: torso }); fl.position.set(0, 0.5, 0.3); [-0.2, 0, 0.2].forEach((x) => { const p = box(0.1, 0.12, 0.05, '#2a3a5a', { parent: torso }); p.position.set(x, 0.38, 0.38); }); } }
  if (T === 'apron2') { const sh = cyl(0.31, 0.35, 0.8, '#fdf3ee', { out: 1.05, parent: torso }); sh.position.y = 0.42; const ap = box(0.5, 0.7, 0.05, tc, { parent: torso }); ap.position.set(0, 0.38, 0.33); }
  if (L.extra.includes('apron')) { const ap = box(0.5, 0.65, 0.05, '#fdf3ee', { out: 1.03, parent: torso }); ap.position.set(0, 0.4, 0.37); }
  if (L.extra.includes('cape')) { const cp = box(0.8, 1.2, 0.06, L.id === 'aud' ? '#f6f7fb' : '#3a1f2e', { out: 1.04, parent: torso }); cp.position.set(0, 0.2, -0.38); cp.rotation.x = 0.1; parts.cape = cp;
    if (L.hat === 'marine') { const jc = box(0.5, 0.28, 0.01, '#1b2a4a', { parent: cp }); jc.position.set(0, 0.3, -0.04); } }
  if (L.extra.includes('swords')) { [-0.18, 0, 0.18].forEach((x, i) => { const sw = box(0.05, 0.9, 0.05, i === 1 ? '#c9d0de' : '#e8ecf4', { out: 1.1, parent: torso }); sw.position.set(0.36, 0.06 + i * 0.02, 0.0 + x * 0.8); sw.rotation.set(0.1, 0, -1.25);
      const hd = cyl(0.045, 0.045, 0.2, '#3a2a1c', { parent: torso }); hd.position.set(0.7, 0.2 + i * 0.02, x * 0.8 - 0.0); hd.rotation.set(0, 0, -1.25); }); }
  if (L.extra.includes('gourd')) { const gd = sphere(0.36, '#d8a85a', { out: 1.05, parent: torso, scl: [1, 1.2, 0.9] }); gd.position.set(0, 0.55, -0.55); const gt = sphere(0.2, '#d8a85a', { out: 1.05, parent: torso }); gt.position.set(0, 1.0, -0.55); const cap = cyl(0.07, 0.09, 0.1, '#b8793a', { parent: torso }); cap.position.set(0, 1.18, -0.55); const st = box(0.06, 0.9, 0.04, '#8a5a3a', { parent: torso }); st.position.set(0.15, 0.55, -0.1); st.rotation.z = -0.5; }
  if (L.extra.includes('kanji')) { const k = box(0.1, 0.1, 0.02, '#c4412f', { mat: new THREE.MeshBasicMaterial({ color: 0xc4412f }), cast: false, parent: torso }); k.position.set(0, 0.55, 0.36); }
  if (L.extra.includes('bangle')) { /* pada tangan, diset di arm */ }
  if (L.extra.includes('tool')) { const b = box(0.52, 0.1, 0.1, '#8a6a3a', { parent: torso }); b.position.set(0, 0.12, 0.34); [-1, 1].forEach((s) => { const p = box(0.08, 0.2, 0.08, '#c9d0de', { parent: torso }); p.position.set(s * 0.18, 0.04, 0.38); }); }

  // lengan (pivot di bahu)
  const arms = [];
  [-1, 1].forEach((s) => {
    const ar = new THREE.Group(); ar.position.set(s * 0.43, 0.76, 0); torso.add(ar);
    const sleeveCol = (T === 'vest' || T === 'tank' || T === 'haramaki' || T === 'overall') ? (T === 'overall' ? tc : (T === 'haramaki' ? tc : skin)) : (T === 'vestnr' ? '#26385a' : tc);
    const am = cyl(0.1, 0.095, 0.55, sleeveCol, { out: 1.08, parent: ar }); am.position.y = -0.27;
    const hand = sphere(0.12, skin, { out: 1.08, parent: ar }); hand.position.y = -0.6;
    if (L.extra.includes('bangle') && s === 1) { const bg = torus(0.1, 0.03, '#ffd24a', { parent: ar }); bg.position.y = -0.5; bg.rotation.x = Math.PI / 2; }
    ar.userData.hand = hand; arms.push(ar);
    ar.rotation.z = s * 0.12;
  });
  parts.armL = arms[0]; parts.armR = arms[1];
}

// ---------------------------------------------------------------- PROPERTI (di tangan kanan)
function buildProp(type, parts) {
  if (!type) return;
  const hand = parts.armR.userData.hand, P = new THREE.Group(); P.position.set(0, -0.02, 0.1); hand.add(P); parts.prop = P;
  const add = (m) => P.add(m);
  switch (type) {
    case 'wrench': { const h = cyl(0.045, 0.045, 0.8, '#c9d0de', { out: 1.1 }); h.rotation.x = 0.4; const hd = torus(0.13, 0.05, '#c9d0de', { out: 1.1 }); hd.position.set(0, 0.05, 0.36); hd.rotation.x = 0.4; add(h); add(hd); break; }
    case 'brush': { const h = cyl(0.03, 0.03, 0.8, '#7a4a2a', { out: 1.1 }); h.rotation.x = 0.5; const tip = cone(0.07, 0.22, '#e74a8a', { out: 1.1 }); tip.position.set(0, 0.1, 0.38); tip.rotation.x = 0.5 - Math.PI / 2 + Math.PI; add(h); add(tip); break; }
    case 'compass': { const c = cyl(0.17, 0.17, 0.06, '#d4b24a', { out: 1.1 }); c.rotation.x = Math.PI / 2; c.position.set(0, 0, 0.12); const n = cone(0.04, 0.2, '#d9382f'); n.position.set(0, 0, 0.16); n.rotation.z = 0.8; add(c); add(n); break; }
    case 'telescope': { const t = cyl(0.07, 0.09, 0.7, '#8a6a3a', { out: 1.1 }); t.rotation.x = Math.PI / 2 - 0.3; t.position.z = 0.25; const r = torus(0.09, 0.02, '#d4b24a'); r.position.set(0, 0.1, 0.55); r.rotation.x = 0.0; add(t); add(r); break; }
    case 'book': { const b = box(0.36, 0.06, 0.48, '#7a3a2a', { out: 1.06 }); b.position.set(0, 0.05, 0.22); b.rotation.x = -0.5; const pg = box(0.32, 0.05, 0.44, '#fff4dc'); pg.position.set(0, 0.07, 0.22); pg.rotation.x = -0.5; add(b); add(pg); break; }
    case 'gavel': { const h = cyl(0.03, 0.03, 0.5, '#7a4a2a', { out: 1.1 }); h.rotation.x = 0.3; const hd = cyl(0.1, 0.1, 0.3, '#5a3a22', { out: 1.1 }); hd.rotation.z = Math.PI / 2; hd.position.set(0, 0.2, 0.18); add(h); add(hd); break; }
    case 'pot': { const p = cyl(0.2, 0.17, 0.2, '#a9afbb', { out: 1.08 }); p.position.set(0, 0.05, 0.28); const hh = box(0.3, 0.04, 0.04, '#6a6f7a'); hh.position.set(0.22, 0.1, 0.28); const st = cyl(0.17, 0.17, 0.02, '#f08a35'); st.position.set(0, 0.16, 0.28); add(p); add(hh); add(st); break; }
    case 'scroll': { const s = cyl(0.08, 0.08, 0.5, '#f1e2b8', { out: 1.1 }); s.rotation.z = Math.PI / 2; s.position.set(0, 0.05, 0.2); const e = cyl(0.09, 0.09, 0.04, '#b04a3a'); e.rotation.z = Math.PI / 2; e.position.set(0.27, 0.05, 0.2); const e2 = e.clone(); e2.position.x = -0.27; add(s); add(e); add(e2); break; }
  }
}

// ---------------------------------------------------------------- PERAKIT
export function buildCharacter(spec, seed = 1) {
  const L = { ...spec.look, id: spec.id };
  const g = new THREE.Group();
  const parts = {};
  buildBody(g, L, parts);
  const head = new THREE.Group(); head.position.y = 1.98; parts.hip.add(head); // head dalam hip -> ikut jongkok saat duduk
  head.position.y = 1.98 - 0.62;
  const skull = sphere(0.66, L.skin, { out: 1.04, parent: head });
  buildFace(head, L); buildHair(head, L, seed); buildHat(head, L);
  parts.head = head;
  buildProp(L.prop, parts);
  g.userData = { parts, spec, sit: false };
  g.scale.setScalar(0.86);
  g.traverse((o) => { if (o.isMesh && !o.userData.outline) { o.castShadow = true; } });
  return g;
}

// pose/anim: state = {mode:'idle'|'walk'|'work'|'read'|'rest'|'pose', t}
export function animate(g, state, t, dt) {
  const p = g.userData.parts, s = Math.sin, k = state.mode;
  const sit = k === 'work' || k === 'read' || k === 'rest';
  const targetHip = sit ? 0.34 : 0.62;
  p.hip.position.y += (targetHip - p.hip.position.y) * Math.min(1, dt * 8);
  const legRot = sit ? -1.45 : (k === 'walk' ? s(t * 9) * 0.7 : 0);
  p.legL.rotation.x += (legRot - p.legL.rotation.x) * Math.min(1, dt * 10);
  p.legR.rotation.x += ((sit ? -1.45 : (k === 'walk' ? -s(t * 9) * 0.7 : 0)) - p.legR.rotation.x) * Math.min(1, dt * 10);
  let aL = 0, aR = 0;
  if (k === 'walk') { aL = -s(t * 9) * 0.8; aR = s(t * 9) * 0.8; }
  else if (k === 'work') { aL = -0.9 + s(t * 11) * 0.12; aR = -0.9 + s(t * 11 + 2) * 0.14; }
  else if (k === 'read') { aL = -1.2; aR = -1.2 + s(t * 0.8) * 0.04; }
  else if (k === 'pose') { aR = -2.7 + s(t * 6) * 0.1; aL = 0.2; }
  else if (k === 'wave') { aR = -2.5 + s(t * 8) * 0.4; }
  else if (k === 'rest') { aL = -0.2; aR = -0.2; }
  else { aL = s(t * 1.4) * 0.05; aR = -s(t * 1.4) * 0.05; }
  p.armL.rotation.x += (aL - p.armL.rotation.x) * Math.min(1, dt * 10);
  p.armR.rotation.x += (aR - p.armR.rotation.x) * Math.min(1, dt * 10);
  p.torso.scale.y = 1 + s(t * 2) * 0.012;
  p.head.rotation.x = k === 'rest' ? 0.4 : (k === 'read' ? 0.25 + s(t * 0.7) * 0.03 : s(t * 1.7) * 0.025);
  p.head.rotation.z = k === 'rest' ? s(t * 0.9) * 0.08 : 0;
  if (p.cape) p.cape.rotation.x = 0.1 + (k === 'walk' ? 0.35 + s(t * 9) * 0.1 : s(t * 1.2) * 0.03);
  if (p.prop) p.prop.rotation.x = k === 'pose' ? 0.3 : 0;
}
