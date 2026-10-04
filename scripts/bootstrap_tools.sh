#!/usr/bin/env bash
# Bootstrap tool deterministik — PIN versi + VERIFIKASI CHECKSUM. DILARANG jalan tanpa approval manusia.
# Blueprint §6 (supply chain) + §9 Phase 5. Tidak ada `curl | sh` di mana pun.
#
# Pemakaian:
#   bash scripts/bootstrap_tools.sh --check                      # hanya status (default)
#   bash scripts/bootstrap_tools.sh --install ruff semgrep --yes # setelah approval manusia
#   bash scripts/bootstrap_tools.sh --install trivy syft --yes
#
# Pin di bawah harus diperbarui eksplisit (bukan "latest") agar build reproducible:
#   ruff/semgrep -> https://pypi.org/pypi/<pkg>/json
#   trivy/syft   -> https://api.github.com/repos/<owner>/<repo>/releases/latest
set -euo pipefail

RUFF_PIN="${RUFF_PIN:-0.16.10}"
SEMGREP_PIN="${SEMGREP_PIN:-1.179.0}"
TRIVY_VERSION="${TRIVY_VERSION:-0.75.0}"
SYFT_VERSION="${SYFT_VERSION:-1.54.0}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"

DRY_RUN=1
APPROVED=0
declare -a WANT=()

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --check) DRY_RUN=1; WANT=(check) ;;
    --install) DRY_RUN=0 ;;
    --yes) APPROVED=1 ;;
    ruff|semgrep|trivy|syft) WANT+=("$arg") ;;
    *) echo "argumen tidak dikenal: $arg" >&2; exit 2 ;;
  esac
done

echo "== Bootstrap tools (pin versi) =="
echo "ruff=$RUFF_PIN semgrep=$SEMGREP_PIN trivy=$TRIVY_VERSION syft=$SYFT_VERSION"
echo "target bin: $BIN_DIR"
echo

status() {
  for t in ruff semgrep trivy syft; do
    if command -v "$t" >/dev/null 2>&1; then
      printf '  OK   %-8s %s (%s)\n' "$t" "$(command -v "$t")" "$("$t" --version 2>&1 | head -1)"
    else
      printf '  MISS %-8s\n' "$t"
    fi
  done
}

if [ "${WANT[0]:-}" = "check" ] || [ ${#WANT[@]} -eq 0 ]; then
  status
  echo
  echo "Jalankan dengan --install <tool> --yes setelah approval manusia (lihat reports/human-approval-required.md)."
  exit 0
fi

if [ "$DRY_RUN" -eq 0 ] && [ "$APPROVED" -ne 1 ]; then
  echo "DITOLAK: butuh approval manusia -> tambahkan --yes setelah persetujuan tercatat." >&2
  exit 3
fi

run() {
  echo "+ $*"
  if [ "$DRY_RUN" -eq 0 ]; then "$@"; fi
}

# --- tool Python via uv (reproducible, tidak menyentuh python sistem) ---
install_pypi_tool() {
  local pkg="$1" ver="$2"
  run uv tool install --force "$pkg==$ver"
}

# --- binari GitHub releases: unduh -> verifikasi SHA256 -> pasang (TANPA pipe ke shell) ---
install_gh_binary() {
  local owner="$1" repo="$2" tag="$3" asset="$4" checksums="$5" member="$6" binname="$7"
  local base="https://github.com/$owner/$repo/releases/download/$tag"
  local tmp; tmp="$(mktemp -d)"
  echo "+ unduh $base/$asset"
  echo "+ unduh $base/$checksums  (verifikasi SHA256 wajib)"
  echo "+ tar -xzf -> ambil '$member' -> pasang ke $BIN_DIR/$binname"
  if [ "$DRY_RUN" -eq 0 ]; then
    curl -fsSL -o "$tmp/$asset" "$base/$asset"
    curl -fsSL -o "$tmp/$checksums" "$base/$checksums"
    ( cd "$tmp" && grep " $asset\$" "$checksums" | sha256sum -c - )
    tar -xzf "$tmp/$asset" -C "$tmp" "$member"
    install -m 0755 "$tmp/$member" "$BIN_DIR/$binname"
    rm -rf "$tmp"
    echo "  terpasang: $BIN_DIR/$binname"
  fi
}

for t in "${WANT[@]}"; do
  case "$t" in
    ruff)    install_pypi_tool ruff "$RUFF_PIN" ;;
    semgrep) install_pypi_tool semgrep "$SEMGREP_PIN" ;;
    trivy)
      install_gh_binary aquasecurity trivy "v$TRIVY_VERSION" \
        "trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" "trivy_${TRIVY_VERSION}_checksums.txt" trivy trivy
      ;;
    syft)
      install_gh_binary anchore syft "v$SYFT_VERSION" \
        "syft_${SYFT_VERSION}_linux_amd64.tar.gz" "syft_${SYFT_VERSION}_checksums.txt" syft syft
      ;;
  esac
done

echo
if [ "$DRY_RUN" -eq 0 ]; then
  status
fi
echo "Catat versi + jalur bukti ke registry/tools.yaml dan reports/."
