#!/usr/bin/env bash
# KANONIK (sejak 30 Okt 2026): toolchain gerbang keamanan SDB untuk SEMUA run/proyek.
# Salinan lama `scripts/privasi/portal-rt-rw/scan-keamanan.sh` DIBEKUKAN apa adanya,
# hanya untuk mereproduksi verdict `runs/rt-rw-portal` (18 Okt 2026). Setiap perbaikan
# alat wajib masuk ke berkas ini; jangan sunting salinan beku itu (drift = alat ganda).
# Gerbang keamanan (tahap 10): SAST + SBOM + kerentanan + scan rahasia.
#
# Alat nyata: semgrep, syft, trivy, ruff. Semua BACA-SAJA atas berkas sumber: tidak
# ada eksekusi kode produk, karena itu boleh berjalan di host (berbeda dari uji yang
# harus terisolasi).
#
# DUA aturan integritas bukti (mengapa skrip ini ditulis begini):
# 1. Kode keluar SETIAP alat diambil apa adanya. Sebelumnya `alat | tail` membuat
#    `$?` = kode keluar `tail` — laporan "exit=0" tidak berarti alatnya berhasil.
# 2. "0 temuan" HANYA sah kalau alatnya benar-benar memindai berkas. Semgrep yang
#    memindai 0 berkas juga melaporkan 0 temuan; itu bukan bukti bersih, itu bukti
#    kosong. Karena itu jumlah berkas dipindai diperiksa dan 0 => GAGAL.
set -uo pipefail

# Jalur TIDAK boleh di-hardcode ke satu proyek: gerbang yang hanya jalan untuk
# portal-rt-rw membuat setiap run baru jatuh ke BLOCKED (terbukti 30 Okt 2026:
# `security_verdict.py --run-dir <baru>` -> BLOCKED "alat tidak ada").
# Kontrak: <proyek> [--run-dir via SDB_RUN_DIR] [--tools via SDB_TOOLS_DIR].
PROYEK="${1:-.}"
TOOLS="${SDB_TOOLS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
RUN="${SDB_RUN_DIR:-$PROYEK/.sdb-run}"
RAW="$RUN/reports/raw"
RINGKASAN="$RUN/reports/scan-keamanan-ringkasan.txt"
PY="${PORTAL_PY:-python3}"
mkdir -p "$RAW"
: > "$RINGKASAN"

GAGAL=0
catat() { # $1 nama, $2 kode keluar, $3 catatan
  printf '%-9s exit=%-3s %s\n' "$1" "$2" "$3" | tee -a "$RINGKASAN"
  [ "$2" -eq 0 ] || GAGAL=1
}

echo "=== 1/5 semgrep (SAST) ==="
# Dua jebakan yang sudah terbukti di lingkungan ini, jangan diulang:
#
# 1. Jalur ABSOLUT di dalam repo git => semgrep memindai 0 berkas dan tetap keluar 0
#    (diuji: absolut -> 0 target; relatif -> 29 target; kontrol di /tmp -> terdeteksi).
#    Karena itu semgrep SELALU dijalankan `cd` ke akar proyek dengan target ".".
# 2. Berkas yang tidak terlacak git diabaikan otomatis. Itu menguntungkan (`.venv`,
#    `logs/`, `scratch/` tak perlu dikecualikan manual), tapi berarti berkas BARU yang
#    belum `git add` juga tak dipindai -> itu tugas `cek_bersih()` di uji pra-rilis,
#    bukan di sini.
#
# KONTROL NEGATIF: berkas sengaja buruk (eval) di direktori sementara WAJIB terdeteksi.
# Tanpa kontrol, "0 temuan" tak bisa dibedakan dari "alat buta".
KONTROL="$(mktemp -d)"
printf 'def f(x):\n    return eval(x)\n' > "$KONTROL/coba.py"
semgrep scan --config=p/default --metrics=off --json \
    --output="$RAW/semgrep-kontrol.json" "$KONTROL" >"$RAW/semgrep-kontrol.log" 2>&1
KT=$("$PY" - "$RAW/semgrep-kontrol.json" <<'PUB'
import json,sys
try:
    print(len(json.load(open(sys.argv[1])).get("results",[])))
except Exception:
    print(-1)
PUB
)
[ -n "$KONTROL" ] && [ "$KONTROL" != "/" ] && rm -rf "$KONTROL"

( cd "$PROYEK" && semgrep scan --config=p/default --metrics=off --json \
    --output="$RAW/semgrep.json" . ) >"$RAW/semgrep.log" 2>&1
KODE=$?
N=$("$PY" - "$RAW/semgrep.json" <<'PUB'
import json,sys
try:
    print(len(json.load(open(sys.argv[1])).get("paths",{}).get("scanned",[])))
except Exception:
    print(-1)
PUB
)
T=$("$PY" - "$RAW/semgrep.json" <<'PUB'
import json,sys
try:
    print(len(json.load(open(sys.argv[1])).get("results",[])))
except Exception:
    print(-1)
PUB
)
if [ "$KT" -lt 1 ]; then
  catat semgrep 1 "KONTROL NEGATIF GAGAL (eval tidak terdeteksi=$KT) — bukti SAST tidak sah"
elif [ "$N" -le 0 ]; then
  catat semgrep 1 "berkas dipindai=0 — keluar 0 tidak berarti bersih (lihat jebakan #1)"
else
  E=$("$PY" - "$RAW/semgrep.json" <<'PUB'
import json,sys
try:
    print(sum(1 for r in json.load(open(sys.argv[1])).get("results",[])
              if r.get("extra",{}).get("severity")=="ERROR"))
except Exception:
    print(-1)
PUB
)
  W=$(( T - E ))
  if [ "$E" -gt 0 ]; then
    catat semgrep 1 "kontrol=$KT, berkas=$N, temuan=$T (ERROR=$E WARNING=$W) — ERROR belum ditriase"
  else
    catat semgrep "$KODE" "kontrol=$KT, berkas=$N, temuan=$T (ERROR=0 WARNING=$W; setiap titik ERROR sudah ditandai nosemgrep + alasan)"
  fi
fi

tail -2 "$RAW/semgrep.log" 2>/dev/null | sed 's/^/  /'


echo "=== 2/5 syft (SBOM) ==="
syft dir:"$PROYEK" -o json --quiet >"$RAW/syft.json" 2>"$RAW/syft.err"
catat syft $? "SBOM: $(du -h "$RAW/syft.json" 2>/dev/null | cut -f1)"

echo "=== 3/5 trivy (kerentanan + rahasia) ==="
# --include-dev-deps WAJIB: tanpa flag ini trivy MENYENYAPKAN seluruh devDependency npm dan
# melaporkan "0 kerentanan" untuk android/package-lock.json padahal ada 12 (terbukti ulang
# 11 Okt 2026: tanpa flag=0, dengan flag=12 [1 CRITICAL, 8 HIGH, 3 MEDIUM]). Laporan lama
# mengaku sudah memperbaikinya di skrip ini, tetapi flag-nya tidak pernah ada.
#
# Temuan dibandingkan dengan BASELINE risiko-terbuka (tools/risiko-diterima.json):
#   - temuan di luar baseline            => GAGAL (kerentanan BARU)
#   - semua temuan ada di baseline        => BERSYARAT: dilaporkan keras per tingkat, bukan
#                                            disenyapkan. Baseline BUKAN persetujuan; ia hanya
#                                            membedakan "sudah diketahui" dari "baru".
trivy fs --include-dev-deps --format json --output "$RAW/trivy.json" \
    --scanners vuln,secret,misconfig "$PROYEK" >"$RAW/trivy.log" 2>&1
KODE=$?
# Baseline risiko-terbuka: milik run bila ada, jika tidak milik toolchain bersama
# (tidak ada baseline = setiap temuan dihitung BARU -> fail-closed, bukan izin).
BASELINE="$RUN/tools/risiko-diterima.json"
[ -f "$BASELINE" ] || BASELINE="$TOOLS/risiko-diterima.json"
[ -f "$BASELINE" ] || BASELINE=/dev/null
HASIL=$("$PY" - "$RAW/trivy.json" "$BASELINE" <<'PUB'
import json,sys,collections
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    print("-1|0|0|rusak"); raise SystemExit
try:
    dasar={x["id"] for x in json.load(open(sys.argv[2])).get("trivy",[])}
except Exception:
    dasar=set()
vul=[(r.get("Target",""),v) for r in d.get("Results",[]) for v in r.get("Vulnerabilities",[])]
lain=sum(len(r.get("Secrets",[]))+len(r.get("Misconfigurations",[])) for r in d.get("Results",[]))
baru=[v for _,v in vul if v["VulnerabilityID"] not in dasar]
sev=collections.Counter(v["Severity"] for _,v in vul)
ket=",".join(f"{k}={sev[k]}" for k in ("CRITICAL","HIGH","MEDIUM","LOW") if sev[k])
print(f"{len(vul)+lain}|{len(baru)+lain}|{len(vul)}|{ket or '-'}")
PUB
)
TEMUAN="${HASIL%%|*}"; R="${HASIL#*|}"; BARU="${R%%|*}"; R="${R#*|}"; VUL="${R%%|*}"; KET="${R#*|}"
if [ "$TEMUAN" = "-1" ]; then
  catat trivy 1 "keluaran trivy tidak terbaca — bukti tidak sah"
elif [ "$BARU" -gt 0 ]; then
  catat trivy 1 "temuan=$TEMUAN, di luar baseline risiko-terbuka=$BARU ($KET) — kerentanan/rahasia BARU"
elif [ "$VUL" -gt 0 ]; then
  catat trivy "$KODE" "BERSYARAT: $VUL kerentanan, semuanya sudah tercatat di baseline risiko-terbuka S-2 ($KET); BUKAN bersih"
else
  catat trivy "$KODE" "temuan=0 (kerentanan+rahasia+misconfig, termasuk devDependency)"
fi

echo "=== 4/5 ruff (keamanan pola — konfigurasi DIPIN di dalam repo) ==="
# Gerbang ini memakai ruff.toml milik repo, BUKAN set bawaan ruff di mesin ini. Tanpa
# konfigurasi dipin, "hijau" bisa berarti "aturan di mesin ini kebetulan lebih longgar",
# bukan "kode bersih" — dan hasilnya tidak bisa direproduksi di mesin lain.
if [ ! -f "$PROYEK/ruff.toml" ]; then
  catat ruff 1 "GAGAL: $PROYEK/ruff.toml tidak ada — aturan lint tidak dipin di repo"
else
  ( cd "$PROYEK" && ruff check --output-format=json . >"$RAW/ruff.json" 2>"$RAW/ruff.err" )
  KODE=$?
  TEMUAN=$("$PY" - "$RAW/ruff.json" <<'PUB'
import json,sys
try:
    print(len(json.load(open(sys.argv[1]))))
except Exception:
    print(-1)
PUB
)
  catat ruff "$KODE" "temuan=$TEMUAN (aturan keamanan S/BLE/B/E9 dari ruff.toml repo)"
  # INTI WAJIB — ruff.toml proyek TIDAK boleh bisa mematikan deteksi keamanan.
  # Bukti kegagalan (30 Okt 2026): proyek yang memilih hanya E9/B lolos dengan
  # `eval(x)` di kode (S307) => verdict PASS. Alat, bukan proyek, yang menentukan inti.
  ( cd "$PROYEK" && ruff check --isolated --select S,BLE,E9 --output-format=json . \
      >"$RAW/ruff-inti.json" 2>"$RAW/ruff-inti.err" )
  KODE_INTI=$?
  TEMUAN_INTI=$("$PY" - "$RAW/ruff-inti.json" <<'PUB'
import json, sys
try:
    print(len(json.load(open(sys.argv[1]))))
except Exception:
    print(-1)
PUB
)
  [ "$KODE_INTI" != "0" ] && KODE=1
  catat ruff-inti "$KODE_INTI" "temuan=$TEMUAN_INTI (S/BLE/E9 dipaksa --isolated; ruff.toml proyek tidak bisa mematikan)"
  # Utang GAYA dilaporkan sebagai tren supaya tidak menghilang, TANPA menggagalkan gerbang
  # keamanan (kosmetik bukan risiko rilis). Ditulis ke ringkasan, bukan lewat catat().
  ( cd "$PROYEK" && ruff check --select UP,RUF,F,EXE,PL,I,SIM,ISC,FURB,DTZ,RET \
      --statistics . 2>/dev/null | grep -E "^Found" | tail -1 ) >"$RAW/ruff-gaya.txt"
  printf '%-9s %-3s %s\n' "ruff-gaya" "-" \
    "utang gaya (daftar aturan TETAP, tidak menggagalkan): $(cat "$RAW/ruff-gaya.txt")" >>"$RINGKASAN"
fi

echo "=== 5/5 privasi-media (identitas pada MEDIA TERLACAK, kanal OCR) ==="
# Mengapa alat kelima ada: ketiga gerbang sebelumnya (scan-keamanan, sapuan produk,
# test penjaga) memakai SATU definisi cakupan yang sama — berkas yang ikut dikemas.
# Tangkapan layar `reports/`, `verification/`, dan video demo ada di repo, TERLACAK git,
# tetapi di luar cakupan kemasan; kanal teks tidak bisa membaca piksel. Hasilnya 11 Okt
# 2026: 41 berkas media terlacak memuat identitas pilot sementara semua gerbang bilang 0.
# Cakupan alat ini = berkas media TERLACAK git, bukan cakupan kemasan. Pelengkap, bukan
# pengganti. Kode keluar: 0=BERSIH/BERSYARAT, 1=temuan BARU, 2=alat OCR tidak ada.
( cd "$PROYEK" && PYTHONDONTWRITEBYTECODE=1 "$PY" \
    "$TOOLS/scan-privasi-media.py" "$PROYEK" --tulis-json \
    >"$RAW/privasi-media.log" 2>&1 )
KODE=$?
RINGKAS_MEDIA=$(grep -E "beridentitas — (BARU|DIKETAHUI)|berkas media TERLACAK diperiksa|TIDAK BERLAKU" "$RAW/privasi-media.log" | tr -s ' ' | tr '\n' ' ' | xargs)
PESAN_MEDIA=$(grep -m1 -E "MEMBLOKIR RILIS|TAK DIVERIFIKASI|GAGAL:" "$RAW/privasi-media.log" | cut -c1-160)
if [ "$KODE" = "2" ]; then
  catat privasi-media 1 "TAK DIVERIFIKASI (fail-closed): ${PESAN_MEDIA:-alat gagal}"
elif [ "$KODE" = "1" ]; then
  catat privasi-media 1 "${PESAN_MEDIA:-media beridentitas BARU} | ${RINGKAS_MEDIA}"
elif [ "$KODE" = "3" ]; then
  # Kode 3 = temuan DIKETAHUI tetapi BELUM DITUTUP (OQ-7). Sengaja MEMBLOKIR: temuan
  # identitas pelanggan yang belum ditutup tidak boleh berubah arti menjadi "diizinkan".
  # Gerbang ini kembali hijau hanya lewat dua jalan yang sah: (a) berkas diredaksi sehingga
  # sha256-nya berubah dan entri gugur dari baseline, atau (b) pemilik menandatangani
  # keputusan 'DITERIMA' di tools/media-diketahui.json.
  catat privasi-media 1 "${PESAN_MEDIA:-MEMBLOKIR RILIS} | ${RINGKAS_MEDIA}"
elif [ "$KODE" = "0" ]; then
  catat privasi-media 0 "${RINGKAS_MEDIA:-log kosong}"
else
  catat privasi-media 1 "kode keluar tak terduga=$KODE — bukti tidak sah"
fi

echo
echo "=== ringkasan kode keluar ==="
cat "$RINGKASAN"
echo "berkas mentah: $RAW"
if [ "$GAGAL" -ne 0 ]; then
  echo "GAGAL: bukti keamanan TIDAK lengkap — perbaiki alat/temuan di atas sebelum rilis"
  exit 1
fi
echo "OK: kelima alat selesai dengan kode keluar 0"

