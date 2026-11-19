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

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
    rows, total = [], 0
    for f in sorted(d.rglob("*")):
        if not f.is_file() or ".git" in f.parts or "__pycache__" in f.parts:
            continue
        total += f.stat().st_size
        if len(rows) < limit:
            rows.append(f"  {f.relative_to(d)} ({f.stat().st_size / 1024:.0f} KB)")
    head = f"{total / 1024:.0f} KB total" if total else "kosong"
    return head + ("\n" + "\n".join(rows) if rows else "")


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


def read_docs(d: Path) -> tuple[str, str, str]:
    """(kode, readme, verify). kode "" berarti dokumen sah dan tidak kosong."""
    readme = _safe_read(d / "README.md", DOC_MAX_BYTES)
    verify = _safe_read(d / "VERIFY.md", DOC_MAX_BYTES)
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
    lengkap = True
    mulai = time.monotonic()
    for root, dirs, files in os.walk(d, followlinks=False):
        if time.monotonic() - mulai > DIGEST_TIME_MAX:
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


def latest_evidence(jid: int) -> dict | None:
    """Event `verify` terakhir untuk job ini. None = tidak ada; {} = tidak bisa dipakai.

    Query langsung, bukan memindai N event terakhir: event `verify` bisa tertimbun
    puluhan `build_output` dari ronde/retry sebelumnya.
    """
    try:
        with jobs.connect() as con:
            baris = con.execute(
                "SELECT text FROM events WHERE job_id=? AND kind='verify' "
                "ORDER BY id DESC LIMIT 1", (jid,)).fetchone()
    except Exception:  # noqa: BLE001
        return {}
    if baris is None:
        return None
    try:
        isi = json.loads(baris["text"] or "")
    except (TypeError, ValueError, IndexError, KeyError):
        return {}
    return isi if isinstance(isi, dict) else {}


def _as_int(v: object) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def evidence_ok(job: dict, real: Path, digest: str, lengkap: bool = True) -> tuple[bool, str]:
    """Bukti mesin sah hanya bila PASS, terikat job + dir nyata + isi workspace.

    `lengkap=False` (sidik sebagian) selalu ditolak: sidik parsial tidak bisa
    membuktikan isi workspace tidak berubah.
    """
    if not lengkap:
        return False, "EVIDENCE_INVALID"
    ev = latest_evidence(int(job["id"]))
    if ev is None:
        return False, "UNVERIFIED"
    if not ev:
        return False, "EVIDENCE_INVALID"
    verdict = ev.get("verdict")
    if verdict in ("FAIL", "TIMEOUT"):
        return False, "VERIFY_FAIL" if verdict == "FAIL" else "VERIFY_TIMEOUT"
    skema = ev.get("schema")
    if not isinstance(skema, int) or isinstance(skema, bool) or skema != 1:
        return False, "EVIDENCE_INVALID"
    if verdict != "PASS":
        return False, "EVIDENCE_INVALID"
    if _as_int(ev.get("job_id")) != int(job["id"]):
        return False, "EVIDENCE_INVALID"
    if str(ev.get("dir_real") or "") != str(real):
        return False, "EVIDENCE_INVALID"
    if str(ev.get("tree_sha256") or "") != digest:
        return False, "EVIDENCE_INVALID"
    return True, ""


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
        sah, kode = evidence_ok(job, real, sidik, lengkap)
        if not sah:
            hasil["code"] = kode
            return hasil
        hasil.update(code="", level="VERIFIED")
    else:
        hasil.update(code="", level="ATTESTED")
    hasil["ok"] = True
    return hasil


# ---------- tahap ----------
def do_spec(job: dict) -> None:
    jid, d = job["id"], Path(job["dir"])
    d.mkdir(parents=True, exist_ok=True)
    jobs.set_status(jid, "spec_running", "spesifikasi dimulai")
    notify(f"[#{jid}] {job['title']}\nTahap 1: menyusun spesifikasi & rencana… (±2-5 menit)")
    text, sid, rc = run_hermes(SPEC_PROMPT.format(guard=GUARD, brief=job["brief"])
                               + (f"\nARAHAN/JAWABAN KLIEN (wajib dipatuhi):\n"
                                  f"{read_text(d / 'ANSWERS.md', 3000)}"
                                  if (d / "ANSWERS.md").exists() else ""),
                               d, SPEC_TIMEOUT, SPEC_TURNS)
    jobs.add_event(jid, "spec_output", text[:6000])
    if sid:
        jobs.set_field(jid, session_spec=sid)
    if rc != 0:
        jobs.set_field(jid, error=f"spec rc={rc}"[:200])
        jobs.set_status(jid, "failed", f"spesifikasi gagal (rc={rc}):\n{text[-800:]}")
        notify(f"[#{jid}] GAGAL tahap spesifikasi (rc={rc}).\n{text[-900:] or '(tanpa output)'}\n"
               f"Coba lagi: /retry {jid}")
        return
    jobs.set_status(jid, "spec_ready", "spesifikasi siap, menunggu persetujuan")
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
    jobs.set_status(jid, "building", "implementasi dimulai")
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
        if ronde > 1:
            prompt = CONTINUE_PROMPT.format(guard=GUARD, round=ronde, rounds=ROUNDS)
        text, sid, rc = run_hermes(prompt, d, BUILD_TIMEOUT, BUILD_TURNS, session=session)
        jobs.add_event(jid, "build_output", f"ronde {ronde} rc={rc}:\n{text[-5000:]}")
        if sid:
            session = sid
            jobs.set_field(jid, session_build=sid)
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
        jobs.add_event(jid, "docs_round", f"rc={rc2}:\n{text2[-4000:]}")
        if sid2:
            jobs.set_field(jid, session_build=sid2)
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
            "VERIFY_FAIL": "verifikasi mesin terakhir gagal.",
            "VERIFY_TIMEOUT": "verifikasi mesin terakhir timeout.",
        }.get(kode, "syarat penyelesaian belum terpenuhi.")
        jobs.set_field(jid, error=kode[:200])
        jobs.set_status(jid, "paused", f"gerbang penyelesaian menolak: {kode}\n{text[-3000:]}")
        notify(f"[#{jid}] {job['title']}\nBELUM TUNTAS — gerbang penyelesaian menolak ({kode}).\n"
               f"{alasan}\nIsi VERIFY.md tidak dianggap bukti mesin.\n"
               f"Lokasi: {d}\nLanjutkan: /retry {jid}")
        return
    # Semua pembacaan setelah gerbang memakai direktori NYATA hasil validasi,
    # bukan path dari kolom DB, agar rename/symlink setelah gerbang tidak dipakai.
    dir_real = Path(hasil["dir_real"])
    if not dir_real.is_dir():
        jobs.set_field(jid, error="WORKSPACE_INVALID")
        jobs.set_status(jid, "paused", "direktori berubah setelah gerbang penyelesaian")
        notify(f"[#{jid}] gerbang lolos tetapi direktori kerja hilang/berubah. "
               f"Lanjutkan: /retry {jid}")
        return
    jobs.set_status(jid, "done", text[-4000:])
    jobs.set_field(jid, error="")
    jobs.add_event(jid, "completion", json.dumps(
        {"schema": 1, "job_id": jid, "level": hasil["level"], "policy": hasil["policy"],
         "dir_real": hasil["dir_real"], "tree_sha256": hasil["tree_sha256"],
         "digest_complete": hasil["digest_complete"], "ts": round(time.time(), 3)},
        ensure_ascii=False))
    verify = hasil["verify"][:700]
    gaps = read_text(dir_real / "GAPS.md", 700)
    body = f"[#{jid}] {job['title']} — SELESAI ({hasil['level']})\n"
    if hasil["level"] == "ATTESTED":
        body += ("LEVEL BUKTI: ATTESTED — dokumen diperiksa, TIDAK diverifikasi mesin. "
                 "Bukan bukti release independen.\n")
    body += f"\n{text[:1600]}\n\nLokasi: {dir_real}\n{listing(dir_real)}\n"
    if verify:
        body += f"\nBUKTI VERIFIKASI (klaim agen, bukan hasil mesin):\n{verify}\n"
    if gaps:
        body += f"\nCATATAN GAPS:\n{gaps}\n"
    body += f"\nUbah lagi: /revise {jid} <arahan> · Log: /job {jid}"
    notify(body[:3900])


# ---------- loop ----------
def once() -> int:
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
