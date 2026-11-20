#!/usr/bin/env bash
# C2-B2M rollback — idempoten. Aman walau apply.sh gagal separuh jalan.
#   SDB_B2M_APPLY=1 SDB_B2M_CONFIRM="SETUJU-B2M" docs/c2b2m/rollback.sh
set -euo pipefail

USER_B="sdbbuild"
WS="/srv/sdb-workspace"
CANARY="/home/anashadi/.sdb-canary"

[[ "${SDB_B2M_APPLY:-0}" == "1" && "${SDB_B2M_CONFIRM:-}" == "SETUJU-B2M" ]] || {
  echo "DITOLAK: butuh SDB_B2M_APPLY=1 dan SDB_B2M_CONFIRM=SETUJU-B2M." >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "DITOLAK: jalankan dengan sudo." >&2; exit 2; }

log() { printf '[rollback] %s\n' "$*"; }

# 1. proses milik builder harus mati dulu (jangan bunuh proses Owner)
if pgrep -u "$USER_B" >/dev/null 2>&1; then
  log "menghentikan proses milik $USER_B"
  pkill -u "$USER_B" || true; sleep 2
  pkill -9 -u "$USER_B" 2>/dev/null || true
fi

# 2. user + home
if getent passwd "$USER_B" >/dev/null; then
  userdel --remove "$USER_B" 2>/dev/null || userdel "$USER_B"
  log "user $USER_B dihapus"
else
  log "user $USER_B sudah tidak ada"
fi

# 3. grup hanya bila benar-benar kosong
if getent group "$USER_B" >/dev/null; then
  anggota=$(getent group "$USER_B" | cut -d: -f4)
  [[ -z "$anggota" ]] && { groupdel "$USER_B"; log "grup $USER_B dihapus"; } \
    || log "grup $USER_B masih dipakai ($anggota) — TIDAK dihapus"
fi

# 4. workspace (hanya jalur ini; repo Owner tidak pernah disentuh)
[[ -d "$WS" ]] && { rm -rf --one-file-system "$WS"; log "workspace $WS dihapus"; }

# 5. canary sintetis
[[ -d "$CANARY" ]] && { rm -rf --one-file-system "$CANARY"; log "canary $CANARY dihapus"; }

# 6. verifikasi sisa
sisa=""
getent passwd "$USER_B" >/dev/null && sisa="$sisa user"
getent group "$USER_B" >/dev/null && sisa="$sisa group"
[[ -e "$WS" ]] && sisa="$sisa workspace"
[[ -e "$CANARY" ]] && sisa="$sisa canary"
[[ -e "/home/anashadi/super-dev-builders/.probe_b2m" ]] && rm -f "/home/anashadi/super-dev-builders/.probe_b2m"

if [[ -z "$sisa" ]]; then
  log "BERSIH: tidak ada sisa"
  exit 0
fi
log "SISA terdeteksi:$sisa"; exit 1
