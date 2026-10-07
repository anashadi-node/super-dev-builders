#!/usr/bin/env bash
# Copot pemasangan Super Dev Builders (skill di semua profil + perintah `sdb`).
#
# Ini pembungkus tipis ke `install.sh --uninstall` supaya logika pemasangan hanya
# ada di SATU tempat. Menduplikasi logika copot di dua berkas berarti dua tempat
# yang bisa menyimpang — sumber bug klasik pada installer.
#
# Pemakaian:
#   ./uninstall.sh                # dry-run (tidak mengubah apa pun)
#   ./uninstall.sh --apply        # benar-benar copot
#   ./uninstall.sh --apply --main-only
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/install.sh" --uninstall "$@"