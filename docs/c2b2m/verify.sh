#!/usr/bin/env bash
# C2-B2M verify — 10 uji akses dengan canary sintetis. Tidak mengubah apa pun.
# Butuh sudo non-interaktif (atau jalankan dalam sesi sudo aktif).
set -uo pipefail

USER_B="sdbbuild"
WS="/srv/sdb-workspace/repo"
CANARY="/home/anashadi/.sdb-canary"
OWNER_HOME="/home/anashadi"
OWNER_REPO="/home/anashadi/super-dev-builders"
fail=0; pass=0
ok()  { pass=$((pass+1)); printf 'PASS  %-42s %s\n' "$1" "${2:-}"; }
no()  { fail=$((fail+1)); printf 'FAIL  %-42s %s\n' "$1" "${2:-}"; }

as_b() { sudo -n -u "$USER_B" bash -lc "$1" 2>&1; }

# 1-4 identitas
uid=$(id -u "$USER_B" 2>/dev/null || echo 0)
[[ "$uid" -ge 1000 ]] && ok "01 uid terbatas" "uid=$uid" || no "01 uid terbatas" "uid=$uid"
grp=$(id -nG "$USER_B" 2>/dev/null | tr ' ' '\n' | grep -Ex 'sdbbuild' || true)
[[ "$grp" == "sdbbuild" ]] && ok "02 grup utama sdbbuild" || no "02 grup utama sdbbuild"
terlarang=$(id -nG "$USER_B" 2>/dev/null | tr ' ' '\n' | grep -Ex 'sudo|docker|lxd|disk|adm' || true)
[[ -z "$terlarang" ]] && ok "03 tanpa grup terlarang" || no "03 tanpa grup terlarang" "$terlarang"

out=$(sudo -n -l -U "$USER_B" 2>&1 || true)
if grep -qi "not allowed to run sudo" <<<"$out"; then ok "04 tanpa sudo"; else no "04 tanpa sudo" "$(head -1 <<<"$out")"; fi

# 5-8 akses negatif ke milik Owner
out=$(as_b "test -r $OWNER_HOME/.hermes && echo BISA || echo TOLAK")
[[ "$out" == *TOLAK ]] && ok "05 tidak baca ~/.hermes" || no "05 tidak baca ~/.hermes" "$out"

out=$(as_b "cat $CANARY/fake_key.pem 2>&1")
grep -qi "permission denied" <<<"$out" && ok "06 tidak baca canary kunci" || no "06 tidak baca canary kunci" "${out:0:60}"

out=$(as_b "cat $CANARY/fake_token.txt 2>&1")
grep -qi "permission denied" <<<"$out" && ok "07 tidak baca canary token" || no "07 tidak baca canary token" "${out:0:60}"

out=$(as_b "touch $OWNER_REPO/.probe_b2m 2>&1")
grep -qi "permission denied" <<<"$out" && ok "08 tidak tulis repo Owner" || no "08 tidak tulis repo Owner" "${out:0:60}"

# 9-10 tidak ada jalur root dan identitas subprocess konsisten
out=$(as_b "sudo -n true 2>&1")
grep -qiE "password|not allowed|a terminal is required" <<<"$out" && ok "09 tanpa jalur sudo" || no "09 tanpa jalur sudo" "${out:0:60}"

out=$(as_b "test -w /var/run/docker.sock && echo BISA || echo TOLAK")
[[ "$out" == *TOLAK ]] && ok "10 tidak akses docker.sock" || no "10 tidak akses docker.sock" "$out"

# 11-12 (bonus) bisa bekerja di workspace dengan identitas sama
out=$(as_b "cd $WS && git rev-parse --short HEAD && python3 -c 'import os;print(os.getuid())'")
headsha=$(head -1 <<<"$out"); subuid=$(tail -1 <<<"$out")
[[ "$headsha" =~ ^[0-9a-f]{7,}$ ]] && ok "11 bisa kerja di workspace" "HEAD=$headsha" || no "11 bisa kerja di workspace" "${out:0:60}"
[[ "$subuid" == "$uid" ]] && ok "12 subprocess identitas sama" "uid=$subuid" || no "12 subprocess identitas sama" "$subuid != $uid"

# 13-16 penutup celah: skills Builder, workspace proyek lain, systemd, proses pekerja
out=$(as_b "test -r $WS/../skills/README.md || ls -1 $WS/../skills | head -1")
[[ -n "$out" ]] && ok "13 baca skills salinan sendiri" "${out:0:28}" || no "13 baca skills salinan sendiri"

out=$(as_b "test -r $OWNER_HOME/vsb && echo BISA || echo TOLAK")
[[ "$out" == *TOLAK ]] && ok "14 tidak baca workspace proyek lain" || no "14 tidak baca workspace proyek lain" "$out"

out=$(as_b "test -w /etc/systemd/system && echo BISA || echo TOLAK")
[[ "$out" == *TOLAK ]] && ok "15 tidak tulis unit systemd" || no "15 tidak tulis unit systemd" "$out"

out=$(as_b "sleep 1 >/dev/null 2>&1 & echo \$!; sleep 0.2; ps -o uid= -p \$! 2>/dev/null")
pid=$(head -1 <<<"$out"); procuid=$(tail -1 <<<"$out" | tr -d ' ')
[[ "$procuid" == "$uid" ]] && ok "16 proses pekerja mewarisi uid" "pid=$pid uid=$procuid" || no "16 proses pekerja mewarisi uid" "uid=${procuid:-?} != $uid"

echo
echo "RINGKASAN: $pass PASS / $fail FAIL"
[[ $fail -eq 0 ]] || exit 1
