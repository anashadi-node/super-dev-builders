# SDB C1-03 Capability Routing Result

**Verdict:** `PASS_VERIFIED_SUBSCOPE` — independent D6+D8 re-review #2 (`deleg_0d003ba8`) returned PASS with 2 Low findings (N-1, N-2) plus one hardening note, all closed afterwards; round-1 PASS was rejected earlier  
**Verification time:** 2026-11-21 (round 2, WIB)  
**Branch:** `feat/c2b2g-ci-hardening`  
**Reference/current HEAD:** `278f13a0d0d41515d0fb5e60778a428e61ab99e1`  
**Local commit C1-03:** not created  
**Maturity:** D6/D8 remediation verified locally with controlled executors; live Hermes was not run; not `INTEGRATED_VERIFIED`

## 1. Outcome

The approved §7 boundary work is implemented within the file allowlist:

- caller self-approval was removed from the CLI and replaced by a distinct trusted approval registry;
- Bubblewrap now builds an allowlisted mount namespace (no host `/`, no `/run`, `/var`, `$HOME` content, `~/.ssh`, other profiles, docker/dbus sockets; runtime `.env` shadowed), FD-bound approved roots, hidden read-only `.git`, and an overlay only for the active Hermes profile;
- executor output must satisfy the strict random-challenge `sdb.capability.result/1` contract;
- HEAD and protected implementation hashes/state are bound before and after execution;
- parent-only, no-follow, mandatory BE-SP-12-compatible evidence replaced the evidence bypass;
- exact frontend `FE-SP-01..12` and backend `BE-SP-01..14` inventories are enforced.

No live Hermes/customer job, worker, service, commit, push, PR, merge, deploy, workflow, agent, dashboard, CI, global-security-policy, OS, or ACL change was made.

## 2. Files

| File | SHA-256 at verification | State |
|---|---|---|
| `registry/capability_pilot.yaml` | `a73f141c15fa5ba535decef030ae6cd5a51883717e4b261e36d86957e1dcb9fd` | modified, not committed |
| `registry/capability_execution_approvals.yaml` | `509a0a9093db667cfc050a0beefca5a436d9dd7077cdd4fea3c75a53b006903f` | new trusted-config candidate, not committed |
| `scripts/sdb_capability_router.py` | `d47be6d33f03e39043445c270956028aa3f6dc12162e48edfba187b8ce20def4` | new/modified, not committed |
| `scripts/sdb_capability_trust.py` | `6e9a3530bcfa99d111eddde4c3fb553db0d589edbf4cd18c9f932885e0040e15` | new, not committed |
| `tests/test_capability_routing.py` | `6ba0f49c032cde309cd42cf251e8e9a48dbda240757fa0b6b657454ef4f92e97` | new/modified, not committed |
| `docs/INDEX.md` | one index line added (required by `make docs-lint`) | modified |
| `docs/SDB_C1_CAPABILITY_ROUTING.md` | `308332e42df42198004bd65135899cc25d29067af31576a66dd5dbef4c7eb536` | new, not committed |
| `reports/SDB_C1_ROUTING_RESULT.md` | this report | updated, not committed |

The protected `reports/SDB_NEW_SESSION_CONTINUATION_RESULT.md` was not read or modified for this remediation.

## 3. D6/D8 remediation matrix

| Finding | Remediation | Local evidence |
|---|---|---|
| Optional evidence | Production CLI has no bypass; evidence validation/write failure makes CLI fail | mandatory-evidence and symlink-parent tests |
| Declarative-only write scope | `/usr/bin/bwrap`; read-only root/repo; existing no-follow directory FDs supplied through `--bind-fd`; `.git` hidden/read-only | real Bubblewrap no-write, approved-root, and `.git` escape tests |
| Exit zero synthesized as PASS | exact result schema plus random nonce/capability/task-digest SHA-256 verifier | empty/arbitrary/malformed/forged/wrong-capability/non-allowlisted tests |
| Caller-controlled authorization | Git-tracked clean approval store distinct from Task Pack; canonical binding, issuer/time bounds, nonce, replay marker | forgery/modification/expiry/wrong-task/replay tests |
| Registry accepted 13/13 split | exact FE 01–12 and BE 01–14 sets required | registry split tests |
| Parent symlink escape | no-follow directory-FD traversal and exclusive parent writes | replay/evidence parent symlink tests |
| Revision captured too late | HEAD and protected-file digest/tracked/dirty state captured before and after | mutation and dirty/untracked tests |
| Buffered/unbounded output | streaming hard combined cap of 1 MiB; bounded stored excerpt | overflow test |
| Descendants survive timeout | new process group/session, group kill, Bubblewrap parent-death behavior | descendant side-effect test |

A positive router verdict is produced only for a challenge-verified `PASS_VERIFIED_SUBSCOPE` with mandatory evidence. `BLOCKED`, `FAIL`, malformed output, process failure, revision drift, or evidence failure cannot become positive evidence. `INTEGRATED_VERIFIED` is not an allowed result.

## 3b. Round-2 findings (D6 BLOCKED / D8 BLOCK) and remediation

| Finding | Remediation | Evidence |
|---|---|---|
| C-1 sandbox `--ro-bind / /` leaks host creds and unix sockets (docker, dbus, systemd) | allowlist root `_sandbox_base`; no `/run`,`/var`,`/home`,`/root`; runtime `.env` shadowed | `test_sandbox_hides_host_sockets_and_credentials`, `test_production_sandbox_shadows_runtime_credential_files`; mutation check: old argv sees `/var/run/docker.sock` (rc 0), new argv does not (rc 1) |
| H-1 only the `sh` stub was pinned | inner entrypoint pinned and verified (`HERMES_INNER_SHA256`) | `test_production_executor_pins_inner_hermes_entrypoint` (constant check only; runtime/profile hashing is a documented limitation) |
| H-2 `git status` could be fooled, working tree read | blobs read via `git show HEAD:path`, clean git env, `ls-files -v` flags count as dirty | `test_index_flags_cannot_hide_a_modified_approval_store`, `test_trust_checks_ignore_caller_git_environment` |
| H-3 / M-excerpt redaction leaks | no raw content stored; `[WITHHELD bytes sha256]` marker | `test_excerpt_never_persists_raw_executor_output` |
| M-4 revision binding reads same loader | uses the same committed-blob state function | existing revision tests |
| M-5 duplicate keys, 9999 TTL, writable `scripts/registry/runs` | strict YAML loader, 31-day TTL, forbidden root heads | `test_approval_rejects_*` |
| L-1 approval burned before validation | consumption moved after executor/sandbox/roots validation | existing replay tests |
| L-2 unbounded goal / blocking stdin | goal 4096 chars, 32 paths, prompt <= 48 KiB | `test_oversized_goal_is_rejected_at_the_boundary` |
| L-3 signal exit recorded as 0 | `128 + signal` | `test_signal_exit_is_not_reported_as_success` |
| M-1, M-2, M-3, network egress, live smoke, BE-SP-04 name source, `test_be_sp03_contract.py` docstring name | **not fixed**: accepted limitations with honest labels (see docs "Accepted limitations") | docs |

## 3c. Re-review #2 outcome

D6+D8 combined: **PASS**. Probes inside the real bwrap argv confirmed absent: docker.sock, `/run`, `/run/user`, `/var`, `/root`, `~/.ssh`, `~/.hermes/auth.json`, other profiles, `/etc/shadow`; runtime `.env`/`.envrc` shadowed empty. New findings closed: N-1 unhashable YAML key now `yaml_invalid` (test added); N-2 abstract unix sockets documented as part of shared-network limitation; `GIT_NO_REPLACE_OBJECTS=1` added to the git env. The active profile (incl. its `auth.json`) stays readable by design and egress is unfiltered, so the exfiltration limitation stands.

## 4. Fresh verification (round 2)

```text
.venv/bin/python -m pytest tests/test_capability_routing.py -q   -> 43 passed
.venv/bin/python -m pytest tests/test_capability_evidence.py tests/test_be_sp03_contract.py tests/test_capability_routing.py -q -> 111 passed
ruff check (3 files) -> All checks passed!
pyright (3 files)    -> 0 errors, 0 warnings, 0 informations
git diff --check     -> exit 0
```

Executable metadata was checked without invocation:

- `/usr/bin/bwrap`: regular non-symlink, UID/GID `0/0`, mode `0755`, no group/world write bit, SHA-256 `523da3e7399044be5163aee6f57a77a6bef7454376e28f0a0627920bae1b76b6`;
- `/home/anashadi/.local/bin/hermes`: regular non-symlink, UID/GID `1000/1000`, mode `0755`, no group/world write bit, pinned SHA-256 `ce029ccc2679fb234364effdc67971c01ea4b8920866793282b53b61c9a57e2f`.

The deterministic approval task digest was independently recomputed as `33b8bce0bda2e20c4522c2dfc7402ff38d3faa668fcb5c3bf39a3266f6f359c6`, matching the approval record.

## 5. Trust model and limitations

The authorization trust root is committed local Git configuration, not a signature or external approval broker. The loader accepts the approval store and routing registry only when tracked and byte-clean relative to committed Git state. It therefore resists a caller changing the Task Pack or working-tree approval data, but it does not resist a principal able to rewrite trusted Git history. Protected review/branch controls or a signed external service are required for broader production use.

This task prohibited commits. Consequently, the new approval store is intentionally rejected by the production CLI while it remains untracked, and the modified routing registry is rejected while dirty. Controlled tests create committed fixture repositories to exercise the intended production trust path. Activation requires a separately authorized reviewed commit; this report does not perform or authorize it.

Hermes network access remains shared because its LLM transport requires network. This is not egress filtering. The deterministic smoke task requests no arbitrary tools. The Hermes executable is user-owned mode `0755`: the router rejects group/world mutability, checks the pinned digest immediately before launch, validates/open-retains the same inode, and passes that FD into the sandbox. A concurrently compromised same-UID host process remains outside the Bubblewrap child threat boundary; a root-owned immutable/package-verified executable would be stronger.

No live nonproduction Hermes execution or runtime evidence was created because the user prohibited live Hermes/jobs/services. The fresh tests verify the sandbox and evidence paths with a controlled programmatic-only executable seam. Full repository-wide `make check` is **red at HEAD 278f13a independent of C1-03** (verified by stashing all C1-03 changes and re-running): `test_gerbang_rahasia_lulus_dengan_scanner_asli` and `test_ratchet_menolak_kebocoran_baru` fail because gitleaks flags 2 `generic-api-key` hits in committed `tests/test_be_sp03_contract.py` (lines 52, 591), and `make fixtures-verify` reports `android-mini` and `desktop-mini` hash mismatch. C1-03 adds no new gitleaks hit (checked with the repo `.gitleaks.toml`) and no new failing test. The result is `PASS_VERIFIED_SUBSCOPE` at most, never `INTEGRATED_VERIFIED`. The hardened sandbox has not been exercised with a live Hermes run (prohibited); whether Hermes starts correctly with a read-only runtime and no `/run` is unproven.
