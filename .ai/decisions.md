# Architecture Decisions — Super Dev Builders Ecosystem

## ADR-001 — Blueprint V2.2 adalah acuan utama
`docs/00_MASTER_BLUEPRINT_V2.2.html` = sumber kebenaran arsitektur. Perubahan menyimpang wajib ADR baru.

## ADR-002 — Baseline Hermes-native, Superpowers sebagai metodologi
Workflow Hermes-native (skills + kanban + cron + tools) = control plane. Superpowers hanya metodologi/referensi;
plugin hanya dipasang bila Skills Guard PASS pada versi Hermes aktual dan hooks/scripts direview.
Dilarang bypass `dangerous verdict`.

## ADR-003 — Repo baru + legacy diarsipkan (bukan ditimpa)
Upgrade dilakukan di `/home/anashadi/super-dev-builders`. Repo V1 tidak dihapus/ditimpa, hanya diarsipkan + backup tar.
Alasan: blueprint §10 melarang overwrite konfigurasi/skill yang masih diperlukan; rollback harus mungkin.

## ADR-004 — Divisi = charter + profil sedikit (7), bukan 12 profil
Blueprint §1: "jangan membuat agent baru jika masalah dapat diselesaikan dengan skill atau tool".
12 divisi dipetakan ke 7 profil (permission boundary berbeda). Divisi lain = mode + skill bundle, lazy load.
Security/Audit dipisah dari Builder (independence), DevOps satu-satunya pemegang hak deploy (dengan approval manusia).

## ADR-005 — Skill kanonik di repo, dipasang ke profil via script
Custom skill (jumlah: registry/skills.yaml) hidup di `skills/` repo ini sebagai sumber tunggal; `scripts/install_skills.py` memasangnya
ke profil sesuai matriks divisi. Menghindari duplikasi liar dan memudahkan rollback/uninstall.

## ADR-006 — Evidence taxonomy anti-halusinasi
Setiap temuan wajib berstatus FACT/OBSERVED, INFERRED(+confidence 0-100), UNKNOWN, atau OUT OF SCOPE.
Tidak ada angka fidelity tunggal; fidelity dilaporkan per dimensi + coverage (blueprint §4.7).

## ADR-007 — Gate #0 sebagai tool deterministik
`scripts/gate_check.py` memvalidasi authorization manifest dan menjadi syarat mutlak sebelum capture/analisis
mendalam. PASS/FAIL/BLOCKED harus bisa direproduksi, bukan opini LLM.

## ADR-008 — Quarantine default untuk pihak ketiga
Semua skill/MCP/tool eksternal masuk registry dengan status QUARANTINE atau pending-approval sampai:
source verified -> pinned revision -> scanner PASS -> manual review -> sandbox test -> approval manusia.
