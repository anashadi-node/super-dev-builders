---
name: accessibility-audit
description: "Use to verify WCAG-level accessibility with axe plus manual checks."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [accessibility, a11y, wcag, axe, keyboard, aria]
    divisions: [D4, D7]
    related_skills: [reconstruction-fidelity, test-pyramid-and-risk]
---


# Accessibility Audit

Aksesibilitas adalah requirement kualitas, bukan pelengkap. Automated = bukti awal, bukan verdict.

## Prosedur
1. Automated: jalankan axe-core pada setiap layar/state utama (default, form error, modal terbuka, empty).
   Simpan hasil JSON mentah; `incomplete`/`inapplicable` **bukan** lulus.
2. Manual (wajib, area yang automation tidak bisa pastikan):
   - navigasi keyboard penuh: tab order logis, tanpa keyboard trap, `Esc` menutup modal, focus kembali ke pemicu;
   - visible focus indicator;
   - struktur heading hierarkis (h1-h2-h3 tanpa lompat);
   - label form + deskripsi error terprogram (`aria-describedby`), bukan hanya warna;
   - kontras teks/ikon (hitung rasio, target WCAG AA: 4.5:1 normal, 3:1 besar);
   - gambar dekoratif `alt=""`, gambar informatif punya alt bermakna;
   - live region untuk update dinamis;
   - zoom 200% tanpa kehilangan fungsi.
3. Uji dengan target viewport/device representatif dan tulis environment-nya.

## Output
- `verification/<target>/a11y/axe-<screen>.json` + `reports/a11y-report.md`
  (temuan per WCAG SC, severity, lokasi, bukti, status perbaikan).
- Ringkas: jumlah temuan per tingkat, yang inconclusive, cakupan layar yang diuji (coverage).

## Aturan
- "Tidak ada error axe" tidak sama dengan "accessible". Tulis secara eksplisit apa yang tidak diuji.
