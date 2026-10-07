<!-- Digabung dari Hermes Super Development Suite v1.0.0 (skill `evidence-normalizer` generik, 2026-09-16)
     untuk menghapus tabrakan nama skill: Hermes tidak bisa memuat dua skill bernama sama. -->

# Common Evidence Schema

Normalize every capture to:
- project: name, platform, target version, authorization scope
- screens: id, viewport/device, screenshot, element tree, actions, transitions
- assets: path/url, type, dimensions/hash if available, licensing note
- styles: tokens, fonts, colors, spacing, responsive rules
- runtime: console, errors, timing, process metadata
- network: observed endpoints, methods, schemas, status codes, websocket events
- verification: visual, structure, behavior, tests, unsupported/private behavior

Never store secrets, access tokens, cookies, credentials, private-user data, or
proprietary backend source in evidence unless the user explicitly owns it and
storage is required.

## Redaction rules
Before writing any evidence artifact:
1. Drop `Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, `*-token` headers
   and any query parameter whose name matches `token|key|secret|sig|auth`.
2. Replace captured credentials with `<redacted>` — never with a partial value,
   and never keep the original in a sibling `*.raw` file inside the repo.
3. Strip absolute home paths from screenshots' metadata before sharing.
4. Record *that* an endpoint was observed, not the response body, unless the
   response is public and the user owns the target.
5. Mark every surface the capture could not legitimately reach as
   `bounded evidence`, never as inferred behavior presented as fact.
## Input lintas platform (dari suite)

Browser trace, HAR (redaksi dulu; `*.har` di-gitignore), screenshot, DOM/UI tree, dump Appium,

laporan MobSF, tree Windows UIA, log, dan metadata codebase. Path & ID diubah ke referensi relatif-proyek

yang stabil; aset & screenshot dideduplikasi berdasarkan hash.
