# Command Code API spec (human report)

Generated (UTC): 2026-09-22T10:44:50Z. Machine-readable twin: `spec/api-spec.json`.
Sources re-resolved this run: 195 sitemap URLs, 7 docs paths, 100 website JS assets, CLI 1.62.1.

## TL;DR

- Models available: **76** (live `GET /provider/v1/models`, no auth needed).
- Free models: `poolside/laguna-s-2.1-free`, `inclusionai/ling-3.0-flash-sante:free`. Free requests still need $1 of credits to start a session.
- Deals in the website bundle: 8 total, 6 live.
- Inference endpoints (chat, responses, messages, systemone) all require a Bearer key (401 without one). No free inference without an account.

## Models available

| Model id | Name | Context | Endpoints | Free |
|---|---|---|---|---|
| `claude-sonnet-5` | Claude Sonnet 5 | 1M | `/messages` |  |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | 1M | `/messages` |  |
| `claude-fable-5-1` | Claude Fable 5.1 | 1M | `/messages` |  |
| `claude-fable-5` | Claude Fable 5 | 1M | `/messages` |  |
| `claude-opus-5` | Claude Opus 5 | 1M | `/messages` |  |
| `claude-opus-4-8` | Claude Opus 4.8 | 1M | `/messages` |  |
| `claude-opus-4-7` | Claude Opus 4.7 | 1M | `/messages` |  |
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 | 200K | `/messages` |  |
| `gpt-5.6-sol` | GPT-5.6 Sol | 1.1M | `/chat/completions`, `/responses` |  |
| `gpt-5.6-terra` | GPT-5.6 Terra | 1.1M | `/chat/completions`, `/responses` |  |
| `gpt-5.6-luna` | GPT-5.6 Luna | 1.1M | `/chat/completions`, `/responses` |  |
| `gpt-5.5` | GPT-5.5 | 400K | `/chat/completions`, `/responses` |  |
| `gpt-5.4` | GPT-5.4 | 400K | `/chat/completions`, `/responses` |  |
| `gpt-5.3-codex` | GPT-5.3 Codex | 400K | `/chat/completions`, `/responses` |  |
| `gpt-5.4-mini` | GPT-5.4 Mini | 400K | `/chat/completions`, `/responses` |  |
| `deepseek/deepseek-v4-pro` | DeepSeek V4 Pro (latest) | 1M | `/chat/completions`, `/responses` |  |
| `deepseek/deepseek-v4-flash` | DeepSeek V4 Flash (latest) | 1M | `/chat/completions`, `/responses` |  |
| `deepseek/deepseek-v4-flash-vision-exp` | DeepSeek V4 Flash Vision (exp) | 1M | `/chat/completions`, `/responses` |  |
| `deepseek/deepseek-v4-flash-fast` | DeepSeek V4 Flash Fast | 1M | `/chat/completions` |  |
| `deepseek/deepseek-v4.1-flash` | DeepSeek V4.1 Flash | 1M | `/chat/completions`, `/responses` |  |
| `moonshotai/Kimi-K3` | Kimi K3 | 1M | `/chat/completions`, `/responses` |  |
| `moonshotai/Kimi-K2.7-Code` | Kimi K2.7 Code | 256K | `/chat/completions`, `/responses` |  |
| `moonshotai/Kimi-K2.7-Code-Highspeed` | Kimi K2.7 Code HighSpeed | 262K | `/chat/completions`, `/responses` |  |
| `moonshotai/Kimi-K2.6` | Kimi K2.6 | 256K | `/chat/completions`, `/responses` |  |
| `moonshotai/Kimi-K2.5` | Kimi K2.5 | 256K | `/chat/completions`, `/responses` |  |
| `z-ai/glm-5.3-flash` | GLM-5.3 Flash | 1.0M | `/chat/completions`, `/responses` |  |
| `z-ai/glm-5.3-flashx` | GLM-5.3 FlashX | 1M | `/chat/completions`, `/responses` |  |
| `zai-org/GLM-5.3` | GLM-5.3 | 1M | `/chat/completions`, `/responses` |  |
| `zai-org/GLM-5.2` | GLM-5.2 | 1M | `/chat/completions`, `/responses` |  |
| `zai-org/GLM-5.2-Fast` | GLM-5.2 Fast | 1M | `/chat/completions`, `/responses` |  |
| `zai-org/GLM-5.1` | GLM-5.1 | 200K | `/chat/completions`, `/responses` |  |
| `zai-org/GLM-5` | GLM-5 | 200K | `/chat/completions`, `/responses` |  |
| `MiniMaxAI/MiniMax-M3` | MiniMax M3 | 1M | `/chat/completions`, `/responses` |  |
| `MiniMaxAI/MiniMax-M2.7` | MiniMax M2.7 | 200K | `/chat/completions`, `/responses` |  |
| `MiniMaxAI/MiniMax-M2.5` | MiniMax M2.5 | 200K | `/chat/completions`, `/responses` |  |
| `xiaomi/mimo-v2.6-pro` | MiMo V2.6 Pro | 1.0M | `/chat/completions`, `/responses` |  |
| `xiaomi/mimo-v2.6-pro-ultraspeed` | MiMo V2.6 Pro UltraSpeed | 1.0M | `/chat/completions`, `/responses` |  |
| `xiaomi/mimo-v2.6-flash` | MiMo V2.6 Flash | 1.0M | `/chat/completions`, `/responses` |  |
| `xiaomi/mimo-v2.5-pro` | MiMo V2.5 Pro | 1M | `/chat/completions`, `/responses` |  |
| `xiaomi/mimo-v2.5` | MiMo V2.5 | 1M | `/chat/completions`, `/responses` |  |
| `Qwen/Qwen3.8-Omni-Flash` | Qwen 3.8 Omni Flash | 1M | `/chat/completions`, `/responses` |  |
| `Qwen/Qwen3.8-Max-0902` | Qwen 3.8 Max 0902 | 1M | `/chat/completions` |  |
| `Qwen/Qwen3.8-Max` | Qwen 3.8 Max | 1M | `/chat/completions`, `/responses` |  |
| `Qwen/Qwen3.8-27B` | Qwen 3.8 27B | 262K | `/chat/completions`, `/responses` |  |
| `Qwen/Qwen3.8-Flash` | Qwen 3.8 Flash | 1M | `/chat/completions` |  |
| `Qwen/Qwen3.7-Max` | Qwen 3.7 Max | 1M | `/chat/completions`, `/responses` |  |
| `Qwen/Qwen3.7-Plus` | Qwen 3.7 Plus | 1M | `/chat/completions`, `/responses` |  |
| `Qwen/Qwen3.7-Flash` | Qwen 3.7 Flash | 1M | `/chat/completions`, `/responses` |  |
| `Qwen/Qwen3.6-Max-Preview` | Qwen 3.6 Max Preview | 200K | `/chat/completions`, `/responses` |  |
| `Qwen/Qwen3.6-Plus` | Qwen 3.6 Plus | 200K | `/chat/completions`, `/responses` |  |
| `meituan/LongCat-2.0` | LongCat 2.0 | 1.0M | `/chat/completions` |  |
| `stepfun/Step-5-Preview` | Step 5 Preview | 1M | `/chat/completions`, `/responses` |  |
| `stepfun/Step-3.7-Flash` | Step 3.7 Flash | 256K | `/chat/completions`, `/responses` |  |
| `stepfun/Step-3.5-Flash` | Step 3.5 Flash | 1M | `/chat/completions` |  |
| `tencent/hy3-paid` | Tencent Hy3 | 262K | `/chat/completions`, `/responses` |  |
| `tencent/hy4-preview` | Tencent Hy4 Preview | 1.0M | `/chat/completions` |  |
| `google/gemini-3.8-flash` | Gemini 3.8 Flash | 1M | `/chat/completions`, `/responses` |  |
| `google/gemini-3.7-flash` | Gemini 3.7 Flash | 1.0M | `/chat/completions` |  |
| `google/gemini-3.6-flash` | Gemini 3.6 Flash | 1M | `/chat/completions`, `/responses` |  |
| `google/gemini-3.5-flash` | Gemini 3.5 Flash | 1M | `/chat/completions`, `/responses` |  |
| `google/gemini-3.5-flash-lite` | Gemini 3.5 Flash Lite | 1M | `/chat/completions`, `/responses` |  |
| `google/gemini-3.1-flash-lite` | Gemini 3.1 Flash Lite | 1M | `/chat/completions`, `/responses` |  |
| `sakana/fugu-ultra` | Fugu Ultra | 1M | `/chat/completions`, `/responses` |  |
| `nvidia/nemotron-3-ultra-550b-a55b` | Nemotron 3 Ultra | 1M | `/chat/completions`, `/responses` |  |
| `thinkingmachines/inkling` | Inkling | 256K | `/chat/completions`, `/responses` |  |
| `thinkingmachines/inkling-small` | Inkling Small | 1M | `/chat/completions`, `/responses` |  |
| `poolside/laguna-s-2.1-free` | Laguna S 2.1 | 256K | `/chat/completions`, `/responses` | yes |
| `inclusionai/ling-3.0-flash-sante:free` | Ling 3.0 Flash Sante | 262K | `/chat/completions` | yes |
| `meta/muse-spark-1.1` | Muse Spark 1.1 | 1.0M | `/chat/completions`, `/responses` |  |
| `meta/muse-spark-1.2` | Muse Spark 1.2 | 1.0M | `/chat/completions`, `/responses` |  |
| `meta/muse-spark-1.2-contributor` | Muse Spark 1.2 Contributor | 1.0M | `/chat/completions`, `/responses` |  |
| `meta/muse-spark-1.3` | Muse Spark 1.3 | 1.0M | `/chat/completions`, `/responses` |  |
| `meta/muse-spark-1.3-contributor` | Muse Spark 1.3 Contributor | 1.0M | `/chat/completions`, `/responses` |  |
| `xai/grok-4.5` | Grok 4.5 | 500K | `/chat/completions`, `/responses` |  |
| `xai/grok-4.6` | Grok 4.6 | 500K | `/chat/completions`, `/responses` |  |
| `xai/grok-4.7` | Grok 4.7 | 500K | `/chat/completions`, `/responses` |  |

## Prices per 1M tokens (USD, at cost)

Scraped from the pricing-limits table. Deal rows show current (`now`) rates; `was` is the pre-deal list price.

| Model | Ctx | In | Out | Cache read | Cache write | Deal |
|---|---|---|---|---|---|---|
| Laguna S 2.1 | 256K | Free | Free | Free | — | FREE |
| Ling 3.0 Flash | 256K | Free | Free | Free | — |  |
| Ling 3.0 Flash Sante | 262K | Free | Free | Free | — | FREE |
| Tencent Hy4 Preview | 1M | $0.834 | $2.501 | $0.042 | — |  |
| Tencent Hy3 | 262K | $0.14 | $0.58 | $0.035 | — |  |
| Kimi K3 | 1M | $3.00 | $15.00 | $0.30 | — |  |
| Kimi K2.7 Code | 256K | $0.95 | $4.00 | $0.19 | — |  |
| Kimi K2.7 Code HighSpeed | 262K | $1.90 | $8.00 | $0.38 | — |  |
| Kimi K2.6 | 256K | $0.95 | $4.00 | $0.16 | — |  |
| Kimi K2.5 | 256K | $0.60 | $3.00 | $0.10 | — |  |
| GLM-5.3 Flash | 1M | $0.15 | $0.50 | $0.03 | — |  |
| GLM-5.3 FlashX | 1M | $0.37 | $1.25 | $0.075 | — |  |
| GLM-5.3 | 1M | $1.40 | $4.40 | $0.26 | — |  |
| GLM-5.2 | 1M | $1.40 | $4.40 | $0.26 | — |  |
| GLM-5.2 Fast | 1M | $3.00 | $10.25 | $0.50 | — |  |
| GLM-5.1 | — | $1.40 | $4.40 | $0.26 | — |  |
| GLM-5 | 200K | $1.00 | $3.20 | $0.20 | — |  |
| MiniMax M3 | 1M | $0.30 | $1.20 | $0.06 | — | -50% (was $0.60/$2.40/$0.12) |
| MiniMax M2.7 | — | $0.30 | $1.20 | $0.06 | — |  |
| MiniMax M2.5 | 200K | $0.30 | $1.20 | $0.03 | — |  |
| DeepSeek V4 Pro (latest) | 1M | $0.66 | $1.98 | $0.022 | — |  |
| DeepSeek V4 Flash (latest) | 1M | $0.15 | $0.60 | $0.003 | — |  |
| DeepSeek V4 Flash Vision (exp) | 1M | $0.15 | $0.60 | $0.003 | — |  |
| DeepSeek V4 Flash Fast | 1M | $0.28 | $0.56 | $0.07 | — |  |
| DeepSeek V4.1 Flash | 1M | $0.15 | $0.60 | $0.003 | — |  |
| Qwen 3.8 Omni Flash | 1M | $0.15 | $0.47 | $0.016 | — |  |
| Qwen 3.8 Max 0902 | 1M | $2.00 | $6.00 | $0.25 | — |  |
| Qwen 3.8 Max | 1M | $2.00 | $6.00 | $0.25 | $2.50 |  |
| Qwen 3.8 27B | 262K | $0.40 | $3.00 | $0.04 | — |  |
| Qwen 3.6 Max Preview | — | $1.30 | $7.80 | $0.26 | $1.63 |  |
| Qwen 3.6 Plus | — | $0.50 | $3.00 | $0.10 | — |  |
| Qwen 3.7 Max | 1M | $2.50 | $7.50 | $0.50 | $3.13 |  |
| Qwen 3.7 Plus | 1M | $0.40 | $1.60 | $0.08 | $0.50 |  |
| Qwen 3.8 Flash | 1M | $0.16 | $0.47 | $0.016 | — |  |
| Qwen 3.7 Flash | 1M | $0.03 | $0.13 | $0.006 | $0.038 |  |
| LongCat 2.0 | 1M | $0.30 | $1.20 | $0.006 | — |  |
| Step 5 Preview | 1M | $1.00 | $2.70 | $0.05 | — |  |
| Step 3.7 Flash | 256K | $0.20 | $1.15 | $0.04 | — |  |
| Step 3.5 Flash | 1M | $0.10 | $0.30 | $0.02 | — |  |
| MiMo V2.6 Pro | 1M | $0.435 | $0.87 | $0.0036 | — |  |
| MiMo V2.6 Pro UltraSpeed | 1M | $4.35 | $8.70 | $0.036 | — |  |
| MiMo V2.6 Flash | 1M | $0.14 | $0.28 | $0.0028 | — |  |
| MiMo V2.5 Pro | 1M | $0.435 | $0.87 | $0.0036 | — | -99% (was $2.00/$6.00/$0.40) |
| MiMo V2.5 | 1M | $0.14 | $0.28 | $0.0028 | — | -98% (was $0.80/$4.00/$0.16) |
| Nemotron 3 Ultra | 1M | $0.60 | $2.40 | $0.12 | — |  |
| Claude Fable 5.1 | 1M | $10.00 | $50.00 | $0.25 | $12.50 |  |
| Claude Fable 5 | 1M | $10.00 | $50.00 | $1.00 | $12.50 |  |
| Claude Opus 5 | 1M | $5.00 | $25.00 | $0.50 | $6.25 |  |
| Claude Opus 4.8 | 1M | $5.00 | $25.00 | $0.50 | $6.25 |  |
| Claude Opus 4.7 | 1M | $5.00 | $25.00 | $0.50 | $6.25 |  |
| Claude Opus 4.6 | 1M | $5.00 | $25.00 | $0.50 | $6.25 |  |
| Claude Sonnet 5 | 1M | $2.00 | $10.00 | $0.20 | $2.50 |  |
| Claude Sonnet 4.6 | 1M | $3.00 | $15.00 | $0.30 | $3.75 |  |
| Claude Haiku 4.5 | 200K | $1.00 | $5.00 | $0.10 | $1.25 |  |
| GPT-6 Astra | 1.1M | $10.00 | $50.00 | $1.00 | $12.50 |  |
| GPT-5.6 Sol | 1.1M | $5.00 | $30.00 | $0.50 | $6.25 |  |
| GPT-5.6 Terra | 1.1M | $2.00 | $12.00 | $0.20 | $2.50 |  |
| GPT-5.6 Luna | 1.1M | $0.20 | $1.20 | $0.02 | $0.25 |  |
| GPT-5.5 | 400K | $5.00 | $30.00 | $0.50 | — |  |
| GPT-5.4 | 400K | $2.50 | $15.00 | $0.25 | — |  |
| GPT-5.4 Mini | 400K | $0.75 | $4.50 | $0.075 | — |  |
| GPT-5.3 Codex | 400K | $2.00 | $8.00 | $0.50 | — |  |
| Gemini 3.8 Flash | 1M | $1.50 | $7.50 | $0.15 | — |  |
| Gemini 3.7 Flash | 1M | $1.50 | $7.50 | $0.15 | $0.08334 |  |
| Gemini 3.6 Flash | 1M | $1.50 | $7.50 | $0.15 | — |  |
| Gemini 3.5 Flash | 1M | $1.50 | $9.00 | $0.15 | — |  |
| Gemini 3.5 Flash Lite | 1M | $0.30 | $2.50 | $0.03 | — |  |
| Gemini 3.1 Flash Lite | 1M | $0.25 | $1.50 | $0.03 | — |  |
| Fugu Ultra | 1M | $5.00 | $30.00 | $0.50 | — |  |
| Muse Spark 1.3 | 1M | $1.25 | $4.25 | $0.15 | — |  |
| Muse Spark 1.3 Contributor | 1M | $0.10 | $0.20 | $0.002 | — |  |
| Muse Spark 1.2 | 1M | $1.25 | $4.25 | $0.15 | — |  |
| Muse Spark 1.2 Contributor | 1M | $0.10 | $0.20 | $0.002 | — |  |
| Muse Spark 1.1 | 1M | $1.25 | $4.25 | $0.15 | — |  |
| Grok 4.7 | 500K | $1.20 | $3.60 | $0.30 | — | -40% (was $2.00/$6.00/$0.50) |
| Grok 4.6 | 500K | $2.00 | $6.00 | $0.50 | — |  |
| Grok 4.5 | 500K | $2.00 | $6.00 | $0.50 | — |  |
| Inkling | 256K | $1.00 | $4.05 | $0.17 | — |  |
| Inkling Small | 1M | $0.50 | $1.20 | $0.10 | — |  |
| Claude Sonnet 4.5 | 1M | $3.00 | $15.00 | $0.30 | $3.75 |  |

## Deals

### Qwen 3.7 Max: 2x usage
- Discount: 50% off (multiplier 0.5, every credit goes ~2.0x further).
- Models: `qwen-3.7-max`.
- Status: EXPIRED 2026-06-22 but still shipped.
- Docs anchor: `#qwen-3.7-max-2x-usage`.

### MiniMax M3: 2x usage
- Discount: 50% off (multiplier 0.5, every credit goes ~2.0x further).
- Models: `minimax-m3`.
- Status: live (no expiry published).
- Docs anchor: `#minimax-m3-2x-usage`.

### Grok 4.7: 40% off at launch
- Discount: 40% off (multiplier 0.6, every credit goes ~1.7x further).
- Models: `grok-4.7`.
- Status: live (through 2026-09-27T23:59:59.999Z).
- Docs anchor: `#grok-4.7-40-off`.

### MiMo V2.5 Pro: up to 99% off
- Discount: 99% off (multiplier 0.2, every credit goes ~5.0x further).
- Models: `mimo-v2.5-pro`.
- Status: live (no expiry published).
- Docs anchor: `#mimo-v2.5-pro-99-off`.

### MiMo V2.5: up to 98% off
- Discount: 98% off (multiplier 0.1, every credit goes ~10.0x further).
- Models: `mimo-v2.5`.
- Status: live (no expiry published).
- Docs anchor: `#mimo-v2.5-98-off`.

### Laguna S 2.1: free
- Discount: 100% off (multiplier 0.0, every credit goes ?).
- Models: `laguna-s-2.1-free`.
- Status: live (while capacity lasts).
- Docs anchor: `#laguna-s-2.1-free`.

### Ling 3.0 Flash: free
- Discount: 100% off (multiplier 0.0, every credit goes ?).
- Models: `ling-3.0-flash-free`.
- Status: EXPIRED 2026-08-02 but still shipped.
- Docs anchor: `#ling-3.0-flash-free`.

### Ling 3.0 Flash Sante: free
- Discount: 100% off (multiplier 0.0, every credit goes ?).
- Models: `ling-3.0-flash-sante:free`.
- Status: live (while it lasts).
- Docs anchor: `#ling-3.0-flash-sante-free`.

## Price cross-check (deals bundle vs pricing table)

Two independent website sources for the same pre-deal list price: 6 fields agree, 0 mismatch, 0 unchecked (no table was-rates).
- All deal list-rates agree with the pricing table.

## Auth gates (probed live, no credentials)

| Endpoint | Verdict |
|---|---|
| `https://api.commandcode.ai/provider/v1/models` | public (200 without token) |
| `https://api.commandcode.ai/alpha/whoami` | auth-required (401 without token) |
| `https://api.commandcode.ai/internal/models` | auth-required (401 without token) |
| `https://api.commandcode.ai/provider` | unreachable/other (404) |
| `https://api.commandcode.ai/provider/v1` | unreachable/other (404) |
| `https://api.commandcode.ai/provider/v1/chat/completions` | auth-required (401 without token) |
| `https://api.commandcode.ai/provider/v1/deals` | unreachable/other (404) |
| `https://api.commandcode.ai/provider/v1/messages` | auth-required (401 without token) |
| `https://api.commandcode.ai/provider/v1/models/pricing` | unreachable/other (404) |
| `https://api.commandcode.ai/provider/v1/pricing` | unreachable/other (404) |
| `https://api.commandcode.ai/provider/v1/responses` | auth-required (401 without token) |
| `https://api.commandcode.ai/provider/v1/systemone` | auth-required (401 without token) |
| `https://api.commandcode.ai/v1/models` | unreachable/other (404) |
| `https://commandcode.ai/api/cli/models` | unreachable/other (404) |
| `https://commandcode.ai/api/deals` | unreachable/other (404) |
| `https://commandcode.ai/api/models` | unreachable/other (404) |
| `https://commandcode.ai/api/pricing` | unreachable/other (404) |
| `https://commandcode.ai/api/v1/models` | unreachable/other (404) |

## Endpoints carrying model / price / deal data

- `https://api.commandcode.ai/provider/v1/models` [model_listing, free_models, reachable_unauth] {"get": 200, "models": 76, "sample_ids": ["claude-sonnet-5", "claude-sonnet-4-6", "claude-fable-5-1", "claude-fable-5", "claude-opus-5"], "has_supported_endpoin
- Prices: `/docs/resources/pricing-limits` model-pricing table (80 rows).
- Deals: website `deals.js` bundle (8 deals).
- Per-plan allowances: website `goat-plan-public` / `plan-tiers` bundles (see corpus/).

## Drift notes

- `qwen-3.7-max-2x-usage` expired 2026-06-22 but is still shipped in the bundle; trust the live probe, not the bundle.
- `ling-3.0-flash-free` expired 2026-08-02 but is still shipped in the bundle; trust the live probe, not the bundle.

## Reproduce

```sh
python3 cc_routes.py            # full run: discover + probe + spec
python3 cc_routes.py --report-only  # re-render this report from spec/api-spec.json
```
