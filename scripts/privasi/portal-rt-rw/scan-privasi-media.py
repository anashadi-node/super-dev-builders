#!/usr/bin/env python3
"""Gerbang privasi MEDIA untuk Super Dev Builders — kanal OCR atas berkas TERLACAK.

MENGAPA ADA
-----------
Sapuan privasi milik produk (`real_system/privacy_scan.py`) memindai berkas yang
**ikut dikirim ke pembeli** (cakupan kemasan: `deploy/kemasan-abaikan.txt`). Berkas
yang ada di repo tetapi TIDAK ikut kemasan — tangkapan layar `reports/`,
`verification/`, dan video demo — berada di luar cakupan itu. Pada saat yang sama
kanal teks tidak bisa membaca PNG/MP4 (byte-nya biner), jadi berkas tersebut tidak
diperiksa kanal mana pun, padahal ia terlacak git dan sudah ter-push.

Akibatnya pernah terjadi "bersih palsu": 40 gambar terlacak + 1 video demo terlacak
memuat identitas pelanggan pilot, sementara setiap gerbang melaporkan 0 temuan.

Kanal ini menutup celah itu: cakupannya = **berkas media yang TERLACAK git**, bukan
cakupan kemasan. Bukan pengganti sapuan produk — pelengkap, sudut pandang berbeda.

PRINSIP
-------
* Fail-closed: alat OCR tidak ada -> keluar 2, bukan "bersih".
* Temuan LAMA yang berstatus TERBUKA tetap MEMBLOKIR rilis (keluar 3).
  Baseline memisahkan LAMA/BARU; baseline BUKAN izin keamanan.
* Pola identitas DITURUNKAN dari daftar larangan produk saat berjalan — skrip ini
  tidak pernah memuat nilai identitas dalam bentuk teks.
* Video disampel deterministik (1 frame/detik) supaya hasilnya dapat diulang.

Pakai:  python3 scan-privasi-media.py [direktori-proyek] [--tulis-json]
Keluar: 0 = BERSYARAT/BERSIH; 1 = temuan BARU; 2 = tidak dapat diverifikasi;
        3 = temuan DIKETAHUI tetapi BELUM DITUTUP (memblokir rilis)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

SUFFIX_GAMBAR = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
SUFFIX_VIDEO = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
OCR_BAHASA = os.environ.get("OCR_BAHASA", "ind+eng")
# Mode OCR digabung (union), BUKAN "mode pertama yang menghasilkan teks".
# Bukti 11 Okt 2026: pada 3 berkas terlacak, `--psm 6` membaca 0 token larangan
# sementara `--psm 11` membacanya. Deteksi yang bergantung mode = false-negative
# senyap. Biaya penggabungan = waktu OCR berlipat; itu harga yang benar.
OCR_PSM = tuple(os.environ.get("OCR_PSM", "6,11").split(","))


def alat(nama: str) -> str | None:
    return shutil.which(nama)


def alat_kurang(butuh_video: bool) -> list[str]:
    perlu = ["tesseract"]
    if butuh_video:
        perlu += ["ffmpeg", "ffprobe"]
    return [n for n in perlu if not alat(n)]


def _jalankan(cmd: list[str], batas: int = 240) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=batas)
    except (OSError, subprocess.SubprocessError):
        return 125, ""
    return p.returncode, (p.stdout or b"").decode("utf-8", "ignore")


def _norm(teks: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", teks).casefold())


def pola_identitas(akar: Path) -> tuple[list[str], list[re.Pattern[str]]]:
    """Ambil daftar larangan dari PRODUK, lalu bentuk pola varian.

    Yang ditambahkan di sini adalah bentuk yang TIDAK tertangkap pencocokan
    substring polos: kata merek berdiri sendiri, dan nomor RW dengan/tanpa
    pemisah (mis. `rwNN`, `RW NN`, `rw-N` — N = digit nomor) yang pada OCR
    sering terpisah spasi. Contoh di sini sengaja generik: alat TIDAK boleh
    memuat nilai identitas, ia hanya membacanya dari daftar larangan produk.
    """
    sys.path.insert(0, str(akar))
    from real_system.privacy_scan import TERLARANG  # type: ignore

    toks = [t for t in TERLARANG if t and len(t) >= 3]
    pola: list[re.Pattern[str]] = []
    for t in toks:
        if t.isdigit():
            continue
        pola.append(re.compile(r"(?<![0-9a-z])" + re.escape(_norm(t)) + r"(?![0-9a-z])"))
    # varian RW: nomor larangan <=3 digit yang muncul berdampingan dengan "rw"
    kecil = sorted({t for t in toks if t.isdigit() and len(t) <= 3}, key=len, reverse=True)
    for d in kecil:
        pola.append(re.compile(r"\brw[\s._-]{0,2}0*" + re.escape(d.lstrip("0") or d) + r"\b"))
    return toks, pola


def ocr_gambar(berkas: Path) -> str:
    """Gabungan OCR beberapa mode. Mengembalikan seluruh teks yang terbaca.

    Sengaja TIDAK memilih mode "terbaik": mode yang berbeda gagal membaca bagian
    yang berbeda pada berkas yang sama. Yang dibuang justru informasi.
    """
    kepingan = []
    for psm in OCR_PSM:
        kode, keluar = _jalankan([alat("tesseract") or "tesseract", str(berkas), "stdout",
                                  "--psm", psm.strip(), "-l", OCR_BAHASA])
        if kode == 0 and keluar.strip():
            kepingan.append(keluar)
    return "\n".join(kepingan)


def ocr_video(berkas: Path, tmp: Path, fps: int = 1) -> tuple[str, int]:
    """OCR sampel frame (deterministik). Kembalikan (teks, jumlah frame ter-OCR)."""
    if alat("ffmpeg") is None:
        return "", 0
    pola = str(tmp / "f_%05d.png")
    kode, _ = _jalankan([alat("ffmpeg") or "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                         "-i", str(berkas), "-vf", f"fps={fps}", pola])
    if kode != 0:
        return "", 0
    teks, n = [], 0
    for f in sorted(tmp.glob("f_*.png")):
        t = ocr_gambar(f)
        f.unlink(missing_ok=True)
        if t.strip():
            n += 1
            teks.append(t)
    return "\n".join(teks), n


def main(argv: list[str]) -> int:
    akar = Path(argv[1] if len(argv) > 1 and not argv[1].startswith("-") else ".").resolve()
    tulis = "--tulis-json" in argv
    sys.path.insert(0, str(akar))
    hasil_dir = Path(__file__).resolve().parent
    dasar_json = hasil_dir / "media-diketahui.json"
    rahasia_json = hasil_dir.parent / "reports/raw/privasi-media.json"

    # `git` wajib: cakupan gerbang ini = berkas TERLACAK. Tanpa git, cakupannya tidak
    # diketahui — dan "0 temuan" dari cakupan tak diketahui bukan bukti apa pun. Tanpa
    # penjaga ini, alat CRASH (exit 1 = "ada temuan BARU") ketika git tak ada di PATH:
    # sinyal yang menyesatkan, terbukti pada skenario (d) 11 Okt 2026.
    if shutil.which("git") is None:
        print("TAK DIVERIFIKASI: `git` tidak ada di PATH — cakupan berkas terlacak tidak "
              "dapat ditentukan (fail-closed)")
        return 2
    tercatat = subprocess.run(["git", "-C", str(akar), "ls-files"],
                              capture_output=True, text=True).stdout.split()
    media = [akar / f for f in tercatat
             if Path(f).suffix.lower() in (SUFFIX_GAMBAR | SUFFIX_VIDEO) and (akar / f).is_file()]
    ada_video = any(p.suffix.lower() in SUFFIX_VIDEO for p in media)
    kurang = alat_kurang(ada_video)
    if kurang:
        print(f"TAK DIVERIFIKASI: alat kurang {kurang} — kanal media GAGAL (fail-closed)")
        return 2

    toks, pola = pola_identitas(akar)
    diketahui = json.loads(dasar_json.read_text(encoding="utf-8")) if dasar_json.exists() else {}
    kenal = {k: v for k, v in diketahui.items() if k != "_catatan"}

    baru, lama, tanpa_teks = [], [], []
    sha_berkas = {}
    for p in sorted(media):
        rel = p.relative_to(akar).as_posix()
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        sha_berkas[rel] = sha
        if p.suffix.lower() in SUFFIX_GAMBAR:
            teks, frame = ocr_gambar(p), 1
        else:
            with tempfile.TemporaryDirectory(prefix="privmedia-") as t:
                teks, frame = ocr_video(p, Path(t))
        n = _norm(teks)
        kategori = []
        for t in toks:
            if t.isdigit():
                continue
            if _norm(t) in n:
                kategori.append("nama-merek")
        for rx in pola:
            if rx.search(n):
                kategori.append("varian-nomor-rw")
        kategori = sorted(set(kategori))
        if not teks.strip():
            tanpa_teks.append(rel)
            continue
        if kategori:
            entri = {"berkas": rel, "kategori": kategori, "sha256": sha, "frame_ocr": frame}
            (lama if sha in kenal else baru).append(entri)

    # ---- Penjaga rekam-panggil (mengapa ada): "0 temuan" bisa berarti dua hal yang
    # sangat berbeda — berkas memang bersih, atau mata alatnya buta. Negatif-kontrol
    # 11 Okt 2026 membuktikannya: tesseract diganti program yang selalu gagal, dan
    # gerbang ini MENCETAK "BERSIH". Karena itu, berkas yang isinya TIDAK BERUBAH
    # (sha256 sama dengan baseline) WAJIB tetap terdeteksi. Bila tidak => OCR merosot,
    # dan satu-satunya jawaban jujur adalah TAK DIVERIFIKASI, bukan BERSIH.
    terdeteksi = {e["sha256"] for e in lama} | {e["sha256"] for e in baru}
    regresi = [rel for rel, sha in sha_berkas.items() if sha in kenal and sha not in terdeteksi]
    semua_buta = bool(media) and len(tanpa_teks) == len(media)

    print(f"berkas media TERLACAK diperiksa : {len(media)}")
    print(f"  mode OCR digabung             : {'+'.join(OCR_PSM)} (bahasa {OCR_BAHASA})")
    print(f"  gambar                        : {sum(1 for p in media if p.suffix.lower() in SUFFIX_GAMBAR)}")
    print(f"  video                         : {sum(1 for p in media if p.suffix.lower() in SUFFIX_VIDEO)}")
    print(f"  gagal diverifikasi (tanpa teks): {len(tanpa_teks)}")
    print(f"  beridentitas — DIKETAHUI       : {len(lama)}")
    print(f"  beridentitas — BARU            : {len(baru)}")
    for e in baru:
        print(f"    [BARU] {e['berkas']} kategori={e['kategori']} frame={e['frame_ocr']}")
    for e in lama[:5]:
        print(f"    [diketahui] {e['berkas']} kategori={e['kategori']}")
    if len(lama) > 5:
        print(f"    … {len(lama) - 5} berkas diketahui lainnya")
    if tulis:
        rahasia_json.parent.mkdir(parents=True, exist_ok=True)
        rahasia_json.write_text(json.dumps(
            {"repo": akar.name, "baru": baru, "diketahui": lama, "tanpa_teks": tanpa_teks},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"bukti mentah: {rahasia_json}")
    # Urutan keputusan penting: TAK DIVERIFIKASI mendahului BERSIH/BERSYARAT.
    if not media:
        print("TAK DIVERIFIKASI: 0 berkas media terlacak — tidak ada yang diperiksa "
              "(0 berkas dipindai bukan bukti bersih, itu bukti kosong)")
        return 2
    if semua_buta:
        print(f"TAK DIVERIFIKASI: OCR tidak membaca teks apa pun dari {len(media)} berkas — "
              "alat/OCR merosot (fail-closed), bukan 'bersih'")
        return 2
    if regresi:
        print(f"TAK DIVERIFIKASI: {len(regresi)} berkas baseline berubah-tidak, tetapi TIDAK "
              "terdeteksi lagi — OCR merosot (contoh: " + ", ".join(regresi[:3]) + ")")
        return 2
    if baru:
        print("GAGAL: ada media beridentitas yang BELUM diketahui (perlu tindakan)")
        return 1
    # Temuan yang diketahui TIDAK otomatis aman. Baseline berkunci sha256, jadi berkas yang
    # sudah diredaksi otomatis gugur dari daftar ini. Selama masih ada temuan berstatus
    # TERBUKA, rilis harus TERBLOKIR — kalau tidak, "sudah diketahui" berubah artinya jadi
    # "diizinkan", dan itulah cara 41 berkas beridentitas lolos selama ini.
    terbuka = [e for e in lama if "TERBUKA" in str(kenal.get(e["sha256"], {}).get("status", "")).upper()]
    if terbuka:
        print(f"MEMBLOKIR RILIS: {len(terbuka)} temuan diketahui & BELUM DITUTUP (OQ-7) — "
              "selesaikan (redaksi/rekam ulang) atau tanda-tangani 'DITERIMA' di baseline")
        for e in terbuka[:5]:
            print(f"    [terbuka] {e['berkas']} kategori={e['kategori']}")
        if len(terbuka) > 5:
            print(f"    … {len(terbuka) - 5} berkas terbuka lainnya")
        return 3
    if lama:
        print("BERSYARAT: seluruh temuan sudah ditutup/diterima — BUKAN pernyataan bersih")
        return 0
    print("BERSIH: tidak ada identitas terdeteksi pada media terlacak")
    return 0


if __name__ == "__main__":
    # Galat tak terduga TIDAK BOLEH keluar sebagai kode 1: kode 1 berarti "ada temuan
    # BARU", sedangkan kode 2 berarti "tidak terverifikasi". Crash = tidak terverifikasi.
    # (Terbukti 11 Okt 2026: PATH tanpa `git` membuat alat keluar 1 — sinyal menyesatkan.)
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as e:
        print(f"TAK DIVERIFIKASI: galat tak terduga ({type(e).__name__}: {e}) — fail-closed")
        sys.exit(2)
