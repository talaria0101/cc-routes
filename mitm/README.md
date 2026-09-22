# mitm/ — drive the real CLI through a capture harness

`cc_routes.py` maps endpoints statically. This harness runs the actual
shipping CLI and records every endpoint it touches, so anything the
static sweep misses (dynamic URLs, third-party OAuth, lazy installs)
shows up with proof.

## How it works

- `hook.mjs` — transparent capture shim, loaded with
  `bun --preload` (and `NODE_OPTIONS=--import` so hooked `node`
  children like `npm` are captured in the same log). Wraps
  `globalThis.fetch` + `http/https.request` (responses sampled via
  `clone()`, CLI traffic untouched) and logs `child_process` spawns.
  Auth material, API keys, and OAuth device artifacts are redacted
  before writing. Stdlib-only, JSONL to `$CC_MITM_LOG`.
- `netlog.c` → `netlog.so` — LD_PRELOAD egress tap (C, no deps):
  logs DNS intent, real connect peers, scans handshakes for
  `CONNECT host:port` lines + TLS SNI, and interposes `execve` to
  log every spawn (path + argv) at OS level — catching non-node
  children (sh, git, tput, npm, node) the JS hook cannot see.
  Covers every binary with zero sockets bound. Built automatically
  by `drive.py` when gcc exists; per-run logs to `*.net.log`.
- `drive.py` — version-pinned setup (resolves latest from the npm
  registry, strips build-time-only `devDependencies`, installs prod
  deps, bootstraps portable npm if needed) then drives a 22-command
  matrix with isolated HOME, closed stdin, per-command timeouts.
- `analyze.py` — unique `(method, host, path)` table, spawn table
  (JS-hook spawns merged with OS-level `execve` rows),
  tap-host merge (`tap-hosts.json`) against a `KNOWN_HOSTS` allowlist
  (unknown hosts are a recorded verdict, never a blocked refresh),
  and a diff against the static bundle route table + prior spec:
  `captures/NEW_ENDPOINTS.md`. Validation floors refuse to overwrite
  curated outputs on empty/partial captures (exit 2, `--force`
  overrides); all writes are atomic (pid-tmp + fsync + rename).
  `analyze.py --report-only` re-renders reports from committed JSONs
  (fresh-clone safe, no network).
- `pty_login.py` — experimental interactive-login driver (needs a pty;
  the sandbox has none, so it is documented, not run).

## Sandbox constraints (honest limits)

- No TCP `bind()` in the sandbox, so a classic TLS-intercepting proxy
  is impossible here. The in-process hook observes the same plaintext
  (pre-TLS request, post-TLS response) with zero behavior change.
- No pty devices, so ink raw-mode flows (`login`, `-p` sessions) die
  before interaction. Auth-gated API calls are recorded as 401s; the
  harness never completes an auth flow (the one issued GitHub device
  code expired unused).
- The published tarball is not `npm install`-able as-is: its
  `devDependencies` reference private `@commandcode/*` packages that
  404 on the public registry. They are build-time only (the bundle
  imports none at runtime), so setup strips them.

## What driving the CLI exposed (v1.62.1, 22-run matrix; see captures/REPORT.md for counts)

New vs the static sweep (`captures/NEW_ENDPOINTS.md`):

- `POST github.com/login/device/code` → 200. `cmd login copilot`
  lazily installs `@byokkit/cmd-provider-copilot` from the public
  registry, then starts a GitHub device flow. Third-party auth surface
  the static route regexes cannot see (dynamic host).
- Provider plugin channel: `@byokkit/*` packages install on demand
  into `~/.commandcode/cache/providers/` (npm registry traffic via a
  hooked npm child). Supply-chain-relevant: `login <provider>` pulls
  and executes third-party install code paths.
- `login anthropic|openai` stop at the browser-confirm prompt: no
  network beyond the startup `whoami`. Default `login` (API-key flow)
  likewise never gets past the ink crash headless.

Confirmed by runtime (already in spec, now with proof):

- Every command starts with `npm view command-code versions --json`
  (update check via subprocess) and `git branch --show-current`.
  `info` additionally probes the terminal/shell (`tput` ×8,
  `ps -p <pid>`, `cmd --version`).
- `GET /alpha/whoami` → 401 is the startup auth check on most
  commands. `status`/`whoami` do a local auth-file check only.
  `-p` without auth exits 3 with no further traffic.
- Telemetry (`/alpha/lifecycle-events`, axiom) never fires
  unauthenticated: all lifecycle tracking is gated on an auth key.

## Reproduce

```sh
python3 drive.py --work ./work --captures ./captures
python3 analyze.py --captures ./captures --spec ../spec/api-spec.json
```

Raw `*.jsonl` + stdout/stderr logs stay local (gitignored); curated
`manifest.json`, `endpoints.json`, `spawns.json`, `NEW_ENDPOINTS.md`
plus human-readable `REPORT.md` / `REPORT.txt` (auto-written by
`analyze.py` on every run) are committed.
