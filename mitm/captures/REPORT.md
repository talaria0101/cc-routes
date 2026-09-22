# CLI drive report (v1.62.1, bun runner)

22 runs, 175 captured events, 30 unique endpoints, 1 new surface. Window (UTC): 2026-09-22T10:46:22Z .. 2026-09-22T10:46:59Z.
Bundle driven: `/tmp/mitm-work/cli-1.62.1/package/dist/cli.mjs`.

## Runs

| Run | Exit | Time | Events |
|---|---|---|---|
| `cmd --help` | 0 | 0.6s | 4 |
| `cmd --version` | 0 | 0.5s | 4 |
| `cmd --list-models` | 0 | 2.8s | 10 |
| `cmd info` | 0 | 2.8s | 20 |
| `cmd status` | 1 | 0.5s | 4 |
| `cmd whoami` | 1 | 0.5s | 4 |
| `cmd update --check-only` | 0 | 2.8s | 10 |
| `cmd login` | 0 | 2.8s | 30 |
| `cmd auth login` | 1 | 0.6s | 4 |
| `cmd login copilot` | 0 | 6.7s | 66 |
| `cmd login anthropic` | 0 | 2.8s | 10 |
| `cmd login openai` | 0 | 2.8s | 9 |
| `cmd -m no-such-model-xyz -p hi` | 1 | 0.5s | 4 |
| `cmd -p say ok --no-session` | 3 | 0.6s | 4 |
| `cmd taste --help` | 0 | 0.5s | 4 |
| `cmd mcp --help` | 0 | 0.5s | 4 |
| `cmd skills --help` | 0 | 0.5s | 4 |
| `cmd mods --help` | 0 | 0.5s | 4 |
| `cmd mcp list` | 0 | 4.0s | 10 |
| `cmd mods list` | 0 | 2.9s | 10 |
| `cmd skills list` | 0 | 0.5s | 4 |
| `cmd taste list` | 0 | 0.6s | 8 |

## Endpoints observed

| Endpoint | Hits | Statuses | Seen in |
|---|---|---|---|
| `GET api.commandcode.ai/alpha/whoami` | 10 | 401 | `cmd --list-models`, `cmd info`, `cmd login`, `cmd login anthropic` |
| `GET registry.npmjs.org/@ai-sdk%2fgateway` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@ai-sdk%2fopenai` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@ai-sdk%2fprovider` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@ai-sdk%2fprovider-utils` | 2 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@ai-sdk/gateway/-/gateway-3.0.197.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@ai-sdk/openai/-/openai-3.0.115.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@ai-sdk/provider-utils/-/provider-utils-4.0.52.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@ai-sdk/provider/-/provider-3.0.16.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@byokkit%2fcmd-provider-copilot` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@byokkit/cmd-provider-copilot/-/cmd-provider-copilot-0.1.1.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@opentelemetry%2fapi` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@opentelemetry/api/-/api-1.9.1.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@standard-schema%2fspec` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@standard-schema/spec/-/spec-1.1.0.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@vercel%2foidc` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/@vercel/oidc/-/oidc-3.2.0.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/ai` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/ai/-/ai-6.0.287.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/command-code` | 21 | 200 | `cmd --help`, `cmd --list-models`, `cmd --version`, `cmd -m no-such-model-xyz -p hi` |
| `GET registry.npmjs.org/eventsource-parser` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/eventsource-parser/-/eventsource-parser-3.1.1.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/json-schema` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/json-schema/-/json-schema-0.4.0.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/npm` | 19 | 200 | `cmd --help`, `cmd --list-models`, `cmd --version`, `cmd -m no-such-model-xyz -p hi` |
| `GET registry.npmjs.org/undici` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/undici/-/undici-6.28.1.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/zod` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/zod/-/zod-4.6.5.tgz` | 1 | 200 | `cmd login copilot` |
| `POST github.com/login/device/code` | 1 | 200 | `cmd login copilot` |

## Subprocesses spawned

| Call | Command | Hits | Runs |
|---|---|---|---|
| exec | `npm view command-code versions --json` | 22 | --help, --list-models, --version |
| execFileSync | `tput` | 28 | info, login |
| execSync | `cmd --version` | 1 | info |
| execSync | `git branch --show-current` | 22 | --help, --list-models, --version |
| execSync | `ps -p 865 -o comm=` | 1 | info |
| execve | `/bin/sh /bin/sh -c cmd --version` | 1 | info |
| execve | `/bin/sh /bin/sh -c git branch --show-current` | 22 | --help, --list-models, --version |
| execve | `/bin/sh /bin/sh -c lock='/tmp/mitm-work/home-09/.commandcode/cache/providers/@by` | 1 | login copilot |
| execve | `/bin/sh /bin/sh -c npm view command-code versions --json` | 22 | --help, --list-models, --version |
| execve | `/bin/sh /bin/sh -c ps -p 865 -o comm=` | 1 | info |
| execve | `/home/qaidvoid/.local/share/mise/installs/node/26.8.1/bin/node /home/qaidvoid/.l` | 23 | --help, --list-models, --version |
| execve | `/tmp/mitm-work/bin/npm npm install @byokkit/cmd-provider-copilot@0.1.1` | 1 | login copilot |
| execve | `/tmp/mitm-work/bin/npm npm view command-code` | 22 | --help, --list-models, --version |
| execve | `/usr/bin/git git branch --show-current` | 22 | --help, --list-models, --version |
| execve | `/usr/bin/mkdir mkdir /tmp/mitm-work/home-09/.commandcode/cache/providers/@byokki` | 1 | login copilot |
| execve | `/usr/bin/ps ps -p 865` | 1 | info |
| execve | `/usr/bin/rm rm -f /tmp/mitm-work/home-09/.commandcode/cache/providers/@byokkit/c` | 1 | login copilot |
| execve | `/usr/bin/rm rm -rf /tmp/mitm-work/home-09/.commandcode/cache/providers/@byokkit/` | 1 | login copilot |
| execve | `/usr/bin/tput tput cols` | 14 | info, login |
| execve | `/usr/bin/tput tput lines` | 14 | info, login |
| spawn | `lock='/tmp/mitm-work/home-09/.commandcode/cache/providers/@byokkit/cmd-provider-` | 1 | login copilot |

## New surface (not in static tables)

- `POST github.com/login/device/code` (hits 1, statuses [200], runs: login copilot)

## Limits

- No TCP bind in the sandbox: capture is in-process (`hook.mjs`), same plaintext visibility as a TLS proxy.
- No ptys: ink raw-mode flows (`login`, `-p` sessions) die before interaction; auth-gated calls recorded as 401s.
- Raw logs (`*.jsonl`, stdout/stderr) stay local; only curated summaries are committed.

## Reproduce

```sh
python3 drive.py --work ./work --captures ./captures
python3 analyze.py --captures ./captures --spec ../spec/api-spec.json
```


## Tap host allowlist verdict

- [ok] `127.0.0.1` hits=1 via dns (local-only/BYOK target (no listener here))
- [ok] `api.axiom.co` hits=13 via dns (telemetry backend (bundle AXIOM_ENDPOINT; DNS-only without auth key, observed live))
- [ok] `api.commandcode.ai` hits=33 via connect_line,sni (provider API (bundle API_BASE_URLS + docs))
- [ok] `github.com` hits=2 via connect_line,sni (copilot provider GitHub device flow (POST /login/device/code, observed live))
- [ok] `ingestion.claicode.com` hits=13 via dns (telemetry backend (bundle ingestion URL; DNS-only without auth key, observed live))
- [ok] `registry.npmjs.org` hits=114 via connect_line,sni (update check via npm child; @byokkit provider lazy-installs)

Verdict: PASS - no unknown hosts.
