# Rollback Plan — Upgrade V1 -> V2.2

Tujuan: setiap perubahan upgrade dapat dibatalkan tanpa kehilangan konfigurasi/skill yang masih dipakai
(blueprint §10: jangan overwrite/menghapus konfigurasi atau skill yang masih diperlukan).

## 0. Titik aman (backup) — SUDAH DIBUAT
| Artefak | Lokasi | Isi |
|---|---|---|
| Backup upgrade | `/home/anashadi/backups/sdb-upgrade-20261004_071800/` | `legacy-project-copy-cloning-super-dev-builders.tar.gz` (repo V1), `profile-configs.tar.gz` (SOUL.md + profile.yaml + config.yaml 7 profil cc-*) |
| Repo V1 asli | `/home/anashadi/copy-cloning-super-dev-builders/` | **tidak diubah/dihapus** |
Integritas: `gzip -t` PASS untuk kedua arsip.

## 1. Yang berubah (ringkas)
| # | Perubahan | Reversibel? | Cara balik |
|---|---|---|---|
| 1 | Repo baru `/home/anashadi/super-dev-builders` | ya | `rm -rf` repo baru (tidak menyentuh apa pun yang lain) |
| 2 | Identitas 7 profil diperbarui: SOUL.md + profile.yaml ditulis ulang. **Nama direktori `cc-*` DIPERTAHANKAN** (rename fisik DITUNDA — `~/.hermes/state.db` & riwayat sesi mereferensikan nama lama). Alias logis `sdb-*` dipetakan di `agents/*.yaml` (`hermes_profile`) | ya | ekstrak `profile-configs.tar.gz` lalu timpa SOUL.md/profile.yaml (lihat §3) |
| 3 | SOUL.md + profile.yaml 7 profil ditulis ulang | ya | ekstrak `profile-configs.tar.gz` dan timpa |
| 4 | 21 custom skill dipasang ke `~/.hermes/skills/` dan/atau profil | ya | `python3 scripts/install_skills.py --uninstall --profile <p>` |
| 5 | (belum) tool security baru (Semgrep/Trivy/Syft/Ruff) | ya | `uv tool uninstall <tool>` / hapus binary user-local |

## 2. Peta alias divisi -> direktori profil Hermes
| Divisi id (logis) | Direktori profil aktual | Peran | Rename fisik? |
|---|---|---|---|
| `sdb-orchestrator` | `cc-orchestrator` | D0 + D2 | tidak (ditunda) |
| `sdb-recon` | `cc-capture-forensics` | D1 | tidak (ditunda) |
| `sdb-architect` | `cc-architect` | D3 + D2 | tidak (ditunda) |
| `sdb-builder` | `cc-builder` | D4 + D5 | tidak (ditunda) |
| `sdb-reviewer` | `cc-reviewer-qa` | D6 + D7 | tidak (ditunda) |
| `sdb-security` | `cc-security-governor` | D8 + D9 | tidak (ditunda) |
| `sdb-devops` | `cc-devops-docs` | D10 + D11 | tidak (ditunda) |

`scripts/install_skills.py` menerima **kedua bentuk** nama (logis atau direktori) lewat resolusi alias dari `agents/*.yaml`.

### 2b. (Opsional) rename fisik di masa depan — hanya bila Owner memutuskan
```bash
hermes pause
for pair in "cc-orchestrator sdb-orchestrator" "cc-capture-forensics sdb-recon" "cc-architect sdb-architect" \
            "cc-builder sdb-builder" "cc-reviewer-qa sdb-reviewer" "cc-security-governor sdb-security" \
            "cc-devops-docs sdb-devops"; do
  set -- $pair; mv "$HOME/.hermes/profiles/$1" "$HOME/.hermes/profiles/$2"; done
# lalu perbarui field hermes_profile di agents/*.yaml dan verifikasi `hermes doctor`
hermes resume
```
Prasyarat: backup `~/.hermes/state.db` + verifikasi bahwa tidak ada cron/kanban yang menugaskan profil lama.

## 3. Prosedur rollback penuh (bila upgrade dinilai merugikan)
```bash
# 1) Stop pekerjaan
hermes pause

# 2) Kembalikan konfigurasi profil (nama direktori tidak berubah -> cukup timpa SOUL.md/profile.yaml)
tar xzf /home/anashadi/backups/sdb-upgrade-20261004_071800/profile-configs.tar.gz -C /tmp/
for p in cc-orchestrator cc-capture-forensics cc-architect cc-builder cc-reviewer-qa cc-security-governor cc-devops-docs; do
  cp "/tmp/profile-configs/$p/SOUL.md"     "$HOME/.hermes/profiles/$p/SOUL.md"
  cp "/tmp/profile-configs/$p/profile.yaml" "$HOME/.hermes/profiles/$p/profile.yaml"
done

# 3) Hapus skill ekosistem baru dari profil
python3 /home/anashadi/super-dev-builders/scripts/install_skills.py --uninstall --all

# 4) (opsional) kembalikan repo V1 sebagai working dir
ls /home/anashadi/copy-cloning-super-dev-builders   # masih utuh
hermes resume
```
Catatan: rollback tidak menghapus backup; jalankan `gzip -t` sebelum ekstraksi untuk memverifikasi arsip.

## 4. Kriteria kapan rollback dipertimbangkan
- Ada regresi pada pekerjaan Anantara Sakti (profil trading) akibat perubahan ini — (tidak terjadi: tidak ada
  profil trading yang disentuh; diverifikasi tidak ada referensi `cc-*` di `config.yaml`/`~/.hermes/cron/jobs.json`/kanban).
- Skill/ekosistem baru menyebabkan kebocoran token atau kegagalan gate yang tidak bisa diperbaiki cepat.
- Owner memutuskan struktur V1 lebih sesuai.
