#!/usr/bin/env python3
"""Bot Telegram read-only untuk ekosistem SDB (Super Dev Builders).

Desain keamanan:
- READ-ONLY: membaca data/control.db lewat koneksi SQLite mode=ro (secara fisik tak bisa menulis)
  dan health.json Command Deck. Tidak ada perintah yang mengubah uang.
- Hanya chat ID pemilik yang dilayani; chat lain diabaikan diam-diam.
- Long polling (tanpa webhook): tidak membuka port, tanpa butuh TLS/publik.
- Token hanya dibaca dari lingkungan, tidak pernah dicetak.

Kebutuhan: stdlib saja. Kredensial di ~/.config/sdb/control.env:
  SDB_TG_BOT_TOKEN  token bot dari @BotFather
  SDB_TG_CHAT_ID    chat ID pemilik (bilangan)
  SDB_DB_PATH       (opsional) path control.db, default ~/super-dev-builders/data/control.db
  SDB_DECK_STATE    (opsional) path state deck, default ~/super-dev-builders/dashboard/state

Pakai:
  python3 scripts/sdb_tg_bot.py          # polling terus
  python3 scripts/sdb_tg_bot.py --once   # tarik satu batch update, proses, keluar
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.telegram.org"
DB_PATH = Path(os.environ.get("SDB_DB_PATH", "~/super-dev-builders/data/control.db")).expanduser()
DECK_STATE = Path(os.environ.get("SDB_DECK_STATE", "~/super-dev-builders/dashboard/state")).expanduser()
OFFSET_FILE = DECK_STATE / "tg_offset"
TOKEN = os.environ.get("SDB_TG_BOT_TOKEN", "")
OWNER = os.environ.get("SDB_TG_CHAT_ID", "")

HELP = (
    "SDB Bot (read-only)\n"
    "/status  - ringkasan sistem\n"
    "/health  - kesehatan 10 profil agen (Command Deck)\n"
    "/revenue - total tagihan/topup/refund agregat\n"
    "/help    - pesan ini"
)


def _post_api(method: str, payload: dict) -> dict:
    """Panggil Bot API. Token tidak pernah masuk log; galat dicetak tanpa URL."""
    url = f"{API}/bot{TOKEN}/{method}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        # body bisa berisi deskripsi; token TIDAK ada di body, aman dicetak
        return {"ok": False, "description": f"HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError):
        return {"ok": False, "description": "jaringan tak terjangkau"}


def _db_ro() -> sqlite3.Connection | None:
    """Koneksi SQLite read-only; None bila berkas tidak ada."""
    if not DB_PATH.exists():
        return None
    uri = f"file:{urllib.parse.quote(str(DB_PATH))}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5)


def cmd_status() -> str:
    lines = []
    # denyut control plane (opsional — boleh mati)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8088/healthz", timeout=3) as r:
            ok = json.loads(r.read()).get("status") == "ok"
        lines.append("control plane :8088 — " + ("HIDUP" if ok else "jawaban aneh"))
    except (OSError, ValueError) as exc:  # URLError turunan OSError
        lines.append(f"control plane :8088 — mati ({type(exc).__name__}): {exc}")
    # kesehatan deck
    hj = DECK_STATE / "health.json"
    if hj.exists():
        age_h = (time.time() - hj.stat().st_mtime) / 3600
        data = json.loads(hj.read_text())
        n_ok = sum(1 for v in data.values() if isinstance(v, dict) and v.get("ok"))
        lines.append(f"deck: {n_ok}/{len(data)} profil OK, health.json umur {age_h:.1f} jam")
    else:
        lines.append("deck: health.json belum ada (jalankan --health-check)")
    # db
    db = _db_ro()
    if db is None:
        lines.append("control.db: belum ada (jalankan make control-plane sekali)")
    else:
        try:
            n_job = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            n_tenant = db.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
            lines.append(f"db: {n_tenant} tenant, {n_job} job")
        finally:
            db.close()
    return "\n".join(lines)


def cmd_health() -> str:
    hj = DECK_STATE / "health.json"
    if not hj.exists():
        return "health.json belum ada. Jalankan: python3 dashboard/server.py --health-check"
    age_h = (time.time() - hj.stat().st_mtime) / 3600
    if age_h > 14:
        return f"health.json STALE ({age_h:.1f} jam) — timer deck-health macet?"
    data = json.loads(hj.read_text())
    rows = []
    for name, v in data.items():
        if isinstance(v, dict):
            rows.append(f"{'OK ' if v.get('ok') else 'GAGAL'} {name}")
    return f"Kesehatan agen (umur {age_h:.1f} jam):\n" + "\n".join(rows)


def cmd_revenue() -> str:
    db = _db_ro()
    if db is None:
        return "control.db tidak ditemukan — control plane belum pernah jalan di PC ini."
    try:
        row = db.execute(
            "SELECT kind, COUNT(*), SUM(amount) FROM ledger GROUP BY kind ORDER BY kind"
        ).fetchall()
        if not row:
            return "Buku besar masih kosong."
        lines = ["Ringkasan buku besar (agregat, μUSD):"]
        for kind, n, total in row:
            lines.append(f"{kind:<10} n={n:<6} total={total or 0:>12,}")
        return "\n".join(lines)
    except sqlite3.Error as e:
        return f"DB tak terbaca: {e.__class__.__name__}"
    finally:
        db.close()


def handle(text: str) -> str:
    t = text.strip().lower()
    if t.startswith("/status"):
        return cmd_status()
    if t.startswith("/health"):
        return cmd_health()
    if t.startswith("/revenue"):
        return cmd_revenue()
    if t.startswith("/help") or t.startswith("/start"):
        return HELP
    return HELP


def process_update(u: dict) -> None:
    msg = u.get("message") or {}
    chat = str((msg.get("chat") or {}).get("id", ""))
    text = msg.get("text", "")
    if chat != OWNER:
        return  # diam-diam: bukan pemilik
    if not text:
        return
    _post_api("sendMessage", {"chat_id": chat, "text": handle(text)})


def main() -> int:
    if not TOKEN or not OWNER:
        print("SDB_TG_BOT_TOKEN / SDB_TG_CHAT_ID belum diset (source ~/.config/sdb/control.env)",
              file=sys.stderr)
        return 2
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    offset = int(OFFSET_FILE.read_text()) if OFFSET_FILE.exists() else 0
    once = "--once" in sys.argv
    while True:
        res = _post_api("getUpdates", {"offset": offset, "timeout": 30 if not once else 1})
        if res.get("ok"):
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                process_update(u)
            OFFSET_FILE.write_text(str(offset))
        elif once:
            time.sleep(1)
        else:
            time.sleep(5)  # galat jaringan: tunggu, jangan spam
        if once:
            return 0


if __name__ == "__main__":
    sys.exit(main())
