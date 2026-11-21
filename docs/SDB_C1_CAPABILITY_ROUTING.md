# C1-03 capability routing security boundary

## Status and scope

This implementation is a nonproduction capability-routing boundary. It does not authorize production work, customer jobs, worker execution, deployment, or a claim of `INTEGRATED_VERIFIED`.

Allowed externally reported verdicts are:

- `PASS_VERIFIED_SUBSCOPE` — a valid executor result before evidence promotion;
- `INTEGRATION_TESTED_NONPRODUCTION` — a challenge-verified result with mandatory evidence;
- `BLOCKED`;
- `FAIL`.

## Trusted authorization

The caller submits a strict `sdb.capability.task/1` Task Pack and an `approval_ref`. There is no CLI option for a caller-provided authorization file or `approved: true` assertion.

The router resolves the reference in `registry/capability_execution_approvals.yaml`. The store is accepted only when Git tracks it and the worktree copy exactly matches the committed copy. Each record binds:

- canonical SHA-256 of the complete Task Pack;
- capability and lane;
- canonical allowed write roots;
- `nonproduction: true`;
- issuer;
- issue and expiry timestamps;
- nonce used by a one-time replay marker.

A replay marker is created by no-follow directory-FD traversal in the parent-only `.git/sdb-capability-approval-replay` state directory before executor launch. The sandbox hides `.git`, so the child cannot remove or alter markers. Unknown, modified, expired, not-yet-valid, replayed, wrong-task, wrong-lane, or changed-root authorization fails closed.

### Trust model and limitation

This is a committed-configuration trust model, not a cryptographically signed approval service. The trust root is local Git history plus control of who may create the trusted commit. A caller who can only alter a task or working-tree approval file cannot forge approval; a principal who can rewrite trusted Git history can. Production adoption therefore requires protected branch/review controls or replacement with a signed external approval service.

The Hermes executable is owned by the expected local UID and is mode 0755. The router rejects symlinks and group/world mutability, checks its pinned digest immediately before launch, validates and retains the same opened inode, and executes through that descriptor. This does not make the file immutable to a concurrently compromised same-UID host process; that host threat is outside the Bubblewrap child boundary. A root-owned immutable/package-verified executable would provide a stronger production trust root.

The included `C1-03-D6D8-NONPROD-20261121` record is the user-approved, short-lived nonproduction configuration candidate for this change. Since this task explicitly forbids committing, the production loader intentionally rejects that file while it remains untracked. Its canonical task is:

```json
{"schema":"sdb.capability.task/1","capability_id":"BE-SP-03","lane":"backend","goal":"Deterministic nonproduction C1-03 authorization and challenge verification smoke test; request no tools and make no repository writes.","requested_write_paths":[]}
```

Canonical task SHA-256: `33b8bce0bda2e20c4522c2dfc7402ff38d3faa668fcb5c3bf39a3266f6f359c6`.

## Routing registry

`registry/capability_pilot.yaml` is trusted routing configuration. It fixes the executable and profiles, and rejects any other lane inventory:

- frontend: exactly `FE-SP-01` through `FE-SP-12`, profile `cc-frontend`;
- backend: exactly `BE-SP-01` through `BE-SP-14`, profile `cc-builder`;
- executable: pinned Hermes adapter only.

Task payloads cannot provide an executable, argv, profile, environment, or evidence bypass.

## OS sandbox

The launcher validates and pins:

- Hermes: `/home/anashadi/.local/bin/hermes`, regular non-symlink file, UID 1000, mode 0755 with no group/other write bit, SHA-256 `ce029ccc2679fb234364effdc67971c01ea4b8920866793282b53b61c9a57e2f`;
- Bubblewrap: `/usr/bin/bwrap`, root-owned regular non-symlink file, mode 0755 with no group/other write bit.

The sandbox uses Bubblewrap with an **allowlisted mount namespace**, not a bind of host `/`. The child sees only: read-only `/usr` (plus `/bin`, `/sbin`, `/lib*` symlinks), a fixed short list of `/etc` entries (resolver, TLS roots, passwd/group, nsswitch, ld cache), a private `/tmp`, `/proc`, `/dev`, the pinned Hermes runtime (`~/.hermes/hermes-agent`, `~/.hermes/tools`, read-only, with runtime `.env`/`.envrc` shadowed by `/dev/null`), the active profile as a temporary overlay, the repository (read-only, from a no-follow directory FD) and the approved writable roots. `/run`, `/var`, `/root`, `/home` (except the mount parents), `~/.ssh`, `~/.gnupg`, other Hermes profiles, `~/.hermes/auth.json`, and host unix sockets (docker, dbus, systemd-user, gcr/ssh) are absent from the namespace, so `connect()` to them fails. Every authorized writable directory must already exist, be canonical and symlink-free, and is supplied from an open directory FD using `--bind-fd`. `.git` paths are rejected, and the child sees an empty read-only mount at `.git`. Evidence is not writable from the child; the parent writes it after verification.

Approvals are additionally constrained: roots `scripts`, `registry`, `runs` are refused, lifetime is capped at 31 days, and the approval store and registry are parsed from the committed Git blob (`git show HEAD:path`) with a clean git environment by a YAML loader that rejects duplicate keys and aliases. Files flagged `assume-unchanged`/`skip-worktree` count as dirty. The consumption of the single-use approval happens only after executor, sandbox, profile and roots validated.

The pinned launcher is a two-line `sh` stub; the real entrypoint it `exec`s (`~/.hermes/hermes-agent/.hermes/bin/hermes`, SHA-256 `08bf3a4bade11a1af7d8a7ce2056aaad81d479343c039ac6ab545732c523a5c2`) is pinned and verified as well. The Python runtime, packages and the active profile content are **not** hashed (see limitations).

The profile overlay is writable but ephemeral; the active profile's own credentials (`auth.json`) remain readable by design, because Hermes cannot run without them.

Network policy is explicit: the namespace shares the network because Hermes requires its configured LLM endpoint. This is not network isolation or egress filtering; loopback services (e.g. the Command Deck on 127.0.0.1:8484), abstract unix sockets of the host network namespace (e.g. X11/dbus abstract names) and the internet stay reachable, so the active profile credential could be exfiltrated by a hostile executor. Egress filtering is a precondition for any production use. The controlled smoke Task Pack requests no arbitrary tools. Stronger egress policy is outside this repository-only scope.

The fixed production Hermes argv is:

```text
/home/anashadi/.local/bin/hermes -p PROFILE chat --query-file - --oneshot --quiet --format text --source tool --run-budget N
```

`--yolo` is never used.

## Revision and result verification

Before launch, the parent captures HEAD plus SHA-256, tracked/dirty state, and presence for protected implementation files. Dirty and untracked implementation files are represented explicitly. The same binding is captured after execution; any change forces `FAIL` even if the child returned a valid result.

The parent generates a random runtime nonce and supplies the canonical task digest and capability. The executor must return exactly one `sdb.capability.result/1` object with:

- the same capability ID;
- an allowlisted verdict;
- `sha256(nonce + "/" + capability_id + "/" + task_digest)`.

Exit status is process status only. Empty, arbitrary, malformed, extra-field, forged, wrong-capability, non-allowlisted, timed-out, or oversized output fails. No test pass is synthesized from exit code 0.

## Mandatory evidence

The public flow always attempts evidence creation, including failed executor results. Failure to validate or write evidence makes the CLI fail.

Evidence uses `sdb.capability.evidence/1`, is validated by the BE-SP-12 evidence validator before writing, includes an integrity digest, and remains `AGENT_REPORTED`, `NOT_REVIEWED`, and `NOT_AUTHORIZED`. Only a verified `PASS_VERIFIED_SUBSCOPE` is promoted to `INTEGRATION_TESTED_NONPRODUCTION`; failed results are recorded as `FAIL` or `BLOCKED` and cannot create positive evidence.

The parent writes invocation and evidence files through no-follow `openat` directory-FD traversal. A symlink in any parent component fails before write. Invocation artifacts persist output length and SHA-256 only. The excerpt fields hold a `[WITHHELD bytes=N sha256=...]` marker: denylist redaction cannot be made complete, so no raw stdout/stderr content is ever persisted.

## Verification coverage

`tests/test_capability_routing.py` uses a controlled executable only through the private programmatic `for_test` seam. It exercises trusted-store modification/forgery/expiry/wrong-task/replay, replay/evidence parent symlinks, exact lane split, no-write, hidden `.git`, and approved-root Bubblewrap behavior, strict challenge results, pre/post revision binding including dirty/untracked files, output overflow, descendant timeout, mandatory positive/failure evidence, and pinned production paths.

Regression tests also probe, from inside the real sandbox, that host sockets, `~/.ssh`, other profiles, `auth.json` and the runtime `.env` are not reachable, plus duplicate-YAML-key, TTL, protected-root, index-flag and caller-`GIT_*` cases, oversized goals, and signal exit codes.

No test invokes live Hermes, a customer job, a worker, or a service.


## Accepted limitations (honest labels)

| Item | Status |
|---|---|
| Result challenge (`sha256(nonce/cap/digest)`) proves the executor read the prompt, not that it did the work. | Evidence stays `AGENT_REPORTED`/`INFORMATIONAL_ONLY`; positive verdict is `INTEGRATION_TESTED_NONPRODUCTION` at most. |
| `issuer` is a free string; trust root is local Git history, not a signature. | Needs protected branch / signed approval before production. |
| `execute()` accepts an `ApprovalRecord` object; provenance is by construction convention, not a capability token. | Public CLI only goes through the trusted loader. |
| Shared network, loopback reachable. | Egress filter required before production. |
| Python runtime/packages/profile content not hashed. | Needs root-owned vendored runtime for production. |
| Live Hermes inside the new sandbox was not executed (prohibited). | Needs one authorized smoke run after commit. |
