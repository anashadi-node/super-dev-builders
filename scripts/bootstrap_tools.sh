#!/usr/bin/env bash
# Bootstrap tool deterministik (PIN versi) — DILARANG jalan tanpa approval manusia.
# Blueprint §9 Phase 5 + §6: pihak ketiga harus lewat gate + approval.
#
# Pemakaian:
#   bash scripts/bootstrap_tools.sh --dry-run          # default: hanya menampilkan rencana
#   bash scripts/bootstrap_tools.sh --install ruff semgrep --yes
#   bash scripts/bootstrap_tools.sh --check
set -euo pipefail

RUFF_PIN="${RUFF_PIN:-0.8.4}"
SEMGREP_PIN="${SEMGREP_PIN:-1.95.0}"
TRIVY_VERSION="${TRIVY_VERSION:-0.58.0}"
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
echo "ruff=$RUFF_PIN semgrep=$SEMGREP_PIN trivy=$TRIVY_VERSION"
echo

if [ "${WANT[0]:-}" = "check" ] || [ ${#WANT[@]} -eq 0 ]; then
  for t in ruff semgrep trivy syft; do
    if command -v "$t" >/dev/null 2>&1; then echo "  OK   $t -> $(command -v "$t")"; else echo "  MISS $t"; fi
  done
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

for t in "${WANT[@]}"; do
  case "$t" in
    ruff)
      run uv tool install "ruff==$RUFF_PIN"
      ;;
    semgrep)
      run uv tool install "semgrep==$SEMGREP_PIN"
      ;;
    trivy)
      echo "Trivy: unduh rilis resmi aquasecurity/trivy v$TRIVY_VERSION, verifikasi checksum SHA256, letakkan di ~/.local/bin"
      echo "  https://github.com/aquasecurity/trivy/releases/tag/v$TRIVY_VERSION"
      ;;
    syft)
      echo "Syft: unduh rilis resmi anchore/syft, verifikasi checksum, letakkan di ~/.local/bin"
      ;;
  esac
done

echo
echo "Selesai. Catat hasil + versi ke registry/tools.yaml dan reports/human-approval-required.md."
