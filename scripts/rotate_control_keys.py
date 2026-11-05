#!/usr/bin/env python3
"""Rotasi kredensial control-plane SDB tanpa pernah mencetak nilainya.

Yang dirotasi: SDB_ADMIN_KEY dan SDB_WORKER_KEY di ~/.config/sdb/control.env.
Nilai lama disimpan hanya di berkas cadangan bermode 0600 untuk keperluan uji
penolakan (bukan untuk dipakai lagi).

Alur (fail-closed):
  1. baca env, cadangkan ke <env>.bak-<stamp> (0600)
  2. tulis nilai baru secara atomik (tmp 0600 -> os.replace), kunci lain utuh
  3. (opsional) restart unit systemd yang memuat EnvironmentFile
  4. (opsional) buktikan: kunci BARU -> 200, kunci LAMA -> 401, /healthz -> 200

Contoh:
  python3 scripts/rotate_control_keys.py --dry-run
  python3 scripts/rotate_control_keys.py \
      --restart sdb-control-plane --restart sdb-build-worker --restart sdb-tg-bot \
      --verify-url http://127.0.0.1:8088/v1/admin/revenue --verify-header X-Admin-Key \
      --verify-url http://127.0.0.1:8088/v1/worker/claim --verify-header X-Worker-Key \
      --verify-method POST --verify-body '{"worker_id":"rotate-check"}'

Keamanan: tidak ada jalur kode yang mencetak nilai kredensial; keluaran hanya
nama kunci, panjang, dan status (BERUBAH/UTUH). Stdlib saja.
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ENV = Path("~/.config/sdb/control.env").expanduser()
ROTATED = ("SDB_ADMIN_KEY", "SDB_WORKER_KEY")


def parse_env(text: str) -> list[tuple[str, str]]:
    """Ubah env jadi token (jenis, isi); komentar/baris kosong dipertahankan."""
    tokens: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            tokens.append(("raw", line))
            continue
        key, value = stripped.split("=", 1)
        tokens.append(("kv", f"{key.strip()}={value.strip()}"))
    return tokens


def env_values(tokens: list[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for kind, body in tokens:
        if kind == "kv" and "=" in body:
            key, value = body.split("=", 1)
            out[key] = value
    return out


def rotate_tokens(tokens: list[tuple[str, str]], keys=ROTATED,
                  generator=None) -> tuple[list[tuple[str, str]], dict[str, tuple[str, str]]]:
    """Ganti nilai `keys` dengan nilai baru; kembalikan token baru + peta perubahan."""
    generator = generator or (lambda: secrets.token_urlsafe(32))
    changed: dict[str, tuple[str, str]] = {}
    fresh = {key: generator() for key in keys}
    for key, value in fresh.items():
        if len(value) < 32:
            raise ValueError(f"nilai baru untuk {key} terlalu pendek ({len(value)} karakter)")
    new_tokens: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, body in tokens:
        if kind == "kv" and "=" in body:
            key, old = body.split("=", 1)
            if key in fresh:
                new_tokens.append(("kv", f"{key}={fresh[key]}"))
                changed[key] = (old, fresh[key])
                seen.add(key)
                continue
        new_tokens.append((kind, body))
    for key in fresh:
        if key not in seen:
            new_tokens.append(("kv", f"{key}={fresh[key]}"))
            changed[key] = ("", fresh[key])
    return new_tokens, changed


def render(tokens: list[tuple[str, str]]) -> str:
    return "\n".join(body for _kind, body in tokens) + "\n"


def write_atomic(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    os.chmod(path, mode)


def backup(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, dest)
    os.chmod(dest, 0o600)
    return dest


def probe(url: str, header: str, key: str, method: str = "GET", body: bytes | None = None,
          timeout: float = 6.0) -> int:
    """Kirim satu permintaan; kembalikan status HTTP (0 bila koneksi gagal)."""
    req = urllib.request.Request(url, method=method, data=body,
                                 headers={header: key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError):
        return 0


def restart_units(units: list[str]) -> list[tuple[str, str]]:
    results = []
    for unit in units:
        done = subprocess.run(["systemctl", "--user", "restart", unit],
                              capture_output=True, text=True)
        state = subprocess.run(["systemctl", "--user", "is-active", unit],
                               capture_output=True, text=True).stdout.strip()
        results.append((unit, state if done.returncode == 0 else f"gagal ({done.stderr.strip()[:60]})"))
    return results


def failure(msg: str) -> str:
    return f"[ROTASI] GAGAL: {msg}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Rotasi SDB_ADMIN_KEY/SDB_WORKER_KEY tanpa mencetak nilainya")
    ap.add_argument("--env", default=str(DEFAULT_ENV))
    ap.add_argument("--dry-run", action="store_true", help="hitung perubahan, jangan tulis/restart")
    ap.add_argument("--restart", action="append", default=[], metavar="UNIT")
    ap.add_argument("--verify-url", action="append", default=[], metavar="URL")
    ap.add_argument("--verify-header", action="append", default=[], metavar="HEADER")
    ap.add_argument("--verify-method", default="GET")
    ap.add_argument("--verify-body", default="")
    ap.add_argument("--backup", help="berkas env lama untuk uji penolakan (default: cadangan baru)")
    ap.add_argument("--healthz", default="http://127.0.0.1:8088/healthz")
    args = ap.parse_args(argv)

    env_path = Path(args.env).expanduser()
    if not env_path.is_file():
        print(failure(f"berkas env tidak ada: {env_path}"))
        return 2

    tokens = parse_env(env_path.read_text())
    before = env_values(tokens)
    if not any(key in before for key in ROTATED):
        print(failure("tidak ada kunci yang bisa dirotasi di berkas env"))
        return 2

    new_tokens, changed = rotate_tokens(tokens)
    for key in ROTATED:
        old, new = changed.get(key, ("", ""))
        print(f"{key:16} panjang_lama={len(old):3} panjang_baru={len(new):3} status="
              f"{'BERUBAH' if new and new != old else 'TIDAK ADA'}")

    if args.dry_run:
        print("[ROTASI] dry-run: berkas tidak diubah, service tidak direstart")
        return 0

    kept = backup(env_path)
    write_atomic(env_path, render(new_tokens))
    print(f"[ROTASI] env ditulis (0600), cadangan: {kept.name} (0600)")

    for unit, state in restart_units(args.restart):
        print(f"[ROTASI] restart {unit}: {state}")

    if args.verify_url:
        ok = True
        old_tokens = parse_env(Path(args.backup).expanduser().read_text()) if args.backup \
            else parse_env(kept.read_text())
        old_values = env_values(old_tokens)
        headers = args.verify_header or []
        body = args.verify_body.encode() if args.verify_body else None
        for url, header in zip(args.verify_url, headers):
            key_name = "SDB_ADMIN_KEY" if "Admin" in header else "SDB_WORKER_KEY"
            old_key = old_values.get(key_name, "")
            new_status = probe(url, header, changed[key_name][1], args.verify_method, body)
            old_status = probe(url, header, old_key, args.verify_method, body)
            good = new_status in (200, 201, 204) and old_status == 401
            ok &= good
            print(f"[ROTASI] {url} [{header}]: baru={new_status} lama={old_status} "
                  f"-> {'OK' if good else 'TIDAK VALID'}")
            if not old_key:
                print("[ROTASI] peringatan: kunci lama tidak ditemukan di cadangan")

    health = probe(args.healthz, "X-Probe", "-")
    print(f"[ROTASI] healthz={health}")
    if health != 200 and args.verify_url:
        print(failure("control plane tidak sehat setelah rotasi"))
        return 1
    if args.verify_url and not ok:
        print(failure("kunci baru tidak diterima atau kunci lama masih diterima"))
        return 1
    print("[ROTASI] selesai")
    return 0


if __name__ == "__main__":
    sys.exit(main())
