#!/usr/bin/env bash
# Pasang peluncur desktop & handler sdb:// untuk ekosistem SDB — tanpa hak admin.
# Semua berkas di ~/.local/share/applications/, ~/Desktop/, dan ~/.local/bin/.
#
# ROOT-CAUSE GUARD (kasus "Invalid Permissions on Desktop File"):
# Semua .desktop WAJIB chmod 755 + gio trusted (di Desktop), dan diverifikasi
# di akhir skrip — gagal verifikasi = gagal skrip (exit non-zero), bukan peringatan.
set -euo pipefail

BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
REPO="$HOME/super-dev-builders"
mkdir -p "$BIN" "$APPS"

# --- helper CLI ---
cat > "$BIN/sdb-deck" <<'EOF'
#!/usr/bin/env bash
# Buka Command Deck SDB (:8484) setelah memastikan layanannya hidup.
systemctl --user is-active --quiet sdb-command-deck \
  || { echo "sdb-command-deck tidak aktif: systemctl --user start sdb-command-deck"; exit 1; }
exec google-chrome --new-window --app=http://127.0.0.1:8484/
EOF
chmod 700 "$BIN/sdb-deck"

cat > "$BIN/sdb-health" <<'EOF'
#!/usr/bin/env bash
# Kesehatan 10 profil agen: paksa refresh bila health.json basi, lalu tampilkan.
STATE="$HOME/super-dev-builders/dashboard/state/health.json"
if [ ! -f "$STATE" ] || [ "$(find "$STATE" -mmin +180 | wc -l)" -eq 1 ]; then
  (cd "$HOME/super-dev-builders" && python3 dashboard/server.py --health-check >/dev/null 2>&1) \
    || echo "(--health-check gagal; menampilkan berkas lama)"
fi
python3 - "$STATE" <<'PY'
import json, sys, time
from pathlib import Path
p = Path(sys.argv[1])
if not p.exists():
    print("health.json belum ada."); raise SystemExit(0)
d = json.loads(p.read_text())
age = (time.time() - p.stat().st_mtime) / 3600
prof = {k: v for k, v in d.items() if isinstance(v, dict)}
ok = sum(1 for v in prof.values() if v.get("ok"))
print(f"SDB Command Deck — {ok}/{len(prof)} profil OK (health.json {age:.1f} jam)")
for name, v in sorted(d.items()):
    if isinstance(v, dict):
        print(f"  {'OK ' if v.get('ok') else 'GAGAL'} {name}")
PY
EOF
chmod 700 "$BIN/sdb-health"

# --- peluncur .desktop ---
cat > "$APPS/sdb-tutorial.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=SDB Tutorial
GenericName=Super Dev Builders Tutorial
Comment=Panduan lengkap SDB (produk berbayar): semua skenario penggunaan
Exec=google-chrome --new-window file://$REPO/docs/TUTORIAL_PENGGUNAAN.html
Icon=text-html
Terminal=false
Categories=Development;Documentation;
Keywords=sdb;tutorial;super dev builders;
EOF

cat > "$APPS/sdb-tutorial-personal.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=SDB Tutorial Pribadi
GenericName=Panduan Pribadi Super Dev Builders
Comment=Panduan pemakaian pribadi di PC ini + bot Telegram (read-only)
Exec=google-chrome --new-window file://$REPO/docs/TUTORIAL_PRIBADI.html
Icon=text-html
Terminal=false
Categories=Development;Documentation;
Keywords=sdb;pribadi;telegram;
EOF

cat > "$APPS/sdb-health.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=SDB Health
GenericName=Kesehatan 10 Profil Agen SDB
Comment=PONG seluruh profil agen Command Deck, hasil di terminal
Exec=$BIN/sdb-health
Icon=utilities-system-monitor
Terminal=true
Categories=Development;
Keywords=sdb;health;kesehatan;
EOF

# --- handler URL sdb:// (buka deck dari browser/CLI mana pun) ---
cat > "$BIN/sdb-open" <<'EOF'
#!/usr/bin/env bash
# sdb://deck -> buka Command Deck. Dipanggil oleh handler sdb://.
case "${1:-}" in
  sdb://deck|sdb://deck/) exec google-chrome --new-window --app=http://127.0.0.1:8484/ ;;
  *) echo "sdb:// belum didukung: $1 (yang ada: sdb://deck)" >&2; exit 1 ;;
esac
EOF
chmod 700 "$BIN/sdb-open"

# --- peluncur utama di Desktop (satu sumber: APPS lalu hardlink ke Desktop) ---
cat > "$APPS/sdb-command-deck.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Version=1.0
Name=SDB Command Deck
GenericName=Super Dev Builders Dashboard
Comment=Dashboard lokal Super Dev Builders — 12 divisi, 10 profil, routing 4 model (bisa dibuka dari HP via WiFi)
Exec=google-chrome --new-window --app=http://127.0.0.1:8484/
Icon=utilities-system-monitor
Terminal=false
Categories=Development;
Keywords=dashboard;super dev builders;hermes;SDB;
StartupWMClass=SDB Command Deck
X-GNOME-UsesNotifications=false
EOF
# --- handler URL sdb:// (buka deck dari browser/CLI mana pun) ---
cat > "$APPS/sdb-url.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=SDB URL Handler
Comment=Pembuka sdb:// (mis. sdb://deck membuka Command Deck)
Exec=$BIN/sdb-open %u
Icon=applications-internet
Terminal=false
NoDisplay=true
MimeType=x-scheme-handler/sdb;
Categories=Development;
EOF

# Salin (bukan symlink — GNOME ding paling andal dengan berkas nyata) ke Desktop.
DESKTOP_FILE="$HOME/Desktop/sdb-command-deck.desktop"
cp "$APPS/sdb-command-deck.desktop" "$DESKTOP_FILE"

chmod 755 "$APPS"/*.desktop "$DESKTOP_FILE"
# GNOME: ikon di Desktop butuh metadata trusted agar tak muncul "Invalid Permissions"/X merah.
gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true

update-desktop-database "$APPS" 2>/dev/null || true
xdg-mime default sdb-url.desktop x-scheme-handler/sdb 2>/dev/null || true

# --- VERIFIKASI WAJIB (fail-loud, bukan peringatan) ---
FAIL=0
for f in "$APPS"/sdb-*.desktop; do
  if ! desktop-file-validate "$f" >/dev/null 2>&1; then
    echo "GAGAL validasi: $f" >&2; desktop-file-validate "$f" >&2 || true; FAIL=1
  fi
  [ -x "$f" ] || { echo "GAGAL: $f tidak executable" >&2; FAIL=1; }
done
if [ ! -e "$DESKTOP_FILE" ]; then echo "GAGAL: $DESKTOP_FILE hilang" >&2; FAIL=1; fi
[ "$FAIL" -eq 0 ] || { echo "install_shortcuts: VERIFIKASI GAGAL" >&2; exit 1; }

echo "Terpasang:"
ls -1 "$APPS"/sdb-*.desktop | sed "s|.*/|  |"
echo "  Desktop    : sdb-command-deck.desktop (salinan dari $APPS, trusted)"
echo "  ~/.local/bin: sdb-deck, sdb-health, sdb-open"
echo "Cek handler:  xdg-mime query default x-scheme-handler/sdb  (harus: sdb-url.desktop)"
