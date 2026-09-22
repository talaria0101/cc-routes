#!/usr/bin/env python3
"""Drive the real Command Code CLI through the capture hook (mitm/hook.mjs).

Matrix of CLI invocations, each with an isolated HOME, closed stdin and a
timeout. Every fetch/http call the CLI makes is logged as JSONL. No
credentials are used: auth-gated calls fail with 401 and that is exactly
what we record (quota instruments stop at the wall).

Setup per run (version-pinned, drift-proof):
  1. Resolve CLI version: $CLI_VERSION or latest from the npm registry.
  2. Download the tarball, extract, strip devDependencies (they reference
     private @commandcode/* packages that 404 on the public registry and
     are build-time only; the shipped bundle imports none of them).
  3. npm install production deps (bootstraps a portable npm if none works).

Usage:
  python3 drive.py [--work DIR] [--cli-version X.Y.Z] [--timeout S]
                   [--only help,version] [--runner bun|node]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import io
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hook.mjs")
NPM_TARBALL_URL = "https://registry.npmjs.org/npm/-/npm-11.6.0.tgz"

MATRIX = [
    (["--help"], 30),
    (["--version"], 30),
    (["--list-models"], 90),
    (["info"], 60),
    (["status"], 60),
    (["whoami"], 60),
    (["update", "--check-only"], 90),
    (["login"], 60),
    (["auth", "login"], 60),
    # provider OAuth logins: device-code init fires before any prompt
    # (copilot); browser-confirm ones stall headless and get killed.
    (["login", "copilot"], 45),
    (["login", "anthropic"], 45),
    (["login", "openai"], 45),
    (["-m", "no-such-model-xyz", "-p", "hi"], 60),
    (["-p", "say ok", "--no-session"], 90),
    (["taste", "--help"], 30),
    (["mcp", "--help"], 30),
    (["skills", "--help"], 30),
    (["mods", "--help"], 30),
    (["mcp", "list"], 60),
    (["mods", "list"], 60),
    (["skills", "list"], 60),
    (["taste", "list"], 60),
]


def fetch(url, timeout=30):
    req = urllib.request.Request(
        url, headers={"User-Agent": "cc-routes-mitm/1.0", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_version():
    meta = json.loads(fetch("https://registry.npmjs.org/command-code/latest"))
    return meta["version"]


def ensure_npm(work):
    """Return a working `npm` (node npm-cli.js). Bootstraps portable npm."""
    for cand in ("npm",):
        p = shutil.which(cand)
        if p:
            r = subprocess.run([p, "--version"], capture_output=True,
                               timeout=30)
            if r.returncode == 0:
                return [p]
    dest = os.path.join(work, "portable-npm")
    cli = os.path.join(dest, "package", "bin", "npm-cli.js")
    if not os.path.exists(cli):
        print("bootstrapping portable npm ...", flush=True)
        raw = fetch(NPM_TARBALL_URL, timeout=120)
        os.makedirs(dest, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
            tf.extractall(dest)
    node = shutil.which("node")
    return [node, cli]


def setup_cli(work, version, npm):
    pkgdir = os.path.join(work, f"cli-{version}", "package")
    marker = os.path.join(work, f"cli-{version}.ready")
    if os.path.exists(marker) and os.path.exists(
            os.path.join(pkgdir, "node_modules")):
        print(f"reusing {pkgdir}", flush=True)
        return os.path.join(pkgdir, "dist", "cli.mjs")
    print(f"fetching command-code@{version} ...", flush=True)
    meta = json.loads(fetch(
        f"https://registry.npmjs.org/command-code/{version}"))
    tarball = meta["dist"]["tarball"]
    raw = fetch(tarball, timeout=120)
    shutil.rmtree(os.path.join(work, f"cli-{version}"), ignore_errors=True)
    os.makedirs(pkgdir, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        tf.extractall(os.path.join(work, f"cli-{version}"))
    pj = os.path.join(pkgdir, "package.json")
    d = json.load(open(pj))
    d.pop("devDependencies", None)  # private build-time packages; 404 public
    json.dump(d, open(pj, "w"), indent=2)
    print("npm install (production) ...", flush=True)
    r = subprocess.run(
        npm + ["install", "--no-audit", "--no-fund", "--omit=dev",
               "--omit=optional"], cwd=pkgdir, capture_output=True,
        timeout=280)
    if r.returncode != 0:
        print(r.stderr.decode()[-2000:], file=sys.stderr)
        raise SystemExit("npm install failed")
    open(marker, "w").write(json.dumps({"version": version, "ts": time.time()}))
    return os.path.join(pkgdir, "dist", "cli.mjs")


def run_one(runner, cli, args, timeout, logpath, homedir, bindir, bindir_shim):
    env = dict(os.environ)
    env["HOME"] = homedir
    env["NO_COLOR"] = "1"
    # NOTE: CI is deliberately NOT set: the CLI disables its background
    # update system when CI is present (shouldSkipUpdateSystem).
    env.pop("CI", None)
    env["TERM"] = "dumb"
    env["CC_MITM_LOG"] = logpath
    # Working npm on PATH so `npm view` update checks execute for real;
    # NODE_OPTIONS propagates the hook into the npm child too, so npm's
    # own registry traffic is captured in the same log.
    env["PATH"] = bindir_shim + os.pathsep + env.get("PATH", "")
    # NODE_OPTIONS is always set so node-based children (npm, git hooks,
    # editors) inherit the hook too; the __ccHookLoaded guard prevents
    # double-wrapping if a runtime honors both preload and NODE_OPTIONS.
    env["NODE_OPTIONS"] = "--import " + HOOK
    if runner == "bun":
        cmd = ["bun", "--preload", HOOK, cli] + args
    else:
        cmd = ["node", cli] + args
    os.makedirs(homedir, exist_ok=True)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=timeout, env=env,
                           cwd=bindir)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = "timeout", (e.stdout or b""), (e.stderr or b"")
    dt = round(time.time() - t0, 1)
    with open(logpath + ".stdout.txt", "wb") as f:
        f.write(out or b"")
    with open(logpath + ".stderr.txt", "wb") as f:
        f.write(err or b"")
    return {"args": args, "rc": rc, "seconds": dt,
            "log": os.path.basename(logpath),
            "stdout_tail": (out or b"").decode(
                "utf-8", "replace")[-500:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=os.path.join(HERE, "work"))
    ap.add_argument("--captures", default=os.path.join(HERE, "captures"))
    ap.add_argument("--cli-version", default=None)
    ap.add_argument("--runner", default="bun", choices=("bun", "node"))
    ap.add_argument("--timeout-scale", type=float, default=1.0)
    ap.add_argument("--only", default=None,
                    help="comma-separated subset of matrix indices")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.captures, exist_ok=True)
    if args.runner == "bun" and not shutil.which("bun"):
        raise SystemExit("bun not on PATH")
    if args.runner == "node" and not shutil.which("node"):
        raise SystemExit("node not on PATH")

    version = args.cli_version or latest_version()
    print(f"CLI version: {version}", flush=True)
    npm = ensure_npm(args.work)
    cli = setup_cli(args.work, version, npm)

    only = None
    if args.only:
        only = {int(x) for x in args.only.split(",")}
    manifest = {"version": version, "runner": args.runner,
                "started": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                         time.gmtime()),
                "cli_bundle": cli,
                "runs": []}
    bindir = os.path.join(args.captures, "bin-empty")
    os.makedirs(bindir, exist_ok=True)
    # npm shim so update checks run for real (sandbox has no working npm)
    shimdir = os.path.join(args.work, "bin")
    os.makedirs(shimdir, exist_ok=True)
    npm_cli = os.path.join(args.work, "portable-npm", "package",
                           "bin", "npm-cli.js")
    node_bin = shutil.which("node")
    with open(os.path.join(shimdir, "npm"), "w") as f:
        f.write(f"#!/bin/sh\nexec {node_bin} {npm_cli} \"$@\"\n")
    os.chmod(os.path.join(shimdir, "npm"), 0o755)
    for i, (cmd_args, t) in enumerate(MATRIX):
        if only is not None and i not in only:
            continue
        name = f"run{i:02d}-{'-'.join(cmd_args).replace(' ','_')[:40] or 'x'}"
        logpath = os.path.join(args.captures, name + ".jsonl")
        for suf in (".jsonl", ".stdout.txt", ".stderr.txt"):
            try:
                os.unlink(os.path.join(args.captures, name + suf))
            except FileNotFoundError:
                pass
        home = os.path.join(args.work, f"home-{i:02d}")
        shutil.rmtree(home, ignore_errors=True)
        print(f"[{i}] {' '.join(cmd_args)} ...", flush=True)
        rec = run_one(args.runner, cli, cmd_args,
                      max(10, int(t * args.timeout_scale)),
                      logpath, home, bindir, shimdir)
        rec["name"] = name
        try:
            n = sum(1 for _ in open(logpath))
        except FileNotFoundError:
            n = 0
        rec["events"] = n
        print(f"    rc={rec['rc']} {rec['seconds']}s events={n}",
              flush=True)
        manifest["runs"].append(rec)
    manifest["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                         time.gmtime())
    with open(os.path.join(args.captures, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"done: {len(manifest['runs'])} runs -> {args.captures}")


if __name__ == "__main__":
    sys.exit(main())
