---
name: technology-selection
description: "Use when picking a stack or dependency. Enforces technology governance tiers."
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [architecture, stack, dependency, governance, drift]
    divisions: [D3, D5]
    related_skills: [architecture-decision-record, api-contract]
---


# Technology Selection

Menerapkan Technology Governance Matrix saat memilih stack, library, atau tool. Tujuan: mencegah framework drift.

## Prosedur
1. Tentukan requirement keras: platform target, performa, tim yang memelihara, ekosistem, lisensi, umur dukungan.
2. Cek tier di `docs/TECHNOLOGY_GOVERNANCE.md`: Core / Platform / Specialized. Stack di luar default wajib alasan tertulis.
3. Untuk tiap kandidat: lisensi (kompatibel?), maintenance (rilis terakhir, isu terbuka), ukuran dependency,
   permukaan keamanan, biaya operasional.
4. Pilih dengan kriteria eksplisit (bukan preferensi). Catat sebagai ADR.
5. Tambahkan dependency ke manifest + catat di registry (`registry/tools.yaml` untuk tool, manifest proyek untuk library).

## Aturan
- Default dulu: Web TypeScript+React/Next.js, backend TS/Node (Python untuk AI), DB PostgreSQL/SQLite,
  mobile Flutter, desktop Tauri/Electron, DevOps Docker+Bash/YAML/Terraform.
- Native Kotlin/Swift/C# hanya bila requirement platform/hardware/performance/security/UX membenarkan.
- Dilarang menambah dependency untuk fungsi yang sudah ada di stdlib/platform.
- Setiap dependency baru lewat review supply-chain (D8) sebelum dipakai produksi.

## Output
- Bagian "Technology Selection" pada ADR + daftar dependency final.
