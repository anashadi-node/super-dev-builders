#!/usr/bin/env python3
"""Mesin laporan ekosistem SDB — deterministik, read-only, stdlib saja.

Dipakai untuk:
  * report otomatis tiap 4 jam (timer sdb-report-4h -> --send 4h)
  * jawaban /eco /projects di bot Telegram (--print full / --print projects)
  * konteks grounding untuk /ask (--json)

Prinsip:
- READ-ONLY ke repo/proyek. Satu-satunya tulisan: snapshot JSON di dashboard/state/
  (untuk menghitung delta antar report).
- Tidak pernah mencetak nilai rahasia; hanya nama/struktur/statistik.
- Angka yang tidak bisa diverifikasi ditandai "n/a", bukan dikarang.

Pakai:
    python3 scripts/sdb_report.py --print 4h
    python3 scripts/sdb_report.py --print full
    python3 scripts/sdb_report.py --print projects
    python3 scripts/sdb_report.py --json
    python3 scripts/sdb_report.py --send 4h        # kirim ke Telegram (butuh env token)
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(os.environ.get("SDB_REPO", "~/super-dev-builders")).expanduser()
DECK_STATE = Path(os.environ.get("SDB_DECK_STATE", str(REPO / "dashboard/state"))).expanduser()
DB_PATH = Path(os.environ.get("SDB_DB_PATH", str(REPO / "data/control.db"))).expanduser()
BUILDS = Path(os.environ.get("SDB_BUILDS", "~/sdb-builds")).expanduser()
SNAP = DECK_STATE / "report_snapshot.json"
WIB = timezone(timedelta(hours=7))
ACTIVE_DAYS = 21
TG_LIMIT = 3900

SERVICES = ["sdb-control-plane", "sdb-tg-bot", "sdb-command-deck",
            "sdb-build-worker", "hermes-gateway"]
TIMERS = ["sdb-ci-watch", "sdb-deck-health", "sdb-report-4h"]


# ---------- util ----------
def now() -> datetime:
    return datetime.now(WIB)


def box(text: str, width: int = 44) -> str:
    line = "─" * width
    return f"{line}\n{text}\n{line}"


def human_age(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 90:
        return f"{s} detik"
    if s < 5400:
        return f"{s // 60} menit"
    if s < 172800:
        return f"{s // 3600} jam"
    return f"{s // 86400} hari"


def du_bytes(p: Path) -> int:
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 12) -> str:
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                           text=True, timeout=timeout)
        return p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------- proyek ----------
def read_tasks(tasks_json: Path) -> tuple[int, int, list[str]]:
    """(selesai, total, id tugas terbuka) — tahan berkas rusak."""
    try:
        d = json.loads(tasks_json.read_text())
    except (OSError, ValueError):
        return 0, 0, []
    tugas = d.get("tugas") if isinstance(d, dict) else None
    if not isinstance(tugas, list):
        return 0, 0, []
    done = sum(1 for t in tugas if isinstance(t, dict) and str(t.get("status", "")).lower() in
               ("selesai", "done", "completed", "closed"))
    open_ids = [str(t.get("id")) for t in tugas
                if isinstance(t, dict) and str(t.get("status", "")).lower() not in
                ("selesai", "done", "completed", "closed")]
    return done, len(tugas), open_ids


def git_info(path: Path) -> dict:
    """Commit terakhir + jumlah commit 24 jam, bila path di dalam repo git."""
    root = run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    if not root:
        return {}
    info = {"repo": Path(root).name}
    info["head"] = run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"])
    subject = run(["git", "-C", str(path), "log", "-1", "--pretty=%s|%ct|%cr"])
    if "|" in subject:
        subj, ts, rel = subject.split("|", 2)
        info.update(subject=subj[:70], commit_ts=int(ts), commit_ago=rel)
    info["dirty"] = bool(run(["git", "-C", str(path), "status", "--porcelain"]))
    last7 = run(["git", "-C", str(path), "log", "--since=7.days", "--oneline"])
    info["commit_7d"] = len([ln for ln in last7.splitlines() if ln.strip()])
    return info


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "build",
             "dist", ".next", ".nuxt", "target", "obj", ".gradle", ".m2", "vendor"}


def iter_files(path: Path):
    """Iterasi berkas proyek tanpa direktori dependensi/build (biar angka jujur)."""
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".cache")]
        for n in names:
            yield Path(root) / n


def project_entry(name: str, path: Path) -> dict | None:
    files: int = 0
    loc: int = 0
    newest: float = 0.0
    for f in iter_files(path):
        if not f.is_file():
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        files += 1
        newest = max(newest, st.st_mtime)
        if f.suffix in (".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".java",
                        ".kt", ".go", ".rs", ".sh", ".md", ".json", ".yaml", ".yml"):
            try:
                with f.open("rb") as fh:
                    loc += fh.read().count(b"\n")
            except OSError:
                pass
    done = total = 0
    open_ids: list[str] = []
    tj = path / "tasks.json"
    if tj.exists():
        done, total, open_ids = read_tasks(tj)
    ent = {
        "nama": name,
        "path": str(path),
        "files": files,
        "loc": loc,
        "size": du_bytes(path),
        "mtime": newest,
        "umur_jam": round((time.time() - newest) / 3600, 1) if newest else None,
        "tugas_selesai": done,
        "tugas_total": total,
        "tugas_terbuka": open_ids[:6],
        "git": git_info(path),
    }
    ent["aktif"] = bool(newest) and (time.time() - newest) < ACTIVE_DAYS * 86400
    return ent if files else None  # folder kosong (mis. antrean build) bukan proyek


def collect_projects() -> list[dict]:
    seen: dict[str, Path] = {}
    for base, tag in ((REPO / "targets", ""), (BUILDS, "")):
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir() and not d.name.startswith("."):
                    seen[f"{d.name}{tag}"] = d
    rp = REPO / "runs"
    if rp.is_dir():
        for d in sorted(rp.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                seen.setdefault(d.name, d)
    out = [e for n, p in seen.items() if (e := project_entry(n, p))]
    out.sort(key=lambda e: (not e["aktif"], -(e["mtime"] or 0)))
    return out


# ---------- ekosistem ----------
def svc_state(unit: str) -> dict:
    act = run(["systemctl", "--user", "is-active", unit]) or "unknown"
    en = run(["systemctl", "--user", "is-enabled", unit]) or "unknown"
    return {"unit": unit, "active": act, "enabled": en}


def timer_table() -> dict:
    """Peta unit -> {next, last} (epoch detik) dari list-timers --output=json."""
    raw = run(["systemctl", "--user", "list-timers", "--all", "--output=json"], timeout=15)
    try:
        rows = json.loads(raw or "[]")
    except ValueError:
        return {}
    out = {}
    for r in rows:
        if not isinstance(r, dict) or not r.get("unit"):
            continue
        out[r["unit"]] = {"next": (r.get("next") or 0) / 1_000_000 or None,
                          "last": (r.get("last") or 0) / 1_000_000 or None}
    return out


def timer_state(unit: str, table: dict) -> dict:
    t = table.get(unit + ".timer", {})
    last = t.get("last")
    return {"unit": unit + ".timer", "next": t.get("next"), "last": last,
            "ago": human_age(time.time() - last) if last else "belum pernah"}


def deck_health() -> dict:
    hj = DECK_STATE / "health.json"
    if not hj.exists():
        return {"ada": False}
    age = time.time() - hj.stat().st_mtime
    try:
        data = json.loads(hj.read_text())
    except ValueError:
        return {"ada": False, "rusak": True}
    profiles = {k: v for k, v in data.items() if isinstance(v, dict)}
    bad = [k for k, v in profiles.items() if not v.get("ok")]
    return {"ada": True, "umur_jam": round(age / 3600, 1), "total": len(profiles),
            "ok": len(profiles) - len(bad), "gagal": bad}


def control_db() -> dict:
    info: dict = {"ada": DB_PATH.exists()}
    if not info["ada"]:
        return info
    try:
        db = sqlite3.connect(f"file:{urllib.parse.quote(str(DB_PATH))}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as e:
        info["galat"] = e.__class__.__name__
        return info
    try:
        info["tenant"] = db.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
        rows = db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
        info["job"] = {s: n for s, n in rows}
        info["ledger"] = db.execute(
            "SELECT kind, COUNT(*), COALESCE(SUM(amount),0) FROM ledger GROUP BY kind").fetchall()
    except sqlite3.Error as e:
        info["galat"] = e.__class__.__name__
    finally:
        db.close()
    return info


def host_state() -> dict:
    load = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
    du = shutil.disk_usage(str(Path.home()))
    mem = {"total": 0, "avail": 0}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem["total"] = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                mem["avail"] = int(line.split()[1]) * 1024
    except OSError:
        pass
    return {"load1": round(load, 2) if load is not None else None,
            "disk_pakai_pct": round(100 * du.used / du.total),
            "ram_pakai_pct": round(100 * (1 - mem["avail"] / mem["total"])) if mem["total"] else None}


def open_jobs(limit: int = 5) -> list[dict]:
    """Job build yang belum selesai (dari antrean worker), untuk laporan."""
    try:
        import sdb_jobs
        return sdb_jobs.list_jobs(limit, only_open=True)
    except Exception:  # noqa: BLE001 — DB belum ada/belum siap: laporan tetap jalan tanpa job
        return []


def build_queue() -> dict:
    db = Path(os.environ.get("SDB_BUILD_DB", "~/.local/state/sdb/build_jobs.db")).expanduser()
    if not db.exists():
        return {"ada": False}
    try:
        con = sqlite3.connect(f"file:{urllib.parse.quote(str(db))}?mode=ro", uri=True, timeout=5)
        rows = con.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
        con.close()
        return {"ada": True, "status": {s: n for s, n in rows}}
    except sqlite3.Error:
        return {"ada": False}


# ---------- snapshot & delta ----------
def load_snap() -> dict:
    try:
        return json.loads(SNAP.read_text())
    except (OSError, ValueError):
        return {}


def save_snap(snap: dict) -> None:
    SNAP.parent.mkdir(parents=True, exist_ok=True)
    tmp = SNAP.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False))
    tmp.replace(SNAP)


def delta(prev: dict, projects: list[dict]) -> dict:
    out = {"baru": [], "commit": {}, "tugas": {}}
    prev_p = prev.get("projects", {})
    for e in projects:
        n = e["nama"]
        old = prev_p.get(n)
        if old is None:
            if prev:
                out["baru"].append(n)
            continue
        if e["git"].get("head") and e["git"].get("head") != old.get("head"):
            out["commit"][n] = human_age(time.time() - e["git"].get("commit_ts", time.time())) + " lalu"
        if e["tugas_selesai"] > old.get("tugas_selesai", 0):
            out["tugas"][n] = e["tugas_selesai"] - old.get("tugas_selesai", 0)
    return out


def snap_of(projects: list[dict]) -> dict:
    return {"ts": int(time.time()),
            "projects": {e["nama"]: {"head": e["git"].get("head"),
                                     "tugas_selesai": e["tugas_selesai"],
                                     "files": e["files"]} for e in projects}}


# ---------- render ----------
def render_projects(projects: list[dict], d: dict, full: bool = False) -> str:
    aktif = [e for e in projects if e["aktif"]]
    dingin = [e for e in projects if not e["aktif"]]
    lines = [f"{len(aktif)} aktif, {len(dingin)} dingin (>21h)"]
    if not aktif:
        lines.append("Tidak ada proyek aktif (>21 hari tanpa perubahan).")
    for e in (proyek for proyek in (aktif if full else aktif[:8])):
        head = f"• {e['nama']}"
        bits = []
        if e["tugas_total"]:
            pct = round(100 * e["tugas_selesai"] / e["tugas_total"])
            bits.append(f"{e['tugas_selesai']}/{e['tugas_total']} tugas ({pct}%)")
        bits.append(f"{e['files']} file")
        if e["loc"]:
            bits.append(f"{e['loc']:,} baris".replace(",", "."))
        g = e["git"]
        if g.get("commit_ts"):
            bits.append(f"commit {human_age(time.time() - g['commit_ts'])} lalu")
            if g.get("commit_7d"):
                bits.append(f"{g['commit_7d']} commit/7h")
        elif e["umur_jam"] is not None:
            bits.append(f"terakhir {human_age(e['umur_jam'] * 3600)} lalu")
        if g.get("dirty"):
            bits.append("ada perubahan belum di-commit")
        if e["nama"] in d["commit"]:
            bits.append(f"BARU: commit {d['commit'][e['nama']]}")
        if e["nama"] in d["tugas"]:
            bits.append(f"+{d['tugas'][e['nama']]} tugas selesai")
        lines.append(head + " — " + ", ".join(bits))
        if full and e["tugas_terbuka"]:
            lines.append("   terbuka: " + ", ".join(e["tugas_terbuka"]))
    if d["baru"]:
        lines.append("proyek baru: " + ", ".join(d["baru"]))
    if dingin and full:
        lines.append("dingin (>21h): " + ", ".join(e["nama"] for e in dingin[:10]))
    elif dingin:
        lines.append("dingin: " + ", ".join(e["nama"] for e in dingin[:6]))
    return "\n".join(lines)


def render_eco(svcs: list[dict], timers: list[dict], deck: dict, db: dict,
               host: dict, builds: dict, jobrows: list[dict] | None = None) -> str:
    live = sum(1 for s in svcs if s["active"] == "active")
    lines = [f"Layanan {live}/{len(svcs)} hidup"]
    for s in svcs:
        if s["active"] != "active":
            lines.append(f"  MATI: {s['unit']}")
    if deck.get("ada"):
        extra = f", GAGAL: {', '.join(deck['gagal'])}" if deck.get("gagal") else ""
        stale = " (STALE)" if deck.get("umur_jam", 0) > 26 else ""
        lines.append(f"Deck: {deck['ok']}/{deck['total']} profil OK, health {deck['umur_jam']}j{stale}{extra}")
    else:
        lines.append("Deck: health.json tidak ada")
    if db.get("ada"):
        jobs = ", ".join(f"{k}={v}" for k, v in (db.get("job") or {}).items()) or "0"
        ledger = "kosong" if not db.get("ledger") else f"{len(db['ledger'])} jenis"
        lines.append(f"control.db: {db.get('tenant', 0)} tenant, job {jobs}, ledger {ledger}")
    else:
        lines.append("control.db: belum ada")
    if builds.get("ada"):
        st = ", ".join(f"{k}={v}" for k, v in builds["status"].items()) or "kosong"
        lines.append(f"antrean build: {st}")
    else:
        lines.append("antrean build: belum dipakai")
    if jobrows:
        for j in jobrows:
            lines.append(f"build #{j['id']} [{j['status']}] {j['title'][:60]}")
    tline = "; ".join(f"{t['unit'].replace('.timer','').replace('sdb-','')} "
                      f"{t['ago']}{' -> ' + datetime.fromtimestamp(t['next'], WIB).strftime('%H:%M') if t['next'] else ''}"
                      for t in timers)
    lines.append("Timer: " + tline)
    ram = f"{host['ram_pakai_pct']}%" if host["ram_pakai_pct"] is not None else "n/a"
    lines.append(f"Host: disk {host['disk_pakai_pct']}%, RAM {ram}, load {host['load1']}")
    return "\n".join(lines)


def alerts(svcs, timers, deck, db, projects, builds) -> list[str]:
    a = []
    for s in svcs:
        if s["active"] != "active" and s["enabled"] == "enabled":
            a.append(f"{s['unit']} enabled tapi {s['active']} — cek: journalctl --user -u {s['unit']}")
    if deck.get("ada") and deck.get("umur_jam", 0) > 26:
        a.append(f"health.json {deck['umur_jam']}j — timer deck-health macet?")
    if deck.get("gagal"):
        a.append("profil agen gagal: " + ", ".join(deck["gagal"]))
    if not db.get("ada"):
        a.append("control.db tidak ada — control plane belum pernah jalan")
    if builds.get("ada"):
        st = builds.get("status", {})
        if st.get("paused"):
            a.append(f"{st['paused']} build tertunda — /retry <id> melanjutkan")
        if st.get("failed"):
            a.append(f"{st['failed']} build gagal — /jobs untuk detail")
        if st.get("running"):
            a.append(f"{st['running']} build sedang jalan")
    for t in timers:
        if t["unit"] == "sdb-report-4h.timer" and not t["next"] and not t["last"]:
            a.append("timer report-4h tidak aktif — jalankan: systemctl --user enable --now sdb-report-4h.timer")
    for e in projects:
        if e["aktif"] and e["git"].get("dirty"):
            a.append(f"{e['nama']}: ada perubahan belum di-commit")
    return a


# ---------- API ----------
def collect() -> dict:
    projects = collect_projects()
    prev = load_snap()
    d = delta(prev, projects)
    svcs = [svc_state(u) for u in SERVICES]
    ttable = timer_table()
    timers = [timer_state(u, ttable) for u in TIMERS]
    deck, db, host, builds = deck_health(), control_db(), host_state(), build_queue()
    save_snap(snap_of(projects))
    return {"ts": int(time.time()), "waktu": now().strftime("%Y-%m-%d %H:%M WIB"),
            "proyek": projects, "delta": d, "layanan": svcs, "timer": timers,
            "deck": deck, "db": db, "host": host, "builds": builds,
            "job": open_jobs(),
            "alert": alerts(svcs, timers, deck, db, projects, builds)}


def report(kind: str = "4h") -> str:
    s = collect()
    full = kind == "full"
    parts = []
    if kind == "projects":
        return "PROYEK SDB — " + s["waktu"] + "\n" + render_projects(s["proyek"], s["delta"], full=True)
    title = f"SDB {'4 JAM' if kind == '4h' else 'EKOSISTEM'} — {s['waktu']}"
    parts.append(title)
    parts.append("")
    parts.append("PROYEK")
    parts.append(render_projects(s["proyek"], s["delta"], full=full))
    parts.append("")
    parts.append("EKOSISTEM")
    parts.append(render_eco(s["layanan"], s["timer"], s["deck"], s["db"], s["host"],
                            s["builds"], s.get("job")))
    if s["alert"]:
        parts.append("")
        parts.append("PERLU DICEK")
        parts.extend("• " + x for x in s["alert"][:8])
    if not full:
        parts.append("")
        parts.append("detail: /eco · proyek: /projects · tanya: /ask <pertanyaan>")
    text = "\n".join(parts)
    return text


def chunk(text: str, limit: int = TG_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    out, buf = [], ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > limit:
            out.append(buf)
            buf = ""
        buf += line
    if buf:
        out.append(buf)
    return out


def send(text: str, token: str, chat: str) -> int:
    n = 0
    for piece in chunk(text):
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": piece,
                             "disable_web_page_preview": True}).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                if json.loads(r.read() or b"{}").get("ok"):
                    n += 1
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as e:
            print(f"kirim gagal: {type(e).__name__}", file=sys.stderr)
            break
    return n


def main(argv: list[str]) -> int:
    kind = "4h"
    mode = "--print"
    for a in argv[1:]:
        if a in ("4h", "full", "projects"):
            kind = a
        elif a in ("--print", "--send", "--json"):
            mode = a
    if mode == "--json":
        print(json.dumps(collect(), ensure_ascii=False, indent=1))
        return 0
    text = report(kind)
    if mode == "--print":
        print(text)
        return 0
    token = os.environ.get("SDB_TG_BOT_TOKEN", "")
    chat = os.environ.get("SDB_TG_CHAT_ID", "")
    if not token or not chat:
        print("token/chat belum diset", file=sys.stderr)
        return 2
    sent = send(text, token, chat)
    print(f"terkirim: {sent} pesan")
    return 0 if sent else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
