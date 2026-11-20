#!/usr/bin/env bash
# C2-B2M preflight — HANYA MEMBACA. Tidak membuat user, tidak mengubah permission.
# Keluar 0 = host siap untuk apply.sh; != 0 = ada penghalang.
set -euo pipefail

fail=0
ok()   { printf 'PASS  %s\n' "$*"; }
bad()  { printf 'FAIL  %s\n' "$*"; fail=1; }
info() { printf 'INFO  %s\n' "$*"; }

info "host: $(uname -srm)"
info "waktu: $(date -Is)"

# 1. user builder belum ada (apply idempoten tidak boleh menimpa akun lain)
if getent passwd sdbbuild >/dev/null; then
  bad "user sdbbuild SUDAH ADA (uid $(id -u sdbbuild)) — hentikan, audit dulu"
else
  ok "user sdbbuild belum ada"
fi

# 2. workspace belum ada atau kosong
if [[ -e /srv/sdb-workspace ]]; then
  bad "/srv/sdb-workspace sudah ada — milik siapa: $(stat -c '%U:%G %A' /srv/sdb-workspace)"
else
  ok "/srv/sdb-workspace belum ada"
fi

# 3. canary belum ada (harus dibuat bersih oleh apply.sh)
if [[ -e /home/anashadi/.sdb-canary ]]; then
  bad "/home/anashadi/.sdb-canary sudah ada — hapus atau audit dulu"
else
  ok "canary belum ada"
fi

# 4. jalur eskalasi yang harus tetap kosong untuk builder
for g in sudo docker lxd disk; do
  if getent group "$g" >/dev/null; then info "grup $g ada (anggota saat ini: $(getent group "$g" | cut -d: -f4))"; fi
done
if [[ -S /var/run/docker.sock ]]; then
  info "docker.sock ada ($(stat -c '%U:%G %A' /var/run/docker.sock)) — builder DILARANG masuk grup docker"
fi

# 5. batas filesystem: home Owner tidak boleh bisa ditembus user lain
h=$(stat -c '%a' /home/anashadi)
case "$h" in
  750|700|770|755) info "mode /home/anashadi = $h" ;;
  *) bad "mode /home/anashadi = $h — periksa sebelum lanjut" ;;
esac
[[ "$h" == "755" ]] && bad "/home/anashadi 0755: user lain bisa menembus home Owner"

# 6. kapasitas & perkakas
avail=$(df -Pk /srv 2>/dev/null | awk 'NR==2{print $4}')
[[ -n "${avail:-}" && "$avail" -gt 5242880 ]] && ok "ruang /srv ${avail}KB" || bad "ruang /srv < 5GB (${avail:-?}KB)"
for t in git python3 bash sudo; do
  command -v "$t" >/dev/null && ok "perkakas: $t" || bad "perkakas hilang: $t"
done

# 7. sudo non-interaktif untuk verifikasi (verify.sh memakai sudo -u sdbbuild)
if sudo -n true 2>/dev/null; then ok "sudo non-interaktif tersedia untuk verify.sh"; else
  info "sudo non-interaktif TIDAK tersedia — verify.sh perlu dijalankan dengan sesi sudo aktif"
fi

echo
[[ $fail -eq 0 ]] && { echo "HASIL: PASS (siap apply, belum ada yang diubah)"; exit 0; }
echo "HASIL: FAIL (perbaiki temuan di atas; tidak ada perubahan dilakukan)"; exit 1
