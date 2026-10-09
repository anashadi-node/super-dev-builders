---
name: technology-profiler
description: "Infer target tech stack with confidence"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [reconstruction, technology, fingerprint, confidence]
    divisions: [D1, D3]
    related_skills: [target-inventory, technology-selection]
---


# Technology Profiler

Menggabungkan sinyal publik (header, aset, nama script/module, perilaku runtime, DOM) menjadi dugaan stack
**dengan skor confidence**, bukan kepastian.

## Sinyal yang boleh dipakai
- HTTP response header publik (server, framework hints, cache).
- Nama/chunk JavaScript, sourcemap publik bila memang disajikan.
- Struktur DOM/atribut khas framework, CSS custom property, meta tag.
- Cookie **nama saja** (tanpa nilai), format routing (hash vs history), perilaku hydration.

## Prosedur
1. Kumpulkan sinyal; simpan sebagai daftar bukti dengan `provenance`.
2. Untuk tiap teknologi: `name`, `signal[]`, `confidence` (0-100), `status: INFERRED`.
3. Konversi ke rekomendasi stack hanya lewat `skills/technology-selection` oleh D3 — profiler tidak memutuskan.

## Aturan
- Tidak ada fingerprinting agresif, tidak ada probing endpoint, tidak ada upaya menembus obfuscation.
- Confidence < 50 => jangan dipakai sebagai dasar keputusan arsitektur.
- Fingerprint **bukan** bukti arsitektur source: bedakan tegas antara "terlihat X" dan "dibangun dengan X".

## Output
- `normalized/<target>/technology.json`: `[{name, signal[], confidence, status, provenance}]`
- Ringkasan: yang yakin, yang meragukan, yang UNKNOWN.
