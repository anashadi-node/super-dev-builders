---
name: architecture-compliance-audit
description: "Detect architecture drift vs ADRs and specs"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [audit, architecture, compliance, drift, independence]
    divisions: [D9]
    related_skills: [engineering-release-audit, architecture-decision-record, architecture-docs]
---


# Architecture Compliance Audit

Menjawab satu pertanyaan: **apakah kode yang ada benar-benar sesuai arsitektur yang disepakati?**
Dijalankan independen dari divisi yang membangun kode.

## Prosedur
1. Kumpulkan sumber kebenaran: ADR, architecture.md, technology governance, kontrak API, batas mock/backend.
2. Petakan repository nyata: struktur modul, dependency graf, arah dependensi, boundary layer, titik integrasi.
3. Bandingkan, temukan penyimpangan:
   - dependency yang tidak ada di ADR (framework drift),
   - boundary dilanggar (UI memanggil DB langsung, business logic di handler HTTP),
   - duplikasi konsep/implementasi paralel,
   - dead code / fitur tidak terdokumentasi,
   - batas mock bocor ke jalur produksi.
4. Tinjau maintainability & technical debt: kompleksitas, fungsi panjang, coupling, mutasi global, error handling.
5. Nilai kesehatan dependency: usang, tidak dirawat, lisensi bermasalah, advisory keamanan terbuka.
6. Verdict per temuan: `compliant | drift(minor) | drift(material) | violation`, plus bukti (path:line).

## Aturan
- Setiap temuan wajib punya bukti lokasi dan dampak; dilarang verdict berbasis "rasa".
- Tidak mengubah kode: output adalah laporan (read-only).
- Bila ADR sendiri usang/kontradiktif, itu temuan juga (ADR perlu diperbarui).

## Output
- `reports/<proyek>/architecture-compliance.md`: tabel temuan, severity, dampak, rekomendasi, bukti.
- Ringkasan: jumlah drift material/violation + area paling berisiko.
