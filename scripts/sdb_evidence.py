#!/usr/bin/env python3
"""Kontrak evidence verifikasi SDB — `sdb.verify.evidence/1`.

Modul ini **hanya memverifikasi**. Tidak ada fungsi menandatangani di sini, dan
itu disengaja: kode yang berjalan di host builder tidak boleh memegang kemampuan
membuat bukti. Penanda tangan hidup di host verifier terpisah (C2-B2).

Yang ditegakkan (semua fail-closed, kode spesifik):
  * versi skema & algoritma sidik eksplisit,
  * identitas job (`job_id`) terikat ke job yang meminta,
  * sidik isi workspace (`workspace_digest`) terikat ke kondisi saat ini,
  * `nonce` sekali pakai + masa berlaku (anti-replay / anti-reuse lintas job),
  * tanda tangan `ssh-keygen -Y verify` atas byte kanonik payload,
  * signer harus ada di `allowed_signers` yang dipin (`verifier.id`),
  * tiga tingkat bukti terpisah: EXECUTION_VERIFIED < ACCEPTANCE_VERIFIED
    < RELEASE_ELIGIBLE (yang terakhir tidak pernah diberikan modul ini).

Catatan kejujuran: verifikasi tanda tangan di sini **belum** menjadikan pipeline
aman. Selama builder berjalan sebagai user yang sama dengan pemilik kunci/DB,
bukti masih dapat dipalsukan di sisi penyimpanan. Itu domain C2-B2.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

SCHEMA = "sdb.verify.evidence/1"
REQUEST_SCHEMA = "sdb.verify.request/1"
DIGEST_ALG = "tree-sha256/1"
NAMESPACE = "sdb-verify-v1"
SIGNATURE_ALGS = ("ssh-ed25519",)
MODES = ("legacy", "strict")

LEVEL_EXECUTION = "EXECUTION_VERIFIED"
LEVEL_ACCEPTANCE = "ACCEPTANCE_VERIFIED"
# Tidak pernah diberikan oleh worker. Hanya catatan persetujuan Owner (C2-B2).
LEVEL_RELEASE = "RELEASE_ELIGIBLE"

CLOCK_SKEW = 300          # toleransi jam verifier vs worker (detik)
VERIFY_TTL_DEFAULT = 1800
VERIFY_TTL_MAX = 86_400   # batas atas masa berlaku permintaan/evidence (detik)
MAX_PAYLOAD_BYTES = 512 * 1024
MAX_SIGNATURE_BYTES = 8192
SIGN_TIMEOUT = 20

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT = re.compile(r"^sha256:[0-9a-f]{64}$")


# ---------- kanonikalisasi ----------
def canonical_bytes(obj: object) -> bytes:
    """Byte kanonik: kunci terurut, tanpa spasi, UTF-8, tanpa NaN.

    Tanda tangan dihitung atas byte ini, bukan atas teks asli kiriman. Dengan
    begitu urutan kunci dan spasi tidak bisa dipakai untuk menggeser isi.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def signable_bytes(evidence: dict) -> bytes:
    """Byte yang ditandatangani: payload tanpa field `signature`."""
    return canonical_bytes({k: v for k, v in evidence.items() if k != "signature"})


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------- pembantu tipe (bool bukan int di JSON) ----------
def as_int(v: object) -> int | None:
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v


def is_hex64(v: object) -> bool:
    return isinstance(v, str) and bool(_HEX64.match(v))


def evidence_mode(raw: str | None = None) -> str:
    """Mode penerimaan event `verify`.

    `legacy` = perilaku C2-A (event tanpa tanda tangan masih diterima). Itu
    bawaan hanya agar perilaku deploy tidak berubah; `strict` adalah syarat
    sebelum `SDB_DONE_POLICY=verified` dinyalakan. Nilai tak dikenal -> strict.
    """
    if raw is None:
        raw = os.environ.get("SDB_EVIDENCE_MODE")
    if raw is None:
        return "legacy"
    raw = raw.strip().lower()
    return raw if raw in MODES else "strict"


# ---------- signer store ----------
_SSH_KEYGEN_PATHS = ("/usr/bin/ssh-keygen", "/bin/ssh-keygen", "/usr/local/bin/ssh-keygen")


def _ssh_keygen() -> str | None:
    """Path absolut `ssh-keygen` milik root, bukan symlink, tidak bisa ditulis user.

    Tanpa ini, satu shim `ssh-keygen` di `~/.local/bin` (yang bisa ditulis proses
    build dan biasanya ada di PATH systemd user unit) membuat semua tanda tangan
    "sah" tanpa menyentuh DB, signer store, atau kode SDB.
    """
    for kandidat in _SSH_KEYGEN_PATHS:
        try:
            st = os.lstat(kandidat)
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            continue
        if st.st_uid != 0 or st.st_mode & 0o022:
            continue
        if not os.access(kandidat, os.X_OK):
            continue
        return kandidat
    return None


def _chain_error(path: Path) -> str:
    """Periksa path dan seluruh parent-nya ("" = layak).

    Menutup celah "hanya komponen terakhir diperiksa": parent symlink, parent
    world-writable (`/tmp/x/allowed_signers`), dan berkas group-writable.
    Pemilik wajib root atau euid sendiri. Parent group-writable masih diterima
    (dokumentasikan sebagai sisa risiko: satu grup = satu kepercayaan).
    """
    try:
        p = Path(path)
    except (TypeError, ValueError):
        return "EVIDENCE_SIGNER_STORE"
    if not p.is_absolute():
        return "EVIDENCE_SIGNER_STORE"
    euid = os.geteuid()
    for komponen in (p, *p.parents):
        try:
            st = komponen.lstat()
        except OSError:
            return "EVIDENCE_SIGNER_STORE"
        if stat.S_ISLNK(st.st_mode):
            return "EVIDENCE_SIGNER_STORE"
        if st.st_uid not in (0, euid):
            return "EVIDENCE_SIGNER_STORE"
        if st.st_mode & 0o002:          # world-writable: siapa pun bisa menambah kunci
            return "EVIDENCE_SIGNER_STORE"
    return ""


def _store_error(path: Path) -> str:
    """Alasan `allowed_signers` tidak layak dipakai ("" = layak)."""
    kode = _chain_error(path)
    if kode:
        return kode
    try:
        st = Path(path).lstat()
    except OSError:
        return "EVIDENCE_SIGNER_STORE"
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return "EVIDENCE_SIGNER_STORE"
    if st.st_mode & 0o022:              # group/world-writable
        return "EVIDENCE_SIGNER_STORE"
    if st.st_size <= 0 or st.st_size > 1024 * 1024:
        return "EVIDENCE_SIGNER_STORE"
    return ""


def read_store(path: Path) -> tuple[bytes | None, str]:
    """Baca isi signer store secara aman, sekali, lalu kembalikan byte-nya.

    Byte yang sudah terbaca inilah yang nanti dipakai verifikasi (disalin ke
    berkas sementara 0600). Dengan begitu berkas asli tidak dibuka ulang oleh
    `ssh-keygen`, sehingga penukaran berkas di antara pemeriksaan dan pemakaian
    (TOCTOU) tidak berpengaruh.
    """
    kode = _store_error(path)
    if kode:
        return None, kode
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError:
        return None, "EVIDENCE_SIGNER_STORE"
    try:
        dst = os.fstat(fd)
        if not stat.S_ISREG(dst.st_mode) or dst.st_mode & 0o022 or dst.st_size > 1024 * 1024:
            return None, "EVIDENCE_SIGNER_STORE"
        with os.fdopen(fd, "rb") as fh:
            fd = -1
            data = fh.read(1024 * 1024 + 1)
    except OSError:
        return None, "EVIDENCE_SIGNER_STORE"
    finally:
        if fd >= 0:
            os.close(fd)
    if not data or len(data) > 1024 * 1024:
        return None, "EVIDENCE_SIGNER_STORE"
    return data, ""


def parse_allowed_signers(text: str) -> tuple[set[str], list[str]]:
    """(principal yang diizinkan, baris kunci). Baris rusak dilewati."""
    principals: set[str] = set()
    keys: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        bagian = line.split()
        if len(bagian) < 3:
            continue
        kandidat = [p.strip() for p in bagian[0].split(",") if p.strip()]
        if not kandidat or any(p in ("cert-authority", "namespaces") for p in kandidat):
            continue
        principals.update(kandidat)
        keys.append(" ".join(bagian[1:3]))
    return principals, keys


def load_allowed_signers(path: Path | None) -> tuple[bool, str, set[str]]:
    if path is None:
        return False, "EVIDENCE_SIGNER_STORE", set()
    data, kode = read_store(Path(path))
    if data is None:
        return False, kode, set()
    principals, _keys = parse_allowed_signers(data.decode("utf-8", errors="replace"))
    if not principals:
        return False, "EVIDENCE_SIGNER_STORE", set()
    return True, "", principals


def verify_signature(payload: bytes, signature: object, signers: Path,
                     identity: str, *, namespace: str = NAMESPACE,
                     timeout: int = SIGN_TIMEOUT) -> tuple[bool, str]:
    """Verifikasi tanda tangan OpenSSH atas `payload` untuk `identity`.

    Tanpa ssh-keygen atau tanpa berkas signer -> **gagal** (fail-closed), bukan
    dilewati. Isi signer store dibaca sekali lalu disalin ke direktori 0700;
    `ssh-keygen` dijalankan dari path absolut milik root dengan environment
    minimal, sehingga tidak bisa dibelokkan lewat PATH/cwd.
    """
    if not isinstance(signature, str) or "BEGIN SSH SIGNATURE" not in signature:
        return False, "EVIDENCE_NO_SIGNATURE"
    if len(signature) > MAX_SIGNATURE_BYTES:
        return False, "EVIDENCE_NO_SIGNATURE"
    if len(payload) > MAX_PAYLOAD_BYTES:
        return False, "EVIDENCE_INVALID"
    if not identity or not isinstance(identity, str):
        return False, "EVIDENCE_UNKNOWN_VERIFIER"
    exe = _ssh_keygen()
    if not exe:
        return False, "EVIDENCE_VERIFIER_UNAVAILABLE"
    store, kode = read_store(Path(signers))
    if store is None:
        return False, kode
    tmp = tempfile.mkdtemp(prefix="sdb-ev-")
    try:
        os.chmod(tmp, 0o700)
        sig_path = Path(tmp) / "payload.sig"
        sig_path.write_text(signature + ("\n" if not signature.endswith("\n") else ""),
                            encoding="utf-8")
        os.chmod(sig_path, 0o600)
        store_path = Path(tmp) / "allowed_signers"
        store_path.write_bytes(store)     # byte yang sudah diperiksa, bukan berkas asli
        os.chmod(store_path, 0o600)
        cmd = [exe, "-Y", "verify", "-f", str(store_path), "-I", identity,
               "-n", namespace, "-s", str(sig_path)]
        env = {"PATH": "/usr/bin:/bin", "HOME": tmp, "TMPDIR": tmp, "LC_ALL": "C"}
        try:
            proc = subprocess.run(cmd, input=payload, capture_output=True,
                                  timeout=timeout, check=False, cwd=tmp, env=env)
        except (OSError, subprocess.SubprocessError):
            return False, "EVIDENCE_VERIFIER_UNAVAILABLE"
        if proc.returncode == 0:
            return True, ""
        return False, "EVIDENCE_UNTRUSTED_SIGNER"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- kriteria penerimaan ----------
def acceptance_ok(evidence: dict, pinned_criteria_digest: str | None) -> tuple[bool, str]:
    """`exit 0` bukan penerimaan. Semua syarat di bawah wajib benar.

    Syarat: eksekusi tidak timeout, exit 0, ada tes yang benar-benar terkumpul,
    nol gagal/error, tidak ada tes yang dibuang tanpa alasan tercatat, dan
    `criteria_digest` cocok dengan yang dipin lokal.
    """
    masalah: list[str] = []
    eksekusi = evidence.get("execution")
    if not isinstance(eksekusi, dict):
        eksekusi = {}
    tes = eksekusi.get("tests")
    if not isinstance(tes, dict):
        tes = {}
    if eksekusi.get("timed_out") is not False:
        masalah.append("TIMEOUT")
    if as_int(eksekusi.get("exit_code")) != 0:
        masalah.append("EXIT_CODE")
    if (as_int(tes.get("collected")) or 0) <= 0:
        masalah.append("NO_TESTS")
    if (as_int(tes.get("failed")) or 0) > 0 or (as_int(tes.get("errors")) or 0) > 0:
        masalah.append("TESTS_FAILED")
    if (as_int(tes.get("deselected")) or 0) > 0 and not evidence.get("deselect_reasons"):
        masalah.append("SILENT_DESELECT")
    kriteria = evidence.get("acceptance_criteria")
    if not isinstance(kriteria, dict):
        kriteria = {}
    if not kriteria.get("id"):
        masalah.append("CRITERIA_ID")
    if not pinned_criteria_digest:
        masalah.append("CRITERIA_UNPINNED")
    elif str(kriteria.get("criteria_digest") or "") != pinned_criteria_digest:
        masalah.append("CRITERIA_MISMATCH")
    return (not masalah), ",".join(masalah)


# ---------- validasi kontrak ----------
def _gagal(kode: str, alasan: str, level: str = "legacy") -> dict:
    return {"ok": False, "code": kode, "reason": alasan,
            "level": "", "acceptance": False, "evidence_level": level,
            "release_eligible": False}


def validate(evidence: object, *, job_id: int, workspace_digest: str,
             digest_complete: bool, now: int, nonce_issued: "dict[str, int] | set[str]",
             nonce_used: set[str], allowed_signers: Path | None,
             verifier_ids: set[str],
             pinned_criteria_digest: str | None = None) -> dict:
    """Validasi penuh evidence `sdb.verify.evidence/1`. Tidak ada jalur "lewati"."""
    if not isinstance(evidence, dict):
        return _gagal("EVIDENCE_SCHEMA", "payload bukan objek JSON")
    if evidence.get("schema") != SCHEMA:
        return _gagal("EVIDENCE_SCHEMA", f"schema bukan {SCHEMA}")
    if evidence.get("digest_alg") != DIGEST_ALG:
        return _gagal("EVIDENCE_SCHEMA", f"digest_alg bukan {DIGEST_ALG}")
    if as_int(evidence.get("job_id")) != int(job_id):
        return _gagal("EVIDENCE_JOB_MISMATCH", "job_id tidak cocok")
    if not isinstance(evidence.get("project_id"), str) or not evidence["project_id"].strip():
        return _gagal("EVIDENCE_SCHEMA", "project_id kosong")
    # Bentuk salah harus jadi kode penolakan, bukan AttributeError di tengah jalan.
    for bagian in ("timestamps", "snapshot", "verifier", "verdict",
                   "acceptance_criteria", "execution"):
        if not isinstance(evidence.get(bagian), dict):
            return _gagal("EVIDENCE_SCHEMA", f"{bagian} bukan objek")
    if not isinstance(evidence["execution"].get("tests"), dict):
        return _gagal("EVIDENCE_SCHEMA", "execution.tests bukan objek")

    nonce = evidence.get("request_nonce")
    if not is_hex64(nonce):
        return _gagal("EVIDENCE_NO_NONCE", "nonce tidak ada/tidak sah")
    if nonce in nonce_used:
        return _gagal("EVIDENCE_REPLAY", "nonce sudah dipakai")
    jendela: int | None = None
    if isinstance(nonce_issued, dict):
        jendela = as_int(nonce_issued.get(nonce))
        if jendela is None:
            return _gagal("EVIDENCE_NONCE_UNKNOWN", "nonce bukan milik job ini")
    elif nonce not in nonce_issued:
        return _gagal("EVIDENCE_NONCE_UNKNOWN", "nonce bukan milik job ini")

    waktu = evidence["timestamps"]
    if not isinstance(waktu, dict):
        return _gagal("EVIDENCE_SCHEMA", "timestamps bukan objek")
    issued, finished = as_int(waktu.get("issued_at")), as_int(waktu.get("finished_at"))
    expires = as_int(waktu.get("expires_at"))
    if issued is None or finished is None or expires is None:
        return _gagal("EVIDENCE_SCHEMA", "timestamps tidak lengkap")
    if finished < issued:
        return _gagal("EVIDENCE_SCHEMA", "finished_at sebelum issued_at")
    if issued > now + CLOCK_SKEW:
        return _gagal("EVIDENCE_CLOCK", "issued_at di masa depan")
    if jendela is not None and now > jendela:
        return _gagal("EVIDENCE_REQUEST_EXPIRED", "permintaan verifikasi sudah kedaluwarsa")
    if expires <= now:
        return _gagal("EVIDENCE_EXPIRED", "evidence kedaluwarsa")
    if expires <= issued:
        return _gagal("EVIDENCE_EXPIRED", "expires_at tidak masuk akal")
    if expires - issued > VERIFY_TTL_MAX:
        return _gagal("EVIDENCE_EXPIRED", "masa berlaku evidence melampaui batas")
    if jendela is not None and expires > jendela:
        return _gagal("EVIDENCE_EXPIRED", "evidence melebihi masa berlaku permintaan")

    snapshot = evidence.get("snapshot") or {}
    if snapshot.get("complete") is not True:
        return _gagal("EVIDENCE_SNAPSHOT_INCOMPLETE", "snapshot tidak lengkap")
    if not isinstance(snapshot.get("snapshot_id"), str) or not _SNAPSHOT.match(snapshot["snapshot_id"]):
        return _gagal("EVIDENCE_SCHEMA", "snapshot_id tidak sah")

    if not digest_complete:
        return _gagal("EVIDENCE_DIGEST_INCOMPLETE", "sidik workspace tidak lengkap")
    if evidence.get("workspace_digest") != workspace_digest:
        return _gagal("EVIDENCE_DIGEST_MISMATCH", "workspace berubah sejak verifikasi")

    verifier = evidence.get("verifier") or {}
    vid = verifier.get("id")
    if not isinstance(vid, str) or not vid.strip():
        return _gagal("EVIDENCE_UNKNOWN_VERIFIER", "verifier.id kosong")
    if verifier_ids and vid not in verifier_ids:
        return _gagal("EVIDENCE_UNKNOWN_VERIFIER", "verifier tidak diizinkan")

    sig = evidence.get("signature") or {}
    if not isinstance(sig, dict):
        return _gagal("EVIDENCE_NO_SIGNATURE", "signature bukan objek")
    if not sig.get("sig"):
        return _gagal("EVIDENCE_NO_SIGNATURE", "tidak ada tanda tangan")
    if sig.get("alg") not in SIGNATURE_ALGS:
        return _gagal("EVIDENCE_SIGNATURE_ALG", "algoritma tanda tangan tidak didukung")
    if sig.get("namespace") != NAMESPACE:
        return _gagal("EVIDENCE_SIGNATURE_ALG", "namespace tanda tangan salah")
    # N3: `json.loads` menerima literal NaN/Infinity, sedangkan `json.dumps`
    # (dengan allow_nan=False) tidak. Tanpa penangkap ini, payload berisi angka
    # tak berhingga meledak sebagai pengecualian tak tertangkap dan berujung
    # `COMPLETION_ERROR` — kode yang salah untuk masalah bentuk payload.
    try:
        payload = signable_bytes(evidence)
    except (ValueError, TypeError):
        return _gagal("EVIDENCE_SCHEMA", "payload berisi angka tidak berhingga (NaN/Infinity)")
    sah, kode = verify_signature(payload, sig.get("sig"),
                                 Path(allowed_signers) if allowed_signers else Path("/nonexistent"),
                                 vid)
    if not sah:
        return _gagal(kode, "tanda tangan tidak sah")
    if sig.get("signer") and sig["signer"] != vid:
        return _gagal("EVIDENCE_UNTRUSTED_SIGNER", "signer != verifier.id")

    verdict = evidence.get("verdict") or {}
    eksekusi = verdict.get("execution")
    if eksekusi == "FAIL":
        return _gagal("VERIFY_FAIL", "eksekusi gagal")
    if eksekusi == "TIMEOUT":
        return _gagal("VERIFY_TIMEOUT", "eksekusi timeout")
    if eksekusi != "PASS":
        return _gagal("EVIDENCE_SCHEMA", "verdict.execution tidak dikenal")

    terima, alasan = acceptance_ok(evidence, pinned_criteria_digest)
    level = LEVEL_ACCEPTANCE if terima else LEVEL_EXECUTION
    if verdict.get("acceptance") == "FAIL":
        terima, level, alasan = False, LEVEL_EXECUTION, alasan or "verdict.acceptance FAIL"
    return {"ok": True, "code": "", "reason": alasan if not terima else "",
            "level": level, "acceptance": terima, "evidence_level": level,
            # Worker tidak pernah menaikkan ke RELEASE_ELIGIBLE; klaim dari payload
            # diabaikan, bukan dipercaya.
            "release_eligible": False}
