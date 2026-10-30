"""G1 — pemindai firewall spesifikasi (fail-closed).

Spesifikasi clean-room (`reconstruction/<target>/SPEC.md`) hanya boleh berisi
teks perilaku + Evidence ID + label. Skrip ini menolak:
  - blok kode berpagar (pseudocode / kode hasil dekompilasi)
  - baris mirip kode (def, class, function, import, const, let, var, #include)
  - literal string panjang (>= 40 karakter dalam tanda kutip)
  - rahasia/credential berpola (API key, private key, token=, password=)
  - email/PII
  - klaim tanpa Evidence ID dan tanpa label observasi/inferensi/tidak-diketahui

Kode keluar: 0 = PASS, 1 = GAGAL (ada pelanggaran), 2 = alat/berkas bermasalah.
Alat rusak TIDAK boleh menghasilkan PASS (aturan 7 riset-penelitian).

Pemakaian:
  python3 tools/gerbang-spec.py reconstruction/e1-app/SPEC.md
  python3 tools/gerbang-spec.py <spec> --verdict reports/e1-app/g1.json
"""

import argparse
import hashlib
import json
import pathlib
import re
import sys

CODE_FENCE = re.compile(r"^\s*```\s*([A-Za-z0-9_+-]*)")
CODE_LINE = re.compile(
    r"^\s*(def |class |function |import |from \w+ import |const |let |var |#include|public class|async function)"
)
LONG_LITERAL = re.compile(r"[\"'`]([^\"'`\n]{40,})[\"'`]")
SECRET_PATTERNS = [
    ("private-key", re.compile(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("assignment", re.compile(r"\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S+", re.I)),
]
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
LABEL = re.compile(r"(observasi|inferensi|tidak-diketahui)", re.I)
EVIDENCE = re.compile(r"\[E\d+")
EXEMPT = re.compile(r"(dilarang|tidak boleh|tidak dipakai|tidak ada|batas|catatan|out of scope|non-goal)", re.I)


def _blocks(text: str):
    """Kelompokkan baris menjadi blok (dipisah baris kosong / judul)."""
    block, start = [], 0
    for no, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            if block:
                yield start, block
                block = []
            continue
        if not block:
            start = no
        block.append((no, line))
    if block:
        yield start, block


def _is_table_header(block) -> bool:
    row = block[0][1].strip()
    if not row.startswith("|"):
        return False
    cells = [c.strip().lower() for c in row.strip("|").split("|")]
    return bool(cells) and cells[0] in ("id", "no", "fitur", "field", "item")


def is_claim_block(block) -> bool:
    head = block[0][1].strip()
    if EXEMPT.search(head):
        return False
    return head.startswith(("- ", "* ")) or head.startswith("|")


def scan(text: str):
    problems = []
    claims = 0
    in_fence = False
    fence_lang = ""
    for no, line in enumerate(text.splitlines(), 1):
        m = CODE_FENCE.match(line)
        if m:
            if not in_fence:
                in_fence = True
                fence_lang = m.group(1).strip()
                if fence_lang:
                    problems.append({
                        "baris": no, "jenis": "blok-kode-berpagar",
                        "detail": f"pagar dengan bahasa '{fence_lang}' — spesifikasi wajib teks, bukan kode",
                    })
            else:
                in_fence = False
                fence_lang = ""
            continue
        if in_fence:
            if CODE_LINE.match(line):
                problems.append({"baris": no, "jenis": "kode-dalam-pagar",
                                 "detail": line.strip()[:80]})
            continue
        if CODE_LINE.match(line):
            problems.append({"baris": no, "jenis": "baris-mirip-kode", "detail": line.strip()[:80]})
        for lit in LONG_LITERAL.finditer(line):
            if EVIDENCE.search(line) and len(lit.group(1).split()) <= 3:
                continue  # entri bukti pendek, bukan salinan teks target
            problems.append({"baris": no, "jenis": "literal-panjang",
                             "detail": f"{len(lit.group(1))} karakter"})
        for name, pat in SECRET_PATTERNS:
            if pat.search(line):
                problems.append({"baris": no, "jenis": f"rahasia:{name}",
                                 "detail": "pola kredensial terdeteksi"})
        if EMAIL.search(line):
            problems.append({"baris": no, "jenis": "pii:email", "detail": "alamat email"})

    for start, block in _blocks(text):
        if not is_claim_block(block):
            continue
        header = _is_table_header(block)
        joined = " ".join(teks for _, teks in block)
        has_ev = bool(EVIDENCE.search(joined) or LABEL.search(joined))
        for idx, (_no, line) in enumerate(block):
            s = line.strip()
            if header and idx == 0:
                continue
            if s.startswith("|---") or s.startswith("|--"):
                continue
            if not s.startswith(("- ", "* ", "|")):
                continue
            claims += 1
        if not has_ev:
            problems.append({"baris": start, "jenis": "klaim-tanpa-bukti",
                             "detail": block[0][1].strip()[:90]})
    if claims == 0:
        problems.append({"baris": 0, "jenis": "tanpa-klaim",
                         "detail": "tidak ada baris klaim terdeteksi — berkas mencurigakan"})
    return problems, claims


def main() -> int:
    ap = argparse.ArgumentParser(description="G1: firewall spesifikasi clean-room")
    ap.add_argument("spec")
    ap.add_argument("--verdict", default=None, help="tulis verdict JSON ke path ini")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    p = pathlib.Path(a.spec)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"G1 TIDAK DIVERIFIKASI: {exc}", file=sys.stderr)
        return 2

    problems, claims = scan(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    verdict = "PASS" if not problems else "FAIL"

    out = {"spec": str(p), "sha256": digest, "claims": claims,
           "verdict": verdict, "violations": problems}
    if a.verdict:
        vp = pathlib.Path(a.verdict)
        vp.parent.mkdir(parents=True, exist_ok=True)
        vp.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    if not a.quiet:
        print(f"G1 {verdict}: {p} (klaim={claims}, pelanggaran={len(problems)}, sha256={digest[:16]})")
        for v in problems[:20]:
            print(f"  baris {v['baris']}: {v['jenis']} — {v['detail']}")
        if len(problems) > 20:
            print(f"  ... {len(problems) - 20} pelanggaran lain")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
