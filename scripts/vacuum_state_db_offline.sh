#!/usr/bin/env bash
# #18 VACUUM state.db — eksekutor jendela offline (otomatis).
#
# Konteks: `hermes sessions optimize` / `optimize-storage` menolak berjalan bila
# masih ada pemegang state.db (gateway, Desktop app, cron). Dari dalam sesi
# Desktop VACUUM mustahil: proses `hermes ... serve` milik Desktop ikut memegang
# DB. Karena itu script ini menunggu sampai SATU-SATUNYA pemegang yang tersisa
# adalah hermes-gateway (artinya Desktop app sudah ditutup), lalu menjalankan
# prosedur resmi docs/HERMES_VENV_HARDENING_2026-10-05.md §7.6:
#
#   systemctl --user stop hermes-gateway
#   hermes sessions optimize && hermes sessions optimize-storage
#   systemctl --user start hermes-gateway
#
# Jaminan aman:
#   - TANPA --force (menulis ulang store di bawah live writer bisa membuat
#     semua agent menolak turn; dilarang).
#   - Fail-closed: bila pemegang non-gateway masih ada saat jendela dicek,
#     script batal dan gateway dinyalakan kembali.
#   - Timeout 18 jam (env VACUUM_WAIT_HOURS) -> keluar tanpa perubahan.
#   - Tidak mengubah data percakapan.
#
# Pakai: bash vacuum_state_db_offline.sh [--check]
#   --check : hanya laporkan pemegang + ukuran, tanpa aksi.
#
# Batalkan watcher: systemctl --user stop hermes-vacuum-offline

set -u
export PATH=/usr/local/bin:/usr/bin:/bin
HOME="${HOME:-/home/anashadi}"

DB="$HOME/.hermes/state.db"
GW="hermes-gateway.service"
HERMES_BIN="$HOME/.local/bin/hermes"
LOGDIR="$HOME/.hermes/logs"
LOG="$LOGDIR/state-db-vacuum-$(date +%Y%m%d-%H%M%S).log"
WAIT_HOURS="${VACUUM_WAIT_HOURS:-18}"
POLL_SEC="${VACUUM_POLL_SEC:-30}"

mkdir -p "$LOGDIR"

log()  { echo "[$(date '+%F %T')] $*"; }
hsize(){ local s; s=$(du -h "$1" 2>/dev/null | cut -f1); echo "${s:-n/a}"; }
holders_now() { /usr/bin/fuser "$DB" 2>/dev/null; }
gw_pid() { /usr/bin/systemctl --user show -p MainPID --value "$GW" 2>/dev/null; }
others_count() {
  local gw n=0 p; gw=$(gw_pid)
  for p in $(holders_now); do [ "$p" = "$gw" ] || n=$((n + 1)); done
  echo "$n"
}

# --check menulis ke stdout (jangan ke log: exec redirect membelokkan stdout).
if [ "${1:-}" = "--check" ]; then
  log "CHECK state.db=$(hsize "$DB") wal=$(hsize "$DB-wal") pemegang=[$(holders_now)] gateway=$(gw_pid) non-gateway=$(others_count)"
  exit 0
fi

exec >>"$LOG" 2>&1

log "watcher #18 mulai — timeout ${WAIT_HOURS}h, poll ${POLL_SEC}s; menunggu Desktop app ditutup"
log "baseline state.db=$(hsize "$DB") wal=$(hsize "$DB-wal")"
deadline=$(( $(date +%s) + WAIT_HOURS * 3600 ))

while :; do
  if [ "$(others_count)" -eq 0 ]; then
    log "jendela offline terdeteksi — hanya gateway yang memegang state.db"
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "TIMEOUT ${WAIT_HOURS}h — Desktop tidak ditutup. Keluar tanpa perubahan."
    exit 0
  fi
  sleep "$POLL_SEC"
done

log "stop $GW"
# Jaring pengaman: apa pun yang terjadi setelah gateway dimatikan (exit, error, SIGTERM dari
# `systemctl stop hermes-vacuum-offline`, Ctrl-C), gateway HARUS dinyalakan lagi. Tanpa ini,
# membatalkan watcher di tengah jendela membiarkan semua agent tanpa gateway.
trap 'log "keluar — memastikan $GW menyala"; /usr/bin/systemctl --user start "$GW"' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
/usr/bin/systemctl --user stop "$GW" || { log "GAGAL stop gateway — batal, tanpa perubahan"; exit 1; }
sleep 2

left=$(holders_now)
if [ -n "$left" ]; then
  log "masih ada pemegang ($left) setelah stop gateway — batal (fail-closed)"
  /usr/bin/systemctl --user start "$GW"
  exit 1
fi

log "== hermes sessions optimize =="
"$HERMES_BIN" sessions optimize; rc_opt=$?
log "optimize rc=$rc_opt"

log "== hermes sessions optimize-storage --yes =="
"$HERMES_BIN" sessions optimize-storage --yes; rc_ost=$?
log "optimize-storage rc=$rc_ost"

log "== hermes doctor (saat store sepi) =="
"$HERMES_BIN" doctor 2>&1 | tail -12

log "start $GW"
/usr/bin/systemctl --user start "$GW"
sleep 5

log "after state.db=$(hsize "$DB") wal=$(hsize "$DB-wal") gateway=$(/usr/bin/systemctl --user is-active "$GW")"
log "SELESAI (optimize=$rc_opt optimize-storage=$rc_ost) — log: $LOG"
