#!/usr/bin/env python3
"""Bot Telegram SDB — laporan otomatis, tanya-jawab, dan perintah build (owner-only).

Desain keamanan:
- control.db dibaca lewat koneksi SQLite mode=ro (secara fisik tak bisa menulis);
  antrean build ditulis terpisah di ~/.local/state/sdb/build_jobs.db
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
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdb_jobs as jobs  # noqa: E402

API = "https://api.telegram.org"
DB_PATH = Path(os.environ.get("SDB_DB_PATH", "~/super-dev-builders/data/control.db")).expanduser()
DECK_STATE = Path(os.environ.get("SDB_DECK_STATE", "~/super-dev-builders/dashboard/state")).expanduser()
OFFSET_FILE = DECK_STATE / "tg_offset"
TOKEN = os.environ.get("SDB_TG_BOT_TOKEN", "")
OWNER = os.environ.get("SDB_TG_CHAT_ID", "")

HELP = (
    "SDB Bot — pemilik saja\n"
    "MONITOR\n"
    "/status /health /revenue — ringkas\n"
    "/eco      — kondisi ekosistem lengkap\n"
    "/projects — progres tiap proyek\n"
    "/ask <tanya> — tanya analis (dijawab dari data nyata)\n"
    "BUILD\n"
    "/build <deskripsi> — ajukan produk (spesifikasi dulu, lalu approve)\n"
    "/jobs /job <id> — daftar & detail\n"
    "/approve <id> — setujui spesifikasi, mulai bangun\n"
    "/revise <id> <arahan> — minta revisi spesifikasi\n"
    "/answer <id> <jawaban> — jawab pertanyaan spesifikasi\n"
    "/reject <id> / /retry <id> / /cancel <id>\n"
    "/help — pesan ini"
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


# --------------------------------------------------------------------------
# lapisan laporan & build (semua aksi hanya untuk pemilik; dibatasi OWNER)
# --------------------------------------------------------------------------
def _arg(text: str, command: str) -> str:
    """Ambil sisa teks setelah /command."""
    body = text.strip()[len(command):].strip()
    return body


def _job_id(text: str, command: str) -> tuple[int, str]:
    body = _arg(text, command)
    parts = body.split(None, 1)
    try:
        return int(parts[0]), (parts[1] if len(parts) > 1 else "")
    except (IndexError, ValueError):
        return 0, body


def _append_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def _ask_hermes(question: str, context: str) -> str:
    """Jawaban analis dari Hermes headless; konteks = laporan nyata, bukan ingatan."""
    prompt = (
        "Kamu analis operasional platform SDB. Jawab pemilik (Mas Anas) dalam bahasa "
        "Indonesia, ringkas tapi lengkap, tanpa basa-basi. Gunakan HANYA angka/fakta dari "
        "DATA di bawah; kalau tidak ada, tulis 'belum ada data'. Jangan mengubah berkas, "
        "jangan menjalankan aksi tulis.\n\nDATA (diambil saat ini):\n"
        f"{context}\n\nPERTANYAAN: {question}\n\nJAWABAN:"
    )
    env = {k: v for k, v in os.environ.items()
           if k not in ("SDB_TG_BOT_TOKEN", "SDB_TG_CHAT_ID", "SDB_ADMIN_KEY")}
    # Toolset minimal: tanpa web/browser/delegation -> analis tidak bisa
    # menjelajah internet atau menyebar aksi; cukup baca berkas + shell baca-saja.
    base = ["hermes", "chat", "-Q", "--oneshot", "--query-file", "-",
            "--max-turns", "20", "--run-budget", "240"]
    try:
        r = subprocess.run(base + ["-t", "terminal,file,skills"], input=prompt,
                           capture_output=True, text=True, timeout=300, env=env)
        if "invalid toolset" in (r.stdout or "") + (r.stderr or ""):
            r = subprocess.run(base, input=prompt, capture_output=True,
                               text=True, timeout=300, env=env)
        out = (r.stdout or "").strip()
        out = "\n".join(l for l in out.splitlines() if not l.startswith("session_id: "))
        return out or "(tidak ada jawaban)"
    except subprocess.TimeoutExpired:
        return "Analisis melebihi 5 menit. Coba pertanyaan lebih spesifik."
    except OSError as e:
        return f"Mesin analis tidak tersedia ({type(e).__name__})."


def cmd_jobs() -> str:
    rows = jobs.list_jobs(12)
    if not rows:
        return "Belum ada job build. Mulai: /build <deskripsi produk>"
    lines = ["JOB BUILD (terbaru dulu)"]
    for j in rows:
        lines.append(f"#{j['id']} [{j['status']}] {j['title'][:52]}")
    lines.append("\n/approve <id> · /job <id> · /build <deskripsi>")
    return "\n".join(lines)


def cmd_job(jid: int) -> str:
    j = jobs.get(jid)
    if not j:
        return f"Job #{jid} tidak ditemukan."
    lines = [f"#{j['id']} [{j['status']}] {j['title']}",
             f"dibuat: {time.strftime('%d %b %H:%M', time.localtime(j['created']))}",
             f"folder: {j['dir']}"]
    if j.get("error"):
        lines.append(f"error: {j['error']}")
    ev = jobs.events(jid, 6)
    if ev:
        lines.append("\nRIWAYAT")
        for e in ev:
            stamp = time.strftime("%d %b %H:%M", time.localtime(e["ts"]))
            lines.append(f"{stamp} {e['kind']}: {e['text'][:220].replace(chr(10), ' ')}")
    return "\n".join(lines)


def cmd_build(brief: str) -> str:
    if len(brief) < 20:
        return ("Deskripsi terlalu pendek. Sertakan: tujuan, pengguna, fitur wajib, "
                "gaya tampilan, dan hal yang TIDAK perlu.\n"
                "Contoh: /build Website katalog villa: daftar villa + filter harga, "
                "halaman detail dengan galeri, form booking WhatsApp, admin CRUD, "
                "mobile-first, warna netral.")
    jid = jobs.create_job(brief)
    return (f"Job #{jid} diterima.\n"
            "Tahap 1: saya susun SPEC.md + PLAN.md + pertanyaan kritis (±2-5 menit).\n"
            "Setelah itu Anda putuskan: /approve " + str(jid) + " untuk mulai membangun.\n"
            "Pantau: /job " + str(jid))


def cmd_approve(jid: int) -> str:
    j = jobs.get(jid)
    if not j:
        return f"Job #{jid} tidak ditemukan."
    if j["status"] != "spec_ready":
        return (f"Job #{jid} berstatus {j['status']} — belum bisa di-approve. "
                "Tunggu sampai 'spec_ready' (/job " + str(jid) + ").")
    jobs.set_status(jid, "build_queued", "disetujui pemilik")
    return f"Job #{jid} disetujui. Implementasi dimulai (10-40 menit). Saya kabari hasilnya."


def cmd_reject(jid: int, why: str) -> str:
    j = jobs.get(jid)
    if not j:
        return f"Job #{jid} tidak ditemukan."
    jobs.set_status(jid, "rejected", why or "ditolak pemilik")
    return f"Job #{jid} ditolak." + (f" Alasan: {why}" if why else "")


def cmd_cancel(jid: int) -> str:
    j = jobs.get(jid)
    if not j:
        return f"Job #{jid} tidak ditemukan."
    if j["status"] in ("done", "cancelled", "rejected"):
        return f"Job #{jid} sudah {j['status']}."
    jobs.set_status(jid, "cancelled", "dibatalkan pemilik")
    return f"Job #{jid} dibatalkan."


def cmd_retry(jid: int) -> str:
    j = jobs.get(jid)
    if not j:
        return f"Job #{jid} tidak ditemukan."
    if j["status"] not in ("failed", "cancelled", "rejected", "paused"):
        return f"Job #{jid} berstatus {j['status']} — tidak perlu retry."
    nxt = "build_queued" if j.get("session_spec") else "spec_queued"
    jobs.set_status(jid, nxt, "retry pemilik")
    return f"Job #{jid} diantrekan ulang ({nxt})."


def cmd_revise(jid: int, arahan: str) -> str:
    j = jobs.get(jid)
    if not j:
        return f"Job #{jid} tidak ditemukan."
    if j["status"] in ("building", "done"):
        return (f"Job #{jid} sudah {j['status']} — revisi lewat job baru, atau tunggu selesai.")
    if not arahan:
        return f"Format: /revise {jid} <arahan revisi>"
    _append_file(Path(j["dir"]) / "ANSWERS.md", f"REVISI: {arahan}")
    jobs.set_status(jid, "spec_queued", f"revisi: {arahan[:300]}")
    return f"Job #{jid} direvisi ulang spesifikasinya. Tunggu notifikasi."


def cmd_answer(jid: int, jawab: str) -> str:
    j = jobs.get(jid)
    if not j:
        return f"Job #{jid} tidak ditemukan."
    if not jawab:
        return f"Format: /answer {jid} <jawaban>"
    _append_file(Path(j["dir"]) / "ANSWERS.md", f"JAWABAN: {jawab}")
    return (f"Jawaban tersimpan untuk job #{jid}. "
            f"Lanjut: /approve {jid} (atau /revise {jid} <arahan>).")


def cmd_eco() -> str:
    import sdb_report
    return sdb_report.report("full")


def cmd_projects() -> str:
    import sdb_report
    return sdb_report.report("projects")


def handle(text: str) -> str:
    t = text.strip().lower()
    if t.startswith("/status"):
        return cmd_status()
    if t.startswith("/health"):
        return cmd_health()
    if t.startswith("/revenue"):
        return cmd_revenue()
    if t.startswith("/eco"):
        return cmd_eco()
    if t.startswith("/projects"):
        return cmd_projects()
    if t.startswith("/ask"):
        q = _arg(text, "/ask")
        if not q:
            return "Format: /ask <pertanyaan>"
        import sdb_report
        return _ask_hermes(q, sdb_report.report("full"))
    if t.startswith("/build"):
        return cmd_build(_arg(text, "/build"))
    if t.startswith("/jobs"):
        return cmd_jobs()
    if t.startswith("/job"):
        jid, _ = _job_id(text, "/job")
        return cmd_job(jid) if jid else "Format: /job <id>"
    if t.startswith("/approve"):
        jid, _ = _job_id(text, "/approve")
        return cmd_approve(jid) if jid else "Format: /approve <id>"
    if t.startswith("/reject"):
        jid, why = _job_id(text, "/reject")
        return cmd_reject(jid, why) if jid else "Format: /reject <id> [alasan]"
    if t.startswith("/cancel"):
        jid, _ = _job_id(text, "/cancel")
        return cmd_cancel(jid) if jid else "Format: /cancel <id>"
    if t.startswith("/retry"):
        jid, _ = _job_id(text, "/retry")
        return cmd_retry(jid) if jid else "Format: /retry <id>"
    if t.startswith("/revise"):
        jid, arahan = _job_id(text, "/revise")
        return cmd_revise(jid, arahan) if jid else "Format: /revise <id> <arahan>"
    if t.startswith("/answer"):
        jid, ans = _job_id(text, "/answer")
        return cmd_answer(jid, ans) if jid else "Format: /answer <id> <jawaban>"
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
    if text.strip().lower().startswith("/ask"):
        _post_api("sendMessage", {"chat_id": chat, "text": "Menganalisis dari data nyata… (±30 dtk)"})
    try:
        reply = handle(text)
    except Exception as e:  # satu perintah rusak tidak boleh mematikan poller
        reply = f"Perintah gagal: {type(e).__name__}: {e}"[:900]
    import sdb_report
    for piece in sdb_report.chunk(reply):
        _post_api("sendMessage", {"chat_id": chat, "text": piece,
                                  "disable_web_page_preview": True})


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
                # simpan tiap pesan: crash saat /ask tidak memutar ulang perintah lama
                OFFSET_FILE.write_text(str(offset))
        elif once:
            time.sleep(1)
        else:
            time.sleep(5)  # galat jaringan: tunggu, jangan spam
        if once:
            return 0


if __name__ == "__main__":
    sys.exit(main())
