# Security & Supply Chain Policy

Sumber: blueprint §6 (kebijakan skills & MCP), §1 (security boundary rule), §9 (prioritas instalasi).

## 1. Trust hierarchy
```text
Hermes builtin/official  >  verified upstream vendor/security org  >  custom audited  >  community
```
Skill pihak ketiga **tidak pernah** otomatis dianggap production-approved walau populer atau open-source.

## 2. Pipeline wajib untuk setiap SKILL / MCP baru
```text
NAMA/SKILL BARU
  -> SOURCE TRUST CHECK (official/vendor > security org > community)
  -> PIN VERSION / COMMIT
  -> HERMES NATIVE SCANNER (hermes skills audit / Skills Guard)   [gate pertama]
  -> BACA STATIS + review manual (scripts, hooks, network, permission, secret access)
  -> SECOND OPINION (skill-scanner Sentry / scanner komunitas)    [defense-in-depth]
  -> TEST di sandbox / repo disposable
  -> ALLOWLIST TOOL MINIMUM
  -> APPROVAL manusia
  -> INSTALL
  -> RE-AUDIT berkala saat update
```
Dilarang memakai `--force` untuk melewati verdict berbahaya. Bila scanner gagal: **port/adapt manual** hanya workflow
yang dibutuhkan menjadi custom skill kecil yang diaudit (blueprint §9 Phase 1).

## 3. Isolasi runtime (boundary sebenarnya)
Approval prompt, redaction, dan allowlist adalah defense-in-depth — **bukan containment absolut**.
Untuk konten/pekerjaan untrusted atau produksi:
- whole-process isolation (Hermes Docker/Compose atau sandbox whole-process setara),
- jalan sebagai non-root,
- mount hanya workspace yang diperlukan,
- egress minimal, tanpa socket Docker host, tanpa mount kredensial host (SSH/AWS/K8s),
- injeksi credential minimum (idealnya tanpa kredensial).

## 4. Kebijakan MCP
- Gunakan MCP official/vendor bila tersedia; expose hanya tool yang diperlukan (include/allowlist).
- Filesystem hanya pada workspace allowlist; database produksi default read-only; scope credential minimum.
- Perlakukan MCP server sebagai trusted code: audit source + versi.

## 5. Larangan auto-approve
Destructive shell, deploy produksi, migration destruktif, perubahan secret/credential, perubahan IAM,
publish/release, aksi payment/financial, penghapusan data, atau MCP baru dengan akses filesystem/network luas.

## 6. Status implementasi di ekosistem ini
- Gate pertama = `hermes skills audit` (native). Status: tersedia di host ini.
- Registry skill: `registry/skills.yaml` (sumber, revisi terpin, status KEEP/ADD/QUARANTINE/pending-approval).
- Tool deterministik security: `registry/tools.yaml` (status terpasang/pending).
- Tidak ada skill/MCP pihak ketiga yang diaktifkan tanpa baris approval manusia di `reports/human-approval-required.md`.
