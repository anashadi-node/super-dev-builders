#!/usr/bin/env bash
# Self-heal peluncur SDB: pastikan izin + trusted benar, perbaiki otomatis bila menyimpang.
# Dipanggil oleh sdb-deck-health.timer (harian) dan oleh sdb-deck (sebelum buka deck).
# Prinsip: diam bila sehat; hanya menulis bila menyimpang. Keluaran hanya bila ada perbaikan.
set -uo pipefail
APPS="$HOME/.local/share/applications"
DESK="$HOME/Desktop/sdb-command-deck.desktop"
SRC="$APPS/sdb-command-deck.desktop"
changed=0

# 1) Sumber & salinan Desktop harus ada.
if [ ! -e "$SRC" ]; then
  bash "$HOME/super-dev-builders/scripts/install_shortcuts.sh" >/dev/null 2>&1 || true
fi
[ -e "$SRC" ] || { echo "sdb-fix-launcher: sumber $SRC hilang, pemasangan gagal" >&2; exit 1; }

# 2) Flag Chrome wajib: di PC tanpa driver EGL, WebGL hanya hidup bila Swiftshader diizinkan.
#    Tanpa flag ini deck berhenti di layar "Menyiapkan Super Dev Builders Workspace…".
for f in "$APPS"/sdb-*.desktop; do
  if grep -q '127\.0\.0\.1:8484' "$f" && ! grep -q -- '--enable-unsafe-swiftshader' "$f"; then
    sed -i 's#^Exec=google-chrome #Exec=google-chrome --enable-unsafe-swiftshader #' "$f"
    changed=1
  fi
done

# 3) Salinan Desktop: buat ulang bila hilang / berbeda isi dari sumber.
if [ ! -e "$DESK" ] || ! cmp -s "$SRC" "$DESK"; then
  cp "$SRC" "$DESK"; changed=1
fi

# 3) Izin: harus 755 (bit executable wajib — tanpa itu GNOME menolak & dialog muncul).
for f in "$APPS"/sdb-*.desktop "$DESK"; do
  if [ "$(stat -c '%a' "$f")" != "755" ]; then chmod 755 "$f"; changed=1; fi
done

# 4) GNOME trust: metadata trusted wajib true untuk ikon Desktop.
if [ "$(gio info -a metadata::trusted "$DESK" 2>/dev/null | grep -c 'trusted: true')" -ne 1 ]; then
  gio set "$DESK" metadata::trusted true && changed=1
fi

# 5) Validasi isi .desktop (kalau tool ada).
if command -v desktop-file-validate >/dev/null 2>&1; then
  for f in "$APPS"/sdb-*.desktop; do
    desktop-file-validate "$f" >/dev/null 2>&1 || { echo "sdb-fix-launcher: INVALID: $f" >&2; exit 1; }
  done
fi

[ "$changed" -eq 1 ] && echo "sdb-fix-launcher: perbaikan otomatis diterapkan ($(date '+%F %T'))" \
                    || true
exit 0
