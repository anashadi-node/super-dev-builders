# Model Routing Matrix — hemat token, kuat di tempat yang tepat

Sumber: blueprint §8 (token & resource policy, butir 7: cheap model untuk rutin, strong model untuk arsitektur/debug/security/final audit).

## Prinsip
1. **Sequential by default.** Maksimum 1-2 spesialis aktif; paralel hanya untuk task independen nyata.
2. **Progressive disclosure.** System prompt hanya memuat nama+deskripsi skill; isi SKILL.md dimuat saat terpicu.
3. **Artifact handoff.** Kirim requirement/ADR/diff/SARIF, bukan transkrip.
4. **Tool before model.** Fakta deterministik (compiler/linter/test/scanner) dijawab tool, bukan LLM.

## Matriks kelas pekerjaan -> kelas model

| Divisi | Kelas pekerjaan | Kelas model | Alasan |
|---|---|---|---|
| D0 Orchestrator | intake, routing, status, ringkasan | cheap/fast | volume tinggi, penalaran rendah |
| D2 Research | retrieval + ringkas dokumen | cheap/mid | output pendek, verifikasi ke sumber |
| D3 Architecture | ADR, trade-off, keputusan stack | **strong** | salah di sini mahal dan menular ke seluruh proyek |
| D4/D5 Engineering | implementasi terarah dari spec + test | mid (strong untuk desain komponen) | mayoritas transformasi; naik kelas saat desain/algoritma sulit |
| D6 Code Review | diff-first review | strong untuk critical/high-risk; mid untuk rutin | butuh penalaran lintas file |
| D7 QA | tulis jalankan test, triase kegagalan | mid | deterministik, sebagian besar mekanis |
| D8 Security | triase temuan, exploitability | **strong** | false negative mahal |
| D9 Audit/Assurance | architecture drift, verdict rilis | **strong** | verdict sistemik |
| D10 DevOps | build/deploy/rollback | mid | prosedural, wajib deterministik |
| D11 Docs | README/runbook/handover | cheap/mid | volume tulis, risiko rendah |
| D1 Recon | capture + normalisasi evidence | mid (strong untuk klasifikasi FACT/INFERRED) | kualitas evidence menentukan segalanya |

## Aturan biaya
- Jangan pakai model kuat untuk transformasi mekanis berulang; jangan pakai model lemah untuk verdict keamanan/arsitektur.
- Naikkan kelas model hanya bila ada bukti kegagalan (bukan preventif tanpa alasan).
- Estimasi konsumsi: lihat `reports/token-estimate.md`.
