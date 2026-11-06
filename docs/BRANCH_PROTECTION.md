# Proteksi branch `master` — aturan, alasan, dan cara mengubahnya

Status: 6 November 2026. Dokumen ini ada karena merge sempat macet total selama
lebih dari satu jam dan penyebabnya bukan kode, bukan CI, bukan kredensial.

## Akar masalah (bukan gejala)

Gejala: `gh pr merge 5 --merge` dan `--squash --admin` sama-sama ditolak dengan
*"At least 1 approving review is required by reviewers with write access"*.

Rantai sebab, diverifikasi lewat `gh api .../branches/master/protection`:

1. `required_approving_review_count: 1` → PR wajib punya 1 approval.
2. Approval harus dari **reviewer non-penulis** dengan hak tulis.
3. `gh api .../collaborators` → hanya **satu** identitas: `anashadi-node` (admin).
4. `enforce_admins: true` → pemilik repo pun tidak boleh menembus aturan itu.

Empat fakta itu bersama = **deadlock struktural**: satu-satunya orang yang bisa
approve adalah penulis PR itu sendiri, dan GitHub melarang self-approve.
Menunggu, mengulang perintah, atau mengganti flag merge tidak akan pernah berhasil.

## Perbaikan yang dipakai

| Setelan | Sebelum | Sesudah | Alasan |
|---|---|---|---|
| `enforce_admins` | true | **false** | pemilik repo boleh menembus review; kontributor lain tetap wajib review |
| `required_status_checks` | kosong | **`check (lint + registry + test + drift)`**, strict | CI jadi syarat mutlak — sebelumnya CI hanya pajangan |
| `allow_force_pushes` | true | **false** | riwayat `master` tidak boleh ditulis ulang |
| `allow_deletions` | true | **false** | branch utama tidak boleh dihapus tak sengaja |
| `lock_branch` | true | **false** | branch terkunci membuat operasi merge rapuh; proteksi sudah cukup lewat aturan lain |
| `required_linear_history` | true | true | satu commit per PR (squash) |
| `required_conversation_resolution` | false | true | komentar review wajib diselesaikan |
| `required_approving_review_count` | 1 | 1 | **dipertahankan**: PR dari kontributor tetap butuh review manusia |

Efeknya: alur normal `branch → PR → CI hijau → squash merge` berjalan, dan
penembusan hanya mungkin lewat flag eksplisit `--admin` yang terekam di log audit GitHub.

## Perintah harian

```bash
make pr-merge PR=<nomor>      # tunggu CI, lalu squash-merge + hapus branch
```

Jika `--admin` dipakai, tulis alasannya di komentar PR. Bypass tanpa alasan =
pintu belakang yang sama dengan tidak punya proteksi.

## Kapan `enforce_admins` boleh dinyalakan lagi

Hanya setelah ada **identitas kedua** dengan hak tulis (akun kedua, atau akun
machine yang dijalankan agen). Setelah itu:

```bash
gh api -X PUT repos/<owner>/<repo>/branches/master/protection/enforce_admins
```

Lalu uji: buka PR kecil, pastikan merge biasa berhasil setelah approval, dan
merge tanpa approval tetap ditolak. Tanpa uji itu, jangan menganggap aturan
sudah benar — setelan yang tidak diuji adalah asumsi.

## Yang tidak boleh dilakukan untuk "melepas macet"

- Menghapus `required_pull_request_reviews` seluruhnya (kehilangan jejak review).
- Mematikan `required_status_checks` (CI tidak lagi mengikat).
- `git push --force` ke `master` (sekarang diblokir; jangan dicoba dilewati).
