#!/usr/bin/env bash
# C2-B2M apply — MEMBUAT user/group/workspace. Butuh dua kunci eksplisit:
#   SDB_B2M_APPLY=1 SDB_B2M_CONFIRM="SETUJU-B2M" docs/c2b2m/apply.sh
# Tanpa keduanya skrip berhenti sebelum menyentuh sistem.
set -euo pipefail

USER_B="sdbbuild"
WS="/srv/sdb-workspace"
CANARY="/home/anashadi/.sdb-canary"
SRC_REPO="/home/anashadi/super-dev-builders"

[[ "${SDB_B2M_APPLY:-0}" == "1" && "${SDB_B2M_CONFIRM:-}" == "SETUJU-B2M" ]] || {
  echo "DITOLAK: set SDB_B2M_APPLY=1 dan SDB_B2M_CONFIRM=SETUJU-B2M (approval Owner)." >&2
  exit 2
}
[[ $EUID -eq 0 ]] || { echo "DITOLAK: jalankan dengan sudo (butuh useradd)." >&2; exit 2; }

log() { printf '[apply] %s\n' "$*"; }

# 0. prasyarat: preflight harus bersih
/home/anashadi/super-dev-builders/docs/c2b2m/preflight.sh || {
  echo "DITOLAK: preflight gagal." >&2; exit 3; }

# 1. grup + user, tanpa shell login interaktif kebutuhan root, tanpa sudo
getent group "$USER_B" >/dev/null || groupadd --system "$USER_B"
if ! getent passwd "$USER_B" >/dev/null; then
  useradd --create-home --shell /bin/bash --gid "$USER_B" \
          --comment "SDB restricted builder (A')" "$USER_B"
fi
usermod -d "/home/$USER_B" "$USER_B"
extra=$(id -nG "$USER_B" | tr ' ' '\n' | grep -Evx "$USER_B" || true)
[[ -z "$extra" ]] || { echo "DITOLAK: grup tambahan pada $USER_B: $extra" >&2; exit 4; }
passwd -l "$USER_B" >/dev/null                 # tanpa password: login hanya via sudo -u
chmod 0750 "/home/$USER_B"
log "user $USER_B uid=$(id -u "$USER_B") grup=$(id -nG "$USER_B")"

# 2. workspace terpisah (TIDAK memakai ACL rekursif ke home Owner)
install -d -m 0750 -o "$USER_B" -g "$USER_B" "$WS" "$WS/out"
if [[ ! -d "$WS/repo/.git" ]]; then
  git clone --quiet "$SRC_REPO" "$WS/repo"
  chown -R "$USER_B:$USER_B" "$WS/repo"
fi
chmod 0750 "$WS/repo"
log "workspace siap: $WS/repo (HEAD=$(git -C "$WS/repo" rev-parse --short HEAD))"

# 2b. skills & tools yang boleh dipakai builder — SALINAN, bukan symlink ke ~/.hermes
#     (symlink akan membuat builder membaca profil Owner; salinan menjaga batas).
if [[ ! -d "$WS/skills" ]]; then
  install -d -m 0750 -o "$USER_B" -g "$USER_B" "$WS/skills"
  cp -a "$SRC_REPO/skills/." "$WS/skills/"
  chown -R "$USER_B:$USER_B" "$WS/skills"
fi

# 2c. venv sendiri: builder tidak boleh memakai .venv Owner (tidak terbaca, dan
#     memakainya berarti eksekusi kode dengan pustaka milik Owner).
if [[ ! -x "$WS/venv/bin/python" ]]; then
  python3 -m venv "$WS/venv"
  chown -R "$USER_B:$USER_B" "$WS/venv"
fi
log "skills + venv builder siap: $WS/skills, $WS/venv"


# 3. canary sintetis (BUKAN rahasia asli) untuk uji akses negatif
install -d -m 0700 -o anashadi -g anashadi "$CANARY"
printf 'CANARY-SINTETIS-JANGAN-DIPAKAI\n' > "$CANARY/fake_key.pem"
printf 'CANARY-SINTETIS-JANGAN-DIPAKAI\n' > "$CANARY/fake_token.txt"
chmod 0600 "$CANARY/fake_key.pem" "$CANARY/fake_token.txt"
chown anashadi:anashadi "$CANARY"/*
log "canary sintetis dibuat di $CANARY"

# 4. verifikasi cepat bahwa builder benar-benar terbatas
sudo -u "$USER_B" bash -lc '
  set -e
  id -nG | tr " " "\n" | grep -Ex "sudo|docker|lxd|disk" && { echo "GAGAL grup terlarang"; exit 1; }
  test "$(whoami)" = sdbbuild
  python3 -c "import os,sys; sys.exit(0 if os.getuid()!=0 else 1)"
'
log "SELESAI. Jalankan docs/c2b2m/verify.sh untuk 10 uji penuh."
