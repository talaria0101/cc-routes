# CLI drive report (v1.62.1, bun runner)

22 runs, 178 captured events, 30 unique endpoints, 1 new surface. Window (UTC): 2026-09-22T09:19:01Z .. 2026-09-22T09:19:42Z.
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
| `cmd login` | 0 | 3.0s | 30 |
| `cmd auth login` | 1 | 0.5s | 4 |
| `cmd login copilot` | 0 | 10.1s | 67 |
| `cmd login anthropic` | 0 | 2.9s | 10 |
| `cmd login openai` | 0 | 2.9s | 10 |
| `cmd -m no-such-model-xyz -p hi` | 1 | 0.6s | 4 |
| `cmd -p say ok --no-session` | 3 | 0.5s | 4 |
| `cmd taste --help` | 0 | 0.5s | 4 |
| `cmd mcp --help` | 0 | 0.5s | 4 |
| `cmd skills --help` | 0 | 0.5s | 4 |
| `cmd mods --help` | 0 | 0.5s | 4 |
| `cmd mcp list` | 0 | 2.7s | 9 |
| `cmd mods list` | 0 | 4.1s | 10 |
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
| `GET registry.npmjs.org/command-code` | 22 | 200 | `cmd --help`, `cmd --list-models`, `cmd --version`, `cmd -m no-such-model-xyz -p hi` |
| `GET registry.npmjs.org/eventsource-parser` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/eventsource-parser/-/eventsource-parser-3.1.1.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/json-schema` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/json-schema/-/json-schema-0.4.0.tgz` | 1 | 200 | `cmd login copilot` |
| `GET registry.npmjs.org/npm` | 21 | 200 | `cmd --help`, `cmd --list-models`, `cmd --version`, `cmd -m no-such-model-xyz -p hi` |
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
| execSync | `ps -p 3702 -o comm=` | 1 | info |
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
