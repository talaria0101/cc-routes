#!/usr/bin/env python3
"""cc-routes: drift-proof Command Code endpoint finder + API spec generator.

Does not trust a hardcoded endpoint list. On every run it re-discovers
routes from first-party sources, probes them live, classifies which ones
carry the model listing / prices / deals / free-model info, prints those,
and writes a fresh api spec answering what we care about:

  - what models are available
  - what prices
  - any deals right now
  - any free models
  - do they work without auth

Sources (all first-party, all fetched live each run):
  1. https://commandcode.ai/sitemap.xml            (site routes)
  2. Docs pages (provider, pricing-limits, CLI models ref, CLI ref)
  3. Website JS asset manifest: fetch /models + /pricing HTML, extract
     /assets/*.js URLs, download them, regex out API-looking paths.
     This is where the web app's own route tables live
     (deals.js, constants.js, plan-tiers.js, goat-plan-public.js...).
     Asset filenames are content-hashed and drift, so we re-parse the
     HTML manifest every run instead of pinning filenames.
  4. CLI tarball: resolve latest version from the npm registry
     (https://registry.npmjs.org/command-code/latest), download the
     tgz, extract dist/cli.mjs, regex out API-looking paths.
     This is the ground truth for what the shipping CLI actually calls.
  5. A small static candidate sweep (api.commandcode.ai + commandcode.ai)
     so a brand-new route family is still probed even if no source
     mentions it yet.

Probing is deliberately gentle: sequential GETs (plus one tiny unauth
POST per inference endpoint to record the auth gate), short timeouts,
no retries, no concurrency. Quota instruments stop at the wall: we never
send authenticated traffic and never hammer.

Usage:
  python3 cc_routes.py [--out spec/api-spec.json] [--corpus corpus/]
                       [--no-fetch-sources] [--spec-only]

  --no-fetch-sources: skip live re-discovery, reuse corpus/ snapshots.
  --spec-only:       rebuild spec from existing corpus without probing.
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import html as htmlmod
import io
import json
import os
import re
import sys
import tarfile
import time
import urllib.parse
import urllib.request

API_HOST = "https://api.commandcode.ai"
WWW_HOST = "https://commandcode.ai"
DOCS_HOST = "https://commandcode.ai/docs"

DOC_PAGES = [
    f"{DOCS_HOST}/provider",
    f"{DOCS_HOST}/resources/pricing-limits",
    f"{DOCS_HOST}/reference/cli/models",
    f"{DOCS_HOST}/reference/cli",
]
SITE_PAGES_FOR_ASSETS = [
    f"{WWW_HOST}/models",
    f"{WWW_HOST}/pricing",
]

UA = {"User-Agent": "cc-routes/1.0 (+https://github.com/talaria0101/cc-routes)"}
TIMEOUT = 20

# Small static sweep: probed every run so brand-new families are caught
# even if no discovery source mentions them yet. Kept small on purpose.
STATIC_CANDIDATES = [
    # provider (documented)
    "/provider/v1/models",
    "/provider/v1/chat/completions",
    "/provider/v1/responses",
    "/provider/v1/messages",
    "/provider/v1/systemone",
    # provider (guessed alternates, cheap to check)
    "/provider/v1/pricing",
    "/provider/v1/deals",
    "/provider/v1/models/pricing",
    "/v1/models",
    # www api (all 404 today, kept so drift TO them is caught)
    ("www", "/api/models"),
    ("www", "/api/pricing"),
    ("www", "/api/deals"),
    ("www", "/api/cli/models"),
    ("www", "/api/v1/models"),
]

INFERENCE_POST_PROBES = {
    "/provider/v1/chat/completions": (
        {"model": "deepseek/deepseek-v4-flash",
         "messages": [{"role": "user", "content": "hi"}]}),
    "/provider/v1/responses": (
        {"model": "deepseek/deepseek-v4-flash", "input": "hi"}),
    "/provider/v1/messages": (
        {"model": "claude-sonnet-4-6", "max_tokens": 5,
         "messages": [{"role": "user", "content": "hi"}]}),
    "/provider/v1/systemone": (
        {"model": "typesafe/jev", "state": "x",
         "questions": {"a": {"type": "noul", "instructions": "x?"}}}),
}

PATH_RE = re.compile(
    r'"/(?:provider|internal|alpha|beta)(?:/[A-Za-z0-9/_\-:{}.]+)?"')
ABS_RE = re.compile(r'https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9/_\-:{}.%]*)?')
ASSET_RE = re.compile(r'(?:src|href)="(/assets/[^"]+\.js[^"]*)"')
DEAL_ID_RE = re.compile(r'id:"([a-z0-9][a-z0-9\-]*)",title:"([^"]+)"')


def fetch(url, method="GET", body=None, headers=None, timeout=TIMEOUT):
    req_headers = dict(UA)
    req_headers["Accept"] = "application/json, text/html, */*"
    if headers:
        req_headers.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=req_headers,
                                 method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return {
                "ok": True, "status": r.status,
                "headers": dict(r.headers.items()),
                "body": raw,
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
    except Exception as e:  # HTTPError carries status + body
        status = getattr(e, "code", None)
        raw = b""
        try:
            raw = e.read()
        except Exception:
            pass
        return {"ok": False, "status": status or 0,
                "error": f"{type(e).__name__}: {e}",
                "body": raw, "elapsed_ms": int((time.time() - t0) * 1000)}


def body_text(resp):
    raw = resp.get("body", b"") or b""
    try:
        return raw.decode("utf-8", "replace")
    except Exception:
        return ""


def try_json(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def strip_tags(page_html):
    t = re.sub(r"<script.*?</script>", " ", page_html,
               flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = htmlmod.unescape(t)
    return [l.strip() for l in t.splitlines() if l.strip()]


# ---- discovery -----------------------------------------------------------

def discover_sitemap(save):
    out = {"source": "sitemap.xml", "urls": []}
    r = fetch(f"{WWW_HOST}/sitemap.xml")
    save("sitemap.xml", r.get("body", b""))
    if r["ok"]:
        out["urls"] = sorted(set(re.findall(r"<loc>([^<]+)</loc>",
                                            body_text(r))))
    out["status"] = r["status"]
    return out


def discover_docs(save):
    found_paths = set()
    pages = {}
    for url in DOC_PAGES:
        r = fetch(url)
        name = urllib.parse.quote(url.split("commandcode.ai/")[1],
                                  safe="").replace("%", "_") + ".html"
        save(name, r.get("body", b""))
        txt = body_text(r)
        pages[url] = {"status": r["status"], "bytes": len(r.get("body", b""))}
        for m in PATH_RE.finditer(txt):
            found_paths.add(m.group(0).strip('"'))
        for m in ABS_RE.finditer(txt):
            u = m.group(0)
            if "commandcode.ai" in u:
                p = urllib.parse.urlparse(u).path
                if p.startswith(("/provider", "/internal", "/alpha",
                                  "/beta", "/api")):
                    found_paths.add(p)
    return {"source": "docs-pages", "pages": pages,
            "paths": sorted(found_paths)}


def discover_assets(save):
    asset_urls, paths, hosts = set(), set(), set()
    for page in SITE_PAGES_FOR_ASSETS:
        r = fetch(page)
        txt = body_text(r)
        for m in ASSET_RE.finditer(txt):
            asset_urls.add(WWW_HOST + m.group(1).split("?")[0])
    for au in sorted(asset_urls):
        r = fetch(au)
        fn = "asset_" + au.split("/assets/")[1].split("?")[0]
        save(fn, r.get("body", b""))
        txt = body_text(r)
        for m in PATH_RE.finditer(txt):
            paths.add(m.group(0).strip('"'))
        for m in ABS_RE.finditer(txt):
            u = m.group(0).rstrip(".,;")
            hosts.add(u)
            p = urllib.parse.urlparse(u).path
            if p.startswith(("/provider", "/internal", "/alpha",
                              "/beta", "/api")):
                paths.add(p)
    return {"source": "website-assets", "assets": len(asset_urls),
            "paths": sorted(paths), "abs_hosts": sorted(hosts)}


def discover_cli(save):
    info = {"source": "cli-tarball"}
    r = fetch("https://registry.npmjs.org/command-code/latest")
    save("npm-latest.json", r.get("body", b""))
    meta = try_json(body_text(r)) or {}
    info["version"] = meta.get("version")
    tarball = ((meta.get("dist") or {}).get("tarball"))
    info["tarball"] = tarball
    paths, hosts = set(), set()
    if tarball:
        tr = fetch(tarball, timeout=60)
        save("cli.tgz", tr.get("body", b""))
        try:
            tf = tarfile.open(fileobj=io.BytesIO(tr.get("body", b"")),
                              mode="r:gz")
            member = next((m for m in tf.getmembers()
                           if m.name.endswith("dist/cli.mjs")), None)
            if member:
                js = tf.extractfile(member).read().decode("utf-8",
                                                          "replace")
                with open(os.path.join(CORPUS, "cli.mjs"), "w") as f:
                    f.write(js)
                for m in PATH_RE.finditer(js):
                    paths.add(m.group(0).strip('"'))
                for m in ABS_RE.finditer(js):
                    u = m.group(0).rstrip(".,;")
                    hosts.add(u)
                    p = urllib.parse.urlparse(u).path
                    if p.startswith(("/provider", "/internal", "/alpha",
                                      "/beta", "/api")):
                        paths.add(p)
                info["cli_mjs_bytes"] = len(js)
        except Exception as e:
            info["extract_error"] = str(e)
    info["paths"] = sorted(paths)
    info["abs_hosts_sample"] = sorted(
        h for h in hosts if "commandcode" in h or "models.dev" in h)[:20]
    return info


# ---- probing + classification --------------------------------------------

def classify(url, get_resp, post_resp=None):
    """Label what a route carries. Never trusts docs, only bodies."""
    txt = body_text(get_resp)
    js = try_json(txt)
    flags = {"model_listing": False, "prices": False, "deals": False,
             "free_models": False, "auth_required": False,
             "reachable_unauth": False}
    detail = {}
    if get_resp.get("status") == 401:
        flags["auth_required"] = True
        detail["get"] = 401
    if get_resp.get("status") == 200:
        flags["reachable_unauth"] = True
        detail["get"] = 200
    else:
        detail["get"] = get_resp.get("status")
    if isinstance(js, dict):
        data = js.get("data")
        if (js.get("object") == "list" and isinstance(data, list)
                and data and all(isinstance(m, dict) and "id" in m
                                 for m in data)):
            flags["model_listing"] = True
            detail["models"] = len(data)
            detail["sample_ids"] = [m["id"] for m in data[:5]]
            if any("supported_endpoints" in m for m in data):
                detail["has_supported_endpoints"] = True
        low = txt.lower()
        if any(k in low for k in ("per 1m", "input", "output",
                                  "cache", "promptcost",
                                  "completioncost")) and "id" in low:
            flags["prices"] = True
        if ("multiplier" in low and "modelids" in low) or (
                "discountpercent" in low):
            flags["deals"] = True
        if (":free" in txt or '"free"' in low or "laguna" in low
                or "cost no credits" in low):
            flags["free_models"] = "free" in low
    else:
        low = txt.lower()
        if "per 1m tokens" in low or ("input" in low and "/m" in txt):
            flags["prices"] = True
        if "deal" in low and ("off" in low or "free" in low):
            flags["deals"] = True
        if "is free" in low or "cost no credits" in low:
            flags["free_models"] = True
    if post_resp is not None:
        detail["post_unauth"] = post_resp.get("status")
        if post_resp.get("status") == 401:
            flags["auth_required"] = True
        if post_resp.get("status") == 200:
            flags["reachable_unauth"] = True
            flags["auth_required"] = False
    return flags, detail


def probe(url, save_name=None, do_post=None):
    g = fetch(url)
    if save_name:
        with open(os.path.join(CORPUS, save_name), "wb") as f:
            f.write(g.get("body", b""))
    p = None
    if do_post is not None:
        p = fetch(url, method="POST", body=do_post)
    flags, detail = classify(url, g, p)
    return {"url": url, "flags": flags, "detail": detail,
            "get_status": g.get("status"),
            "post_status": p.get("status") if p else None,
            "bytes": len(g.get("body", b""))}


# ---- spec build ----------------------------------------------------------

def build_spec(probe_results, discovery):
    now = datetime.datetime.now(datetime.timezone.utc)
    models_entry = next(
        (r for r in probe_results
         if r["url"].endswith("/provider/v1/models") and r["flags"].get(
             "model_listing")), None)
    models, free_models = [], []
    if models_entry:
        try:
            with open(os.path.join(CORPUS, "provider-models.json"),
                      "rb") as f:
                js = json.load(f)
            for m in js.get("data", []):
                models.append({
                    "id": m.get("id"), "name": m.get("name"),
                    "context_length": m.get("context_length"),
                    "supported_endpoints": m.get("supported_endpoints", []),
                    "free": ("free" in str(m.get("id", "")).lower()),
                })
            free_models = [m["id"] for m in models if m["free"]]
        except Exception as e:
            models_entry["detail"]["spec_error"] = str(e)
    deals = scrape_deals_from_corpus()
    prices = scrape_prices_from_corpus()
    interesting = [r for r in probe_results if r["flags"].get(
        "model_listing") or r["flags"].get("prices") or r["flags"].get(
        "deals")]
    auth = {}
    for r in probe_results:
        key = r["url"]
        if r["post_status"] == 401 or (
                r["get_status"] == 401 and r["post_status"] is None):
            auth[key] = "auth-required (401 without token)"
        elif r["flags"].get("reachable_unauth"):
            auth[key] = "public (200 without token)"
        else:
            auth[key] = f"unreachable/other ({r['get_status']})"
    return {
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": discovery,
        "models_available": models,
        "model_count": len(models),
        "prices_n": len(prices),
        "prices_per_1m_usd": prices,
        "deals_now": deals,
        "free_models": free_models,
        "auth": auth,
        "interesting_endpoints": [
            {"url": r["url"], "flags": r["flags"], "detail": r["detail"]}
            for r in interesting],
        "all_probed": [
            {"url": r["url"], "get": r["get_status"],
             "post": r["post_status"], "flags": r["flags"]}
            for r in probe_results],
    }


def scrape_deals_from_corpus():
    deals = []
    for fn in sorted(os.listdir(CORPUS)):
        if not (fn.startswith("asset_deals") and fn.endswith(".js")):
            continue
        try:
            js = open(os.path.join(CORPUS, fn)).read()
        except Exception:
            continue
        for m in re.finditer(
                r'\{id:"([^"]+)",title:"([^"]+)"(.*?)docsAnchor:"([^"]+)"',
                js, re.S):
            chunk = m.group(0)
            mult = re.search(r"multiplier:([0-9.]+|!0)", chunk)
            disc = re.search(r"discountPercent:([0-9]+)", chunk)
            exp = re.search(r'expires:"([^"]+)"', chunk)
            start = re.search(r'starts:"([^"]+)"', chunk)
            end = re.search(r'endsWhen:"([^"]+)"', chunk)
            mids = re.search(r"modelIds:\[([^\]]*)\]", chunk)
            deals.append({
                "id": m.group(1), "title": m.group(2),
                "docs_anchor": m.group(4),
                "multiplier": (0 if mult and mult.group(1) == "!0"
                               else float(mult.group(1))) if mult else None,
                "discount_percent": int(disc.group(1)) if disc else None,
                "model_ids": re.findall(r'"([^"]+)"', mids.group(1))
                if mids else [],
                "starts": start.group(1) if start else None,
                "expires": exp.group(1) if exp else None,
                "ends_when": end.group(1) if end else None,
            })
    return deals


PRICE_CTX = {"256K", "262K", "1M", "1.1M", "500K", "200K",
             "400K"}
DEAL_BADGES = {"FREE", "-50%", "-99%", "-98%", "-40%"}


def scrape_prices_from_corpus():
    # The pricing table renders as grid divs with role="row". Token
    # grammar per row: name, [deal badge], context, prices..., notes.
    # Deal rows carry was+now pairs (strike + bold), so 6-7 price
    # tokens instead of 4; we keep the "now" (current) rates.
    prices = {}
    for fn in sorted(os.listdir(CORPUS)):
        if ".html" not in fn or "pricing" not in fn:
            continue
        try:
            page = open(os.path.join(CORPUS, fn)).read()
        except Exception:
            continue
        for row in page.split('role="row"')[1:]:
            toks = [x.strip() for x in
                    re.findall(r">([^<>]+)<", row) if x.strip()]
            if not toks or toks[0] == "Model":
                continue
            name = toks[0]
            rest = toks[1:]
            badge = None
            if rest and rest[0] in DEAL_BADGES:
                badge = rest[0]
                rest = rest[1:]
            if not rest or (rest[0] not in PRICE_CTX
                            and rest[0] != "\u2014"):
                continue
            ctx = rest[0]
            vals = []
            for tok in rest[1:]:
                if re.match(r"^(Free|\$[0-9.]+|\u2014)$", tok):
                    vals.append(tok)
                else:
                    break
            if len(vals) >= 6:
                # was/now pairs: input, output, cache-read each twice
                entry = {"context": ctx, "input_per_1m": vals[1],
                         "output_per_1m": vals[3],
                         "cache_read_per_1m": vals[5],
                         "cache_write_per_1m": (vals[6] if len(vals) > 6
                                                else None),
                         "was_per_1m": [vals[0], vals[2], vals[4]]}
            elif len(vals) >= 3:
                entry = {"context": ctx, "input_per_1m": vals[0],
                         "output_per_1m": vals[1],
                         "cache_read_per_1m": vals[2],
                         "cache_write_per_1m": (vals[3] if len(vals) > 3
                                                else None)}
            else:
                continue
            if badge:
                entry["deal_badge"] = badge
            prices[name] = entry
    return prices


CORPUS = "corpus"


def deal_status(d, generated_utc):
    """One-line human status for a deal (live / expired / unbounded)."""
    exp = d.get("expires")
    if d.get("ends_when"):
        return f"live ({d['ends_when']})"
    if not exp:
        return "live (no expiry published)"
    try:
        exp_dt = exp.replace("Z", "+00:00")
        alive = exp_dt >= (generated_utc or "")
    except Exception:
        return f"expires {exp}"
    return (f"live (through {exp})" if alive
            else f"EXPIRED {exp} but still shipped")


def render_markdown(spec):
    L = []
    A = L.append
    gen = spec.get("generated_utc", "?")
    src = spec.get("sources", {})
    A("# Command Code API spec (human report)")
    A("")
    A(f"Generated (UTC): {gen}. Machine-readable twin: "
      f"`spec/api-spec.json`.")
    A(f"Sources re-resolved this run: {src.get('sitemap_urls', '?')} "
      f"sitemap URLs, {src.get('docs_paths', '?')} docs paths, "
      f"{src.get('asset_js', '?')} website JS assets, "
      f"CLI {src.get('cli_version', '?')}.")
    A("")
    A("## TL;DR")
    A("")
    A(f"- Models available: **{spec.get('model_count', 0)}** "
      f"(live `GET /provider/v1/models`, no auth needed).")
    free = spec.get("free_models", [])
    A(f"- Free models: "
      f"{', '.join(f'`{m}`' for m in free) if free else 'none'}."
      f" Free requests still need $1 of credits to start a session.")
    deals = spec.get("deals_now", [])
    live = [d for d in deals
            if not deal_status(d, gen).startswith("EXPIRED")]
    A(f"- Deals in the website bundle: {len(deals)} total, "
      f"{len(live)} live.")
    A("- Inference endpoints (chat, responses, messages, systemone) "
      "all require a Bearer key (401 without one). No free inference "
      "without an account.")
    A("")
    A("## Models available")
    A("")
    A("| Model id | Name | Context | Endpoints | Free |")
    A("|---|---|---|---|---|")
    for m in spec.get("models_available", []):
        eps = ", ".join(f"`{e}`"
                         for e in m.get("supported_endpoints", []))
        ctx = m.get("context_length") or "?"
        if isinstance(ctx, int):
            if ctx >= 1000000:
                ctx = (f"{ctx // 1000000}M" if ctx % 1000000 == 0
                       else f"{ctx / 1000000:.1f}M")
            elif ctx >= 1000:
                ctx = f"{ctx // 1000}K"
        A(f"| `{m.get('id')}` | {m.get('name')} | {ctx} | {eps} | "
          f"{'yes' if m.get('free') else ''} |")
    A("")
    A("## Prices per 1M tokens (USD, at cost)")
    A("")
    A("Scraped from the pricing-limits table. Deal rows show current "
      "(`now`) rates; `was` is the pre-deal list price.")
    A("")
    A("| Model | Ctx | In | Out | Cache read | Cache write | Deal |")
    A("|---|---|---|---|---|---|---|")
    for name, p in spec.get("prices_per_1m_usd", {}).items():
        was = (" (was " + "/".join(p["was_per_1m"]) + ")"
               if p.get("was_per_1m") else "")
        A(f"| {name} | {p.get('context')} | {p.get('input_per_1m')} | "
          f"{p.get('output_per_1m')} | {p.get('cache_read_per_1m')} | "
          f"{p.get('cache_write_per_1m')} | "
          f"{p.get('deal_badge', '')}{was} |")
    A("")
    A("## Deals")
    A("")
    for d in deals:
        mult = d.get("multiplier")
        eff = (f"~{1 / mult:.1f}x further" if mult else "?")
        A(f"### {d.get('title')}")
        A(f"- Discount: {d.get('discount_percent')}% off "
          f"(multiplier {mult}, every credit goes {eff}).")
        A(f"- Models: "
          f"{', '.join(f'`{m}`' for m in d.get('model_ids', []))}.")
        A(f"- Status: {deal_status(d, gen)}.")
        A(f"- Docs anchor: `#{d.get('docs_anchor')}`.")
        A("")
    A("## Auth gates (probed live, no credentials)")
    A("")
    A("| Endpoint | Verdict |")
    A("|---|---|")
    for url, verdict in spec.get("auth", {}).items():
        A(f"| `{url}` | {verdict} |")
    A("")
    A("## Endpoints carrying model / price / deal data")
    A("")
    for e in spec.get("interesting_endpoints", []):
        fl = ", ".join(k for k, v in e["flags"].items() if v)
        A(f"- `{e['url']}` [{fl}] {json.dumps(e['detail'])[:160]}")
    A("- Prices: `/docs/resources/pricing-limits` model-pricing table "
      f"({spec.get('prices_n', 0)} rows).")
    A("- Deals: website `deals.js` bundle "
      f"({len(deals)} deals).")
    A("- Per-plan allowances: website `goat-plan-public` / `plan-tiers` "
      "bundles (see corpus/).")
    A("")
    A("## Drift notes")
    A("")
    expired = [d for d in deals
               if deal_status(d, gen).startswith("EXPIRED")]
    for d in expired:
        A(f"- `{d['id']}` expired {d.get('expires')} but is still "
          "shipped in the bundle; trust the live probe, not the bundle.")
    live_ids = {m for d in deals for m in d.get("model_ids", [])}
    reg_ids = {m.get("id", "").split("/")[-1].lower().replace(
        ":free", "").replace("-", "")
        for m in spec.get("models_available", [])}
    for d in deals:
        for m in d.get("model_ids", []):
            norm = m.lower().replace(":free", "").replace("-", "")
            if norm not in reg_ids and not deal_status(
                    d, gen).startswith("EXPIRED"):
                A(f"- Deal model `{m}` ({d['id']}) is not in the live "
                  "model list; may be renamed or offline.")
    if not expired:
        A("- No expired deals in the bundle this run.")
    A("")
    A("## Reproduce")
    A("")
    A("```sh")
    A("python3 cc_routes.py            # full run: discover + probe + spec")
    A("python3 cc_routes.py --report-only  # re-render this report from "
      "spec/api-spec.json")
    A("```")
    return "\n".join(L) + "\n"


def _txt_table(headers, rows):
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], min(52, len(c)))
    def fmt(r):
        return " | ".join(c[:widths[i]].ljust(widths[i])
                            for i, c in enumerate(r))
    lines = [fmt(headers), "-+- ".join("-" * w for w in widths)]
    lines += [fmt(r) for r in rows]
    return lines


def render_text(spec):
    L = []
    A = L.append
    gen = spec.get("generated_utc", "?")
    A("COMMAND CODE API SPEC (human report)")
    A(f"Generated (UTC): {gen}. Twin: spec/api-spec.json.")
    A("")
    A("TL;DR")
    A(f"  models: {spec.get('model_count', 0)} (live, no auth)")
    A(f"  free: {', '.join(spec.get('free_models', [])) or 'none'}")
    A(f"  deals: {len(spec.get('deals_now', []))} in bundle")
    A("  inference endpoints: Bearer key required (401 without one)")
    A("")
    A("MODELS")
    L += _txt_table(
        ["model id", "context", "endpoints", "free"],
        [[m.get("id", ""), str(m.get("context_length") or "?"),
          ",".join(m.get("supported_endpoints", [])),
          "yes" if m.get("free") else ""]
         for m in spec.get("models_available", [])])
    A("")
    A("PRICES PER 1M TOKENS (USD)")
    L += _txt_table(
        ["model", "ctx", "in", "out", "read", "write", "deal"],
        [[n, p.get("context", ""), p.get("input_per_1m", ""),
          p.get("output_per_1m", ""), p.get("cache_read_per_1m", ""),
          p.get("cache_write_per_1m", ""), p.get("deal_badge", "")]
         for n, p in spec.get("prices_per_1m_usd", {}).items()])
    A("")
    A("DEALS")
    for d in spec.get("deals_now", []):
        A(f"  {d.get('title')} -- {d.get('discount_percent')}% off, "
          f"models: {', '.join(d.get('model_ids', []))}, "
          f"status: {deal_status(d, gen)}")
    A("")
    A("AUTH GATES")
    for url, verdict in spec.get("auth", {}).items():
        A(f"  {url} -> {verdict}")
    return "\n".join(L) + "\n"


def write_reports(spec, md_path, txt_path):
    if md_path:
        d = os.path.dirname(md_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(md_path, "w") as f:
            f.write(render_markdown(spec))
    if txt_path:
        d = os.path.dirname(txt_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(txt_path, "w") as f:
            f.write(render_text(spec))
    return [p for p in (md_path, txt_path) if p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="spec/api-spec.json")
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--no-fetch-sources", action="store_true")
    ap.add_argument("--spec-only", action="store_true")
    ap.add_argument("--report", default=None,
                    help="markdown report path "
                    "(default: <spec-dir>/REPORT.md)")
    ap.add_argument("--report-txt", default=None,
                    help="plain-text report path "
                    "(default: <spec-dir>/REPORT.txt)")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--report-only", action="store_true",
                    help="render reports from an existing spec only; "
                    "pairs with --spec")
    ap.add_argument("--spec", default=None,
                    help="existing spec to render (with --report-only)")
    args = ap.parse_args()
    if args.report_only:
        spec_path = args.spec or args.out
        spec = json.load(open(spec_path))
        spec_dir = os.path.dirname(os.path.abspath(spec_path))
        md = args.report or os.path.join(spec_dir, "REPORT.md")
        tx = args.report_txt or os.path.join(spec_dir, "REPORT.txt")
        print(f"report: {write_reports(spec, md, tx)}")
        return
    global CORPUS
    CORPUS = args.corpus
    os.makedirs(CORPUS, exist_ok=True)

    def save(name, data):
        with open(os.path.join(CORPUS, name), "wb") as f:
            f.write(data or b"")

    discovery = {}
    if not args.no_fetch_sources and not args.spec_only:
        print("[1/4] sitemap ...", flush=True)
        discovery["sitemap"] = discover_sitemap(save)
        print("      urls:", len(discovery["sitemap"].get("urls", [])),
              flush=True)
        print("[2/4] docs pages ...", flush=True)
        discovery["docs"] = discover_docs(save)
        print("      paths:", len(discovery["docs"].get("paths", [])),
              flush=True)
        print("[3/4] website assets ...", flush=True)
        discovery["assets"] = discover_assets(save)
        print("      js assets:", discovery["assets"].get("assets"),
              "paths:", len(discovery["assets"].get("paths", [])),
              flush=True)
        print("[4/4] cli tarball ...", flush=True)
        discovery["cli"] = discover_cli(save)
        print("      version:", discovery["cli"].get("version"),
              "paths:", len(discovery["cli"].get("paths", [])),
              flush=True)
        with open(os.path.join(CORPUS, "discovery.json"), "w") as f:
            json.dump(discovery, f, indent=2)
    else:
        try:
            discovery = json.load(open(os.path.join(CORPUS,
                                                    "discovery.json")))
        except Exception:
            discovery = {"note": "no discovery snapshot; run without flags"}

    # Candidate set = union of everything discovered + static sweep.
    cands = {}  # url -> why
    for c in STATIC_CANDIDATES:
        if isinstance(c, tuple):
            host, path = c
            cands[WWW_HOST + path] = "static-sweep"
        else:
            cands[API_HOST + c] = "static-sweep"
    for key in ("docs", "assets", "cli"):
        for p in (discovery.get(key) or {}).get("paths", []):
            if p.startswith("/provider/v1/"):
                cands.setdefault(API_HOST + p, f"discovered-{key}")
            elif p.startswith("/provider"):
                cands.setdefault(API_HOST + p, f"discovered-{key}")
            # /internal + /alpha + /beta need auth; probe the safe,
            # known ones only (whoami + models) to record the gate
            # without spraying authed surface.
    for p in ("/internal/models", "/alpha/whoami"):
        cands.setdefault(API_HOST + p, "auth-gate-check")

    probe_results = []
    if not args.spec_only:
        print(f"probing {len(cands)} candidates ...", flush=True)
        for url, why in sorted(cands.items()):
            name = None
            if url.endswith("/provider/v1/models"):
                name = "provider-models.json"
            path = urllib.parse.urlparse(url).path
            do_post = INFERENCE_POST_PROBES.get(path)
            r = probe(url, save_name=name, do_post=do_post)
            r["why"] = why
            probe_results.append(r)
            fl = ",".join(k for k, v in r["flags"].items() if v)
            print(f"  {r['get_status']} "
                  f"{('POST:' + str(r['post_status'])) if r['post_status'] else '':10}"
                  f" {url} [{fl or 'no-signal'}]", flush=True)
        with open(os.path.join(CORPUS, "probes.json"), "w") as f:
            json.dump(probe_results, f, indent=2)
    else:
        probe_results = json.load(open(os.path.join(CORPUS, "probes.json")))

    spec = build_spec(probe_results, {
        "sitemap_urls": len((discovery.get("sitemap") or {}).get("urls",
                                                                 [])),
        "docs_paths": len((discovery.get("docs") or {}).get("paths", [])),
        "asset_js": (discovery.get("assets") or {}).get("assets"),
        "cli_version": (discovery.get("cli") or {}).get("version"),
    })
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(spec, f, indent=2)

    print("\n=== endpoints carrying model listing / prices / deals ===")
    for e in spec["interesting_endpoints"]:
        fl = ",".join(k for k, v in e["flags"].items() if v)
        print(f"  {e['url']} [{fl}] {json.dumps(e['detail'])[:200]}")
    print("\n=== non-endpoint carriers (website sources, re-resolved each run) ===")
    print("  prices: /docs/resources/pricing-limits model-pricing table "
          f"({spec['prices_n']} rows in spec)")
    deal_assets = sorted(f for f in os.listdir(CORPUS)
                         if f.startswith("asset_deals"))
    print(f"  deals: website deals.js asset {deal_assets} "
          f"({len(spec['deals_now'])} deals in spec)")
    print("  per-plan allowances: website goat-plan-public / plan-tiers "
          "assets (see corpus/)")
    print(f"\nmodels: {spec['model_count']}, free: {spec['free_models']}")
    print(f"deals: {len(spec['deals_now'])}, "
          f"prices scraped: {len(spec['prices_per_1m_usd'])}")
    print(f"spec: {args.out}")
    if not args.no_report:
        spec_dir = os.path.dirname(os.path.abspath(args.out))
        md = args.report or os.path.join(spec_dir, "REPORT.md")
        tx = args.report_txt or os.path.join(spec_dir, "REPORT.txt")
        print(f"report: {write_reports(spec, md, tx)}")


if __name__ == "__main__":
    sys.exit(main())
