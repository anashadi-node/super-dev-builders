#!/usr/bin/env python3
"""SDB Intake API — kanal input per skenario: teks bebas, link, dan lampiran file.

Setiap kiriman menjadi satu entri nyata di disk:

    ~/sdb-workspace/intake/<YYYYMMDD-HHMMSS>-<rand>/
        meta.json     data kiriman (teks, link, daftar file + sha256, skenario)
        brief.md      versi manusia & mesin: dipakai agen sebagai konteks tahap
        files/        lampiran asli, nama sudah disanitasi

Keamanan (sama ketatnya dengan ws_api):
- Wajib header X-SDB-Token (token 72-bit yang sama, dibuat ws_api.get_token()).
- Ukuran per file dibatasi 25 MB dan dihitung SAAT streaming (bukan hanya dari header).
- Nama file disanitasi: basename saja, tanpa karakter kontrol, tanpa awalan titik.
- Setiap path di-resolve dan harus tetap di dalam direktori intake (anti traversal/symlink).
- File tidak pernah dieksekusi. Unduhan non-gambar dipaksa application/octet-stream
  + Content-Disposition: attachment, jadi .html/.svg tidak bisa jalan sebagai halaman.
"""
import datetime
import hashlib
import hmac
import json
import re
import secrets
import shutil
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ws_api

ROOT = Path.home() / "sdb-workspace" / "intake"
MAX_FILE = 25 * 1024 * 1024        # 25 MB per file
MAX_TOTAL = 400 * 1024 * 1024      # 400 MB total satu intake
MAX_FILES = 40
MAX_TEXT = 20000                   # karakter brief
MAX_LINKS = 20
CHUNK = 256 * 1024

ID_RE = re.compile(r"\d{8}-\d{6}-[a-z0-9]{6}")
SAFE_RE = re.compile(r"[^A-Za-z0-9._()\[\] -]")
INLINE_IMG = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}

_lock = threading.RLock()


def _warn(msg):
    print(f"[inbox] {msg}", file=sys.stderr)


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def safe_name(raw, maxlen=120):
    """Nama file yang aman untuk disk DAN untuk ditampilkan kembali."""
    base = Path(str(raw or "")).name.replace("\\", "_")
    base = "".join(ch for ch in base if ch.isprintable())
    base = SAFE_RE.sub("_", base).strip(" .")
    if not base:
        base = "file"
    if base.startswith("."):
        base = "_" + base
    return base[:maxlen]


def intake_dir(iid):
    if not isinstance(iid, str) or not ID_RE.fullmatch(iid):
        raise ValueError("id intake tidak valid")
    d = ROOT / iid
    if not d.is_dir():
        raise ValueError("intake tidak ditemukan")
    return d


def _inside(path, base):
    try:
        return path.resolve().is_relative_to(base.resolve())
    except (OSError, ValueError):
        return False


def read_meta(d):
    try:
        m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        return m if isinstance(m, dict) else None
    except (OSError, ValueError) as exc:
        _warn(f"meta.json rusak di {d.name}: {type(exc).__name__}")
        return None


def write_meta(d, meta):
    tmp = d / "meta.json.tmp"
    tmp.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(d / "meta.json")


def brief_md(meta):
    files = meta.get("files") or []
    links = meta.get("links") or []
    total = sum(int(f.get("size") or 0) for f in files)
    rows = "\n".join(
        f"| `{f['stored']}` | {f['name']} | {f['size']:,} B | `{f['sha256'][:16]}` |"
        for f in files) or "| — | — | — | — |"
    link_md = "\n".join(f"- {u}" for u in links) or "- (tidak ada)"
    stage = meta.get("stage") or "-"
    return f"""# Brief — {meta.get('title') or meta['id']}

- **Intake**: `{meta['id']}`
- **Skenario**: {meta.get('scen') or '-'} — {meta.get('scen_title') or '(tidak disebut)'}
- **Tahap**: {stage}
- **Target**: {meta.get('target') or '(belum ditentukan)'}
- **Dibuat**: {meta.get('created')}
- **Lampiran**: {len(files)} file · {total:,} B

## Yang diminta Owner

{meta.get('text') or '(kosong — hanya lampiran/link)'}

## Contoh / referensi (link)

{link_md}

## Lampiran

| Disimpan sebagai | Nama asli | Ukuran | SHA-256 (16) |
|---|---|---|---|
{rows}

## Catatan pemakaian

Brief ini adalah **masukan**, bukan klaim hasil. Agen wajib memperlakukan isi
lampiran sebagai data yang belum diverifikasi sampai ada pembacaan nyata.
Jangan pernah menyalin kredensial dari lampiran ke dokumen tahap (`[REDACTED]`).
"""


def _rewrite_brief(d, meta):
    tmp = d / "brief.md.tmp"
    tmp.write_text(brief_md(meta), encoding="utf-8")
    tmp.replace(d / "brief.md")


def _normalize_links(raw):
    out = []
    for u in raw if isinstance(raw, list) else []:
        s = str(u or "").strip()[:2000]
        if not s:
            continue
        if not re.match(r"^https?://", s, re.I):
            raise ValueError(f"link harus http/https: {s[:60]}")
        if s not in out:
            out.append(s)
        if len(out) >= MAX_LINKS:
            break
    return out


def create(body):
    text = str(body.get("text") or "").strip()
    links = _normalize_links(body.get("links"))
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    expect_files = int(body.get("expect_files") or 0)
    if not text and not links and not expect_files:
        raise ValueError("brief kosong: tulis teks, tambahkan link, atau lampirkan file")
    if len(text) > MAX_TEXT:
        raise ValueError(f"teks terlalu panjang (maks {MAX_TEXT} karakter)")

    ROOT.mkdir(parents=True, exist_ok=True)
    iid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    d = ROOT / iid
    (d / "files").mkdir(parents=True, exist_ok=False)

    title = (str(body.get("title") or "").strip() or first or (links[0] if links else iid))[:120]
    meta = {
        "id": iid, "created": now(), "status": "draft",
        "scen": str(body.get("scen") or "")[:40],
        "scen_title": str(body.get("scen_title") or "")[:120],
        "stage": str(body.get("stage") or "")[:10],
        "target": str(body.get("target") or "")[:80],
        "title": title, "text": text, "links": links, "files": [],
    }
    write_meta(d, meta)
    _rewrite_brief(d, meta)
    return meta


def add_file(iid, raw_name, stream, length):
    """Stream body ke files/ sambil menghitung ukuran & sha256. Mengembalikan entri file."""
    d = intake_dir(iid)
    name = safe_name(raw_name)
    with _lock:
        meta = read_meta(d) or {}
        files = meta.get("files") or []
        if len(files) >= MAX_FILES:
            raise ValueError(f"maks {MAX_FILES} file per intake")
        used = sum(int(f.get("size") or 0) for f in files)
        if used + (length or 0) > MAX_TOTAL:
            raise ValueError("total lampiran melebihi 400 MB")

        fdir = d / "files"
        fdir.mkdir(exist_ok=True)
        stem, dot, ext = name.rpartition(".")
        n = 1
        stored = name
        while (fdir / stored).exists():
            n += 1
            stored = f"{stem}-{n}.{ext}" if dot else f"{name}-{n}"
        target = fdir / stored
        if not _inside(target, fdir):  # sabuk pengaman kedua setelah safe_name
            raise ValueError("nama file ditolak")

        h = hashlib.sha256()
        size = 0
        tmp = fdir / (stored + ".part")
        remaining = int(length)
        try:
            with tmp.open("wb") as fh:
                # Baca PERSIS sejumlah Content-Length: read(n) tanpa sisa membuat
                # koneksi keep-alive menggantung sampai timeout.
                while remaining > 0:
                    chunk = stream.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    size += len(chunk)
                    if size > MAX_FILE:
                        raise ValueError(f"{name}: melebihi 25 MB")
                    h.update(chunk)
                    fh.write(chunk)
            if size != length:  # body terpotong: jangan simpan file setengah
                raise ValueError(f"{name}: ukuran tidak cocok ({size} dari {length} B)")
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        entry = {"name": name, "stored": stored, "size": size,
                 "sha256": h.hexdigest(), "added": now()}
        files.append(entry)
        meta["files"] = files
        meta["updated"] = now()
        write_meta(d, meta)
        _rewrite_brief(d, meta)
        return entry, meta


def list_intakes(limit=40):
    out = []
    if not ROOT.is_dir():
        return out
    for d in sorted((p for p in ROOT.iterdir() if p.is_dir() and ID_RE.fullmatch(p.name)),
                    key=lambda p: p.name, reverse=True)[:limit]:
        m = read_meta(d)
        if not m:
            continue
        files = m.get("files") or []
        out.append({"id": m.get("id", d.name), "created": m.get("created", ""),
                    "scen": m.get("scen", ""), "scen_title": m.get("scen_title", ""),
                    "stage": m.get("stage", ""), "title": m.get("title", ""),
                    "text": (m.get("text") or "")[:400], "links": m.get("links") or [],
                    "n_files": len(files), "bytes": sum(int(f.get("size") or 0) for f in files),
                    "files": [{"name": f.get("name"), "size": f.get("size")} for f in files]})
    return out


def delete_intake(iid):
    d = intake_dir(iid)
    if not _inside(d, ROOT):
        raise ValueError("path ditolak")
    shutil.rmtree(d)
    return {"deleted": iid}


# --------------------------------------------------------------- HTTP
def _authed(h):
    given = h.headers.get("X-SDB-Token", "")
    tok = ws_api.get_token()
    return hmac.compare_digest(given.encode("utf-8", "replace"), tok.encode("utf-8"))


def _serve_file(h, q):
    iid = (q.get("id") or [""])[0]
    stored = safe_name((q.get("name") or [""])[0])
    d = intake_dir(iid)
    fdir = d / "files"
    fp = fdir / stored
    if not (_inside(fp, fdir) and fp.is_file()):
        h.send_error(404)
        return
    ext = fp.suffix.lstrip(".").lower()
    data = fp.read_bytes()
    h.send_response(200)
    if ext in INLINE_IMG:  # hanya gambar raster: aman dipratinjau di halaman
        h.send_header("Content-Type", INLINE_IMG[ext])
        h.send_header("Content-Disposition", f'inline; filename="{stored}"')
    else:                  # html/svg/md/doc/pdf: paksa unduhan, tidak pernah dirender
        h.send_header("Content-Type", "application/octet-stream")
        h.send_header("Content-Disposition", f'attachment; filename="{stored}"')
    h.send_header("Content-Length", str(len(data)))
    h.send_header("X-Content-Type-Options", "nosniff")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(data)


def handle(h, method, send):
    """Return True bila path ditangani."""
    u = urlparse(h.path)
    path, q = u.path, parse_qs(u.query)
    if not path.startswith("/api/inbox"):
        return False
    route = path[len("/api/inbox"):].strip("/")

    # Unduhan pakai token di query? Tidak — header wajib, konsisten dengan rute lain.
    if not _authed(h):
        client = h.client_address[0]
        with ws_api.rate_lock:
            hits = [t for t in ws_api.rate_401.get(client, ()) if time.monotonic() - t < 60.0]
            hits.append(time.monotonic())
            ws_api.rate_401[client] = hits[-40:]
        if len(hits) > 30:
            send(429, {"error": "terlalu banyak kegagalan autentikasi"})
        else:
            send(401, {"error": "token salah/kosong — buka dari PC lokal untuk melihat PIN"})
        return True

    try:
        if route == "submit" and method == "POST":
            n = int(h.headers.get("Content-Length") or 0)
            if n < 0 or n > 128 * 1024:
                send(413, {"error": "body terlalu besar"})
                return True
            body = json.loads(h.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body harus objek JSON")
            meta = create(body)
            send(200, {"id": meta["id"], "dir": str(ROOT / meta["id"]), "title": meta["title"]})

        elif route == "file" and method == "POST":
            iid = (q.get("id") or [""])[0]
            raw_name = (q.get("name") or [""])[0]
            n = int(h.headers.get("Content-Length") or 0)
            if n <= 0:
                send(400, {"error": "file kosong"})
                return True
            if n > MAX_FILE:
                send(413, {"error": "file melebihi 25 MB"})
                return True
            entry, meta = add_file(iid, raw_name, h.rfile, n)
            send(200, {"file": entry, "n_files": len(meta["files"])})

        elif route == "list" and method == "GET":
            send(200, {"items": list_intakes(), "root": str(ROOT)})

        elif route == "get" and method == "GET":
            d = intake_dir((q.get("id") or [""])[0])
            meta = read_meta(d) or {}
            try:
                meta["brief"] = (d / "brief.md").read_text(encoding="utf-8")
            except OSError:
                meta["brief"] = ""
            meta["dir"] = str(d)
            send(200, meta)

        elif route == "download" and method == "GET":
            _serve_file(h, q)

        elif route == "delete" and method == "POST":
            n = int(h.headers.get("Content-Length") or 0)
            body = json.loads(h.rfile.read(n) or b"{}") if 0 < n <= 4096 else {}
            send(200, delete_intake(str((body or {}).get("id", ""))))

        else:
            send(404, {"error": "rute tidak dikenal"})
    except (ValueError, RuntimeError) as e:
        send(400, {"error": str(e)})
    except Exception as e:  # noqa: BLE001 — batas HTTP: jangan pernah mematikan server
        import traceback
        print(f"[inbox] 500 {method} {route}: {type(e).__name__}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        send(500, {"error": f"kesalahan server ({type(e).__name__})"})
    return True
