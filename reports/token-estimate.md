# Token & Resource Estimate — V2.2

Diukur dari artefak nyata repo ini (2026-10-04), bukan perkiraan naratif.

## 1. Biaya progressive disclosure (deskripsi skill)
- 21 custom skill: total deskripsi **1609 karakter** ~ **402 token** bila SEMUA dipasang di satu profil.
- Per profil divisi (hanya deskripsi yang masuk system prompt):

| Profil (divisi) | Skill terpasang | Deskripsi (char) | ~token |
|---|---|---|---|
| `sdb-orchestrator` | 1 | 72 | ~18 |
| `sdb-recon` | 8 | 613 | ~153 |
| `sdb-architect` | 6 | 468 | ~117 |
| `sdb-builder` | 5 | 377 | ~94 |
| `sdb-reviewer` | 4 | 305 | ~76 |
| `sdb-security` | 6 | 449 | ~112 |
| `sdb-devops` | 6 | 470 | ~118 |

Kesimpulan: memasang seluruh 21 di satu profil adalah skenario terburuk; model divisi memotong overhead
secara signifikan. **Keputusan**: 21 skill TIDAK dipasang ke profil `default` untuk menjaga biaya per-turn;
bila diinginkan: `/usr/bin/python3 scripts/install_skills.py --main` (rollback `--uninstall --main`).

## 2. Biaya tool (terukur)
| Aktivitas | Biaya |
|---|---|
| Test suite (21 test) | ~0.2 detik per run |
| gate_check / evidence_lint / registry_lint | < 0.5 detik |
| SkillSpector 21 skill (`--no-llm`) | ~1 menit (tanpa LLM = murah) |
| `hermes skills audit` | ~30 detik |
| `hermes security audit` (OSV, 136 komponen) | ~2-4 menit (jaringan) |
| Penulisan upgrade ini (~92 file) | berat sekali (event one-off, bukan biaya rutin) |

## 3. Aturan konsumsi mengikat (blueprint §8)
1. Sequential by default; maksimum 1-2 spesialis aktif.
2. Progressive disclosure: SKILL.md dimuat hanya saat terpicu.
3. Artifact handoff (requirement/ADR/diff/SARIF), bukan transkrip.
4. Tool sebelum model untuk fakta deterministik.
5. Bounded loop 2-3 siklus lalu eskalasi.
6. Model murah untuk rutin; kuat untuk arsitektur, debugging kompleks, triase security, audit final.
7. Tanpa keluarga skill duplikat.

## 4. Resource PC
- Divisi lazy/on-demand; jangan spawn bersamaan.
- Tool berat dilarang di jalur default: CodeQL, Ghidra, MobSF, emulator mobile.
- Capture: batasi viewport/route/retry; artefak ke disk, bukan ke konteks.
- Scan cepat harian (Semgrep/Trivy); CodeQL hanya milestone/release.
- Disk: 128 GB bebas dari 468 GB (72% terpakai) + kebijakan retensi 30 hari (di manifest otorisasi).

## 5. Estimasi satu siklus reconstruction
| Tahap | Beban dominan | Kelas model |
|---|---|---|
| Gate #0 + intake | tool + dokumen | murah |
| Capture + normalisasi | browser (tool berat) + LLM menengah | menengah |
| Spec + ADR | penalaran arsitektur | kuat |
| Rebuild | implementasi + test | menengah |
| Review/QA | diff + test | menengah |
| Security + audit | triase + verdict | kuat |
| Deploy + handover | prosedural + tulis | murah-menengah |
