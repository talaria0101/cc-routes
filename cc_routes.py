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
                       [--no-fetch-sources] [--spec-only] [--force]
                       [--report PATH] [--report-txt PATH] [--no-report]
                       [--report-only] [--spec PATH]

  --no-fetch-sources: skip live re-discovery, reuse corpus/ snapshots.
  --spec-only:       rebuild spec from existing corpus without probing.
  --force:           write outputs even when validation gates fail.
  --report-only:     render REPORT.md/.txt from an existing spec only.

Writes are atomic and validated: empty sections or major count
collapses vs the prior spec refuse the overwrite (exit 2) unless
--force. The prior spec is kept as <out>.prev.json.
"""
from __future__ import annotations

import argparse
import datetime
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

# Fallback probe models (used only when the live registry cannot be read;
# in that case validation refuses the overwrite anyway). Live runs pick
# probe models from the fetched registry (pick_probe_models), so a model
# rename/removal surfaces as drift instead of a misleading 404 verdict.
FALLBACK_CHAT_MODEL = "deepseek/deepseek-v4-flash"
FALLBACK_MSG_MODEL = "claude-sonnet-4-6"


def pick_probe_models():
    """Build auth-gate POST bodies from the live registry snapshot.

    Returns {path: body}. Picks the first registry id advertising each
    wire format via supported_endpoints, so probes stay endpoint-correct
    when models churn. Falls back to hardcoded ids (which then likely
    404, and the missing model-listing gate refuses the write)."""
    chat_m, msg_m = FALLBACK_CHAT_MODEL, FALLBACK_MSG_MODEL
    try:
        js = json.load(open(os.path.join(CORPUS, "provider-models.json")))
        for m in js.get("data", []):
            eps = m.get("supported_endpoints", []) or []
            if chat_m == FALLBACK_CHAT_MODEL and \
                    "/chat/completions" in eps:
                chat_m = m["id"]
            if msg_m == FALLBACK_MSG_MODEL and "/messages" in eps:
                msg_m = m["id"]
            if chat_m != FALLBACK_CHAT_MODEL and \
                    msg_m != FALLBACK_MSG_MODEL:
                break
    except Exception:
        pass
    return {
        "/provider/v1/chat/completions": (
            {"model": chat_m,
             "messages": [{"role": "user", "content": "hi"}]}),
        "/provider/v1/responses": (
            {"model": chat_m, "input": "hi"}),
        "/provider/v1/messages": (
            {"model": msg_m, "max_tokens": 5,
             "messages": [{"role": "user", "content": "hi"}]}),
        "/provider/v1/systemone": (
            {"model": "typesafe/jev", "state": "x",
             "questions": {"a": {"type": "noul",
                                     "instructions": "x?"}}}),
    }

PATH_RE = re.compile(
    r'"/(?:provider|internal|alpha|beta)(?:/[A-Za-z0-9/_\-:{}.]+)?"')
ABS_RE = re.compile(r'https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9/_\-:{}.%]*)?')
ASSET_RE = re.compile(r'(?:src|href)="(/assets/[^"]+\.js[^"]*)"')


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
                atomic_write(os.path.join(CORPUS, "cli.mjs"), js)
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
        tmp = os.path.join(CORPUS, save_name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(g.get("body", b""))
        os.replace(tmp, os.path.join(CORPUS, save_name))
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
    deals = scrape_deals_from_corpus()
    free_by_deal = set()
    for d in deals:
        if d.get("multiplier") == 0:
            for m in d.get("model_ids", []):
                free_by_deal.add(norm_mid(m))
    prices = scrape_prices_from_corpus()
    cross = cross_check_deal_rates(deals, prices)
    models, free_models = [], []
    if models_entry:
        try:
            with open(os.path.join(CORPUS, "provider-models.json"),
                      "rb") as f:
                js = json.load(f)
            for m in js.get("data", []):
                mid = m.get("id", "")
                free = ("free" in str(mid).lower()
                        or norm_mid(mid) in free_by_deal)
                models.append({
                    "id": mid, "name": m.get("name"),
                    "context_length": m.get("context_length"),
                    "supported_endpoints": m.get("supported_endpoints", []),
                    "free": free,
                })
            free_models = [m["id"] for m in models if m["free"]]
        except Exception as e:
            models_entry["detail"]["spec_error"] = str(e)
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
        "price_crosscheck": cross,
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
        spans = list(re.finditer(
            r'\{id:"([^"]+)",title:"([^"]+)"(.*?)docsAnchor:"([^"]+)"',
            js, re.S))
        for si, m in enumerate(spans):
            chunk = m.group(0)
            # listRates sits AFTER docsAnchor in the object, so scan the
            # window up to the next deal for it.
            tail = js[m.end():spans[si + 1].start()
                      if si + 1 < len(spans) else len(js)]
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
            lr = re.search(r"listRates:\{([^}]*\{[^}]*\}[^}]*)\}",
                           tail)
            if lr:
                rates = {}
                for rm in re.finditer(
                        r'"([^"]+)":\{input:([0-9.]+),output:([0-9.]+),'        r"cacheRead:([0-9.]+)\}", lr.group(1)):
                    rates[rm.group(1)] = {
                        "input": float(rm.group(2)),
                        "output": float(rm.group(3)),
                        "cache_read": float(rm.group(4))}
                if rates:
                    deals[-1]["list_rates"] = rates
    return deals


def _num(s):
    try:
        return float(str(s).replace("$", "").strip())
    except Exception:
        return None


def cross_check_deal_rates(deals, prices):
    """Cross-check deals-bundle listRates vs pricing-table was-rates.

    Two independent website sources for the same pre-deal list price.
    Returns {agree: [...], mismatch: [...], unchecked: [...]}; mismatches
    mean one of the two sources drifted and need a human look."""
    by_norm = {norm_mid(n): (n, p) for n, p in prices.items()}
    out = {"agree": [], "mismatch": [], "unchecked": []}
    for d in deals:
        for mid, rates in (d.get("list_rates") or {}).items():
            hit = by_norm.get(norm_mid(mid))
            if not hit or not hit[1].get("was_per_1m"):
                out["unchecked"].append(
                    {"deal": d["id"], "model": mid,
                     "reason": "no was-rates in pricing table"})
                continue
            name, p = hit
            pairs = [("input", rates["input"], p["was_per_1m"][0]),
                     ("output", rates["output"], p["was_per_1m"][1]),
                     ("cache_read", rates["cache_read"],
                      p["was_per_1m"][2])]
            for field, a, b in pairs:
                bnum = _num(b)
                if bnum is None or abs(a - bnum) > 1e-9:
                    out["mismatch"].append(
                        {"deal": d["id"], "model": mid, "field": field,
                         "bundle_list": a, "table_was": b})
                else:
                    out["agree"].append(
                        {"deal": d["id"], "model": mid, "field": field})
    return out


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


def _parse_ts(s):
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = datetime.datetime.strptime(s[:10], "%Y-%m-%d")
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def deal_status(d, generated_utc):
    """One-line human status for a deal (live / expired / unbounded)."""
    exp = d.get("expires")
    if d.get("ends_when"):
        return f"live ({d['ends_when']})"
    if not exp:
        return "live (no expiry published)"
    exp_dt, gen_dt = _parse_ts(exp), _parse_ts(generated_utc)
    if exp_dt is None or gen_dt is None:
        return f"expires {exp}"
    return (f"live (through {exp})" if exp_dt >= gen_dt
            else f"EXPIRED {exp} but still shipped")


def cell(v):
    return str(v).replace("|", "/")


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
        A(f"| `{m.get('id')}` | {cell(m.get('name'))} | {ctx} | {eps} | "
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
        A(f"| {cell(name)} | {p.get('context')} | {p.get('input_per_1m')} | "
          f"{p.get('output_per_1m')} | {p.get('cache_read_per_1m')} | "
          f"{p.get('cache_write_per_1m')} | "
          f"{p.get('deal_badge', '')}{was} |")
    A("")
    A("## Deals")
    A("")
    for d in deals:
        mult = d.get("multiplier")
        eff = (f"~{1 / mult:.1f}x further" if mult else "?")
        A(f"### {cell(d.get('title'))}")
        A(f"- Discount: {d.get('discount_percent')}% off "
          f"(multiplier {mult}, every credit goes {eff}).")
        A(f"- Models: "
          f"{', '.join(f'`{m}`' for m in d.get('model_ids', []))}.")
        A(f"- Status: {deal_status(d, gen)}.")
        A(f"- Docs anchor: `#{d.get('docs_anchor')}`.")
        A("")
    A("## Price cross-check (deals bundle vs pricing table)")
    A("")
    cc = spec.get("price_crosscheck", {})
    agree, mism = cc.get("agree", []), cc.get("mismatch", [])
    unchk = cc.get("unchecked", [])
    A(f"Two independent website sources for the same pre-deal list "
      f"price: {len(agree)} fields agree, {len(mism)} mismatch, "
      f"{len(unchk)} unchecked (no table was-rates).")
    for m in mism:
        A(f"- MISMATCH `{m['model']}` ({m['deal']}) {m['field']}: "
          f"bundle {m['bundle_list']} vs table {m['table_was']} - one "
          f"source drifted, needs a human look.")
    for u in unchk:
        A(f"- unchecked `{u['model']}` ({u['deal']}): {u['reason']}.")
    if not mism and not unchk:
        A("- All deal list-rates agree with the pricing table.")
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
    reg_ids = {norm_mid(m.get("id", ""))
               for m in spec.get("models_available", [])}
    for d in deals:
        for m in d.get("model_ids", []):
            norm = norm_mid(m)
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
    A("PRICE CROSS-CHECK")
    cc = spec.get("price_crosscheck", {})
    A(f"  agree={len(cc.get('agree', []))} "
      f"mismatch={len(cc.get('mismatch', []))} "
      f"unchecked={len(cc.get('unchecked', []))}")
    for m in cc.get("mismatch", []):
        A(f"  MISMATCH {m['model']} {m['field']}: bundle {m['bundle_list']} "
          f"vs table {m['table_was']}")
    A("")
    A("AUTH GATES")
    for url, verdict in spec.get("auth", {}).items():
        A(f"  {url} -> {verdict}")
    return "\n".join(L) + "\n"


def norm_mid(mid):
    """Normalise a model id for cross-source joins: short name, lower,
    no :free/-free suffix, no dashes/spaces/dots."""
    s = str(mid or "").split("/")[-1].lower()
    for suf in (":free", "-free"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    for ch in ("-", " ", ".", "_"):
        s = s.replace(ch, "")
    return s


def atomic_write(path, data):
    # pid-suffixed tmp (no clobber on concurrent runs) + fsync before
    # rename, so a crash can never leave a half-written committed file.
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def validate_spec(spec, prior):
    """Returns (errors, warnings). Errors refuse the write (no --force)."""
    errors, warnings = [], []
    n_m = spec.get("model_count", 0)
    n_p = spec.get("prices_n", 0)
    n_d = len(spec.get("deals_now", []))
    if n_m == 0:
        errors.append("zero models (registry fetch/parse broke?)")
    if n_p == 0:
        errors.append("zero price rows (pricing table parse broke?)")
    if n_d == 0:
        errors.append("zero deals (deals bundle parse broke?)")
    urls = [e["url"] for e in spec.get("interesting_endpoints", [])]
    if not any(u.endswith("/provider/v1/models") for u in urls):
        errors.append("model-listing endpoint missing from interesting set")
    if not spec.get("auth"):
        errors.append("empty auth-gate table (probes all failed?)")
    if prior:
        pm = prior.get("model_count", 0) or 0
        pp = prior.get("prices_n", 0) or 0
        if pm and n_m < max(10, pm // 2):
            errors.append(f"models collapsed {pm} -> {n_m} "
                          "(registry drift or truncated fetch?)")
        elif pm and n_m < pm:
            warnings.append(f"models shrank {pm} -> {n_m}")
        if pp and n_p < max(10, pp // 2):
            errors.append(f"prices collapsed {pp} -> {n_p} "
                          "(table layout drift?)")
        elif pp and n_p < pp:
            warnings.append(f"prices shrank {pp} -> {n_p}")
        pd = len(prior.get("deals_now", []))
        if pd and n_d == 0:
            errors.append(f"deals went {pd} -> 0 (bundle parse broke?)")
        elif n_d < pd:
            warnings.append(f"deals shrank {pd} -> {n_d} (expiry? check)")
    return errors, warnings


def write_reports(spec, md_path, txt_path):
    if md_path:
        d = os.path.dirname(md_path)
        if d:
            os.makedirs(d, exist_ok=True)
        atomic_write(md_path, render_markdown(spec))
    if txt_path:
        d = os.path.dirname(txt_path)
        if d:
            os.makedirs(d, exist_ok=True)
        atomic_write(txt_path, render_text(spec))
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
    ap.add_argument("--force", action="store_true",
                    help="write outputs even when validation gates fail")
    args = ap.parse_args()
    if args.report_only:
        spec_path = args.spec or args.out
        try:
            spec = json.load(open(spec_path))
        except FileNotFoundError:
            print(f"no spec at {spec_path}; run a live pass first",
                  flush=True)
            return 2
        except json.JSONDecodeError as e:
            print(f"spec corrupt: {e}; refusing", flush=True)
            return 2
        spec_dir = os.path.dirname(os.path.abspath(spec_path))
        md = args.report or os.path.join(spec_dir, "REPORT.md")
        tx = args.report_txt or os.path.join(spec_dir, "REPORT.txt")
        print(f"report: {write_reports(spec, md, tx)}")
        return
    global CORPUS
    CORPUS = args.corpus
    os.makedirs(CORPUS, exist_ok=True)

    def save(name, data):
        # Atomic even for gitignored fetch cache: a truncated write must
        # never poison a later --spec-only run that reads this corpus.
        tmp = os.path.join(CORPUS, name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data or b"")
        os.replace(tmp, os.path.join(CORPUS, name))

    # Fetch-cache prune (oc-routes snapshot-prune lesson): hashed asset
    # filenames drift, so stale asset_*.js/docs_*.html would pile up and
    # the scrapers (which glob the whole dir) would read stale + fresh
    # together. Wipe the refetchable cache at the start of a live run;
    # committed snapshots (*.json) are kept. If fetching then fails, the
    # gates below refuse the snapshot overwrite instead of publishing
    # partial data.
    FETCH_CACHE_RES = ("asset_", "docs_2F", "cli.tgz", "cli.mjs",
                       "npm-latest.json", "sitemap.xml")
    discovery = {}
    if not args.no_fetch_sources and not args.spec_only:
        for fn in os.listdir(CORPUS):
            if fn.startswith(FETCH_CACHE_RES) and ".tmp" not in fn:
                try:
                    os.unlink(os.path.join(CORPUS, fn))
                except OSError:
                    pass
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
        derrs = []
        if not (discovery.get("sitemap") or {}).get("urls"):
            derrs.append("empty sitemap (offline?)")
        docs = discovery.get("docs") or {}
        bad_docs = [u for u, p in (docs.get("pages") or {}).items()
                    if p.get("status") != 200 or p.get("bytes", 0) < 50000]
        if bad_docs:
            derrs.append(f"docs pages failed/thin: {bad_docs} "
                          "(bot-wall or truncated fetch?)")
        if not (discovery.get("assets") or {}).get("assets"):
            derrs.append("zero website JS assets (markup drift?)")
        if not (discovery.get("cli") or {}).get("version"):
            derrs.append("CLI version unresolved (registry down?)")
        if not (discovery.get("cli") or {}).get("paths"):
            derrs.append("zero CLI bundle paths (tarball truncated?)")
        if derrs and not args.force:
            print("REFUSING to overwrite discovery snapshot:", flush=True)
            for e in derrs:
                print(f"  - {e}", flush=True)
            return 2
        atomic_write(os.path.join(CORPUS, "discovery.json"),
                     json.dumps(discovery, indent=2))
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
        # Models endpoint first: its snapshot feeds live probe-model
        # picking, so auth-gate verdicts stay endpoint-correct on churn.
        model_url = API_HOST + "/provider/v1/models"
        if model_url in cands:
            r = probe(model_url, save_name="provider-models.json")
            r["why"] = cands.pop(model_url)
            probe_results.append(r)
            fl = ",".join(k for k, v in r["flags"].items() if v)
            print(f"  {r['get_status']}            {model_url} "
                  f"[{fl or 'no-signal'}]", flush=True)
        live_probes = pick_probe_models()
        print(f"probing {len(cands)} candidates ...", flush=True)
        for url, why in sorted(cands.items()):
            name = None
            path = urllib.parse.urlparse(url).path
            do_post = live_probes.get(path)
            r = probe(url, save_name=name, do_post=do_post)
            r["why"] = why
            probe_results.append(r)
            fl = ",".join(k for k, v in r["flags"].items() if v)
            print(f"  {r['get_status']} "
                  f"{('POST:' + str(r['post_status'])) if r['post_status'] else '':10}"
                  f" {url} [{fl or 'no-signal'}]", flush=True)
        if not any(r["flags"].get("model_listing")
                   for r in probe_results) and not args.force:
            print("REFUSING to overwrite probes snapshot: "
                  "model listing missing (API down?)", flush=True)
            return 2
        atomic_write(os.path.join(CORPUS, "probes.json"),
                     json.dumps(probe_results, indent=2))
    else:
        try:
            probe_results = json.load(open(os.path.join(CORPUS,
                                                        "probes.json")))
        except FileNotFoundError:
            print(f"no probes snapshot in {CORPUS}; run a live pass "
                  "first (no --spec-only)", flush=True)
            return 2
        except json.JSONDecodeError as e:
            print(f"probes snapshot corrupt: {e}; refusing", flush=True)
            return 2

    spec = build_spec(probe_results, {
        "sitemap_urls": len((discovery.get("sitemap") or {}).get("urls",
                                                                 [])),
        "docs_paths": len((discovery.get("docs") or {}).get("paths", [])),
        "asset_js": (discovery.get("assets") or {}).get("assets"),
        "cli_version": (discovery.get("cli") or {}).get("version"),
    })
    # ---- validation gates: good data is never overwritten by bad/empty ----
    prior = None
    if os.path.exists(args.out):
        try:
            prior = json.load(open(args.out))
        except Exception as e:
            print(f"prior spec unreadable ({e}); treating as no prior",
                  flush=True)
    errors, warnings = validate_spec(spec, prior)
    for w in warnings:
        print(f"WARNING: {w}", flush=True)
    if errors and not args.force:
        print("REFUSING to overwrite spec/reports:", flush=True)
        for e in errors:
            print(f"  - {e}", flush=True)
        print("kept previous outputs; fix the cause or pass --force",
              flush=True)
        return 2
    for e in errors:
        print(f"WARNING (--force): {e}", flush=True)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if prior is not None:
        atomic_write(args.out + ".prev.json",
                     json.dumps(prior, indent=2))
    atomic_write(args.out, json.dumps(spec, indent=2))

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
