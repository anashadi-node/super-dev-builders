# Upgrade Report — Copy Cloning Super Dev Builders (V1) -> Super Dev Builders Ecosystem V2.2

Tanggal: 2026-10-04 WIB · Acuan: `docs/00_MASTER_BLUEPRINT_V2.2.html` · Owner: Mas Anas

## 1. Ringkasan
Upgrade dilakukan **non-destruktif**: repo V2.2 baru di `/home/anashadi/super-dev-builders`,
repo V1 tetap utuh di `/home/anashadi/copy-cloning-super-dev-builders`, backup terverifikasi di
`/home/anashadi/backups/sdb-upgrade-20261004_071800/` (dua arsip, `gzip -t` PASS).

## 2. Inventory BEFORE
| Aspek | V1 (sebelum) |
|---|---|
| Home | `~/copy-cloning-super-dev-builders` |
| File repo | 24 file; `agents/`, `workflows/`, `tests/`, `reconstruction/`, `verification/` KOSONG |
| Git | tanpa repo git (tanpa jejak audit) |
| Divisi | 7 profil `cc-*` (charter markdown saja) |
| Skill ekosistem | 0 custom skill (charter hanya naratif) |
| Gate | checklist manual (tidak deterministik, tidak bisa diuji) |
| Registry skill/tool | tidak ada |
| Permission / model routing | tidak ada |
| Tool ekosistem | `doctor.py`, `init_target.py` saja |
| Plugin/MCP | 0 untuk ekosistem |
| Host tools ada | git, node 26.7, npm 11.19, python 3.12 (sistem) + 3.14 (Hermes), docker 29.8, uv, pytest, playwright CLI, jq, adb |
| Host tools hilang | semgrep, codeql, trivy, syft, ruff, gh, jadx, apktool, ghidra |

## 3. Inventory AFTER
| Aspek | V2.2 (sesudah) |
|---|---|
| Home | `~/super-dev-builders` (git repo) |
| File repo | 92 file terstruktur |
| Divisi | 12 divisi terdefinisi -> 7 profil (independence Security/Audit vs Builder dijaga) |
| Skill ekosistem | **21 custom skill** |
| Gate | Gate #0 + Release Gate **deterministik** dengan exit code |
| Registry | `registry/skills.yaml` (21 custom + 18 sumber pihak ketiga ter-pin) + `registry/tools.yaml` |
| Matrix | permission, model-routing, risk class, token policy |
| Charter | `agents/*.yaml` (machine-readable, permission eksplisit, alias profil) |
| Test suite | 21 test pytest — SEMUA PASS |
| Gate self-test | PASS / FAIL / BLOCKED terbukti (exit 0/1/2) |
| Skill scan | SkillSpector v2.12.0: 20 bersih, 1 LOW (false positive ditriase); Skills Guard native: 4 DANGEROUS/7 CAUTION/7 SAFE dari 18 skill hub, 11 BLOCKED -> setelah approval #9/#9b: **14 hub skill, 0 DANGEROUS** |
| Tool deterministik | ruff 0.16.10 + semgrep 1.179.0 + trivy 0.75.0 terpasang (pin + checksum); scan repo: ruff 35->0, semgrep 0/344 rule, trivy 0 (tanpa manifest) |
| Pemasangan skill | 36 operasi ke 7 profil divisi |

## 4. Gap-analysis -> klasifikasi keputusan
| Kapabilitas | V1 | Keputusan | Tindakan |
|---|---|---|---|
| Gate otorisasi | markdown manual | **REPLACE** | `scripts/gate_check.py` + template manifest |
| Evidence schema | JSON tanpa taxonomy | **UPDATE** | + `status`/`confidence`/`redaction_status`, `evidence_lint.py` |
| Charter agent | markdown naratif | **UPDATE** | `docs/DIVISIONS.md` + `agents/*.yaml` |
| Gate #0 doc | markdown | **KEEP + UPDATE** | + whole-process isolation, redaksi sebelum LLM |
| Workflow SOP | 9 tahap | **UPDATE** | 16 tahap + risk class §10A |
| Custom skill | tidak ada | **ADD** | 21 skill (directive butir 8) |
| Skill pihak ketiga | tidak ada | **QUARANTINE / PENDING_APPROVAL** | registry + pipeline §6, belum dipasang |
| Tool keamanan | tidak ada | **ADD (pending approval)** | `bootstrap_tools.sh` + pin versi |
| Skill hub DANGEROUS (`inference-sh-cli`) | terpasang | **QUARANTINE (temuan)** | dilaporkan, keputusan removal = Owner |
| Profil divisi | 7 (`cc-*`) | **KEEP nama + UPDATE isi** | SOUL.md & profile.yaml ditulis ulang; alias `sdb-*` |
| Repo legacy | ada | **KEEP (arsip)** | tidak dihapus/ditimpa |

ADR-004: nama direktori profil dipertahankan (`cc-*`) karena `~/.hermes/state.db` & riwayat sesi
mereferensikannya; identitas ekosistem pindah ke SOUL.md + alias `sdb-*` (`hermes_profile` di `agents/*.yaml`).

## 5. Deliverable (blueprint §10 butir 13)
| Deliverable | Lokasi | Status |
|---|---|---|
| Architecture diagram | `docs/ARCHITECTURE.md` | DONE |
| Inventory before/after | `reports/inventory_before.json`, `reports/inventory_after.json` | DONE |
| Skill registry + sumber + pin | `registry/skills.yaml` | DONE |
| Permission matrix | `docs/PERMISSION_MATRIX.md` | DONE |
| Model-routing matrix | `docs/MODEL_ROUTING_MATRIX.md` | DONE |
| Workflow/gates | `docs/WORKFLOW_GATES.md` + `workflows/*.yaml` | DONE |
| Rollback plan | `docs/ROLLBACK_PLAN.md` | DONE |
| Security audit report | `reports/security-audit.md` | DONE |
| Token/resource estimate | `reports/token-estimate.md` | DONE |
| Daftar butuh approval | `reports/human-approval-required.md` | DONE |
| Installation plan | `docs/INSTALLATION_PLAN.md` | DONE |

## 6. Bukti verifikasi (perintah nyata)
```text
/usr/bin/python3 -m pytest tests -q            -> 21 passed
/usr/bin/python3 scripts/doctor.py             -> exit 0 (kapabilitas wajib OK)
/usr/bin/python3 scripts/registry_lint.py      -> PASS (21 custom, 7 profil)
gate_check.py template kosong                  -> FAIL   (exit 1)
gate_check.py manifest lengkap                 -> PASS   (exit 0)
gate_check.py mode B tanpa izin tertulis       -> BLOCKED (exit 2)
skillspector scan skills/ --recursive --no-llm -> 21 skill, 20 bersih, 1 LOW (FP ditriase)
hermes -p cc-builder skills list               -> 5 skill ekosistem enabled/visible
hermes skills audit                            -> 18 skill hub: 4 DANGEROUS, 7 CAUTION, 7 SAFE, 11 BLOCKED
hermes skills uninstall --yes inference-sh-cli -> dibuang; list=0, direktori hilang, audit tidak memindainya lagi
bash scripts/bootstrap_tools.sh --install ruff semgrep trivy --yes
                                               -> ruff 0.16.10, semgrep 1.179.0, trivy 0.75.0 (SHA256 OK)
ruff check scripts tests                       -> 35 temuan -> 0 setelah diperbaiki
semgrep scan --config p/default                -> 344 rule / 93 file -> 0 findings
trivy fs --scanners vuln,misconfig,secret      -> 0 hasil (repo belum punya manifest -> tidak ada yang diperiksa)
hermes security audit (OSV, venv Hermes)       -> 71 advisory / 136 komponen (di luar scope repo)
```
Artefak bukti: `reports/upgrade-evidence/`.

## 7. Known limitations (jujur)
1. ~~Belum ada target reconstruction pertama~~ **SELESAI 2026-10-04**: pipeline diuji end-to-end pada target `sdb-local-demo` (milik sendiri, Mode A) — Gate #0 PASS/BLOCKED/FAIL, capture nyata, redaksi, normalisasi, evidence lint PASS, fidelity 9 dimensi, release gate PASS. **2026-10-04 (target kedua, OPEN-SOURCE)**: pipeline diuji lagi pada `startbootstrap-agency` (MIT, commit ter-pin) — Gate #0 PASS, rebuild clean-room, fidelity 9 dimensi bercoverage, CodeQL JS + semgrep + trivy + SBOM, release gate PASS. Lihat `docs/PIPELINE_E2E_EVIDENCE.md` §5.
2. Semgrep/Trivy/ruff (approval #4) + Syft/CodeQL/Playwright (approval #2) sudah terpasang, semuanya pin + checksum. Hasil trivy saat ini
   **nihil karena tidak ada manifest dependency/IaC** di repo -> bukan bukti bebas kerentanan.
3. SkillSpector coverage **parsial (23.81%)** — bukan jaminan bebas temuan.
4. 21 skill baru diuji struktural + lint + scan, belum diuji lewat pemakaian nyata.
5. Kepatuhan permission divisi belum diuji runtime (masih kontrak + policy).
6. Hermes venv membawa 71 advisory (1 CRITICAL PyJWT) — di luar repo ini, butuh keputusan upgrade.

## 8. Next steps
1. ~~Pasang Semgrep/Trivy/ruff~~ **SELESAI** (2026-10-04, approval #4).
2. ~~Buang skill hub DANGEROUS `inference-sh-cli`~~ **SELESAI** (2026-10-04, approval #9; backup + verifikasi).
3. ~~Putuskan/buang skill hub DANGEROUS lain: `comfyui`, `huggingface-hub`, `reddit-reading`~~ **SELESAI** (approval #9b, 2026-10-04; audit ulang 0 DANGEROUS, denylist dibuat).
4. Pilih target pertama (milik sendiri/open-source) -> Gate #0 -> capture Mode A -> rebuild -> fidelity.
5. CodeQL dipakai ketat sesuai lisensi (hanya OSI-approved/akademik; bukan internal/CI). Syft bila SBOM diminta.
6. **Belum diuji**: target eksternal (web publik / APK / desktop), analisis mendalam Mode B, CodeQL pada kode internal (dilarang lisensi).
