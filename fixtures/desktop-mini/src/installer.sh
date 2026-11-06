#!/bin/sh
# Installer fixture — idempoten: salinan hanya ditulis bila hash berbeda.
set -eu
PREFIX="${PREFIX:-$HOME/.local/share/mini-desktop}"
SRC="$(dirname "$0")/desktop-mini"
mkdir -p "$PREFIX"
if [ -f "$PREFIX/desktop-mini" ] && cmp -s "$SRC" "$PREFIX/desktop-mini"; then
  echo "sudah terpasang: $PREFIX/desktop-mini"
  exit 0
fi
cp "$SRC" "$PREFIX/desktop-mini"
chmod 0755 "$PREFIX/desktop-mini"
echo "terpasang: $PREFIX/desktop-mini"
