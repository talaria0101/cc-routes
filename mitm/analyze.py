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


def run_table_md(manifest):
    lines = ["| Run | Exit | Time | Events |",
             "|---|---|---|---|"
             ]
    for r in manifest.get("runs", []):
        cmd = "cmd " + " ".join(r["args"])
        lines.append(f"| `{cmd}` | {r['rc']} | {r['seconds']}s | "
                     f"{r['events']} |")
    return lines


def build_reports(manifest, out_eps, spawns, new, total_events,
                  bundle, tap_summary=(), unknown=()):
    """Returns (markdown, text) strings; callers write them (atomically)."""
    ver = manifest.get("version", "?")
    n_runs = len(manifest.get("runs", []))
    win = f"{manifest.get('started', '?')} .. " \
        f"{manifest.get('finished', '?')}"
    md = [f"# CLI drive report (v{ver}, "
          f"{manifest.get('runner', '?')} runner)",
          "",
          f"{n_runs} runs, {total_events} captured events, "
          f"{len(out_eps)} unique endpoints, {len(new)} new surface. "
          f"Window (UTC): {win}.",
          f"Bundle driven: `{bundle or 'n/a'}`.",
          "",
          "## Runs",
          ""]
    md += run_table_md(manifest)
    md += ["", "## Endpoints observed", "",
           "| Endpoint | Hits | Statuses | Seen in |",
           "|---|---|---|---|"
           ]
    for e in out_eps:
        runs = ", ".join(f"`cmd {' '.join(r.split())}`"[:60]
                           for r in e["runs"][:4])
        sts = ", ".join(str(s) for s in e["statuses"])
        md.append(f"| `{e['endpoint']}` | {e['hits']} | {sts} | "
                  f"{runs} |")
    md += ["", "## Subprocesses spawned", "",
           "| Call | Command | Hits | Runs |",
           "|---|---|---|---|"
           ]
    for (call, cmd), v in sorted(spawns.items()):
        runs = ", ".join(sorted(v["runs"])[:3])
        md.append(f"| {call} | `{cmd[:80]}` | {v['hits']} | {runs} |")
    md += ["", "## New surface (not in static tables)", ""]
    if new:
        for e in new:
            md.append(f"- `{e['endpoint']}` "
                      f"(hits {e['hits']}, statuses {e['statuses']}, "
                      f"runs: {', '.join(e['runs'])})")
    else:
        md.append("None: every runtime endpoint is already covered.")
    md += ["",
           "## Limits",
           "",
           "- No TCP bind in the sandbox: capture is in-process "
           "(`hook.mjs`), same plaintext visibility as a TLS proxy.",
           "- No ptys: ink raw-mode flows (`login`, `-p` sessions) die "
           "before interaction; auth-gated calls recorded as 401s.",
           "- Raw logs (`*.jsonl`, stdout/stderr) stay local; only "
           "curated summaries are committed.",
           "",
           "## Reproduce",
           "",
           "```sh",
           "python3 drive.py --work ./work --captures ./captures",
           "python3 analyze.py --captures ./captures "
           "--spec ../spec/api-spec.json",
           "```",
           ""]
    if tap_summary:
        md += ["", "## Tap host allowlist verdict", ""]
        for t in tap_summary:
            mark = "ok" if t["known"] else "UNKNOWN"
            why = KNOWN_HOSTS.get(t["host"], "NOT IN ALLOWLIST")
            md.append(f"- [{mark}] `{t['host']}` hits={t['hits']} "
                      f"via {','.join(t['evidence'])} ({why})")
        if unknown:
            md += ["", "Verdict: FAIL - unknown hosts need a reason "
                   "before they join the allowlist."]
        else:
            md += ["", "Verdict: PASS - no unknown hosts."]
    md += [""]
    tx = [f"CLI DRIVE REPORT v{ver} ({manifest.get('runner', '?')})", 
          f"{n_runs} runs, {total_events} events, "
          f"{len(out_eps)} endpoints, {len(new)} new. {win}",
          "", "RUNS"]
    for r in manifest.get("runs", []):
        tx.append(f"  cmd {' '.join(r['args']):44} rc={r['rc']!s:8} "
                  f"{r['seconds']}s events={r['events']}")
    tx += ["", "ENDPOINTS"]
    for e in out_eps:
        tx.append(f"  {e['hits']:3}  {e['endpoint'][:76]:76} "
                  f"{e['statuses']}")
    tx += ["", "SPAWNS"]
    for (call, cmd), v in sorted(spawns.items()):
        tx.append(f"  {v['hits']:3}  {call:10} {cmd[:70]}")
    tx += ["", "NEW SURFACE"]
    tx += [f"  {e['endpoint']} {e['statuses']}" for e in new] or \
        ["  none"]
    if tap_summary:
        tx += ["", "TAP HOSTS"]
        for t in tap_summary:
            mark = "ok" if t["known"] else "UNKNOWN"
            tx.append(f"  [{mark}] {t['host']:30} hits={t['hits']} "
                      f"{','.join(t['evidence'])}")
        tx.append("  verdict: " +
                  ("FAIL - unknown hosts" if unknown else "PASS"))
    return "\n".join(md), "\n".join(tx) + "\n"


# host -> why it is known. Derived from bundle pins + observed-and-explained
# traffic, never guessed: update with a reason when adding.
KNOWN_HOSTS = {
    "api.commandcode.ai": "provider API (bundle API_BASE_URLS + docs)",
    "api.axiom.co": "telemetry backend (bundle AXIOM_ENDPOINT; "
    "DNS-only without auth key, observed live)",
    "ingestion.claicode.com": "telemetry backend (bundle ingestion URL; "
    "DNS-only without auth key, observed live)",
    "commandcode.ai": "docs/site links opened from CLI text",
    "registry.npmjs.org": "update check via npm child; @byokkit "
    "provider lazy-installs",
    "github.com": "copilot provider GitHub device flow "
    "(POST /login/device/code, observed live)",
    "169.254.169.1": "sandbox egress proxy transport, not a destination",
    "127.0.0.1": "local-only/BYOK target (no listener here)",
    "localhost": "local-only/BYOK target (no listener here)",
}

# Transport-only evidence: the egress proxy address, never a destination.
TRANSPORT_IPS = {"169.254.169.1"}


def parse_netlogs(capdir):
    """Merge per-run CC_NETLOG files.

    Returns (hosts, execs, files): host -> {runs, evs, comms, hits},
    (exec_path, argv_str) -> {runs, hits}."""
    hosts, execs = {}, {}
    files = 0
    for path in sorted(glob.glob(os.path.join(capdir, "*.net.log"))):
        files += 1
        run = os.path.basename(path).replace(".net.log", "")
        try:
            lines = open(path).read().splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev, d = r.get("ev"), r.get("d", "")
            if ev == "exec":
                # exec lines carry top-level path/argv fields
                # (written raw, not inside "d").
                argv = " ".join(r.get("argv", [])[:3])[:100]
                k = (r.get("path", "?"), argv)
                s = execs.setdefault(k, {"runs": set(), "hits": 0})
                s["hits"] += 1
                s["runs"].add(run)
                continue
            host = None
            if ev in ("dns", "sni"):
                host = d.split(":")[0].lower()
            elif ev == "connect_line":
                host = d.split(":")[0].lower()
            elif ev == "connect":
                ip = d.split(":")[0]
                if ip in TRANSPORT_IPS:
                    continue
                host = ip
            if not host:
                continue
            h = hosts.setdefault(host, {"runs": set(), "evs": set(),
                                        "comms": set(), "hits": 0})
            h["hits"] += 1
            h["runs"].add(run)
            h["evs"].add(ev)
            h["comms"].add(r.get("comm", "?"))
    return hosts, execs, files


def atomic_write(path, data):
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def report_only(args):
    """Re-render human reports from committed curated JSONs only.

    Needs no raw logs (*.jsonl, *.net.log are gitignored) and no
    network: works on a fresh clone. Never touches the curated JSONs.
    """
    cap = args.captures
    try:
        manifest = json.load(open(os.path.join(cap, "manifest.json")))
        out_eps = json.load(open(os.path.join(cap, "endpoints.json")))
        spawns_j = json.load(open(os.path.join(cap, "spawns.json")))
        tap_summary = json.load(open(os.path.join(cap, "tap-hosts.json")))
    except FileNotFoundError as e:
        print(f"report-only needs curated JSONs: {e}", flush=True)
        return 2
    spawns = {}
    for s in spawns_j:
        spawns[(s["call"], s["cmd"])] = {
            "hits": s["hits"], "runs": set(s["runs"]),
            "args": set(s.get("args_sample", []))}
    unknown = [t["host"] for t in tap_summary if not t.get("known")]
    new = [e for e in out_eps if is_new_report_only(e)]
    total_events = sum(r.get("events", 0)
                       for r in manifest.get("runs", []))
    bundle = manifest.get("cli_bundle", "n/a")
    md_s, tx_s = build_reports(manifest, out_eps, spawns, new,
                               total_events, bundle, tap_summary, unknown)
    atomic_write(os.path.join(cap, "REPORT.md"), md_s)
    atomic_write(os.path.join(cap, "REPORT.txt"), tx_s)
    print(f"report-only: {len(manifest.get('runs', []))} runs, "
          f"{len(out_eps)} endpoints re-rendered -> {cap}")
    return 0


def is_new_report_only(e):
    if e.get("in_static_bundle") is False:
        return True
    if e.get("in_prior_spec") is False:
        return True
    if e.get("host") not in ("api.commandcode.ai", "registry.npmjs.org"):
        return e.get("in_static_bundle") is None
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", default=os.path.join(HERE, "captures"))
    ap.add_argument("--spec",
                    default=os.path.join(HERE, "..", "spec", "api-spec.json"))
    ap.add_argument("--no-report", action="store_true",
                    help="skip REPORT.md / REPORT.txt")
    ap.add_argument("--force", action="store_true",
                    help="write outputs even when validation floors fail")
    ap.add_argument("--min-events-per-run", type=float, default=1.0,
                    help="refuse to overwrite unless avg events/run >= this")
    ap.add_argument("--report-only", action="store_true",
                    help="re-render REPORT.md/.txt from committed curated "
                    "JSONs only (no raw logs, no network, no validation "
                    "floors); for fresh clones and offline use")
    args = ap.parse_args()

    if args.report_only:
        return report_only(args)

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
    # ---- netlog tap merge + host allowlist verdict ----
    tap_hosts, tap_execs, tap_files = parse_netlogs(args.captures)
    # OS-level exec events join the spawn table (call=execve): they catch
    # non-node children (git, tput, npm, sh) the JS hook cannot see.
    run_of_short = {os.path.splitext(k)[0]: v for k, v in run_of.items()}
    for (path, argv), v in tap_execs.items():
        k = ("execve", path + (" " + argv if argv else ""))
        s = spawns.setdefault(k, {"hits": 0, "runs": set(),
                                   "args": set()})
        s["hits"] += v["hits"]
        s["runs"].update(" ".join(run_of_short.get(r, [r]))
                           for r in v["runs"])
    hook_hosts = {e["host"] for e in out_eps}
    blind = {h: v for h, v in tap_hosts.items()
             if h not in hook_hosts and h not in TRANSPORT_IPS}
    unknown = {h: v for h, v in tap_hosts.items() if h not in KNOWN_HOSTS}
    tap_summary = [{"host": h, "hits": v["hits"],
                    "evidence": sorted(v["evs"]),
                    "runs": sorted(v["runs"])[:6],
                    "known": h in KNOWN_HOSTS,
                    "seen_by_hook": h in hook_hosts}
                   for h, v in sorted(tap_hosts.items())]

    # ---- validation floors: never overwrite good data with bad/empty ----
    n_runs = len(manifest.get("runs", []))
    avg = (total_events / n_runs) if n_runs else 0
    problems = []
    if n_runs == 0:
        problems.append("no runs in manifest")
    if total_events == 0:
        problems.append("zero captured events (hook dead?)")
    if avg < args.min_events_per_run:
        problems.append(f"avg events/run {avg:.2f} < floor "
                        f"{args.min_events_per_run} (partial capture?)")
    if len(out_eps) == 0:
        problems.append("zero unique endpoints (network down?)")
    if tap_files == 0:
        problems.append("no netlog tap files (LD_PRELOAD ineffective? "
                        "cross-check missing)")
    if problems and not args.force:
        print("REFUSING to overwrite curated outputs:", flush=True)
        for p in problems:
            print(f"  - {p}", flush=True)
        print("kept previous outputs; re-run or pass --force",
              flush=True)
        return 2
    for p in problems:
        print(f"WARNING (--force): {p}", flush=True)

    atomic_write(os.path.join(args.captures, "endpoints.json"),
                 json.dumps(out_eps, indent=2))
    atomic_write(os.path.join(args.captures, "tap-hosts.json"),
                 json.dumps(tap_summary, indent=2))

    # New = api/CLI surface absent from the static tables, plus any
    # non-npm third-party host the CLI itself contacts (npm-child
    # registry traffic is expected and reported separately).
    # Shared with --report-only via is_new_report_only (same predicate).
    new = [e for e in out_eps if is_new_report_only(e)]
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
    lines += ["## Tap host allowlist verdict", ""]
    if tap_hosts:
        for t in tap_summary:
            mark = "ok" if t["known"] else "UNKNOWN"
            why = KNOWN_HOSTS.get(t["host"], "NOT IN ALLOWLIST")
            lines.append(f"- [{mark}] `{t['host']}` hits={t['hits']} "
                         f"via {','.join(t['evidence'])} ({why})")
    else:
        lines.append("- no tap data (files missing or tap ineffective)")
    if blind:
        lines += ["",
                  "Hook blind spots (tap saw host, hook saw no URL):"]
        for h in sorted(blind):
            lines.append(f"- `{h}`")
    lines.append("")
    atomic_write(os.path.join(args.captures, "NEW_ENDPOINTS.md"),
                 "\n".join(lines))

    atomic_write(os.path.join(args.captures, "spawns.json"),
                 json.dumps([{"call": k[0], "cmd": k[1],
                              "hits": v["hits"],
                              "runs": sorted(v["runs"]),
                              "args_sample": sorted(v["args"])[:6]}
                             for k, v in sorted(spawns.items())],
                            indent=2))
    if not args.no_report:
        md_s, tx_s = build_reports(manifest, out_eps, spawns, new,
                                   total_events, bundle, tap_summary,
                                   unknown)
        atomic_write(os.path.join(args.captures, "REPORT.md"), md_s)
        atomic_write(os.path.join(args.captures, "REPORT.txt"), tx_s)
    # Exit contract: 0 whenever curated outputs were written (the unknown-
    # host verdict lives in NEW_ENDPOINTS.md + REPORT, it must not block a
    # refresh the way oc-routes learned); 2 only on validation refusal.
    if unknown:
        print(f"VERDICT: {len(unknown)} unknown host(s) need a reason "
              "before joining KNOWN_HOSTS: "
              f"{sorted(unknown)}", flush=True)
    print(f"events: {total_events}, unique endpoints: {len(out_eps)}, "
          f"new: {len(new)}, unique spawns: {len(spawns)}, "
          f"tap hosts: {len(tap_hosts)} ({len(unknown)} unknown)")
    for e in out_eps:
        print(f"  {e['hits']:3}  {e['endpoint']:80} "
              f"{e['statuses']}")
    print("spawns:")
    for (call, cmd), v in sorted(spawns.items()):
        print(f"  {v['hits']:3}  {call:10} {cmd[:90]} "
              f"[{', '.join(sorted(v['runs'])[:4])}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
