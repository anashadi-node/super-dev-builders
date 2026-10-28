---
name: reconstruction-scope-gate
description: "Gate #0: authorization before recon capture"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: BUSL-1.1
platforms: [linux, macos]
metadata:
  hermes:
    tags: [reconstruction, security, gate, authorization, scope]
    divisions: [D0, D1, D8]
    related_skills: [evidence-normalizer, target-inventory]
---


# Reconstruction Scope Gate (Gate #0)

Gate masuk untuk **semua** pekerjaan terhadap target existing. Tidak ada crawl, screenshot, trace,
analisis binary, atau clone repo sebelum gate PASS.

## Kapan dipakai
- Ada permintaan menyentuh URL/aplikasi/repo/binari pihak lain, termasuk milik sendiri tapi di produksi.
- Ada permintaan "clone/replikasi/benchmark" aplikasi apa pun.
- Sebelum menjalankan Playwright/Crawlee/MobSF/JADX/Apktool/Ghidra.

## Prosedur
1. Buat workspace target: `python3 scripts/init_target.py <slug>`.
2. Isi `evidence/<slug>/authorization.yaml` dari `templates/authorization_manifest.yaml`.
   - Tentukan `mode`: **A** (eksternal, default) atau **B** (deep, hanya bila ada izin tertulis).
3. Jalankan gate: `python3 scripts/gate_check.py --target <slug>`.
4. Baca verdict: **PASS** lanjut; **FAIL** perbaiki manifest; **BLOCKED** berhenti dan tanya Owner.
5. Lampirkan verdict ke handoff (`reports/<slug>/gate0-verdict.json`).

## Aturan keras
- Mode B wajib `authorization_type: written_permission` + `license_or_permission_ref` terisi.
  Tidak ada izin tertulis => turunkan ke Mode A atau BLOCKED.
- `forbidden_actions` tidak boleh dihapus/dilonggarkan untuk "mempercepat" pekerjaan.
- Sandbox wajib: whole-process isolation, non-root, mount workspace saja, tanpa socket Docker host,
  tanpa kredensial host.
- `retention.redact_before_prompt: true` wajib — redaksi sebelum evidence masuk konteks LLM.

## Larangan (tanpa pengecualian)
Bypass authentication/authorization, CAPTCHA/anti-bot, paywall, rate limit, DRM/licensing, code-signing,
certificate pinning, secret/credential control; eksploitasi vulnerability untuk akses; brute-force endpoint;
ekstraksi source/backend/database privat; menyimpan cookie/token/PII.

## Output
- `reports/<slug>/gate0-verdict.json` (PASS/FAIL/BLOCKED + daftar alasan)
- Catatan scope: URL/repo/app yang boleh, akun test, data yang dilarang, route out-of-scope.

## Checklist sebelum menyerahkan ke divisi lain
- [ ] verdict PASS, bukan asumsi
- [ ] mode & izin eksplisit
- [ ] daftar out-of-scope tercatat
- [ ] sandbox & redaksi aktif
- [ ] tidak ada kredensial tersimpan di mana pun
