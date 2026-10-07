# Super Dev Builders Ecosystem

Software-engineering ecosystem berbasis Hermes: merancang, membangun, menguji, mengaudit, mengamankan,
mendokumentasikan, dan men-deploy website / web app / mobile / desktop / backend / API / database /
AI-agent integration / platform enterprise — **termasuk Authorized Reverse Engineering & Reconstruction**.

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
docs/            blueprint + architecture, divisi, workflow/gate, policy, rollback
registry/        skill registry + tool registry (sumber, revisi terpin, status)
skills/          sumber kanonik custom skill ekosistem ini (jumlah = registry/skills.yaml, kini 37; cek `make drift`) (dipasang ke profil, bukan disalin liar)
agents/          charter mesin-terbaca per divisi (permission, input/output, batas)
workflows/       definisi gate + tahap workflow (machine-readable)
templates/       manifest otorisasi, target manifest, ADR, laporan akhir, handover
scripts/         deterministik: doctor, inventory, init-target, install-skills, gate-check,
                 release-check, workflow-run, sdb (CLI satu pintu), evidence-lint, redact-network
evidence/        evidence mentah (wajib redacted)  -> per target
normalized/      evidence ternormalisasi -> per target
reconstruction/  hasil rebuild clean-room -> per target
verification/    hasil verifikasi visual/behavioral/a11y/security -> per target
reports/         laporan gate, audit, upgrade, fidelity, handover
tests/           test untuk scripts/ (dijalankan sebelum commit)
```

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

## Aturan yang tidak bisa dinegosiasikan
1. Tidak ada deep scan tanpa `authorization.yaml` berstatus PASS (Gate #0).
2. Tidak ada bypass auth / CAPTCHA / anti-bot / paywall / DRM / licensing / pinning / access control.
3. Tidak ada credential, session token, cookie, atau PII di evidence maupun konteks LLM.
4. Tidak ada klaim "selesai/lulus" tanpa fresh build/test/scan evidence.
5. Security/Audit tidak punya hak deploy produksi. Deploy produksi = approval manusia.
6. Skill/MCP pihak ketiga: source check -> pin revisi -> scanner -> review manual -> sandbox -> approval.
7. Release = residual risk diketahui, gate lulus, risk owner manusia menerima sisa risiko.
