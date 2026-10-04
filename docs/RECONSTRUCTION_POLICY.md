# Reconstruction Policy — Authorized Reverse Engineering

Sumber: blueprint §4 (termasuk hard boundary, dua mode, workflow, network policy, taxonomy).

## 1. Hard boundary (tidak bisa dilanggar, dalam kondisi apa pun)
Dilarang: bypass authentication/authorization, CAPTCHA/anti-bot/access control, paywall, rate limit,
DRM/licensing, code-signing, certificate pinning, secret/credential control, atau mengeksploitasi
vulnerability untuk memperoleh akses. Dilarang mengambil private source/data/API tanpa otorisasi.

Jika target butuh akses lebih dalam: Owner **harus** menyediakan source/binary/test account/staging/credential
dan scope otorisasi eksplisit -> baru Mode B boleh jalan.

## 2. Dua mode
| Mode | Input | Boleh | Tidak boleh |
|---|---|---|---|
| **A — External Reconstruction** (default) | URL publik / aplikasi yang dapat diamati sah | public crawl, browser automation, DOM/layout/assets, screenshot, responsive state, perilaku network publik, public API contract, sinyal teknologi, aksesibilitas/performance, observasi user-flow | bypass login/access control/anti-bot, pencurian credential, discovery endpoint privat via eksploit, pencurian source |
| **B — Owner-Authorized Deep** (khusus) | source/repo, APK/IPA/EXE/binary, test account, staging, API docs, DB schema, environment milik/berwenang audit | static/dynamic analysis, analisis package/dependency, observasi runtime/network, arsitektur source, API/schema berizin, inspeksi binary, review config/CI-CD sesuai scope | keluar dari target/scope, menyerang dependency/service pihak ketiga, mengambil data nyata yang tidak diperlukan |

Mode B wajib: `authorization_type: written_permission` + `license_or_permission_ref` terisi di manifest,
dan tool berat (MobSF/JADX/Apktool/Ghidra) dijalankan terisolasi pada artefak yang diotorisasi saja.

## 3. Network observation policy
Browser DevTools/Playwright trace = pilihan pertama. Proxy/interception hanya di Mode B pada environment
yang Owner otorisasi, dan **tidak** untuk mematahkan kontrol TLS/certificate pihak ketiga.
Dilarang menyimpan authorization header, cookie, token, atau PII ke artefak reconstruction —
redaksi wajib **sebelum** evidence masuk konteks LLM.

## 4. Urutan kerja (reconstruction)
```text
AUTHORIZATION & SCOPE GATE -> TARGET INVENTORY -> SAFE DISCOVERY/CRAWL
 -> UI+UX+NAVIGATION+STATE MAP -> OBSERVED NETWORK/API/DATA CONTRACT
 -> TECHNOLOGY+ASSET+DEPENDENCY PROFILE -> (Mode B) AUTHORIZED STATIC/DYNAMIC ANALYSIS
 -> EVIDENCE NORMALIZATION -> FACT/INFERRED/UNKNOWN CLASSIFICATION
 -> FEATURE MATRIX + RECONSTRUCTION PRD -> ARCHITECTURE & PLAN
 -> FRONTEND/BACKEND REBUILD -> VISUAL+FUNCTIONAL+A11Y+PERFORMANCE DIFF
 -> QA -> SECURITY -> ASSURANCE -> RECONSTRUCTION FIDELITY REPORT
```

## 5. Aturan alat capture
- Playwright = mesin observasi utama. Crawlee = crawling terstruktur; **anti-bot evasion/proxy rotation dilarang**
  untuk menghindari pembatas target; hormati scope, robots/policy relevan, dan rate limit.
- Lighthouse/axe-core = evidence kualitas; bukan alat reverse-engineering backend.
- BackstopJS: status maintenance harus dicek; prioritaskan Playwright-native screenshot assertion untuk longevity.

## 6. Larangan output
- Tidak ada kode/source pihak ketiga yang disalin ke `reconstruction/` tanpa lisensi/izin yang jelas.
- Tidak ada artefak target (cookie, token, data personal) yang tersimpan.
- Tidak ada klaim "identik" — yang dilaporkan adalah fidelity per dimensi + coverage.
