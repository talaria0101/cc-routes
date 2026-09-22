# Runtime-observed endpoints missing from static tables

Bundle: `/tmp/mitm-work/cli-1.62.1/package/dist/cli.mjs`.
Observed 30 unique endpoints (177 events); 1 not covered by static/spec tables.

## `POST github.com/login/device/code`
- hits: 1, statuses: [200]
- in static bundle: None, in prior spec: None, 401 seen: False
- runs: login copilot

## Tap host allowlist verdict

- [ok] `127.0.0.1` hits=1 via dns (local-only/BYOK target (no listener here))
- [ok] `api.axiom.co` hits=13 via dns (telemetry backend (bundle AXIOM_ENDPOINT; DNS-only without auth key, observed live))
- [ok] `api.commandcode.ai` hits=33 via connect_line,sni (provider API (bundle API_BASE_URLS + docs))
- [ok] `github.com` hits=2 via connect_line,sni (copilot provider GitHub device flow (POST /login/device/code, observed live))
- [ok] `ingestion.claicode.com` hits=13 via dns (telemetry backend (bundle ingestion URL; DNS-only without auth key, observed live))
- [ok] `registry.npmjs.org` hits=114 via connect_line,sni (update check via npm child; @byokkit provider lazy-installs)

Hook blind spots (tap saw host, hook saw no URL):
- `127.0.0.1`
- `api.axiom.co`
- `ingestion.claicode.com`
