#!/usr/bin/env python3
"""Bukti deterministik untuk skill pihak ketiga yang dipasang di profil default.

- pola berbahaya (kelas yang kita larang: sudo, curl|sh, obfuscation, exfil, ssh key, rm -rf root)
- sha256 per berkas (provenance; bisa dibandingkan ulang dengan upstream)
Output: JSON siap disimpan sebagai artefak bukti.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time

SKILLS_DIR = os.path.expanduser("~/.hermes/skills")
PATTERNS = {
    "sudo": r"\bsudo\b",
    "curl_pipe_shell": r"curl[^\n|]*\|\s*(ba)?sh",
    "wget_pipe_shell": r"wget[^\n|]*\|\s*(ba)?sh",
    "obfuscation_eval": r"\beval\s*\(",
    "base64_decode": r"base64\s+(-d|--decode)",
    "credential_read": r"\.ssh/id_|\.aws/credentials|\.netrc|printenv\s|env\s*\|\s*grep",
    "exfil_http": r"requests\.post\(|urllib\.request\.urlopen\([^)]*data=",
    "rm_rf_root": r"rm\s+-rf\s+/(?!tmp/)",
    "chmod_777": r"chmod\s+777",
    "reverse_shell": r"/dev/tcp/|nc\s+-e|bash\s+-i",
}
TEXT_EXT = (".md", ".py", ".sh", ".yaml", ".yml", ".json", ".txt", ".js", ".ts")


def scan_skill(name: str) -> dict:
    root = os.path.join(SKILLS_DIR, name)
    files, findings, hashes = [], [], {}
    for dirpath, _dirs, names in os.walk(root):
        for fn in sorted(names):
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            try:
                raw = open(path, "rb").read()
            except OSError:
                continue
            files.append(rel)
            hashes[rel] = hashlib.sha256(raw).hexdigest()
            if not fn.endswith(TEXT_EXT):
                continue
            text = raw.decode("utf-8", "ignore")
            for label, pat in PATTERNS.items():
                for m in re.finditer(pat, text):
                    line = text[: m.start()].count("\n") + 1
                    findings.append({"pattern": label, "file": rel, "line": line,
                                     "match": text[max(0, m.start() - 60): m.end() + 60].replace("\n", " ")[:160]})
    return {"skill": name, "path": root, "n_files": len(files), "files": files,
            "danger_findings": findings, "sha256": hashes,
            "danger_clean": len(findings) == 0}


def main(names: list[str]) -> int:
    out = {"provenance": "scripts/third_party_scan.py (di dalam repo)",
           "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
           "redaction_status": "clean", "status": "OBSERVED",
           "scanner": "pola regex deterministik (bukan LLM)", "skills": []}
    for n in names:
        p = os.path.join(SKILLS_DIR, n)
        if not os.path.isdir(p):
            out["skills"].append({"skill": n, "error": "tidak terpasang"})
            continue
        out["skills"].append(scan_skill(n))
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
