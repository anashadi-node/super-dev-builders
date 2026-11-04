"""Uji gerbang dokumen (`scripts/docs_lint.py`) — tiap aturan harus benar-benar MENOLAK.

Konteks: audit 2026-11-04 menemukan 10 dokumen tanpa entri indeks, 3 PDF hasil generate
masih terlacak, dan README mengklaim 39 skill padahal registry berisi 40. Tanpa uji negatif,
gerbang seperti ini perlahan berubah jadi prosa lagi.
"""
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "docs_lint.py")

README_BERSIH = """# Repo Uji
Repo resmi: <https://github.com/anashadi-node/super-dev-builders>

skills/ isi custom skill (jumlah = registry/skills.yaml, kini 2; cek `make drift`)
"""
INDEX_BERSIH = """# Indeks

| Berkas | Isi |
|---|---|
| `KEBIJAKAN.md` | kebijakan |
| `adr/0001-model.md` | keputusan pertama |
"""
REGISTRY_BERSIH = """custom:
  - name: satu
  - name: dua
"""


def _git(root: str, *args: str) -> None:
    subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, text=True)


def _repo(tmp_path, files: dict[str, str]):
    root = tmp_path / "repo"
    if root.exists():  # uji kedua dalam satu test memakai tmp_path yang sama
        shutil.rmtree(root)
    root.mkdir()
    _git(str(root), "init", "-q")
    _git(str(root), "config", "user.email", "uji@example.com")
    _git(str(root), "config", "user.name", "Uji")
    for rel, isi in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(isi, encoding="utf-8")
    _git(str(root), "add", "-A")
    _git(str(root), "commit", "-qm", "init")
    return str(root)


def _lint(root: str) -> dict:
    out = subprocess.run([sys.executable, SCRIPT, "--root", root, "--json"],
                         capture_output=True, text=True, timeout=60, check=False)
    return json.loads(out.stdout)


def _dasar(**extra) -> dict:
    files = {
        "README.md": README_BERSIH,
        "docs/INDEX.md": INDEX_BERSIH,
        "docs/KEBIJAKAN.md": "# Kebijakan\n",
        "docs/adr/0001-model.md": "# ADR 1\n",
        "registry/skills.yaml": REGISTRY_BERSIH,
        "platform/docs-html-allowlist.json": json.dumps({"files": []}),
    }
    files.update(extra)
    return files


def test_repo_bersih_lolos(tmp_path):
    hasil = _lint(_repo(tmp_path, _dasar()))
    assert hasil["ok"], hasil["errors"]
    assert hasil["stats"]["custom_skill"] == 2


def test_dokumen_tanpa_entri_indeks_ditolak(tmp_path):
    hasil = _lint(_repo(tmp_path, _dasar(**{"docs/LUPA.md": "# Lupa\n"})))
    assert not hasil["ok"]
    assert any("LUPA.md" in e for e in hasil["errors"])


def test_adr_diindeks_lewat_nomor_boleh(tmp_path):
    hasil = _lint(_repo(tmp_path, _dasar(**{"docs/adr/0001-model.md": "# ADR 1 revisi\n"})))
    assert hasil["ok"], hasil["errors"]


def test_rujukan_indeks_mati_ditolak(tmp_path):
    index = INDEX_BERSIH + "| `HANTU.md` | tidak ada |\n"
    hasil = _lint(_repo(tmp_path, _dasar(**{"docs/INDEX.md": index})))
    assert not hasil["ok"]
    assert any("HANTU.md" in e for e in hasil["errors"])


def test_pdf_terlacak_ditolak(tmp_path):
    hasil = _lint(_repo(tmp_path, _dasar(**{"docs/KEBIJAKAN.pdf": "%PDF-1.4\n"})))
    assert not hasil["ok"]
    assert any("PDF" in e for e in hasil["errors"])


def test_html_tanpa_izin_ditolak(tmp_path):
    hasil = _lint(_repo(tmp_path, _dasar(**{"docs/KEBIJAKAN.html": "<html></html>\n"})))
    assert not hasil["ok"]
    assert any("KEBIJAKAN.html" in e for e in hasil["errors"])


def test_html_berizin_lolos_dan_wajib_alasan(tmp_path):
    izin = {"files": [{"path": "docs/KEBIJAKAN.html", "reason": "dibaca langsung dari repo"}]}
    berkas = _dasar(**{"docs/KEBIJAKAN.html": "<html></html>\n",
                       "platform/docs-html-allowlist.json": json.dumps(izin)})
    hasil = _lint(_repo(tmp_path, berkas))
    assert hasil["ok"], hasil["errors"]

    # Entri tanpa alasan tertulis tetap lolos tapi harus berisik: gerbang tanpa alasan = daftar tanpa makna.
    izin_tanpa_alasan = {"files": [{"path": "docs/KEBIJAKAN.html", "reason": ""}]}
    berkas["platform/docs-html-allowlist.json"] = json.dumps(izin_tanpa_alasan)
    hasil2 = _lint(_repo(tmp_path, berkas))
    assert any("alasan" in w for w in hasil2["warnings"])


def test_klaim_jumlah_skill_harus_sama_registry(tmp_path):
    hasil = _lint(_repo(tmp_path, _dasar(**{"registry/skills.yaml": "custom:\n  - name: satu\n"})))
    assert not hasil["ok"]
    assert any("kini 2" in e and "1" in e for e in hasil["errors"])


def test_tautan_repo_resmi_wajib_ada(tmp_path):
    readme = README_BERSIH.replace("Repo resmi: <https://github.com/anashadi-node/super-dev-builders>\n\n", "")
    hasil = _lint(_repo(tmp_path, _dasar(**{"README.md": readme})))
    assert not hasil["ok"]
    assert any("github.com/anashadi-node/super-dev-builders" in e for e in hasil["errors"])


def test_repo_sdb_sendiri_lolos():
    """Gerbang yang tidak lolos di repo sendiri adalah gerbang yang akan dimatikan orang."""
    hasil = _lint(REPO)
    assert hasil["ok"], hasil["errors"]
