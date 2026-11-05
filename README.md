# Super Dev Builders Ecosystem

Software-engineering ecosystem berbasis Hermes: merancang, membangun, menguji, mengaudit, mengamankan,
mendokumentasikan, dan men-deploy website / web app / mobile / desktop / backend / API / database /
AI-agent integration / platform enterprise — **termasuk Authorized Reverse Engineering & Reconstruction**.

Repo resmi: <https://github.com/anashadi-node/super-dev-builders> — **publik** (dicek 2026-11-05 lewat
`gh repo view`; sebelumnya README menyebut "privat/undangan", itu tidak akurat). Konsekuensinya:
tidak ada kredensial, kunci, data pelanggan, atau berkas profil browser yang boleh masuk repo —
gerbang higiene (`scripts/repo_hygiene.py`) menegakkan ini.

Acuan utama (sumber kebenaran) arsitektur ini: `docs/00_MASTER_BLUEPRINT_V2.2.html`
(Hermes AI Software Engineering Company — Super Dev Builders Ecosystem — Master Blueprint V2.2).
Semua keputusan di repo ini harus bisa ditelusuri balik ke blueprint tersebut.

## Prinsip #0 — Security, Safety & Privacy
Security/privacy adalah hal paling utama — di atas kecepatan dan kenyamanan. Semua target, repo,
link, dependency, skill, MCP, dan artefak capture diperlakukan **untrusted** sampai lolos gate.

## Cara kerja ekosistem (ringkas)
- **Agent = tanggung jawab.** Divisi dipisah hanya bila perlu independence, permission boundary,
  atau konteks berbeda. Divisi bersifat **lazy/on-demand** — tidak pernah di-spawn serentak.
- **Skill = SOP.** Pengetahuan dimuat hanya saat relevan (progressive disclosure).
- **Tool = bukti deterministik.** Compiler, test runner, linter, scanner, Git, Playwright.
- **Gate = keputusan.** PASS/FAIL berbasis evidence, bukan "feeling" LLM.

## Struktur
```text
platform/        kontrak produk: skema tenant/job/artifact, baseline higiene, manifest paket (Fase 1)
sdb_platform/    kode produk Python — control plane: tenant, kuota, job, artefak (Fase 2a)
docs/            blueprint, arsitektur, ADR, runbook, kebijakan, indeks dokumen (docs/INDEX.md)
registry/        skill registry + tool registry (sumber, revisi terpin, status)
skills/          sumber kanonik custom skill ekosistem ini (jumlah = registry/skills.yaml, kini 40; cek `make drift`) (dipasang ke profil, bukan disalin liar)
agents/          charter mesin-terbaca per divisi (permission, input/output, batas)
workflows/       definisi gate + tahap workflow (machine-readable)
templates/       manifest otorisasi, target manifest, ADR, laporan akhir, handover
scripts/         deterministik: doctor, inventory, init-target, install-skills, gate-check,
                 release-check, workflow-run, sdb (CLI satu pintu), evidence-lint, redact-network,
                 repo-hygiene (gerbang artefak)
evidence/        evidence mentah (wajib redacted)  -> per target  [transisi: keluar ke object store]
normalized/      evidence ternormalisasi -> per target             [transisi: keluar ke object store]
reconstruction/  hasil rebuild clean-room -> per target
verification/    hasil verifikasi visual/behavioral/a11y/security -> per target [transisi]
reports/         laporan gate, audit, upgrade, fidelity, handover
tests/           test untuk scripts/ (dijalankan sebelum commit)
```

> **Arah struktur (ADR-0002)**: kode, kontrak, dan dokumen tetap di git; **hasil pekerjaan** (capture, evidence,
> log, laporan generate) pindah ke object store per tenant. Repo tidak boleh tumbuh karena data pelanggan —
> dijaga oleh `make hygiene`. Peta lengkap: `docs/PETA_STRUKTUR.md`; indeks dokumen: `docs/INDEX.md`.

## Lisensi

SDB berlisensi **Business Source License 1.1** (`LICENSE`): bebas untuk penggunaan **non-produksi**; pemakaian
produksi untuk klien atau sebagai bagian layanan berbayar memerlukan perjanjian komersial. Setiap versi beralih
ke Apache-2.0 pada 2030-10-26. Komponen pihak ketiga punya lisensinya sendiri — lihat `THIRD_PARTY_NOTICES.md`
(perhatian: satu paket skill memakai CC-BY-SA-4.0 dan tidak boleh dilisensikan ulang sebagai BUSL).

Kontak lisensi/komersial: `lisensi [at] anantara-sakti [dot] id`.

## Mulai dari sini
Baru pertama kali? Ikuti **`docs/GETTING_STARTED.md`** — panduan Bahasa Indonesia dari nol
sampai bisa dipakai sendiri (pasang, verifikasi, buat target, Gate #0, workflow 16 tahap,
release gate, troubleshooting, copot pemasangan).

## Quickstart
```bash
./install.sh                                  # DRY-RUN pemasangan (skill + perintah `sdb`)
./install.sh --apply                          # baru benar-benar memasang (backup otomatis dulu)

sdb doctor                                    # kapabilitas host + drift skill (read-only)
sdb init nama-target                          # workspace per target (evidence/normalized/...)
sdb gate nama-target                          # Gate #0 -> PASS/FAIL/BLOCKED
sdb workflow nama-target                      # laporan 18 baris tahap: ada / MISSING
sdb release nama-target                        # release gate berbasis artefak
make check                                    # gerbang lokal wajib sebelum commit

# tanpa perintah `sdb` pun bisa:
python3 scripts/doctor.py                     # kapabilitas host (deterministik)
python3 scripts/gate_check.py <name>          # validasi authorization manifest -> PASS/FAIL/BLOCKED
python3 scripts/init_target.py <name>         # workspace per target (evidence/normalized/...)
python3 scripts/install_skills.py --profile sdb-builder
python3 -m pytest tests -q                    # test suite skrip
```

## Penjaga CI (kegagalan tidak boleh jadi latar belakang)
```bash
python3 scripts/ci_watch.py --status          # ringkasan 30 run terakhir
python3 scripts/ci_watch.py                   # laporkan kegagalan BARU saja
python3 scripts/ci_watch.py --dry-run         # periksa tanpa menulis state
```
Dijadwalkan tiap 3 jam oleh `sdb-ci-watch.timer` (unit di `ops/systemd/`). Aturan mainnya:
hanya kegagalan **baru** yang dikirim (state = memori, idempoten), dan bila `gh` tidak bisa
dipakai hasilnya **exit 2 "GAGAL MEMERIKSA"** — bukan "hijau". Kanal: Telegram
(`SDB_TG_BOT_TOKEN`/`SDB_TG_CHAT_ID`, fallback ke bot yang sudah ada) + catatan JSONL di
`~/.local/state/sdb/ci-watch/alerts.jsonl`, sehingga bukti tetap ada walau jaringan mati.

## Telegram operasional (`@super_dev_builders_bot`)
Tiga kanal, satu bot, khusus pemilik (`SDB_TG_CHAT_ID`; chat lain diabaikan diam-diam):

- **Laporan otomatis tiap 4 jam** — `sdb-report-4h.timer` menjalankan
  `scripts/sdb_report.py --send 4h` (00/04/08/12/16/20 WIB). Deterministik, tanpa LLM,
  memuat proyek + progres, layanan, timer, deck, `control.db`, host, dan delta sejak
  laporan sebelumnya.
- **Tanya-jawab kapan saja** — `/eco`, `/projects`, `/ask <pertanyaan>`. `/ask`
  menyuntikkan laporan nyata sebagai DATA ke agen dengan toolset minimal
  (`terminal,file,skills`; tanpa web/browser/delegasi) sehingga jawaban ber-grounding.
- **Perintah build** — `/build <deskripsi>` → `SPEC.md`/`PLAN.md`/`QUESTIONS.md` →
  `/approve <id>` → implementasi bertahap (maks. 3 ronde) dengan tes nyata, `VERIFY.md`,
  `README.md`, `GAPS.md`. Worker: `sdb-build-worker.service`, sandbox `~/sdb-builds/<id>-<slug>/`.

Detail perintah, alur, konfigurasi, dan batas: [`docs/TELEGRAM_SDB.md`](docs/TELEGRAM_SDB.md).

## Aturan yang tidak bisa dinegosiasikan
1. Tidak ada deep scan tanpa `authorization.yaml` berstatus PASS (Gate #0).
2. Tidak ada bypass auth / CAPTCHA / anti-bot / paywall / DRM / licensing / pinning / access control.
3. Tidak ada credential, session token, cookie, atau PII di evidence maupun konteks LLM.
4. Tidak ada klaim "selesai/lulus" tanpa fresh build/test/scan evidence.
5. Security/Audit tidak punya hak deploy produksi. Deploy produksi = approval manusia.
6. Skill/MCP pihak ketiga: source check -> pin revisi -> scanner -> review manual -> sandbox -> approval.
7. Release = residual risk diketahui, gate lulus, risk owner manusia menerima sisa risiko.
