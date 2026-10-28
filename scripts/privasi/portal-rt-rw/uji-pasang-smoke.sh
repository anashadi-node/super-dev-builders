#!/usr/bin/env bash
# BUILD + PASANG + SMOKE — Portal Warga (bukti tahap 12, 14, 15)
#
# Menghasilkan tiga berkas bukti dengan isi dari keluaran nyata:
#   logs/build-<stamp>.log   — artefak yang dibangun + sidik jari SHA-256
#   logs/smoke-<stamp>.log   — server dijalankan lalu endpoint diperiksa (HTTP nyata)
#   (kegagalan pasang akan terlihat sebagai baris GAGAL, bukan disembunyikan)
#
# Prinsip: setiap langkah mencetak buktinya. Tidak ada "seharusnya jalan".
set -uo pipefail

PROYEK="${1:-/home/anashadi/rt-rw-portal}"
RUN=/home/anashadi/super-dev-builders/runs/rt-rw-portal
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_BUILD="$RUN/logs/build-$STAMP.log"
LOG_SMOKE="$RUN/logs/smoke-$STAMP.log"
SCRATCH="${TMPDIR:-/tmp}"
PASANG="$SCRATCH/pasang-portal.$STAMP"
PORT="${PORT:-8191}"
mkdir -p "$RUN/logs"

# ---------------------------------------------------------------------------
# PREFLIGHT PORT — wajib. Bila port sudah dipakai (server sisa/asing), uji ini
# akan "lulus" dari jawaban proses LAIN dan gagal bind diam-diam. Lebih baik
# menolak jalan daripada menghasilkan log bukti yang menyesatkan.
# ---------------------------------------------------------------------------
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  echo "GAGAL PREFLIGHT: port $PORT sudah dipakai proses lain:"
  ss -ltnp 2>/dev/null | grep ":$PORT " | sed 's/^/    /'
  echo "Hentikan proses itu atau jalankan ulang dengan PORT=<lain>. Tidak ada log bukti dibuat."
  exit 3
fi

gagal=0
catat() { echo "$1"; }

# ---------------------------------------------------------------- BUILD ----
{
  catat "# Bukti build — Portal Warga"
  catat "- waktu   : $(date -Is)"
  catat "- komit   : $(git -C "$PROYEK" rev-parse HEAD 2>/dev/null || echo '-')"
  catat "- cabang  : $(git -C "$PROYEK" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '-')"
  catat "- python  : $(/usr/bin/python3 -V 2>&1)"
  catat "- dependensi (requirements.txt):"
  sed 's/^/    /' "$PROYEK/requirements.txt"
  catat ""
  catat "## Artefak yang dibangun"
  for skrip in build_standalone build_android_www build_mock build_penawaran; do
    printf "  %-22s " "$skrip"
    if out="$(cd "$PROYEK" && /usr/bin/python3 "scripts/$skrip.py" 2>&1)"; then
      echo "OK"
    else
      echo "GAGAL"; echo "$out" | tail -3 | sed 's/^/      /'; gagal=1
    fi
  done
  catat ""
  catat "## Sidik jari artefak (sha256 + ukuran)"
  for f in demo/standalone.html android/www/index.html reports/mock-portal-warga.html \
           docs/PENAWARAN-PORTAL-WARGA.pdf docs/PENAWARAN-PORTAL-WARGA.html; do
    if [ -f "$PROYEK/$f" ]; then
      printf "  %-42s %s  %s byte\n" "$f" "$(sha256sum "$PROYEK/$f" | cut -c1-16)" "$(stat -c %s "$PROYEK/$f")"
    else
      printf "  %-42s HILANG\n" "$f"; gagal=1
    fi
  done
  catat ""
  catat "## Berkas font yang ikut paket (prasyarat ADR-003/uji terisolasi)"
  for f in "$PROYEK"/assets/fonts/*; do
    printf "  %-34s %s byte\n" "$(basename "$f")" "$(stat -c %s "$f")"
  done
  catat ""
  catat "## Hasil build: $([ "$gagal" = 0 ] && echo SUKSES || echo ADA-KEGAGALAN)"
} 2>&1 | tee "$LOG_BUILD"

# -------------------------------------------------- PASANG (INSTALL) ----
{
  catat ""
  catat "## PASANG: menyalin ke $PASANG lalu memasang dependensi di venv bersih"
  mkdir -p "$PASANG"
  tar -C "$PROYEK" --exclude-from="$PROYEK/deploy/kemasan-abaikan.txt" -cf - . \
    | tar -C "$PASANG" -xf -
  catat "  berkas tersalin: $(find "$PASANG" -type f | wc -l)"
  if /usr/bin/python3 -m venv "$PASANG/.venv" 2>&1 | tail -2; then
    catat "  venv dibuat"
  else
    catat "  GAGAL membuat venv"; gagal=1
  fi
  if "$PASANG/.venv/bin/pip" install -q -r "$PASANG/requirements.txt" 2>&1 | tail -3; then
    catat "  dependensi terpasang: $("$PASANG/.venv/bin/pip" list --format=freeze 2>/dev/null | grep -ciE 'fpdf2|cryptography') dari 2"
  else
    catat "  GAGAL memasang dependensi"; gagal=1
  fi
  catat "  uji impor modul:"
  ( cd "$PASANG" && "$PASANG/.venv/bin/python" -c "
import real_system.pdf_service as p, real_system.secrets_store as s, real_system.prod_server as ps
print('    pdf_service  OK — font:', p.direktori_font())
print('    secrets_store OK — fail-closed:', not s.AVAILABLE if hasattr(s,'AVAILABLE') else 'n/a')
print('    prod_server  OK')
" ) 2>&1 | sed 's/^/  /' || { catat "  GAGAL impor modul"; gagal=1; }
} 2>&1 | tee -a "$LOG_BUILD"

# ------------------------------------------------------------- SMOKE ----
: > "$LOG_SMOKE"
{
  catat "# Bukti smoke — Portal Warga"
  catat "- waktu  : $(date -Is)"
  catat "- alamat : http://127.0.0.1:$PORT"
  catat "- DB     : $PASANG/data/portal.sqlite3 (seed demo PORTAL_SEED=1)"
  catat ""
  catat "## Menjalankan server (venv hasil pasangan, bukan venv pengembang)"
} >> "$LOG_SMOKE"

# PID harus menunjuk ke proses `python` itu sendiri, BUKAN ke subshell.
# Pola lama `( cd DIR && ... ) &` + `PID=$!` menyimpan PID subshell: `kill` hanya
# membunuh pembungkusnya, server anak tetap hidup dan menahan port -> smoke
# berikutnya gagal bind dan "server sisa" dari sesi sebelumnya yang menjawab
# /healthz. Diperbaiki dengan `env -C` (coreutils >= 8.28) sehingga tidak ada
# subshell sama sekali.
env -C "$PASANG" \
    PORTAL_SEED=1 PORTAL_DB="$PASANG/data/portal.sqlite3" HOST=127.0.0.1 PORT="$PORT" \
    "$PASANG/.venv/bin/python" -m real_system.prod_server > "$PASANG/server.log" 2>&1 &
PID=$!

# ---------------------------------------------------------------------------
# JAMINAN BERSIH: apa pun yang terjadi (galat sintaks, variabel kosong, abort,
# Ctrl-C), server uji WAJIB dimatikan. Di sinilah kelas bug "server sisa
# menahan port" ditutup — bukan dengan ingat-ingat menjalankan kill manual.
# ---------------------------------------------------------------------------
bersihkan() {
  [ -n "${PID:-}" ] || return 0
  kill "$PID" 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$PID" 2>/dev/null || return 0
    sleep 0.3
  done
  kill -9 "$PID" 2>/dev/null
}
trap bersihkan EXIT INT TERM

# Tunggu siap (poll, bukan tidur buta). Berhenti lebih awal kalau proses KITA
# sudah mati (mis. gagal bind) — supaya tidak "siap" dari proses orang lain.
siap=0
for i in $(seq 1 40); do
  if curl -fsS -m 2 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then siap=1; break; fi
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.5
done
echo "- pid server uji: $PID ; siap=$siap setelah ~$((i*500)) ms" >> "$LOG_SMOKE"
if [ "$siap" != 1 ]; then
  {
    catat "  GAGAL: server uji tidak menjawab /healthz — tidak ada uji lanjutan dijalankan"
    catat "  --- server.log ---"
    sed 's/^/    /' "$PASANG/server.log" 2>/dev/null
  } >> "$LOG_SMOKE"
  echo "log smoke : $LOG_SMOKE (GAGAL: server tidak siap)"
  exit 4
fi

periksa() {  # nama, metode, jalur, kode-diharapkan, [cookie]
  local nama="$1" metode="$2" jalur="$3" harap="$4" jar="${5:-}"
  local kode
  if [ -n "$jar" ]; then
    kode=$(curl -s -o "$PASANG/out.txt" -w '%{http_code}' -b "$PASANG/cookies.txt" -X "$metode" "http://127.0.0.1:$PORT$jalur")
  else
    kode=$(curl -s -o "$PASANG/out.txt" -w '%{http_code}' -X "$metode" "http://127.0.0.1:$PORT$jalur")
  fi
  local ukuran; ukuran=$(stat -c %s "$PASANG/out.txt")
  if [ "$kode" = "$harap" ]; then
    printf "  OK    %-34s %s (%s byte)\n" "$jalur" "$kode" "$ukuran" >> "$LOG_SMOKE"
  else
    printf "  GAGAL %-34s %s (harap %s)\n" "$jalur" "$kode" "$harap" >> "$LOG_SMOKE"
  fi
}

{
  catat ""
  catat "## Pemeriksaan tanpa masuk (pengunjung)"
  periksa health GET /healthz 200
  periksa kesehatan-json GET /api/health/live 200
  periksa halaman-utama GET / 200
  periksa darurat GET /emergency 200
  periksa cctv GET /cctv 200
  periksa privasi GET /privacy 200
  catat ""
  catat "## Masuk sebagai ketua RW (seed demo)"
  kode=$(curl -s -o "$PASANG/login.txt" -w '%{http_code}' -c "$PASANG/cookies.txt" \
      -H 'Content-Type: application/json' \
      -d '{"email":"ketua.rwNN@portal.local","password":"PortalRwAdm"}' \
      "http://127.0.0.1:$PORT/api/login")
  catat "  POST /api/login -> $kode ; cookie sesi: $(grep -c portal_session "$PASANG/cookies.txt" 2>/dev/null || echo 0)"
  periksa sesi-saya GET /api/me 200 jar
  periksa daftar-iuran GET /api/dues 200 jar
  catat ""
  catat "## Dokumen PDF (jalur yang gagal di sistem tanpa font)"
  id=$(/usr/bin/python3 -c "
import json,sys
try:
    d=json.load(open('$PASANG/out.txt'))
    rows=d if isinstance(d,list) else d.get('dues') or d.get('items') or []
    print(rows[0]['id'] if rows else '')
except Exception: print('')
")
  if [ -n "$id" ]; then
    kode=$(curl -s -o "$PASANG/kwitansi.pdf" -w '%{http_code}' -b "$PASANG/cookies.txt" \
        "http://127.0.0.1:$PORT/api/dues/$id/pdf")
    jenis=$(file -b "$PASANG/kwitansi.pdf" 2>/dev/null | cut -c1-40)
    catat "  GET /api/dues/$id/pdf -> $kode ($(stat -c %s "$PASANG/kwitansi.pdf") byte) $jenis"
  else
    catat "  (tidak ada id iuran pada seed demo — dilewati)"
  fi
  catat ""
  catat "## Pemeriksaan negatif (harus DITOLAK)"
  periksa tanpa-sesi GET /api/me 401
  kode=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
      -d '{"email":"ketua.rwNN@portal.local","password":"salah-sekali"}' \
      "http://127.0.0.1:$PORT/api/login")
  catat "  POST /api/login sandi salah -> $kode (harap 401/403)"
  catat ""
  catat "## Log server (20 baris terakhir)"
  tail -20 "$PASANG/server.log" | sed 's/^/  /'
} >> "$LOG_SMOKE" 2>&1

kill "$PID" 2>/dev/null
sleep 1
kill -9 "$PID" 2>/dev/null
{
  catat ""
  catat "## Server dihentikan"
  if curl -fsS -m 2 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    catat "  GAGAL: server masih menjawab setelah dihentikan"
  else
    catat "  OK: port $PORT tidak lagi menjawab (proses bersih)"
  fi
} >> "$LOG_SMOKE"

echo
echo "log build : $LOG_BUILD"
echo "log smoke : $LOG_SMOKE"
echo "salinan pasangan: $PASANG"
grep -c "GAGAL" "$LOG_SMOKE" >/dev/null 2>&1 && echo "periksa baris GAGAL di log smoke"
