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

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdb_jobs as jobs  # noqa: E402

TOKEN = os.environ.get("SDB_TG_BOT_TOKEN", "")
OWNER = os.environ.get("SDB_TG_CHAT_ID", "")
MODEL = os.environ.get("SDB_BUILD_MODEL", "")
SPEC_TIMEOUT = int(os.environ.get("SDB_SPEC_TIMEOUT", "900"))
BUILD_TIMEOUT = int(os.environ.get("SDB_BUILD_TIMEOUT", "3600"))
SPEC_TURNS = int(os.environ.get("SDB_SPEC_TURNS", "40"))
BUILD_TURNS = int(os.environ.get("SDB_BUILD_TURNS", "300"))
POLL = int(os.environ.get("SDB_WORKER_POLL", "10"))
ROUNDS = int(os.environ.get("SDB_BUILD_ROUNDS", "3"))

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
    spec = read_text(d / "SPEC.md", 1500)
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
        done = (d / "README.md").exists() and (d / "VERIFY.md").exists()
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
        done = (d / "README.md").exists() and (d / "VERIFY.md").exists()
    if not done:
        jobs.set_field(jid, error=f"belum tuntas setelah {ROUNDS} ronde (rc={rc})"[:200])
        jobs.set_status(jid, "paused", text[-4000:])
        notify(f"[#{jid}] {job['title']}\nBELUM TUNTAS setelah {ROUNDS} ronde.\n"
               f"{text[-1100:] or '(tanpa output)'}\n\nLokasi: {d}\nLanjutkan: /retry {jid}")
        return
    jobs.set_status(jid, "done", text[-4000:])
    verify = read_text(d / "VERIFY.md", 700)
    gaps = read_text(d / "GAPS.md", 700)
    body = (f"[#{jid}] {job['title']} — SELESAI\n\n{text[:1600]}\n\n"
            f"Lokasi: {d}\n{listing(d)}\n")
    if verify:
        body += f"\nBUKTI VERIFIKASI:\n{verify}\n"
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
        except Exception as e:  # worker tidak boleh mati karena satu job rusak
            print(f"loop error: {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
