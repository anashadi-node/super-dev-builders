---
name: target-inventory
description: "Enumerate pages, routes, roles, forms"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [reconstruction, inventory, scope, evidence]
    divisions: [D1, D3]
    related_skills: [ui-ux-state-mapper, reconstruction-spec]
---


# Target Inventory

Mendaftar permukaan target yang sah **sebelum** capture mendalam, sehingga pekerjaan terukur dan tidak melebar.

## Prosedur
1. Konfirmasi Gate #0 PASS.
2. Enumerasi dari sumber yang diizinkan: sitemap publik, navigasi yang terlihat, tautan internal yang dapat diklik,
   menu, footer, dokumentasi publik.
3. Catat per halaman/screen: URL/route, peran yang boleh mengakses, entry point, form, tabel/list, state khusus
   (empty/loading/error/success), aset penting.
4. Tandai area yang butuh login/berbayar sebagai `OUT_OF_SCOPE` (bukan ditebak).
5. Simpan `normalized/<target>/inventory.json` dengan field: `id, url, title, role, entry_points, forms,
   states, feature_area, status, provenance, captured_at`.

## Aturan
- Hormati `robots.txt` dan rate limit; tanpa anti-bot evasion, tanpa proxy rotation.
- Jangan menyimpulkan endpoint/backend privat dari pola URL (itu INFERRED + confidence, atau UNKNOWN).
- Batas jumlah: mulai kecil (mis. 25 halaman inti), perluas hanya bila ada alasan.
- Setiap baris inventory wajib punya status: FACT / INFERRED / UNKNOWN / OUT_OF_SCOPE.

## Output
- `normalized/<target>/inventory.json`
- Ringkasan gap: area yang tidak bisa dipetakan + alasannya (login/paywall/dinamis).

## Judgement
- Inventory "lengkap" tidak pernah diklaim; laporkan cakupan (berapa banyak dari yang terlihat).
