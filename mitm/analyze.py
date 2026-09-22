#!/usr/bin/env python3
"""Analyse MITM captures: unique endpoints hit by the CLI, diffed against
the static route table so genuinely new exposures stand out.

Reads captures/*.jsonl (+ manifest.json), writes:
  captures/endpoints.json  - every observed (method, host, path) with
                             per-run hits, statuses, body sizes
  captures/NEW_ENDPOINTS.md - runtime-observed endpoints NOT present in
                             the static bundle route table or the
                             previous cc-routes spec probe set

Static route table is re-extracted from the CLI bundle under test
(mitm/work/cli-<ver>/package/dist/cli.mjs), so drift in the bundle
cannot hide new endpoints.

Usage: python3 analyze.py [--captures DIR] [--spec ../spec/api-spec.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PATH_RE = re.compile(r'"/(?:provider|internal|alpha|beta)'
                     r'(?:/[A-Za-z0-9/_\-:{}.]+)?"')


def load_jsonl(path):
    recs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return recs


def key_of(method, url):
    try:
        u = urllib.parse.urlparse(url)
        if not u.scheme.startswith("http"):
            return None  # data:, blob:, file: ... runtime noise
        return (method.upper(), u.hostname or "", u.path or "/",
                u.query)
    except Exception:
        return None


def static_routes(cli_bundle):
    routes = set()
    try:
        t = open(cli_bundle, errors="ignore").read()
    except FileNotFoundError:
        return routes
    for m in PATH_RE.finditer(t):
        routes.add(m.group(0).strip('"'))
    return routes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", default=os.path.join(HERE, "captures"))
    ap.add_argument("--spec",
                    default=os.path.join(HERE, "..", "spec", "api-spec.json"))
    args = ap.parse_args()

    try:
        manifest = json.load(open(
            os.path.join(args.captures, "manifest.json")))
    except FileNotFoundError:
        manifest = {"runs": []}
    run_of = {}
    for r in manifest.get("runs", []):
        run_of[r["log"]] = r["args"]

    eps = {}  # (method, host, path) -> info
    spawns = {}  # (call, cmd) -> {runs, hits, args_sample}
    total_events = 0
    for path in sorted(glob.glob(os.path.join(args.captures, "*.jsonl"))):
        run_args = run_of.get(os.path.basename(path), ["?"])
        for rec in load_jsonl(path):
            if rec.get("type") == "spawn":
                k = (rec.get("call"), rec.get("cmd"))
                s = spawns.setdefault(k, {"hits": 0, "runs": set(),
                                           "args": set()})
                s["hits"] += 1
                s["runs"].add(" ".join(run_args))
                for a in (rec.get("args") or [])[:4]:
                    s["args"].add(a)
                total_events += 1
                continue
            if rec.get("type") not in ("fetch", "http.request"):
                continue
            if rec.get("phase") not in ("request-response", "response",
                                        "error"):
                continue
            total_events += 1
            k = key_of(rec.get("method", "?"), rec.get("url", ""))
            if not k:
                continue
            method, host, pth, query = k
            key = f"{method} {host}{pth}"
            e = eps.setdefault(key, {"method": method, "host": host,
                                     "path": pth, "queries": set(),
                                     "statuses": set(), "runs": set(),
                                     "hits": 0, "auth_401": False})
            e["hits"] += 1
            e["runs"].add(" ".join(run_args))
            if query:
                e["queries"].add(query[:80])
            if rec.get("status") is not None:
                e["statuses"].add(rec["status"])
                if rec["status"] == 401:
                    e["auth_401"] = True
            if rec.get("phase") == "error":
                e["statuses"].add("ERR:" + str(rec.get("error"))[:60])

    # Static table from the bundle actually driven (path in manifest).
    bundle = manifest.get("cli_bundle")
    if not bundle:
        for cand in glob.glob(os.path.join(HERE, "work", "cli-*",
                                           "package", "dist", "cli.mjs")):
            bundle = cand
    static = static_routes(bundle) if bundle else set()

    try:
        spec = json.load(open(args.spec))
        spec_known = {a["url"] for a in spec.get("all_probed", [])}
    except FileNotFoundError:
        spec_known = set()

    out_eps = []
    for key in sorted(eps):
        e = eps[key]
        full_api = f"https://api.commandcode.ai{e['path']}" \
            if e["host"] == "api.commandcode.ai" else None
        out_eps.append({
            "endpoint": key,
            "host": e["host"],
            "path": e["path"],
            "hits": e["hits"],
            "statuses": sorted(e["statuses"], key=str),
            "runs": sorted(e["runs"]),
            "in_static_bundle": (e["path"] in static
                                 if e["host"] == "api.commandcode.ai"
                                 else None),
            "in_prior_spec": (full_api in spec_known
                              if full_api else None),
            "auth_gate_observed": e["auth_401"],
        })
    with open(os.path.join(args.captures, "endpoints.json"), "w") as f:
        json.dump(out_eps, f, indent=2)

    # New = api/CLI surface absent from the static tables, plus any
    # non-npm third-party host the CLI itself contacts (npm-child
    # registry traffic is expected and reported separately).
    def is_new(e):
        if e["in_static_bundle"] is False or e["in_prior_spec"] is False:
            return True
        if e["host"] not in ("api.commandcode.ai", "registry.npmjs.org"):
            return e["in_static_bundle"] is None  # unseen third party
        return False
    new = [e for e in out_eps if is_new(e)]
    lines = ["# Runtime-observed endpoints missing from static tables",
             "",
             f"Bundle: `{bundle or 'n/a'}`.",
             f"Observed {len(out_eps)} unique endpoints "
             f"({total_events} events); "
             f"{len(new)} not covered by static/spec tables.",
             ""]
    for e in new:
        lines.append(f"## `{e['endpoint']}`")
        lines.append(f"- hits: {e['hits']}, statuses: {e['statuses']}")
        lines.append(f"- in static bundle: {e['in_static_bundle']}, "
                     f"in prior spec: {e['in_prior_spec']}, "
                     f"401 seen: {e['auth_gate_observed']}")
        lines.append(f"- runs: {', '.join(e['runs'])}")
        lines.append("")
    if len(new) == 0:
        lines.append("None: every runtime endpoint is already in the "
                     "static tables.")
        lines.append("")
    with open(os.path.join(args.captures, "NEW_ENDPOINTS.md"), "w") as f:
        f.write("\n".join(lines))

    with open(os.path.join(args.captures, "spawns.json"), "w") as f:
        json.dump([{"call": k[0], "cmd": k[1], "hits": v["hits"],
                    "runs": sorted(v["runs"]),
                    "args_sample": sorted(v["args"])[:6]}
                   for k, v in sorted(spawns.items())], f, indent=2)
    print(f"events: {total_events}, unique endpoints: {len(out_eps)}, "
          f"new: {len(new)}, unique spawns: {len(spawns)}")
    for e in out_eps:
        print(f"  {e['hits']:3}  {e['endpoint']:80} "
              f"{e['statuses']}")
    print("spawns:")
    for (call, cmd), v in sorted(spawns.items()):
        print(f"  {v['hits']:3}  {call:10} {cmd[:90]} "
              f"[{', '.join(sorted(v['runs'])[:4])}]")


if __name__ == "__main__":
    raise SystemExit(main())
