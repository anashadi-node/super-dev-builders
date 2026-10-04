# Technology & Language Governance

Sumber: blueprint §3. Architect memilih stack; developer **tidak** bebas mengganti framework demi kenyamanan model.

| Tier | Teknologi | Penggunaan |
|---|---|---|
| Core | TypeScript, JavaScript, Python, SQL, HTML/CSS, Bash | web, backend, API, AI/automation, database, scripting |
| Platform | Kotlin, Swift, Dart/Flutter, C#/.NET | Android native, Apple native, cross-platform mobile, Windows |
| Specialized | Go, Rust, Java, C/C++, PowerShell | high performance, systems, enterprise JVM, native/system integration |

## Default stack
- Web: TypeScript + React/Next.js
- Backend: TypeScript/Node.js; Python untuk AI/automation
- Database: PostgreSQL/SQLite
- Mobile: Flutter sebagai default cross-platform
- Desktop: Tauri atau Electron sesuai requirement
- DevOps: Docker + Bash/YAML; Terraform bila perlu

## Aturan keputusan
1. Native Kotlin/Swift/C# hanya bila requirement platform, hardware/API OS, performance, security, atau UX membenarkannya —
   bukan untuk terlihat "enterprise".
2. Pergantian stack/framework wajib ADR (`skills/architecture-decision-record`).
3. Penambahan dependency wajib lolos review supply-chain dan tercatat di registry.
4. Untuk reconstruction: pilih stack baru yang bersih berdasarkan spec/evidence — **jangan** memaksa menyalin
   implementasi internal target, kecuali Owner memang memberikan source yang boleh dimodifikasi.

## Tool deterministik (kanonik)
| Kebutuhan | Tool | Status di host |
|---|---|---|
| Test runner | pytest (Python), Playwright Test (web) | pytest ada; Playwright CLI ada |
| Lint/format Python | Ruff | **terpasang 0.16.10** (approval #4) |
| SAST cepat | Semgrep | **terpasang 1.179.0** (approval #4) |
| SAST mendalam | CodeQL | **terpasang 2.27.1** (approval #2) — ⚠️ LISENSI: hanya codebase OSI-approved/riset akademik, **dilarang** untuk kode proprietary internal & CI/CD |
| Dependency/container/IaC | Trivy | **terpasang 0.75.0** (approval #4) |
| SBOM | Syft | **terpasang 1.54.0** (approval #2); "No packages discovered" bila tanpa manifest ≠ bebas kerentanan |
| Browser observasi | Playwright | **terpasang 1.63.0** + Chromium (approval #2); capture engine nyata (`scripts/capture_web.py`) |
| Accessibility | axe-core | belum (npm local) |
| Performance | Lighthouse | belum (npm local) |
| Git/GitHub | git / gh CLI | git ada; `gh` belum terpasang |
Detail dan pin versi: `registry/tools.yaml`.
