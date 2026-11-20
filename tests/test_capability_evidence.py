"""C1-01 — tes evidence capability BE-SP-12 (`sdb.capability.evidence/1`).

Semua data sintetis: repo git sementara, artefak sementara, tanpa jaringan,
tanpa menyentuh `runs/capability/` milik repo asli, tanpa menjalankan perintah
yang berasal dari payload.

Peta tes -> acceptance criteria direktif:
  T1 evidence sah diterima                     -> test_T01_*
  T2 capability tak dikenal ditolak            -> test_T02_*
  T3 revision/hash mismatch ditolak            -> test_T03_*
  T4 JSON/skema/NaN/Infinity ditolak           -> test_T04_*
  T5 exit code gagal bukan PASS                -> test_T05_*
  T6 nol tes tidak menghasilkan acceptance     -> test_T06_*
  T7 path traversal & symlink ditolak          -> test_T07_*
  T8 self-attestation tidak naik level         -> test_T08_*
  T9 mutation testing di salinan scratch       -> test_T09_*
  T10 19 stage & struktur agent utuh           -> test_T10_*
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import sdb_capability_evidence as evd

HEAD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
OTHER = "0123456789abcdef0123456789abcdef01234567"


# ---------- fixtures ----------
def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "user.email=fixture@sdb.test",
         "-c", "user.name=sdb-test", *args],
        cwd=str(repo), capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"git {args} gagal: {proc.stderr}"
    return proc.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> dict:
    """Repo git sementara + salinan registry pilot (isolasi penuh dari repo asli)."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "registry").mkdir()
    shutil.copy(REPO / "registry/capability_pilot.yaml",
                root / "registry/capability_pilot.yaml")
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    head = _git(root, "rev-parse", "HEAD")
    return {"root": root, "head": head, "evidence": root / "runs" / "capability"}


def _artifact(repo_dir: Path, name: str = "junit.xml", body: str = "<testsuite/>\n") -> tuple[str, str]:
    path = repo_dir / "artifacts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    data = path.read_bytes()
    import hashlib
    return path.relative_to(repo_dir).as_posix(), hashlib.sha256(data).hexdigest()


def _payload(**over) -> dict:
    """Payload sah; `over` menimpa field tertentu untuk kasus negatif.

    Revision default hanya konstanta SHA sah. Helper `_validate` mengikat default
    itu ke HEAD fixture, agar tes negatif lain tidak berhenti terlalu dini pada
    revision mismatch.
    """
    base = {
        "schema": evd.SCHEMA,
        "capability_id": "BE-SP-12",
        "revision": HEAD,
        "test_command": "pytest -q tests/test_capability_evidence.py",
        "exit_code": 0,
        "test_results": {"passed": 12, "failed": 0, "skipped": 1, "errors": 0, "total": 13},
        "artifact_refs": [],
        "evidence_level": "AGENT_REPORTED",
        "verification_timestamp": "2026-11-20T08:00:00Z",
        "review_status": "NOT_REVIEWED",
        "release_authorization": "NOT_AUTHORIZED",
    }
    base.update(over)
    return base


NOW = __import__("datetime").datetime(2026, 11, 20, 8, 5, tzinfo=__import__("datetime").timezone.utc)


def _validate(payload, repo_fx, **over):
    # HEAD acak per fixture; payload normal menggunakan HEAD itu. Payload yang
    # sengaja menguji revision tetap dipertahankan.
    payload = dict(payload)
    if payload.get("revision") == HEAD:
        payload["revision"] = repo_fx["head"]
    return evd.validate_payload(payload, repo=repo_fx["root"], head=repo_fx["head"],
                                now=over.pop("now", NOW))


# ---------- T1: evidence sah diterima ----------
def test_T01_evidence_sah_diterima_dan_tercatat(repo):
    rel, digest = _artifact(repo["root"])
    out = evd.record(capability_id="BE-SP-12", revision=repo["head"],
                     test_command="pytest -q tests/test_capability_evidence.py",
                     exit_code=0,
                     results={"passed": 12, "failed": 0, "skipped": 1, "errors": 0, "total": 13},
                     artifacts=[{"path": rel, "sha256": digest}],
                     root=repo["evidence"], repo=repo["root"], now=NOW)
    assert out["execution_status"] == evd.EXEC_PASS
    assert out["acceptance_status"] == evd.ACCEPT_INFORMATIONAL
    assert out["release_authorization"] == evd.RELEASE_NOT_AUTHORIZED
    path = Path(out["evidence_path"])
    assert path.is_file()
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    ev = json.loads(path.read_text(encoding="utf-8"))
    assert ev["integrity"] == evd.integrity_of(ev)
    assert ev["artifact_refs"] == [{"path": rel, "sha256": digest}]
    verdict = evd.validate_file(path, repo=repo["root"], head=repo["head"], now=NOW)
    assert verdict["execution_status"] == evd.EXEC_PASS


def test_T01b_penulisan_atomik_tidak_meninggalkan_berkas_tmp(repo):
    evd.record(capability_id="BE-SP-12", revision=repo["head"], test_command="pytest -q",
               exit_code=0, results={"passed": 1, "failed": 0, "skipped": 0, "errors": 0,
                                     "total": 1},
               root=repo["evidence"], repo=repo["root"], now=NOW)
    leftovers = list(repo["evidence"].rglob(".capability-*.tmp"))
    assert leftovers == []


def test_T01c_evidence_immutable_tanpa_replace(repo):
    kwargs = dict(capability_id="BE-SP-12", revision=repo["head"], test_command="pytest -q",
                  exit_code=0,
                  results={"passed": 1, "failed": 0, "skipped": 0, "errors": 0, "total": 1},
                  root=repo["evidence"], repo=repo["root"], now=NOW)
    evd.record(**kwargs)
    with pytest.raises(evd.EvidenceError) as exc:
        evd.record(**kwargs)
    assert exc.value.code == "evidence_exists"
    # replace eksplisit tetap atomik dan tidak menghapus direktori
    evd.record(**kwargs, replace=True)


def test_T01d_gagal_validasi_tidak_menulis_apa_pun(repo):
    target = repo["evidence"] / "BE-SP-12" / f"{repo['head']}.json"
    with pytest.raises(evd.EvidenceError):
        evd.record(capability_id="BE-SP-12", revision=repo["head"], test_command="pytest -q",
                   exit_code=0,
                   results={"passed": 1, "failed": 0, "skipped": 0, "errors": 0, "total": 1},
                   artifacts=[{"path": "artifacts/tidak-ada.xml", "sha256": "b" * 64}],
                   root=repo["evidence"], repo=repo["root"], now=NOW)
    assert not target.exists()


def test_T01e_race_destination_tidak_menimpa_berkas_pesaing(tmp_path, monkeypatch):
    target = tmp_path / "evidence.json"
    competitor = b"dibuat proses pesaing\n"

    def competing_link(_source, destination):
        Path(destination).write_bytes(competitor)
        raise FileExistsError(destination)

    monkeypatch.setattr(evd.os, "link", competing_link)
    with pytest.raises(evd.EvidenceError) as exc:
        evd.atomic_write(target, b"payload kita\n")
    assert exc.value.code == "evidence_exists"
    assert target.read_bytes() == competitor
    assert list(tmp_path.glob(".capability-*.tmp")) == []


# ---------- T2: capability tak dikenal / tak sah ----------
@pytest.mark.parametrize("cid,code", [
    ("BE-SP-99", "capability_unknown"),
    ("be-sp-12", "capability_id_invalid"),
    ("BE_SP_12", "capability_id_invalid"),
    ("", "capability_id_invalid"),
    (12, "capability_id_invalid"),
])
def test_T02_capability_tak_dikenal_ditolak(repo, cid, code):
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(capability_id=cid), repo)
    assert exc.value.code == code


# ---------- T3: revision & hash mismatch ----------
def test_T03a_revision_bukan_head_ditolak(repo):
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(revision=OTHER), repo)
    assert exc.value.code == "revision_mismatch"


def test_T03b_revision_bukan_sha40_ditolak(repo):
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(revision=repo["head"][:12]), repo)
    assert exc.value.code == "revision_invalid"


def test_T03c_hash_artefak_salah_ditolak(repo):
    rel, _ = _artifact(repo["root"])
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(artifact_refs=[{"path": rel, "sha256": "c" * 64}]), repo)
    assert exc.value.code == "artifact_hash_mismatch"


def test_T03d_artefak_berubah_setelah_dicatat_ditolak(repo):
    rel, digest = _artifact(repo["root"])
    out = evd.record(capability_id="BE-SP-12", revision=repo["head"], test_command="pytest -q",
                     exit_code=0,
                     results={"passed": 2, "failed": 0, "skipped": 0, "errors": 0, "total": 2},
                     artifacts=[{"path": rel, "sha256": digest}],
                     root=repo["evidence"], repo=repo["root"], now=NOW)
    (repo["root"] / rel).write_text("<testsuite>diubah</testsuite>\n", encoding="utf-8")
    with pytest.raises(evd.EvidenceError) as exc:
        evd.validate_file(Path(out["evidence_path"]), repo=repo["root"], head=repo["head"], now=NOW)
    assert exc.value.code == "artifact_hash_mismatch"


# ---------- T4: JSON / skema / NaN / Infinity ----------
def test_T04a_json_rusak_ditolak(repo):
    p = repo["evidence"] / "rusak.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"schema": "sdb.capability.evidence/1",}', encoding="utf-8")
    with pytest.raises(evd.EvidenceError) as exc:
        evd.validate_file(p, repo=repo["root"], head=repo["head"], now=NOW)
    assert exc.value.code == "json_invalid"


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_T04b_nan_infinity_ditolak(repo, literal):
    body = json.dumps(_payload()).replace('"exit_code": 0', f'"exit_code": {literal}')
    with pytest.raises(evd.EvidenceError) as exc:
        evd.loads_strict(body)
    assert exc.value.code == "json_non_finite"


def test_T04c_kunci_ganda_ditolak(repo):
    body = '{"schema":"x","schema":"y"}'
    with pytest.raises(evd.EvidenceError) as exc:
        evd.loads_strict(body)
    assert exc.value.code == "json_duplicate_key"


@pytest.mark.parametrize("mutate,code", [
    (lambda p: p.pop("revision"), "schema_missing_field"),
    (lambda p: p.update(catatan="tambahan"), "schema_unknown_field"),
    (lambda p: p.update(schema="sdb.capability.evidence/0"), "schema_mismatch"),
    (lambda p: p.update(exit_code=True), "exit_code_invalid"),
    (lambda p: p.update(exit_code=999), "exit_code_invalid"),
    (lambda p: p.update(test_results={"passed": 1, "failed": 0, "skipped": 0,
                                      "errors": 0, "total": 5}), "test_results_inconsistent"),
    (lambda p: p.update(test_results={"passed": 1, "failed": 0, "skipped": 0, "errors": 0}),
     "test_results_invalid"),
    (lambda p: p.update(verification_timestamp="2026-11-20 08:00:00"), "timestamp_invalid"),
    (lambda p: p.update(verification_timestamp="2027-01-01T00:00:00Z"), "timestamp_future"),
    (lambda p: p.update(artifact_refs=[{"path": "a.xml"}]), "artifact_refs_invalid"),
])
def test_T04d_skema_dilanggar_ditolak(repo, mutate, code):
    payload = _payload()
    mutate(payload)
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(payload, repo)
    assert exc.value.code == code


def test_T04e_skema_berkas_selaras_dengan_validator():
    schema = json.loads((REPO / "registry/capability_evidence.schema.json").read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["additionalProperties"] is False
    assert tuple(schema["required"]) == evd._REQUIRED
    assert schema["properties"]["evidence_level"]["enum"] == ["AGENT_REPORTED"]
    assert schema["properties"]["review_status"]["enum"] == ["NOT_REVIEWED"]
    assert schema["properties"]["release_authorization"]["enum"] == ["NOT_AUTHORIZED"]
    assert schema["properties"]["test_results"]["properties"]["total"]["minimum"] == 1


# ---------- T5: exit code gagal bukan PASS ----------
def test_T05_exit_code_gagal_tidak_pernah_pass(repo):
    out = evd.record(capability_id="BE-SP-12", revision=repo["head"], test_command="pytest -q",
                     exit_code=1,
                     results={"passed": 11, "failed": 1, "skipped": 0, "errors": 0, "total": 12},
                     root=repo["evidence"], repo=repo["root"], now=NOW)
    assert out["execution_status"] == evd.EXEC_FAIL
    assert out["acceptance_status"] == evd.ACCEPT_NONE
    path = Path(out["evidence_path"])
    assert evd.validate_file(path, repo=repo["root"], head=repo["head"], now=NOW)[
        "execution_status"] == evd.EXEC_FAIL


def test_T05b_exit_gagal_tanpa_kegagalan_tercatat_ditolak(repo):
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(exit_code=1), repo)
    assert exc.value.code == "test_results_inconsistent"


def test_T05c_exit_nol_tanpa_tes_lulus_bukan_pass(repo):
    payload = _payload(test_results={"passed": 0, "failed": 2, "skipped": 0,
                                     "errors": 0, "total": 2})
    out = _validate(payload, repo)
    assert out["execution_status"] == evd.EXEC_FAIL
    assert out["acceptance_status"] == evd.ACCEPT_NONE


# ---------- T6: nol tes tidak menghasilkan acceptance ----------
def test_T06_total_nol_ditolak(repo):
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(test_results={"passed": 0, "failed": 0, "skipped": 0,
                                        "errors": 0, "total": 0}), repo)
    assert exc.value.code == "no_tests_executed"


def test_T06b_semua_skip_ditolak(repo):
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(test_results={"passed": 0, "failed": 0, "skipped": 4,
                                        "errors": 0, "total": 4}), repo)
    assert exc.value.code == "no_tests_executed"


# ---------- T7: path traversal & symlink ----------
def test_T07a_path_traversal_ditolak(repo):
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(artifact_refs=[{"path": "../../etc/passwd",
                                           "sha256": "d" * 64}]), repo)
    assert exc.value.code == "artifact_path_traversal"


def test_T07b_path_absolut_dan_backslash_ditolak(repo):
    for raw in ("/etc/passwd", "artifacts\\junit.xml", "artifacts/../../x.xml", "."):
        with pytest.raises(evd.EvidenceError) as exc:
            evd.safe_artifact(repo["root"], raw)
        assert exc.value.code in ("artifact_path_absolute", "artifact_path_invalid",
                                  "artifact_path_traversal")


def test_T07c_artefak_symlink_ditolak(repo):
    real = repo["root"] / "artifacts" / "real.xml"
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text("<testsuite/>\n", encoding="utf-8")
    link = repo["root"] / "artifacts" / "link.xml"
    link.unlink(missing_ok=True)
    link.symlink_to(real)
    with pytest.raises(evd.EvidenceError) as exc:
        evd.safe_artifact(repo["root"], "artifacts/link.xml")
    assert exc.value.code == "artifact_symlink"


def test_T07d_direktori_symlink_menuju_luar_ditolak(repo):
    luar = repo["root"].parent / "luar"
    luar.mkdir(exist_ok=True)
    (luar / "rahasia.txt").write_text("bukan milikmu\n", encoding="utf-8")
    link_dir = repo["root"] / "linked"
    if link_dir.exists() or link_dir.is_symlink():
        link_dir.unlink()
    link_dir.symlink_to(luar, target_is_directory=True)
    with pytest.raises(evd.EvidenceError) as exc:
        evd.safe_artifact(repo["root"], "linked/rahasia.txt")
    assert exc.value.code == "artifact_symlink"


def test_T07e_root_symlink_ditolak(repo, tmp_path):
    root = tmp_path / "root-nyata"
    root.mkdir()
    link = tmp_path / "root-link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(evd.EvidenceError) as exc:
        evd.safe_artifact(link, "x.xml")
    assert exc.value.code == "artifact_root_symlink"


def test_T07f_artefak_hilang_ditolak(repo):
    with pytest.raises(evd.EvidenceError) as exc:
        evd.safe_artifact(repo["root"], "artifacts/tidak-ada.xml")
    assert exc.value.code == "artifact_missing"


def test_T07g_root_output_di_luar_runs_capability_ditolak(repo, tmp_path):
    with pytest.raises(evd.EvidenceError) as exc:
        evd.record(capability_id="BE-SP-12", revision=repo["head"], test_command="pytest -q",
                   exit_code=0,
                   results={"passed": 1, "failed": 0, "skipped": 0, "errors": 0, "total": 1},
                   root=tmp_path / "output-liar", repo=repo["root"], now=NOW)
    assert exc.value.code == "evidence_root_unauthorized"


def test_T07h_symlink_pada_rantai_root_output_ditolak(repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo["root"] / "runs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(evd.EvidenceError) as exc:
        evd.record(capability_id="BE-SP-12", revision=repo["head"], test_command="pytest -q",
                   exit_code=0,
                   results={"passed": 1, "failed": 0, "skipped": 0, "errors": 0, "total": 1},
                   root=repo["evidence"], repo=repo["root"], now=NOW)
    assert exc.value.code == "evidence_root_symlink"


def test_T07i_validate_tidak_membaca_berkas_di_luar_root(repo, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("bukan evidence", encoding="utf-8")
    with pytest.raises(evd.EvidenceError) as exc:
        evd.validate_file(outside, repo=repo["root"], head=repo["head"], now=NOW)
    assert exc.value.code == "evidence_path_unauthorized"


# ---------- T8: self-attestation ----------
@pytest.mark.parametrize("field,value,code", [
    ("evidence_level", "CI_ATTESTED", "self_attestation_rejected"),
    ("evidence_level", "INDEPENDENT_REVIEW", "self_attestation_rejected"),
    ("evidence_level", "RELEASE_ELIGIBLE", "evidence_level_invalid"),
    ("review_status", "REVIEWED_INDEPENDENT", "self_attestation_rejected"),
    ("review_status", "APPROVED", "self_attestation_rejected"),
    ("release_authorization", "AUTHORIZED", "release_claim_rejected"),
])
def test_T08a_klaim_naik_level_ditolak(repo, field, value, code):
    with pytest.raises(evd.EvidenceError) as exc:
        _validate(_payload(**{field: value}), repo)
    assert exc.value.code == code


def test_T08b_agent_reported_tidak_pernah_accepted_independent():
    assert evd.acceptance_status(evd.LEVEL_AGENT, evd.REVIEW_NONE, evd.EXEC_PASS) == \
        evd.ACCEPT_INFORMATIONAL
    assert evd.acceptance_status(evd.LEVEL_CI, evd.REVIEW_NONE, evd.EXEC_PASS) == evd.ACCEPT_PENDING
    assert evd.acceptance_status(evd.LEVEL_CI, evd.REVIEW_INDEPENDENT, evd.EXEC_PASS) == \
        evd.ACCEPT_PENDING
    assert evd.acceptance_status(evd.LEVEL_INDEPENDENT, evd.REVIEW_INDEPENDENT,
                                 evd.EXEC_PASS) == evd.ACCEPT_INDEPENDENT
    assert evd.acceptance_status(evd.LEVEL_INDEPENDENT, evd.REVIEW_INDEPENDENT,
                                 evd.EXEC_FAIL) == evd.ACCEPT_NONE


def test_T08c_integritas_diubah_ditolak(repo):
    out = evd.record(capability_id="BE-SP-12", revision=repo["head"], test_command="pytest -q",
                     exit_code=0,
                     results={"passed": 3, "failed": 0, "skipped": 0, "errors": 0, "total": 3},
                     root=repo["evidence"], repo=repo["root"], now=NOW)
    path = Path(out["evidence_path"])
    ev = json.loads(path.read_text(encoding="utf-8"))
    ev["test_results"]["passed"] = 999
    path.write_text(json.dumps(ev), encoding="utf-8")
    with pytest.raises(evd.EvidenceError) as exc:
        evd.validate_file(path, repo=repo["root"], head=repo["head"], now=NOW)
    assert exc.value.code == "integrity_mismatch"


def test_T08d_test_command_tidak_pernah_dijalankan(repo, tmp_path):
    canary = tmp_path / "pwned.txt"
    out = evd.record(capability_id="BE-SP-12", revision=repo["head"],
                     test_command=f"touch {canary}", exit_code=0,
                     results={"passed": 1, "failed": 0, "skipped": 0, "errors": 0, "total": 1},
                     root=repo["evidence"], repo=repo["root"], now=NOW)
    assert not canary.exists()
    assert Path(out["evidence_path"]).is_file()
    src = (REPO / "scripts/sdb_capability_evidence.py").read_text(encoding="utf-8")
    for forbidden in ("os.system", "shell=True", "eval(", "exec("):
        assert forbidden not in src


# ---------- T9: mutation testing dalam salinan scratch ----------
_MUTATIONS = {
    "M1_revisi_tidak_diikat": [
        ("    if revision != head:\n", "    if False:  # mutan\n"),
    ],
    "M2_hash_artefak_tidak_diperiksa": [
        ("        if actual != declared:\n", "        if False:  # mutan\n"),
    ],
    "M3_self_attestation_diizinkan": [
        ("    if level in ELEVATED_LEVELS:\n", "    if False:  # mutan\n"),
        ("    if level not in PRODUCER_LEVELS:\n",
         "    if level not in PRODUCER_LEVELS + ELEVATED_LEVELS:  # mutan\n"),
    ],
    "M4_acceptance_dinaikkan": [
        ("    if level in PRODUCER_LEVELS:\n        return ACCEPT_INFORMATIONAL\n",
         "    if level in PRODUCER_LEVELS:\n        return ACCEPT_INDEPENDENT  # mutan\n"),
    ],
    "M5_nol_tes_boleh_pass": [
        ('    if vals["total"] == 0:\n        '
         'raise EvidenceError("no_tests_executed", "total 0: tidak ada tes yang dijalankan")\n',
         "    # mutan\n"),
        ('    if vals["passed"] + vals["failed"] + vals["errors"] == 0:\n        '
         'raise EvidenceError("no_tests_executed", "semua tes skip: tidak ada eksekusi nyata")\n',
         "    # mutan\n"),
        ("    if exit_code == 0 and vals[\"failed\"] == 0 and vals[\"errors\"] == 0 and vals[\"passed\"] > 0:\n",
         "    if exit_code == 0 and vals[\"failed\"] == 0 and vals[\"errors\"] == 0:  # mutan\n"),
    ],
}

_DRIVER = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import sdb_capability_evidence as evd
case = json.loads(sys.stdin.read())
repo, head, now = case["repo"], case["head"], evd._dt.datetime(2026, 11, 20, 8, 5, tzinfo=evd._dt.timezone.utc)
payload = case["payload"]
try:
    out = evd.validate_payload(payload, repo=__import__("pathlib").Path(repo), head=head, now=now)
    print(json.dumps({"rejected": False, "acceptance": out["acceptance_status"],
                      "execution": out["execution_status"]}))
except evd.EvidenceError as exc:
    print(json.dumps({"rejected": True, "code": exc.code}))
'''


def _run_driver(module_dir: Path, repo_dir: Path, case: dict, scratch: Path) -> dict:
    driver = scratch / f"driver-{module_dir.name}.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=f"{module_dir}{os.pathsep}{REPO / 'scripts'}")
    proc = subprocess.run([sys.executable, str(driver), str(module_dir)],
                          input=json.dumps(case), capture_output=True, text=True,
                          env=env, cwd=str(repo_dir), check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _mutant_dir(tmp_path: Path, name: str) -> tuple[Path, bool]:
    """Salin modul ke scratch lalu terapkan mutasi. True bila semua pola ketemu."""
    src = (REPO / "scripts/sdb_capability_evidence.py").read_text(encoding="utf-8")
    mutated, ok = src, True
    for old, new in _MUTATIONS[name]:
        if old not in mutated:
            ok = False
        mutated = mutated.replace(old, new, 1)
    d = tmp_path / name
    d.mkdir()
    (d / "sdb_capability_evidence.py").write_text(mutated, encoding="utf-8")
    return d, ok


def test_T09_mutation_testing_mendeteksi_kontrol_hilang(tmp_path):
    """Setiap mutan harus LOLOS pada input yang seharusnya ditolak aslinya.

    Bila mutan tetap menolak, berarti kontrol tidak diuji oleh tes mana pun
    (tes tidak sensitif) — itu kegagalan T9.
    """
    src = (REPO / "scripts/sdb_capability_evidence.py").read_text(encoding="utf-8")
    for mutations in _MUTATIONS.values():
        for old, _ in mutations:
            assert old in src, f"pola mutasi tidak ditemukan: {old[:48]!r}"

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q", "-b", "main")
    (repo_dir / "registry").mkdir()
    shutil.copy(REPO / "registry/capability_pilot.yaml", repo_dir / "registry/capability_pilot.yaml")
    art = repo_dir / "artifacts" / "junit.xml"
    art.parent.mkdir(parents=True)
    art.write_bytes(b"<testsuite/>\n")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-qm", "init")
    head = _git(repo_dir, "rev-parse", "HEAD")

    base = {"schema": evd.SCHEMA, "capability_id": "BE-SP-12", "revision": head,
            "test_command": "pytest -q", "exit_code": 0,
            "test_results": {"passed": 2, "failed": 0, "skipped": 0, "errors": 0, "total": 2},
            "artifact_refs": [], "evidence_level": "AGENT_REPORTED",
            "verification_timestamp": "2026-11-20T08:00:00Z",
            "review_status": "NOT_REVIEWED", "release_authorization": "NOT_AUTHORIZED"}

    def case(**over):
        payload = json.loads(json.dumps(base))
        payload.update(over)
        return {"repo": str(repo_dir), "head": head, "payload": payload}

    cases = {
        "M1_revisi_tidak_diikat": case(revision="f" * 40),
        "M2_hash_artefak_tidak_diperiksa": case(
            artifact_refs=[{"path": "artifacts/junit.xml", "sha256": "9" * 64}]),
        "M3_self_attestation_diizinkan": case(evidence_level="INDEPENDENT_REVIEW"),
        "M4_acceptance_dinaikkan": case(),
        "M5_nol_tes_boleh_pass": case(
            test_results={"passed": 0, "failed": 0, "skipped": 1, "errors": 0, "total": 1}),
    }

    # Repo asli: seluruh kasus DITOLAK (atau tidak menghasilkan acceptance).
    for name, payload_case in cases.items():
        res = _run_driver(REPO / "scripts", repo_dir, payload_case, tmp_path)
        if name == "M4_acceptance_dinaikkan":
            assert res["rejected"] is False
            assert res["acceptance"] == evd.ACCEPT_INFORMATIONAL, res
        elif name == "M5_nol_tes_boleh_pass":
            assert res["rejected"] is True
            assert res["code"] == "no_tests_executed", res
        else:
            assert res["rejected"] is True, f"{name}: asli seharusnya menolak, dapat {res}"

    # Mutan: kontrol yang dihapus harus membuat kasus buruk LOLOS.
    for name, payload_case in cases.items():
        d, ok = _mutant_dir(tmp_path, name)
        assert ok, f"mutasi {name} gagal diterapkan"
        res = _run_driver(d, repo_dir, payload_case, tmp_path)
        if name == "M4_acceptance_dinaikkan":
            assert res["acceptance"] == evd.ACCEPT_INDEPENDENT, f"{name}: mutan tidak terdeteksi {res}"
        elif name == "M5_nol_tes_boleh_pass":
            assert res["execution"] == evd.EXEC_PASS, f"{name}: mutan tidak terdeteksi {res}"
        else:
            assert res["rejected"] is False, f"{name}: mutan tidak terdeteksi {res}"


def test_T09b_script_tidak_memuat_rahasia_atau_jaringan():
    src = (REPO / "scripts/sdb_capability_evidence.py").read_text(encoding="utf-8")
    for forbidden in ("import requests", "urllib.request", "socket.", "http://", "https://"):
        assert forbidden not in src


# ---------- T10: 19 stage & struktur agent utuh ----------
def test_T10_struktur_workflow_dan_agent_tidak_berubah():
    stages = REPO / "workflows/stages.yaml"
    head_bytes = subprocess.run(["git", "-C", str(REPO), "show", "HEAD:workflows/stages.yaml"],
                               capture_output=True, check=False)
    assert head_bytes.returncode == 0
    assert head_bytes.stdout == stages.read_bytes(), "workflows/stages.yaml berubah dari HEAD"

    import yaml
    data = yaml.safe_load(stages.read_text(encoding="utf-8"))
    assert len(data["stages"]) == 19

    agents = sorted((REPO / "agents").glob("*.yaml"))
    assert len(agents) == 9
    for path in agents:
        rel = path.relative_to(REPO).as_posix()
        show = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{rel}"],
                              capture_output=True, check=False)
        assert show.returncode == 0
        assert show.stdout == path.read_bytes(), f"{rel} berubah dari HEAD"


def test_T10b_tidak_ada_perubahan_di_jalur_terlarang():
    forbidden = ("workflows/", "agents/", "platform/", "dashboard/", ".github/",
                 "scripts/release_check.py", "scripts/did_validate.py", "registry/skills.yaml",
                 "Makefile", "pyproject.toml")
    changed = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain=v1"],
                            capture_output=True, text=True, check=True).stdout.splitlines()
    for line in changed:
        path = line[3:].strip().strip('"')
        for bad in forbidden:
            assert not (path == bad or path.startswith(bad)), f"jalur terlarang berubah: {path}"
