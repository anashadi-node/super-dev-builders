# Evidence Schema V2

Migrasi dari V1 (`normalized/screens.json`, `actions.json`, `assets.json`, `network.json`, `components.json`, `verification.json`)
dengan tambahan wajib dari taxonomy V2.2: `status`, `confidence`, `redaction_status`.

## Metadata wajib setiap record
```json
{"provenance":"capture-run-id","captured_at":"ISO-8601","redaction_status":"clean|redacted|blocked",
 "status":"FACT|INFERRED|UNKNOWN|OUT_OF_SCOPE","confidence":null}
```

## screens.json
```json
[{"id":"home-desktop-1440","url":"/","viewport":{"w":1440,"h":900},
  "screenshot":"evidence/<target>/home-desktop-1440.png","dom":"evidence/<target>/home-desktop-1440.html",
  "provenance":"run-2026-10-04-a","captured_at":"2026-10-04T09:10:00+07:00",
  "redaction_status":"clean","status":"FACT","confidence":null}]
```

## actions.json
```json
[{"id":"login-submit","from":"login","to":"dashboard",
  "steps":[{"type":"click","selector":"button[type=submit]"}],"expected":"dashboard visible",
  "status":"FACT","confidence":null,"inferred":false,"provenance":"run-2026-10-04-a"}]
```

## assets.json
```json
[{"id":"logo","path":"assets/logo.svg","hash":"sha256:...",
  "license":"authorized|open|substituted","source":"observed","status":"FACT"}]
```

## network.json
```json
[{"id":"get-products","method":"GET","path":"/api/products","status_code":200,
  "request_schema":{},"response_schema":{},"auth":"required-redacted","status":"FACT","confidence":null}]
```

## components.json
```json
[{"name":"ProductCard","evidence":["screen:home"],"props":["title","price","image"],
  "states":["default","hover","loading"],"status":"OBSERVED","confidence":null}]
```

## verification.json
```json
[{"dimension":"visual","viewport":"desktop-1440","coverage":0.82,
  "result":"diff","evidence":"verification/<target>/visual/desktop-1440-diff.png","status":"FACT"}]
```

## Aturan validasi (dijalankan `scripts/gate_check.py --evidence`)
- Record tanpa `provenance`/`captured_at`/`status` => invalid.
- `status: INFERRED` tanpa `confidence` numerik => invalid.
- `status: UNKNOWN` dengan isi spekulatif => invalid (harus kosong + catatan).
- Adanya pola credential/token/cookie pada nilai => invalid + wajib redaksi ulang.
