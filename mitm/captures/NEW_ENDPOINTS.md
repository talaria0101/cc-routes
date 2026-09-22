# Runtime-observed endpoints missing from static tables

Bundle: `/tmp/mitm-work/cli-1.62.1/package/dist/cli.mjs`.
Observed 30 unique endpoints (178 events); 1 not covered by static/spec tables.

## `POST github.com/login/device/code`
- hits: 1, statuses: [200]
- in static bundle: None, in prior spec: None, 401 seen: False
- runs: login copilot
