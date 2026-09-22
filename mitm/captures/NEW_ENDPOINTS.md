# Runtime-observed endpoints missing from static tables

Bundle: `/tmp/mitm-work/cli-1.62.1/package/dist/cli.mjs`.
Observed 30 unique endpoints (174 events); 1 not covered by static/spec tables.

## `POST github.com/login/device/code`
- hits: 1, statuses: [200]
- in static bundle: None, in prior spec: None, 401 seen: False
- runs: login copilot

## Tap host allowlist verdict

- [ok] `127.0.0.1` hits=1 via dns (local-only/BYOK target (no listener here))
- [UNKNOWN] `api.axiom.co` hits=14 via dns (NOT IN ALLOWLIST)
- [ok] `api.commandcode.ai` hits=31 via connect_line,sni (provider API (bundle API_BASE_URLS + docs))
- [ok] `github.com` hits=2 via connect_line,sni (copilot provider GitHub device flow (POST /login/device/code, observed live))
- [UNKNOWN] `ingestion.claicode.com` hits=14 via dns (NOT IN ALLOWLIST)
- [ok] `registry.npmjs.org` hits=114 via connect_line,sni (update check via npm child; @byokkit provider lazy-installs)

Hook blind spots (tap saw host, hook saw no URL):
- `127.0.0.1`
- `api.axiom.co`
- `ingestion.claicode.com`
