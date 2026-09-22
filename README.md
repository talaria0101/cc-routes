# cc-routes

Drift-proof route finder + fresh API spec for Command Code.
No pinned endpoint list. Every run re-discovers routes from first-party
sources, probes them live, prints the ones carrying model / price / deal
data, and writes `spec/api-spec.json` answering what we care about.

## What we learned from the docs + CLI reference (2026-09-22)

Studied: `commandcode.ai/docs` (all 60 nav pages), CLI models reference
(`docs/reference/cli/models`), CLI reference (`docs/reference/cli`),
pricing-limits, provider API page, `/models`, `/pricing`, the website JS
bundles, and CLI v1.62.1 (`dist/cli.mjs` from the npm registry).

- Provider API base is `https://api.commandcode.ai`. Five routes:
  `POST /provider/v1/chat/completions` (OpenAI),
  `POST /provider/v1/responses` (OpenAI Responses; open + OpenAI models),
  `POST /provider/v1/messages` (Anthropic; Claude models only),
  `GET /provider/v1/models` (live model list),
  `POST /provider/v1/systemone` (decision model `typesafe/jev`,
  never streams, not drivable via `/model`).
- Each entry in the models list carries `supported_endpoints`, so check
  there before picking an endpoint. Claude = `/messages` only.
- CLI: `cmd --list-models` prints the same registry that backs the docs
  tables and the `/model` picker. `--model` matching is case-insensitive,
  full id or short name after `/`. Default model is
  `deepseek/deepseek-v4-flash`.
- Website bundles carry their own machine-readable truth: `deals.js`
  (deal ids, multipliers, model ids, expiry), `constants.js` (full
  INTERNAL/ALPHA/BETA route tables, per-provider per-token costs,
  plan gating), `plan-tiers.js`, `goat-plan-public.js` (per-model
  allowances). The harness parses these live because the filenames are
  content-hashed and drift.

## Answers right now (see spec/api-spec.json for the full tables)

- Models available: 76 via unauth `GET /provider/v1/models`.
- Prices: per-1M-tokens input/output/cache-read/write in spec
  (`prices_per_1m_usd`, 80 rows scraped from the pricing-limits table).
- Deals now: 8 deal objects in spec (`deals_now`) with multipliers and
  model ids. Live ones include MiMo V2.5/V2.5-Pro (98-99% off),
  MiniMax M3 2x, Grok 4.7 40% off (ends Sep 27 2026).
- Free models: `poolside/laguna-s-2.1-free` (free while capacity lasts),
  `inclusionai/ling-3.0-flash-sante:free` (free, 100 req/day).
  Contributor editions (Muse Spark 1.2/1.3 Contributor) are ~95% off,
  not free. Free tiers still need $1 of credits to start a session.
- Auth: ONLY `/provider/v1/models` works without auth (200, CORS `*`).
  Chat/responses/messages/systemone all return 401 without a Bearer key,
  as do `/internal/models` and `/alpha/whoami`. No free inference
  without an account.

## Known drift (why this harness exists)

- `ling-3.0-flash-free` deal (expired Aug 2 2026, model offline) is still
  shipped in `deals.js` but gone from the live models list.
- `qwen-3.7-max-2x-usage` deal (expired Jun 22 2026) is still shipped in
  `deals.js`.
- The CLI bundle contains hidden free variants (`minimax-m3-free`,
  `longcat-2.0:free`, `tencent/Hy3` badge free) not present in the live
  list. Trust the live probe, not the bundle.

## Usage

```sh
python3 cc_routes.py                      # full run: discover + probe + spec
python3 cc_routes.py --spec-only          # rebuild spec from corpus/
python3 cc_routes.py --no-fetch-sources   # re-probe, reuse discovery snapshot
python3 cc_routes.py --out /tmp/spec.json --corpus /tmp/corpus
```

Stdlib only. Gentle by design: sequential requests, short timeouts, no
auth, no retries. Quota instruments stop at the wall.

## Layout

- `cc_routes.py` - the instrument (discover, probe, classify, emit spec)
- `spec/api-spec.json` - latest generated spec (committed each run)
- `corpus/` - small snapshots (`discovery.json`, `probes.json`,
  `provider-models.json`); large fetch cache is gitignored
