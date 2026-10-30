#!/usr/bin/env python3
"""Penjaga CI: laporkan kegagalan GitHub Actions yang BARU, bukan yang sudah dikenal.

Kenapa ada: pada 30 Okt 2026 CI merah berhari-hari (run 40972713592 -> 40997883099)
karena kegagalan hanya masuk surel yang tidak dibaca. Alat ini menutup celah itu:
- memeriksa run terbaru lewat `gh run list`
- melaporkan HANYA kegagalan yang belum pernah dilihat (idempoten, tanpa spam)
- gagal-closed: bila `gh` tidak bisa dipakai, TIDAK pernah melaporkan "hijau"
  (exit 2 + catatan), sebab "tidak bisa memeriksa" bukan "aman"

Kanal: Telegram bila kredensial tersedia; setiap kejadian SELALU ditulis ke
berkas JSONL (bukti lokal, tidak bergantung jaringan).

Kredensial Telegram, urut prioritas (nilai tidak pernah dicetak):
  1. env SDB_TG_BOT_TOKEN + SDB_TG_CHAT_ID
  2. ~/.config/sdb/control.env (KEY=VALUE, di-parse tanpa dieksekusi)
  3. ~/anantara-sakti/.env -> TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (bot yang sudah ada)

Pakai:
  python3 scripts/ci_watch.py                 # periksa, laporkan yang baru
  python3 scripts/ci_watch.py --dry-run       # periksa & cetak, state tidak ditulis
  python3 scripts/ci_watch.py --status        # ringkasan 20 run terakhir
Exit: 0 bersih/tidak ada yang baru, 1 ada kegagalan baru, 2 pemeriksaan gagal.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.telegram.org"
STATE_DEFAULT = Path("~/.local/state/sdb/ci-watch/state.json").expanduser()
ALERT_DEFAULT = Path("~/.local/state/sdb/ci-watch/alerts.jsonl").expanduser()
ENV_SDB = Path("~/.config/sdb/control.env").expanduser()
ENV_ANANTARA = Path("~/anantara-sakti/.env").expanduser()
POLA_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _bin(nama: str) -> str:
    """Path absolut alat (bukan nama telanjang): tidak menebak dari PATH orang lain."""
    jalur = shutil.which(nama)
    if not jalur:
        raise GhError(f"alat '{nama}' tidak terpasang di PATH")
    return jalur


class GhError(RuntimeError):
    """`gh` tidak bisa dipakai atau keluarannya tidak bisa dipercaya."""


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_dari_git(root: str = ".") -> str:
    """Ambil owner/nama dari remote origin; divalidasi sebelum dipakai sebagai argumen."""
    out = subprocess.run([_bin("git"), "-C", root, "remote", "get-url", "origin"],
                         capture_output=True, text=True, timeout=20)
    if out.returncode != 0:
        raise GhError("remote origin tidak terbaca")
    url = out.stdout.strip()
    m = re.search(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?$", url)
    if not m or not POLA_REPO.match(m.group(1)):
        raise GhError(f"remote origin tidak berbentuk owner/repo: {url[:40]}")
    return m.group(1)


def ambil_runs(repo: str, limit: int = 30) -> list[dict]:
    """`gh run list --json` dengan argv TETAP (repo sudah divalidasi regex)."""
    if not POLA_REPO.match(repo):
        raise GhError(f"nama repo tidak valid: {repo!r}")
    out = subprocess.run(
        [_bin("gh"), "run", "list", "--repo", repo, "--limit", str(int(limit)),
         "--json", "databaseId,conclusion,status,displayTitle,workflowName,headBranch,createdAt,url,event"],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise GhError(f"gh keluar {out.returncode}: {(out.stderr or '').strip()[:200]}")
    try:
        data = json.loads(out.stdout or "[]")
    except json.JSONDecodeError as e:
        raise GhError(f"keluaran gh bukan JSON: {e}") from e
    if not isinstance(data, list):
        raise GhError("keluaran gh bukan larik run")
    return data


def kunci(run: dict) -> str:
    return str(run.get("databaseId") or run.get("url") or "")


def gagal(run: dict) -> bool:
    return run.get("status") == "completed" and str(run.get("conclusion")) not in ("success", "skipped", "neutral")


def pilih_baru(runs: list[dict], sudah: dict[str, dict]) -> list[dict]:
    """Kegagalan selesai yang belum tercatat, terlama dulu (urutan baca manusiawi)."""
    baru = [r for r in runs if kunci(r) and gagal(r) and kunci(r) not in sudah]
    return sorted(baru, key=lambda r: str(r.get("createdAt") or ""))


def muat_state(path: Path) -> dict:
    """State rusak/hilang diperlakukan sebagai kosong, tetapi ditandai agar tidak
    diam-diam dianggap 'belum pernah ada' tanpa terlihat di keluaran."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sudah"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"sudah": {}, "rusak": path.exists()}


def simpan_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def catat(path: Path, kejadian: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(kejadian, ensure_ascii=False) + "\n")


def _parse_env(path: Path, nama: list[str]) -> dict[str, str]:
    """Baca KEY=VALUE tanpa mengeksekusi berkas. Nilai tidak pernah dicetak."""
    hasil: dict[str, str] = {}
    try:
        for baris in path.read_text(encoding="utf-8", errors="replace").splitlines():
            baris = baris.strip()
            if not baris or baris.startswith("#") or "=" not in baris:
                continue
            k, _, v = baris.partition("=")
            k = k.strip().removeprefix("export ").strip()
            if k in nama:
                hasil[k] = v.strip().strip("'\"")
    except OSError:
        return {}
    return hasil


def kredensial() -> tuple[str, str] | None:
    """(token, chat_id) dari sumber pertama yang lengkap; None bila tak ada."""
    t, c = os.environ.get("SDB_TG_BOT_TOKEN", ""), os.environ.get("SDB_TG_CHAT_ID", "")
    if t and c:
        return t, c
    sdb = _parse_env(ENV_SDB, ["SDB_TG_BOT_TOKEN", "SDB_TG_CHAT_ID"])
    if sdb.get("SDB_TG_BOT_TOKEN") and sdb.get("SDB_TG_CHAT_ID"):
        return sdb["SDB_TG_BOT_TOKEN"], sdb["SDB_TG_CHAT_ID"]
    ana = _parse_env(ENV_ANANTARA, ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
    if ana.get("TELEGRAM_BOT_TOKEN") and ana.get("TELEGRAM_CHAT_ID"):
        return ana["TELEGRAM_BOT_TOKEN"], ana["TELEGRAM_CHAT_ID"]
    return None


def kirim_telegram(teks: str, token: str, chat: str) -> bool:
    # Penjaga sebelum urlopen: hanya https ke host tetap. Token tidak pernah dicetak/log.
    url = f"{API}/bot{token}/sendMessage"
    if not url.startswith("https://api.telegram.org/bot"):
        return False
    body = json.dumps({"chat_id": chat, "text": teks, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return bool(json.loads(r.read() or b"{}").get("ok"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return False


def format_pesan(runs: list[dict], judul: str) -> str:
    baris = [f"SDB {judul}", ""]
    for r in runs:
        wf = r.get("workflowName") or "ci"
        cabang = r.get("headBranch") or "?"
        judul_run = (r.get("displayTitle") or "").strip()[:90]
        baris.append(f"- {wf} @ {cabang}: {judul_run}")
        baris.append(f"  {r.get('createdAt', '')} · {r.get('conclusion')} · {r.get('url', '')}")
    return "\n".join(baris)[:3900]


def ringkas_status(runs: list[dict]) -> str:
    if not runs:
        return "tidak ada run"
    return "; ".join(f"{r.get('workflowName') or 'ci'}={r.get('conclusion') or r.get('status')}"
                     for r in runs[:5])


def main(argv: list[str] | None = None, ambil=ambil_runs, kred=kredensial,
         kirim=kirim_telegram) -> int:
    ap = argparse.ArgumentParser(description="Laporkan kegagalan CI GitHub yang baru.")
    ap.add_argument("--repo", default="")
    ap.add_argument("--state", default=str(STATE_DEFAULT))
    ap.add_argument("--alert-file", default=str(ALERT_DEFAULT))
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)

    state_path, alert_path = Path(a.state), Path(a.alert_file)
    state = muat_state(state_path)
    sudah = state["sudah"]

    try:
        repo = a.repo or repo_dari_git()
        runs = ambil(repo, a.limit)
    except (GhError, subprocess.SubprocessError, OSError) as e:
        # Gagal-closed: tidak memeriksa != aman. OSError menangkap `gh`/`git` tidak ada.
        kejadian = {"waktu": _iso(), "jenis": "pemeriksaan_gagal", "sebab": str(e)[:300], "repo": a.repo or "?"}
        if not a.dry_run:
            catat(alert_path, kejadian)
        print(f"GAGAL MEMERIKSA (bukan hijau): {e}", file=sys.stderr)
        return 2

    if a.status:
        print(f"repo={repo} run={len(runs)}\n{ringkas_status(runs)}")
        return 0

    pertama_kali = not sudah and not state.get("rusak")
    baru = pilih_baru(runs, sudah)

    if pertama_kali:
        # Pemasangan pertama: jangan membanjiri dengan kegagalan lama.
        # Tetapi bila HEAD sekarang merah, itu keadaan nyata hari ini -> laporkan sekali.
        terbaru = max(runs, key=lambda r: str(r.get("createdAt") or ""), default=None)
        baru = [terbaru] if terbaru and gagal(terbaru) else []

    for r in runs:
        k = kunci(r)
        if k and k not in sudah:
            sudah[k] = {"conclusion": r.get("conclusion"), "waktu": r.get("createdAt"),
                        "judul": (r.get("displayTitle") or "")[:90]}

    if not baru:
        if not a.dry_run:
            state.update({"diperiksa": _iso(), "repo": repo, "rusak": False})
            simpan_state(state_path, state)
        print(f"BERSIH: tidak ada kegagalan baru ({len(runs)} run diperiksa, {len(sudah)} tercatat)")
        return 0

    pesan = format_pesan(baru, "CI GAGAL (baru)")
    kanal = "berkas"
    k = kred()
    if k and kirim(pesan, *k):
        kanal = "telegram+berkas"
    elif k:
        kanal = "berkas (telegram gagal)"

    kejadian = {"waktu": _iso(), "jenis": "ci_gagal", "repo": repo, "kanal": kanal,
                "runs": [{"id": kunci(r), "conclusion": r.get("conclusion"), "judul": r.get("displayTitle"),
                          "cabang": r.get("headBranch"), "url": r.get("url"), "waktu": r.get("createdAt")}
                         for r in baru]}
    if not a.dry_run:
        catat(alert_path, kejadian)
        state.update({"diperiksa": _iso(), "repo": repo, "rusak": False})
        simpan_state(state_path, state)
    print(pesan)
    print(f"kanal={kanal} dicatat={alert_path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
