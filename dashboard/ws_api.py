"""SDB Workspace API — diskusi ide -> draft Gate #0 -> approve -> tahap pipeline.

Prinsip (aturan repo):
- Tidak ada tahap jalan tanpa approve Owner (Gate #0).
- Tidak ada klaim "selesai" tanpa artefak nyata di disk; status = file yang ada.
- LLM dipanggil via `hermes -p <profil> -z` dengan toolset dibatasi (tanpa shell/file),
  karena server ini terbuka di LAN. Semua endpoint wajib header X-SDB-Token.
- Tidak ada kredensial di prompt, log, atau artefak.
"""
import datetime
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOME = Path.home()
DATA = HOME / "sdb-workspace"
HERMES = str(HOME / ".local/bin/hermes")
TOKEN_FILE = DATA / ".token"
MAX_BODY = 64 * 1024
MAX_PARALLEL = 2

STAGES = [
    ("01", "Intake", "cc-orchestrator", "doc"),
    ("02", "Clarify", "cc-orchestrator", "doc"),
    ("03", "Scope", "cc-orchestrator", "doc"),
    ("04", "ADR/Design", "cc-architect", "doc"),
    ("05", "Recon", "cc-capture-forensics", "doc"),
    ("06", "Impl Plan", "cc-orchestrator", "doc"),
    ("07", "Build", "cc-builder", "exec"),
    ("08", "Review", "cc-reviewer-qa", "exec"),
    ("09", "QA/E2E", "cc-reviewer-qa", "exec"),
    ("10", "Security", "cc-security-governor", "exec"),
    ("11", "Audit", "auditor", "exec"),
    ("12", "Verdict", "auditor", "exec"),
    ("13", "Dashboard", "cc-frontend", "exec"),
    ("14", "Release", "cc-devops-docs", "exec"),
    ("15", "Deploy", "cc-devops-docs", "exec"),
    ("16", "Handover", "cc-devops-docs", "exec"),
]
# Tahap "doc" = keluaran dokumen murni (aman dijalankan dari web).
# Tahap "exec" = butuh kode/test/scan nyata di repo -> hanya brief serah-terima.

SEED_PROJECTS = [
    {"id": "villa-agency", "name": "Villa Agency", "path": str(HOME / "villa-agency-os"), "kind": "real"},
    {"id": "rt-rw-portal", "name": "RT-RW Portal Warga", "path": str(HOME / "rt-rw-portal"), "kind": "real"},
]

_lock = threading.RLock()
JOBS = {}


# ----------------------------------------------------------------- util
def hermes_env():
    """Environment subprocess hermes: warisi env + kunci dari ~/.hermes/.env
    (profil tidak membaca .env global; tanpa ini systemd -> 401). Nilai tak pernah dicetak."""
    env = dict(os.environ)
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env["PATH"] = str(HOME / ".local/bin") + ":" + env["PATH"]
    try:
        for line in (HOME / ".hermes" / ".env").read_text().splitlines():
            m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
            if m and m.group(1) not in env:
                env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s or "proyek")[:40]


rate_401: dict[str, list[float]] = {}
rate_lock = threading.Lock()


def get_token():
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = None
    if not TOKEN_FILE.exists():
        # Tulis ke berkas sementara 0600 lalu os.link (atomik, gagal bila sudah ada):
        # pembaca tidak pernah melihat berkas kosong; dua thread tidak bertabrakan.
        tmp = TOKEN_FILE.with_name(f".token.{os.getpid()}.{threading.get_ident()}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(9))
        try:
            os.link(tmp, TOKEN_FILE)
        except FileExistsError:
            pass
        finally:
            os.unlink(tmp)
    tok = TOKEN_FILE.read_text().strip()
    if not tok:  # fail-closed: token kosong tidak boleh membuat auth lolos
        raise RuntimeError("berkas token kosong — hapus lalu restart layanan")
    return tok


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    tmp.replace(path)


def registry():
    reg = read_json(DATA / "projects.json", None)
    if reg is None:
        reg = SEED_PROJECTS
        write_json(DATA / "projects.json", reg)
    return reg


def find_project(pid):
    for p in registry():
        if p["id"] == pid:
            return p
    return None


_PID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,59}")


def pdir(pid):
    # Tolak "../" dan path absolut: pid datang dari klien (scope/project/artifact).
    if not isinstance(pid, str) or not _PID_RE.fullmatch(pid):
        raise ValueError("id proyek tidak valid")
    return DATA / "projects" / pid


def stage_status(pid):
    """Status tiap tahap dari FILE nyata di disk (bukan klaim)."""
    d = pdir(pid) / "stages"
    out = []
    for num, name, prof, kind in STAGES:
        hit = sorted(d.glob(f"{num}-*.md")) if d.exists() else []
        brief = [h for h in hit if h.name.endswith(".brief.md")]
        done = [h for h in hit if not h.name.endswith(".brief.md")]
        out.append({"n": num, "name": name, "profile": prof, "kind": kind,
                    "state": "done" if done else ("brief" if brief else "todo"),
                    "file": (done or brief or [None])[0].name if hit else None})
    return out


def sh(args, cwd, timeout=8):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[ws_api] perintah gagal: {type(exc).__name__}: {exc}", file=sys.stderr)
        return ""


def project_facts(p):
    """Fakta read-only dari repo nyata (terverifikasi saat dibaca)."""
    path = Path(p.get("path", ""))
    if not path.is_dir():
        return {"exists": False}
    git = (path / ".git").exists()
    top = sorted(x.name for x in path.iterdir() if not x.name.startswith("."))[:14]
    return {"exists": True, "git": git,
            "head": sh(["git", "log", "-1", "--format=%h %s"], path) if git else "",
            "dirty": bool(sh(["git", "status", "--porcelain"], path)) if git else None,
            "top": top}


# ----------------------------------------------------------------- LLM job runner
def run_llm(profile, prompt, toolsets="todo", timeout=300):
    cmd = [HERMES, "-p", profile, "--ignore-rules", "-t", toolsets, "-z", prompt]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=hermes_env())
    out = (r.stdout or "").strip()
    if r.returncode != 0 or not out:
        raise RuntimeError((r.stderr or out or "kosong")[-300:])
    if re.search(r"rejected your API key|HTTP 40[13]", out[:400]):
        raise RuntimeError("provider menolak kunci/kuota: " + out[:200].replace("\n", " "))
    return out


def start_job(kind, profile, project, fn):
    with _lock:
        running = [j for j in JOBS.values() if j["status"] == "running"]
        if len(running) >= MAX_PARALLEL:
            raise RuntimeError(f"maks {MAX_PARALLEL} job bersamaan — tunggu salah satu selesai")
        if any(j["project"] == project and j["status"] == "running" for j in running):
            raise RuntimeError("proyek ini masih punya job berjalan")
        jid = uuid.uuid4().hex[:8]
        job = {"id": jid, "kind": kind, "profile": profile, "project": project,
               "status": "running", "started": now(), "t0": time.time(), "result": None, "error": None}
        JOBS[jid] = job

    def work():
        try:
            job["result"] = fn()
            job["status"] = "done"
        except subprocess.TimeoutExpired:
            job["status"], job["error"] = "error", "timeout"
        except Exception as e:  # noqa: BLE001 — batas thread job: kode tugas arbitrer; galat direkam ke job["error"], tidak ditelan
            job["status"], job["error"] = "error", str(e)[:300]
        job["ended"] = now()
        job["secs"] = round(time.time() - job["t0"], 1)

    threading.Thread(target=work, daemon=True).start()
    return job


def public_job(j):
    return {k: j.get(k) for k in ("id", "kind", "profile", "project", "status", "started", "ended",
                                  "secs", "result", "error")}


# ----------------------------------------------------------------- chat / draft
CHAT_RULES = """Kamu adalah "Kapten", orchestrator Super Dev Builders (SDB). Lawan bicara = Mas Anas (Owner).
Tugas: diskusikan ide proyek (web / Android / SaaS) sampai jelas, lalu rangkum jadi DRAFT intake.
Aturan: Bahasa Indonesia, ringkas, tanpa basa-basi. Tanya klarifikasi MAKS 3 hal paling penting sekaligus.
Jangan mengarang fakta, harga, atau teknologi yang tidak diminta. Jangan klaim sesuatu sudah dibangun.
Tidak ada eksekusi apa pun terjadi dari obrolan ini; pipeline hanya jalan setelah Owner menekan Approve.
Jika info cukup (tujuan, pengguna, fitur inti, platform, batasan), AKHIRI jawaban dengan satu blok:
<DRAFT>{"title":"...","type":"web|android|saas","summary":"...","users":"...","features":["..."],"platform":"...","constraints":"...","risks":["..."],"open_questions":["..."]}</DRAFT>
(JSON valid satu baris, tanpa komentar). Jika belum cukup, JANGAN keluarkan blok DRAFT."""


def chat_file(cid):
    return DATA / "chats" / f"{re.sub(r'[^a-zA-Z0-9_-]', '', cid)[:40] or 'x'}.json"


def project_context(scope):
    if scope in ("", "baru", None):
        return "Konteks: ide proyek BARU (belum ada repo)."
    p = find_project(scope)
    if not p:
        return "Konteks: ide proyek BARU."
    f = project_facts(p)
    lines = [f"Konteks: proyek nyata '{p['name']}' (path {p['path']})."]
    if f.get("exists"):
        lines.append("Isi folder (terverifikasi): " + ", ".join(f["top"]))
        if f.get("head"):
            lines.append("Commit terakhir: " + f["head"])
    return "\n".join(lines)


def do_chat(body):
    msg = (body.get("message") or "").strip()[:4000]
    if not msg:
        raise ValueError("pesan kosong")
    cid = body.get("cid") or uuid.uuid4().hex[:10]
    scope = body.get("scope") or "baru"
    if scope != "baru" and not find_project(scope):
        raise ValueError("proyek tidak dikenal")
    cf = chat_file(cid)
    hist = read_json(cf, {"cid": cid, "scope": scope, "messages": [], "drafts": []})
    hist["scope"] = scope
    tail = hist["messages"][-10:]
    convo = "\n".join(f"{'Owner' if m['role'] == 'user' else 'Kapten'}: {m['text'][:1500]}" for m in tail)
    prompt = f"{CHAT_RULES}\n\n{project_context(scope)}\n\nRiwayat:\n{convo or '(awal)'}\n\nPesan baru Owner: {msg}"

    def fn():
        raw = run_llm("cc-orchestrator", prompt, toolsets="todo", timeout=180)
        draft = None
        m = re.search(r"<DRAFT>(.*?)</DRAFT>", raw, re.S)
        if m:
            try:
                d = json.loads(m.group(1).strip())
                if isinstance(d, dict) and d.get("title"):
                    d["id"] = uuid.uuid4().hex[:8]
                    d["created"] = now()
                    d["status"] = "pending"
                    draft = d
            except ValueError:
                draft = None
        reply = re.sub(r"<DRAFT>.*?</DRAFT>", "", raw, flags=re.S).strip()
        with _lock:
            h = read_json(cf, hist)
            h["messages"] += [{"role": "user", "text": msg, "t": now()},
                              {"role": "kapten", "text": reply, "t": now()}]
            if draft:
                h["drafts"].append(draft)
            write_json(cf, h)
        return {"cid": cid, "reply": reply, "draft": draft}

    return start_job("chat", "cc-orchestrator", f"chat:{cid}", fn), cid


def intake_md(d, scope):
    feats = "\n".join(f"- {x}" for x in d.get("features", []))
    risks = "\n".join(f"- {x}" for x in d.get("risks", [])) or "- (belum ada)"
    qs = "\n".join(f"- {x}" for x in d.get("open_questions", [])) or "- (tidak ada)"
    return f"""# Intake (Gate #0) — {d['title']}

- Tipe: {d.get('type', '-')}
- Platform: {d.get('platform', '-')}
- Konteks: {'proyek baru' if scope in ('baru', '') else 'perubahan pada ' + scope}
- Disetujui Owner: {now()}

## Ringkasan
{d.get('summary', '')}

## Pengguna
{d.get('users', '')}

## Fitur inti
{feats}

## Batasan
{d.get('constraints', '')}

## Risiko
{risks}

## Pertanyaan terbuka
{qs}
"""


def do_approve(body):
    # Seluruh baca-periksa-tulis di bawah satu kunci (RLock): dua approve paralel
    # tidak bisa membuat proyek ganda atau menimpa chat dengan snapshot basi.
    with _lock:
        return _do_approve(body)


def _do_approve(body):
    cid, did = body.get("cid", ""), body.get("draft_id", "")
    cf = chat_file(cid)
    h = read_json(cf, None)
    if not h:
        raise ValueError("percakapan tidak ditemukan")
    draft = next((x for x in h["drafts"] if x["id"] == did), None)
    if not draft:
        raise ValueError("draft tidak ditemukan")
    if draft["status"] == "approved":
        raise ValueError("draft sudah disetujui")
    scope = h.get("scope", "baru")
    with _lock:
        if scope in ("baru", ""):
            pid = slugify(draft["title"])
            reg = registry()
            base, i = pid, 2
            while any(p["id"] == pid for p in reg):
                pid, i = f"{base}-{i}", i + 1
            reg.append({"id": pid, "name": draft["title"][:60], "path": "", "kind": "baru",
                        "type": draft.get("type", "")})
            write_json(DATA / "projects.json", reg)
        else:
            pid = scope
        d = pdir(pid)
        (d / "stages").mkdir(parents=True, exist_ok=True)
        n = len(list((d / "intakes").glob("*.json"))) + 1 if (d / "intakes").exists() else 1
        write_json(d / "intakes" / f"{n:02d}-{draft['id']}.json", draft)
        md = intake_md(draft, scope)
        (d / "stages" / f"01-intake{'' if n == 1 else '-' + str(n)}.md").write_text(md)
        draft["status"] = "approved"
        draft["approved"] = now()
        draft["project"] = pid
        write_json(cf, h)
    return {"project": pid, "stage": "01"}


# ----------------------------------------------------------------- stages
STAGE_BRIEF = {
    "02": "Daftar pertanyaan klarifikasi yang benar-benar menentukan scope (maks 8), tiap item dengan opsi jawaban & rekomendasi + alasan. Jangan mengarang jawaban Owner.",
    "03": "Dokumen Scope: in-scope, out-of-scope, kriteria sukses terukur, asumsi (ditandai ASUMSI), dependensi, estimasi kasar (rentang, ditandai estimasi).",
    "04": "ADR/Design: pilihan stack (2-3 opsi + trade-off + rekomendasi), arsitektur tingkat tinggi, model data inti, batas keamanan & privasi, risiko. Tandai apa yang butuh keputusan Owner.",
    "05": "Recon: ringkasan praktik/solusi sejenis & risiko pasar/teknis yang relevan. Sebut sumber bila ada; tandai TIDAK TERVERIFIKASI bila dari ingatan model.",
    "06": "Implementation Plan: pecah jadi milestone & task terurut, tiap task punya kriteria selesai yang bisa diuji, urutan dependensi, dan siapa (Frontend/Backend/DevOps) yang mengerjakan.",
}


def prior_docs(pid, upto):
    d = pdir(pid) / "stages"
    parts = []
    for f in sorted(d.glob("*.md")):
        if f.name.endswith(".brief.md") or f.name[:2] >= upto:
            continue
        parts.append(f"### {f.name}\n{f.read_text()[:3500]}")
    return "\n\n".join(parts)[:12000]


def clean_doc(text):
    """Buang pembungkus ```markdown ... ``` dan kalimat pembuka sebelum judul pertama."""
    m = re.search(r"```(?:markdown|md)?\s*\n(#.*?)\n```\s*$", text, re.S)
    if m:
        return m.group(1).strip()
    i = text.find("\n# ")
    if text.lstrip().startswith("#"):
        return text.strip()
    return text[i + 1:].strip() if i != -1 else text.strip()


def do_stage_run(body):
    pid, num = body.get("project", ""), body.get("stage", "")
    p = find_project(pid)
    st = next((s for s in STAGES if s[0] == num), None)
    if not p or not st:
        raise ValueError("proyek/tahap tidak valid")
    if num == "01":
        raise ValueError("tahap 01 = intake Gate #0: dibuat lewat approve draft, bukan dijalankan ulang")
    status = {s["n"]: s for s in stage_status(pid)}
    if status["01"]["state"] != "done":
        raise ValueError("Gate #0 belum: approve draft intake dulu")
    prev = f"{int(num) - 1:02d}"
    if status.get(prev, {}).get("state") not in ("done",):
        extra = " (tahap eksekusi hanya membuat brief dari web; selesaikan di terminal dengan bukti)" if status.get(prev, {}).get("kind") == "exec" else ""
        raise ValueError(f"tahap {prev} belum selesai{extra}")
    _, name, prof, kind = st
    sdir = pdir(pid) / "stages"
    slug = slugify(name)
    if kind == "exec":
        # Tahap eksekusi butuh repo/test/scan nyata -> hanya brief serah-terima (tanpa LLM, tanpa klaim).
        brief = (f"# Brief serah-terima — tahap {num} {name}\n\nProyek: {p['name']}\nProfil: `{prof}`\n"
                 f"Repo: `{p.get('path') or '(belum ada repo — buat dulu)'}`\n\n"
                 "Tahap ini membutuhkan eksekusi nyata (kode/test/scan) dan BELUM dijalankan dari web.\n"
                 "Jalankan di terminal (satu tugas, dengan bukti output):\n\n"
                 f"```\n{prof} -z \"Baca ~/sdb-workspace/projects/{pid}/stages/*.md lalu kerjakan tahap {num} {name}; "
                 "lampirkan bukti test/scan nyata.\"\n```\n\nSelesai hanya jika ada bukti build/test/scan segar.\n")
        (sdir / f"{num}-{slug}.brief.md").write_text(brief)
        return None, {"brief": True}

    docs = prior_docs(pid, num)
    facts = project_context(pid if p["kind"] == "real" else "baru")
    prompt = (f"Kamu agen SDB profil {prof}. Tulis dokumen Markdown untuk tahap {num} {name} proyek '{p['name']}'.\n"
              f"Instruksi tahap: {STAGE_BRIEF.get(num, '')}\n"
              "Aturan: Bahasa Indonesia; hanya pakai fakta dari dokumen di bawah; bedakan FAKTA / ASUMSI / REKOMENDASI; "
              "jangan klaim sudah dibangun/diuji; tanpa kredensial.\n"
              "KELUARKAN HANYA isi dokumen Markdown itu sendiri: tanpa kalimat pembuka/penutup, tanpa code fence pembungkus, "
              "tanpa membahas tool/berkas (server yang menyimpan file).\n"
              f"{facts}\n\n=== DOKUMEN SEBELUMNYA ===\n{docs}")
    tools = "web" if num == "05" else "todo"

    def fn():
        text = clean_doc(run_llm(prof, prompt, toolsets=tools, timeout=420))
        head = f"<!-- tahap {num} {name} · profil {prof} · {now()} · draft LLM, butuh review Owner -->\n\n"
        with _lock:
            out = sdir / f"{num}-{slug}.md"
            if out.exists():  # jalankan ulang tidak boleh menghapus versi lama diam-diam
                out.replace(sdir / f"{num}-{slug}.md.prev")
            out.write_text(head + text)
        return {"file": f"{num}-{slug}.md", "chars": len(text)}

    return start_job("stage", prof, pid, fn), None


# ----------------------------------------------------------------- HTTP glue
def project_view(p):
    pid = p["id"]
    st = stage_status(pid)
    return {"id": pid, "name": p["name"], "kind": p["kind"], "path": p.get("path", ""),
            "type": p.get("type", ""), "facts": project_facts(p) if p.get("path") else {"exists": False},
            "stages": st, "done": sum(1 for s in st if s["state"] == "done")}


def handle(h, method, send):
    """h: BaseHTTPRequestHandler; send(code, obj). Return True jika path ditangani."""
    u = urlparse(h.path)
    path, q = u.path, parse_qs(u.query)
    if not path.startswith("/api/ws/"):
        return False
    route = path[len("/api/ws/"):].strip("/")
    host = (h.headers.get("Host") or "").strip().lower()
    host = host[1:host.find("]")] if host.startswith("[") else host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    # PIN hanya untuk klien loopback DAN Host loopback: DNS-rebinding (Host: evil.test
    # dari browser di PC ini) tidak boleh bisa membaca PIN.
    local = h.client_address[0] in ("127.0.0.1", "::1") and host in ("127.0.0.1", "localhost", "::1")
    token = get_token()

    if route == "whoami" and method == "GET":
        send(200, {"local": local, "token": token if local else None, "lan_hint": not local})
        return True
    given = h.headers.get("X-SDB-Token", "")
    # bytes: compare_digest(str) melempar TypeError untuk header non-ASCII.
    if not hmac.compare_digest(given.encode("utf-8", "replace"), token.encode("utf-8")):
        # Laju 401 per klien: menebak PIN 72-bit tetap mustahil, tetapi membatasi percobaan membuat
        # percobaan otomatis gagal cepat alih-alih membebani proses.
        client = h.client_address[0]
        now = time.monotonic()
        with rate_lock:
            hits = [t for t in rate_401.get(client, ()) if now - t < 60.0] + [now]
            rate_401[client] = hits[-40:]
            burst = len(hits)
        if burst > 30:
            send(429, {"error": "terlalu banyak kegagalan autentikasi; coba lagi sebentar"})
            return True
        send(401, {"error": "token salah/kosong — buka dari PC lokal untuk melihat PIN"})
        return True
    try:
        body = {}
        if method == "POST":
            n = int(h.headers.get("Content-Length") or 0)
            if n < 0 or n > MAX_BODY:
                send(413, {"error": "terlalu besar"})
                return True
            body = json.loads(h.rfile.read(n) or b"{}")
            if not isinstance(body, dict):  # array/teks JSON -> body.get() akan AttributeError (500)
                raise ValueError("body harus objek JSON")

        if route == "projects" and method == "GET":
            send(200, {"projects": [project_view(p) for p in registry()], "stages": [
                {"n": s[0], "name": s[1], "profile": s[2], "kind": s[3]} for s in STAGES]})
        elif route == "jobs" and method == "GET":
            send(200, {"jobs": [public_job(j) for j in sorted(JOBS.values(), key=lambda x: x["t0"])[-20:]]})
        elif route.startswith("job/") and method == "GET":
            j = JOBS.get(route.split("/", 1)[1])
            send(200 if j else 404, public_job(j) if j else {"error": "job tidak ada"})
        elif route == "chat" and method == "POST":
            job, cid = do_chat(body)
            send(202, {"job": job["id"], "cid": cid})
        elif route == "chat/history" and method == "GET":
            cid = (q.get("cid") or [""])[0]
            send(200, read_json(chat_file(cid), {"messages": [], "drafts": []}))
        elif route == "draft/approve" and method == "POST":
            send(200, do_approve(body))
        elif route == "stage/run" and method == "POST":
            job, extra = do_stage_run(body)
            send(202 if job else 200, {"job": job["id"]} if job else extra)
        elif route == "artifact" and method == "GET":
            pid, f = (q.get("project") or [""])[0], (q.get("file") or [""])[0]
            base = pdir(pid).resolve()
            # resolve() dulu: symlink di dalam stages/ tidak boleh membaca berkas di
            # luar direktori proyek (T11-3, CWE-59). Bukan pengganti pdir() (CWE-22).
            fp = (base / "stages" / Path(f).name).resolve()
            if not (fp.is_relative_to(base) and fp.is_file()):
                send(404, {"error": "tidak ada"})
            else:
                send(200, {"file": fp.name, "text": fp.read_text()[:60000]})
        else:
            send(404, {"error": "rute tidak dikenal"})
    except (ValueError, RuntimeError) as e:
        send(400, {"error": str(e)})
    except Exception as e:  # noqa: BLE001 — batas HTTP: galat apa pun harus jadi 500 + log, bukan mematikan server
        # Jangan kirim str(e) ke klien (bisa memuat path/isi internal); catat lengkap di stderr.
        import sys
        import traceback
        print(f"[ws_api] 500 {method} {route}: {type(e).__name__}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        send(500, {"error": f"kesalahan server ({type(e).__name__})"})
    return True
