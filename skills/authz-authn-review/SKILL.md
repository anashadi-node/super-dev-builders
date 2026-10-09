---
name: authz-authn-review
description: "Review authentication and authorization code"
version: 1.0.0
author: Super Dev Builders Ecosystem
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [auth, authz, authn, session, rbac, security]
    divisions: [D5, D8]
    related_skills: [api-contract, engineering-release-audit]
---


# AuthN / AuthZ Review

Checklist wajib untuk fitur identitas. Auth adalah kelas risiko HIGH: tidak ada perubahan tanpa review D8.

## Authentication
- [ ] Password: hashing adaptif (argon2id/bcrypt/scrypt), bukan SHA tunggal; tanpa batas panjang artifisial.
- [ ] Session/token: rotasi saat login & privilege change; expiry wajar; revocation memungkinkan; cookie
      `HttpOnly` + `Secure` + `SameSite`; token disimpan aman, tidak di localStorage bila bisa dihindari.
- [ ] MFA/step-up untuk operasi sensitif bila ada; recovery flow tidak boleh melemahkan faktor utama.
- [ ] Rate limit + lockout progresif pada login/reset; respons tidak membocorkan keberadaan akun.
- [ ] Reset password: token sekali pakai, kedaluwarsa pendek, tidak mengirim password via email.

## Authorization
- [ ] Cek otorisasi di **server**, per resource + per aksi (bukan hanya di UI).
- [ ] Tolak default (deny by default); allowlist peran/scope, bukan blocklist.
- [ ] Cegah IDOR/BOLA: kepemilikan objek diverifikasi setiap request.
- [ ] Privilege escalation: perubahan peran diaudit; tidak ada jalur naik peran via parameter klien.
- [ ] Pemisahan peran (admin/user/service) dengan scope minimum.

## Prosedur review
1. Petakan alur data dari input -> pemeriksaan -> akses resource (data flow, bukan asumsi).
2. Tulis bukti per temuan: endpoint/baris kode, kondisi, dampak, tingkat keyakinan.
3. Tandai temuan dengan exploitability; hanya temuan yang bisa dieksploitasi masuk kritikal.

## Larangan
- Tidak ada bypass auth untuk "mempermudah testing" di kode produksi.
- Tidak ada mock auth yang bisa aktif di produksi tanpa flag yang jelas dan terkunci.
- Tidak ada penyimpanan kredensial PII di prompt/artifact.
