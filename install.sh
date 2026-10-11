#!/usr/bin/env bash
# Pasang Super Dev Builders ke host Hermes: 37 skill custom + perintah `sdb`.
#
# Prinsip:
#  1. DRY-RUN adalah default. Tidak ada yang berubah di host tanpa `--apply`.
#     Alasannya konkret: penamaan skill bertabrakan membuat Hermes tidak bisa
#     memuat salah satunya (temuan audit 2026-10-07), jadi pemasangan harus
#     selalu dapat diperiksa lebih dulu.
#  2. Back-up dulu, baru timpa. Tidak ada `rm -rf` tanpa cadangan.
#  3. Tidak membaca/menulis rahasia apa pun. Tidak ada akses jaringan.
#  4. Fail-closed: prasyarat tidak lengkap -> berhenti, bukan asal jalan.
#
# Pemakaian:
#   ./install.sh                      # tampilkan rencana saja (dry-run)
#   ./install.sh --apply              # benar-benar pasang
#   ./install.sh --apply --no-cli     # hanya skill, tanpa perintah `sdb`
#   ./install.sh --apply --main-only  # hanya namespace utama (~/.hermes/skills)
#   ./install.sh --uninstall --apply  # copot pemasangan
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PY="${SDB_PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then PY="$(command -v python3)"
  else echo "FATAL: python3 tidak ditemukan" >&2; exit 1; fi
fi

APPLY=0; DO_CLI=1; MAIN_ONLY=0; UNINSTALL=0
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --dry-run) APPLY=0 ;;
    --no-cli) DO_CLI=0 ;;
    --main-only) MAIN_ONLY=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "FATAL: argumen tidak dikenal: $a" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

step "Prasyarat"
if [ ! -f "$ROOT/registry/skills.yaml" ]; then
  say "FATAL: registry/skills.yaml tidak ada — ini bukan root repo Super Dev Builders"; exit 1
fi
if ! "$PY" -c "import yaml" 2>/dev/null; then
  say "FATAL: PyYAML wajib (baca registry). Pasang: \"$PY\" -m pip install pyyaml"; exit 1
fi
say "repo      : $ROOT"
say "python    : $PY"
say "hermes    : $HERMES_HOME"
say "mode      : $([ "$APPLY" = 1 ] && echo 'APPLY (mengubah host)' || echo 'DRY-RUN (tidak mengubah apa pun)')"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$HERMES_HOME/backups/super-dev-builders-$STAMP"

step "Pemetaan skill -> profil (dari registry)"
"$PY" "$ROOT/scripts/install_skills.py" --list

if [ "$UNINSTALL" = 1 ]; then
  step "Copot skill"
  if [ "$MAIN_ONLY" = 1 ]; then
    "$PY" "$ROOT/scripts/install_skills.py" --main --uninstall $([ "$APPLY" = 1 ] || echo --dry-run)
  else
    "$PY" "$ROOT/scripts/install_skills.py" --all --uninstall $([ "$APPLY" = 1 ] || echo --dry-run)
    "$PY" "$ROOT/scripts/install_skills.py" --main --uninstall $([ "$APPLY" = 1 ] || echo --dry-run)
  fi
else
  step "Back-up (hanya bila --apply)"
  if [ "$APPLY" = 1 ]; then
    mkdir -p "$BACKUP"
    for ns in "$HERMES_HOME/skills/super-dev-builders" "$HERMES_HOME"/profiles/*/skills/super-dev-builders; do
      [ -d "$ns" ] || continue
      rel="${ns#"$HERMES_HOME"/}"
      mkdir -p "$BACKUP/$(dirname "$rel")"
      cp -a "$ns" "$BACKUP/$rel"
    done
    say "back-up   : $BACKUP"
  else
    say "dilewati (dry-run): mkdir -p $BACKUP; cp -a <namespace terpasang>"
  fi

  step "Pasang skill"
  if [ "$MAIN_ONLY" = 1 ]; then
    "$PY" "$ROOT/scripts/install_skills.py" --main $([ "$APPLY" = 1 ] || echo --dry-run)
  else
    "$PY" "$ROOT/scripts/install_skills.py" --all $([ "$APPLY" = 1 ] || echo --dry-run)
    "$PY" "$ROOT/scripts/install_skills.py" --main $([ "$APPLY" = 1 ] || echo --dry-run)
  fi
fi

if [ "$DO_CLI" = 1 ]; then
  step "Perintah sdb"
  BIN="${SDB_BIN_DIR:-$HOME/.local/bin}"
  SHIM="$BIN/sdb"
  if [ "$UNINSTALL" = 1 ]; then
    if [ -f "$SHIM" ]; then
      say "hapus: $SHIM"
      [ "$APPLY" = 1 ] && rm -f "$SHIM"
    else
      say "tidak ada: $SHIM"
    fi
  else
    mkdir -p "$BIN" 2>/dev/null || true
    say "tulis: $SHIM  ->  $PY $ROOT/scripts/sdb.py \"\$@\""
    if [ "$APPLY" = 1 ]; then
      if [ -f "$SHIM" ] && ! grep -q "scripts/sdb.py" "$SHIM" 2>/dev/null; then
        mkdir -p "$BACKUP/bin"; cp -a "$SHIM" "$BACKUP/bin/sdb"
        say "back-up shim lama: $BACKUP/bin/sdb"
      fi
      # %q: path berisi $ ` " spasi tidak dieksekusi/pecah saat shim jalan. rm dulu: `>` akan
      # mengikuti symlink dan menimpa berkas lain bila $SHIM ternyata symlink.
      rm -f -- "$SHIM"
      umask 022
      printf '#!/usr/bin/env bash\n# Dibuat otomatis oleh super-dev-builders/install.sh (%s).\n# Satu pintu masuk ekosistem Super Dev Builders.\nexec %q %q "$@"\n' \
        "$STAMP" "$PY" "$ROOT/scripts/sdb.py" > "$SHIM"
      chmod +x "$SHIM"
    fi
    case ":$PATH:" in
      *":$BIN:"*) : ;;
      *) say "CATATAN: $BIN belum ada di PATH — tambahkan: export PATH=\"$BIN:\$PATH\"" ;;
    esac
  fi
fi

step "Langkah berikutnya"
if [ "$APPLY" = 1 ]; then
  say "1) Verifikasi pemasangan : sdb doctor"
  say "2) Cek drift skill       : sdb list-skills --list"
  say "3) Mulai target baru     : sdb init <nama-target>"
  say "4) Jalankan workflow     : sdb workflow <nama-target>"
  say "5) Copot bila perlu      : $ROOT/install.sh --uninstall --apply"
  say ""
  say "Back-up tersimpan di: $BACKUP"
else
  say "Ini DRY-RUN — tidak ada yang berubah. Jalankan ulang dengan --apply untuk memasang."
fi