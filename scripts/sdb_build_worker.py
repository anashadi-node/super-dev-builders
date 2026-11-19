#!/usr/bin/env python3
"""Worker build SDB: jalankan Hermes headless untuk job dari Telegram.

Dua tahap per job:
  1. SPEC  (status spec_queued)  -> menulis SPEC.md, PLAN.md, QUESTIONS.md
  2. BUILD (status build_queued) -> implementasi + tes + README, setelah /approve

Keamanan:
  - Hanya memproses job berstatus antre; tidak menerima teks bebas dari jaringan.
  - Direktori kerja wajib di dalam SDB_BUILDS (dipaksa, bukan disarankan).
  - Tiap proses Hermes dibatasi --max-turns dan --run-budget, dimatikan
    seluruh process-group-nya bila melewati batas wall-clock.
  - Prompt melarang menyentuh ~/.config, ~/.hermes, repo lain, dan data rahasia.

Jalankan: systemctl --user start sdb-build-worker   (atau python3 scripts/sdb_build_worker.py --once)
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdb_evidence as evd
import sdb_jobs as jobs

TOKEN = os.environ.get("SDB_TG_BOT_TOKEN", "")
OWNER = os.environ.get("SDB_TG_CHAT_ID", "")
MODEL = os.environ.get("SDB_BUILD_MODEL", "")
SPEC_TIMEOUT = int(os.environ.get("SDB_SPEC_TIMEOUT", "900"))
BUILD_TIMEOUT = int(os.environ.get("SDB_BUILD_TIMEOUT", "3600"))
SPEC_TURNS = int(os.environ.get("SDB_SPEC_TURNS", "40"))
BUILD_TURNS = int(os.environ.get("SDB_BUILD_TURNS", "300"))
POLL = int(os.environ.get("SDB_WORKER_POLL", "10"))
ROUNDS = int(os.environ.get("SDB_BUILD_ROUNDS", "3"))

# --- gerbang penyelesaian (C2-A) ---
# Target kebijakan adalah `verified`, tetapi default kode sengaja `attested`:
# mengaktifkan `verified` sebelum C2-B (verifier tersandbox) membuat semua build
# berhenti `paused`. Aktivasi = set SDB_DONE_POLICY=verified, butuh persetujuan Owner.
DONE_POLICY_DEFAULT = "attested"
DONE_POLICIES = ("attested", "verified")
DOC_MAX_BYTES = 200_000
DIGEST_FILE_MAX = 20_000
DIGEST_BYTE_MAX = 256 * 1024 * 1024
DIGEST_TIME_MAX = 20.0
DIGEST_SKIP_DIRS = frozenset({"node_modules", ".venv", ".git", "__pycache__",
                              ".pytest_cache", ".mypy_cache", ".ruff_cache"})
# C2-B1: batas keras agar satu workspace besar tidak memblokir satu-satunya worker.
LISTING_ENTRY_MAX = 20_000
LISTING_BYTE_MAX = 512 * 1024 * 1024
DIGEST_ENTRY_MAX = 200_000
# Nonce permintaan verifikasi: sekali pakai, berbatas waktu.
VERIFY_TTL_DEFAULT = 1800
VERIFY_TTL_MAX = 86_400
# Reaper: job yang tertinggal di status berjalan > batas ini dikembalikan ke `paused`.
STALE_RUNNING_SECONDS = 7200
_DB_TRIES = 3

GUARD = """ATURAN KERAS (tidak bisa dinegosiasikan):
- Bekerja HANYA di direktori kerja saat ini. Jangan menulis/menghapus di luar itu.
- Dilarang menyentuh ~/.hermes, ~/.config, ~/anantara-sakti, kredensial, .env, kunci API.
- Jangan menjalankan perintah destruktif (rm -rf, mkfs, dd, shutdown, reboot).
- Jangan mengarang hasil. Setiap klaim "selesai" wajib disertai output perintah nyata.
"""

SPEC_PROMPT = """{guard}

KAMU engineer senior + arsitek produk. Klien menulis via Telegram:

<<<
{brief}
>>>

TAHAP 1 — SPESIFIKASI. Jangan menulis kode produksi.

Yang wajib kamu hasilkan (berkas nyata di direktori kerja):
1. SPEC.md — tujuan & pengguna; fitur MoSCoW (Must/Should/Could/Won't); kebutuhan
   non-fungsional (performa, keamanan, aksesibilitas, mobile); acceptance criteria
   yang TERUKUR (bisa diuji ya/tidak); di luar lingkup.
2. PLAN.md — stack + alasan singkat; struktur berkas; langkah implementasi bernomor
   dengan estimasi; risiko + mitigasi; cara menguji.
3. QUESTIONS.md — maksimal 5 pertanyaan yang benar-benar mengubah arsitektur.
   Kalau tidak ada, tulis tepat: TIDAK ADA PERTANYAAN.

Setelah menulis, balas RINGKAS (<=1200 karakter, bahasa Indonesia, tanpa basa-basi):
- stack terpilih
- jumlah fitur Must / Should
- 3 langkah pertama
- pertanyaan kritis (kalau ada), nomor 1..n
"""

DOCS_PROMPT = """{guard}

RONDE DOKUMENTASI (terakhir). Pekerjaan fitur sudah dilakukan di ronde sebelumnya.
Tugasmu sekarang HANYA menutup dengan bukti, tanpa menambah fitur baru:

1. Jalankan verifikasi nyata yang tersedia (mis. `npm run build`, `npm test`,
   `npm run typecheck`, smoke test). Tempel perintah + potongan output APA ADANYA.
2. Tulis VERIFY.md: tabel perintah -> hasil (lulus/gagal), plus output ringkas.
3. Tulis README.md: apa ini, prasyarat, langkah pasang, cara menjalankan, cara tes,
   struktur folder, catatan konfigurasi (.env contoh), dan batasan.
4. Tulis GAPS.md: yang belum selesai/berisiko, jujur; tulis "TIDAK ADA" kalau bersih.
5. Jangan mengubah kode kecuali memperbaiki kegagalan build/test yang muncul.

Balas RINGKAS (<=900 karakter): hasil verifikasi + status akhir.
"""

CONTINUE_PROMPT = """{guard}

LANJUTAN RONDE {round}/{rounds}. Sesi ini melanjutkan pekerjaan yang belum selesai
di direktori kerja yang sama. Jangan mengulang berkas yang sudah jadi.

1. Periksa keadaan nyata dulu: `ls`, baca README/GAPS bila ada, jalankan build/test.
2. Kerjakan sisa pekerjaan sampai tidak ada fitur Must yang stub.
3. Jalankan verifikasi nyata (build + tes + smoke), lalu tulis VERIFY.md dan GAPS.md.
4. Kalau setelah semua itu benar-benar tuntas, awali jawabanmu dengan kata: SELESAI

Balas RINGKAS (<=1200 karakter): yang selesai + bukti perintah, yang belum, langkah berikut.
"""

BUILD_PROMPT = """{guard}

TAHAP 2 — IMPLEMENTASI PENUH. Spesifikasi ada di SPEC.md dan rencana di PLAN.md
(direktori kerja saat ini). Baca keduanya dulu, lalu kerjakan sampai selesai.

Definisi selesai (semua wajib):
1. Semua fitur Must benar-benar berfungsi, bukan stub/TODO.
2. Ada tes otomatis yang lulus, atau smoke test nyata yang kamu jalankan sendiri.
3. Aplikasi bisa dijalankan: sertakan README.md berisi perintah persis + prasyarat.
4. UI (kalau ada) rapi: responsif, kontras cukup, tanpa teks contoh palsu.
5. Kamu menjalankan verifikasi nyata dan menempelkan buktinya di VERIFY.md
   (perintah + potongan output, apa adanya).
6. Tidak ada data rahasia, kunci, atau berkas pribadi yang tersalin.

Kalau ada yang tidak selesai, tulis jelas di GAPS.md — jangan disembunyikan.

Kalau setelah semua itu benar-benar tuntas, awali jawabanmu dengan kata: SELESAI

Balas RINGKAS (<=1500 karakter, bahasa Indonesia):
- apa yang sudah jalan (dengan bukti perintah)
- cara menjalankan
- berkas utama
- kekurangan/gaps
"""


# ---------- telegram ----------
def notify(text: str) -> None:
    if not TOKEN or not OWNER:
        print("(notifikasi dilewati: token/chat belum diset)", file=sys.stderr)
        return
    for piece in [text[i:i + 3800] for i in range(0, len(text), 3800)] or [""]:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=json.dumps({"chat_id": OWNER, "text": piece,
                             "disable_web_page_preview": True}).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
        except OSError as e:
            print(f"notify gagal: {type(e).__name__}", file=sys.stderr)


# ---------- hermes ----------
def run_hermes(prompt: str, cwd: Path, timeout: int, turns: int,
               session: str = "") -> tuple[str, str, int]:
    """(teks jawaban, session_id, exit_code). Proses dimatikan via process group."""
    # Sesi baru: semua pembatas dipasang di sini.
    # Resume: Hermes menolak override kebijakan sesi (max-turns/run-budget/model),
    # jadi saat resume hanya --resume yang boleh dikirim.
    if session:
        cmd = ["hermes", "chat", "-Q", "--oneshot", "--query-file", "-",
               "--pass-session-id", "--resume", session, "--no-restore-cwd"]
    else:
        cmd = ["hermes", "chat", "-Q", "--oneshot", "--query-file", "-",
               "--pass-session-id", "--in", str(cwd),
               "--max-turns", str(turns), "--run-budget", str(max(60, timeout - 30))]
        if MODEL:
            cmd += ["-m", MODEL]
    env = dict(os.environ)
    env.pop("SDB_TG_BOT_TOKEN", None)   # token bot tidak diwariskan ke agen
    env.pop("SDB_TG_CHAT_ID", None)
    p = subprocess.Popen(cmd, cwd=str(cwd), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, start_new_session=True, env=env)
    try:
        out, _ = p.communicate(prompt, timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except OSError:
            pass
        try:
            out, _ = p.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except OSError:
                pass
            out = ""
        rc = 124
    out = out or ""
    sid = ""
    lines = []
    for line in out.splitlines():
        if line.startswith("session_id: "):
            sid = line.split("session_id: ", 1)[1].strip()
        else:
            lines.append(line)
    return "\n".join(lines).strip(), sid, rc


def read_text(p: Path, limit: int = 1200) -> str:
    try:
        return p.read_text(errors="replace")[:limit].strip()
    except OSError:
        return ""


def listing(d: Path, limit: int = 25) -> str:
    """Ringkasan isi direktori dengan batas entri & byte (tidak boleh memblokir worker).

    Memakai `os.scandir` beriterasi dan berhenti saat batas tercapai. Versi lama
    memakai `sorted(d.rglob("*"))`, yang mematerialisasi + mengurutkan SELURUH
    pohon lebih dulu — batas entri baru diperiksa setelah pekerjaan mahal selesai
    (mis. `node_modules` hasil `npm install`).
    """
    rows: list[str] = []
    total = 0
    entri = 0
    dipotong = False
    tumpukan = [d]
    while tumpukan and not dipotong:
        akar = tumpukan.pop()
        try:
            with os.scandir(akar) as it:
                for e in it:
                    entri += 1
                    if entri > LISTING_ENTRY_MAX or total > LISTING_BYTE_MAX:
                        dipotong = True
                        break
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if e.name not in DIGEST_SKIP_DIRS:
                                tumpukan.append(Path(e.path))
                            continue
                        if not e.is_file(follow_symlinks=False):
                            continue
                        ukuran = e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
                    total += ukuran
                    if len(rows) < limit:
                        rows.append(f"  {Path(e.path).relative_to(d)} ({ukuran / 1024:.0f} KB)")
        except OSError:
            continue
    head = f"{total / 1024:.0f} KB total" if total else "kosong"
    if dipotong:
        head += " (daftar dipotong: melewati batas entri/byte)"
    return head + ("\n" + "\n".join(sorted(rows)) if rows else "")


# ---------- gerbang penyelesaian (C2-A) ----------
# Prinsip: keberadaan dokumen tidak membuktikan apa pun. Yang diperiksa di sini
# adalah identitas job, lokasi direktori, bentuk dokumen, dan (pada kebijakan
# `verified`) bukti mesin yang terikat ke isi workspace saat ini.
def done_policy() -> str:
    """Kebijakan gerbang `done`. Hanya "tidak diset" yang memakai default.

    Nilai kosong/spasi/tak dikenal = salah set -> fail-closed ke `verified`
    (jangan pernah menurunkan gerbang secara diam-diam).
    """
    raw = os.environ.get("SDB_DONE_POLICY")
    if raw is None:
        return DONE_POLICY_DEFAULT
    raw = raw.strip().lower()
    return raw if raw in DONE_POLICIES else "verified"


def resolve_workspace(job: dict) -> tuple[Path | None, str]:
    """Direktori kerja sah untuk job ini, atau (None, kode) bila gagal."""
    try:
        jid = int(job.get("id") or 0)
    except (TypeError, ValueError):
        return None, "WORKSPACE_INVALID"
    raw = str(job.get("dir") or "")
    if not jid or not raw:
        return None, "WORKSPACE_INVALID"
    try:
        baris = jobs.get(jid)  # identitas: dir di DB harus sama dengan job yang diproses
    except Exception:  # noqa: BLE001 — DB rusak tidak boleh membuat job dianggap selesai
        return None, "WORKSPACE_INVALID"
    if not baris or str(baris.get("dir") or "") != raw:
        return None, "WORKSPACE_INVALID"
    p = Path(raw)
    try:
        if p.is_symlink():
            return None, "WORKSPACE_INVALID"
        real = p.resolve(strict=True)
    except OSError:
        return None, "WORKSPACE_INVALID"
    if not real.is_dir():
        return None, "WORKSPACE_INVALID"
    try:
        root = Path(jobs.BUILDS).resolve()
    except OSError:
        return None, "WORKSPACE_INVALID"
    if real == root or root not in real.parents:
        return None, "WORKSPACE_INVALID"
    if not real.name.startswith(f"{jid:03d}-"):
        return None, "WORKSPACE_INVALID"
    return real, ""


def _safe_read(p: Path, limit: int) -> str | None:
    """Baca berkas regular tanpa mengikuti symlink. None bila tidak sah.

    lstat -> open(O_NOFOLLOW|O_NONBLOCK) -> fstat menutup "periksa lalu baca":
    symlink/hardlink ditolak, berkas yang ditukar antara lstat dan open ditolak
    (dev/ino berbeda), dan FIFO tidak bisa menggantung worker.
    """
    try:
        st = p.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return None
    # Hardlink ditolak: user yang sama bisa menautkan berkas rahasia ke README.md
    # atau VERIFY.md, sehingga isinya terbaca dan ikut terkirim ke Telegram.
    if st.st_nlink > 1 or st.st_size > limit:
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(p, flags)
    except OSError:
        return None
    try:
        dst = os.fstat(fd)
        if (dst.st_dev, dst.st_ino) != (st.st_dev, st.st_ino):
            return None
        if not stat.S_ISREG(dst.st_mode):
            return None
        with os.fdopen(fd, "rb") as fh:
            fd = -1
            data = fh.read(limit + 1)
    except OSError:
        return None
    finally:
        if fd >= 0:
            os.close(fd)
    if len(data) > limit:
        return None
    return data.decode("utf-8", errors="replace").strip()


def _safe_read_at(dirfd: int, nama: str, limit: int) -> str | None:
    """Baca `nama` relatif terhadap `dirfd` — menutup TOCTOU komponen path (R-3).

    Path `dirfd/nama` tidak bisa dialihkan dengan me-rename direktori induk di
    tengah jalan, karena direktori sudah terbuka dan diperiksa sekali. Symlink,
    hardlink, FIFO, dan berkas yang ditukar antara stat dan open tetap ditolak.
    """
    if not nama or "/" in nama or nama in (".", ".."):
        return None
    try:
        st = os.stat(nama, dir_fd=dirfd, follow_symlinks=False)
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return None
    if st.st_nlink > 1 or st.st_size > limit:
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(nama, flags, dir_fd=dirfd)
    except OSError:
        return None
    try:
        dst = os.fstat(fd)
        if (dst.st_dev, dst.st_ino) != (st.st_dev, st.st_ino):
            return None
        if not stat.S_ISREG(dst.st_mode):
            return None
        with os.fdopen(fd, "rb") as fh:
            fd = -1
            data = fh.read(limit + 1)
    except OSError:
        return None
    finally:
        if fd >= 0:
            os.close(fd)
    if len(data) > limit:
        return None
    return data.decode("utf-8", errors="replace").strip()


def read_docs(d: Path) -> tuple[str, str, str]:
    """(kode, readme, verify). kode "" berarti dokumen sah dan tidak kosong."""
    try:
        dirfd = os.open(d, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return "DOCS_INVALID", "", ""
    try:
        readme = _safe_read_at(dirfd, "README.md", DOC_MAX_BYTES)
        verify = _safe_read_at(dirfd, "VERIFY.md", DOC_MAX_BYTES)
    finally:
        os.close(dirfd)
    if not readme:
        return "DOCS_INVALID", "", ""
    if not verify:
        return "DOCS_INVALID", readme, ""
    return "", readme, verify


def tree_digest(d: Path) -> tuple[str, bool]:
    """(sidik isi workspace, lengkap?) untuk berkas regular non-symlink.

    Isi SEMUA berkas regular dihash (streaming, tanpa batas per-berkas) agar
    perubahan sekecil apa pun menggugurkan bukti lama. Direktori dependensi/cache
    hanya dicatat keberadaannya (`D <rel>`), jadi mutasi di dalamnya TIDAK
    mengubah sidik — itu keterbatasan yang dicatat, bukan disamarkan.

    Anggaran byte dan waktu mencegah satu job besar memblokir worker. Bila
    anggaran habis, `lengkap` menjadi False dan bukti `verified` ditolak.
    """
    h = hashlib.sha256()
    n = 0
    dipakai = 0
    entri = 0
    lengkap = True
    mulai = time.monotonic()
    for root, dirs, files in os.walk(d, followlinks=False):
        if time.monotonic() - mulai > DIGEST_TIME_MAX:
            lengkap = False
            break
        entri += len(dirs) + len(files)
        if entri > DIGEST_ENTRY_MAX:   # batas keras: pohon raksasa tidak boleh macet
            lengkap = False
            break
        rel_root = Path(root).relative_to(d)
        sisa = []
        for name in sorted(dirs):
            p = Path(root) / name
            rel = rel_root / name
            if p.is_symlink():
                h.update(f"L {rel}\n".encode())
            elif name in DIGEST_SKIP_DIRS:
                h.update(f"D {rel}\n".encode())
            else:
                sisa.append(name)
        dirs[:] = sisa
        for name in sorted(files):
            p = Path(root) / name
            rel = rel_root / name
            try:
                st = p.lstat()
            except OSError:
                lengkap = False
                continue
            if stat.S_ISLNK(st.st_mode):
                h.update(f"L {rel}\n".encode())
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            n += 1
            if n > DIGEST_FILE_MAX:
                lengkap = False
                break
            h.update(f"F {rel} {st.st_size}\n".encode())
            if dipakai + st.st_size > DIGEST_BYTE_MAX:
                lengkap = False
                continue
            dipakai += st.st_size
            try:
                with open(p, "rb") as fh:
                    for potong in iter(lambda: fh.read(65536), b""):
                        h.update(potong)
            except OSError:
                h.update(b"UNREADABLE\n")
                lengkap = False
        if not lengkap:
            break
    if not lengkap:
        h.update(b"PARTIAL\n")
    return h.hexdigest(), lengkap


def latest_evidence_row(jid: int) -> tuple[int | None, dict | None]:
    """(id event, payload) `verify` terakhir. (None, None) = tidak ada; (id, {}) = rusak.

    Query langsung, bukan memindai N event terakhir: event `verify` bisa tertimbun
    puluhan `build_output` dari ronde/retry sebelumnya.
    """
    try:
        with contextlib.closing(jobs.connect()) as con:
            baris = con.execute(
                "SELECT id, text FROM events WHERE job_id=? AND kind='verify' "
                "ORDER BY id DESC LIMIT 1", (jid,)).fetchone()
    except Exception:  # noqa: BLE001
        return None, {}
    if baris is None:
        return None, None
    try:
        isi = json.loads(baris["text"] or "")
    except (TypeError, ValueError, IndexError, KeyError):
        return int(baris["id"]), {}
    return int(baris["id"]), (isi if isinstance(isi, dict) else {})


def latest_evidence(jid: int) -> dict | None:
    return latest_evidence_row(jid)[1]


# ---------- C2-B1: permintaan verifikasi, nonce, dan ketahanan DB ----------
def verify_ttl() -> int:
    """Masa berlaku nonce (detik), dibatasi agar tidak pernah tak berujung."""
    try:
        ttl = int(os.environ.get("SDB_VERIFY_TTL", "") or VERIFY_TTL_DEFAULT)
    except (TypeError, ValueError):
        return VERIFY_TTL_DEFAULT
    return min(max(ttl, 60), VERIFY_TTL_MAX)


def allowed_signers_path() -> Path | None:
    raw = (os.environ.get("SDB_EVIDENCE_ALLOWED_SIGNERS") or "").strip()
    return Path(raw).expanduser() if raw else None


def authorized_verifiers() -> set[str]:
    raw = os.environ.get("SDB_EVIDENCE_VERIFIERS") or ""
    return {x.strip() for x in raw.split(",") if x.strip()}


def pinned_criteria_digest() -> str | None:
    raw = (os.environ.get("SDB_ACCEPTANCE_CRITERIA_DIGEST") or "").strip()
    return raw or None


def issue_nonce(jid: int) -> str:
    """Terbitkan nonce sekali pakai untuk satu permintaan verifikasi job ini.

    Nonce disimpan sebagai event `verify_request` — bukan kolom baru — supaya
    skema DB tidak berubah. Masa berlakunya ikut dicatat.
    """
    nonce = secrets.token_hex(32)
    sekarang = int(time.time())
    _add_event(jid, "verify_request", json.dumps(
        {"schema": evd.REQUEST_SCHEMA, "job_id": jid, "nonce": nonce,
         "issued_at": sekarang, "expires_at": sekarang + verify_ttl()},
        ensure_ascii=False))
    return nonce


def _nonce_state(jid: int, exclude_event: int | None = None) -> tuple[dict[str, int], set[str]]:
    """(nonce -> batas berlaku, nonce yang sudah diterima) untuk job ini.

    Sumber "sudah dipakai" adalah event `verify_accepted` yang HANYA ditulis
    worker setelah `validate()` sukses. Event `verify` mentah tidak dihitung:
    kalau dihitung, satu event sampah `{"request_nonce": <nonce>}` yang ditulis
    builder akan membakar nonce sah secara permanen (DoS jalur `verified`).
    """
    terbit: dict[str, int] = {}
    dipakai: set[str] = set()
    try:
        with contextlib.closing(jobs.connect()) as con:
            baris = con.execute(
                "SELECT id, kind, text FROM events WHERE job_id=? AND kind IN "
                "('verify_request','verify_accepted') ORDER BY id", (jid,)).fetchall()
    except Exception:  # noqa: BLE001
        return terbit, dipakai
    for r in baris:
        if exclude_event is not None and int(r["id"]) == exclude_event:
            continue
        try:
            isi = json.loads(r["text"] or "")
        except (TypeError, ValueError):
            continue
        if not isinstance(isi, dict):
            continue
        # PENTING: verify_request menulis kunci `nonce`; verify_accepted memakai
        # `request_nonce`. Jangan tertukar: `nonce` di payload evidence tidak sah.
        if r["kind"] == "verify_request":
            nonce = isi.get("nonce")
            batas = evd.as_int(isi.get("expires_at"))
            if isinstance(nonce, str) and evd.is_hex64(nonce) and batas:
                terbit[nonce] = batas
        else:
            nonce = isi.get("request_nonce")
            if isinstance(nonce, str) and evd.is_hex64(nonce):
                dipakai.add(nonce)
    return terbit, dipakai


def _db_retry(fn, *args, **kwargs):
    """Retry singkat saat SQLITE_BUSY/locked (R-5), selain itu langsung naikkan."""
    for percobaan in range(1, _DB_TRIES + 1):
        try:
            return fn(*args, **kwargs)
        except sqlite3.OperationalError as e:
            pesan = str(e).lower()
            if percobaan == _DB_TRIES or not ("locked" in pesan or "busy" in pesan):
                raise
            time.sleep(0.2 * percobaan)
    raise AssertionError("tak terjangkau")  # pragma: no cover


def set_status(jid: int, status: str, note: str = "") -> None:
    _db_retry(jobs.set_status, jid, status, note)


def set_field(jid: int, **fields) -> None:
    _db_retry(jobs.set_field, jid, **fields)


def pause_if_building(jid: int, kode: str, note: str) -> bool:
    """Pindahkan job ke `paused` HANYA bila masih `building`. True bila menang.

    R-2 (review D6): `set_status` polos bisa menimpa `done`/`cancelled` yang ditulis
    proses lain di antara pemeriksaan dan penulisan. CAS menutup jendela itu.
    """
    def _kerja() -> bool:
        with contextlib.closing(jobs.connect()) as con:
            cur = con.execute(
                "UPDATE jobs SET status='paused', error=?, updated=?"
                " WHERE id=? AND status='building'", (kode[:200], time.time(), jid))
            menang = cur.rowcount == 1
            con.commit()
            return menang
    if not bool(_db_retry(_kerja)):
        return False
    _db_retry(jobs.add_event, jid, "paused", note)
    return True


def _add_event(jid: int, kind: str, text: str) -> None:
    _db_retry(jobs.add_event, jid, kind, text)


def add_event(jid: int, kind: str, text: str) -> None:
    _add_event(jid, kind, text)


def _env_int(nama: str, bawaan: int, bawah: int, atas: int) -> int:
    """Baca env integer dengan batas; nilai rusak/aneh -> bawaan (bukan 0)."""
    try:
        nilai = int(os.environ.get(nama, "") or bawaan)
    except (TypeError, ValueError):
        return bawaan
    return min(max(nilai, bawah), atas)


def reap_stale(max_age: float | None = None) -> int:
    """Kembalikan job yang tertinggal di status berjalan ke `paused` (R-5).

    Status menggantung terjadi bila proses mati di tengah jalan (OOM, SIGKILL,
    DB sibuk). Tanpa reaper, job itu tidak akan pernah diproses lagi.
    """
    if max_age is None:
        max_age = _env_int("SDB_STALE_BUILD_SECONDS", STALE_RUNNING_SECONDS, 60, 604_800)
    batas = max_age
    sekarang = time.time()
    dipulihkan = 0
    try:
        kandidat = [j for j in jobs.list_jobs(limit=200, only_open=True)
                    if j.get("status") in ("building", "spec_running")]
    except Exception:  # noqa: BLE001
        return 0
    for j in kandidat:
        jid = int(j["id"])
        lama = float(j.get("updated") or 0)
        status_lama = str(j.get("status") or "")
        if sekarang - lama <= batas:
            continue
        # Compare-and-swap: menang hanya bila status DAN `updated` belum berubah.
        # Tanpa ini, job yang selesai `done` di antara pembacaan daftar dan
        # penulisan akan "mundur" menjadi `paused` + error STALE_RUNNING.
        try:
            with contextlib.closing(jobs.connect()) as con:
                cur = con.execute(
                    "UPDATE jobs SET status='paused', updated=? WHERE id=? AND status=? "
                    "AND updated=?", (sekarang, jid, status_lama, lama))
                con.commit()
                menang = cur.rowcount == 1
        except Exception:  # noqa: BLE001
            continue
        if not menang:
            continue
        try:
            set_field(jid, error="STALE_RUNNING")
            _add_event(jid, "reaper",
                       f"status {status_lama} menggantung > {int(batas)} detik; "
                       "dikembalikan ke paused")
        except Exception:  # noqa: BLE001
            pass
        dipulihkan += 1
    return dipulihkan


def heartbeat(jid: int) -> None:
    """Tandai job masih hidup tanpa mengubah status.

    `jobs.add_event` tidak menyentuh kolom `updated`, jadi build panjang tanpa
    `session_id` bisa terlihat basi dan dipanen reaper padahal prosesnya hidup.
    """
    try:
        with contextlib.closing(jobs.connect()) as con:
            con.execute("UPDATE jobs SET updated=? WHERE id=? AND status IN "
                        "('building','spec_running')", (time.time(), jid))
            con.commit()
    except Exception:  # noqa: BLE001 — heartbeat tidak boleh menghentikan job
        pass


def _as_int(v: object) -> int | None:
    """Satu definisi ketat untuk kedua jalur (legacy & kontrak).

    Dulu legacy memakai `int()` longgar sehingga `job_id: true` atau `"12"`
    diterima, sementara jalur bertanda tangan menolaknya. Sekarang keduanya
    memakai `evd.as_int` (tolak bool dan string).
    """
    return evd.as_int(v)


def evidence_detail(job: dict, real: Path, digest: str, lengkap: bool = True) -> dict:
    """Rincian penerimaan bukti mesin: sah?, kode, tingkat, acceptance.

    Dua jalur penerimaan:
      * `sdb.verify.evidence/1` — kontrak bertanda tangan (C2-B1). Selalu diperiksa
        penuh: job, sidik, nonce, masa berlaku, signer, tanda tangan.
      * legacy C2-A (`schema: 1`, tanpa tanda tangan) — hanya diterima bila
        `SDB_EVIDENCE_MODE` bukan `strict`. Ini jujur: bukti tanpa tanda tangan
        TIDAK pernah menjadi `ACCEPTANCE_VERIFIED` dan tidak boleh dipakai untuk
        mengaktifkan `SDB_DONE_POLICY=verified`.
    """
    hasil = {"ok": False, "code": "EVIDENCE_INVALID", "level": "",
             "acceptance": False, "release_eligible": False, "reason": ""}
    if not lengkap:
        return {**hasil, "code": "EVIDENCE_DIGEST_INCOMPLETE",
                "reason": "sidik workspace tidak lengkap (anggaran entri/byte habis)"}
    jid = int(job["id"])
    eid, ev = latest_evidence_row(jid)
    if eid is None:
        return {**hasil, "code": "UNVERIFIED"}
    if not ev:
        return hasil

    if ev.get("schema") == evd.SCHEMA:
        terbit, dipakai = _nonce_state(jid, exclude_event=eid)
        hasil = evd.validate(
            ev, job_id=jid, workspace_digest=digest, digest_complete=lengkap,
            now=int(time.time()), nonce_issued=terbit, nonce_used=dipakai,
            allowed_signers=allowed_signers_path(), verifier_ids=authorized_verifiers(),
            pinned_criteria_digest=pinned_criteria_digest())
        if hasil["ok"]:
            # N2: penandaan nonce TIDAK ditulis di sini. Menulisnya sebelum status
            # `done` ter-commit membuat job yang gagal sesudahnya mustahil di-retry
            # (nonce terbakar, retry selalu EVIDENCE_REPLAY). Payload penerimaan
            # dikembalikan ke pemanggil dan ditulis bersama status oleh `finish_job`.
            verifier = ev.get("verifier")
            hasil["accept"] = {
                "schema": evd.REQUEST_SCHEMA, "job_id": jid,
                "request_nonce": ev.get("request_nonce"),
                "verifier": verifier.get("id") if isinstance(verifier, dict) else None,
                "level": hasil["level"], "accepted_at": int(time.time())}
        return hasil

    # --- jalur legacy C2-A ---
    if evd.evidence_mode() == "strict":
        return {**hasil, "code": "EVIDENCE_LEGACY_REJECTED",
                "reason": "mode strict menolak bukti tanpa tanda tangan"}
    verdict = ev.get("verdict")
    if verdict in ("FAIL", "TIMEOUT"):
        return {**hasil, "code": "VERIFY_FAIL" if verdict == "FAIL" else "VERIFY_TIMEOUT"}
    skema = ev.get("schema")
    if not isinstance(skema, int) or isinstance(skema, bool) or skema != 1:
        return hasil
    if verdict != "PASS":
        return hasil
    if _as_int(ev.get("job_id")) != jid:
        return hasil
    if str(ev.get("dir_real") or "") != str(real):
        return hasil
    if str(ev.get("tree_sha256") or "") != digest:
        return hasil
    return {"ok": True, "code": "", "level": "LEGACY_UNSIGNED",
            "acceptance": False, "release_eligible": False,
            "reason": "bukti legacy tanpa tanda tangan"}


def evidence_ok(job: dict, real: Path, digest: str, lengkap: bool = True) -> tuple[bool, str]:
    """(sah, kode) — pembungkus tipis `evidence_detail` untuk pemanggil lama."""
    d = evidence_detail(job, real, digest, lengkap)
    return bool(d["ok"]), str(d["code"])


def assess_completion(job: dict, d: Path) -> dict:
    """Hasil gerbang penyelesaian. `ok` False -> `code` berisi alasan (fail-closed).

    Kegagalan tak terduga tidak boleh membuat worker mati dengan job tertinggal di
    `building`; semuanya diterjemahkan menjadi kode dan status `paused`.
    """
    try:
        return _assess_completion(job, d)
    except Exception:  # noqa: BLE001
        return {"ok": False, "code": "COMPLETION_ERROR", "level": "", "readme": "",
                "verify": "", "dir_real": "", "tree_sha256": "", "digest_complete": False,
                "policy": done_policy()}


def _assess_completion(job: dict, d: Path) -> dict:
    hasil = {"ok": False, "code": "WORKSPACE_INVALID", "level": "", "readme": "",
             "verify": "", "dir_real": "", "tree_sha256": "", "digest_complete": False,
             "policy": done_policy()}
    real, kode = resolve_workspace(job)
    if kode or real is None:
        return hasil
    kode, readme, verify = read_docs(real)
    if kode:
        hasil["code"] = kode
        return hasil
    sidik, lengkap = tree_digest(real)
    hasil.update(readme=readme, verify=verify, dir_real=str(real),
                 tree_sha256=sidik, digest_complete=lengkap)
    if hasil["policy"] == "verified":
        # Mode `legacy` masih menerima event tanpa tanda tangan. Kalau itu hidup di
        # bawah `verified`, seluruh mesin tanda tangan bisa dilewati hanya dengan
        # tidak menyetel satu variabel lingkungan. Jadi `verified` menuntut `strict`
        # yang eksplisit; tidak ada jalur diam-diam.
        if evd.evidence_mode() != "strict":
            hasil["code"] = "EVIDENCE_MODE_REQUIRED"
            return hasil
        bukti = evidence_detail(job, real, sidik, lengkap)
        hasil["evidence"] = bukti
        if not bukti["ok"]:
            hasil["code"] = bukti["code"]
            return hasil
        # Level job membawa tingkat bukti yang sebenarnya. `EXECUTION_VERIFIED`
        # berarti "tes berjalan dan lulus", BUKAN "kriteria penerimaan terpenuhi";
        # di bawah kebijakan `verified` hanya tingkat acceptance yang boleh `done`
        # (N1). Tingkat yang tak dikenal ditolak, bukan diam-diam jadi "VERIFIED".
        tingkat = bukti["level"]
        if tingkat == evd.LEVEL_ACCEPTANCE:
            hasil.update(code="", level=tingkat)
        elif tingkat == evd.LEVEL_EXECUTION:
            hasil.update(code="ACCEPTANCE_NOT_MET", level=tingkat)
        else:
            hasil.update(code="EVIDENCE_LEVEL_UNKNOWN", level="")
    else:
        hasil.update(code="", level="ATTESTED",
                     evidence={"ok": False, "code": "", "level": "", "acceptance": False,
                               "release_eligible": False, "reason": "kebijakan attested"})
    # `ok` diturunkan dari kode: penolakan level bukti (N1) juga berarti belum tuntas.
    hasil["ok"] = not hasil["code"]
    return hasil


# ---------- tahap ----------
def finish_job(jid: int, note: str, hasil: dict) -> tuple[bool, str]:
    """Transisi `done` secara ATOMIK: status + `verify_accepted` + `completion`.

    N2: nonce hanya boleh dianggap terpakai bila job benar-benar menjadi `done`.
    Sebelumnya event penerimaan ditulis lebih dulu, lalu status; kegagalan di
    antaranya membuat retry selalu `EVIDENCE_REPLAY` tanpa sebab yang jelas.
    Di sini keempat tulisan berada dalam satu transaksi `BEGIN IMMEDIATE`:

    * CAS status (`WHERE status IN ('building','spec_running')`) — job yang sudah
      dipindahkan proses lain (done/cancelled) tidak bisa ditimpa;
    * pemeriksaan nonce diulang DI DALAM kunci tulis, menutup jendela balapan;
    * kegagalan apa pun -> `rollback` -> nonce utuh -> `/retry` tetap mungkin.
    """
    bukti = hasil.get("evidence") or {}
    terima = bukti.get("accept") if isinstance(bukti.get("accept"), dict) else None
    # F1: penjaga kedua di dalam transisi. `finish_job` tidak boleh percaya begitu
    # saja pada pemanggil — di bawah kebijakan selain `attested` (fail-closed: `verified`
    # maupun nilai tak dikenal), `done` hanya sah untuk bukti tingkat penerimaan
    # yang benar-benar lulus acceptance.
    if hasil.get("policy") != "attested" and (
            hasil.get("level") != evd.LEVEL_ACCEPTANCE or bukti.get("acceptance") is not True):
        return False, "ACCEPTANCE_NOT_MET"
    now = time.time()
    kompl = json.dumps(
        {"schema": 1, "job_id": jid, "level": hasil["level"], "policy": hasil["policy"],
         "dir_real": hasil["dir_real"], "tree_sha256": hasil["tree_sha256"],
         "digest_complete": hasil["digest_complete"],
         # C2-B1: tingkat bukti dicatat terpisah dari status. `done` tetap berarti
         # pekerjaan berhenti, bukan berarti siap rilis.
         "evidence": {"level": bukti.get("level", ""),
                      "acceptance": bool(bukti.get("acceptance")),
                      "release_eligible": False},
         "ts": round(now, 3)}, ensure_ascii=False)
    con = jobs.connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        cur = con.execute(
            "UPDATE jobs SET status='done', error='', updated=?"
            " WHERE id=? AND status='building'", (now, jid))
        if cur.rowcount != 1:
            con.rollback()
            return False, "DONE_CONFLICT"
        if terima:
            nonce = terima.get("request_nonce")
            for baris in con.execute(
                    "SELECT text FROM events WHERE job_id=? AND kind='verify_accepted'", (jid,)):
                teks = baris["text"]
                if not isinstance(teks, str):
                    continue
                try:
                    isi = json.loads(teks)
                except (ValueError, TypeError):
                    continue
                if not isinstance(isi, dict):
                    continue
                dipakai = isi.get("request_nonce")
                if isinstance(dipakai, str) and dipakai and dipakai == nonce:
                    con.rollback()
                    return False, "EVIDENCE_REPLAY"
            con.execute("INSERT INTO events(job_id,ts,kind,text) VALUES(?,?,?,?)",
                        (jid, now, "verify_accepted",
                         json.dumps(terima, ensure_ascii=False)[:8000]))
        con.execute("INSERT INTO events(job_id,ts,kind,text) VALUES(?,?,?,?)",
                    (jid, now, "done", note[:4000]))
        con.execute("INSERT INTO events(job_id,ts,kind,text) VALUES(?,?,?,?)",
                    (jid, now, "completion", kompl[:8000]))
        con.commit()
        return True, ""
    except Exception:
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        con.close()


def do_spec(job: dict) -> None:
    jid, d = job["id"], Path(job["dir"])
    d.mkdir(parents=True, exist_ok=True)
    set_status(jid, "spec_running", "spesifikasi dimulai")
    notify(f"[#{jid}] {job['title']}\nTahap 1: menyusun spesifikasi & rencana… (±2-5 menit)")
    text, sid, rc = run_hermes(SPEC_PROMPT.format(guard=GUARD, brief=job["brief"])
                               + (f"\nARAHAN/JAWABAN KLIEN (wajib dipatuhi):\n"
                                  f"{read_text(d / 'ANSWERS.md', 3000)}"
                                  if (d / "ANSWERS.md").exists() else ""),
                               d, SPEC_TIMEOUT, SPEC_TURNS)
    add_event(jid, "spec_output", text[:6000])
    if sid:
        set_field(jid, session_spec=sid)
    if rc != 0:
        set_field(jid, error=f"spec rc={rc}"[:200])
        set_status(jid, "failed", f"spesifikasi gagal (rc={rc}):\n{text[-800:]}")
        notify(f"[#{jid}] GAGAL tahap spesifikasi (rc={rc}).\n{text[-900:] or '(tanpa output)'}\n"
               f"Coba lagi: /retry {jid}")
        return
    set_status(jid, "spec_ready", "spesifikasi siap, menunggu persetujuan")
    q = read_text(d / "QUESTIONS.md", 900)
    body = (f"[#{jid}] {job['title']}\nSPESIFIKASI SIAP — menunggu persetujuan Anda.\n\n"
            f"{text[:1500]}\n")
    if q and "TIDAK ADA PERTANYAAN" not in q.upper():
        body += f"\nPERTANYAAN (jawab lewat /answer {jid} <jawaban>):\n{q[:900]}\n"
    body += (f"\nBerkas: {listing(d)}\n\n"
             f"Setujui: /approve {jid}\nRevisi: /revise {jid} <arahan>\nTolak: /reject {jid}")
    notify(body[:3900])


def do_build(job: dict) -> None:
    jid, d = job["id"], Path(job["dir"])
    set_status(jid, "building", "implementasi dimulai")
    notify(f"[#{jid}] {job['title']}\nTahap 2: implementasi + verifikasi nyata… "
           f"(bisa 10-40 menit; saya kabari kalau selesai)")
    answers = read_text(d / "ANSWERS.md", 2000)
    prompt = BUILD_PROMPT.format(guard=GUARD)
    if answers:
        prompt += f"\n\nJAWABAN KLIEN (wajib dipatuhi):\n{answers}"
    session = job.get("session_spec") or ""
    text, sid, rc, done = "", "", 0, False
    # Satu sesi agen punya batas turn; build besar butuh beberapa ronde.
    for ronde in range(1, ROUNDS + 1):
        heartbeat(jid)          # jaga `updated` segar: build panjang bukan job mati
        if ronde > 1:
            prompt = CONTINUE_PROMPT.format(guard=GUARD, round=ronde, rounds=ROUNDS)
        text, sid, rc = run_hermes(prompt, d, BUILD_TIMEOUT, BUILD_TURNS, session=session)
        add_event(jid, "build_output", f"ronde {ronde} rc={rc}:\n{text[-5000:]}")
        if sid:
            session = sid
            set_field(jid, session_build=sid)
        # Penanda "SELESAI" sering terlewat; bukti dokumentasi lebih keras daripada klaim.
        done = not read_docs(d)[0]
        if done:
            break
        if ronde < ROUNDS:
            notify(f"[#{jid}] ronde {ronde}/{ROUNDS} selesai (rc={rc}) — melanjutkan sisa pekerjaan…")
    if not done:
        # Ronde penutup: agen sering kehabisan turn setelah fitur jadi, dokumen terlewat.
        # Paksa satu ronde dokumentasi yang menjalankan verifikasi nyata.
        text2, sid2, rc2 = run_hermes(
            DOCS_PROMPT.format(guard=GUARD), d, min(BUILD_TIMEOUT, 1200), BUILD_TURNS,
            session=session)
        add_event(jid, "docs_round", f"rc={rc2}:\n{text2[-4000:]}")
        if sid2:
            set_field(jid, session_build=sid2)
        if text2:
            text, rc = text2, rc2
        done = not read_docs(d)[0]
    # Gerbang penyelesaian: dokumen sah bukan bukti. Periksa identitas job, lokasi
    # direktori, bentuk dokumen, dan pada kebijakan `verified` bukti mesin terikat.
    # Jalur "belum tuntas" juga lewat sini agar kode alasannya spesifik.
    hasil = assess_completion(job, d)
    if not hasil["ok"]:
        kode = hasil["code"]
        alasan = {
            "DOCS_INVALID": "README.md/VERIFY.md tidak ada, kosong, symlink, atau hardlink.",
            "WORKSPACE_INVALID": "direktori kerja tidak sah (luar SDB_BUILDS/symlink/ID tak cocok).",
            "UNVERIFIED": "belum ada bukti verifikasi mesin untuk kebijakan `verified`.",
            "EVIDENCE_INVALID": "bukti tidak terikat job/isi workspace saat ini (atau rusak).",
            "EVIDENCE_SCHEMA": "versi skema/field evidence tidak sah.",
            "EVIDENCE_JOB_MISMATCH": "evidence milik job lain.",
            "EVIDENCE_NO_NONCE": "evidence tanpa nonce permintaan verifikasi.",
            "EVIDENCE_NONCE_UNKNOWN": "nonce bukan untuk job ini.",
            "EVIDENCE_REPLAY": "nonce sudah dipakai (evidence lama diputar ulang).",
            "EVIDENCE_EXPIRED": "evidence sudah kedaluwarsa.",
            "EVIDENCE_CLOCK": "waktu penerbitan evidence di masa depan.",
            "EVIDENCE_SNAPSHOT_INCOMPLETE": "snapshot yang diverifikasi tidak lengkap.",
            "EVIDENCE_DIGEST_INCOMPLETE": "sidik workspace tidak lengkap.",
            "EVIDENCE_DIGEST_MISMATCH": "workspace berubah setelah diverifikasi.",
            "EVIDENCE_UNKNOWN_VERIFIER": "verifier tidak ada di daftar yang diizinkan.",
            "EVIDENCE_NO_SIGNATURE": "evidence tanpa tanda tangan.",
            "EVIDENCE_SIGNATURE_ALG": "algoritma/namespace tanda tangan tidak didukung.",
            "EVIDENCE_UNTRUSTED_SIGNER": "tanda tangan tidak sah untuk signer ini.",
            "EVIDENCE_VERIFIER_UNAVAILABLE": "alat verifikasi tanda tangan tidak tersedia.",
            "EVIDENCE_SIGNER_STORE": "daftar signer tidak layak dipakai (hilang/symlink/terbuka).",
            "EVIDENCE_LEGACY_REJECTED": "mode strict menolak bukti tanpa tanda tangan.",
            "EVIDENCE_MODE_REQUIRED": "kebijakan `verified` menuntut SDB_EVIDENCE_MODE=strict.",
            "EVIDENCE_REQUEST_EXPIRED": "permintaan verifikasi (nonce) sudah kedaluwarsa.",
            "ACCEPTANCE_NOT_MET": ("bukti hanya level eksekusi: tes berjalan, tetapi kriteria "
                                  "penerimaan belum terpenuhi. `done` menuntut acceptance."),
            "EVIDENCE_LEVEL_UNKNOWN": "tingkat bukti tidak dikenal (fail-closed).",
            "DONE_CONFLICT": "job sudah dipindahkan proses lain (tidak lagi building).",
            "VERIFY_FAIL": "verifikasi mesin terakhir gagal.",
            "VERIFY_TIMEOUT": "verifikasi mesin terakhir timeout.",
        }.get(kode, "syarat penyelesaian belum terpenuhi.")
        set_field(jid, error=kode[:200])
        set_status(jid, "paused", f"gerbang penyelesaian menolak: {kode}\n{text[-3000:]}")
        notify(f"[#{jid}] {job['title']}\nBELUM TUNTAS — gerbang penyelesaian menolak ({kode}).\n"
               f"{alasan}\nIsi VERIFY.md tidak dianggap bukti mesin.\n"
               f"Lokasi: {d}\nLanjutkan: /retry {jid}")
        return
    # Semua pembacaan setelah gerbang memakai direktori NYATA hasil validasi,
    # bukan path dari kolom DB, agar rename/symlink setelah gerbang tidak dipakai.
    dir_real = Path(hasil["dir_real"])
    if not dir_real.is_dir():
        set_field(jid, error="WORKSPACE_INVALID")
        set_status(jid, "paused", "direktori berubah setelah gerbang penyelesaian")
        notify(f"[#{jid}] gerbang lolos tetapi direktori kerja hilang/berubah. "
               f"Lanjutkan: /retry {jid}")
        return
    # N2: transisi `done` + penandaan nonce + event `completion` dalam satu
    # transaksi. Kalau gagal, job kembali ke `paused` dengan nonce utuh.
    sukses, kode_commit = _db_retry(finish_job, jid, text[-4000:], hasil)
    if not sukses:
        alasan_commit = {
            "DONE_CONFLICT": "job sudah dipindahkan proses lain (tidak lagi building).",
            "EVIDENCE_REPLAY": "nonce evidence sudah dipakai penerimaan lain.",
            "ACCEPTANCE_NOT_MET": "bukti belum level penerimaan; `done` tidak boleh ditulis.",
        }.get(kode_commit, "penulisan status selesai gagal.")
        # F2/R-2: `paused` ditulis dengan CAS `status='building'` — kalau di antara
        # pemeriksaan dan penulisan ini proses lain sudah memindahkan job
        # (`done`/`cancelled`), tidak ada yang ditimpa.
        if not pause_if_building(jid, kode_commit,
                                 f"transisi `done` dibatalkan: {kode_commit}"):
            kini = (jobs.get(jid) or {}).get("status", "?")
            notify(f"[#{jid}] {job['title']}\nTransisi ganda diabaikan — status sudah "
                   f"`{kini}` ({kode_commit}). Tidak ada yang ditimpa.")
            return
        notify(f"[#{jid}] {job['title']}\nBELUM TUNTAS — transisi `done` dibatalkan "
               f"({kode_commit}).\n{alasan_commit}\nLokasi: {d}\nLanjutkan: /retry {jid}")
        return
    bukti = hasil.get("evidence") or {}
    verify = hasil["verify"][:700]
    gaps = read_text(dir_real / "GAPS.md", 700)
    body = f"[#{jid}] {job['title']} — SELESAI ({hasil['level']})\n"
    if hasil["level"] == "ATTESTED":
        body += ("LEVEL BUKTI: ATTESTED — dokumen diperiksa, TIDAK diverifikasi mesin. "
                 "Bukan bukti release independen.\n")
    elif bukti.get("level"):
        body += (f"TINGKAT BUKTI MESIN: {bukti.get('level')}"
                 f"{'' if bukti.get('acceptance') else ' (penerimaan BELUM terpenuhi)'} — "
                 f"bukan izin rilis.\n")
    body += f"\n{text[:1600]}\n\nLokasi: {dir_real}\n{listing(dir_real)}\n"
    if verify:
        body += f"\nBUKTI VERIFIKASI (klaim agen, bukan hasil mesin):\n{verify}\n"
    if gaps:
        body += f"\nCATATAN GAPS:\n{gaps}\n"
    body += f"\nUbah lagi: /revise {jid} <arahan> · Log: /job {jid}"
    notify(body[:3900])


# ---------- loop ----------
def once() -> int:
    # Reaper dijalankan tiap putaran: job yang tertinggal di status berjalan
    # (proses mati/SIGKILL/DB sibuk) harus bisa dilanjutkan lewat /retry.
    try:
        reap_stale()
    except Exception:  # noqa: BLE001 — reaper tidak boleh menghentikan loop
        pass
    did = 0
    job = jobs.claim("spec_queued", "spec_running")
    if job:
        do_spec(job)
        did += 1
    job = jobs.claim("build_queued", "building")
    if job:
        do_build(job)
        did += 1
    return did


def main() -> int:
    # Jalur operator: terbitkan nonce verifikasi untuk satu job, lalu keluar.
    # Diletakkan SEBELUM pemeriksaan token/owner karena hanya menyentuh DB lokal
    # (tidak mengirim apa pun ke Telegram).
    if "--issue-nonce" in sys.argv:
        i = sys.argv.index("--issue-nonce")
        if i + 1 >= len(sys.argv):
            print("pakai: --issue-nonce <job_id>", file=sys.stderr)
            return 2
        try:
            jid = int(sys.argv[i + 1])
        except ValueError:
            print("job_id harus angka", file=sys.stderr)
            return 2
        job = jobs.get(jid)
        if not job:
            print(f"job #{jid} tidak ada", file=sys.stderr)
            return 1
        nonce = issue_nonce(jid)
        print(nonce)
        return 0
    if not TOKEN or not OWNER:
        print("SDB_TG_BOT_TOKEN / SDB_TG_CHAT_ID belum diset", file=sys.stderr)
        return 2
    if "--once" in sys.argv:
        once()
        return 0
    while True:
        try:
            if not once():
                time.sleep(POLL)
        except Exception as e:  # noqa: BLE001 — worker tidak boleh mati karena satu job rusak
            print(f"loop error: {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
